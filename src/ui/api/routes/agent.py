from __future__ import annotations

import json
import logging
import os


from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from google import genai
from google.genai import types
from pydantic import BaseModel

from src.ui.api.auth import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_HISTORY_TURNS = 20


class ChatRequest(BaseModel):
    market: str
    message: str
    history: list[dict[str, str]] = []


def _get_gemini_key(request: Request) -> str:
    app = getattr(request.app.state, "app", None)
    key = ""
    if app and hasattr(app, "settings"):
        key = getattr(app.settings, "agent", {})
        if isinstance(key, dict):
            key = key.get("gemini_api_key", "")
        else:
            key = getattr(key, "gemini_api_key", "")
    if not key:
        key = os.environ.get("GEMINI_API_KEY", "")
    return key


def _build_system_prompt(request: Request, market: str, user_id: int) -> str:
    app = getattr(request.app.state, "app", None)
    lines = [
        "당신은 암호화폐 투자 분석 AI 어시스턴트입니다.",
        "",
    ]

    # Market info
    korean_name = market.replace("KRW-", "")
    price = "N/A"
    change_rate = "N/A"
    volume_24h = "N/A"

    if app:
        if hasattr(app, "collector"):
            korean_name = app.collector.korean_names.get(market, korean_name)
        if hasattr(app, "upbit_ws"):
            snapshot = app.upbit_ws.get_snapshot()
            ticker = snapshot.get(market, {})
            if ticker:
                price = f"₩{float(ticker.get('price', 0)):,.0f}"
                cr = float(ticker.get("change_rate", 0)) * 100
                change_rate = f"{'+' if cr >= 0 else ''}{cr:.2f}%"
                vol = float(ticker.get("acc_trade_price_24h", 0))
                if vol >= 1_000_000_000_000:
                    volume_24h = f"₩{vol / 1_000_000_000_000:.1f}조"
                elif vol >= 100_000_000:
                    volume_24h = f"₩{vol / 100_000_000:.0f}억"
                else:
                    volume_24h = f"₩{vol / 10_000:.0f}만"

    lines.append("현재 코인 정보:")
    lines.append(f"- 마켓: {market} ({korean_name})")
    lines.append(f"- 현재가: {price} (전일 대비 {change_rate})")
    lines.append(f"- 24시간 거래대금: {volume_24h}")

    # Position info
    if app and hasattr(app, "user_accounts"):
        account = app.user_accounts.get(user_id)
        if account:
            pos = account.positions.get(market)
            if pos:
                lines.append("")
                lines.append("보유 포지션:")
                lines.append(f"- 보유수량: {pos.quantity}")
                lines.append(f"- 평균매수가: ₩{float(pos.entry_price):,.0f}")
                lines.append(f"- 미실현손익: ₩{float(pos.unrealized_pnl):,.0f}")
                lines.append(f"- 투자금액: ₩{float(pos.total_invested):,.0f}")

    lines.append("")
    lines.append("역할 및 응답 규칙:")
    lines.append("- Google 검색을 활용하여 최신 뉴스, 커뮤니티 동향, 시장 분석을 참고하세요")
    lines.append("- 한국어로 응답하세요")
    lines.append("- 투자 조언이 아닌 정보 제공임을 한 줄로 명시하세요")
    lines.append("")
    lines.append("응답 형식 (반드시 아래 순서와 형식을 따르세요):")
    lines.append("1. 첫 줄에 매매 추천을 한 줄로: `**추천: 매수 / 매도 / 관망**` (이유 한 줄 포함)")
    lines.append("2. `## 시장 동향` — 현재 가격 흐름과 추세를 2~3문장으로")
    lines.append("3. `## 주요 뉴스` — 최근 관련 뉴스 핵심 2~3개를 글머리 기호로")
    lines.append("4. `## 커뮤니티 여론` — 투자자 심리를 1~2문장으로")
    lines.append("")
    lines.append("전체 응답은 200자 이내로 간결하게 작성하세요. 긴 설명은 금지합니다.")

    return "\n".join(lines)


@router.post("/chat")
async def agent_chat(
    request: Request,
    body: ChatRequest,
    user: dict = Depends(get_current_user),
) -> StreamingResponse:
    api_key = _get_gemini_key(request)
    if not api_key:
        raise HTTPException(status_code=503, detail="Gemini API key not configured")

    user_id = user["id"]
    system_prompt = _build_system_prompt(request, body.market, user_id)

    # Build conversation contents
    history = body.history[-MAX_HISTORY_TURNS * 2 :]
    contents: list[types.Content] = []
    for msg in history:
        role = "user" if msg.get("role") == "user" else "model"
        contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))
    contents.append(types.Content(role="user", parts=[types.Part(text=body.message)]))

    client = genai.Client(api_key=api_key)

    async def stream_generator():
        try:
            response = client.models.generate_content_stream(
                model="gemini-2.5-flash",
                contents=contents,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    tools=[types.Tool(google_search=types.GoogleSearch())],
                ),
            )
            grounding_sources = []
            for chunk in response:
                if chunk.text:
                    yield f"data: {json.dumps({'token': chunk.text})}\n\n"
                # Collect grounding metadata
                if (
                    chunk.candidates
                    and chunk.candidates[0].grounding_metadata
                    and chunk.candidates[0].grounding_metadata.grounding_chunks
                ):
                    for gc in chunk.candidates[0].grounding_metadata.grounding_chunks:
                        if gc.web and gc.web.uri:
                            source = {"url": gc.web.uri}
                            if gc.web.title:
                                source["title"] = gc.web.title
                            grounding_sources.append(source)

            if grounding_sources:
                # Deduplicate by URL
                seen = set()
                unique = []
                for s in grounding_sources:
                    if s["url"] not in seen:
                        seen.add(s["url"])
                        unique.append(s)
                yield f"data: {json.dumps({'grounding_sources': unique})}\n\n"

            yield "data: [DONE]\n\n"
        except Exception:
            logger.exception("Gemini streaming error")
            yield f"data: {json.dumps({'error': 'AI 응답 생성 중 오류가 발생했습니다.'})}\n\n"
            yield "data: [DONE]\n\n"

    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

# AI Agent Chat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an AI agent chat panel to the Exchange page that analyzes crypto trends via Gemini API with Google Search Grounding and supports free-form conversation.

**Architecture:** FastAPI SSE endpoint receives chat requests with market + history, injects real-time coin data into a system prompt, streams Gemini responses back. Frontend renders a chat UI below the OrderPanel with streaming token display.

**Tech Stack:** google-genai (Gemini 2.5 Flash), FastAPI StreamingResponse (SSE), React useState + fetch ReadableStream

---

## File Structure

| File | Action | Responsibility |
|---|---|---|
| `src/ui/api/routes/agent.py` | Create | SSE chat endpoint, system prompt construction, Gemini streaming |
| `src/ui/api/server.py` | Modify | Register agent router |
| `config/settings.yaml` | Modify | Add `gemini_api_key` field |
| `pyproject.toml` | Modify | Add `google-genai` dependency |
| `src/ui/frontend/src/pages/Exchange.tsx` | Modify | Add AgentChat component inside ExchangeDetail |
| `src/ui/frontend/src/index.css` | Modify | Chat UI styles |
| `tests/unit/test_agent_route.py` | Create | Backend endpoint tests |

---

### Task 1: Add google-genai dependency and config

**Files:**
- Modify: `pyproject.toml:5-23`
- Modify: `config/settings.yaml:49-50`

- [ ] **Step 1: Add google-genai to pyproject.toml**

In `pyproject.toml`, add `"google-genai>=1.0"` to the `dependencies` list:

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "websockets>=14.0",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "httpx>=0.28",
    "lightgbm>=4.5",
    "xgboost>=2.1",
    "scikit-learn>=1.6",
    "pandas>=2.2",
    "numpy>=2.1",
    "ta>=0.11",
    "joblib>=1.4",
    "aiosqlite>=0.21",
    "pyyaml>=6.0",
    "bcrypt>=4.2",
    "PyJWT>=2.9",
    "google-genai>=1.0",
]
```

- [ ] **Step 2: Add gemini_api_key to settings.yaml**

Append at the end of `config/settings.yaml`:

```yaml
agent:
  gemini_api_key: ""
```

- [ ] **Step 3: Install dependencies**

Run: `uv sync`
Expected: successful install including google-genai

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml config/settings.yaml uv.lock
git commit -m "feat: add google-genai dependency and agent config"
```

---

### Task 2: Create agent chat SSE endpoint

**Files:**
- Create: `src/ui/api/routes/agent.py`
- Modify: `src/ui/api/server.py:11-35`

- [ ] **Step 1: Create `src/ui/api/routes/agent.py`**

```python
from __future__ import annotations

import json
import logging
import os
from typing import Any

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

    # ML signal info
    if app and hasattr(app, "signal_repo"):
        # Signal data is async, but system prompt is built synchronously.
        # We'll inject signal context only if cached data is available.
        pass

    lines.append("")
    lines.append("역할:")
    lines.append("- Google 검색을 활용하여 최신 뉴스, 커뮤니티 동향, 시장 분석을 참고하세요")
    lines.append("- 상승세/하락세 판단, 매수/매도/관망 추천을 근거와 함께 제시하세요")
    lines.append("- 투자 조언이 아닌 정보 제공임을 명시하세요")
    lines.append("- 한국어로 응답하세요")

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
```

- [ ] **Step 2: Register agent router in server.py**

In `src/ui/api/server.py`, add the import and include_router.

Add to imports (after line 13):
```python
from src.ui.api.routes import agent as agent_router
```

Add after the exchange router line (after line 35):
```python
    app.include_router(agent_router.router, prefix="/api/agent", tags=["agent"])
```

- [ ] **Step 3: Verify the server starts**

Run: `uv run python -c "from src.ui.api.server import create_app; app = create_app(); print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/ui/api/routes/agent.py src/ui/api/server.py
git commit -m "feat: add AI agent chat SSE endpoint with Gemini"
```

---

### Task 3: Write backend tests

**Files:**
- Create: `tests/unit/test_agent_route.py`

- [ ] **Step 1: Write tests for agent route**

Create `tests/unit/test_agent_route.py`:

```python
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.ui.api.server import create_app


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_header():
    from src.ui.api.auth import create_access_token
    token = create_access_token(user_id=1)
    return {"Authorization": f"Bearer {token}"}


def test_agent_chat_requires_auth(client):
    res = client.post("/api/agent/chat", json={"market": "KRW-BTC", "message": "hi"})
    assert res.status_code == 401


def test_agent_chat_no_api_key(client, auth_header):
    """Returns 503 when no Gemini API key is configured."""
    res = client.post(
        "/api/agent/chat",
        json={"market": "KRW-BTC", "message": "hi", "history": []},
        headers=auth_header,
    )
    assert res.status_code == 503
    assert "Gemini API key" in res.json()["detail"]


def test_agent_chat_validation(client, auth_header):
    """Missing required fields returns 422."""
    res = client.post(
        "/api/agent/chat",
        json={},
        headers=auth_header,
    )
    assert res.status_code == 422
```

- [ ] **Step 2: Run tests**

Run: `uv run pytest tests/unit/test_agent_route.py -v`
Expected: 3 tests PASS

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_agent_route.py
git commit -m "test: add agent chat endpoint tests"
```

---

### Task 4: Add AgentChat component to Exchange page

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx:680-936`

- [ ] **Step 1: Add AgentChat component**

In `Exchange.tsx`, add the `AgentChat` function component **before** the `ExchangeDetail` component (before line 682). Insert the following:

```tsx
/* ── AgentChat ─────────────────────────────────── */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { title: string; url: string }[];
}

function AgentChat({ market, accessToken }: { market: string; accessToken: string | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevMarketRef = useRef(market);

  const API_BASE = import.meta.env.VITE_API_URL || "";

  // Reset messages when market changes
  useEffect(() => {
    if (prevMarketRef.current !== market) {
      setMessages([]);
      setInput("");
      prevMarketRef.current = market;
    }
  }, [market]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming || !accessToken) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    // Build history from existing messages (last 20 turns)
    const history = [...messages, userMsg]
      .slice(-40)
      .map((m) => ({ role: m.role, content: m.content }));

    // Add placeholder assistant message
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ market, message: text, history: history.slice(0, -1) }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "요청 실패" }));
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `오류: ${err.detail || "AI 응답을 받지 못했습니다."}`,
          };
          return updated;
        });
        setIsStreaming(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) { setIsStreaming(false); return; }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const payload = trimmed.slice(6);

          if (payload === "[DONE]") continue;

          try {
            const data = JSON.parse(payload);
            if (data.token) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + data.token };
                return updated;
              });
            }
            if (data.grounding_sources) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, sources: data.grounding_sources };
                return updated;
              });
            }
            if (data.error) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + `\n\n${data.error}` };
                return updated;
              });
            }
          } catch {
            // skip malformed JSON
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "네트워크 오류가 발생했습니다.",
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  }, [isStreaming, accessToken, messages, market, API_BASE]);

  const handleAnalyze = () => {
    sendMessage("이 코인의 현재 트렌드, 전망, 커뮤니티 여론을 분석하고 매매 추천을 해주세요.");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  return (
    <div className="panel agent-chat">
      <div className="agent-chat-header" onClick={() => setIsCollapsed(!isCollapsed)}>
        <span className="agent-chat-title">AI 에이전트</span>
        <span className="agent-chat-toggle">{isCollapsed ? "▼" : "▲"}</span>
      </div>
      {!isCollapsed && (
        <div className="agent-chat-body">
          {messages.length === 0 && !isStreaming && (
            <div className="agent-chat-empty">
              <button className="btn btn-accent agent-analyze-btn" onClick={handleAnalyze}>
                분석 요청
              </button>
              <p className="agent-chat-hint">AI에게 이 코인의 분석을 요청하세요</p>
            </div>
          )}
          {messages.length > 0 && (
            <div className="agent-chat-messages">
              {messages.map((msg, i) => (
                <div key={i} className={`agent-msg agent-msg-${msg.role}`}>
                  <div className="agent-msg-content">
                    {msg.content}
                    {msg.role === "assistant" && isStreaming && i === messages.length - 1 && (
                      <span className="streaming-cursor" />
                    )}
                  </div>
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="agent-msg-sources">
                      {msg.sources.map((s, j) => (
                        <a key={j} href={s.url} target="_blank" rel="noopener noreferrer" className="agent-source-chip">
                          {s.title || new URL(s.url).hostname}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
          <form className="agent-input-area" onSubmit={handleSubmit}>
            <input
              className="agent-input"
              type="text"
              placeholder="질문을 입력하세요..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isStreaming}
            />
            <button className="btn btn-accent agent-send-btn" type="submit" disabled={isStreaming || !input.trim()}>
              전송
            </button>
          </form>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Wire AgentChat into ExchangeDetail**

In the `ExchangeDetail` component's return block (around line 930-936), add `AgentChat` after the OrderPanel:

Replace:
```tsx
      {/* Order Panel */}
      <div style={{ marginTop: 16 }}>
        <OrderPanel market={market} price={curPrice} position={position} cashBalance={cashBalance} />
      </div>
    </div>
```

With:
```tsx
      {/* Order Panel */}
      <div style={{ marginTop: 16 }}>
        <OrderPanel market={market} price={curPrice} position={position} cashBalance={cashBalance} />
      </div>

      {/* AI Agent Chat */}
      <div style={{ marginTop: 16 }}>
        <AgentChat market={market} accessToken={auth.accessToken} />
      </div>
    </div>
```

To access `auth`, add it to the `ExchangeDetail` component. Update the component to destructure `auth` from `useAuthContext()`:

Find in `ExchangeDetail` (around line 695):
```tsx
  const { api } = useAuthContext();
```
Replace with:
```tsx
  const { api, auth } = useAuthContext();
```

- [ ] **Step 3: Verify no TypeScript errors**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx
git commit -m "feat: add AgentChat component to Exchange page"
```

---

### Task 5: Add chat UI styles

**Files:**
- Modify: `src/ui/frontend/src/index.css` (append at end)

- [ ] **Step 1: Add agent chat styles**

Append the following at the end of `src/ui/frontend/src/index.css`:

```css
/* ═══════════════════════════════════════════════════
   Agent Chat
   ═══════════════════════════════════════════════════ */

.agent-chat {
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.agent-chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 16px;
  background: var(--bg-card);
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid var(--border);
}

.agent-chat-title {
  font-family: "Outfit", sans-serif;
  font-weight: 600;
  font-size: 0.9rem;
  color: var(--accent);
}

.agent-chat-toggle {
  color: var(--text-muted);
  font-size: 0.75rem;
}

.agent-chat-body {
  background: var(--bg-raised);
}

.agent-chat-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 24px 16px;
}

.agent-analyze-btn {
  padding: 10px 24px;
  font-size: 0.9rem;
}

.agent-chat-hint {
  color: var(--text-muted);
  font-size: 0.8rem;
  margin: 0;
}

.agent-chat-messages {
  max-height: 400px;
  overflow-y: auto;
  padding: 12px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-msg {
  max-width: 85%;
  animation: fadeIn 0.15s ease;
}

.agent-msg-user {
  align-self: flex-end;
}

.agent-msg-assistant {
  align-self: flex-start;
}

.agent-msg-content {
  padding: 10px 14px;
  border-radius: 12px;
  font-size: 0.85rem;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.agent-msg-user .agent-msg-content {
  background: var(--accent-deep);
  color: #fff;
  border-bottom-right-radius: 4px;
}

.agent-msg-assistant .agent-msg-content {
  background: var(--bg-card);
  color: var(--text);
  border: 1px solid var(--border);
  border-bottom-left-radius: 4px;
}

.agent-msg-sources {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 6px;
}

.agent-source-chip {
  display: inline-block;
  padding: 2px 8px;
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: 0.7rem;
  color: var(--accent);
  text-decoration: none;
  transition: border-color 0.15s;
}

.agent-source-chip:hover {
  border-color: var(--accent);
}

.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  background: var(--accent);
  margin-left: 2px;
  vertical-align: text-bottom;
  animation: blink 0.8s step-end infinite;
}

@keyframes blink {
  50% { opacity: 0; }
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(4px); }
  to { opacity: 1; transform: translateY(0); }
}

.agent-input-area {
  display: flex;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-card);
}

.agent-input {
  flex: 1;
  padding: 8px 12px;
  background: var(--bg-raised);
  border: 1px solid var(--border);
  border-radius: 8px;
  color: var(--text);
  font-size: 0.85rem;
  outline: none;
  transition: border-color 0.15s;
}

.agent-input:focus {
  border-color: var(--accent);
}

.agent-input:disabled {
  opacity: 0.5;
}

.agent-send-btn {
  padding: 8px 16px;
  font-size: 0.85rem;
  white-space: nowrap;
}

.agent-send-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
```

- [ ] **Step 2: Verify styles load**

Run: `cd src/ui/frontend && npx vite build`
Expected: build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/index.css
git commit -m "feat: add agent chat UI styles"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Run all backend tests**

Run: `uv run pytest tests/ -v --timeout=30`
Expected: all tests pass

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/ui/api/routes/agent.py`
Expected: no errors

- [ ] **Step 3: Run frontend build**

Run: `cd src/ui/frontend && npx vite build`
Expected: build succeeds without errors

- [ ] **Step 4: Final commit (if any lint fixes needed)**

```bash
git add -A
git commit -m "fix: lint and build fixes for agent chat"
```

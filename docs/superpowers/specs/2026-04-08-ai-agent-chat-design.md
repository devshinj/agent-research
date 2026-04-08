# AI Agent Chat — Design Spec

## Overview

거래소 페이지(Exchange)의 매수/매도 패널 아래에 AI 에이전트 채팅 기능을 추가한다.
선택된 코인에 대해 Gemini API(Google Search Grounding 포함)를 활용하여 트렌드, 전망, 커뮤니티 여론을 분석하고, 매수/매도/관망 추천을 근거와 함께 제공한 후 자유 채팅이 가능하다.

## Architecture

```
[Exchange.tsx]                [FastAPI]                    [Gemini API]
     │                           │                             │
     │  POST /api/agent/chat     │                             │
     │  {market, message,        │                             │
     │   history[]}              │                             │
     │ ────────────────────────► │  시스템 프롬프트 구성         │
     │                           │  (시세 + 포지션 + 시그널)     │
     │                           │                             │
     │                           │  generateContentStream()    │
     │                           │ ──────────────────────────► │
     │                           │                             │
     │  SSE: text/event-stream   │  ◄──── 스트리밍 청크 ─────── │
     │ ◄──────────────────────── │                             │
     │  data: {"token": "..."}   │                             │
     │  data: {"token": "..."}   │                             │
     │  data: [DONE]             │                             │
```

통신 방식: SSE (Server-Sent Events). 프론트엔드가 `fetch` + `ReadableStream`으로 토큰 단위 수신.

## Backend

### Endpoint

```
POST /api/agent/chat
Content-Type: application/json
Authorization: Bearer <token>
Response: text/event-stream
```

### Request Body

```json
{
  "market": "KRW-BTC",
  "message": "이 코인 지금 사도 될까?",
  "history": [
    {"role": "user", "content": "..."},
    {"role": "assistant", "content": "..."}
  ]
}
```

- `market`: 현재 선택된 코인 마켓 코드
- `message`: 사용자 입력 메시지
- `history`: 이전 대화 내역 배열 (최대 20턴, 프론트에서 관리)

### SSE Response Format

```
data: {"token": "비트코인은"}
data: {"token": " 현재"}
data: {"token": " 상승세를 보이고 있습니다."}
data: {"grounding_sources": [{"title": "...", "url": "..."}]}
data: [DONE]
```

- 각 줄은 `data: ` 접두사 + JSON
- 스트리밍 완료 시 `data: [DONE]` 전송
- Grounding 출처가 있으면 `[DONE]` 직전에 `grounding_sources` 이벤트 전송

### System Prompt Construction

서버가 요청 시점에 자동으로 다음 데이터를 수집하여 시스템 프롬프트에 주입:

1. **시세 정보**: 현재가, 등락률, 24시간 거래대금 (upbit_ws 또는 upbit API에서)
2. **포지션 정보** (있을 경우): 보유수량, 평균매수가, 미실현손익, 투자금액
3. **ML 시그널** (있을 경우): 최신 스크리닝/시그널 결과

시스템 프롬프트 템플릿:
```
당신은 암호화폐 투자 분석 AI 어시스턴트입니다.

현재 코인 정보:
- 마켓: {market} ({korean_name})
- 현재가: ₩{price} (전일 대비 {change_rate})
- 24시간 거래대금: {volume_24h}
{position_info}
{signal_info}

역할:
- Google 검색을 활용하여 최신 뉴스, 커뮤니티 동향, 시장 분석을 참고하세요
- 상승세/하락세 판단, 매수/매도/관망 추천을 근거와 함께 제시하세요
- 투자 조언이 아닌 정보 제공임을 명시하세요
- 한국어로 응답하세요
```

### Gemini Configuration

- **패키지**: `google-genai`
- **모델**: `gemini-2.5-flash`
- **도구**: `[{"google_search": {}}]` (Google Search Grounding)
- **API 키**: `.env`의 `GEMINI_API_KEY` → settings.yaml에서 로드
- **히스토리 제한**: 최대 20턴 (초과 시 오래된 턴부터 제거)

### New File

`src/ui/api/routes/agent.py`:
- `POST /api/agent/chat` 엔드포인트
- `get_current_user` 의존성으로 인증
- `StreamingResponse(media_type="text/event-stream")` 반환
- Gemini 클라이언트 초기화 및 스트리밍 호출 로직

### Modified Files

- `src/ui/api/server.py`: agent 라우터 등록
- `config/settings.yaml`: `gemini_api_key` 필드 추가

### Dependencies

- `google-genai`: pyproject.toml에 추가

## Frontend

### UI Component: AgentChat

Exchange 페이지의 `ExchangeDetail` 컴포넌트 내부, OrderPanel 아래에 배치.

#### Structure

```
┌─────────────────────────────────┐
│ AI 에이전트            [접기 ▲] │  ← 패널 헤더 + 토글
├─────────────────────────────────┤
│ [분석 요청] 버튼                │  ← 초기 상태
├─────────────────────────────────┤
│                                 │
│  🤖 비트코인은 현재 상승세를     │  ← AI 메시지 (왼쪽)
│  보이고 있습니다...              │
│  📎 출처: news.com, reddit.com  │  ← Grounding 링크
│                                 │
│         지금 추가 매수 괜찮아? 👤│  ← 사용자 메시지 (오른쪽)
│                                 │
│  🤖 현재 포지션 대비...         │  ← AI 응답 (스트리밍 중 커서)
│                                 │
├─────────────────────────────────┤
│ [메시지 입력...        ] [전송] │  ← 입력 영역
└─────────────────────────────────┘
```

#### Behavior

1. **코인 선택 시**: 에이전트 패널 표시 (빈 상태, "분석 요청" 버튼만)
2. **"분석 요청" 클릭**: 서버에 사전 정의 메시지 전송 (`"이 코인의 현재 트렌드, 전망, 커뮤니티 여론을 분석하고 매매 추천을 해주세요"`)
   → 스트리밍 응답이 채팅 영역에 렌더링
3. **자유 채팅**: 입력창에 질문 → history 배열과 함께 전송 → 스트리밍 응답
4. **코인 변경 시**: 대화 내역 초기화, "분석 요청" 버튼 상태로 복귀
5. **접기/펼치기**: 패널 토글, 접힌 상태에서도 대화 유지

#### State Management

```typescript
interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { title: string; url: string }[];
}

// AgentChat 컴포넌트 내부 state
const [messages, setMessages] = useState<ChatMessage[]>([]);
const [input, setInput] = useState("");
const [isStreaming, setIsStreaming] = useState(false);
const [isCollapsed, setIsCollapsed] = useState(false);
```

- 코인(market) 변경 시 `messages`를 빈 배열로 초기화
- 스트리밍 중에는 입력/전송 비활성화
- history는 `messages`에서 최근 20턴만 추출하여 서버에 전송

#### Streaming Implementation

`fetch` + `ReadableStream`으로 SSE 파싱:
- 응답을 라인 단위로 읽음
- `data: {"token": "..."}` → 현재 assistant 메시지에 토큰 누적
- `data: {"grounding_sources": [...]}` → 메시지에 출처 정보 첨부
- `data: [DONE]` → 스트리밍 완료 처리

### Styling

`src/ui/frontend/src/index.css`에 추가:
- `.agent-chat`: 패널 컨테이너
- `.agent-chat-header`: 헤더 (타이틀 + 토글)
- `.agent-chat-messages`: 스크롤 가능한 메시지 영역 (max-height: 400px)
- `.agent-msg-user`: 사용자 메시지 (오른쪽, accent 배경)
- `.agent-msg-assistant`: AI 메시지 (왼쪽, 카드 배경)
- `.agent-msg-sources`: 출처 링크 칩
- `.agent-input-area`: 입력 영역 (input + send 버튼)
- `.agent-analyze-btn`: 분석 요청 버튼
- `.streaming-cursor`: 스트리밍 중 깜빡이는 커서 애니메이션

기존 다크 테마 변수(`--bg-card`, `--accent`, `--text-dim` 등)를 그대로 활용.

## Decisions

| 항목 | 결정 | 이유 |
|---|---|---|
| LLM | Gemini 2.5 Flash | 빠른 응답 + 비용 효율 |
| 검색 | Google Search Grounding | 실시간 뉴스/여론 반영 |
| 통신 | SSE | API 키 보안 + 서버 데이터 주입 용이 |
| 저장 | 세션 내 메모리 | 요구사항: DB 저장 불필요 |
| 트리거 | 분석 요청 버튼 | 불필요한 API 호출 방지 |
| 히스토리 | 최대 20턴 | 토큰 비용 관리 |

## Files to Change

| File | Action | Description |
|---|---|---|
| `src/ui/api/routes/agent.py` | Create | SSE 스트리밍 채팅 엔드포인트 |
| `src/ui/api/server.py` | Modify | agent 라우터 등록 |
| `config/settings.yaml` | Modify | gemini_api_key 설정 추가 |
| `pyproject.toml` | Modify | google-genai 의존성 추가 |
| `src/ui/frontend/src/pages/Exchange.tsx` | Modify | AgentChat 컴포넌트 추가 |
| `src/ui/frontend/src/index.css` | Modify | 채팅 UI 스타일 추가 |

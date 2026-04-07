# Exchange Page & Manual Trading Design

## Overview

거래소 메뉴를 추가하여 업비트 KRW 마켓 전체 리스트를 실시간으로 표시하고, 사용자가 직접 수동 매수/매도할 수 있는 기능을 구현한다. 자동매매와 수동매매가 공존하며, 포지션별로 AUTO/MANUAL 모드를 관리한다.

## 핵심 결정 사항

| 항목 | 결정 |
|------|------|
| 마켓 범위 | KRW 전체 + 스크리닝 통과 코인 상단 하이라이트 |
| 주문 방식 | 시장가 + 금액/비율 입력 |
| 자동/수동 공존 | 공존, 포지션별 모드 관리 |
| 실시간 데이터 | 업비트 WebSocket + REST 폴백 |
| 레이아웃 | 좌측 코인 리스트 + 우측 상세/주문 (업비트 웹 스타일) |

---

## 1. 데이터 모델 변경

### Position 모델 확장

기존 Position 필드에 추가:

```
trade_mode: str           # "AUTO" | "MANUAL" (기본값: "AUTO")
stop_loss_price: Decimal | None   # MANUAL 포지션용 예약 손절가
take_profit_price: Decimal | None # MANUAL 포지션용 예약 익절가
```

### DB 스키마 변경

`positions` 테이블에 3개 컬럼 추가:
- `trade_mode TEXT NOT NULL DEFAULT 'AUTO'`
- `stop_loss_price TEXT` (Decimal 문자열, nullable)
- `take_profit_price TEXT` (Decimal 문자열, nullable)

### 모드 전환 규칙

| 상황 | 결과 모드 |
|------|-----------|
| 자동매매가 매수 | AUTO |
| 사용자가 수동 매수 (신규 포지션) | MANUAL |
| AUTO 포지션에 수동 추가매수 | MANUAL로 전환 |
| 사용자가 포지션 상세에서 토글 | 확인 후 전환 |

### 자동매매 동작 분기

- **AUTO 포지션:** 기존대로 ML 시그널 기반 매도 (손절/익절/트레일링/부분익절)
- **MANUAL 포지션:** ML 매도 시그널 무시. `stop_loss_price`/`take_profit_price` 설정 시 해당 가격 도달하면 자동 실행

---

## 2. 백엔드 — 업비트 WebSocket 서비스

### 새 서비스: `src/service/upbit_ws.py`

`UpbitWebSocketService` 클래스:

```
connect()        — wss://api.upbit.com/websocket/v1 연결
subscribe()      — KRW 마켓 티커 구독 메시지 전송
_recv_loop()     — 수신 루프, 파싱 후 내부 캐시 갱신
_reconnect()     — 끊김 시 지수 백오프 재연결 (1s → 2s → 4s → ... 최대 60s)
get_snapshot()   — 현재 캐시된 전체 티커 딕셔너리 반환
_health_check()  — 마지막 수신 시각 확인, 30초 무응답 시 재연결
```

### TickerData 구조

```
market: str                    # "KRW-BTC"
price: Decimal                 # 현재가
change: str                    # "RISE" | "FALL" | "EVEN"
change_rate: Decimal           # 변동률
change_price: Decimal          # 변동가
volume_24h: Decimal            # 24시간 거래량
acc_trade_price_24h: Decimal   # 24시간 거래대금
timestamp: int                 # ms
```

### 프론트 중계

기존 `/ws/live` WebSocket 엔드포인트를 확장하여 `{"type": "ticker", "data": {...}}` 메시지로 프론트에 브로드캐스트. 변동이 있는 마켓만 전송 (델타 방식).

### 안정성

- 지수 백오프 재연결: 1s → 2s → 4s → ... 최대 60s
- 헬스체크: 30초 무응답 시 재연결 트리거
- 폴백: WebSocket 연결 실패 3회 연속 시 REST 폴링 모드 전환 (10초 간격 `fetch_tickers`). 연결 복구되면 WebSocket 복귀.
- 연결 상태를 프론트에 전달 (`{"type": "ws_status", "data": {"upbit": "connected" | "polling" | "disconnected"}}`)

---

## 3. 백엔드 — 수동 주문 API

### 새 라우트: `src/ui/api/routes/exchange.py`

#### 마켓 리스트

`GET /api/exchange/markets`
- 응답: `[{market, korean_name, price, change_rate, volume_24h, is_screened}]`
- 가격 데이터는 WebSocket 캐시에서 조회

#### 수동 매수

`POST /api/exchange/buy`
- 요청: `{market: str, amount_krw: str}` (Decimal 문자열, 총 투자금액 — 수수료/슬리피지는 PaperEngine 내부에서 차감)
- 흐름:
  1. RiskManager.approve() 체크 (일일 한도, 최대 포지션 등)
  2. PaperEngine.execute_buy(reason="MANUAL")
  3. 기존 포지션 있으면 trade_mode = "MANUAL"로 전환
  4. 신규 포지션이면 trade_mode = "MANUAL"로 생성
- 응답: `{success, order, position}` 또는 에러 (사유 포함)

#### 수동 매도

`POST /api/exchange/sell`
- 요청: `{market: str, fraction: str}` (0.25 / 0.5 / 0.75 / 1.0)
- 흐름:
  - fraction < 1.0: execute_partial_sell(reason="MANUAL")
  - fraction == 1.0: execute_sell(reason="MANUAL")
- 응답: `{success, order, position | null}`

#### 포지션 모드 관리

`PATCH /api/exchange/position/{market}/mode`
- 요청: `{trade_mode: "AUTO" | "MANUAL"}`

`PATCH /api/exchange/position/{market}/exit-orders`
- 요청: `{stop_loss_price?: str, take_profit_price?: str}` (Decimal 문자열, null로 해제)

---

## 4. 프론트엔드 — 거래소 페이지

### 네비게이션

사이드바에 "거래소" 메뉴 추가. 라우트: `/exchange`

### 레이아웃 (좌우 분할)

#### 좌측 패널 — 코인 리스트 (약 40%)

- **검색:** 상단 입력창, 코인명/티커 실시간 필터
- **스크리닝 통과 섹션:** 상단 고정, 하이라이트 배경
- **전체 KRW 마켓:** 스크롤 리스트
- **각 행:** 코인명(한글), 티커, 현재가, 전일대비 변동률(%), 거래대금

#### 가격 변동 UX 효과

- 가격 상승 시: 초록색 플래시 애니메이션 (0.5초 페이드)
- 가격 하락 시: 빨간색 플래시 애니메이션
- 변동률 수치 색상 반영 (양수 초록, 음수 빨강)
- 가격 텍스트 변동 시 스케일업 효과 (1.05배 → 1.0, 0.3초)

#### 우측 패널 — 선택 코인 상세 + 주문 (약 60%)

**상단 — 코인 헤더:**
- 코인명, 현재가 (큰 글씨), 변동률, 24h 고가/저가/거래대금

**중단 — 주문 패널:**

매수/매도 탭 전환 방식.

매수 탭:
- 투자가능금액 표시
- 금액 직접 입력 필드
- 비율 프리셋 버튼: 25% / 50% / 75% / 100% (투자가능금액 기준)
- 예상 수량 자동 계산 (수수료, 슬리피지 반영)
- 매수 버튼

매도 탭:
- 보유수량 / 평균매입가 / 현재 손익 표시
- 비율 프리셋 버튼: 25% / 50% / 75% / 100% (보유수량 기준)
- 매도 버튼
- 포지션 없으면 "보유하지 않은 코인입니다" 표시

예약 주문 섹션 (보유 중일 때만):
- 손절가 입력 (직접 입력)
- 익절가 입력 (직접 입력)
- 설정/해제 버튼

**하단 — 최근 거래 내역 (해당 코인만 필터)**

---

## 5. 포지션 모드 관리 UI

### Dashboard 포지션 테이블 확장

- **모드 뱃지:** `AUTO` (accent 색상) / `MANUAL` (warn 색상)
- **모드 토글:** 뱃지 클릭 시 확인 모달

### 전환 확인 모달

AUTO → MANUAL:
> "이 포지션을 수동 관리로 전환합니다. 자동매매 시그널이 적용되지 않습니다."

MANUAL → AUTO:
> "이 포지션을 자동매매에 위임합니다. 현재 손익: {pnl}%. 설정된 예약 손절/익절은 해제됩니다."

포지션 정보 요약 (평균매입가, 수량, 손익) + 확인/취소 버튼.

### 거래 내역 테이블 확장

기존 BUY/SELL 뱃지 옆에 reason 서브 뱃지 추가:
- `ML_SIGNAL`, `MANUAL`, `ADDITIONAL_BUY`, `MANUAL_STOP_LOSS`, `MANUAL_TAKE_PROFIT` 등

---

## 6. MANUAL 포지션 예약 주문 실행

### Portfolio 서비스 확장

포지션 체크 루프에서 모드별 분기:

```
for position in positions:
    if position.trade_mode == "AUTO":
        → 기존 로직 (손절/익절/트레일링/부분익절)

    elif position.trade_mode == "MANUAL":
        → ML 시그널 무시
        → stop_loss_price 설정 시: 현재가 <= stop_loss_price → execute_sell(reason="MANUAL_STOP_LOSS")
        → take_profit_price 설정 시: 현재가 >= take_profit_price → execute_sell(reason="MANUAL_TAKE_PROFIT")
```

### 체결 알림

- WebSocket으로 프론트에 전송: `{"type": "order_filled", "data": {market, side, reason, price}}`
- 프론트: 토스트 알림 표시 (5초 후 자동 사라짐)
  - 예: "BTC 예약 손절 실행 — 95,000,000원에 매도 완료"

---

## 변경 파일 목록

### 신규
- `src/service/upbit_ws.py` — 업비트 WebSocket 서비스
- `src/ui/api/routes/exchange.py` — 수동 주문 API 라우트
- `src/ui/frontend/src/pages/Exchange.tsx` — 거래소 페이지

### 수정
- `src/types/models.py` — Position에 trade_mode, stop_loss_price, take_profit_price 추가
- `src/repository/database.py` — positions 테이블 스키마 확장
- `src/repository/portfolio_repo.py` — 새 필드 저장/로드
- `src/service/portfolio.py` — MANUAL 포지션 예약 주문 체크 로직
- `src/service/paper_engine.py` — reason 파라미터 확장, trade_mode 설정
- `src/runtime/app.py` — UpbitWebSocketService 생명주기 관리, WebSocket 중계
- `src/ui/api/server.py` — exchange 라우트 등록
- `src/ui/frontend/src/App.tsx` — 거래소 라우트/네비 추가
- `src/ui/frontend/src/pages/Dashboard.tsx` — 포지션 테이블에 모드 뱃지/토글, 거래 내역에 reason 뱃지
- `src/ui/frontend/src/index.css` — 가격 변동 애니메이션, 거래소 페이지 스타일

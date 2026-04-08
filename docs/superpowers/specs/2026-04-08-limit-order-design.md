# Limit Buy Order Design

## Overview

거래소 페이지에 지정가 매수 기능을 추가한다. 사용자가 원하는 가격과 금액을 지정하면, 서버가 현재가를 감시하여 조건 충족 시 자동 체결한다.

## Requirements

- 지정가 매수: 사용자가 지정한 가격 이하가 되면 자동 체결
- 당일 만료: 미체결 주문은 당일 23:59:59 KST에 자동 만료
- DB 저장: 서버 재시작 시에도 미체결 주문 유지 및 복원
- 금액 안전성: 모든 금액 변동은 DB 트랜잭션 단위, 이벤트 소실 없음

## Data Model

### DB Table: `pending_orders`

```sql
CREATE TABLE IF NOT EXISTS pending_orders (
    id          TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    market      TEXT NOT NULL,
    side        TEXT NOT NULL DEFAULT 'BUY',
    limit_price TEXT NOT NULL,
    amount_krw  TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'PENDING',
    created_at  INTEGER NOT NULL,
    expires_at  INTEGER NOT NULL,
    filled_at   INTEGER
);
```

- `status`: PENDING / FILLED / CANCELLED / EXPIRED
- `expires_at`: 생성 시점의 당일 23:59:59 KST (Unix timestamp)

### Type: `PendingOrder` (`src/types/models.py`)

```python
@dataclass
class PendingOrder:
    id: str
    user_id: int
    market: str
    side: str
    limit_price: Decimal
    amount_krw: Decimal
    status: str
    created_at: int
    expires_at: int
    filled_at: int | None = None
```

## Money Safety Guarantees

모든 금액 변동은 단일 DB 트랜잭션으로 처리하여 누락/이중 처리를 방지한다.

### 1. 주문 등록 (원자적)

하나의 트랜잭션 내에서:
- `cash_balance -= amount_krw` (잔고 선차감 = 동결)
- `pending_orders INSERT`

트랜잭션 실패 시 둘 다 롤백.

### 2. 체결 (원자적)

하나의 트랜잭션 내에서:
- `UPDATE pending_orders SET status='FILLED' WHERE id=? AND status='PENDING'` (CAS)
- `rows_affected == 0`이면 이미 처리된 것으로 스킵 (이중 체결 방지)
- 동결 금액에서 포지션으로 전환 (`execute_limit_buy`)
- 수수료/슬리피지 차액 cash 환불
- `orders` 테이블에 체결 기록 저장

### 3. 취소 (원자적)

하나의 트랜잭션 내에서:
- `pending_orders.status = CANCELLED`
- `cash_balance += amount_krw` (환불)

### 4. 만료 (원자적)

하나의 트랜잭션 내에서:
- 만료 대상 일괄 `status = EXPIRED`
- 각 주문의 `amount_krw`를 `cash_balance`에 환불

### 5. 서버 재시작 복원

App 시작 시:
- `pending_orders WHERE status = 'PENDING'` 조회
- `expires_at < now`인 것은 즉시 만료 처리 (환불 트랜잭션)
- 유효한 것은 메모리에 로드하여 감시 재개

## Backend Architecture

### Repository: `PendingOrderRepo` (`src/repository/pending_order_repo.py`)

| Method | Role |
|--------|------|
| `create(order, account)` | INSERT + 잔고 차감 (단일 트랜잭션) |
| `fill(order_id)` | status->FILLED, CAS 방식 이중 체결 방지 |
| `cancel(order_id, account)` | status->CANCELLED + 잔고 환불 (단일 트랜잭션) |
| `expire_all(user_id, account)` | 만료 대상 일괄 처리 + 잔고 환불 (단일 트랜잭션) |
| `get_pending_by_user(user_id)` | 유저별 PENDING 목록 |
| `get_all_pending()` | 전체 PENDING (감시 루프용) |
| `load_unexpired()` | 서버 시작 시 복원용 |

### Service: `PaperEngine` 확장

새 메서드 `execute_limit_buy(account, market, fill_price, amount_krw, confidence, reason)`:
- 기존 `execute_buy`와 유사하지만 cash 차감 없음 (이미 선차감됨)
- 동결 금액에서 수수료/슬리피지 적용 후 포지션 생성
- 차액(동결 금액 - 실제 소요)은 cash로 환불
- Order 객체 반환

### Runtime: `_monitor_positions` 확장

감시 간격: 30초 -> **10초**

루프 내 추가 로직:
1. 가격 데이터 조회 (WS 캐시 -> REST 폴백)
2. [기존] 포지션 SL/TP 체크
3. [추가] 지정가 주문 체결 조건 체크
   - `current_price <= limit_price` 이면 체결
   - fill 트랜잭션 -> `execute_limit_buy` -> order 저장 -> WS 알림
4. [추가] 만료 주문 정리
   - `expires_at < now`인 PENDING 주문 만료 처리 + 환불

## API Endpoints

### POST `/api/exchange/limit-buy`

Request:
```json
{
  "market": "KRW-BTC",
  "limit_price": "135000000",
  "amount_krw": "100000"
}
```

Validation:
- `amount_krw >= min_order_krw`
- `amount_krw <= safe_buy_amount(cash_balance)` (선차감 후 잔고 기준)
- `limit_price > 0`
- 포지션 한도 체크 (기존 포지션 없는 마켓이면 max_open_positions 확인)

Response:
```json
{
  "success": true,
  "pending_order": {
    "id": "...",
    "market": "KRW-BTC",
    "limit_price": "135000000",
    "amount_krw": "100000",
    "status": "PENDING",
    "expires_at": 1744127999
  }
}
```

### DELETE `/api/exchange/limit-buy/{order_id}`

취소 + 환불 트랜잭션. 본인 주문만 취소 가능.

### GET `/api/exchange/pending-orders`

해당 유저의 PENDING 상태 주문 목록 반환.

## Frontend UI

### OrderPanel 매수 탭 변경

주문 유형 토글 추가:
```
[시장가] [지정가]
```

**시장가**: 기존 동작 그대로

**지정가 선택 시**:
- 지정가 입력 필드 (현재가로 자동 채움, 수정 가능)
- 투자 금액 입력 (기존 input 재활용)
- 25%/50%/75%/100% 프리셋 동일
- 수수료/슬리피지 예상 표시
- "지정가 매수 신청" 버튼 -> 확인 모달 -> 등록

### 미체결 주문 목록

OrderPanel 하단 (RecentTrades 위)에 미체결 주문 섹션:
- 마켓명, 지정가, 금액, 만료 시간 표시
- 각 주문에 취소 버튼
- 체결/만료 시 WebSocket으로 실시간 반영

### 확인 모달 확장

기존 `OrderConfirmModal`에 지정가 주문 정보 추가:
- 주문 유형: 지정가
- 지정가: 표시
- 만료: 오늘 23:59

### WebSocket 메시지 타입 추가

- `pending_order_placed`: 주문 등록 확인
- `pending_order_filled`: 체결 알림
- `pending_order_expired`: 만료 알림
- `pending_order_cancelled`: 취소 확인

## Layer Compliance

6-layer 아키텍처 준수:
- `types/models.py` — PendingOrder dataclass
- `repository/pending_order_repo.py` — DB CRUD + 트랜잭션
- `service/paper_engine.py` — execute_limit_buy 메서드
- `runtime/app.py` — 감시 루프 확장, 서버 시작 복원
- `ui/api/routes/exchange.py` — API 엔드포인트
- `ui/frontend/src/pages/Exchange.tsx` — UI 컴포넌트

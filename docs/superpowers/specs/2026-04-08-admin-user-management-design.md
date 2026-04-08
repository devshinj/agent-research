# Admin User Management & Balance Control

## Summary

관리자 전용 회원 관리 페이지(`/admin`)를 추가한다. 기존 System 페이지의 AdminUserPanel을 새 페이지로 이동하고, 잔고 충전/차감 기능과 이력 추적을 새로 구현한다.

## Requirements

1. 관리자가 회원 잔고를 증감 방식으로 충전/차감할 수 있다
2. 모든 잔고 변경은 이력(ledger)으로 기록된다
3. 기존 회원 관리 기능(활성/비활성, 설정 수정)을 별도 `/admin` 페이지로 통합한다
4. 사이드바에 관리자 전용 메뉴를 추가한다

## Database

### New Table: `balance_ledger`

```sql
CREATE TABLE balance_ledger (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       INTEGER NOT NULL REFERENCES users(id),
    admin_id      INTEGER NOT NULL REFERENCES users(id),
    amount        TEXT NOT NULL,
    balance_after TEXT NOT NULL,
    memo          TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL
);
```

- `amount`: Decimal TEXT. 양수 = 충전, 음수 = 차감
- `balance_after`: 변경 후 잔고 (감사 추적)
- `memo`: 관리자가 남기는 사유 (선택)

Migration은 `database.py`의 `_run_migrations()`에 추가한다.

## Backend API

기존 `src/ui/api/routes/admin.py`에 엔드포인트 추가. 모두 `require_admin` 의존성 사용.

### POST `/api/admin/users/{user_id}/balance`

**Request:**
```json
{ "amount": "5000000", "memo": "초기 자본금 충전" }
```

**Logic:**
1. 대상 유저 존재 및 활성 확인
2. 현재 `account_state.cash_balance` 조회
3. `new_balance = cash_balance + Decimal(amount)`
4. `new_balance < 0`이면 400 에러
5. 단일 트랜잭션: `account_state` UPDATE + `balance_ledger` INSERT
6. 런타임 메모리(`app.user_accounts`)의 잔고 동기화
7. 변경 후 잔고 반환

**Response:**
```json
{ "user_id": 2, "balance_before": "5000000", "balance_after": "10000000", "amount": "5000000" }
```

### GET `/api/admin/users/{user_id}/balance-history`

**Response:**
```json
{
  "history": [
    {
      "id": 1,
      "admin_id": 1,
      "admin_nickname": "admin",
      "amount": "5000000",
      "balance_after": "10000000",
      "memo": "초기 자본금 충전",
      "created_at": "2026-04-08T12:00:00"
    }
  ]
}
```

최신순 정렬. 페이지네이션은 초기 버전에서 생략(유저당 이력이 적을 것으로 예상).

### 기존 GET `/api/admin/users` 확장

각 유저 객체에 `cash_balance` 필드 추가.

## Frontend

### 라우팅

- 새 페이지: `/admin` → `Admin.tsx`
- 사이드바에 "회원 관리" 메뉴 추가 (`is_admin`일 때만 노출)

### System 페이지 변경

`AdminUserPanel` 관련 코드를 System.tsx에서 제거. System 페이지는 시스템 제어(엔진 pause/resume, reset, config)만 담당.

### Admin.tsx 구성

**유저 목록 테이블:**
| 컬럼 | 내용 |
|------|------|
| 닉네임 | 유저 닉네임 |
| 이메일 | 유저 이메일 |
| 잔고 | 현재 cash_balance (KRW 포맷) |
| 상태 | 활성/비활성 배지 + 토글 버튼 |
| 가입일 | created_at |
| 액션 | "잔고 관리" 버튼, "설정" 버튼 |

**잔고 관리 모달:**
- 현재 잔고 표시
- 금액 입력 필드 (양수: 충전, 음수: 차감)
- 메모 입력 필드 (선택)
- 확인/취소 버튼
- 하단: 해당 유저의 충전/차감 이력 테이블 (일시, 금액, 변경 후 잔고, 메모, 처리자)

**설정 모달:**
- 기존 AdminUserPanel의 유저별 설정 수정 UI를 모달로 이동

## Layer Architecture

- `src/repository/database.py` — migration 추가
- `src/repository/user_repo.py` — ledger CRUD 메서드 추가
- `src/ui/api/routes/admin.py` — 엔드포인트 추가
- `src/ui/frontend/src/pages/Admin.tsx` — 새 페이지
- `src/ui/frontend/src/pages/System.tsx` — AdminUserPanel 제거

types → config → repository → service → runtime → ui 레이어 규칙을 준수한다.

## Error Handling

- 차감 시 잔고 부족: 400 에러 + 명확한 메시지
- 존재하지 않는 유저: 404
- 비활성 유저 잔고 변경: 허용 (비활성이어도 잔고 관리는 가능)
- amount가 0: 400 에러

## Testing

- 잔고 충전/차감 API 단위 테스트
- 잔고 부족 차감 시 에러 검증
- ledger 기록 정확성 검증
- 트랜잭션 원자성 검증 (충전 실패 시 ledger도 롤백)

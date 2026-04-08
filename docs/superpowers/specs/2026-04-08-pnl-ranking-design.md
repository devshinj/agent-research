# 투자 손익 랭킹 기능 설계

## 개요

로그인한 모든 사용자가 다른 사용자들의 투자 수익률 순위를 볼 수 있는 공개 랭킹 페이지를 추가한다.

## 요구사항

- 전체 기간 누적 수익률(%) 기준으로 순위 정렬
- 닉네임 시스템 도입 (중복 불가)
- 본인 랭킹 항목은 시각적으로 강조 표시
- 상위 3명은 메달 아이콘 표시
- 상세 정보: 수익률, 승률, 거래 횟수, 최대 낙폭, 미니차트(sparkline)

## 접근 방식

실시간 계산 방식 — API 호출 시 기존 테이블을 JOIN 쿼리로 집계하여 랭킹 반환. 현재 SQLite 기반 소규모 시스템에 적합하며, 사용자 증가 시 스냅샷 테이블 방식으로 전환 가능.

## 데이터 모델

### users 테이블 변경

`nickname TEXT UNIQUE` 컬럼 추가. 미설정 시 `User#{user_id}` 기본값 사용.

### RankingEntry 타입 (src/types/models.py)

```python
@dataclass
class RankingEntry:
    rank: int
    user_id: int
    nickname: str
    return_pct: Decimal        # (total_equity - initial_balance) / initial_balance * 100
    win_rate: Decimal          # win_trades / (win_trades + loss_trades) * 100
    total_trades: int          # filled orders 수
    max_drawdown_pct: Decimal  # daily_summary에서 MAX(max_drawdown_pct)
    daily_equities: list[Decimal]  # 최근 30일 ending_balance (sparkline용)
    is_me: bool                # 요청자 본인 여부
```

## 백엔드 API

### GET /api/ranking

별도 라우트 파일 `src/ui/api/routes/ranking.py`에 생성.

**응답:**

```json
{
  "rankings": [
    {
      "rank": 1,
      "user_id": 3,
      "nickname": "CryptoKing",
      "return_pct": 15.23,
      "win_rate": 68.5,
      "total_trades": 42,
      "max_drawdown_pct": 3.7,
      "daily_equities": [1000000, 1010000, 1050000],
      "is_me": true
    }
  ],
  "my_rank": 1,
  "total_users": 12
}
```

**집계 로직 (ranking_repo.py):**

1. `daily_summary`에서 가장 최근 날짜의 `ending_balance` → total_equity로 사용. 포지션 평가액의 실시간 계산은 런타임 레이어에 속하므로, 랭킹에서는 마지막으로 기록된 ending_balance를 기준으로 한다. (일일 요약이 없는 신규 사용자는 account_state.cash_balance를 사용)
2. `user_settings`에서 initial_balance → 수익률(%) = (total_equity - initial_balance) / initial_balance * 100
3. `daily_summary` 집계: SUM(win_trades), SUM(loss_trades), MAX(max_drawdown_pct)
4. `orders` 집계: COUNT(*) WHERE status='filled'
5. `daily_summary`에서 최근 30일 ending_balance → sparkline 배열
6. 활성 사용자만 (is_active=1)
7. 수익률(%) 내림차순 정렬

### PATCH /api/auth/nickname

닉네임 변경 엔드포인트. 중복 검사 포함.

### POST /api/auth/register 변경

회원가입 시 nickname 필드 추가 (선택사항, 미입력 시 기본값).

## 프론트엔드

### 라우팅

- `/ranking` 경로 추가 (App.tsx)
- 네비게이션에 "랭킹" 메뉴 항목 추가

### Ranking.tsx 페이지

**상단 영역:**
- 페이지 제목 "투자 손익 랭킹"
- 내 순위 요약 카드 — "내 순위: #3 / 12명, 수익률: +8.2%"

**랭킹 테이블:**

| 순위 | 닉네임 | 수익률(%) | 승률(%) | 거래 횟수 | 최대 낙폭(%) | 미니차트 |
|------|---------|-----------|---------|-----------|-------------|---------|
| 1 | CryptoKing | +15.23% | 68.5% | 42 | -3.7% | sparkline |
| 2 | TraderJ | +12.10% | 61.2% | 35 | -5.1% | sparkline |
| **3** | **MyNick** | **+8.20%** | **55.0%** | **28** | **-4.2%** | **sparkline** |

**시각 디자인:**
- 상위 3명: 금/은/동 메달 아이콘
- 본인 행: 배경색 하이라이트 + 왼쪽 강조 바
- 미니차트: 최근 30일 ending_balance sparkline (작은 라인 차트)
- 수익률 양수는 초록, 음수는 빨강

**닉네임 설정:**
- Register.tsx에 닉네임 입력 필드 추가
- 랭킹 페이지에서 닉네임 미설정 시 설정 유도 배너 표시

## 변경 파일 목록

| 파일 | 변경 내용 |
|------|-----------|
| `src/types/models.py` | `RankingEntry` dataclass 추가 |
| `src/repository/database.py` | users 테이블에 nickname 컬럼 |
| `src/repository/user_repo.py` | 닉네임 저장/조회 메서드 |
| `src/repository/ranking_repo.py` | 신규 — 랭킹 집계 쿼리 |
| `src/ui/api/routes/ranking.py` | 신규 — API 엔드포인트 |
| `src/ui/api/app.py` | ranking 라우터 등록 |
| `src/ui/frontend/src/pages/Ranking.tsx` | 신규 — 랭킹 페이지 |
| `src/ui/frontend/src/App.tsx` | 라우트 추가 |
| `src/ui/frontend/src/pages/Register.tsx` | 닉네임 필드 추가 |

## 레이어 준수

6-layer 아키텍처 (types → config → repository → service → runtime → ui) 준수:

- **types**: `RankingEntry` dataclass
- **repository**: `ranking_repo.py` (집계 쿼리), `user_repo.py` (닉네임), `database.py` (스키마)
- **service**: 별도 서비스 불필요 — repository에서 직접 집계
- **ui/api**: `ranking.py` 라우트
- **ui/frontend**: `Ranking.tsx` 페이지

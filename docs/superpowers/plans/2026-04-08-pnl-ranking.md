# 투자 손익 랭킹 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 로그인한 모든 사용자가 수익률(%) 기준으로 다른 사용자들의 투자 손익 순위를 볼 수 있는 공개 랭킹 페이지를 추가한다.

**Architecture:** `ranking_repo.py`에서 기존 `daily_summary`, `orders`, `account_state`, `users`, `user_settings` 테이블을 JOIN 쿼리로 집계하여 랭킹 데이터를 실시간 반환. `RankingEntry` 타입을 정의하고, `/api/ranking` 엔드포인트와 React `Ranking.tsx` 페이지를 추가한다. 닉네임 시스템은 이미 구현되어 있으므로 추가 작업 불필요.

**Tech Stack:** Python 3.12+, FastAPI, aiosqlite, React, TypeScript, Recharts (sparkline)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `src/types/models.py` | Modify | `RankingEntry` dataclass 추가 |
| `src/repository/ranking_repo.py` | Create | 랭킹 집계 SQL 쿼리 |
| `tests/unit/test_ranking_repo.py` | Create | ranking_repo 단위 테스트 |
| `src/ui/api/routes/ranking.py` | Create | `GET /api/ranking` 엔드포인트 |
| `tests/unit/test_ranking_api.py` | Create | API 엔드포인트 테스트 |
| `src/ui/api/server.py` | Modify | ranking 라우터 등록 (line 14, 37) |
| `src/ui/frontend/src/pages/Ranking.tsx` | Create | 랭킹 페이지 UI |
| `src/ui/frontend/src/App.tsx` | Modify | 라우트 + 네비게이션 추가 (lines 87-91, 115-120) |

---

### Task 1: RankingEntry 타입 정의

**Files:**
- Modify: `src/types/models.py:96` (DailySummary 뒤에 추가)

- [ ] **Step 1: RankingEntry dataclass 추가**

`src/types/models.py` 끝에 추가:

```python
@dataclass(frozen=True)
class RankingEntry:
    rank: int
    user_id: int
    nickname: str
    return_pct: Decimal
    win_rate: Decimal
    total_trades: int
    max_drawdown_pct: Decimal
    daily_equities: tuple[Decimal, ...]
    is_me: bool
```

- [ ] **Step 2: 타입 확인**

Run: `uv run python -c "from src.types.models import RankingEntry; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/types/models.py
git commit -m "feat(types): add RankingEntry dataclass"
```

---

### Task 2: ranking_repo.py 작성 (TDD)

**Files:**
- Create: `src/repository/ranking_repo.py`
- Create: `tests/unit/test_ranking_repo.py`

- [ ] **Step 1: 테스트 파일 작성**

`tests/unit/test_ranking_repo.py`:

```python
from __future__ import annotations

import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.ranking_repo import RankingRepo
from src.repository.user_repo import UserRepo
from src.repository.portfolio_repo import PortfolioRepository
from src.types.models import DailySummary


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def repos(db):
    return {
        "user": UserRepo(db),
        "portfolio": PortfolioRepository(db),
        "ranking": RankingRepo(db),
    }


async def _create_user(repos, email: str, nickname: str, initial_balance: str, cash_balance: str) -> int:
    """Helper: create user, set initial_balance and cash_balance."""
    from src.ui.api.auth import hash_password
    user = await repos["user"].create(
        email=email, password_hash=hash_password("password123"), nickname=nickname,
    )
    uid = user["id"]
    await repos["user"].update_settings(uid, {"initial_balance": initial_balance})
    conn = repos["ranking"]._db.conn
    await conn.execute(
        "UPDATE account_state SET cash_balance = ? WHERE user_id = ?",
        (cash_balance, uid),
    )
    await conn.commit()
    return uid


@pytest.mark.asyncio
async def test_ranking_empty(repos):
    """No users → empty ranking."""
    result = await repos["ranking"].get_ranking(requesting_user_id=999)
    assert result == []


@pytest.mark.asyncio
async def test_ranking_single_user(repos):
    """Single user with daily summaries."""
    uid = await _create_user(repos, "a@test.com", "Alice", "1000000", "1100000")

    await repos["portfolio"].save_daily_summary(
        DailySummary(
            date="2026-04-07",
            starting_balance=Decimal("1000000"),
            ending_balance=Decimal("1050000"),
            realized_pnl=Decimal("50000"),
            total_trades=5,
            win_trades=3,
            loss_trades=2,
            max_drawdown_pct=Decimal("2.1"),
        ),
        user_id=uid,
    )
    await repos["portfolio"].save_daily_summary(
        DailySummary(
            date="2026-04-08",
            starting_balance=Decimal("1050000"),
            ending_balance=Decimal("1100000"),
            realized_pnl=Decimal("50000"),
            total_trades=3,
            win_trades=2,
            loss_trades=1,
            max_drawdown_pct=Decimal("1.5"),
        ),
        user_id=uid,
    )

    result = await repos["ranking"].get_ranking(requesting_user_id=uid)
    assert len(result) == 1
    entry = result[0]
    assert entry.rank == 1
    assert entry.nickname == "Alice"
    assert entry.return_pct == Decimal("10")  # (1100000-1000000)/1000000*100
    assert entry.total_trades == 8  # 5+3
    assert entry.win_rate == Decimal("62.5")  # 5/(5+3)*100
    assert entry.max_drawdown_pct == Decimal("2.1")  # max of 2.1, 1.5
    assert entry.is_me is True
    assert len(entry.daily_equities) == 2


@pytest.mark.asyncio
async def test_ranking_order(repos):
    """Two users, ranked by return_pct descending."""
    uid1 = await _create_user(repos, "a@test.com", "Alice", "1000000", "1200000")
    uid2 = await _create_user(repos, "b@test.com", "Bob", "1000000", "1100000")

    # Alice: 20% return
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1200000"),
                     Decimal("200000"), 10, 7, 3, Decimal("3.0")),
        user_id=uid1,
    )
    # Bob: 10% return
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1100000"),
                     Decimal("100000"), 5, 3, 2, Decimal("1.5")),
        user_id=uid2,
    )

    result = await repos["ranking"].get_ranking(requesting_user_id=uid2)
    assert len(result) == 2
    assert result[0].nickname == "Alice"
    assert result[0].rank == 1
    assert result[0].is_me is False
    assert result[1].nickname == "Bob"
    assert result[1].rank == 2
    assert result[1].is_me is True


@pytest.mark.asyncio
async def test_ranking_excludes_inactive(repos):
    """Inactive users are excluded from ranking."""
    uid1 = await _create_user(repos, "a@test.com", "Alice", "1000000", "1200000")
    uid2 = await _create_user(repos, "b@test.com", "Bob", "1000000", "1100000")

    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1200000"),
                     Decimal("200000"), 10, 7, 3, Decimal("3.0")),
        user_id=uid1,
    )
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1100000"),
                     Decimal("100000"), 5, 3, 2, Decimal("1.5")),
        user_id=uid2,
    )

    await repos["user"].set_active(uid2, False)

    result = await repos["ranking"].get_ranking(requesting_user_id=uid1)
    assert len(result) == 1
    assert result[0].nickname == "Alice"


@pytest.mark.asyncio
async def test_ranking_no_initial_balance(repos):
    """User with initial_balance=0 shows 0% return."""
    uid = await _create_user(repos, "a@test.com", "Alice", "0", "0")

    result = await repos["ranking"].get_ranking(requesting_user_id=uid)
    assert len(result) == 1
    assert result[0].return_pct == Decimal("0")
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/unit/test_ranking_repo.py -v`
Expected: FAIL (ModuleNotFoundError: ranking_repo)

- [ ] **Step 3: ranking_repo.py 구현**

`src/repository/ranking_repo.py`:

```python
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from src.repository.database import Database
from src.types.models import RankingEntry


class RankingRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_ranking(self, requesting_user_id: int) -> list[RankingEntry]:
        conn = self._db.conn

        # Get active users with their initial_balance and current cash_balance
        cursor = await conn.execute(
            """
            SELECT u.id, u.nickname,
                   COALESCE(us.initial_balance, '0') AS initial_balance,
                   COALESCE(a.cash_balance, '0') AS cash_balance
            FROM users u
            LEFT JOIN user_settings us ON us.user_id = u.id
            LEFT JOIN account_state a ON a.user_id = u.id
            WHERE u.is_active = 1
            """
        )
        users = await cursor.fetchall()

        if not users:
            return []

        entries: list[RankingEntry] = []
        for row in users:
            uid, nickname, initial_str, cash_str = row
            initial_balance = Decimal(initial_str)
            cash_balance = Decimal(cash_str)

            # Get latest ending_balance from daily_summary
            cursor = await conn.execute(
                "SELECT ending_balance FROM daily_summary"
                " WHERE user_id = ? ORDER BY date DESC LIMIT 1",
                (uid,),
            )
            latest = await cursor.fetchone()
            if latest:
                total_equity = Decimal(latest[0])
            else:
                total_equity = cash_balance

            # Return percentage
            if initial_balance > 0:
                return_pct = (
                    (total_equity - initial_balance) / initial_balance * 100
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                return_pct = Decimal("0")

            # Aggregated trade stats from daily_summary
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(total_trades), 0),"
                "       COALESCE(SUM(win_trades), 0),"
                "       COALESCE(SUM(loss_trades), 0),"
                "       COALESCE(MAX(max_drawdown_pct), '0')"
                " FROM daily_summary WHERE user_id = ?",
                (uid,),
            )
            stats = await cursor.fetchone()
            total_trades = int(stats[0])
            win_trades = int(stats[1])
            loss_trades = int(stats[2])
            max_drawdown_pct = Decimal(stats[3])

            total_decided = win_trades + loss_trades
            if total_decided > 0:
                win_rate = (
                    Decimal(win_trades) / Decimal(total_decided) * 100
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                win_rate = Decimal("0")

            # Last 30 days of ending_balance for sparkline
            cursor = await conn.execute(
                "SELECT ending_balance FROM daily_summary"
                " WHERE user_id = ? ORDER BY date DESC LIMIT 30",
                (uid,),
            )
            equity_rows = await cursor.fetchall()
            daily_equities = tuple(
                Decimal(r[0]) for r in reversed(equity_rows)
            )

            entries.append(RankingEntry(
                rank=0,  # assigned after sorting
                user_id=uid,
                nickname=nickname,
                return_pct=return_pct,
                win_rate=win_rate,
                total_trades=total_trades,
                max_drawdown_pct=max_drawdown_pct,
                daily_equities=daily_equities,
                is_me=(uid == requesting_user_id),
            ))

        # Sort by return_pct descending, assign ranks
        entries.sort(key=lambda e: e.return_pct, reverse=True)
        ranked: list[RankingEntry] = []
        for i, entry in enumerate(entries, start=1):
            ranked.append(RankingEntry(
                rank=i,
                user_id=entry.user_id,
                nickname=entry.nickname,
                return_pct=entry.return_pct,
                win_rate=entry.win_rate,
                total_trades=entry.total_trades,
                max_drawdown_pct=entry.max_drawdown_pct,
                daily_equities=entry.daily_equities,
                is_me=entry.is_me,
            ))

        return ranked
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_ranking_repo.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/repository/ranking_repo.py tests/unit/test_ranking_repo.py
git commit -m "feat(repo): add RankingRepo with ranking aggregation queries"
```

---

### Task 3: API 엔드포인트 (TDD)

**Files:**
- Create: `src/ui/api/routes/ranking.py`
- Create: `tests/unit/test_ranking_api.py`
- Modify: `src/ui/api/server.py:11-14,37`

- [ ] **Step 1: API 테스트 작성**

`tests/unit/test_ranking_api.py`:

```python
from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.types.models import RankingEntry


def _make_app():
    """Create a test FastAPI app with ranking router."""
    from src.ui.api.routes.ranking import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/ranking", tags=["ranking"])
    return app


def _mock_app_state(ranking_entries: list[RankingEntry]):
    """Create a mock app state with ranking_repo."""
    mock_ranking_repo = AsyncMock()
    mock_ranking_repo.get_ranking.return_value = ranking_entries

    mock_app = MagicMock()
    mock_app.ranking_repo = mock_ranking_repo
    mock_app.user_repo = AsyncMock()
    return mock_app


@pytest.fixture
def sample_entries():
    return [
        RankingEntry(
            rank=1, user_id=1, nickname="Alice",
            return_pct=Decimal("15.23"), win_rate=Decimal("68.50"),
            total_trades=42, max_drawdown_pct=Decimal("3.70"),
            daily_equities=(Decimal("1000000"), Decimal("1050000"), Decimal("1152300")),
            is_me=False,
        ),
        RankingEntry(
            rank=2, user_id=2, nickname="Bob",
            return_pct=Decimal("10.00"), win_rate=Decimal("55.00"),
            total_trades=20, max_drawdown_pct=Decimal("5.10"),
            daily_equities=(Decimal("1000000"), Decimal("1100000")),
            is_me=True,
        ),
    ]


def test_ranking_endpoint(sample_entries):
    app = _make_app()
    mock_state = _mock_app_state(sample_entries)

    # Patch auth dependency
    from src.ui.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": 2, "nickname": "Bob"}

    app.state.app = mock_state
    mock_state.user_repo.get_by_id.return_value = {"id": 2, "is_active": 1}

    client = TestClient(app)
    resp = client.get("/api/ranking/")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_users"] == 2
    assert data["my_rank"] == 2
    assert len(data["rankings"]) == 2

    first = data["rankings"][0]
    assert first["rank"] == 1
    assert first["nickname"] == "Alice"
    assert first["return_pct"] == "15.23"
    assert first["is_me"] is False

    second = data["rankings"][1]
    assert second["is_me"] is True
    assert len(second["daily_equities"]) == 2


def test_ranking_endpoint_empty():
    app = _make_app()
    mock_state = _mock_app_state([])

    from src.ui.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "nickname": "X"}

    app.state.app = mock_state
    mock_state.user_repo.get_by_id.return_value = {"id": 1, "is_active": 1}

    client = TestClient(app)
    resp = client.get("/api/ranking/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rankings"] == []
    assert data["my_rank"] is None
    assert data["total_users"] == 0
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/unit/test_ranking_api.py -v`
Expected: FAIL (ModuleNotFoundError: ranking)

- [ ] **Step 3: ranking 라우트 구현**

`src/ui/api/routes/ranking.py`:

```python
from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.ui.api.auth import get_current_user

router = APIRouter()


@router.get("/")
async def get_ranking(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    app = request.app.state.app
    entries = await app.ranking_repo.get_ranking(
        requesting_user_id=user["id"]
    )

    my_rank = None
    for entry in entries:
        if entry.is_me:
            my_rank = entry.rank
            break

    return {
        "rankings": [
            {
                "rank": e.rank,
                "user_id": e.user_id,
                "nickname": e.nickname,
                "return_pct": str(e.return_pct),
                "win_rate": str(e.win_rate),
                "total_trades": e.total_trades,
                "max_drawdown_pct": str(e.max_drawdown_pct),
                "daily_equities": [str(d) for d in e.daily_equities],
                "is_me": e.is_me,
            }
            for e in entries
        ],
        "my_rank": my_rank,
        "total_users": len(entries),
    }
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_ranking_api.py -v`
Expected: All 2 tests PASS

- [ ] **Step 5: server.py에 라우터 등록**

`src/ui/api/server.py` line 14에 import 추가:

```python
from src.ui.api.routes import ranking as ranking_router
```

line 37 뒤에 router 등록 추가:

```python
    app.include_router(ranking_router.router, prefix="/api/ranking", tags=["ranking"])
```

- [ ] **Step 6: runtime/app.py에 ranking_repo 초기화**

`src/runtime/app.py`에서 `self.user_repo = UserRepo(self.db)` 줄 근처에 추가:

```python
from src.repository.ranking_repo import RankingRepo
```

(imports에 추가) 그리고 `__init__` 내에서:

```python
self.ranking_repo = RankingRepo(self.db)
```

- [ ] **Step 7: Commit**

```bash
git add src/ui/api/routes/ranking.py tests/unit/test_ranking_api.py src/ui/api/server.py src/runtime/app.py
git commit -m "feat(api): add GET /api/ranking endpoint"
```

---

### Task 4: 프론트엔드 Ranking.tsx 페이지

**Files:**
- Create: `src/ui/frontend/src/pages/Ranking.tsx`
- Modify: `src/ui/frontend/src/App.tsx:5-12,87-91,115-121`

- [ ] **Step 1: Ranking.tsx 작성**

`src/ui/frontend/src/pages/Ranking.tsx`:

```tsx
import { useEffect, useState, useCallback } from "react";
import { useAuthContext } from "../context/AuthContext";
import {
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

interface RankingEntry {
  rank: number;
  user_id: number;
  nickname: string;
  return_pct: string;
  win_rate: string;
  total_trades: number;
  max_drawdown_pct: string;
  daily_equities: string[];
  is_me: boolean;
}

interface RankingResponse {
  rankings: RankingEntry[];
  my_rank: number | null;
  total_users: number;
}

export default function Ranking() {
  const { api } = useAuthContext();
  const [data, setData] = useState<RankingResponse | null>(null);
  const [loading, setLoading] = useState(true);

  const fetchRanking = useCallback(async () => {
    try {
      const res = await api.get<RankingResponse>("/api/ranking/");
      setData(res);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchRanking();
  }, [fetchRanking]);

  if (loading) return <div className="page-loading">로딩 중...</div>;
  if (!data) return <div className="page-error">데이터를 불러올 수 없습니다</div>;

  const myEntry = data.rankings.find((e) => e.is_me);

  return (
    <div className="ranking-page">
      <div className="page-header">
        <h2>투자 손익 랭킹</h2>
      </div>

      {myEntry && (
        <div className="ranking-my-summary">
          <div className="my-rank-card">
            <span className="my-rank-label">내 순위</span>
            <span className="my-rank-value">#{myEntry.rank}</span>
            <span className="my-rank-total">/ {data.total_users}명</span>
          </div>
          <div className="my-rank-card">
            <span className="my-rank-label">수익률</span>
            <span
              className={`my-rank-value ${
                Number(myEntry.return_pct) >= 0 ? "positive" : "negative"
              }`}
            >
              {Number(myEntry.return_pct) >= 0 ? "+" : ""}
              {myEntry.return_pct}%
            </span>
          </div>
          <div className="my-rank-card">
            <span className="my-rank-label">승률</span>
            <span className="my-rank-value">{myEntry.win_rate}%</span>
          </div>
        </div>
      )}

      <div className="ranking-table-wrap">
        <table className="ranking-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>닉네임</th>
              <th>수익률</th>
              <th>승률</th>
              <th>거래</th>
              <th>최대 낙폭</th>
              <th>추이</th>
            </tr>
          </thead>
          <tbody>
            {data.rankings.map((entry) => {
              const returnNum = Number(entry.return_pct);
              const medal =
                entry.rank === 1
                  ? "🥇"
                  : entry.rank === 2
                  ? "🥈"
                  : entry.rank === 3
                  ? "🥉"
                  : `${entry.rank}`;

              const sparkData = entry.daily_equities.map((v, i) => ({
                i,
                v: Number(v),
              }));

              return (
                <tr
                  key={entry.user_id}
                  className={entry.is_me ? "ranking-row-me" : ""}
                >
                  <td className="ranking-rank">
                    {entry.is_me && <span className="me-bar" />}
                    {medal}
                  </td>
                  <td className="ranking-nickname">
                    {entry.nickname}
                    {entry.is_me && <span className="me-badge">나</span>}
                  </td>
                  <td
                    className={`ranking-return ${
                      returnNum >= 0 ? "positive" : "negative"
                    }`}
                  >
                    {returnNum >= 0 ? "+" : ""}
                    {entry.return_pct}%
                  </td>
                  <td>{entry.win_rate}%</td>
                  <td>{entry.total_trades}회</td>
                  <td className="negative">-{entry.max_drawdown_pct}%</td>
                  <td className="ranking-sparkline">
                    {sparkData.length > 1 ? (
                      <ResponsiveContainer width={80} height={28}>
                        <LineChart data={sparkData}>
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke={returnNum >= 0 ? "#22c55e" : "#ef4444"}
                            strokeWidth={1.5}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <span className="no-data">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {data.rankings.length === 0 && (
              <tr>
                <td colSpan={7} className="ranking-empty">
                  아직 랭킹 데이터가 없습니다
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: App.tsx에 라우트 및 네비게이션 추가**

`src/ui/frontend/src/App.tsx`에서:

line 5 아래에 import 추가:

```tsx
import Ranking from "./pages/Ranking";
```

line 90 (리스크 NavLink 뒤, 시스템 NavLink 앞) 에 랭킹 메뉴 추가:

```tsx
          <li><NavLink to="/ranking"><span className="nav-icon">&#9734;</span> 랭킹</NavLink></li>
```

line 119 (risk Route 뒤) 에 Route 추가:

```tsx
          <Route path="/ranking" element={<Ranking />} />
```

- [ ] **Step 3: 프론트엔드 빌드 확인**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds without errors

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Ranking.tsx src/ui/frontend/src/App.tsx
git commit -m "feat(frontend): add Ranking page with sparkline charts"
```

---

### Task 5: 랭킹 페이지 CSS 스타일링

**Files:**
- Modify: 기존 CSS 파일 (프로젝트의 글로벌 스타일 파일 위치 확인 필요)

- [ ] **Step 1: 기존 CSS 파일 위치 확인**

Run: `ls src/ui/frontend/src/*.css` 또는 글로벌 스타일 파일을 찾아 위치를 확인한다.

- [ ] **Step 2: 랭킹 스타일 추가**

프로젝트의 글로벌 CSS 파일 하단에 다음 스타일을 추가한다:

```css
/* ── Ranking Page ── */
.ranking-page { padding: 0; }
.ranking-page .page-header { margin-bottom: 1.5rem; }
.ranking-page .page-header h2 { font-size: 1.25rem; font-weight: 600; }

.ranking-my-summary {
  display: flex; gap: 1rem; margin-bottom: 1.5rem; flex-wrap: wrap;
}
.my-rank-card {
  background: var(--card-bg, #1a1a2e);
  border: 1px solid var(--border, #2a2a4a);
  border-radius: 8px; padding: 1rem 1.5rem;
  display: flex; flex-direction: column; gap: 0.25rem; min-width: 140px;
}
.my-rank-label { font-size: 0.75rem; color: var(--text-muted, #888); text-transform: uppercase; }
.my-rank-value { font-size: 1.5rem; font-weight: 700; }
.my-rank-total { font-size: 0.85rem; color: var(--text-muted, #888); }

.ranking-table-wrap { overflow-x: auto; }
.ranking-table {
  width: 100%; border-collapse: collapse; font-size: 0.9rem;
}
.ranking-table th {
  text-align: left; padding: 0.75rem 1rem;
  border-bottom: 2px solid var(--border, #2a2a4a);
  font-size: 0.75rem; text-transform: uppercase;
  color: var(--text-muted, #888); font-weight: 600;
}
.ranking-table td {
  padding: 0.75rem 1rem;
  border-bottom: 1px solid var(--border, #2a2a4a);
  vertical-align: middle;
}
.ranking-table tbody tr:hover {
  background: rgba(255,255,255,0.03);
}

/* Me row highlight */
.ranking-row-me {
  background: rgba(99, 102, 241, 0.08) !important;
}
.ranking-row-me td { font-weight: 600; }
.me-bar {
  display: inline-block; width: 3px; height: 1.2em;
  background: #6366f1; border-radius: 2px;
  margin-right: 0.5rem; vertical-align: middle;
}
.me-badge {
  display: inline-block; font-size: 0.65rem;
  background: #6366f1; color: #fff;
  border-radius: 4px; padding: 0.1rem 0.4rem;
  margin-left: 0.5rem; vertical-align: middle; font-weight: 700;
}

.ranking-rank { white-space: nowrap; font-size: 1rem; }
.ranking-nickname { font-weight: 500; }
.ranking-return { font-weight: 600; font-variant-numeric: tabular-nums; }

.positive { color: #22c55e; }
.negative { color: #ef4444; }

.ranking-sparkline { width: 80px; }
.ranking-empty {
  text-align: center; padding: 3rem 1rem;
  color: var(--text-muted, #888); font-style: italic;
}
```

- [ ] **Step 3: 빌드 확인**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add <css-file-path>
git commit -m "style: add Ranking page styles with me-highlight and sparkline"
```

---

### Task 6: 전체 테스트 실행 및 검증

**Files:** (없음 — 검증만)

- [ ] **Step 1: Python 테스트 전체 실행**

Run: `uv run pytest -v`
Expected: All tests PASS (기존 + 새 ranking 테스트)

- [ ] **Step 2: 린트 확인**

Run: `uv run ruff check src/`
Expected: No errors

- [ ] **Step 3: 타입 체크**

Run: `uv run mypy src/`
Expected: No errors (또는 기존과 동일한 수준)

- [ ] **Step 4: 프론트엔드 빌드 최종 확인**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

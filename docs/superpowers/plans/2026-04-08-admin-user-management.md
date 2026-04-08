# Admin User Management & Balance Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 관리자 전용 회원 관리 페이지(`/admin`)를 추가하고, 잔고 충전/차감 기능과 이력(ledger) 추적을 구현한다.

**Architecture:** `balance_ledger` 테이블을 추가하여 모든 잔고 변경을 기록한다. `user_repo.py`에 ledger CRUD를 추가하고, `admin.py`에 잔고 관리 API를 추가한다. 프론트엔드는 `System.tsx`에서 `AdminUserPanel`을 제거하고 새 `Admin.tsx` 페이지로 이동하며, 잔고 관리 모달을 추가한다.

**Tech Stack:** Python 3.12+, FastAPI, aiosqlite, Decimal, React 18, TypeScript, Vite

---

## File Structure

| Action | Path | Responsibility |
|--------|------|----------------|
| Modify | `src/repository/database.py` | `balance_ledger` 테이블 migration 추가 |
| Modify | `src/repository/user_repo.py` | ledger INSERT/SELECT, cash_balance 조회 메서드 |
| Modify | `src/ui/api/routes/admin.py` | 잔고 충전/차감, 이력 조회 엔드포인트 |
| Create | `src/ui/frontend/src/pages/Admin.tsx` | 회원 관리 + 잔고 관리 페이지 |
| Modify | `src/ui/frontend/src/pages/System.tsx` | `AdminUserPanel` 제거 |
| Modify | `src/ui/frontend/src/App.tsx` | `/admin` 라우트 + 사이드바 메뉴 추가 |
| Create | `tests/unit/test_admin_balance.py` | 잔고 충전/차감 API 테스트 |

---

### Task 1: Database Migration — `balance_ledger` 테이블

**Files:**
- Modify: `src/repository/database.py:132-224` (`_migrate` 메서드)

- [ ] **Step 1: `_migrate()` 메서드 끝에 `balance_ledger` 테이블 생성 추가**

`src/repository/database.py`의 `_migrate()` 메서드 마지막(인덱스 생성 블록 뒤, 현재 line 224 부근)에 다음을 추가:

```python
        # ── balance_ledger table ──
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS balance_ledger (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                admin_id   INTEGER NOT NULL REFERENCES users(id),
                amount     TEXT NOT NULL,
                balance_after TEXT NOT NULL,
                memo       TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
```

- [ ] **Step 2: 앱을 시작하여 migration이 에러 없이 동작하는지 확인**

Run: `uv run python -c "import asyncio; from src.repository.database import Database; db = Database(':memory:'); asyncio.run(db.initialize()); print('OK')"`
Expected: `OK` 출력, 에러 없음

- [ ] **Step 3: Commit**

```bash
git add src/repository/database.py
git commit -m "feat: add balance_ledger table migration"
```

---

### Task 2: Repository — Ledger CRUD 및 cash_balance 조회

**Files:**
- Modify: `src/repository/user_repo.py`
- Create: `tests/unit/test_admin_balance.py`

- [ ] **Step 1: 테스트 파일 생성 — ledger 기록 및 조회 테스트 작성**

`tests/unit/test_admin_balance.py`:

```python
import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.user_repo import UserRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.initialize()
    repo = UserRepo(db)
    yield repo
    await db.close()


@pytest.fixture
async def two_users(repo: UserRepo):
    """Create admin (id=1) and normal user (id=2)."""
    admin = await repo.create(
        email="admin@test.com", password_hash="hash", nickname="admin",
    )
    user = await repo.create(
        email="user@test.com", password_hash="hash", nickname="user",
    )
    return admin, user


@pytest.mark.asyncio
async def test_get_cash_balance(repo: UserRepo, two_users):
    _, user = two_users
    balance = await repo.get_cash_balance(user["id"])
    assert balance == Decimal("5000000")


@pytest.mark.asyncio
async def test_adjust_balance_credit(repo: UserRepo, two_users):
    admin, user = two_users
    result = await repo.adjust_balance(
        user_id=user["id"],
        admin_id=admin["id"],
        amount=Decimal("3000000"),
        memo="초기 자본금 충전",
    )
    assert result["balance_before"] == Decimal("5000000")
    assert result["balance_after"] == Decimal("8000000")
    assert result["amount"] == Decimal("3000000")

    # Verify DB balance updated
    new_balance = await repo.get_cash_balance(user["id"])
    assert new_balance == Decimal("8000000")


@pytest.mark.asyncio
async def test_adjust_balance_debit(repo: UserRepo, two_users):
    admin, user = two_users
    result = await repo.adjust_balance(
        user_id=user["id"],
        admin_id=admin["id"],
        amount=Decimal("-2000000"),
        memo="차감",
    )
    assert result["balance_after"] == Decimal("3000000")


@pytest.mark.asyncio
async def test_adjust_balance_insufficient(repo: UserRepo, two_users):
    admin, user = two_users
    with pytest.raises(ValueError, match="잔고 부족"):
        await repo.adjust_balance(
            user_id=user["id"],
            admin_id=admin["id"],
            amount=Decimal("-99999999"),
            memo="과다 차감",
        )


@pytest.mark.asyncio
async def test_adjust_balance_zero_rejected(repo: UserRepo, two_users):
    admin, user = two_users
    with pytest.raises(ValueError, match="0이 될 수 없습니다"):
        await repo.adjust_balance(
            user_id=user["id"],
            admin_id=admin["id"],
            amount=Decimal("0"),
            memo="",
        )


@pytest.mark.asyncio
async def test_get_balance_history(repo: UserRepo, two_users):
    admin, user = two_users
    await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("1000000"), memo="1차 충전",
    )
    await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("-500000"), memo="차감",
    )
    history = await repo.get_balance_history(user["id"])
    assert len(history) == 2
    # 최신순
    assert history[0]["amount"] == "-500000"
    assert history[0]["balance_after"] == "5500000"
    assert history[0]["memo"] == "차감"
    assert history[1]["amount"] == "1000000"
    assert history[1]["balance_after"] == "6000000"
    assert history[1]["memo"] == "1차 충전"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/unit/test_admin_balance.py -v`
Expected: FAIL — `get_cash_balance`, `adjust_balance`, `get_balance_history` 메서드가 없음

- [ ] **Step 3: `user_repo.py`에 `get_cash_balance` 메서드 추가**

`src/repository/user_repo.py`의 `list_all` 메서드(line 91) 뒤에 추가:

```python
    async def get_cash_balance(self, user_id: int) -> Decimal:
        """Return user's current cash_balance as Decimal."""
        from decimal import Decimal as D

        conn = self._db.conn
        row = await conn.execute_fetchall(
            "SELECT cash_balance FROM account_state WHERE user_id = ?",
            (user_id,),
        )
        if not row:
            raise ValueError(f"User {user_id} has no account_state")
        return D(row[0][0])
```

파일 상단 import에 추가:

```python
from decimal import Decimal
```

- [ ] **Step 4: `user_repo.py`에 `adjust_balance` 메서드 추가**

`get_cash_balance` 메서드 뒤에 추가:

```python
    async def adjust_balance(
        self,
        *,
        user_id: int,
        admin_id: int,
        amount: Decimal,
        memo: str = "",
    ) -> dict:
        """Adjust user balance by amount. Positive = credit, negative = debit.

        Returns dict with user_id, balance_before, balance_after, amount.
        Raises ValueError if amount is 0 or result would be negative.
        """
        if amount == 0:
            raise ValueError("금액은 0이 될 수 없습니다")

        conn = self._db.conn
        current = await self.get_cash_balance(user_id)
        new_balance = current + amount
        if new_balance < 0:
            raise ValueError("잔고 부족: 차감 후 잔고가 음수가 됩니다")

        from datetime import datetime, UTC

        now = datetime.now(UTC).isoformat()

        await conn.execute(
            "UPDATE account_state SET cash_balance = ?, updated_at = ? WHERE user_id = ?",
            (str(new_balance), now, user_id),
        )
        await conn.execute(
            """INSERT INTO balance_ledger (user_id, admin_id, amount, balance_after, memo, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (user_id, admin_id, str(amount), str(new_balance), memo, now),
        )
        await conn.commit()

        return {
            "user_id": user_id,
            "balance_before": current,
            "balance_after": new_balance,
            "amount": amount,
        }
```

- [ ] **Step 5: `user_repo.py`에 `get_balance_history` 메서드 추가**

`adjust_balance` 메서드 뒤에 추가:

```python
    async def get_balance_history(self, user_id: int) -> list[dict]:
        """Return balance change history for user, newest first."""
        conn = self._db.conn
        rows = await conn.execute_fetchall(
            """SELECT bl.id, bl.admin_id, u.nickname AS admin_nickname,
                      bl.amount, bl.balance_after, bl.memo, bl.created_at
               FROM balance_ledger bl
               JOIN users u ON u.id = bl.admin_id
               WHERE bl.user_id = ?
               ORDER BY bl.id DESC""",
            (user_id,),
        )
        return [
            {
                "id": r[0],
                "admin_id": r[1],
                "admin_nickname": r[2],
                "amount": r[3],
                "balance_after": r[4],
                "memo": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]
```

- [ ] **Step 6: 테스트 실행하여 모두 통과하는지 확인**

Run: `uv run pytest tests/unit/test_admin_balance.py -v`
Expected: 6 tests PASSED

- [ ] **Step 7: Commit**

```bash
git add src/repository/user_repo.py tests/unit/test_admin_balance.py
git commit -m "feat: add balance ledger CRUD to UserRepo with tests"
```

---

### Task 3: Backend API — 잔고 관리 엔드포인트

**Files:**
- Modify: `src/ui/api/routes/admin.py`
- Modify: `tests/unit/test_admin_balance.py`

- [ ] **Step 1: API 통합 테스트 추가**

`tests/unit/test_admin_balance.py` 파일 끝에 추가:

```python
from httpx import ASGITransport, AsyncClient
from src.ui.api.server import create_app
from src.config.settings import (
    Settings, PaperTradingConfig, RiskConfig, ScreeningConfig,
    StrategyConfig, CollectorConfig, DataConfig,
)
from src.runtime.app import App


@pytest.fixture
async def admin_client():
    """Authenticated admin client with initialized app."""
    fastapi_app = create_app()
    settings = Settings(
        paper_trading=PaperTradingConfig(
            initial_balance=Decimal("5000000"), max_position_pct=Decimal("0.25"),
            max_open_positions=4, fee_rate=Decimal("0.0005"),
            slippage_rate=Decimal("0.0005"), min_order_krw=5000,
        ),
        risk=RiskConfig(
            stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
            trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
            max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
        ),
        screening=ScreeningConfig(
            min_volume_krw=Decimal("500000000"), min_volatility_pct=Decimal("1.0"),
            max_volatility_pct=Decimal("15.0"), max_coins=10,
            refresh_interval_min=30, always_include=("KRW-BTC",),
        ),
        strategy=StrategyConfig(
            lookahead_minutes=5, threshold_pct=Decimal("0.3"),
            retrain_interval_hours=6, min_confidence=Decimal("0.6"),
        ),
        collector=CollectorConfig(
            candle_timeframe=1, max_candles_per_market=200,
            market_refresh_interval_min=60,
        ),
        data=DataConfig(
            db_path=":memory:", model_dir="data/models",
            stale_candle_days=7, stale_model_days=30, stale_order_days=90,
        ),
    )
    app_instance = App(settings)
    await app_instance.db.initialize()
    fastapi_app.state.app = app_instance

    # Create admin user and get token
    from src.ui.api.auth import hash_password, create_access_token, JWT_SECRET
    from datetime import timedelta

    await app_instance.user_repo.create(
        email="admin@test.com", password_hash=hash_password("pass"), nickname="admin",
    )
    await app_instance.user_repo.create(
        email="user@test.com", password_hash=hash_password("pass"), nickname="user",
    )
    token = create_access_token(1, JWT_SECRET, timedelta(minutes=30))

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, app_instance

    await app_instance.db.close()


@pytest.mark.asyncio
async def test_api_adjust_balance(admin_client):
    client, app = admin_client
    resp = await client.post("/api/admin/users/2/balance", json={
        "amount": "3000000", "memo": "충전",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance_before"] == "5000000"
    assert data["balance_after"] == "8000000"

    # Verify runtime memory synced
    assert app.user_accounts[2].cash_balance == Decimal("8000000")


@pytest.mark.asyncio
async def test_api_adjust_balance_insufficient(admin_client):
    client, _ = admin_client
    resp = await client.post("/api/admin/users/2/balance", json={
        "amount": "-99999999",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_balance_history(admin_client):
    client, _ = admin_client
    await client.post("/api/admin/users/2/balance", json={
        "amount": "1000000", "memo": "1차",
    })
    await client.post("/api/admin/users/2/balance", json={
        "amount": "-500000", "memo": "차감",
    })
    resp = await client.get("/api/admin/users/2/balance-history")
    assert resp.status_code == 200
    history = resp.json()["history"]
    assert len(history) == 2
    assert history[0]["memo"] == "차감"


@pytest.mark.asyncio
async def test_api_list_users_includes_balance(admin_client):
    client, _ = admin_client
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    users = resp.json()
    # user id=2 should have cash_balance field
    user2 = next(u for u in users if u["id"] == 2)
    assert "cash_balance" in user2
    assert user2["cash_balance"] == "5000000"
```

- [ ] **Step 2: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/unit/test_admin_balance.py::test_api_adjust_balance -v`
Expected: FAIL — 엔드포인트가 없음 (404 또는 405)

- [ ] **Step 3: `admin.py`에 Pydantic 모델과 잔고 조정 엔드포인트 추가**

`src/ui/api/routes/admin.py`의 `SetActiveRequest` 클래스(line 15-16) 뒤에 추가:

```python
class AdjustBalanceRequest(BaseModel):
    amount: str
    memo: str = ""
```

파일 끝(line 82 뒤)에 엔드포인트 추가:

```python
@router.post("/users/{user_id}/balance")
async def adjust_balance(
    user_id: int,
    body: AdjustBalanceRequest,
    request: Request,
    admin: dict = Depends(require_admin),
):
    from decimal import Decimal, InvalidOperation

    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        amount = Decimal(body.amount)
    except InvalidOperation:
        raise HTTPException(status_code=400, detail="Invalid amount")

    try:
        result = await app.user_repo.adjust_balance(
            user_id=user_id,
            admin_id=admin["id"],
            amount=amount,
            memo=body.memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Sync runtime memory
    if user_id in app.user_accounts:
        app.user_accounts[user_id].cash_balance = result["balance_after"]

    return {
        "user_id": user_id,
        "balance_before": str(result["balance_before"]),
        "balance_after": str(result["balance_after"]),
        "amount": str(result["amount"]),
    }
```

참고: `require_admin`이 router-level dependency로 걸려 있지만, 이 엔드포인트에서는 `admin["id"]`가 필요하므로 파라미터-level `Depends(require_admin)`을 추가로 사용한다. router-level dependency는 인증만 검증하고, 파라미터-level은 admin dict를 주입받는다.

- [ ] **Step 4: `admin.py`에 잔고 이력 조회 엔드포인트 추가**

`adjust_balance` 엔드포인트 뒤에 추가:

```python
@router.get("/users/{user_id}/balance-history")
async def get_balance_history(user_id: int, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    history = await app.user_repo.get_balance_history(user_id)
    return {"history": history}
```

- [ ] **Step 5: `admin.py`의 `list_users` 엔드포인트에 `cash_balance` 필드 추가**

`list_users` 함수(line 19-33)를 수정. 각 유저 딕셔너리에 `cash_balance` 추가:

```python
@router.get("/users")
async def list_users(request: Request):
    app = request.app.state.app
    users = await app.user_repo.list_all()
    result = []
    for u in users:
        balance = await app.user_repo.get_cash_balance(u["id"])
        result.append({
            "id": u["id"],
            "email": u["email"],
            "nickname": u["nickname"],
            "is_admin": bool(u["is_admin"]),
            "is_active": bool(u["is_active"]),
            "created_at": u["created_at"],
            "cash_balance": str(balance),
        })
    return result
```

- [ ] **Step 6: runtime memory sync를 위해 `adjust_balance` 엔드포인트에서 `load_user` 활용**

`adjust_balance` 엔드포인트의 runtime memory sync 부분을 확인. 유저가 `user_accounts`에 아직 로드되지 않은 경우도 처리해야 한다. 이미 Step 3에서 `if user_id in app.user_accounts:` 조건으로 처리했으므로, 로드되지 않은 유저의 경우 DB에만 반영되고 다음 로그인/로드 시 적용된다.

- [ ] **Step 7: 모든 API 테스트 실행**

Run: `uv run pytest tests/unit/test_admin_balance.py -v`
Expected: 모든 테스트 PASSED (repo 테스트 6개 + API 테스트 4개)

- [ ] **Step 8: Commit**

```bash
git add src/ui/api/routes/admin.py tests/unit/test_admin_balance.py
git commit -m "feat: add balance adjust and history API endpoints"
```

---

### Task 4: Frontend — Admin.tsx 페이지 생성

**Files:**
- Create: `src/ui/frontend/src/pages/Admin.tsx`

- [ ] **Step 1: Admin.tsx 페이지 생성**

`src/ui/frontend/src/pages/Admin.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useAuthContext } from "../context/AuthContext";

interface UserItem {
  id: number;
  email: string;
  nickname: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  cash_balance: string;
}

interface UserSettings {
  stop_loss_pct: number;
  take_profit_pct: number;
  trailing_stop_pct: number;
}

interface BalanceHistory {
  id: number;
  admin_id: number;
  admin_nickname: string;
  amount: string;
  balance_after: string;
  memo: string;
  created_at: string;
}

function formatKRW(value: string): string {
  return Number(value).toLocaleString("ko-KR") + " KRW";
}

export default function Admin() {
  const { api } = useAuthContext();
  const { get, patchJson, postJson } = api;

  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(false);

  // Settings modal
  const [settingsUser, setSettingsUser] = useState<UserItem | null>(null);
  const [settings, setSettings] = useState<UserSettings>({ stop_loss_pct: 0, take_profit_pct: 0, trailing_stop_pct: 0 });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsError, setSettingsError] = useState("");

  // Balance modal
  const [balanceUser, setBalanceUser] = useState<UserItem | null>(null);
  const [balanceAmount, setBalanceAmount] = useState("");
  const [balanceMemo, setBalanceMemo] = useState("");
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [balanceError, setBalanceError] = useState("");
  const [balanceHistory, setBalanceHistory] = useState<BalanceHistory[]>([]);

  const fetchUsers = () => {
    get<UserItem[]>("/api/admin/users").then(setUsers).catch(() => {});
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleToggleActive = async (user: UserItem) => {
    setLoading(true);
    try {
      await patchJson(`/api/admin/users/${user.id}`, { is_active: !user.is_active });
      fetchUsers();
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  // ── Settings Modal ──
  const openSettings = async (user: UserItem) => {
    setSettingsUser(user);
    setSettingsError("");
    try {
      const s = await get<UserSettings>(`/api/admin/users/${user.id}/settings`);
      setSettings(s);
    } catch {
      setSettings({ stop_loss_pct: 0, take_profit_pct: 0, trailing_stop_pct: 0 });
    }
  };

  const handleSaveSettings = async () => {
    if (!settingsUser) return;
    setSettingsLoading(true);
    setSettingsError("");
    try {
      await patchJson(`/api/admin/users/${settingsUser.id}/settings`, settings);
      setSettingsUser(null);
    } catch (err: any) {
      setSettingsError(err.message || "저장 실패");
    } finally {
      setSettingsLoading(false);
    }
  };

  // ── Balance Modal ──
  const openBalance = async (user: UserItem) => {
    setBalanceUser(user);
    setBalanceAmount("");
    setBalanceMemo("");
    setBalanceError("");
    try {
      const data = await get<{ history: BalanceHistory[] }>(`/api/admin/users/${user.id}/balance-history`);
      setBalanceHistory(data.history);
    } catch {
      setBalanceHistory([]);
    }
  };

  const handleAdjustBalance = async () => {
    if (!balanceUser || !balanceAmount) return;
    setBalanceLoading(true);
    setBalanceError("");
    try {
      await postJson(`/api/admin/users/${balanceUser.id}/balance`, {
        amount: balanceAmount,
        memo: balanceMemo,
      });
      // Refresh
      fetchUsers();
      const data = await get<{ history: BalanceHistory[] }>(`/api/admin/users/${balanceUser.id}/balance-history`);
      setBalanceHistory(data.history);
      // Update local user cash_balance for display
      const updated = await get<UserItem[]>("/api/admin/users");
      const refreshed = updated.find(u => u.id === balanceUser.id);
      if (refreshed) setBalanceUser(refreshed);
      setBalanceAmount("");
      setBalanceMemo("");
    } catch (err: any) {
      setBalanceError(err.message || "잔고 변경 실패");
    } finally {
      setBalanceLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>회원 관리</h2>
        <div className="page-sub">회원 상태, 설정, 잔고를 관리합니다</div>
      </div>

      {/* ── User Table ── */}
      <div className="panel">
        <div className="panel-header">
          <h3>회원 목록</h3>
          <span className="badge info">{users.length}명</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {users.length === 0 ? (
            <div className="empty-state"><div className="empty-text">사용자 없음</div></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>닉네임</th>
                  <th>이메일</th>
                  <th style={{ textAlign: "right" }}>잔고</th>
                  <th style={{ textAlign: "center" }}>상태</th>
                  <th style={{ textAlign: "center" }}>가입일</th>
                  <th style={{ textAlign: "center" }}>액션</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 600 }}>{u.nickname}</td>
                    <td style={{ color: "var(--text-dim)", fontSize: 13 }}>{u.email}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                      {formatKRW(u.cash_balance)}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <span className={`badge ${u.is_active ? "info" : "loss"}`} style={{ fontSize: 10 }}>
                        {u.is_active ? "활성" : "비활성"}
                      </span>
                    </td>
                    <td style={{ textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString("ko-KR") : "-"}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                        <button
                          className="btn btn-sm btn-primary"
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => openBalance(u)}
                        >
                          잔고 관리
                        </button>
                        <button
                          className="btn btn-sm btn-ghost"
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => openSettings(u)}
                        >
                          설정
                        </button>
                        <button
                          className={`btn btn-sm ${u.is_active ? "btn-ghost" : "btn-primary"}`}
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => handleToggleActive(u)}
                          disabled={loading || u.is_admin}
                        >
                          {u.is_active ? "비활성화" : "활성화"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Balance Modal ── */}
      {balanceUser && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
          onClick={() => setBalanceUser(null)}
        >
          <div
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 560, width: "90%", maxHeight: "80vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 4px", color: "var(--text)" }}>잔고 관리</h3>
            <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--text-dim)" }}>
              {balanceUser.nickname} ({balanceUser.email})
            </p>

            <div style={{ background: "var(--bg-darker)", borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontFamily: "var(--font-mono)", fontSize: 15, textAlign: "center" }}>
              현재 잔고: <strong style={{ color: "var(--accent)" }}>{formatKRW(balanceUser.cash_balance)}</strong>
            </div>

            {balanceError && (
              <div className="auth-error" style={{ marginBottom: 12 }}>{balanceError}</div>
            )}

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="form-group" style={{ flex: 2, marginBottom: 0 }}>
                <label>금액 (양수: 충전, 음수: 차감)</label>
                <input
                  type="text"
                  placeholder="예: 5000000 또는 -1000000"
                  value={balanceAmount}
                  onChange={(e) => setBalanceAmount(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                <label>메모 (선택)</label>
                <input
                  type="text"
                  placeholder="사유"
                  value={balanceMemo}
                  onChange={(e) => setBalanceMemo(e.target.value)}
                />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginBottom: 24 }}>
              <button className="btn btn-ghost" onClick={() => setBalanceUser(null)}>닫기</button>
              <button className="btn btn-primary" onClick={handleAdjustBalance} disabled={balanceLoading || !balanceAmount}>
                {balanceLoading ? "처리 중..." : "적용"}
              </button>
            </div>

            {/* History */}
            {balanceHistory.length > 0 && (
              <>
                <h4 style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  충전/차감 이력
                </h4>
                <table className="data-table" style={{ fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>일시</th>
                      <th style={{ textAlign: "right" }}>금액</th>
                      <th style={{ textAlign: "right" }}>변경 후</th>
                      <th>메모</th>
                      <th>처리자</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balanceHistory.map((h) => (
                      <tr key={h.id}>
                        <td style={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                          {new Date(h.created_at).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: Number(h.amount) >= 0 ? "var(--profit)" : "var(--loss)" }}>
                          {Number(h.amount) >= 0 ? "+" : ""}{Number(h.amount).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                          {Number(h.balance_after).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ color: "var(--text-dim)" }}>{h.memo || "-"}</td>
                        <td>{h.admin_nickname}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Settings Modal ── */}
      {settingsUser && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
          onClick={() => setSettingsUser(null)}
        >
          <div
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 420, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 4px", color: "var(--text)" }}>사용자 설정</h3>
            <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--text-dim)" }}>{settingsUser.nickname} ({settingsUser.email})</p>
            {settingsError && (
              <div className="auth-error" style={{ marginBottom: 12 }}>{settingsError}</div>
            )}
            <div className="form-group">
              <label>손절 비율 (%)</label>
              <input type="number" step="0.1" value={settings.stop_loss_pct} onChange={e => setSettings(s => ({ ...s, stop_loss_pct: Number(e.target.value) }))} />
            </div>
            <div className="form-group">
              <label>익절 비율 (%)</label>
              <input type="number" step="0.1" value={settings.take_profit_pct} onChange={e => setSettings(s => ({ ...s, take_profit_pct: Number(e.target.value) }))} />
            </div>
            <div className="form-group">
              <label>트레일링 스탑 비율 (%)</label>
              <input type="number" step="0.1" value={settings.trailing_stop_pct} onChange={e => setSettings(s => ({ ...s, trailing_stop_pct: Number(e.target.value) }))} />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 20 }}>
              <button className="btn btn-ghost" onClick={() => setSettingsUser(null)}>취소</button>
              <button className="btn btn-primary" onClick={handleSaveSettings} disabled={settingsLoading}>
                {settingsLoading ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: TypeScript 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Admin.tsx
git commit -m "feat: add Admin page with balance management modal"
```

---

### Task 5: Frontend — 라우팅 및 사이드바 업데이트

**Files:**
- Modify: `src/ui/frontend/src/App.tsx`
- Modify: `src/ui/frontend/src/pages/System.tsx`

- [ ] **Step 1: `App.tsx`에 Admin 페이지 import 추가**

`src/ui/frontend/src/App.tsx` line 9 (`import System...`) 뒤에 추가:

```tsx
import Admin from "./pages/Admin";
```

- [ ] **Step 2: 사이드바에 관리자 전용 "회원 관리" 메뉴 추가**

`src/ui/frontend/src/App.tsx`의 `AuthenticatedApp` 컴포넌트 내 사이드바 nav 목록(line 80-86)을 수정. `</ul>` 닫는 태그 직전에 관리자 전용 메뉴 추가:

기존:
```tsx
        <ul className="sidebar-nav">
          <li><NavLink to="/" end><span className="nav-icon">&#9632;</span> 대시보드</NavLink></li>
          <li><NavLink to="/exchange"><span className="nav-icon">◇</span> 거래소</NavLink></li>
          <li><NavLink to="/strategy"><span className="nav-icon">&#9650;</span> 전략</NavLink></li>
          <li><NavLink to="/risk"><span className="nav-icon">&#9679;</span> 리스크</NavLink></li>
          <li><NavLink to="/system"><span className="nav-icon">&#9881;</span> 시스템</NavLink></li>
        </ul>
```

변경:
```tsx
        <ul className="sidebar-nav">
          <li><NavLink to="/" end><span className="nav-icon">&#9632;</span> 대시보드</NavLink></li>
          <li><NavLink to="/exchange"><span className="nav-icon">◇</span> 거래소</NavLink></li>
          <li><NavLink to="/strategy"><span className="nav-icon">&#9650;</span> 전략</NavLink></li>
          <li><NavLink to="/risk"><span className="nav-icon">&#9679;</span> 리스크</NavLink></li>
          <li><NavLink to="/system"><span className="nav-icon">&#9881;</span> 시스템</NavLink></li>
          {auth.isAdmin && <li><NavLink to="/admin"><span className="nav-icon">&#9998;</span> 회원 관리</NavLink></li>}
        </ul>
```

- [ ] **Step 3: Route 추가**

`src/ui/frontend/src/App.tsx`의 Routes 블록(line 108-115)에서 `<Route path="/system".../>` 뒤에 추가:

```tsx
          {auth.isAdmin && <Route path="/admin" element={<Admin />} />}
```

- [ ] **Step 4: `System.tsx`에서 AdminUserPanel 제거**

`src/ui/frontend/src/pages/System.tsx`에서:

1. `AdminUserPanel` 함수 전체 삭제 (line 62-236)
2. 관련 인터페이스 삭제: `UserItem` (line 17-24), `UserSettings` (line 26-30)
3. System 컴포넌트 내 `{auth.isAdmin && <AdminUserPanel />}` 라인(line 363) 삭제
4. System 컴포넌트의 `auth` destructuring이 더 이상 필요없으면 제거. 확인: `auth`는 `useAuthContext()`에서 가져오는데, AdminUserPanel 제거 후에는 System 컴포넌트에서 `auth`를 사용하지 않으므로, destructuring에서 `auth`를 제거:

기존 (line 240): `const { api, auth } = useAuthContext();`
변경: `const { api } = useAuthContext();`

- [ ] **Step 5: TypeScript 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 6: Commit**

```bash
git add src/ui/frontend/src/App.tsx src/ui/frontend/src/pages/System.tsx src/ui/frontend/src/pages/Admin.tsx
git commit -m "feat: add /admin route with sidebar menu, remove AdminUserPanel from System"
```

---

### Task 6: Lint 및 전체 테스트 검증

**Files:** 없음 (검증만)

- [ ] **Step 1: Python lint**

Run: `uv run ruff check src/`
Expected: 에러 없음 (또는 기존 경고만)

- [ ] **Step 2: Python 전체 테스트**

Run: `uv run pytest -v`
Expected: 모든 테스트 PASSED

- [ ] **Step 3: Frontend 빌드**

Run: `cd src/ui/frontend && npm run build`
Expected: 빌드 성공

- [ ] **Step 4: 최종 Commit (필요시)**

lint 수정이 필요했다면:
```bash
git add -A
git commit -m "fix: lint and build fixes for admin user management"
```

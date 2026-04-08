# Limit Buy Order Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 사용자가 지정가와 금액을 입력하면 서버가 감시하여 조건 충족 시 자동 체결하는 지정가 매수 기능 추가

**Architecture:** 새 `pending_orders` DB 테이블과 `PendingOrderRepo`로 주문 영속화. `PaperEngine.execute_limit_buy`가 동결 금액에서 포지션으로 전환. 기존 `_monitor_positions` 루프(10초)에서 체결 조건 및 만료 체크. 모든 금액 변동은 단일 DB 트랜잭션.

**Tech Stack:** Python 3.12, aiosqlite, FastAPI, React/TypeScript

**Spec:** `docs/superpowers/specs/2026-04-08-limit-order-design.md`

---

## File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `src/repository/pending_order_repo.py` | pending_orders CRUD, 트랜잭션 기반 잔고 관리 |
| Create | `tests/unit/test_pending_order_repo.py` | PendingOrderRepo 단위 테스트 |
| Create | `tests/unit/test_limit_buy.py` | PaperEngine.execute_limit_buy 단위 테스트 |
| Create | `tests/unit/test_limit_order_api.py` | API 엔드포인트 테스트 |
| Modify | `src/types/models.py` | PendingOrder dataclass 추가 |
| Modify | `src/types/enums.py` | OrderType.LIMIT 추가 |
| Modify | `src/repository/database.py` | pending_orders 테이블 스키마 + 마이그레이션 |
| Modify | `src/service/paper_engine.py` | execute_limit_buy 메서드 추가 |
| Modify | `src/runtime/app.py` | 감시 루프 확장, 서버 시작 복원, 10초 간격 |
| Modify | `src/ui/api/routes/exchange.py` | limit-buy, pending-orders API 추가 |
| Modify | `src/ui/frontend/src/pages/Exchange.tsx` | 지정가 매수 UI, 미체결 목록 |

---

### Task 1: PendingOrder 데이터 모델

**Files:**
- Modify: `src/types/models.py:98-112` (파일 끝에 추가)
- Modify: `src/types/enums.py:22-23` (OrderType에 LIMIT 추가)
- Test: `tests/unit/test_models.py`

- [ ] **Step 1: Write failing test for PendingOrder model**

```python
# tests/unit/test_models.py — 파일 끝에 추가
from src.types.models import PendingOrder


def test_pending_order_dataclass():
    po = PendingOrder(
        id="test-uuid",
        user_id=1,
        market="KRW-BTC",
        side="BUY",
        limit_price=Decimal("50000000"),
        amount_krw=Decimal("100000"),
        status="PENDING",
        created_at=1700000000,
        expires_at=1700086399,
    )
    assert po.filled_at is None
    assert po.status == "PENDING"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_models.py::test_pending_order_dataclass -v`
Expected: FAIL — `ImportError: cannot import name 'PendingOrder'`

- [ ] **Step 3: Add PendingOrder to models.py and LIMIT to OrderType**

`src/types/models.py` — 파일 끝에 추가:
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

`src/types/enums.py` — OrderType 클래스 수정:
```python
class OrderType(Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_models.py::test_pending_order_dataclass -v`
Expected: PASS

- [ ] **Step 5: Run full test suite for regressions**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All existing tests PASS (OrderType.LIMIT 추가는 기존 코드에 영향 없음)

- [ ] **Step 6: Commit**

```bash
git add src/types/models.py src/types/enums.py tests/unit/test_models.py
git commit -m "feat: add PendingOrder model and OrderType.LIMIT enum"
```

---

### Task 2: DB 스키마 — pending_orders 테이블

**Files:**
- Modify: `src/repository/database.py:5-119` (SCHEMA_SQL에 테이블 추가)
- Modify: `src/repository/database.py:293-304` (reset_trading_data에 pending_orders 추가)

- [ ] **Step 1: Add pending_orders table to SCHEMA_SQL**

`src/repository/database.py` — SCHEMA_SQL 끝 (balance_ledger 뒤, `"""` 닫기 전)에 추가:
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

- [ ] **Step 2: Add pending_orders to reset_trading_data**

`src/repository/database.py` — `reset_trading_data` 메서드의 `tables` 리스트에 `"pending_orders"` 추가:
```python
tables = ["orders", "positions", "account_state",
          "daily_summary", "risk_state", "signals", "pending_orders"]
```

- [ ] **Step 3: Run existing DB tests to verify no regressions**

Run: `uv run pytest tests/unit/test_candle_repo.py tests/unit/test_order_repo.py tests/unit/test_portfolio_repo.py -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/repository/database.py
git commit -m "feat: add pending_orders table schema"
```

---

### Task 3: PendingOrderRepo — 핵심 트랜잭션 로직

**Files:**
- Create: `src/repository/pending_order_repo.py`
- Create: `tests/unit/test_pending_order_repo.py`

- [ ] **Step 1: Write failing test — create (주문 등록 + 잔고 차감)**

```python
# tests/unit/test_pending_order_repo.py
import time
from decimal import Decimal

import pytest
import aiosqlite

from src.repository.database import Database
from src.repository.pending_order_repo import PendingOrderRepo
from src.repository.portfolio_repo import PortfolioRepository
from src.types.models import PaperAccount, PendingOrder


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def repo(db):
    return PendingOrderRepo(db)


@pytest.fixture
async def portfolio_repo(db):
    return PortfolioRepository(db)


@pytest.fixture
def account():
    return PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )


@pytest.fixture
def pending_order():
    now = int(time.time())
    return PendingOrder(
        id="test-order-1",
        user_id=1,
        market="KRW-BTC",
        side="BUY",
        limit_price=Decimal("50000000"),
        amount_krw=Decimal("100000"),
        status="PENDING",
        created_at=now,
        expires_at=now + 86400,
    )


@pytest.mark.asyncio
async def test_create_deducts_cash(repo, portfolio_repo, account, pending_order, db):
    # Save initial account state
    await portfolio_repo.save_account(account, user_id=1)

    await repo.create(pending_order, account)

    assert account.cash_balance == Decimal("9900000")

    # Verify DB has the pending order
    orders = await repo.get_pending_by_user(1)
    assert len(orders) == 1
    assert orders[0].id == "test-order-1"
    assert orders[0].status == "PENDING"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_pending_order_repo.py::test_create_deducts_cash -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.repository.pending_order_repo'`

- [ ] **Step 3: Implement PendingOrderRepo**

```python
# src/repository/pending_order_repo.py
from __future__ import annotations

import time
from decimal import Decimal

from src.repository.database import Database
from src.types.models import PaperAccount, PendingOrder


class PendingOrderRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, order: PendingOrder, account: PaperAccount) -> None:
        """Insert pending order and deduct cash in a single transaction."""
        account.cash_balance -= order.amount_krw
        await self._db.conn.execute("BEGIN")
        try:
            await self._db.conn.execute(
                """INSERT INTO pending_orders
                   (id, user_id, market, side, limit_price, amount_krw,
                    status, created_at, expires_at, filled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order.id, order.user_id, order.market, order.side,
                 str(order.limit_price), str(order.amount_krw),
                 order.status, order.created_at, order.expires_at,
                 order.filled_at),
            )
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), order.user_id),
            )
            await self._db.conn.execute("COMMIT")
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance += order.amount_krw
            raise

    async def fill(self, order_id: str) -> bool:
        """Mark order as FILLED using CAS. Returns False if already processed."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """UPDATE pending_orders SET status = 'FILLED', filled_at = ?
               WHERE id = ? AND status = 'PENDING'""",
            (now, order_id),
        )
        await self._db.conn.commit()
        return cursor.rowcount > 0

    async def cancel(self, order_id: str, account: PaperAccount, user_id: int) -> bool:
        """Cancel order and refund cash in a single transaction."""
        # Fetch order first
        cursor = await self._db.conn.execute(
            "SELECT amount_krw FROM pending_orders WHERE id = ? AND user_id = ? AND status = 'PENDING'",
            (order_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        amount = Decimal(row[0])
        await self._db.conn.execute("BEGIN")
        try:
            cur = await self._db.conn.execute(
                """UPDATE pending_orders SET status = 'CANCELLED'
                   WHERE id = ? AND status = 'PENDING'""",
                (order_id,),
            )
            if cur.rowcount == 0:
                await self._db.conn.execute("ROLLBACK")
                return False
            account.cash_balance += amount
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), user_id),
            )
            await self._db.conn.execute("COMMIT")
            return True
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance -= amount
            raise

    async def expire_all(self, user_id: int, account: PaperAccount) -> int:
        """Expire all overdue PENDING orders for a user, refund cash."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """SELECT id, amount_krw FROM pending_orders
               WHERE user_id = ? AND status = 'PENDING' AND expires_at < ?""",
            (user_id, now),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        total_refund = sum(Decimal(r[1]) for r in rows)
        ids = [r[0] for r in rows]

        await self._db.conn.execute("BEGIN")
        try:
            placeholders = ",".join("?" for _ in ids)
            await self._db.conn.execute(
                f"""UPDATE pending_orders SET status = 'EXPIRED'
                    WHERE id IN ({placeholders}) AND status = 'PENDING'""",
                ids,
            )
            account.cash_balance += total_refund
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), user_id),
            )
            await self._db.conn.execute("COMMIT")
            return len(rows)
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance -= total_refund
            raise

    async def get_pending_by_user(self, user_id: int) -> list[PendingOrder]:
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE user_id = ? AND status = 'PENDING'
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    async def get_all_pending(self) -> list[PendingOrder]:
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE status = 'PENDING'"""
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    async def load_unexpired(self) -> list[PendingOrder]:
        """Load PENDING orders that haven't expired yet (for server restart recovery)."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE status = 'PENDING' AND expires_at >= ?""",
            (now,),
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    @staticmethod
    def _row_to_order(row: tuple) -> PendingOrder:  # type: ignore[type-arg]
        return PendingOrder(
            id=row[0], user_id=int(row[1]), market=row[2], side=row[3],
            limit_price=Decimal(row[4]), amount_krw=Decimal(row[5]),
            status=row[6], created_at=int(row[7]), expires_at=int(row[8]),
            filled_at=int(row[9]) if row[9] is not None else None,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_pending_order_repo.py::test_create_deducts_cash -v`
Expected: PASS

- [ ] **Step 5: Write tests for cancel and expire_all**

`tests/unit/test_pending_order_repo.py`에 추가:

```python
@pytest.mark.asyncio
async def test_cancel_refunds_cash(repo, portfolio_repo, account, pending_order, db):
    await portfolio_repo.save_account(account, user_id=1)
    await repo.create(pending_order, account)
    assert account.cash_balance == Decimal("9900000")

    result = await repo.cancel("test-order-1", account, user_id=1)
    assert result is True
    assert account.cash_balance == Decimal("10000000")

    orders = await repo.get_pending_by_user(1)
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false(repo, portfolio_repo, account, db):
    await portfolio_repo.save_account(account, user_id=1)
    result = await repo.cancel("nonexistent", account, user_id=1)
    assert result is False


@pytest.mark.asyncio
async def test_expire_all_refunds(repo, portfolio_repo, account, db):
    await portfolio_repo.save_account(account, user_id=1)
    now = int(time.time())
    expired_order = PendingOrder(
        id="expired-1", user_id=1, market="KRW-BTC", side="BUY",
        limit_price=Decimal("50000000"), amount_krw=Decimal("200000"),
        status="PENDING", created_at=now - 100000, expires_at=now - 1,
    )
    # Create with manual cash deduction
    await repo.create(expired_order, account)
    assert account.cash_balance == Decimal("9800000")

    count = await repo.expire_all(1, account)
    assert count == 1
    assert account.cash_balance == Decimal("10000000")


@pytest.mark.asyncio
async def test_fill_cas_prevents_double_fill(repo, portfolio_repo, account, pending_order, db):
    await portfolio_repo.save_account(account, user_id=1)
    await repo.create(pending_order, account)

    first = await repo.fill("test-order-1")
    assert first is True

    second = await repo.fill("test-order-1")
    assert second is False
```

- [ ] **Step 6: Run all repo tests**

Run: `uv run pytest tests/unit/test_pending_order_repo.py -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/repository/pending_order_repo.py tests/unit/test_pending_order_repo.py
git commit -m "feat: add PendingOrderRepo with transactional money safety"
```

---

### Task 4: PaperEngine.execute_limit_buy

**Files:**
- Modify: `src/service/paper_engine.py:39-117` (execute_limit_buy 메서드 추가)
- Create: `tests/unit/test_limit_buy.py`

- [ ] **Step 1: Write failing test**

```python
# tests/unit/test_limit_buy.py
from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.service.paper_engine import PaperEngine
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import PaperAccount


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def test_execute_limit_buy_no_cash_deduction():
    """execute_limit_buy should NOT deduct cash (already frozen)."""
    engine = PaperEngine(make_pt_config())
    # Cash is 9,900,000 because 100,000 was already frozen
    account = PaperAccount(Decimal("10000000"), Decimal("9900000"), {})
    frozen_amount = Decimal("100000")
    current_price = Decimal("49000000")  # below limit

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", current_price, frozen_amount, reason="LIMIT_BUY",
    )

    assert order.status == OrderStatus.FILLED
    assert order.order_type == OrderType.LIMIT
    assert order.side == OrderSide.BUY
    assert "KRW-BTC" in account.positions
    # Cash should have increased by refund (frozen - actual cost)
    assert refund >= Decimal("0")
    # The original cash should NOT have been further deducted
    assert account.cash_balance >= Decimal("9900000")


def test_execute_limit_buy_refund_calculation():
    """Refund = frozen_amount - (actual_spend + fee)."""
    engine = PaperEngine(make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9900000"), {})
    frozen_amount = Decimal("100000")
    current_price = Decimal("50000000")

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", current_price, frozen_amount, reason="LIMIT_BUY",
    )

    actual_spend_plus_fee = frozen_amount - refund
    assert actual_spend_plus_fee > Decimal("0")
    assert actual_spend_plus_fee <= frozen_amount
    # Cash = 9,900,000 + refund
    assert account.cash_balance == Decimal("9900000") + refund


def test_execute_limit_buy_adds_to_existing_position():
    """When position already exists, should update weighted average."""
    from src.types.models import Position

    engine = PaperEngine(make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9800000"), {})
    account.positions["KRW-BTC"] = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("51000000"), quantity=Decimal("0.001"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("51000000"), total_invested=Decimal("51000"),
    )

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", Decimal("49000000"), Decimal("100000"), reason="LIMIT_BUY",
    )

    pos = account.positions["KRW-BTC"]
    assert pos.quantity > Decimal("0.001")
    assert pos.add_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_limit_buy.py -v`
Expected: FAIL — `AttributeError: 'PaperEngine' object has no attribute 'execute_limit_buy'`

- [ ] **Step 3: Implement execute_limit_buy**

`src/service/paper_engine.py` — `execute_buy` 메서드 뒤에 추가:

```python
    def execute_limit_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        frozen_amount: Decimal,
        reason: str | None = None,
    ) -> tuple[Order, Decimal]:
        """Execute a limit buy using pre-frozen cash.

        Returns (order, refund) where refund is the difference between
        frozen_amount and actual cost (spend + fee). Refund is added to cash.
        """
        fill_price = current_price * (_ONE + self._config.slippage_rate)
        quantity = _quantize_quantity(frozen_amount, fill_price)
        actual_spend = _truncate_krw(quantity * fill_price)
        fee = _truncate_krw(actual_spend * self._config.fee_rate)
        total_cost = actual_spend + fee
        refund = frozen_amount - total_cost
        now = int(time.time())

        # Refund the difference to cash (do NOT deduct — already frozen)
        account.cash_balance += refund

        trade_mode = "MANUAL"

        existing = account.positions.get(market)
        if existing is not None:
            new_total_invested = existing.total_invested + actual_spend
            new_quantity = existing.quantity + quantity
            new_entry_price = (
                new_total_invested / new_quantity
                if new_quantity > _ZERO else fill_price
            )
            existing.entry_price = new_entry_price
            existing.quantity = new_quantity
            existing.total_invested = new_total_invested
            existing.add_count += 1
            existing.highest_price = max(existing.highest_price, fill_price)
            existing.trade_mode = "MANUAL"
        else:
            account.positions[market] = Position(
                market=market,
                side=OrderSide.BUY,
                entry_price=fill_price,
                quantity=quantity,
                entry_time=now,
                unrealized_pnl=_ZERO,
                highest_price=fill_price,
                add_count=0,
                total_invested=actual_spend,
                trade_mode=trade_mode,
            )

        order = Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.BUY,
            order_type=OrderType.LIMIT,
            price=current_price,
            quantity=quantity,
            status=OrderStatus.FILLED,
            signal_confidence=0.0,
            reason=reason if reason else "LIMIT_BUY",
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )
        return order, refund
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_limit_buy.py -v`
Expected: All PASS

- [ ] **Step 5: Run existing paper_engine tests for regressions**

Run: `uv run pytest tests/unit/test_paper_engine.py -v`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/service/paper_engine.py tests/unit/test_limit_buy.py
git commit -m "feat: add PaperEngine.execute_limit_buy for frozen-amount execution"
```

---

### Task 5: Runtime — 감시 루프 확장 + 서버 복원

**Files:**
- Modify: `src/runtime/app.py:60-114` (PendingOrderRepo import + 초기화)
- Modify: `src/runtime/app.py:172-231` (start에 복원 로직 + 10초 간격)
- Modify: `src/runtime/app.py:634-722` (_monitor_positions 확장)

- [ ] **Step 1: Add PendingOrderRepo import and initialization in App.__init__**

`src/runtime/app.py` — imports에 추가:
```python
from src.repository.pending_order_repo import PendingOrderRepo
```

`__init__` 메서드, `self.portfolio_repo` 바로 뒤에 추가:
```python
        self.pending_order_repo = PendingOrderRepo(self.db)
```

- [ ] **Step 2: Add server-restart recovery in App.start()**

`src/runtime/app.py` — `start()` 메서드, `await self._cleanup_stale_data()` 뒤에 추가:
```python
        # Recover pending limit orders
        await self._recover_pending_orders()
```

`_monitor_positions` 간격을 30 → 10으로 변경:
```python
        self.scheduler.schedule_interval(
            "monitor_positions", self._monitor_positions,
            interval_seconds=10,
        )
```

- [ ] **Step 3: Implement _recover_pending_orders**

`src/runtime/app.py` — `_monitor_positions` 메서드 앞에 추가:

```python
    async def _recover_pending_orders(self) -> None:
        """Recover pending orders on server restart: expire overdue, log active."""
        for user_id, account in self.user_accounts.items():
            expired = await self.pending_order_repo.expire_all(user_id, account)
            if expired:
                logger.info("Expired %d pending orders for user %d on startup", expired, user_id)
                await self.portfolio_repo.save_account(account, user_id)

        active = await self.pending_order_repo.get_all_pending()
        if active:
            logger.info("Recovered %d active pending orders", len(active))
```

- [ ] **Step 4: Extend _monitor_positions to check pending orders**

`src/runtime/app.py` — `_monitor_positions` 메서드 끝 (기존 for 루프 뒤)에 추가:

```python
        # Check pending limit orders
        await self._check_pending_orders()
```

- [ ] **Step 5: Implement _check_pending_orders**

`src/runtime/app.py` — `_monitor_positions` 메서드 뒤에 추가:

```python
    async def _check_pending_orders(self) -> None:
        """Check all pending limit orders for fill conditions and expiry."""
        pending = await self.pending_order_repo.get_all_pending()
        if not pending:
            return

        now = int(time.time())

        for po in pending:
            account = self.user_accounts.get(po.user_id)
            if account is None:
                continue

            # Expire check
            if po.expires_at < now:
                expired = await self.pending_order_repo.expire_all(po.user_id, account)
                if expired:
                    await self._save_user_state(po.user_id)
                    self._push_ws_message(po.user_id, {
                        "type": "pending_order_expired",
                        "data": {"order_id": po.id, "market": po.market},
                    })
                continue

            # Fill check: current_price <= limit_price
            price = self.upbit_ws.get_price(po.market)
            if price is None:
                continue

            if price <= po.limit_price:
                filled = await self.pending_order_repo.fill(po.id)
                if not filled:
                    continue  # Already processed (CAS)

                order, refund = self.paper_engine.execute_limit_buy(
                    account, po.market, price, po.amount_krw, reason="LIMIT_BUY",
                )

                # Persist refund to account_state
                await self.order_repo.save(order, po.user_id)
                rm = self.user_risk.get(po.user_id)
                if rm:
                    rm.record_trade()
                await self._save_user_state(po.user_id)

                self._push_ws_message(po.user_id, {
                    "type": "pending_order_filled",
                    "data": {
                        "order_id": po.id,
                        "market": order.market,
                        "side": order.side.value,
                        "price": str(order.fill_price),
                        "quantity": str(order.quantity),
                        "refund": str(refund),
                    },
                })
                logger.info(
                    "Limit order %s filled: %s @ %s for user %d",
                    po.id, po.market, price, po.user_id,
                )
```

- [ ] **Step 6: Run lint and type check**

Run: `uv run ruff check src/runtime/app.py && uv run mypy src/runtime/app.py --ignore-missing-imports`
Expected: No errors

- [ ] **Step 7: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: extend monitor loop for limit order fill/expire (10s interval)"
```

---

### Task 6: API 엔드포인트

**Files:**
- Modify: `src/ui/api/routes/exchange.py`
- Create: `tests/unit/test_limit_order_api.py`

- [ ] **Step 1: Write failing test for limit-buy endpoint**

```python
# tests/unit/test_limit_order_api.py
import time
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.ui.api.routes.exchange import router


def _make_app():
    """Create a test app with mocked state."""
    app = FastAPI()
    app.include_router(router, prefix="/api/exchange")

    state = MagicMock()
    state.app = MagicMock()
    state.app.settings.paper_trading.min_order_krw = 5000

    account = MagicMock()
    account.cash_balance = Decimal("10000000")
    account.positions = {}
    state.app.user_accounts = {1: account}
    state.app.user_risk = {1: MagicMock()}
    state.app.paper_engine.safe_buy_amount.return_value = Decimal("9990000")

    pending_repo = AsyncMock()
    state.app.pending_order_repo = pending_repo
    state.app._save_user_state = AsyncMock()
    state.app._push_ws_message = MagicMock()

    app.state = state
    return app, state


@pytest.fixture
def client():
    app, state = _make_app()
    with patch("src.ui.api.routes.exchange.get_current_user", return_value={"id": 1}):
        yield TestClient(app), state


def test_limit_buy_success(client):
    test_client, state = client
    response = test_client.post("/api/exchange/limit-buy", json={
        "market": "KRW-BTC",
        "limit_price": "50000000",
        "amount_krw": "100000",
    })
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    assert data["pending_order"]["market"] == "KRW-BTC"
    assert data["pending_order"]["status"] == "PENDING"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_limit_order_api.py::test_limit_buy_success -v`
Expected: FAIL — endpoint not found (404)

- [ ] **Step 3: Add API models and endpoints**

`src/ui/api/routes/exchange.py` — imports에 추가:
```python
import time
import uuid
from datetime import datetime, timezone, timedelta

from src.types.models import PendingOrder
```

기존 `ExitOrdersRequest` 뒤에 request model 추가:
```python
class LimitBuyRequest(BaseModel):
    market: str
    limit_price: str
    amount_krw: str
```

`max_buy_amount` 엔드포인트 뒤에 새 엔드포인트 추가:

```python
def _end_of_day_kst() -> int:
    """Return Unix timestamp for 23:59:59 KST today."""
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    eod = now_kst.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(eod.timestamp())


@router.post("/limit-buy")
async def create_limit_buy(
    request: Request, body: LimitBuyRequest, user: dict = Depends(get_current_user),
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    amount = Decimal(body.amount_krw)
    limit_price = Decimal(body.limit_price)

    if limit_price <= 0:
        return {"success": False, "error": "지정가는 0보다 커야 합니다"}

    if amount < app.settings.paper_trading.min_order_krw:
        return {"success": False, "error": f"최소 주문 금액({app.settings.paper_trading.min_order_krw}원) 미달"}

    safe_max = app.paper_engine.safe_buy_amount(account.cash_balance)
    if amount > safe_max:
        return {"success": False, "error": f"잔고 부족 (수수료 포함 최대 {safe_max:,.0f}원)"}

    existing = account.positions.get(body.market)
    if existing is None and len(account.positions) >= app.settings.paper_trading.max_open_positions:
        # Also count pending orders for different markets
        return {"success": False, "error": "포지션 한도 도달"}

    now = int(time.time())
    pending_order = PendingOrder(
        id=str(uuid.uuid4()),
        user_id=user_id,
        market=body.market,
        side="BUY",
        limit_price=limit_price,
        amount_krw=amount,
        status="PENDING",
        created_at=now,
        expires_at=_end_of_day_kst(),
    )

    await app.pending_order_repo.create(pending_order, account)
    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "pending_order_placed",
        "data": {
            "order_id": pending_order.id,
            "market": pending_order.market,
            "limit_price": str(pending_order.limit_price),
            "amount_krw": str(pending_order.amount_krw),
        },
    })

    return {
        "success": True,
        "pending_order": {
            "id": pending_order.id,
            "market": pending_order.market,
            "limit_price": str(pending_order.limit_price),
            "amount_krw": str(pending_order.amount_krw),
            "status": pending_order.status,
            "created_at": pending_order.created_at,
            "expires_at": pending_order.expires_at,
        },
    }


@router.delete("/limit-buy/{order_id}")
async def cancel_limit_buy(
    request: Request, order_id: str, user: dict = Depends(get_current_user),
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    result = await app.pending_order_repo.cancel(order_id, account, user_id)
    if not result:
        return {"success": False, "error": "주문을 찾을 수 없거나 이미 처리되었습니다"}

    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "pending_order_cancelled",
        "data": {"order_id": order_id},
    })
    return {"success": True}


@router.get("/pending-orders")
async def get_pending_orders(
    request: Request, user: dict = Depends(get_current_user),
) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    user_id = user["id"]
    orders = await app.pending_order_repo.get_pending_by_user(user_id)
    return [
        {
            "id": o.id,
            "market": o.market,
            "limit_price": str(o.limit_price),
            "amount_krw": str(o.amount_krw),
            "status": o.status,
            "created_at": o.created_at,
            "expires_at": o.expires_at,
        }
        for o in orders
    ]
```

- [ ] **Step 4: Run API tests**

Run: `uv run pytest tests/unit/test_limit_order_api.py -v`
Expected: All PASS

- [ ] **Step 5: Run lint**

Run: `uv run ruff check src/ui/api/routes/exchange.py`
Expected: No errors

- [ ] **Step 6: Commit**

```bash
git add src/ui/api/routes/exchange.py tests/unit/test_limit_order_api.py
git commit -m "feat: add limit-buy API endpoints (create, cancel, list)"
```

---

### Task 7: Frontend — 지정가 매수 UI

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx`

- [ ] **Step 1: Add PendingOrder type and state**

`Exchange.tsx` — `OrderResult` interface 뒤에 추가:

```typescript
interface PendingOrderItem {
  id: string;
  market: string;
  limit_price: string;
  amount_krw: string;
  status: string;
  created_at: number;
  expires_at: number;
}
```

- [ ] **Step 2: Add order type toggle and limit price state to OrderPanel**

`OrderPanel` 함수 안, 기존 state 선언 뒤에 추가:

```typescript
  const [orderType, setOrderType] = useState<"market" | "limit">("market");
  const [limitPrice, setLimitPrice] = useState("");
  const [pendingOrders, setPendingOrders] = useState<PendingOrderItem[]>([]);
```

가격이 바뀔 때 지정가 기본값 업데이트:
```typescript
  useEffect(() => {
    if (orderType === "limit" && !limitPrice && Number(price) > 0) {
      setLimitPrice(price);
    }
  }, [price, orderType, limitPrice]);
```

미체결 주문 조회:
```typescript
  const fetchPendingOrders = useCallback(async () => {
    try {
      const res = await get<PendingOrderItem[]>("/api/exchange/pending-orders");
      setPendingOrders(res.filter((o) => o.market === market));
    } catch { /* ignore */ }
  }, [get, market]);

  useEffect(() => {
    fetchPendingOrders();
  }, [fetchPendingOrders, tradesRefresh]);
```

- [ ] **Step 3: Add limit buy submit handler**

```typescript
  const handleLimitBuy = async () => {
    if (!amount || Number(amount) <= 0 || !limitPrice || Number(limitPrice) <= 0) return;
    const qty = (Number(amount) / Number(limitPrice)).toFixed(8);
    setConfirm({
      side: "buy",
      market,
      price: limitPrice,
      quantity: qty,
      amount,
    });
  };

  const executeLimitBuy = async () => {
    if (!amount || !limitPrice) return;
    setConfirm(null);
    try {
      const res = await postJson<{ success: boolean; error?: string; pending_order?: PendingOrderItem }>(
        "/api/exchange/limit-buy",
        { market, limit_price: limitPrice, amount_krw: amount },
      );
      if (res.success) {
        showResult("success", `지정가 매수 신청 — ₩${formatPrice(limitPrice)} × ${formatKRW(amount)}`);
        setAmount("");
        setLimitPrice("");
        fetchPendingOrders();
      } else {
        showResult("error", res.error ?? "지정가 매수 실패");
      }
    } catch {
      showResult("error", "요청 실패");
    }
  };
```

- [ ] **Step 4: Add cancel handler**

```typescript
  const cancelPendingOrder = async (orderId: string) => {
    try {
      const res = await postJson<{ success: boolean; error?: string }>(
        `/api/exchange/limit-buy/${orderId}`,
        {},
      );
      if (res.success) {
        showResult("success", "지정가 주문 취소됨");
        fetchPendingOrders();
      } else {
        showResult("error", res.error ?? "취소 실패");
      }
    } catch {
      showResult("error", "취소 실패");
    }
  };
```

Note: DELETE 메서드를 사용해야 하므로 `postJson` 대신 fetch를 직접 사용하거나, api에 `deleteJson` 헬퍼가 있는지 확인. 없으면 다음과 같이 수정:

```typescript
  const cancelPendingOrder = async (orderId: string) => {
    try {
      const API_BASE = import.meta.env.VITE_API_URL || "";
      const res = await fetch(`${API_BASE}/api/exchange/limit-buy/${orderId}`, {
        method: "DELETE",
        headers: { "Content-Type": "application/json", ...(api.getAuthHeaders?.() || {}) },
      });
      const data = await res.json();
      if (data.success) {
        showResult("success", "지정가 주문 취소됨");
        fetchPendingOrders();
      } else {
        showResult("error", data.error ?? "취소 실패");
      }
    } catch {
      showResult("error", "취소 실패");
    }
  };
```

(구현 시 AuthContext의 API 구조에 맞춰 조정)

- [ ] **Step 5: Modify buy tab UI — add order type toggle**

매수 탭 JSX에서 기존 `<div className="order-form">` 내부 맨 위에 주문 유형 토글 추가:

```tsx
<div className="order-type-toggle">
  <button
    className={`order-type-btn${orderType === "market" ? " active" : ""}`}
    onClick={() => { setOrderType("market"); setLimitPrice(""); }}
  >
    시장가
  </button>
  <button
    className={`order-type-btn${orderType === "limit" ? " active" : ""}`}
    onClick={() => { setOrderType("limit"); setLimitPrice(price); }}
  >
    지정가
  </button>
</div>
```

지정가 선택 시 가격 입력 필드 (현재가 아래, amount input 위에):

```tsx
{orderType === "limit" && (
  <div className="order-info-row" style={{ marginBottom: 8 }}>
    <span className="order-label">지정가</span>
    <input
      className="order-input"
      type="number"
      placeholder="매수 희망 가격"
      value={limitPrice}
      onChange={(e) => setLimitPrice(e.target.value)}
    />
  </div>
)}
```

매수 버튼을 조건부로 변경:

```tsx
<button
  className="btn btn-accent order-submit"
  onClick={orderType === "market" ? handleBuy : handleLimitBuy}
  disabled={exceedsCash || amountNum <= 0 || (orderType === "limit" && Number(limitPrice) <= 0)}
>
  {orderType === "market" ? "매수 주문" : "지정가 매수 신청"}
</button>
```

확인 모달 onConfirm도 조건부:
```tsx
{confirm && (
  <OrderConfirmModal
    info={confirm}
    onConfirm={() =>
      confirm.side === "buy"
        ? (orderType === "limit" ? executeLimitBuy() : executeBuy())
        : executeSell(confirm.fraction!)
    }
    onCancel={() => setConfirm(null)}
  />
)}
```

- [ ] **Step 6: Add pending orders list section**

RecentTrades 위에 미체결 주문 목록 추가:

```tsx
{pendingOrders.length > 0 && (
  <div className="pending-orders-section">
    <h4>미체결 지정가 주문</h4>
    <div className="pending-orders-list">
      {pendingOrders.map((po) => (
        <div key={po.id} className="pending-order-item">
          <div className="pending-order-info">
            <span className="pending-order-price">₩{formatPrice(po.limit_price)}</span>
            <span className="pending-order-amount">{formatKRW(po.amount_krw)}</span>
            <span className="pending-order-expiry">
              만료 {new Date(po.expires_at * 1000).toLocaleTimeString("ko-KR", {
                hour: "2-digit", minute: "2-digit",
              })}
            </span>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => cancelPendingOrder(po.id)}
          >
            취소
          </button>
        </div>
      ))}
    </div>
  </div>
)}
```

- [ ] **Step 7: Add CSS styles**

`src/ui/frontend/src/index.css`에 추가:

```css
/* Order type toggle */
.order-type-toggle {
  display: flex;
  gap: 4px;
  margin-bottom: 12px;
  background: var(--bg-card);
  border-radius: 8px;
  padding: 2px;
}
.order-type-btn {
  flex: 1;
  padding: 6px 0;
  border: none;
  border-radius: 6px;
  background: transparent;
  color: var(--text-dim);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
}
.order-type-btn.active {
  background: var(--accent);
  color: #fff;
}

/* Pending orders */
.pending-orders-section {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--border);
}
.pending-orders-section h4 {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  color: var(--text-secondary);
}
.pending-order-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
}
.pending-order-info {
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 12px;
}
.pending-order-price {
  font-weight: 600;
  color: var(--text-primary);
}
.pending-order-amount {
  color: var(--text-secondary);
}
.pending-order-expiry {
  color: var(--text-dim);
  font-size: 11px;
}
.btn-sm {
  padding: 4px 8px;
  font-size: 11px;
}
```

- [ ] **Step 8: Build and verify no TypeScript errors**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 9: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx src/ui/frontend/src/index.css
git commit -m "feat(frontend): add limit buy order UI with pending orders list"
```

---

### Task 8: OrderConfirmModal 지정가 정보 표시

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx:296-374`

- [ ] **Step 1: Extend ConfirmInfo with optional limitOrder flag**

```typescript
interface ConfirmInfo {
  side: "buy" | "sell";
  market: string;
  price: string;
  quantity: string;
  amount: string;
  fraction?: string;
  isLimit?: boolean;  // 추가
}
```

- [ ] **Step 2: Update handleLimitBuy to set isLimit**

```typescript
  const handleLimitBuy = async () => {
    if (!amount || Number(amount) <= 0 || !limitPrice || Number(limitPrice) <= 0) return;
    const qty = (Number(amount) / Number(limitPrice)).toFixed(8);
    setConfirm({
      side: "buy",
      market,
      price: limitPrice,
      quantity: qty,
      amount,
      isLimit: true,
    });
  };
```

- [ ] **Step 3: Update OrderConfirmModal to show limit info**

매수 섹션에 조건부 추가 (기존 "투자 금액" 행 위):

```tsx
{info.isLimit && (
  <>
    <div className="order-confirm-row">
      <span className="order-confirm-label">주문 유형</span>
      <span className="order-confirm-value" style={{ color: "var(--accent)" }}>지정가</span>
    </div>
    <div className="order-confirm-row">
      <span className="order-confirm-label">만료</span>
      <span className="order-confirm-value">오늘 23:59</span>
    </div>
  </>
)}
```

기존 "현재가" 라벨을 지정가일 때 "지정가"로 변경:

```tsx
<div className="order-confirm-row">
  <span className="order-confirm-label">{info.isLimit ? "지정가" : "현재가"}</span>
  <span className="order-confirm-value">₩{formatPrice(info.price)}</span>
</div>
```

- [ ] **Step 4: Build and verify**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx
git commit -m "feat(frontend): show limit order details in confirm modal"
```

---

### Task 9: WebSocket 알림 연동

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx` (WS 메시지 핸들링)

- [ ] **Step 1: Add WS message handling for pending order events**

Exchange 컴포넌트 안에서 WebSocket 메시지를 처리하는 부분을 찾아서, 기존 `order_filled` 핸들링 근처에 추가:

```typescript
// WS message handler 내부에 추가
if (msg.type === "pending_order_filled") {
  // Refresh pending orders and portfolio
  fetchPendingOrders();
  // Show toast notification
}
if (msg.type === "pending_order_expired") {
  fetchPendingOrders();
}
if (msg.type === "pending_order_cancelled") {
  fetchPendingOrders();
}
```

Note: 실제 WS 메시지 핸들링 구조(useWebSocket hook의 onMessage 콜백 등)에 맞춰 조정. `fetchPendingOrders`를 OrderPanel에서 상위 컴포넌트로 끌어올리거나, WS 이벤트가 OrderPanel 안에서 직접 처리 가능하도록 구조 확인 필요.

- [ ] **Step 2: Build and verify**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx
git commit -m "feat(frontend): handle pending order WS notifications"
```

---

### Task 10: Full Integration Test + Lint

**Files:**
- All modified files

- [ ] **Step 1: Run full backend test suite**

Run: `uv run pytest tests/ -v --tb=short`
Expected: All tests PASS

- [ ] **Step 2: Run ruff lint on all changed Python files**

Run: `uv run ruff check src/types/models.py src/types/enums.py src/repository/database.py src/repository/pending_order_repo.py src/service/paper_engine.py src/runtime/app.py src/ui/api/routes/exchange.py`
Expected: No errors

- [ ] **Step 3: Run mypy**

Run: `uv run mypy src/ --ignore-missing-imports`
Expected: No new errors

- [ ] **Step 4: Run structural tests**

Run: `uv run pytest tests/structural/ -v`
Expected: All PASS (layer dependency and decimal enforcement)

- [ ] **Step 5: Run frontend build**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Final commit if any fixups needed**

```bash
git add -A
git commit -m "chore: fix lint/type issues from limit order implementation"
```

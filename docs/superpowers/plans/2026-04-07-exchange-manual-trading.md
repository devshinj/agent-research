# Exchange Page & Manual Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an Exchange page with real-time Upbit market data, manual buy/sell capability, and per-position AUTO/MANUAL mode management.

**Architecture:** Extend the Position model with `trade_mode`/`stop_loss_price`/`take_profit_price` fields. Add an Upbit WebSocket service for real-time ticker streaming. Create exchange API routes for manual orders and position mode management. Build a new Exchange page with left-side market list and right-side chart+order panel.

**Tech Stack:** Python 3.12, FastAPI, aiosqlite, websockets, React 19, TypeScript, lightweight-charts, recharts

---

## File Structure

### New Files
- `src/service/upbit_ws.py` — Upbit WebSocket ticker streaming service with reconnection and REST fallback
- `src/ui/api/routes/exchange.py` — Manual order and position mode API endpoints
- `src/ui/frontend/src/pages/Exchange.tsx` — Exchange page with market list, chart, and order panel

### Modified Files
- `src/types/models.py:20-30` — Add `trade_mode`, `stop_loss_price`, `take_profit_price` to Position
- `src/repository/database.py:60-71` — Add 3 columns to positions table schema
- `src/repository/portfolio_repo.py:62-123` — Update save/load to handle new Position fields
- `src/service/paper_engine.py:46-106` — Accept optional `reason` parameter in execute_buy, set trade_mode on positions
- `src/service/portfolio.py:29-46` — Add MANUAL position exit-order checking
- `src/runtime/app.py:54-100` — Initialize UpbitWebSocketService, wire WebSocket relay
- `src/ui/api/server.py:9,22-26` — Register exchange router
- `src/ui/frontend/src/App.tsx` — Add Exchange route and nav item
- `src/ui/frontend/src/pages/Dashboard.tsx` — Add mode badge/toggle to positions table, reason badge to trade history
- `src/ui/frontend/src/index.css` — Price flash animations, exchange page styles

---

### Task 1: Extend Position Model

**Files:**
- Modify: `src/types/models.py:19-30`
- Test: `tests/unit/test_position_model.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_position_model.py
from decimal import Decimal
from src.types.enums import OrderSide
from src.types.models import Position


def test_position_has_trade_mode_default() -> None:
    p = Position(
        market="KRW-BTC",
        side=OrderSide.BUY,
        entry_price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        entry_time=1000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
    )
    assert p.trade_mode == "AUTO"
    assert p.stop_loss_price is None
    assert p.take_profit_price is None


def test_position_manual_with_exit_orders() -> None:
    p = Position(
        market="KRW-ETH",
        side=OrderSide.BUY,
        entry_price=Decimal("3000000"),
        quantity=Decimal("0.1"),
        entry_time=1000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("3000000"),
        trade_mode="MANUAL",
        stop_loss_price=Decimal("2800000"),
        take_profit_price=Decimal("3500000"),
    )
    assert p.trade_mode == "MANUAL"
    assert p.stop_loss_price == Decimal("2800000")
    assert p.take_profit_price == Decimal("3500000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_position_model.py -v`
Expected: FAIL with `TypeError: Position.__init__() got an unexpected keyword argument 'trade_mode'`

- [ ] **Step 3: Add fields to Position dataclass**

In `src/types/models.py`, replace the Position class (lines 19-30):

```python
@dataclass
class Position:
    market: str
    side: OrderSide
    entry_price: Decimal
    quantity: Decimal
    entry_time: int
    unrealized_pnl: Decimal
    highest_price: Decimal
    add_count: int = 0
    total_invested: Decimal = field(default_factory=lambda: Decimal("0"))
    partial_sold: bool = False
    trade_mode: str = "AUTO"
    stop_loss_price: Decimal | None = None
    take_profit_price: Decimal | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_position_model.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/types/models.py tests/unit/test_position_model.py
git commit -m "feat: add trade_mode, stop_loss_price, take_profit_price to Position"
```

---

### Task 2: Extend Database Schema

**Files:**
- Modify: `src/repository/database.py:60-71`
- Modify: `src/repository/portfolio_repo.py:62-123`
- Test: `tests/unit/test_portfolio_repo_mode.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_portfolio_repo_mode.py
import asyncio
from decimal import Decimal

import pytest

from src.repository.database import Database
from src.repository.portfolio_repo import PortfolioRepository
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


@pytest.fixture
def repo(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    asyncio.get_event_loop().run_until_complete(db.initialize())
    yield PortfolioRepository(db)
    asyncio.get_event_loop().run_until_complete(db.close())


def test_save_load_position_with_trade_mode(repo: PortfolioRepository) -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("9000000"),
        positions={
            "KRW-BTC": Position(
                market="KRW-BTC",
                side=OrderSide.BUY,
                entry_price=Decimal("50000000"),
                quantity=Decimal("0.001"),
                entry_time=1000,
                unrealized_pnl=Decimal("0"),
                highest_price=Decimal("50000000"),
                trade_mode="MANUAL",
                stop_loss_price=Decimal("48000000"),
                take_profit_price=Decimal("55000000"),
            ),
        },
    )
    asyncio.get_event_loop().run_until_complete(repo.save_account(account))
    loaded = asyncio.get_event_loop().run_until_complete(
        repo.load_account(Decimal("10000000"))
    )
    assert loaded is not None
    pos = loaded.positions["KRW-BTC"]
    assert pos.trade_mode == "MANUAL"
    assert pos.stop_loss_price == Decimal("48000000")
    assert pos.take_profit_price == Decimal("55000000")


def test_save_load_position_auto_no_exit_orders(repo: PortfolioRepository) -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("9000000"),
        positions={
            "KRW-ETH": Position(
                market="KRW-ETH",
                side=OrderSide.BUY,
                entry_price=Decimal("3000000"),
                quantity=Decimal("0.1"),
                entry_time=1000,
                unrealized_pnl=Decimal("0"),
                highest_price=Decimal("3000000"),
            ),
        },
    )
    asyncio.get_event_loop().run_until_complete(repo.save_account(account))
    loaded = asyncio.get_event_loop().run_until_complete(
        repo.load_account(Decimal("10000000"))
    )
    assert loaded is not None
    pos = loaded.positions["KRW-ETH"]
    assert pos.trade_mode == "AUTO"
    assert pos.stop_loss_price is None
    assert pos.take_profit_price is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_portfolio_repo_mode.py -v`
Expected: FAIL (column count mismatch in INSERT/SELECT)

- [ ] **Step 3: Update positions table schema**

In `src/repository/database.py`, replace the positions table (lines 60-71):

```sql
CREATE TABLE IF NOT EXISTS positions (
    market           TEXT PRIMARY KEY,
    side             TEXT NOT NULL,
    entry_price      TEXT NOT NULL,
    quantity         TEXT NOT NULL,
    entry_time       INTEGER NOT NULL,
    unrealized_pnl   TEXT NOT NULL,
    highest_price    TEXT NOT NULL,
    add_count        INTEGER NOT NULL DEFAULT 0,
    total_invested   TEXT NOT NULL DEFAULT '0',
    partial_sold     INTEGER NOT NULL DEFAULT 0,
    trade_mode       TEXT NOT NULL DEFAULT 'AUTO',
    stop_loss_price  TEXT,
    take_profit_price TEXT
);
```

- [ ] **Step 4: Update save_account in PortfolioRepository**

In `src/repository/portfolio_repo.py`, replace the positions INSERT in `save_account` (lines 74-85):

```python
            await self._db.conn.executemany(
                """INSERT INTO positions
                   (market, side, entry_price, quantity, entry_time, unrealized_pnl,
                    highest_price, add_count, total_invested, partial_sold,
                    trade_mode, stop_loss_price, take_profit_price)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (market, p.side.value, str(p.entry_price), str(p.quantity),
                     p.entry_time, str(p.unrealized_pnl), str(p.highest_price),
                     p.add_count, str(p.total_invested), int(p.partial_sold),
                     p.trade_mode,
                     str(p.stop_loss_price) if p.stop_loss_price is not None else None,
                     str(p.take_profit_price) if p.take_profit_price is not None else None)
                    for market, p in account.positions.items()
                ],
            )
```

- [ ] **Step 5: Update load_account in PortfolioRepository**

In `src/repository/portfolio_repo.py`, replace the SELECT and Position construction in `load_account` (lines 98-117):

```python
        cursor = await self._db.conn.execute(
            "SELECT market, side, entry_price, quantity, entry_time, unrealized_pnl,"
            " highest_price, add_count, total_invested, partial_sold,"
            " trade_mode, stop_loss_price, take_profit_price FROM positions"
        )
        pos_rows = await cursor.fetchall()
        positions = {
            r[0]: Position(
                market=r[0],
                side=OrderSide(r[1]),
                entry_price=Decimal(r[2]),
                quantity=Decimal(r[3]),
                entry_time=int(r[4]),
                unrealized_pnl=Decimal(r[5]),
                highest_price=Decimal(r[6]),
                add_count=int(r[7]),
                total_invested=Decimal(r[8]),
                partial_sold=bool(r[9]),
                trade_mode=str(r[10]),
                stop_loss_price=Decimal(r[11]) if r[11] is not None else None,
                take_profit_price=Decimal(r[12]) if r[12] is not None else None,
            )
            for r in pos_rows
        }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_portfolio_repo_mode.py -v`
Expected: PASS

- [ ] **Step 7: Run all existing tests to verify no regressions**

Run: `uv run pytest tests/ -v`
Expected: All existing tests PASS

- [ ] **Step 8: Commit**

```bash
git add src/repository/database.py src/repository/portfolio_repo.py tests/unit/test_portfolio_repo_mode.py
git commit -m "feat: extend positions schema with trade_mode and exit orders"
```

---

### Task 3: Extend PaperEngine for Manual Orders

**Files:**
- Modify: `src/service/paper_engine.py:46-106,108-162`
- Test: `tests/unit/test_manual_orders.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_manual_orders.py
from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.service.paper_engine import PaperEngine
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def _make_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"),
        max_position_pct=Decimal("0.1"),
        max_open_positions=5,
        fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.001"),
        min_order_krw=Decimal("5000"),
        max_additional_buys=3,
        additional_buy_drop_pct=Decimal("0.03"),
        additional_buy_ratio=Decimal("0.5"),
    )


def test_manual_buy_new_position_sets_manual_mode() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    order = engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.0, reason="MANUAL",
    )
    assert order.reason == "MANUAL"
    pos = account.positions["KRW-BTC"]
    assert pos.trade_mode == "MANUAL"


def test_manual_buy_existing_auto_position_switches_to_manual() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    # First buy by ML (auto)
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    assert account.positions["KRW-BTC"].trade_mode == "AUTO"

    # Second buy manually
    engine.execute_buy(
        account, "KRW-BTC", Decimal("51000000"),
        Decimal("100000"), 0.0, reason="MANUAL",
    )
    assert account.positions["KRW-BTC"].trade_mode == "MANUAL"


def test_manual_sell_sets_reason() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "MANUAL")
    assert order.reason == "MANUAL"


def test_manual_partial_sell_sets_reason() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    order = engine.execute_partial_sell(
        account, "KRW-BTC", Decimal("51000000"),
        Decimal("0.5"), reason="MANUAL",
    )
    assert order.reason == "MANUAL"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_manual_orders.py -v`
Expected: FAIL with `TypeError: execute_buy() got an unexpected keyword argument 'reason'`

- [ ] **Step 3: Update execute_buy to accept optional reason parameter**

In `src/service/paper_engine.py`, update `execute_buy` signature and logic (lines 46-106):

```python
    def execute_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        invest_amount: Decimal,
        confidence: float,
        reason: str | None = None,
    ) -> Order:
        fill_price = current_price * (_ONE + self._config.slippage_rate)
        quantity = _quantize_quantity(invest_amount, fill_price)
        actual_spend = _truncate_krw(quantity * fill_price)
        fee = _truncate_krw(actual_spend * self._config.fee_rate)
        total_cost = actual_spend + fee
        now = int(time.time())

        account.cash_balance -= total_cost

        is_manual = reason == "MANUAL"
        existing = account.positions.get(market)
        if existing is not None:
            # 추가매수: 가중평균 entry_price 계산
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
            if is_manual:
                existing.trade_mode = "MANUAL"
            order_reason = reason if reason else "ADDITIONAL_BUY"
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
                trade_mode="MANUAL" if is_manual else "AUTO",
            )
            order_reason = reason if reason else "ML_SIGNAL"

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=quantity,
            status=OrderStatus.FILLED,
            signal_confidence=confidence,
            reason=order_reason,
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )
```

- [ ] **Step 4: Update execute_partial_sell to accept optional reason parameter**

In `src/service/paper_engine.py`, update `execute_partial_sell` signature (lines 108-162):

```python
    def execute_partial_sell(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        fraction: Decimal,
        reason: str | None = None,
    ) -> Order:
```

And change the hardcoded reason in the Order return (line 157):

```python
            reason=reason if reason else "PARTIAL_TAKE_PROFIT",
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_manual_orders.py -v`
Expected: PASS

- [ ] **Step 6: Run all existing tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS (existing callers don't pass `reason`, so default None preserves behavior)

- [ ] **Step 7: Commit**

```bash
git add src/service/paper_engine.py tests/unit/test_manual_orders.py
git commit -m "feat: extend PaperEngine with manual order reason and trade_mode"
```

---

### Task 4: MANUAL Position Exit-Order Checking in Portfolio

**Files:**
- Modify: `src/service/portfolio.py:29-46`
- Test: `tests/unit/test_manual_exit_orders.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_manual_exit_orders.py
from decimal import Decimal

from src.config.settings import RiskConfig
from src.service.portfolio import PortfolioManager
from src.types.enums import OrderSide
from src.types.models import Position


def _make_risk() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.03"),
        take_profit_pct=Decimal("0.10"),
        trailing_stop_pct=Decimal("0.02"),
        max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=20,
        consecutive_loss_limit=3,
        cooldown_minutes=60,
        partial_take_profit_pct=Decimal("0.04"),
        partial_sell_fraction=Decimal("0.5"),
    )


def _make_manual_position(
    stop_loss_price: Decimal | None = None,
    take_profit_price: Decimal | None = None,
) -> Position:
    return Position(
        market="KRW-BTC",
        side=OrderSide.BUY,
        entry_price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        entry_time=1000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
        trade_mode="MANUAL",
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
    )


def test_manual_stop_loss_triggered() -> None:
    pm = PortfolioManager(_make_risk())
    pos = _make_manual_position(stop_loss_price=Decimal("48000000"))
    result = pm.check_manual_exit(pos, Decimal("47000000"))
    assert result == "MANUAL_STOP_LOSS"


def test_manual_take_profit_triggered() -> None:
    pm = PortfolioManager(_make_risk())
    pos = _make_manual_position(take_profit_price=Decimal("55000000"))
    result = pm.check_manual_exit(pos, Decimal("56000000"))
    assert result == "MANUAL_TAKE_PROFIT"


def test_manual_no_exit_when_not_triggered() -> None:
    pm = PortfolioManager(_make_risk())
    pos = _make_manual_position(
        stop_loss_price=Decimal("48000000"),
        take_profit_price=Decimal("55000000"),
    )
    result = pm.check_manual_exit(pos, Decimal("50000000"))
    assert result is None


def test_manual_no_exit_when_no_orders_set() -> None:
    pm = PortfolioManager(_make_risk())
    pos = _make_manual_position()
    result = pm.check_manual_exit(pos, Decimal("40000000"))
    assert result is None


def test_auto_position_not_checked_by_manual_exit() -> None:
    pm = PortfolioManager(_make_risk())
    pos = Position(
        market="KRW-BTC",
        side=OrderSide.BUY,
        entry_price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        entry_time=1000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
        trade_mode="AUTO",
    )
    # AUTO position should return None from check_manual_exit
    result = pm.check_manual_exit(pos, Decimal("40000000"))
    assert result is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_manual_exit_orders.py -v`
Expected: FAIL with `AttributeError: 'PortfolioManager' object has no attribute 'check_manual_exit'`

- [ ] **Step 3: Add check_manual_exit method**

In `src/service/portfolio.py`, add the following method after `check_exit_conditions` (after line 46):

```python
    def check_manual_exit(self, position: Position, current_price: Decimal) -> str | None:
        """Check MANUAL position exit orders. Returns reason or None."""
        if position.trade_mode != "MANUAL":
            return None
        if position.stop_loss_price is not None and current_price <= position.stop_loss_price:
            return "MANUAL_STOP_LOSS"
        if position.take_profit_price is not None and current_price >= position.take_profit_price:
            return "MANUAL_TAKE_PROFIT"
        return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_manual_exit_orders.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/portfolio.py tests/unit/test_manual_exit_orders.py
git commit -m "feat: add check_manual_exit for MANUAL position exit orders"
```

---

### Task 5: Integrate Mode-Aware Position Monitoring in App

**Files:**
- Modify: `src/runtime/app.py:372-433`

- [ ] **Step 1: Update _monitor_positions to respect trade_mode**

In `src/runtime/app.py`, replace the trading_enabled block inside `_monitor_positions` (lines 389-403):

```python
            if self.trading_enabled:
                # MANUAL 포지션: 예약 손절/익절만 체크
                if position.trade_mode == "MANUAL":
                    manual_reason = self.portfolio_manager.check_manual_exit(position, price)
                    if manual_reason is not None:
                        exits.append((market, price, manual_reason))
                    continue

                # AUTO 포지션: 기존 로직
                # 1. 손절 체크 (최우선)
                pnl_pct = (price - position.entry_price) / position.entry_price
                if pnl_pct <= -self.settings.risk.stop_loss_pct:
                    exits.append((market, price, "STOP_LOSS"))
                    continue
                # 2. 부분 익절 체크
                fraction = self.portfolio_manager.check_partial_exit(position, price)
                if fraction is not None:
                    partial_exits.append((market, price, fraction))
                    continue
                # 3. 전체 매도 조건 (트레일링, 전체 익절)
                reason = self.portfolio_manager.check_exit_conditions(position, price)
                if reason is not None:
                    exits.append((market, price, reason))
```

- [ ] **Step 2: Update _on_signal to skip MANUAL positions for SELL signals**

In `src/runtime/app.py`, add a guard at the top of the SELL branch (around line 548):

```python
        elif event.signal_type == SignalType.SELL:
            position = self.account.positions.get(event.market)
            if position is None:
                return
            if position.trade_mode == "MANUAL":
                logger.info("Skipping ML SELL for MANUAL position %s", event.market)
                return
            tickers = await self.upbit.fetch_tickers([event.market])
            if not tickers:
                return
            price = tickers[0]["price"]
            entry_price = position.entry_price
            quantity = position.quantity
            order = self.paper_engine.execute_sell(
                self.account, event.market, price, "ML_SIGNAL",
            )
```

- [ ] **Step 3: Run all existing tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: mode-aware position monitoring (skip ML exits for MANUAL)"
```

---

### Task 6: Upbit WebSocket Service

**Files:**
- Create: `src/service/upbit_ws.py`
- Test: `tests/unit/test_upbit_ws.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_upbit_ws.py
import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.upbit_ws import UpbitWebSocketService


def test_parse_ticker_message() -> None:
    """Test that raw Upbit WS ticker messages are correctly parsed."""
    service = UpbitWebSocketService()
    raw = {
        "type": "ticker",
        "code": "KRW-BTC",
        "trade_price": 50000000,
        "change": "RISE",
        "signed_change_rate": 0.025,
        "signed_change_price": 1200000,
        "acc_trade_volume_24h": 1234.5,
        "acc_trade_price_24h": 61725000000000,
        "timestamp": 1712500000000,
    }
    ticker = service._parse_ws_ticker(raw)
    assert ticker["market"] == "KRW-BTC"
    assert ticker["price"] == Decimal("50000000")
    assert ticker["change"] == "RISE"
    assert ticker["change_rate"] == Decimal("0.025")
    assert ticker["change_price"] == Decimal("1200000")
    assert ticker["volume_24h"] == Decimal("1234.5")
    assert ticker["acc_trade_price_24h"] == Decimal("61725000000000")
    assert ticker["timestamp"] == 1712500000


def test_get_snapshot_returns_cached_data() -> None:
    service = UpbitWebSocketService()
    service._cache["KRW-BTC"] = {
        "market": "KRW-BTC",
        "price": Decimal("50000000"),
        "change": "RISE",
        "change_rate": Decimal("0.025"),
        "change_price": Decimal("1200000"),
        "volume_24h": Decimal("1234.5"),
        "acc_trade_price_24h": Decimal("61725000000000"),
        "timestamp": 1712500000,
    }
    snapshot = service.get_snapshot()
    assert "KRW-BTC" in snapshot
    assert snapshot["KRW-BTC"]["price"] == Decimal("50000000")


def test_get_price_returns_none_for_unknown_market() -> None:
    service = UpbitWebSocketService()
    assert service.get_price("KRW-UNKNOWN") is None


def test_get_price_returns_cached_price() -> None:
    service = UpbitWebSocketService()
    service._cache["KRW-BTC"] = {
        "market": "KRW-BTC",
        "price": Decimal("50000000"),
        "change": "RISE",
        "change_rate": Decimal("0.025"),
        "change_price": Decimal("1200000"),
        "volume_24h": Decimal("1234.5"),
        "acc_trade_price_24h": Decimal("61725000000000"),
        "timestamp": 1712500000,
    }
    assert service.get_price("KRW-BTC") == Decimal("50000000")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_upbit_ws.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'src.service.upbit_ws'`

- [ ] **Step 3: Implement UpbitWebSocketService**

Create `src/service/upbit_ws.py`:

```python
# src/service/upbit_ws.py
from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from src.service.upbit_client import UpbitClient

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
logger = logging.getLogger(__name__)


class UpbitWebSocketService:
    def __init__(self, upbit_client: UpbitClient | None = None) -> None:
        self._client = upbit_client
        self._cache: dict[str, dict[str, Any]] = {}
        self._ws: ClientConnection | None = None
        self._markets: list[str] = []
        self._running = False
        self._last_recv_time: float = 0
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._consecutive_failures: int = 0
        self._fallback_polling = False
        self._poll_task: asyncio.Task[None] | None = None
        self.status: str = "disconnected"  # "connected" | "polling" | "disconnected"

    def _parse_ws_ticker(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": str(raw["code"]),
            "price": Decimal(str(raw["trade_price"])),
            "change": str(raw["change"]),
            "change_rate": Decimal(str(raw["signed_change_rate"])),
            "change_price": Decimal(str(raw["signed_change_price"])),
            "volume_24h": Decimal(str(raw["acc_trade_volume_24h"])),
            "acc_trade_price_24h": Decimal(str(raw["acc_trade_price_24h"])),
            "timestamp": int(raw["timestamp"]) // 1000,
        }

    def get_snapshot(self) -> dict[str, dict[str, Any]]:
        return dict(self._cache)

    def get_price(self, market: str) -> Decimal | None:
        ticker = self._cache.get(market)
        return ticker["price"] if ticker else None

    async def start(self, markets: list[str]) -> None:
        self._markets = markets
        self._running = True
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        self.status = "disconnected"

    def update_markets(self, markets: list[str]) -> None:
        self._markets = markets

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._connect_and_recv()
            except Exception as e:
                logger.warning("Upbit WS error: %s", e)
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3 and not self._fallback_polling:
                    logger.info("Switching to REST polling fallback")
                    self._fallback_polling = True
                    self.status = "polling"
                    self._poll_task = asyncio.create_task(self._poll_loop())
                    return
                delay = min(
                    self._reconnect_delay * (2 ** (self._consecutive_failures - 1)),
                    self._max_reconnect_delay,
                )
                logger.info("Reconnecting in %.1fs...", delay)
                self.status = "disconnected"
                await asyncio.sleep(delay)

    async def _connect_and_recv(self) -> None:
        async with websockets.connect(UPBIT_WS_URL) as ws:
            self._ws = ws
            self._consecutive_failures = 0
            self._reconnect_delay = 1.0
            self.status = "connected"

            # If we were in fallback mode, cancel polling
            if self._fallback_polling:
                self._fallback_polling = False
                if self._poll_task and not self._poll_task.done():
                    self._poll_task.cancel()

            # Subscribe
            subscribe_msg = self._build_subscribe(self._markets)
            await ws.send(subscribe_msg)
            logger.info("Upbit WS connected, subscribed to %d markets", len(self._markets))

            self._last_recv_time = time.time()

            # Start health check
            health_task = asyncio.create_task(self._health_check())

            try:
                async for message in ws:
                    self._last_recv_time = time.time()
                    if isinstance(message, bytes):
                        data = json.loads(message.decode("utf-8"))
                    else:
                        data = json.loads(message)

                    if data.get("type") == "ticker":
                        ticker = self._parse_ws_ticker(data)
                        self._cache[ticker["market"]] = ticker
            finally:
                health_task.cancel()

    async def _health_check(self) -> None:
        while self._running:
            await asyncio.sleep(10)
            if time.time() - self._last_recv_time > 30:
                logger.warning("No WS data for 30s, forcing reconnect")
                if self._ws:
                    await self._ws.close()
                return

    async def _poll_loop(self) -> None:
        """REST polling fallback when WebSocket fails."""
        while self._running and self._fallback_polling and self._client:
            try:
                if self._markets:
                    # Batch into chunks of 100 (Upbit limit)
                    for i in range(0, len(self._markets), 100):
                        chunk = self._markets[i:i + 100]
                        tickers = await self._client.fetch_tickers(chunk)
                        for t in tickers:
                            market = t["market"]
                            self._cache[market] = {
                                "market": market,
                                "price": t["price"],
                                "change": "EVEN",
                                "change_rate": t["change_rate"],
                                "change_price": Decimal("0"),
                                "volume_24h": Decimal("0"),
                                "acc_trade_price_24h": t["volume_24h"],
                                "timestamp": t["timestamp"],
                            }
            except Exception as e:
                logger.warning("REST polling error: %s", e)
            await asyncio.sleep(10)

            # Periodically try to reconnect WebSocket
            try:
                async with websockets.connect(UPBIT_WS_URL) as ws:
                    logger.info("WS reconnected from polling fallback")
                    self._fallback_polling = False
                    self.status = "connected"
                    await ws.close()
                    asyncio.create_task(self._run_loop())
                    return
            except Exception:
                pass

    @staticmethod
    def _build_subscribe(markets: list[str]) -> str:
        payload = [
            {"ticket": "crypto-paper-trader-live"},
            {"type": "ticker", "codes": markets, "isOnlyRealtime": True},
            {"format": "DEFAULT"},
        ]
        return json.dumps(payload)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_upbit_ws.py -v`
Expected: PASS

- [ ] **Step 5: Ensure websockets is installed**

Run: `uv add websockets`

- [ ] **Step 6: Commit**

```bash
git add src/service/upbit_ws.py tests/unit/test_upbit_ws.py
git commit -m "feat: add UpbitWebSocketService with reconnection and REST fallback"
```

---

### Task 7: Wire UpbitWebSocketService into App and WebSocket Relay

**Files:**
- Modify: `src/runtime/app.py:54-100,111-168`
- Modify: `src/ui/api/server.py:9,22-26,32-43`

- [ ] **Step 1: Add UpbitWebSocketService to App.__init__**

In `src/runtime/app.py`, add import at the top (after line 32):

```python
from src.service.upbit_ws import UpbitWebSocketService
```

In `App.__init__` (after `self.upbit = UpbitClient()` around line 70):

```python
        self.upbit_ws = UpbitWebSocketService(self.upbit)
```

- [ ] **Step 2: Start/stop WebSocket service in App lifecycle**

In `src/runtime/app.py`, add to the end of `start()` method (before the final log line, around line 167):

```python
        # Start Upbit WebSocket for live ticker data
        all_markets = self.collector.markets
        if all_markets:
            await self.upbit_ws.start(all_markets)
            logger.info("Upbit WebSocket started for %d markets", len(all_markets))
```

In `stop()` method (before `await self.upbit.close()`, around line 249):

```python
        await self.upbit_ws.stop()
```

- [ ] **Step 3: Update WebSocket relay in server.py to broadcast tickers**

In `src/ui/api/server.py`, replace the `websocket_live` endpoint (lines 32-43):

```python
    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket) -> None:
        await ws.accept()
        try:
            prev_snapshot: dict[str, dict] = {}
            while True:
                messages: list[dict] = [{"type": "heartbeat", "data": {}}]

                # Relay ticker deltas from Upbit WS
                app_instance = getattr(app.state, "app", None)
                if app_instance and hasattr(app_instance, "upbit_ws"):
                    snapshot = app_instance.upbit_ws.get_snapshot()
                    for market, ticker in snapshot.items():
                        prev = prev_snapshot.get(market)
                        if prev is None or prev.get("price") != ticker.get("price"):
                            messages.append({
                                "type": "ticker",
                                "data": {
                                    "market": ticker["market"],
                                    "price": str(ticker["price"]),
                                    "change": ticker["change"],
                                    "change_rate": str(ticker["change_rate"]),
                                    "change_price": str(ticker["change_price"]),
                                    "volume_24h": str(ticker.get("volume_24h", "0")),
                                    "acc_trade_price_24h": str(ticker.get("acc_trade_price_24h", "0")),
                                    "timestamp": ticker["timestamp"],
                                },
                            })
                    prev_snapshot = dict(snapshot)

                    # Relay WS connection status
                    messages.append({
                        "type": "ws_status",
                        "data": {"upbit": app_instance.upbit_ws.status},
                    })

                for msg in messages:
                    await ws.send_text(json.dumps(msg))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass
```

- [ ] **Step 4: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/app.py src/ui/api/server.py
git commit -m "feat: wire UpbitWebSocketService into app and relay tickers to frontend"
```

---

### Task 8: Exchange API Routes

**Files:**
- Create: `src/ui/api/routes/exchange.py`
- Modify: `src/ui/api/server.py:9,22-26`

- [ ] **Step 1: Create exchange routes**

Create `src/ui/api/routes/exchange.py`:

```python
# src/ui/api/routes/exchange.py
from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class BuyRequest(BaseModel):
    market: str
    amount_krw: str


class SellRequest(BaseModel):
    market: str
    fraction: str


class ModeRequest(BaseModel):
    trade_mode: str


class ExitOrdersRequest(BaseModel):
    stop_loss_price: str | None = None
    take_profit_price: str | None = None


@router.get("/markets")
async def get_exchange_markets(request: Request) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    names = app.collector.korean_names
    screened = set(app.screened_markets)
    snapshot = app.upbit_ws.get_snapshot()

    result = []
    for market in app.collector.markets:
        ticker = snapshot.get(market, {})
        result.append({
            "market": market,
            "korean_name": names.get(market, market.replace("KRW-", "")),
            "price": str(ticker.get("price", "0")),
            "change": ticker.get("change", "EVEN"),
            "change_rate": str(ticker.get("change_rate", "0")),
            "acc_trade_price_24h": str(ticker.get("acc_trade_price_24h", "0")),
            "is_screened": market in screened,
        })

    # Sort: screened first, then by trade price descending
    result.sort(key=lambda x: (not x["is_screened"], -float(x["acc_trade_price_24h"] or "0")))
    return result


@router.post("/buy")
async def manual_buy(request: Request, body: BuyRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    amount = Decimal(body.amount_krw)

    # Check risk limits (reuse logic without Signal object)
    if amount < app.settings.paper_trading.min_order_krw:
        return {"success": False, "error": f"최소 주문 금액({app.settings.paper_trading.min_order_krw}원) 미달"}

    existing = app.account.positions.get(body.market)
    if existing is None and len(app.account.positions) >= app.settings.paper_trading.max_open_positions:
        return {"success": False, "error": "포지션 한도 도달"}

    if amount > app.account.cash_balance:
        return {"success": False, "error": "잔고 부족"}

    # Get current price
    price = app.upbit_ws.get_price(body.market)
    if price is None:
        tickers = await app.upbit.fetch_tickers([body.market])
        if not tickers:
            return {"success": False, "error": "가격 조회 실패"}
        price = tickers[0]["price"]

    order = app.paper_engine.execute_buy(
        app.account, body.market, price, amount, 0.0, reason="MANUAL",
    )
    await app.order_repo.save(order)
    app.risk_manager.record_trade()
    await app._save_state()

    pos = app.account.positions.get(body.market)
    return {
        "success": True,
        "order": {
            "id": order.id,
            "market": order.market,
            "side": order.side.value,
            "price": str(order.fill_price),
            "quantity": str(order.quantity),
            "fee": str(order.fee),
            "reason": order.reason,
        },
        "position": _serialize_position(pos) if pos else None,
    }


@router.post("/sell")
async def manual_sell(request: Request, body: SellRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if body.market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = app.account.positions[body.market]
    entry_price = position.entry_price
    quantity = position.quantity
    fraction = Decimal(body.fraction)

    price = app.upbit_ws.get_price(body.market)
    if price is None:
        tickers = await app.upbit.fetch_tickers([body.market])
        if not tickers:
            return {"success": False, "error": "가격 조회 실패"}
        price = tickers[0]["price"]

    if fraction >= Decimal("1"):
        order = app.paper_engine.execute_sell(app.account, body.market, price, "MANUAL")
    else:
        order = app.paper_engine.execute_partial_sell(
            app.account, body.market, price, fraction, reason="MANUAL",
        )

    await app.order_repo.save(order)
    app.risk_manager.record_trade()
    assert order.fill_price is not None
    app._record_trade_result(entry_price, order.fill_price, quantity if fraction >= Decimal("1") else order.quantity)
    await app._save_state()

    pos = app.account.positions.get(body.market)
    return {
        "success": True,
        "order": {
            "id": order.id,
            "market": order.market,
            "side": order.side.value,
            "price": str(order.fill_price),
            "quantity": str(order.quantity),
            "fee": str(order.fee),
            "reason": order.reason,
        },
        "position": _serialize_position(pos) if pos else None,
    }


@router.patch("/position/{market}/mode")
async def update_position_mode(request: Request, market: str, body: ModeRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    if body.trade_mode not in ("AUTO", "MANUAL"):
        return {"success": False, "error": "유효하지 않은 모드"}

    position = app.account.positions[market]
    position.trade_mode = body.trade_mode

    # Switching to AUTO clears manual exit orders
    if body.trade_mode == "AUTO":
        position.stop_loss_price = None
        position.take_profit_price = None

    await app._save_state()
    return {"success": True, "position": _serialize_position(position)}


@router.patch("/position/{market}/exit-orders")
async def update_exit_orders(request: Request, market: str, body: ExitOrdersRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = app.account.positions[market]
    position.stop_loss_price = Decimal(body.stop_loss_price) if body.stop_loss_price else None
    position.take_profit_price = Decimal(body.take_profit_price) if body.take_profit_price else None
    await app._save_state()
    return {"success": True, "position": _serialize_position(position)}


def _serialize_position(pos) -> dict:  # type: ignore[type-arg]
    return {
        "market": pos.market,
        "entry_price": str(pos.entry_price),
        "quantity": str(pos.quantity),
        "unrealized_pnl": str(pos.unrealized_pnl),
        "add_count": pos.add_count,
        "total_invested": str(pos.total_invested),
        "partial_sold": pos.partial_sold,
        "trade_mode": pos.trade_mode,
        "stop_loss_price": str(pos.stop_loss_price) if pos.stop_loss_price else None,
        "take_profit_price": str(pos.take_profit_price) if pos.take_profit_price else None,
    }
```

- [ ] **Step 2: Register exchange router in server.py**

In `src/ui/api/server.py`, add to imports (line 9):

```python
from src.ui.api.routes import control, dashboard, exchange, portfolio, risk, strategy
```

Add router registration (after the control router, around line 26):

```python
    app.include_router(exchange.router, prefix="/api/exchange", tags=["exchange"])
```

- [ ] **Step 3: Run lint check**

Run: `uv run ruff check src/ui/api/routes/exchange.py`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add src/ui/api/routes/exchange.py src/ui/api/server.py
git commit -m "feat: add exchange API routes for manual trading and position mode"
```

---

### Task 9: Extend Candles Endpoint with Timeframe Parameter

**Files:**
- Modify: `src/ui/api/routes/dashboard.py:20-39`

- [ ] **Step 1: Update candles endpoint to accept timeframe**

In `src/ui/api/routes/dashboard.py`, replace the candles endpoint (lines 20-39):

```python
@router.get("/candles")
async def get_candles(
    request: Request, market: str, limit: int = 200, timeframe: str | None = None,
) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    # For timeframes we don't cache, fetch directly from Upbit
    if timeframe == "1D":
        # Daily candles use a different Upbit endpoint
        candles = await app.upbit.fetch_daily_candles(market, count=limit)
    elif timeframe is not None and int(timeframe) != app.settings.collector.candle_timeframe:
        candles = await app.upbit.fetch_candles(market, timeframe=int(timeframe), count=limit)
    else:
        tf_str = f"{app.settings.collector.candle_timeframe}m"
        candles = await app.candle_repo.get_latest(market, tf_str, limit=limit)

    return [
        {
            "timestamp": c.timestamp,
            "open": str(c.open),
            "high": str(c.high),
            "low": str(c.low),
            "close": str(c.close),
            "volume": str(c.volume),
        }
        for c in reversed(candles)
    ]
```

- [ ] **Step 2: Add fetch_daily_candles to UpbitClient**

In `src/service/upbit_client.py`, add after `fetch_candles` (after line 58):

```python
    async def fetch_daily_candles(
        self, market: str, count: int = 200
    ) -> list[Candle]:
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get(
                "/candles/days",
                params={"market": market, "count": count},
            )
            resp.raise_for_status()
        return [self.parse_candle(raw, "1D") for raw in resp.json()]
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/ui/api/routes/dashboard.py src/service/upbit_client.py
git commit -m "feat: add timeframe parameter to candles endpoint with daily candle support"
```

---

### Task 10: Exchange Page — Market List (Left Panel)

**Files:**
- Create: `src/ui/frontend/src/pages/Exchange.tsx`
- Modify: `src/ui/frontend/src/App.tsx`
- Modify: `src/ui/frontend/src/index.css`

- [ ] **Step 1: Add Exchange route and nav item to App.tsx**

In `src/ui/frontend/src/App.tsx`, add import:

```tsx
import Exchange from "./pages/Exchange";
```

Add nav item in the sidebar nav list (after Dashboard, before Strategy):

```tsx
<li>
  <NavLink to="/exchange" className={({ isActive }) => (isActive ? "active" : "")}>
    <span className="nav-icon">◇</span> 거래소
  </NavLink>
</li>
```

Add route:

```tsx
<Route path="/exchange" element={<Exchange />} />
```

- [ ] **Step 2: Create Exchange.tsx with market list**

Create `src/ui/frontend/src/pages/Exchange.tsx`:

```tsx
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";

/* ── Types ── */

interface MarketItem {
  market: string;
  korean_name: string;
  price: string;
  change: string;
  change_rate: string;
  acc_trade_price_24h: string;
  is_screened: boolean;
}

interface TickerWS {
  market: string;
  price: string;
  change: string;
  change_rate: string;
  change_price: string;
  volume_24h: string;
  acc_trade_price_24h: string;
  timestamp: number;
}

/* ── Helpers ── */

function formatKRW(val: string | number): string {
  const n = typeof val === "string" ? Number(val) : val;
  if (n === 0) return "₩0";
  if (n >= 1_000_000_000_000) return `₩${(n / 1_000_000_000_000).toFixed(1)}조`;
  if (n >= 100_000_000) return `₩${(n / 100_000_000).toFixed(0)}억`;
  if (n >= 10_000) return `₩${(n / 10_000).toFixed(0)}만`;
  return `₩${n.toLocaleString("ko-KR")}`;
}

function formatPrice(val: string): string {
  const n = Number(val);
  if (n >= 1000) return n.toLocaleString("ko-KR");
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(4);
}

function formatPct(val: string): string {
  const n = Number(val) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

/* ── Component ── */

export default function Exchange() {
  const { get } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");

  const [markets, setMarkets] = useState<MarketItem[]>([]);
  const [search, setSearch] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);

  // Track price flashes: market -> "up" | "down" | null
  const [flashes, setFlashes] = useState<Record<string, string>>({});
  const flashTimers = useRef<Record<string, ReturnType<typeof setTimeout>>>({});

  // Fetch market list
  const fetchMarkets = useCallback(() => {
    get<MarketItem[]>("/api/exchange/markets").then(setMarkets);
  }, [get]);

  useEffect(() => {
    fetchMarkets();
    const interval = setInterval(fetchMarkets, 30000);
    return () => clearInterval(interval);
  }, [fetchMarkets]);

  // Handle WebSocket ticker updates
  useEffect(() => {
    if (lastMessage?.type !== "ticker") return;
    const ticker = lastMessage.data as unknown as TickerWS;

    setMarkets((prev) =>
      prev.map((m) => {
        if (m.market !== ticker.market) return m;
        const oldPrice = Number(m.price);
        const newPrice = Number(ticker.price);
        if (oldPrice !== newPrice) {
          const dir = newPrice > oldPrice ? "up" : "down";
          setFlashes((f) => ({ ...f, [m.market]: dir }));
          if (flashTimers.current[m.market]) clearTimeout(flashTimers.current[m.market]);
          flashTimers.current[m.market] = setTimeout(() => {
            setFlashes((f) => ({ ...f, [m.market]: "" }));
          }, 500);
        }
        return {
          ...m,
          price: ticker.price,
          change: ticker.change,
          change_rate: ticker.change_rate,
          acc_trade_price_24h: ticker.acc_trade_price_24h,
        };
      }),
    );
  }, [lastMessage]);

  // Filter & group markets
  const { screened, others } = useMemo(() => {
    const q = search.toLowerCase();
    const filtered = markets.filter(
      (m) =>
        m.korean_name.toLowerCase().includes(q) ||
        m.market.toLowerCase().includes(q),
    );
    return {
      screened: filtered.filter((m) => m.is_screened),
      others: filtered.filter((m) => !m.is_screened),
    };
  }, [markets, search]);

  const selected = markets.find((m) => m.market === selectedMarket) ?? null;

  return (
    <div className="exchange-layout">
      {/* Left Panel — Market List */}
      <div className="exchange-left">
        <div className="panel">
          <div className="panel-header">
            <h2>KRW 마켓</h2>
          </div>
          <div className="panel-body" style={{ padding: 0 }}>
            <div className="exchange-search">
              <input
                type="text"
                placeholder="코인명/티커 검색..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>

            <div className="exchange-market-list">
              {screened.length > 0 && (
                <div className="exchange-section screened-section">
                  <div className="exchange-section-label">스크리닝 통과</div>
                  {screened.map((m) => (
                    <MarketRow
                      key={m.market}
                      item={m}
                      flash={flashes[m.market] || ""}
                      selected={m.market === selectedMarket}
                      onClick={() => setSelectedMarket(m.market)}
                    />
                  ))}
                </div>
              )}
              <div className="exchange-section">
                {screened.length > 0 && (
                  <div className="exchange-section-label">전체</div>
                )}
                {others.map((m) => (
                  <MarketRow
                    key={m.market}
                    item={m}
                    flash={flashes[m.market] || ""}
                    selected={m.market === selectedMarket}
                    onClick={() => setSelectedMarket(m.market)}
                  />
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel — Detail + Order */}
      <div className="exchange-right">
        {selected ? (
          <ExchangeDetail market={selected} />
        ) : (
          <div className="panel">
            <div className="panel-body">
              <div className="empty-state">
                <div className="empty-icon">◇</div>
                <div className="empty-text">코인을 선택해 주세요</div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Market Row ── */

function MarketRow({
  item,
  flash,
  selected,
  onClick,
}: {
  item: MarketItem;
  flash: string;
  selected: boolean;
  onClick: () => void;
}) {
  const changeNum = Number(item.change_rate);
  const changeClass = changeNum > 0 ? "positive" : changeNum < 0 ? "negative" : "";

  return (
    <div
      className={`exchange-market-row ${selected ? "selected" : ""} ${flash ? `flash-${flash}` : ""}`}
      onClick={onClick}
    >
      <div className="market-name">
        <span className="market-korean">{item.korean_name}</span>
        <span className="market-ticker">{item.market.replace("KRW-", "")}</span>
      </div>
      <div className="market-data">
        <span className={`market-price ${changeClass} ${flash ? "price-bump" : ""}`}>
          {formatPrice(item.price)}
        </span>
        <span className={`market-change ${changeClass}`}>
          {formatPct(item.change_rate)}
        </span>
        <span className="market-volume">{formatKRW(item.acc_trade_price_24h)}</span>
      </div>
    </div>
  );
}

/* ── Exchange Detail (placeholder — implemented in next tasks) ── */

function ExchangeDetail({ market }: { market: MarketItem }) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h2>
          {market.korean_name}{" "}
          <span style={{ color: "var(--text-dim)", fontSize: "0.85em" }}>
            {market.market}
          </span>
        </h2>
      </div>
      <div className="panel-body">
        <div className="exchange-detail-price">
          <span
            className={`detail-price ${Number(market.change_rate) >= 0 ? "positive" : "negative"}`}
          >
            {formatPrice(market.price)}
          </span>
          <span
            className={`detail-change ${Number(market.change_rate) >= 0 ? "positive" : "negative"}`}
          >
            {formatPct(market.change_rate)}
          </span>
        </div>
        <div className="empty-state" style={{ marginTop: 40 }}>
          <div className="empty-text">차트 & 주문 패널 준비 중...</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Add exchange styles to index.css**

Append to the end of `src/ui/frontend/src/index.css`:

```css
/* ── Exchange Page ── */
.exchange-layout {
  display: grid;
  grid-template-columns: 380px 1fr;
  gap: 16px;
  height: calc(100vh - 40px);
}

.exchange-left {
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.exchange-left .panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.exchange-left .panel-body {
  flex: 1;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.exchange-search {
  padding: 12px 16px;
  border-bottom: 1px solid var(--border);
}

.exchange-search input {
  width: 100%;
  padding: 8px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 0.82rem;
  outline: none;
  transition: border-color 0.2s var(--ease);
}

.exchange-search input:focus {
  border-color: var(--accent);
}

.exchange-market-list {
  flex: 1;
  overflow-y: auto;
}

.exchange-section-label {
  padding: 8px 16px 4px;
  font-size: 0.72rem;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.screened-section {
  background: var(--accent-glow);
  border-bottom: 1px solid var(--border);
}

.exchange-market-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 16px;
  cursor: pointer;
  transition: background 0.15s var(--ease);
  border-bottom: 1px solid rgba(30, 42, 58, 0.3);
}

.exchange-market-row:hover {
  background: var(--bg-card-hover);
}

.exchange-market-row.selected {
  background: var(--bg-card);
  border-left: 3px solid var(--accent);
}

.market-name {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.market-korean {
  font-size: 0.85rem;
  font-weight: 500;
  color: var(--text);
}

.market-ticker {
  font-size: 0.72rem;
  color: var(--text-muted);
  font-family: var(--font-mono);
}

.market-data {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 2px;
}

.market-price {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  font-weight: 600;
  transition: transform 0.3s var(--ease);
}

.market-price.price-bump {
  transform: scale(1.05);
}

.market-change {
  font-family: var(--font-mono);
  font-size: 0.75rem;
}

.market-volume {
  font-size: 0.7rem;
  color: var(--text-muted);
}

.market-price.positive,
.market-change.positive { color: var(--profit); }
.market-price.negative,
.market-change.negative { color: var(--loss); }

/* Flash animations */
.flash-up {
  animation: flash-green 0.5s ease-out;
}

.flash-down {
  animation: flash-red 0.5s ease-out;
}

@keyframes flash-green {
  0% { background: rgba(0, 224, 175, 0.25); }
  100% { background: transparent; }
}

@keyframes flash-red {
  0% { background: rgba(255, 68, 102, 0.25); }
  100% { background: transparent; }
}

/* Exchange Right Panel */
.exchange-right {
  overflow-y: auto;
}

.exchange-detail-price {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 20px;
}

.detail-price {
  font-family: var(--font-mono);
  font-size: 2rem;
  font-weight: 700;
}

.detail-change {
  font-family: var(--font-mono);
  font-size: 1.1rem;
  font-weight: 500;
}

.detail-price.positive,
.detail-change.positive { color: var(--profit); }
.detail-price.negative,
.detail-change.negative { color: var(--loss); }
```

- [ ] **Step 4: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx src/ui/frontend/src/App.tsx src/ui/frontend/src/index.css
git commit -m "feat: add Exchange page with real-time market list and price flash effects"
```

---

### Task 11: Exchange Detail — Candlestick Chart

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx`

- [ ] **Step 1: Replace ExchangeDetail placeholder with chart implementation**

In `src/ui/frontend/src/pages/Exchange.tsx`, replace the `ExchangeDetail` component with the full implementation including chart. Add the import at the top:

```tsx
import { createChart, CandlestickSeries, HistogramSeries, IChartApi, ISeriesApi } from "lightweight-charts";
import type { CandlestickData, HistogramData } from "lightweight-charts";
```

Replace the `ExchangeDetail` component:

```tsx
interface CandleRaw {
  timestamp: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

interface PositionInfo {
  market: string;
  entry_price: string;
  quantity: string;
  unrealized_pnl: string;
  add_count: number;
  total_invested: string;
  partial_sold: boolean;
  trade_mode: string;
  stop_loss_price: string | null;
  take_profit_price: string | null;
}

type Timeframe = 1 | 5 | 15 | 60 | 240;
type DailyTf = "1D";
const TIMEFRAMES: { label: string; value: Timeframe | DailyTf }[] = [
  { label: "1분", value: 1 },
  { label: "5분", value: 5 },
  { label: "15분", value: 15 },
  { label: "1시간", value: 60 },
  { label: "4시간", value: 240 },
  { label: "일봉", value: "1D" },
];

function ExchangeDetail({ market }: { market: MarketItem }) {
  const { get, postJson, patchJson } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");

  const [timeframe, setTimeframe] = useState<Timeframe | DailyTf>(5);
  const [position, setPosition] = useState<PositionInfo | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);

  // Fetch position for this market
  useEffect(() => {
    get<PositionInfo[]>("/api/portfolio/positions").then((positions) => {
      const pos = positions.find(
        (p: { market: string }) => p.market === market.market,
      );
      setPosition(pos && "trade_mode" in pos ? (pos as unknown as PositionInfo) : null);
    });
  }, [get, market.market]);

  // Candlestick chart
  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 360,
      layout: {
        background: { color: "#0b1018" },
        textColor: "#4a5a70",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1a2332" },
        horzLines: { color: "#1a2332" },
      },
      crosshair: {
        vertLine: { color: "#2a3a50", labelBackgroundColor: "#151d28" },
        horzLine: { color: "#2a3a50", labelBackgroundColor: "#151d28" },
      },
      timeScale: { borderColor: "#1a2332", timeVisible: true },
      rightPriceScale: { borderColor: "#1a2332" },
    });

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00e0af",
      downColor: "#ff4466",
      borderUpColor: "#00e0af",
      borderDownColor: "#ff4466",
      wickUpColor: "#00e0af",
      wickDownColor: "#ff4466",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;

    // Fetch candle data
    get<CandleRaw[]>(
      `/api/dashboard/candles?market=${market.market}&limit=200&timeframe=${timeframe}`,
    ).then((candles) => {
      const candleData: CandlestickData[] = candles.map((c) => ({
        time: (Number(c.timestamp) / 1000) as unknown as CandlestickData["time"],
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      }));
      const volumeData: HistogramData[] = candles.map((c) => ({
        time: (Number(c.timestamp) / 1000) as unknown as HistogramData["time"],
        value: Number(c.volume),
        color:
          Number(c.close) >= Number(c.open)
            ? "rgba(0, 224, 175, 0.3)"
            : "rgba(255, 68, 102, 0.3)",
      }));
      candleSeries.setData(candleData);
      volumeSeries.setData(volumeData);
      chart.timeScale().fitContent();

      // Position overlay lines
      if (position) {
        candleSeries.createPriceLine({
          price: Number(position.entry_price),
          color: "#00e0af",
          lineWidth: 1,
          lineStyle: 2, // dashed
          axisLabelVisible: true,
          title: "평균매입가",
        });
        if (position.stop_loss_price) {
          candleSeries.createPriceLine({
            price: Number(position.stop_loss_price),
            color: "#ff4466",
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: "손절가",
          });
        }
        if (position.take_profit_price) {
          candleSeries.createPriceLine({
            price: Number(position.take_profit_price),
            color: "#00e0af",
            lineWidth: 1,
            lineStyle: 0,
            axisLabelVisible: true,
            title: "익절가",
          });
        }
      }
    });

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
    };
  }, [market.market, timeframe, get, position]);

  // Real-time candle update from WebSocket ticker
  useEffect(() => {
    if (lastMessage?.type !== "ticker") return;
    const ticker = lastMessage.data as unknown as TickerWS;
    if (ticker.market !== market.market) return;
    if (!candleSeriesRef.current) return;

    const price = Number(ticker.price);
    const now = Math.floor(ticker.timestamp);
    candleSeriesRef.current.update({
      time: now as unknown as CandlestickData["time"],
      open: price,
      high: price,
      low: price,
      close: price,
    });
  }, [lastMessage, market.market]);

  return (
    <>
      {/* Header */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header">
          <h2>
            {market.korean_name}{" "}
            <span style={{ color: "var(--text-dim)", fontSize: "0.85em" }}>
              {market.market}
            </span>
          </h2>
        </div>
        <div className="panel-body">
          <div className="exchange-detail-price">
            <span
              className={`detail-price ${Number(market.change_rate) >= 0 ? "positive" : "negative"}`}
            >
              {formatPrice(market.price)}
            </span>
            <span
              className={`detail-change ${Number(market.change_rate) >= 0 ? "positive" : "negative"}`}
            >
              {formatPct(market.change_rate)}
            </span>
            <span className="market-volume" style={{ marginLeft: 12 }}>
              거래대금 {formatKRW(market.acc_trade_price_24h)}
            </span>
          </div>
        </div>
      </div>

      {/* Chart */}
      <div className="panel" style={{ marginBottom: 16 }}>
        <div className="panel-header">
          <h3>차트</h3>
          <div className="period-switch">
            {TIMEFRAMES.map((tf) => (
              <button
                key={tf.value}
                className={`period-btn ${timeframe === tf.value ? "active" : ""}`}
                onClick={() => setTimeframe(tf.value)}
              >
                {tf.label}
              </button>
            ))}
          </div>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          <div ref={chartContainerRef} style={{ width: "100%", height: 360 }} />
        </div>
      </div>

      {/* Order Panel — implemented in next task */}
      <OrderPanel market={market} position={position} onPositionChange={setPosition} />
    </>
  );
}
```

- [ ] **Step 2: Add OrderPanel placeholder**

Add at the bottom of Exchange.tsx (before the final closing):

```tsx
function OrderPanel({
  market,
  position,
  onPositionChange,
}: {
  market: MarketItem;
  position: PositionInfo | null;
  onPositionChange: (p: PositionInfo | null) => void;
}) {
  return (
    <div className="panel">
      <div className="panel-header">
        <h3>주문</h3>
      </div>
      <div className="panel-body">
        <div className="empty-state">
          <div className="empty-text">주문 패널 준비 중...</div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx
git commit -m "feat: add candlestick chart with timeframe switching and position overlay"
```

---

### Task 12: Exchange Detail — Order Panel

**Files:**
- Modify: `src/ui/frontend/src/pages/Exchange.tsx`

- [ ] **Step 1: Replace OrderPanel with full implementation**

Replace the `OrderPanel` component in Exchange.tsx:

```tsx
function OrderPanel({
  market,
  position,
  onPositionChange,
}: {
  market: MarketItem;
  position: PositionInfo | null;
  onPositionChange: (p: PositionInfo | null) => void;
}) {
  const { get, postJson, patchJson } = useApi();
  const [tab, setTab] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [cashBalance, setCashBalance] = useState("0");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  // Exit order inputs
  const [slPrice, setSlPrice] = useState("");
  const [tpPrice, setTpPrice] = useState("");

  // Fetch cash balance
  useEffect(() => {
    get<{ cash_balance: string }>("/api/dashboard/summary").then((s) =>
      setCashBalance(s.cash_balance),
    );
  }, [get]);

  // Sync exit order inputs from position
  useEffect(() => {
    if (position) {
      setSlPrice(position.stop_loss_price ?? "");
      setTpPrice(position.take_profit_price ?? "");
    }
  }, [position]);

  const handleBuy = async () => {
    if (!amount || Number(amount) <= 0) return;
    setLoading(true);
    setResult(null);
    const res = await postJson<{
      success: boolean;
      error?: string;
      position?: PositionInfo;
    }>("/api/exchange/buy", { market: market.market, amount_krw: amount });
    setLoading(false);
    if (res.success) {
      setResult({ ok: true, msg: "매수 완료" });
      setAmount("");
      if (res.position) onPositionChange(res.position);
      get<{ cash_balance: string }>("/api/dashboard/summary").then((s) =>
        setCashBalance(s.cash_balance),
      );
    } else {
      setResult({ ok: false, msg: res.error ?? "매수 실패" });
    }
  };

  const handleSell = async (fraction: string) => {
    setLoading(true);
    setResult(null);
    const res = await postJson<{
      success: boolean;
      error?: string;
      position?: PositionInfo | null;
    }>("/api/exchange/sell", { market: market.market, fraction });
    setLoading(false);
    if (res.success) {
      setResult({ ok: true, msg: "매도 완료" });
      onPositionChange(res.position ?? null);
      get<{ cash_balance: string }>("/api/dashboard/summary").then((s) =>
        setCashBalance(s.cash_balance),
      );
    } else {
      setResult({ ok: false, msg: res.error ?? "매도 실패" });
    }
  };

  const handleSetExitOrders = async () => {
    const res = await patchJson<{ success: boolean; position?: PositionInfo }>(
      `/api/exchange/position/${market.market}/exit-orders`,
      {
        stop_loss_price: slPrice || null,
        take_profit_price: tpPrice || null,
      },
    );
    if (res.success && res.position) {
      onPositionChange(res.position);
      setResult({ ok: true, msg: "예약 주문 설정 완료" });
    }
  };

  const cash = Number(cashBalance);

  return (
    <div className="panel">
      <div className="panel-header">
        <h3>주문</h3>
        <div className="period-switch">
          <button
            className={`period-btn ${tab === "buy" ? "active" : ""}`}
            onClick={() => setTab("buy")}
          >
            매수
          </button>
          <button
            className={`period-btn ${tab === "sell" ? "active" : ""}`}
            onClick={() => setTab("sell")}
          >
            매도
          </button>
        </div>
      </div>
      <div className="panel-body">
        {tab === "buy" ? (
          <div className="order-form">
            <div className="order-info-row">
              <span className="order-label">투자가능</span>
              <span className="order-value">{formatKRW(cash)}</span>
            </div>
            <input
              type="number"
              className="order-input"
              placeholder="투자 금액 (KRW)"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <div className="order-presets">
              {[0.25, 0.5, 0.75, 1].map((pct) => (
                <button
                  key={pct}
                  className="btn btn-ghost"
                  onClick={() =>
                    setAmount(String(Math.floor(cash * pct)))
                  }
                >
                  {pct * 100}%
                </button>
              ))}
            </div>
            {amount && Number(amount) > 0 && (
              <div className="order-info-row" style={{ marginTop: 8 }}>
                <span className="order-label">예상 수량</span>
                <span className="order-value">
                  ≈{" "}
                  {(Number(amount) / Number(market.price)).toFixed(8)}{" "}
                  {market.market.replace("KRW-", "")}
                </span>
              </div>
            )}
            <button
              className="btn btn-primary order-submit"
              disabled={loading || !amount || Number(amount) <= 0}
              onClick={handleBuy}
            >
              {loading ? "처리 중..." : "매수"}
            </button>
          </div>
        ) : (
          <div className="order-form">
            {position ? (
              <>
                <div className="order-info-row">
                  <span className="order-label">보유수량</span>
                  <span className="order-value">
                    {Number(position.quantity).toFixed(8)}
                  </span>
                </div>
                <div className="order-info-row">
                  <span className="order-label">평균매입가</span>
                  <span className="order-value">
                    {formatPrice(position.entry_price)}
                  </span>
                </div>
                <div className="order-info-row">
                  <span className="order-label">평가손익</span>
                  <span
                    className={`order-value ${Number(position.unrealized_pnl) >= 0 ? "positive" : "negative"}`}
                  >
                    {Number(position.unrealized_pnl) >= 0 ? "+" : ""}
                    {Number(position.unrealized_pnl).toFixed(2)}%
                  </span>
                </div>
                <div className="order-presets" style={{ marginTop: 12 }}>
                  {["0.25", "0.5", "0.75", "1"].map((f) => (
                    <button
                      key={f}
                      className={`btn ${f === "1" ? "btn-danger" : "btn-ghost"}`}
                      disabled={loading}
                      onClick={() => handleSell(f)}
                    >
                      {Number(f) * 100}%{f === "1" ? " 전량" : ""}
                    </button>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty-state">
                <div className="empty-text">보유하지 않은 코인입니다</div>
              </div>
            )}
          </div>
        )}

        {/* Exit orders (only when holding) */}
        {position && (
          <div className="exit-orders-section">
            <h4>예약 손절/익절</h4>
            <div className="order-info-row">
              <span className="order-label">손절가</span>
              <input
                type="number"
                className="order-input-sm"
                placeholder="미설정"
                value={slPrice}
                onChange={(e) => setSlPrice(e.target.value)}
              />
            </div>
            <div className="order-info-row">
              <span className="order-label">익절가</span>
              <input
                type="number"
                className="order-input-sm"
                placeholder="미설정"
                value={tpPrice}
                onChange={(e) => setTpPrice(e.target.value)}
              />
            </div>
            <button className="btn btn-ghost" onClick={handleSetExitOrders}>
              설정 저장
            </button>
          </div>
        )}

        {/* Result toast */}
        {result && (
          <div className={`order-result ${result.ok ? "success" : "error"}`}>
            {result.msg}
          </div>
        )}

        {/* Recent trades for this coin */}
        <RecentTrades market={market.market} />
      </div>
    </div>
  );
}

/* ── Recent Trades (coin-filtered) ── */

interface TradeItem {
  id: string;
  filled_at: number;
  market: string;
  side: string;
  quantity: string;
  price: string;
  total_amount: string;
  reason: string;
}

function RecentTrades({ market }: { market: string }) {
  const { get } = useApi();
  const [trades, setTrades] = useState<TradeItem[]>([]);

  useEffect(() => {
    get<{ items: TradeItem[] }>(`/api/portfolio/history?page=1&size=50`).then(
      (res) => {
        setTrades(res.items.filter((t) => t.market === market));
      },
    );
  }, [get, market]);

  if (trades.length === 0) return null;

  return (
    <div className="recent-trades-section">
      <h4>최근 거래 내역</h4>
      <table className="data-table">
        <thead>
          <tr>
            <th>시간</th>
            <th>구분</th>
            <th>가격</th>
            <th>수량</th>
            <th>사유</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 10).map((t) => (
            <tr key={t.id}>
              <td>{new Date(t.filled_at * 1000).toLocaleString("ko-KR")}</td>
              <td>
                <span className={`badge ${t.side === "BUY" ? "profit" : "loss"}`}>
                  {t.side === "BUY" ? "매수" : "매도"}
                </span>
              </td>
              <td>{formatPrice(t.price)}</td>
              <td>{Number(t.quantity).toFixed(8)}</td>
              <td>
                <span className="badge neutral" style={{ fontSize: "0.7rem" }}>
                  {t.reason}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 2: Add order panel styles to index.css**

Append to `src/ui/frontend/src/index.css`:

```css
/* ── Order Panel ── */
.order-form {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.order-info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 4px 0;
}

.order-label {
  font-size: 0.82rem;
  color: var(--text-dim);
}

.order-value {
  font-family: var(--font-mono);
  font-size: 0.85rem;
  color: var(--text);
}

.order-value.positive { color: var(--profit); }
.order-value.negative { color: var(--loss); }

.order-input {
  width: 100%;
  padding: 10px 12px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 0.9rem;
  outline: none;
}

.order-input:focus {
  border-color: var(--accent);
}

.order-input-sm {
  width: 140px;
  padding: 6px 10px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 0.82rem;
  outline: none;
}

.order-input-sm:focus {
  border-color: var(--accent);
}

.order-presets {
  display: flex;
  gap: 8px;
}

.order-presets .btn {
  flex: 1;
  font-size: 0.8rem;
  padding: 6px 0;
}

.order-submit {
  margin-top: 12px;
  padding: 12px;
  font-size: 0.95rem;
  font-weight: 600;
}

.exit-orders-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.exit-orders-section h4 {
  font-size: 0.85rem;
  color: var(--text-dim);
  margin-bottom: 8px;
}

.order-result {
  margin-top: 12px;
  padding: 10px 14px;
  border-radius: 6px;
  font-size: 0.82rem;
  text-align: center;
  animation: fadeIn 0.3s var(--ease);
}

.order-result.success {
  background: var(--profit-bg);
  color: var(--profit);
  border: 1px solid rgba(0, 224, 175, 0.2);
}

.order-result.error {
  background: var(--loss-bg);
  color: var(--loss);
  border: 1px solid rgba(255, 68, 102, 0.2);
}

@keyframes fadeIn {
  from { opacity: 0; transform: translateY(-4px); }
  to { opacity: 1; transform: translateY(0); }
}

.recent-trades-section {
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}

.recent-trades-section h4 {
  font-size: 0.85rem;
  color: var(--text-dim);
  margin-bottom: 8px;
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Exchange.tsx src/ui/frontend/src/index.css
git commit -m "feat: add order panel with buy/sell, presets, and exit order management"
```

---

### Task 13: Dashboard — Mode Badge, Toggle, and Reason Badge

**Files:**
- Modify: `src/ui/frontend/src/pages/Dashboard.tsx`

- [ ] **Step 1: Add mode badge to positions table**

In `src/ui/frontend/src/pages/Dashboard.tsx`, add `trade_mode` to the `PositionItem` type:

```tsx
trade_mode: string;  // "AUTO" | "MANUAL"
```

Add a column header in the positions table:

```tsx
<th>모드</th>
```

Add the mode badge cell in each position row (after the status badges column):

```tsx
<td>
  <span
    className={`badge ${pos.trade_mode === "AUTO" ? "info" : "warn"}`}
    style={{ cursor: "pointer" }}
    onClick={(e) => {
      e.stopPropagation();
      handleModeToggle(pos.market, pos.trade_mode);
    }}
  >
    {pos.trade_mode}
  </span>
</td>
```

- [ ] **Step 2: Add mode toggle handler with confirmation modal**

Add state and handler:

```tsx
const [modeModal, setModeModal] = useState<{
  market: string;
  currentMode: string;
  pnl: string;
} | null>(null);

const handleModeToggle = (market: string, currentMode: string) => {
  const pos = positions.find((p) => p.market === market);
  setModeModal({
    market,
    currentMode,
    pnl: pos ? pos.pnl_pct.toFixed(2) : "0",
  });
};

const confirmModeToggle = async () => {
  if (!modeModal) return;
  const newMode = modeModal.currentMode === "AUTO" ? "MANUAL" : "AUTO";
  await patchJson(`/api/exchange/position/${modeModal.market}/mode`, {
    trade_mode: newMode,
  });
  setModeModal(null);
  refreshAll();
};
```

Add the modal JSX at the end of the component return:

```tsx
{modeModal && (
  <div className="modal-overlay" onClick={() => setModeModal(null)}>
    <div className="modal-box" onClick={(e) => e.stopPropagation()}>
      <h3>매매 모드 전환</h3>
      <p>
        {modeModal.currentMode === "AUTO"
          ? "이 포지션을 수동 관리로 전환합니다. 자동매매 시그널이 적용되지 않습니다."
          : `이 포지션을 자동매매에 위임합니다. 현재 손익: ${Number(modeModal.pnl) >= 0 ? "+" : ""}${modeModal.pnl}%. 설정된 예약 손절/익절은 해제됩니다.`}
      </p>
      <div className="modal-actions">
        <button className="btn btn-ghost" onClick={() => setModeModal(null)}>
          취소
        </button>
        <button className="btn btn-primary" onClick={confirmModeToggle}>
          확인
        </button>
      </div>
    </div>
  </div>
)}
```

- [ ] **Step 3: Add reason badge to trade history**

In the `HistoryItem` type, add:

```tsx
reason: string;
```

In the history table, add a column and badge after the side column:

```tsx
<th>사유</th>
```

```tsx
<td>
  <span className={`badge ${
    h.reason === "ML_SIGNAL" ? "info"
    : h.reason === "MANUAL" ? "warn"
    : h.reason?.includes("STOP_LOSS") ? "loss"
    : "neutral"
  }`} style={{ fontSize: "0.7rem" }}>
    {h.reason}
  </span>
</td>
```

- [ ] **Step 4: Add modal styles to index.css**

Append to `src/ui/frontend/src/index.css`:

```css
/* ── Modal ── */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  backdrop-filter: blur(4px);
}

.modal-box {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--card-radius);
  padding: 24px;
  max-width: 420px;
  width: 90%;
}

.modal-box h3 {
  margin-bottom: 12px;
  color: var(--text);
}

.modal-box p {
  color: var(--text-dim);
  font-size: 0.9rem;
  line-height: 1.5;
  margin-bottom: 20px;
}

.modal-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}
```

- [ ] **Step 5: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 6: Commit**

```bash
git add src/ui/frontend/src/pages/Dashboard.tsx src/ui/frontend/src/index.css
git commit -m "feat: add mode badge/toggle and reason badge to Dashboard"
```

---

### Task 14: Toast Notifications for Order Fills

**Files:**
- Modify: `src/ui/frontend/src/App.tsx`
- Modify: `src/ui/frontend/src/index.css`

- [ ] **Step 1: Add toast notification system in App.tsx**

Add state and WebSocket handler for order_filled events in App.tsx:

```tsx
const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
const toastId = useRef(0);

useEffect(() => {
  if (lastMessage?.type !== "order_filled") return;
  const d = lastMessage.data as { market: string; side: string; reason: string; price: string };
  const id = ++toastId.current;
  const msg =
    d.side === "SELL"
      ? `${d.market.replace("KRW-", "")} ${d.reason} — ₩${Number(d.price).toLocaleString("ko-KR")}에 매도 완료`
      : `${d.market.replace("KRW-", "")} 매수 완료 — ₩${Number(d.price).toLocaleString("ko-KR")}`;
  setToasts((prev) => [...prev, { id, msg }]);
  setTimeout(() => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, 5000);
}, [lastMessage]);
```

Add toast container JSX at the bottom of the App return (after `</main>`):

```tsx
<div className="toast-container">
  {toasts.map((t) => (
    <div key={t.id} className="toast">{t.msg}</div>
  ))}
</div>
```

- [ ] **Step 2: Add toast styles**

Append to `src/ui/frontend/src/index.css`:

```css
/* ── Toast ── */
.toast-container {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 2000;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.toast {
  background: var(--bg-card);
  border: 1px solid var(--accent);
  border-radius: 8px;
  padding: 12px 18px;
  color: var(--text);
  font-size: 0.85rem;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.4);
  animation: slideIn 0.3s var(--ease), fadeOut 0.5s 4.5s var(--ease) forwards;
  max-width: 360px;
}

@keyframes slideIn {
  from { transform: translateX(100%); opacity: 0; }
  to { transform: translateX(0); opacity: 1; }
}

@keyframes fadeOut {
  from { opacity: 1; }
  to { opacity: 0; }
}
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/App.tsx src/ui/frontend/src/index.css
git commit -m "feat: add toast notification system for order fills"
```

---

### Task 15: Broadcast Order Fill Events from Backend

**Files:**
- Modify: `src/ui/api/server.py`

- [ ] **Step 1: Add order fill broadcasting to WebSocket relay**

In `src/ui/api/server.py`, in the `websocket_live` function, add order fill event relay. This requires tracking filled orders. Add after the ticker delta section in the while loop:

```python
                # Relay order fill events (check if new orders since last check)
                # This is handled by the order_filled events stored in app
```

Instead of polling orders, we'll add a simple queue to the App class. In `src/runtime/app.py`, add to `__init__`:

```python
        self._ws_outbox: list[dict[str, object]] = []
```

In `_monitor_positions`, after each `execute_sell` or `execute_partial_sell` call, add:

```python
            self._ws_outbox.append({
                "type": "order_filled",
                "data": {
                    "market": order.market,
                    "side": order.side.value,
                    "reason": order.reason,
                    "price": str(order.fill_price),
                },
            })
```

In `src/ui/api/server.py`, in the `websocket_live` while loop, after the ticker section:

```python
                # Relay queued events (order fills, etc.)
                if app_instance and hasattr(app_instance, "_ws_outbox"):
                    while app_instance._ws_outbox:
                        messages.append(app_instance._ws_outbox.pop(0))
```

- [ ] **Step 2: Also add outbox push in exchange routes for manual orders**

In `src/ui/api/routes/exchange.py`, after `await app._save_state()` in `manual_buy`:

```python
    app._ws_outbox.append({
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })
```

Do the same in `manual_sell`.

- [ ] **Step 3: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add src/runtime/app.py src/ui/api/server.py src/ui/api/routes/exchange.py
git commit -m "feat: broadcast order fill events via WebSocket for toast notifications"
```

---

### Task 16: Final Integration Test and Lint

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: All PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/`
Expected: No errors (fix any issues)

- [ ] **Step 3: Run type checker**

Run: `uv run mypy src/`
Expected: No new errors (fix any issues)

- [ ] **Step 4: Build frontend**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -A
git commit -m "fix: lint and type check cleanup for exchange feature"
```

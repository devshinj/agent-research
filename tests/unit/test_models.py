from decimal import Decimal

from src.types.enums import OrderSide, OrderStatus, OrderType, SignalType, WSMessageType


def test_signal_type_values() -> None:
    assert SignalType.BUY.value == 1
    assert SignalType.HOLD.value == 0
    assert SignalType.SELL.value == -1


def test_order_side_values() -> None:
    assert OrderSide.BUY.value == "BUY"
    assert OrderSide.SELL.value == "SELL"


def test_order_status_values() -> None:
    assert OrderStatus.PENDING.value == "PENDING"
    assert OrderStatus.FILLED.value == "FILLED"
    assert OrderStatus.CANCELLED.value == "CANCELLED"


def test_order_type_values() -> None:
    assert OrderType.MARKET.value == "MARKET"


def test_ws_message_type_values() -> None:
    assert WSMessageType.PRICE_UPDATE.value == "price_update"
    assert WSMessageType.TRADE_EXECUTED.value == "trade_executed"


import pytest
from dataclasses import FrozenInstanceError

from src.types.models import Candle, Order, PaperAccount, Position, Signal, DailySummary, Trade


def test_candle_creation() -> None:
    c = Candle(
        market="KRW-BTC",
        timeframe="1m",
        timestamp=1700000000,
        open=Decimal("50000000"),
        high=Decimal("50100000"),
        low=Decimal("49900000"),
        close=Decimal("50050000"),
        volume=Decimal("1.5"),
    )
    assert c.market == "KRW-BTC"
    assert c.close == Decimal("50050000")


def test_paper_account_initial_state() -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
        positions={},
    )
    assert account.initial_balance == Decimal("10000000")
    assert account.positions == {}


def test_signal_creation() -> None:
    s = Signal(
        market="KRW-ETH",
        signal_type=SignalType.BUY,
        confidence=0.75,
        timestamp=1700000000,
    )
    assert s.signal_type == SignalType.BUY
    assert s.confidence == 0.75


def test_position_creation() -> None:
    p = Position(
        market="KRW-BTC",
        side=OrderSide.BUY,
        entry_price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        entry_time=1700000000,
        unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
    )
    assert p.entry_price == Decimal("50000000")


def test_order_creation() -> None:
    o = Order(
        id="test-uuid",
        market="KRW-BTC",
        side=OrderSide.BUY,
        order_type=OrderType.MARKET,
        price=Decimal("50000000"),
        quantity=Decimal("0.001"),
        status=OrderStatus.PENDING,
        signal_confidence=0.8,
        reason="ML_SIGNAL",
        created_at=1700000000,
        fill_price=None,
        filled_at=None,
        fee=Decimal("0"),
    )
    assert o.status == OrderStatus.PENDING


def test_daily_summary_creation() -> None:
    ds = DailySummary(
        date="2026-04-03",
        starting_balance=Decimal("10000000"),
        ending_balance=Decimal("10234500"),
        realized_pnl=Decimal("234500"),
        total_trades=12,
        win_trades=8,
        loss_trades=4,
        max_drawdown_pct=Decimal("0.015"),
    )
    assert ds.win_trades == 8


def test_trade_creation() -> None:
    trade = Trade(
        market="KRW-BTC",
        price=Decimal("50000000"),
        volume=Decimal("0.001"),
        timestamp=1700000000,
        ask_bid="BID",
    )
    assert trade.market == "KRW-BTC"
    assert trade.price == Decimal("50000000")
    assert trade.ask_bid == "BID"


def test_trade_is_frozen() -> None:
    trade = Trade("KRW-BTC", Decimal("50000000"), Decimal("0.001"), 1700000000, "ASK")
    with pytest.raises(FrozenInstanceError):
        trade.price = Decimal("0")

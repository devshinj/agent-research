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

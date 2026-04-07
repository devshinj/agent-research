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
    result = pm.check_manual_exit(pos, Decimal("40000000"))
    assert result is None

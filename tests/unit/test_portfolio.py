from decimal import Decimal

from src.service.portfolio import PortfolioManager
from src.config.settings import RiskConfig
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )


def make_position(entry: str = "50000000", highest: str | None = None) -> Position:
    return Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal(entry), quantity=Decimal("0.05"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal(highest or entry),
    )


def test_update_unrealized_pnl():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    current_price = Decimal("51000000")
    pm.update_position(pos, current_price)
    assert pos.unrealized_pnl == Decimal("2")  # +2%


def test_update_highest_price():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    pm.update_position(pos, Decimal("52000000"))
    assert pos.highest_price == Decimal("52000000")


def test_stop_loss_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("48900000"))  # -2.2%
    assert action == "STOP_LOSS"


def test_take_profit_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("52600000"))  # +5.2%
    assert action == "TAKE_PROFIT"


def test_trailing_stop_trigger():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000", "55000000")  # 최고가 55M
    action = pm.check_exit_conditions(pos, Decimal("54000000"))
    assert action == "TRAILING_STOP"


def test_no_exit_in_normal_range():
    pm = PortfolioManager(make_risk_config())
    pos = make_position("50000000")
    action = pm.check_exit_conditions(pos, Decimal("50500000"))  # +1%
    assert action is None


def test_total_equity_calculation():
    pm = PortfolioManager(make_risk_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("7500000"),
        positions={
            "KRW-BTC": make_position("50000000"),
        },
    )
    prices = {"KRW-BTC": Decimal("51000000")}
    equity = pm.calculate_total_equity(account, prices)
    assert equity == Decimal("10050000")

"""Integration test: position monitoring triggers auto-exit and records trade results."""
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.service.paper_engine import PaperEngine
from src.service.portfolio import PortfolioManager
from src.service.risk_manager import RiskManager
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def _make_configs() -> tuple[RiskConfig, PaperTradingConfig]:
    risk = RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )
    pt = PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )
    return risk, pt


def test_stop_loss_triggers_sell_and_records_loss():
    """Stop-loss exit should sell the position and record a loss."""
    risk_cfg, pt_cfg = _make_configs()
    pm = PortfolioManager(risk_cfg)
    engine = PaperEngine(pt_cfg)
    rm = RiskManager(risk_cfg, pt_cfg)

    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})
    invest = rm.calculate_position_size(account)
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)

    position = account.positions["KRW-BTC"]
    # Price drops to trigger stop loss (-2%)
    drop_price = Decimal("48500000")
    pm.update_position(position, drop_price)
    reason = pm.check_exit_conditions(position, drop_price)
    assert reason == "STOP_LOSS"

    # Execute the exit
    entry_price = position.entry_price
    quantity = position.quantity
    order = engine.execute_sell(account, "KRW-BTC", drop_price, reason)

    # Record result
    if order.fill_price < entry_price:
        rm.record_loss()
        rm.record_daily_loss(
            (entry_price - order.fill_price) / entry_price,
        )

    assert "KRW-BTC" not in account.positions
    assert rm.dump_state()["consecutive_losses"] == 1
    assert Decimal(str(rm.dump_state()["daily_loss"])) > Decimal("0")


def test_take_profit_triggers_sell_and_records_win():
    """Take-profit exit should sell and record a win."""
    risk_cfg, pt_cfg = _make_configs()
    pm = PortfolioManager(risk_cfg)
    engine = PaperEngine(pt_cfg)
    rm = RiskManager(risk_cfg, pt_cfg)

    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})
    invest = rm.calculate_position_size(account)
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)

    position = account.positions["KRW-BTC"]
    up_price = Decimal("53000000")  # +6%
    pm.update_position(position, up_price)
    reason = pm.check_exit_conditions(position, up_price)
    assert reason == "TAKE_PROFIT"

    entry_price = position.entry_price
    order = engine.execute_sell(account, "KRW-BTC", up_price, reason)

    if order.fill_price >= entry_price:
        rm.record_win()

    assert "KRW-BTC" not in account.positions
    assert rm.dump_state()["consecutive_losses"] == 0
    # Cash should be more than initial (profit)
    assert account.cash_balance > Decimal("10000000")


def test_consecutive_losses_trigger_circuit_breaker():
    """Multiple stop-loss exits should activate the circuit breaker."""
    risk_cfg, pt_cfg = _make_configs()
    rm = RiskManager(risk_cfg, pt_cfg)

    for _ in range(5):
        rm.record_loss()
        rm.record_daily_loss(Decimal("0.005"))

    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})
    from src.types.models import Signal
    from src.types.enums import SignalType
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "서킷 브레이커" in reason


def test_daily_loss_limit_blocks_new_buys():
    """When daily loss exceeds limit, new buys should be blocked."""
    risk_cfg, pt_cfg = _make_configs()
    rm = RiskManager(risk_cfg, pt_cfg)

    # Accumulate 6% daily loss (limit is 5%)
    rm.record_daily_loss(Decimal("0.03"))
    rm.record_daily_loss(Decimal("0.03"))

    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})
    from src.types.models import Signal
    from src.types.enums import SignalType
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "일일 최대 손실" in reason

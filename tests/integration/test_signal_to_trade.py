from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.service.risk_manager import RiskManager
from src.service.paper_engine import PaperEngine
from src.types.enums import SignalType, OrderStatus
from src.types.models import PaperAccount, Signal


def test_full_buy_flow():
    """Signal -> RiskManager.approve -> PaperEngine.execute_buy 전체 흐름"""
    risk_config = RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )
    pt_config = PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )

    rm = RiskManager(risk_config, pt_config)
    engine = PaperEngine(pt_config)
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})

    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved

    invest = rm.calculate_position_size(account)
    order = engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)

    assert order.status == OrderStatus.FILLED
    assert "KRW-BTC" in account.positions
    assert account.cash_balance < Decimal("10000000")


def test_full_sell_flow():
    """보유 포지션 -> SELL Signal -> 체결 -> 포지션 청산"""
    risk_config = RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )
    pt_config = PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )

    rm = RiskManager(risk_config, pt_config)
    engine = PaperEngine(pt_config)
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})

    # 먼저 매수
    invest = rm.calculate_position_size(account)
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), invest, 0.8)
    assert "KRW-BTC" in account.positions

    # 매도 시그널
    sell_signal = Signal("KRW-BTC", SignalType.SELL, 0.9, 1700000060)
    approved, _ = rm.approve(sell_signal, account)
    assert approved

    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "ML_SIGNAL")
    assert order.status == OrderStatus.FILLED
    assert "KRW-BTC" not in account.positions

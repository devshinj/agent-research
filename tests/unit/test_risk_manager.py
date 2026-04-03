# tests/unit/test_risk_manager.py
from decimal import Decimal

from src.service.risk_manager import RiskManager
from src.config.settings import PaperTradingConfig, RiskConfig
from src.types.enums import SignalType, OrderSide
from src.types.models import PaperAccount, Position, Signal


def make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def make_account(cash: str = "10000000", positions: dict | None = None) -> PaperAccount:
    return PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal(cash),
        positions=positions or {},
    )


def test_approve_valid_buy_signal():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account()
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is True


def test_reject_when_max_positions_reached():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        f"KRW-COIN{i}": Position(
            f"KRW-COIN{i}", OrderSide.BUY, Decimal("1000000"),
            Decimal("1"), 1700000000, Decimal("0"), Decimal("1000000"),
        )
        for i in range(4)
    }
    account = make_account("0", positions)
    signal = Signal("KRW-NEW", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "포지션 한도" in reason


def test_reject_duplicate_buy():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        "KRW-BTC": Position(
            "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
            Decimal("0.001"), 1700000000, Decimal("0"), Decimal("50000000"),
        )
    }
    account = make_account("7500000", positions)
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "이미 보유" in reason


def test_reject_on_circuit_breaker():
    rm = RiskManager(make_risk_config(), make_pt_config())
    for _ in range(5):
        rm.record_loss()
    account = make_account()
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "서킷 브레이커" in reason


def test_sell_signal_allowed_when_holding():
    rm = RiskManager(make_risk_config(), make_pt_config())
    positions = {
        "KRW-BTC": Position(
            "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
            Decimal("0.001"), 1700000000, Decimal("0"), Decimal("50000000"),
        )
    }
    account = make_account("7500000", positions)
    signal = Signal("KRW-BTC", SignalType.SELL, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is True


def test_calculate_position_size():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account("10000000")
    size = rm.calculate_position_size(account)
    # max 25% of total balance
    assert size == Decimal("2500000")


def test_position_size_limited_by_cash():
    rm = RiskManager(make_risk_config(), make_pt_config())
    # positions에 자산이 있어서 total_equity > cash인 경우 cash가 한도
    positions = {
        "KRW-ETH": Position(
            "KRW-ETH", OrderSide.BUY, Decimal("10000000"),
            Decimal("1"), 1700000000, Decimal("0"), Decimal("10000000"),
        )
    }
    account = make_account("1000000", positions)
    size = rm.calculate_position_size(account)
    # total_equity = 1,000,000 + 10,000,000 = 11,000,000
    # max_amount = 11,000,000 * 0.25 = 2,750,000
    # min(cash=1,000,000, max=2,750,000) = 1,000,000
    assert size == Decimal("1000000")


def test_reject_below_min_order():
    rm = RiskManager(make_risk_config(), make_pt_config())
    account = make_account("3000")  # 3000원 — 최소 5000원 미만
    signal = Signal("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    approved, reason = rm.approve(signal, account)
    assert approved is False
    assert "최소 주문" in reason


def test_dump_and_load_state():
    rm = RiskManager(make_risk_config(), make_pt_config())
    for _ in range(3):
        rm.record_loss()
    rm.record_trade()
    rm.record_trade()

    state = rm.dump_state()
    assert state["consecutive_losses"] == 3
    assert state["daily_trades"] == 2

    rm2 = RiskManager(make_risk_config(), make_pt_config())
    rm2.load_state(state)
    state2 = rm2.dump_state()
    assert state2["consecutive_losses"] == 3
    assert state2["daily_trades"] == 2

# tests/unit/test_additional_buy.py
"""Phase 2: 추가 매수(물타기) 테스트."""
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.service.paper_engine import PaperEngine
from src.service.risk_manager import RiskManager
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def _make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
    )


def _make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
        max_additional_buys=3, additional_buy_drop_pct=Decimal("0.03"),
        additional_buy_ratio=Decimal("0.5"),
    )


def test_two_buys_weighted_average_entry_price() -> None:
    """같은 코인 2회 매수 후 entry_price가 가중평균인지 검증."""
    engine = PaperEngine(_make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})

    # 1차 매수: 50,000,000원
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), Decimal("1000000"), 0.8)
    pos = account.positions["KRW-BTC"]
    first_entry = pos.entry_price
    first_qty = pos.quantity
    first_invested = pos.total_invested
    assert pos.add_count == 0

    # 2차 매수: 48,000,000원 (하락 후)
    engine.execute_buy(account, "KRW-BTC", Decimal("48000000"), Decimal("500000"), 0.8)
    pos = account.positions["KRW-BTC"]
    assert pos.add_count == 1
    assert pos.quantity > first_qty
    assert pos.total_invested > first_invested
    # 가중평균: total_invested / total_quantity
    expected_entry = pos.total_invested / pos.quantity
    assert pos.entry_price == expected_entry
    # entry_price는 두 가격 사이에 있어야 함
    second_fill = Decimal("48000000") * (Decimal("1") + Decimal("0.0005"))
    assert second_fill < pos.entry_price < first_entry


def test_max_additional_buys_rejected() -> None:
    """add_count가 max에 도달하면 should_additional_buy가 False."""
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    position = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("50000000"), quantity=Decimal("0.01"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
        add_count=3,  # max에 도달
        total_invested=Decimal("1500000"),
    )
    # 충분히 하락했어도 max 횟수 초과면 거부
    current_price = Decimal("45000000")  # -10%
    assert rm.should_additional_buy(position, current_price) is False


def test_insufficient_drop_skips_additional_buy() -> None:
    """가격이 충분히 하락하지 않으면 추가매수 스킵."""
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    position = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("50000000"), quantity=Decimal("0.01"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
        add_count=0,
        total_invested=Decimal("500000"),
    )
    # 1% 하락 — 3% 미만이므로 스킵
    current_price = Decimal("49500000")
    assert rm.should_additional_buy(position, current_price) is False


def test_sufficient_drop_triggers_additional_buy() -> None:
    """가격이 3% 이상 하락하면 추가매수 허용."""
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    position = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("50000000"), quantity=Decimal("0.01"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("50000000"),
        add_count=0,
        total_invested=Decimal("500000"),
    )
    # 4% 하락 — 3% 이상이므로 허용
    current_price = Decimal("48000000")
    assert rm.should_additional_buy(position, current_price) is True


def test_additional_buy_position_size_is_half() -> None:
    """추가매수 시 포지션 사이즈가 initial의 50%."""
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("10000000"), {})
    normal = rm.calculate_position_size(account, Decimal("0.8"))
    additional = rm.calculate_position_size(account, Decimal("0.8"), is_additional=True)
    assert additional == normal // 2

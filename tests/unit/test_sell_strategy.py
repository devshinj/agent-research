# tests/unit/test_sell_strategy.py
"""Phase 4: 매도 전략 고도화 테스트."""
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.service.paper_engine import PaperEngine
from src.service.portfolio import PortfolioManager
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def _make_risk_config() -> RiskConfig:
    return RiskConfig(
        stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.08"),
        trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
        max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
        partial_take_profit_pct=Decimal("0.04"), partial_sell_fraction=Decimal("0.5"),
    )


def _make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def _make_position(
    entry_price: str = "50000000",
    quantity: str = "0.01",
    highest_price: str | None = None,
    partial_sold: bool = False,
    total_invested: str = "500000",
) -> Position:
    hp = highest_price or entry_price
    return Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal(entry_price), quantity=Decimal(quantity),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal(hp),
        total_invested=Decimal(total_invested),
        partial_sold=partial_sold,
    )


def test_partial_sell_at_4_pct() -> None:
    """+4% 도달 시 50% 매도 후 포지션 quantity가 절반."""
    pm = PortfolioManager(_make_risk_config())
    engine = PaperEngine(_make_pt_config())

    account = PaperAccount(Decimal("10000000"), Decimal("9500000"), {})
    pos = _make_position()
    account.positions["KRW-BTC"] = pos
    original_qty = pos.quantity

    # +4.5% 수익
    price = Decimal("52250000")
    pm.update_position(pos, price)
    fraction = pm.check_partial_exit(pos, price)
    assert fraction == Decimal("0.5")

    order = engine.execute_partial_sell(account, "KRW-BTC", price, fraction)
    assert order.reason == "PARTIAL_TAKE_PROFIT"
    # 잔여 포지션이 절반
    remaining_pos = account.positions.get("KRW-BTC")
    assert remaining_pos is not None
    assert remaining_pos.quantity < original_qty
    assert remaining_pos.partial_sold is True


def test_trailing_stop_only_in_profit() -> None:
    """트레일링 스톱이 평단 아래에서는 발동하지 않음."""
    pm = PortfolioManager(_make_risk_config())

    # 고점 기록 후 하락했지만 현재가가 평단 아래
    pos = _make_position(
        entry_price="50000000",
        highest_price="51000000",  # 고점
    )
    # 현재가가 평단 아래 (49500000) — 고점 대비 -2.9%이지만 평단 아래
    price = Decimal("49500000")
    pm.update_position(pos, price)
    reason = pm.check_exit_conditions(pos, price)
    # 트레일링 스톱이 아닌 다른 이유여야 함 (손절 조건 체크)
    assert reason != "TRAILING_STOP"


def test_trailing_stop_fires_in_profit() -> None:
    """수익 상태에서 고점 대비 1.5% 이상 하락 시 트레일링 스톱 발동."""
    pm = PortfolioManager(_make_risk_config())

    pos = _make_position(
        entry_price="50000000",
        highest_price="53000000",
    )
    # 현재가: 52000000 — 고점 대비 -1.88%, 평단 대비 +4%
    price = Decimal("52000000")
    pm.update_position(pos, price)
    reason = pm.check_exit_conditions(pos, price)
    assert reason == "TRAILING_STOP"


def test_partial_sell_not_repeated() -> None:
    """부분매도 후 다시 부분매도 조건이 와도 None 반환."""
    pm = PortfolioManager(_make_risk_config())
    pos = _make_position(partial_sold=True)

    # +5% — 충분한 수익이지만 이미 partial_sold
    price = Decimal("52500000")
    pm.update_position(pos, price)
    fraction = pm.check_partial_exit(pos, price)
    assert fraction is None


def test_partial_sell_tiny_remainder_fully_closes() -> None:
    """부분매도 후 잔여 포지션이 min_order_krw 미만이면 전량 청산."""
    engine = PaperEngine(_make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9999000"), {})

    # 아주 작은 포지션
    pos = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("50000000"), quantity=Decimal("0.00010000"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("52000000"),
        total_invested=Decimal("5000"),
    )
    account.positions["KRW-BTC"] = pos

    # 50% 매도 → 잔여 = 0.00005 * 50,000,000 = 2,500원 < min_order_krw(5000원)
    order = engine.execute_partial_sell(account, "KRW-BTC", Decimal("52000000"), Decimal("0.5"))
    # 전량 청산되어야 함
    assert "KRW-BTC" not in account.positions

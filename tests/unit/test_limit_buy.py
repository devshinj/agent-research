from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.service.paper_engine import PaperEngine
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import PaperAccount, Position


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def test_execute_limit_buy_no_cash_deduction():
    """execute_limit_buy should NOT deduct cash (already frozen)."""
    engine = PaperEngine(make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9900000"), {})
    frozen_amount = Decimal("100000")
    current_price = Decimal("49000000")

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", current_price, frozen_amount, reason="LIMIT_BUY",
    )

    assert order.status == OrderStatus.FILLED
    assert order.order_type == OrderType.LIMIT
    assert order.side == OrderSide.BUY
    assert "KRW-BTC" in account.positions
    assert refund >= Decimal("0")
    assert account.cash_balance >= Decimal("9900000")


def test_execute_limit_buy_refund_calculation():
    """Refund = frozen_amount - (actual_spend + fee)."""
    engine = PaperEngine(make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9900000"), {})
    frozen_amount = Decimal("100000")
    current_price = Decimal("50000000")

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", current_price, frozen_amount, reason="LIMIT_BUY",
    )

    actual_spend_plus_fee = frozen_amount - refund
    assert actual_spend_plus_fee > Decimal("0")
    assert actual_spend_plus_fee <= frozen_amount
    assert account.cash_balance == Decimal("9900000") + refund


def test_execute_limit_buy_adds_to_existing_position():
    """When position already exists, should update weighted average."""
    engine = PaperEngine(make_pt_config())
    account = PaperAccount(Decimal("10000000"), Decimal("9800000"), {})
    account.positions["KRW-BTC"] = Position(
        market="KRW-BTC", side=OrderSide.BUY,
        entry_price=Decimal("51000000"), quantity=Decimal("0.001"),
        entry_time=1700000000, unrealized_pnl=Decimal("0"),
        highest_price=Decimal("51000000"), total_invested=Decimal("51000"),
    )

    order, refund = engine.execute_limit_buy(
        account, "KRW-BTC", Decimal("49000000"), Decimal("100000"), reason="LIMIT_BUY",
    )

    pos = account.positions["KRW-BTC"]
    assert pos.quantity > Decimal("0.001")
    assert pos.add_count == 1

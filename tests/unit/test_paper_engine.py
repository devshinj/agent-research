import uuid
from decimal import Decimal

from src.service.paper_engine import PaperEngine
from src.config.settings import PaperTradingConfig
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import PaperAccount, Order, Position


def make_pt_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"), max_position_pct=Decimal("0.25"),
        max_open_positions=4, fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.0005"), min_order_krw=5000,
    )


def make_account(cash: str = "10000000") -> PaperAccount:
    return PaperAccount(Decimal("10000000"), Decimal(cash), {})


def test_execute_buy_order():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    current_price = Decimal("50000000")
    invest_amount = Decimal("2500000")

    order = engine.execute_buy(account, "KRW-BTC", current_price, invest_amount, 0.8)

    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.BUY
    assert order.fee > Decimal("0")
    assert "KRW-BTC" in account.positions
    assert account.cash_balance < Decimal("10000000")


def test_buy_applies_slippage():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    current_price = Decimal("50000000")

    order = engine.execute_buy(account, "KRW-BTC", current_price, Decimal("2500000"), 0.8)

    assert order.fill_price is not None
    assert order.fill_price > current_price


def test_execute_sell_order():
    engine = PaperEngine(make_pt_config())
    account = make_account("7500000")
    account.positions["KRW-BTC"] = Position(
        "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
        Decimal("0.05"), 1700000000, Decimal("0"), Decimal("50000000"),
    )

    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "ML_SIGNAL")

    assert order.status == OrderStatus.FILLED
    assert order.side == OrderSide.SELL
    assert "KRW-BTC" not in account.positions
    assert account.cash_balance > Decimal("7500000")


def test_sell_calculates_pnl():
    engine = PaperEngine(make_pt_config())
    account = make_account("7500000")
    entry = Decimal("50000000")
    account.positions["KRW-BTC"] = Position(
        "KRW-BTC", OrderSide.BUY, entry,
        Decimal("0.05"), 1700000000, Decimal("0"), entry,
    )

    sell_price = Decimal("52000000")
    order = engine.execute_sell(account, "KRW-BTC", sell_price, "TAKE_PROFIT")

    assert account.cash_balance > Decimal("7500000") + entry * Decimal("0.05") * Decimal("0.03")


def test_buy_deducts_fee_from_cash():
    engine = PaperEngine(make_pt_config())
    account = make_account()
    engine.execute_buy(account, "KRW-BTC", Decimal("50000000"), Decimal("2500000"), 0.8)

    expected_max = Decimal("10000000") - Decimal("2500000")
    assert account.cash_balance < expected_max

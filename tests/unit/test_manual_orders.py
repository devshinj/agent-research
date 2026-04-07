from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.service.paper_engine import PaperEngine
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


def _make_config() -> PaperTradingConfig:
    return PaperTradingConfig(
        initial_balance=Decimal("10000000"),
        max_position_pct=Decimal("0.1"),
        max_open_positions=5,
        fee_rate=Decimal("0.0005"),
        slippage_rate=Decimal("0.001"),
        min_order_krw=5000,
    )


def test_manual_buy_new_position_sets_manual_mode() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    order = engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.0, reason="MANUAL",
    )
    assert order.reason == "MANUAL"
    pos = account.positions["KRW-BTC"]
    assert pos.trade_mode == "MANUAL"


def test_manual_buy_existing_auto_position_switches_to_manual() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    assert account.positions["KRW-BTC"].trade_mode == "AUTO"
    engine.execute_buy(
        account, "KRW-BTC", Decimal("51000000"),
        Decimal("100000"), 0.0, reason="MANUAL",
    )
    assert account.positions["KRW-BTC"].trade_mode == "MANUAL"


def test_manual_sell_sets_reason() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    order = engine.execute_sell(account, "KRW-BTC", Decimal("51000000"), "MANUAL")
    assert order.reason == "MANUAL"


def test_manual_partial_sell_sets_reason() -> None:
    engine = PaperEngine(_make_config())
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )
    engine.execute_buy(
        account, "KRW-BTC", Decimal("50000000"),
        Decimal("100000"), 0.8,
    )
    order = engine.execute_partial_sell(
        account, "KRW-BTC", Decimal("51000000"),
        Decimal("0.5"), reason="MANUAL",
    )
    assert order.reason == "MANUAL"

import asyncio
from decimal import Decimal

import pytest

from src.repository.database import Database
from src.repository.portfolio_repo import PortfolioRepository
from src.types.enums import OrderSide
from src.types.models import PaperAccount, Position


@pytest.fixture
def repo(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    asyncio.get_event_loop().run_until_complete(db.initialize())
    yield PortfolioRepository(db)
    asyncio.get_event_loop().run_until_complete(db.close())


def test_save_load_position_with_trade_mode(repo: PortfolioRepository) -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("9000000"),
        positions={
            "KRW-BTC": Position(
                market="KRW-BTC",
                side=OrderSide.BUY,
                entry_price=Decimal("50000000"),
                quantity=Decimal("0.001"),
                entry_time=1000,
                unrealized_pnl=Decimal("0"),
                highest_price=Decimal("50000000"),
                trade_mode="MANUAL",
                stop_loss_price=Decimal("48000000"),
                take_profit_price=Decimal("55000000"),
            ),
        },
    )
    asyncio.get_event_loop().run_until_complete(repo.save_account(account))
    loaded = asyncio.get_event_loop().run_until_complete(
        repo.load_account(Decimal("10000000"))
    )
    assert loaded is not None
    pos = loaded.positions["KRW-BTC"]
    assert pos.trade_mode == "MANUAL"
    assert pos.stop_loss_price == Decimal("48000000")
    assert pos.take_profit_price == Decimal("55000000")


def test_save_load_position_auto_no_exit_orders(repo: PortfolioRepository) -> None:
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("9000000"),
        positions={
            "KRW-ETH": Position(
                market="KRW-ETH",
                side=OrderSide.BUY,
                entry_price=Decimal("3000000"),
                quantity=Decimal("0.1"),
                entry_time=1000,
                unrealized_pnl=Decimal("0"),
                highest_price=Decimal("3000000"),
            ),
        },
    )
    asyncio.get_event_loop().run_until_complete(repo.save_account(account))
    loaded = asyncio.get_event_loop().run_until_complete(
        repo.load_account(Decimal("10000000"))
    )
    assert loaded is not None
    pos = loaded.positions["KRW-ETH"]
    assert pos.trade_mode == "AUTO"
    assert pos.stop_loss_price is None
    assert pos.take_profit_price is None

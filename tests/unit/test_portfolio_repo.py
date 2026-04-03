import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.portfolio_repo import PortfolioRepository
from src.types.enums import OrderSide
from src.types.models import DailySummary, PaperAccount, Position


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def portfolio_repo(db):
    return PortfolioRepository(db)


async def test_save_and_get_daily_summary(portfolio_repo):
    ds = DailySummary(
        date="2026-04-03", starting_balance=Decimal("10000000"),
        ending_balance=Decimal("10234500"), realized_pnl=Decimal("234500"),
        total_trades=12, win_trades=8, loss_trades=4,
        max_drawdown_pct=Decimal("0.015"),
    )
    await portfolio_repo.save_daily_summary(ds)
    result = await portfolio_repo.get_daily_summary("2026-04-03")
    assert result is not None
    assert result.realized_pnl == Decimal("234500")


async def test_get_daily_summaries_range(portfolio_repo):
    for i in range(3):
        ds = DailySummary(
            date=f"2026-04-0{i+1}", starting_balance=Decimal("10000000"),
            ending_balance=Decimal("10000000"), realized_pnl=Decimal("0"),
            total_trades=0, win_trades=0, loss_trades=0,
            max_drawdown_pct=Decimal("0"),
        )
        await portfolio_repo.save_daily_summary(ds)
    result = await portfolio_repo.get_daily_summaries("2026-04-01", "2026-04-03")
    assert len(result) == 3


# ── Account State Persistence ──


async def test_save_and_load_account(portfolio_repo):
    account = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("7500000"),
        positions={
            "KRW-BTC": Position(
                market="KRW-BTC", side=OrderSide.BUY,
                entry_price=Decimal("50000000"), quantity=Decimal("0.05"),
                entry_time=1700000000, unrealized_pnl=Decimal("25000"),
                highest_price=Decimal("50500000"),
            ),
        },
    )
    await portfolio_repo.save_account(account)
    loaded = await portfolio_repo.load_account(Decimal("10000000"))

    assert loaded is not None
    assert loaded.cash_balance == Decimal("7500000")
    assert loaded.initial_balance == Decimal("10000000")
    assert "KRW-BTC" in loaded.positions
    pos = loaded.positions["KRW-BTC"]
    assert pos.entry_price == Decimal("50000000")
    assert pos.quantity == Decimal("0.05")
    assert pos.side == OrderSide.BUY
    assert pos.highest_price == Decimal("50500000")


async def test_load_account_returns_none_when_empty(portfolio_repo):
    result = await portfolio_repo.load_account(Decimal("10000000"))
    assert result is None


async def test_save_account_replaces_positions(portfolio_repo):
    account1 = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("8000000"),
        positions={
            "KRW-BTC": Position(
                "KRW-BTC", OrderSide.BUY, Decimal("50000000"),
                Decimal("0.04"), 1700000000, Decimal("0"), Decimal("50000000"),
            ),
        },
    )
    await portfolio_repo.save_account(account1)

    # Save again with different positions
    account2 = PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("9500000"),
        positions={
            "KRW-ETH": Position(
                "KRW-ETH", OrderSide.BUY, Decimal("3000000"),
                Decimal("0.1"), 1700001000, Decimal("0"), Decimal("3000000"),
            ),
        },
    )
    await portfolio_repo.save_account(account2)

    loaded = await portfolio_repo.load_account(Decimal("10000000"))
    assert loaded is not None
    assert "KRW-BTC" not in loaded.positions
    assert "KRW-ETH" in loaded.positions
    assert loaded.cash_balance == Decimal("9500000")


# ── Risk State Persistence ──


async def test_save_and_load_risk_state(portfolio_repo):
    state = {
        "consecutive_losses": 3,
        "cooldown_until": 1700003600,
        "daily_loss": Decimal("150000"),
        "daily_trades": 12,
        "current_day": "2026-04-03",
    }
    await portfolio_repo.save_risk_state(state)
    loaded = await portfolio_repo.load_risk_state()

    assert loaded is not None
    assert loaded["consecutive_losses"] == 3
    assert loaded["cooldown_until"] == 1700003600
    assert loaded["daily_loss"] == Decimal("150000")
    assert loaded["daily_trades"] == 12
    assert loaded["current_day"] == "2026-04-03"


async def test_load_risk_state_returns_none_when_empty(portfolio_repo):
    result = await portfolio_repo.load_risk_state()
    assert result is None

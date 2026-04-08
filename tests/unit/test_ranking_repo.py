from __future__ import annotations

import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.ranking_repo import RankingRepo
from src.repository.user_repo import UserRepo
from src.repository.portfolio_repo import PortfolioRepository
from src.types.models import DailySummary


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def repos(db):
    return {
        "user": UserRepo(db),
        "portfolio": PortfolioRepository(db),
        "ranking": RankingRepo(db),
    }


async def _create_user(repos, email: str, nickname: str, initial_balance: str, cash_balance: str) -> int:
    """Helper: create user, set initial_balance and cash_balance."""
    from src.ui.api.auth import hash_password
    user = await repos["user"].create(
        email=email, password_hash=hash_password("password123"), nickname=nickname,
    )
    uid = user["id"]
    await repos["user"].update_settings(uid, {"initial_balance": initial_balance})
    conn = repos["ranking"]._db.conn
    await conn.execute(
        "UPDATE account_state SET cash_balance = ? WHERE user_id = ?",
        (cash_balance, uid),
    )
    await conn.commit()
    return uid


@pytest.mark.asyncio
async def test_ranking_empty(repos):
    """No users → empty ranking."""
    result = await repos["ranking"].get_ranking(requesting_user_id=999)
    assert result == []


@pytest.mark.asyncio
async def test_ranking_single_user(repos):
    """Single user with daily summaries."""
    uid = await _create_user(repos, "a@test.com", "Alice", "1000000", "1100000")

    await repos["portfolio"].save_daily_summary(
        DailySummary(
            date="2026-04-07",
            starting_balance=Decimal("1000000"),
            ending_balance=Decimal("1050000"),
            realized_pnl=Decimal("50000"),
            total_trades=5,
            win_trades=3,
            loss_trades=2,
            max_drawdown_pct=Decimal("2.1"),
        ),
        user_id=uid,
    )
    await repos["portfolio"].save_daily_summary(
        DailySummary(
            date="2026-04-08",
            starting_balance=Decimal("1050000"),
            ending_balance=Decimal("1100000"),
            realized_pnl=Decimal("50000"),
            total_trades=3,
            win_trades=2,
            loss_trades=1,
            max_drawdown_pct=Decimal("1.5"),
        ),
        user_id=uid,
    )

    result = await repos["ranking"].get_ranking(requesting_user_id=uid)
    assert len(result) == 1
    entry = result[0]
    assert entry.rank == 1
    assert entry.nickname == "Alice"
    assert entry.return_pct == Decimal("10.00")  # (1100000-1000000)/1000000*100
    assert entry.realized_pnl == Decimal("100000")  # 1100000-1000000
    assert entry.initial_balance == Decimal("1000000")
    assert entry.total_trades == 8  # 5+3
    assert entry.win_rate == Decimal("62.50")  # 5/(5+3)*100
    assert entry.max_drawdown_pct == Decimal("2.1")  # max of 2.1, 1.5
    assert entry.is_me is True
    assert len(entry.daily_equities) == 2


@pytest.mark.asyncio
async def test_ranking_order(repos):
    """Two users, ranked by realized_pnl descending."""
    uid1 = await _create_user(repos, "a@test.com", "Alice", "1000000", "1200000")
    uid2 = await _create_user(repos, "b@test.com", "Bob", "1000000", "1100000")

    # Alice: 20% return
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1200000"),
                     Decimal("200000"), 10, 7, 3, Decimal("3.0")),
        user_id=uid1,
    )
    # Bob: 10% return
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1100000"),
                     Decimal("100000"), 5, 3, 2, Decimal("1.5")),
        user_id=uid2,
    )

    result = await repos["ranking"].get_ranking(requesting_user_id=uid2)
    assert len(result) == 2
    assert result[0].nickname == "Alice"
    assert result[0].rank == 1
    assert result[0].is_me is False
    assert result[1].nickname == "Bob"
    assert result[1].rank == 2
    assert result[1].is_me is True


@pytest.mark.asyncio
async def test_ranking_excludes_inactive(repos):
    """Inactive users are excluded from ranking."""
    uid1 = await _create_user(repos, "a@test.com", "Alice", "1000000", "1200000")
    uid2 = await _create_user(repos, "b@test.com", "Bob", "1000000", "1100000")

    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1200000"),
                     Decimal("200000"), 10, 7, 3, Decimal("3.0")),
        user_id=uid1,
    )
    await repos["portfolio"].save_daily_summary(
        DailySummary("2026-04-08", Decimal("1000000"), Decimal("1100000"),
                     Decimal("100000"), 5, 3, 2, Decimal("1.5")),
        user_id=uid2,
    )

    await repos["user"].set_active(uid2, False)

    result = await repos["ranking"].get_ranking(requesting_user_id=uid1)
    assert len(result) == 1
    assert result[0].nickname == "Alice"


@pytest.mark.asyncio
async def test_ranking_no_initial_balance(repos):
    """User with initial_balance=0 shows 0% return."""
    uid = await _create_user(repos, "a@test.com", "Alice", "0", "0")

    result = await repos["ranking"].get_ranking(requesting_user_id=uid)
    assert len(result) == 1
    assert result[0].return_pct == Decimal("0")

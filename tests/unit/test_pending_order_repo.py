import time
from decimal import Decimal

import pytest

from src.repository.database import Database
from src.repository.pending_order_repo import PendingOrderRepo
from src.repository.portfolio_repo import PortfolioRepository
from src.types.models import PaperAccount, PendingOrder


@pytest.fixture
async def db(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    yield db
    await db.close()


@pytest.fixture
async def repo(db):
    return PendingOrderRepo(db)


@pytest.fixture
async def portfolio_repo(db):
    return PortfolioRepository(db)


@pytest.fixture
def account():
    return PaperAccount(
        initial_balance=Decimal("10000000"),
        cash_balance=Decimal("10000000"),
    )


@pytest.fixture
def pending_order():
    now = int(time.time())
    return PendingOrder(
        id="test-order-1",
        user_id=1,
        market="KRW-BTC",
        side="BUY",
        limit_price=Decimal("50000000"),
        amount_krw=Decimal("100000"),
        status="PENDING",
        created_at=now,
        expires_at=now + 86400,
    )


@pytest.mark.asyncio
async def test_create_deducts_cash(repo, portfolio_repo, account, pending_order, db):
    await portfolio_repo.save_account(account, user_id=1)
    await repo.create(pending_order, account)
    assert account.cash_balance == Decimal("9900000")
    orders = await repo.get_pending_by_user(1)
    assert len(orders) == 1
    assert orders[0].id == "test-order-1"
    assert orders[0].status == "PENDING"


@pytest.mark.asyncio
async def test_cancel_refunds_cash(repo, portfolio_repo, account, pending_order, db):
    await portfolio_repo.save_account(account, user_id=1)
    await repo.create(pending_order, account)
    assert account.cash_balance == Decimal("9900000")
    result = await repo.cancel("test-order-1", account, user_id=1)
    assert result is True
    assert account.cash_balance == Decimal("10000000")
    orders = await repo.get_pending_by_user(1)
    assert len(orders) == 0


@pytest.mark.asyncio
async def test_cancel_nonexistent_returns_false(repo, portfolio_repo, account, db):
    await portfolio_repo.save_account(account, user_id=1)
    result = await repo.cancel("nonexistent", account, user_id=1)
    assert result is False


@pytest.mark.asyncio
async def test_expire_all_refunds(repo, portfolio_repo, account, db):
    await portfolio_repo.save_account(account, user_id=1)
    now = int(time.time())
    expired_order = PendingOrder(
        id="expired-1", user_id=1, market="KRW-BTC", side="BUY",
        limit_price=Decimal("50000000"), amount_krw=Decimal("200000"),
        status="PENDING", created_at=now - 100000, expires_at=now - 1,
    )
    await repo.create(expired_order, account)
    assert account.cash_balance == Decimal("9800000")
    count = await repo.expire_all(1, account)
    assert count == 1
    assert account.cash_balance == Decimal("10000000")


@pytest.mark.asyncio
async def test_fill_cas_prevents_double_fill(repo, portfolio_repo, account, pending_order, db):
    await portfolio_repo.save_account(account, user_id=1)
    await repo.create(pending_order, account)
    first = await repo.fill("test-order-1")
    assert first is True
    second = await repo.fill("test-order-1")
    assert second is False

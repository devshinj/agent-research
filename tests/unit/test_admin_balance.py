import pytest
from decimal import Decimal

from src.repository.database import Database
from src.repository.user_repo import UserRepo


@pytest.fixture
async def repo():
    db = Database(":memory:")
    await db.initialize()
    repo = UserRepo(db)
    yield repo
    await db.close()


@pytest.fixture
async def two_users(repo: UserRepo):
    admin = await repo.create(
        email="admin@test.com", password_hash="hash", nickname="admin",
    )
    user = await repo.create(
        email="user@test.com", password_hash="hash", nickname="user",
    )
    return admin, user


@pytest.mark.asyncio
async def test_get_cash_balance(repo: UserRepo, two_users):
    _, user = two_users
    balance = await repo.get_cash_balance(user["id"])
    assert balance == Decimal("5000000")


@pytest.mark.asyncio
async def test_adjust_balance_credit(repo: UserRepo, two_users):
    admin, user = two_users
    result = await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("3000000"), memo="초기 자본금 충전",
    )
    assert result["balance_before"] == Decimal("5000000")
    assert result["balance_after"] == Decimal("8000000")
    assert result["amount"] == Decimal("3000000")
    new_balance = await repo.get_cash_balance(user["id"])
    assert new_balance == Decimal("8000000")


@pytest.mark.asyncio
async def test_adjust_balance_debit(repo: UserRepo, two_users):
    admin, user = two_users
    result = await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("-2000000"), memo="차감",
    )
    assert result["balance_after"] == Decimal("3000000")


@pytest.mark.asyncio
async def test_adjust_balance_insufficient(repo: UserRepo, two_users):
    admin, user = two_users
    with pytest.raises(ValueError, match="잔고 부족"):
        await repo.adjust_balance(
            user_id=user["id"], admin_id=admin["id"],
            amount=Decimal("-99999999"), memo="과다 차감",
        )


@pytest.mark.asyncio
async def test_adjust_balance_zero_rejected(repo: UserRepo, two_users):
    admin, user = two_users
    with pytest.raises(ValueError, match="0이 될 수 없습니다"):
        await repo.adjust_balance(
            user_id=user["id"], admin_id=admin["id"],
            amount=Decimal("0"), memo="",
        )


@pytest.mark.asyncio
async def test_get_balance_history(repo: UserRepo, two_users):
    admin, user = two_users
    await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("1000000"), memo="1차 충전",
    )
    await repo.adjust_balance(
        user_id=user["id"], admin_id=admin["id"],
        amount=Decimal("-500000"), memo="차감",
    )
    history = await repo.get_balance_history(user["id"])
    assert len(history) == 2
    assert history[0]["amount"] == "-500000"
    assert history[0]["balance_after"] == "5500000"
    assert history[0]["memo"] == "차감"
    assert history[1]["amount"] == "1000000"
    assert history[1]["balance_after"] == "6000000"
    assert history[1]["memo"] == "1차 충전"

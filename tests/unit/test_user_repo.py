import pytest
import pytest_asyncio
from src.repository.database import Database
from src.repository.user_repo import UserRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    repo = UserRepo(db)
    yield repo
    await db.close()


@pytest.mark.asyncio
async def test_create_and_get_user(repo: UserRepo):
    user = await repo.create(
        email="test@example.com",
        password_hash="hashed_pw",
        nickname="tester",
    )
    assert user["id"] == 1
    assert user["email"] == "test@example.com"
    assert user["is_admin"] == 1  # first user is always admin

    fetched = await repo.get_by_email("test@example.com")
    assert fetched is not None
    assert fetched["nickname"] == "tester"


@pytest.mark.asyncio
async def test_first_user_is_admin(repo: UserRepo):
    user = await repo.create(
        email="admin@example.com",
        password_hash="hashed",
        nickname="admin",
    )
    assert user["is_admin"] == 1

    user2 = await repo.create(
        email="user2@example.com",
        password_hash="hashed",
        nickname="user2",
    )
    assert user2["is_admin"] == 0


@pytest.mark.asyncio
async def test_duplicate_email_raises(repo: UserRepo):
    await repo.create(email="dup@test.com", password_hash="h", nickname="a")
    with pytest.raises(ValueError, match="email"):
        await repo.create(email="dup@test.com", password_hash="h", nickname="b")


@pytest.mark.asyncio
async def test_get_settings_defaults(repo: UserRepo):
    user = await repo.create(email="s@t.com", password_hash="h", nickname="s")
    settings = await repo.get_settings(user["id"])
    assert settings["initial_balance"] == "5000000"
    assert settings["max_open_positions"] == 4
    assert settings["trading_enabled"] == 0


@pytest.mark.asyncio
async def test_update_settings(repo: UserRepo):
    user = await repo.create(email="s@t.com", password_hash="h", nickname="s")
    await repo.update_settings(user["id"], {"stop_loss_pct": "0.05"})
    settings = await repo.get_settings(user["id"])
    assert settings["stop_loss_pct"] == "0.05"


@pytest.mark.asyncio
async def test_list_users(repo: UserRepo):
    await repo.create(email="a@t.com", password_hash="h", nickname="a")
    await repo.create(email="b@t.com", password_hash="h", nickname="b")
    users = await repo.list_all()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_set_active(repo: UserRepo):
    user = await repo.create(email="a@t.com", password_hash="h", nickname="a")
    await repo.set_active(user["id"], False)
    fetched = await repo.get_by_id(user["id"])
    assert fetched["is_active"] == 0


@pytest.mark.asyncio
async def test_get_all_active_user_ids(repo: UserRepo):
    u1 = await repo.create(email="a@t.com", password_hash="h", nickname="a")
    u2 = await repo.create(email="b@t.com", password_hash="h", nickname="b")
    await repo.set_active(u2["id"], False)
    active = await repo.get_active_user_ids()
    assert active == [u1["id"]]

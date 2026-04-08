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

    # initial_balance should also increase so PnL stays neutral
    settings = await repo.get_settings(user["id"])
    assert Decimal(settings["initial_balance"]) == Decimal("8000000")


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


from httpx import ASGITransport, AsyncClient
from src.ui.api.server import create_app
from src.config.settings import (
    Settings, PaperTradingConfig, RiskConfig, ScreeningConfig,
    StrategyConfig, CollectorConfig, DataConfig,
)
from src.runtime.app import App


@pytest.fixture
async def admin_client():
    fastapi_app = create_app()
    settings = Settings(
        paper_trading=PaperTradingConfig(
            initial_balance=Decimal("5000000"), max_position_pct=Decimal("0.25"),
            max_open_positions=4, fee_rate=Decimal("0.0005"),
            slippage_rate=Decimal("0.0005"), min_order_krw=5000,
        ),
        risk=RiskConfig(
            stop_loss_pct=Decimal("0.02"), take_profit_pct=Decimal("0.05"),
            trailing_stop_pct=Decimal("0.015"), max_daily_loss_pct=Decimal("0.05"),
            max_daily_trades=50, consecutive_loss_limit=5, cooldown_minutes=60,
        ),
        screening=ScreeningConfig(
            min_volume_krw=Decimal("500000000"), min_volatility_pct=Decimal("1.0"),
            max_volatility_pct=Decimal("15.0"), max_coins=10,
            refresh_interval_min=30, always_include=("KRW-BTC",),
        ),
        strategy=StrategyConfig(
            lookahead_minutes=5, threshold_pct=Decimal("0.3"),
            retrain_interval_hours=6, min_confidence=Decimal("0.6"),
        ),
        collector=CollectorConfig(
            candle_timeframe=1, max_candles_per_market=200,
            market_refresh_interval_min=60,
        ),
        data=DataConfig(
            db_path=":memory:", model_dir="data/models",
            stale_candle_days=7, stale_model_days=30, stale_order_days=90,
        ),
    )
    app_instance = App(settings)
    await app_instance.db.initialize()
    fastapi_app.state.app = app_instance

    from src.ui.api.auth import hash_password, create_access_token, JWT_SECRET
    from datetime import timedelta

    await app_instance.user_repo.create(
        email="admin@test.com", password_hash=hash_password("pass"), nickname="admin",
    )
    await app_instance.user_repo.create(
        email="user@test.com", password_hash=hash_password("pass"), nickname="user",
    )
    # Load user 2 into runtime memory
    await app_instance.load_user(2)

    token = create_access_token(1, JWT_SECRET, timedelta(minutes=30))

    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["Authorization"] = f"Bearer {token}"
        yield c, app_instance

    await app_instance.db.close()


@pytest.mark.asyncio
async def test_api_adjust_balance(admin_client):
    client, app = admin_client
    resp = await client.post("/api/admin/users/2/balance", json={
        "amount": "3000000", "memo": "충전",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["balance_before"] == "5000000"
    assert data["balance_after"] == "8000000"
    assert app.user_accounts[2].cash_balance == Decimal("8000000")


@pytest.mark.asyncio
async def test_api_adjust_balance_insufficient(admin_client):
    client, _ = admin_client
    resp = await client.post("/api/admin/users/2/balance", json={
        "amount": "-99999999",
    })
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_api_balance_history(admin_client):
    client, _ = admin_client
    await client.post("/api/admin/users/2/balance", json={
        "amount": "1000000", "memo": "1차",
    })
    await client.post("/api/admin/users/2/balance", json={
        "amount": "-500000", "memo": "차감",
    })
    resp = await client.get("/api/admin/users/2/balance-history")
    assert resp.status_code == 200
    history = resp.json()["history"]
    assert len(history) == 2
    assert history[0]["memo"] == "차감"


@pytest.mark.asyncio
async def test_api_list_users_includes_balance(admin_client):
    client, _ = admin_client
    resp = await client.get("/api/admin/users")
    assert resp.status_code == 200
    users = resp.json()
    user2 = next(u for u in users if u["id"] == 2)
    assert "cash_balance" in user2
    assert user2["cash_balance"] == "5000000"

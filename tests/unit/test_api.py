import pytest
from httpx import ASGITransport, AsyncClient

from src.ui.api.server import create_app


@pytest.fixture
async def client():
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def test_health_check(client):
    resp = await client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


async def test_dashboard_summary(client):
    resp = await client.get("/api/dashboard/summary")
    assert resp.status_code == 200
    data = resp.json()
    assert "total_equity" in data
    assert "cash_balance" in data
    assert "daily_pnl" in data


async def test_portfolio_positions(client):
    resp = await client.get("/api/portfolio/positions")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_risk_status(client):
    resp = await client.get("/api/risk/status")
    assert resp.status_code == 200
    data = resp.json()
    assert "circuit_breaker_active" in data
    assert "consecutive_losses" in data


async def test_reset_trading_data():
    from src.repository.database import Database

    db = Database(":memory:")
    await db.initialize()

    # Insert dummy data into each trading table
    await db.conn.execute(
        "INSERT INTO account_state (id, cash_balance, updated_at) VALUES (1, '5000000', 100)"
    )
    await db.conn.execute(
        "INSERT INTO orders (id, market, side, order_type, price, quantity, fee, status, created_at) "
        "VALUES ('o1', 'KRW-BTC', 'BUY', 'MARKET', '1000', '1', '0.5', 'FILLED', 100)"
    )
    await db.conn.execute(
        "INSERT INTO positions (market, side, entry_price, quantity, entry_time, unrealized_pnl, highest_price) "
        "VALUES ('KRW-BTC', 'BUY', '1000', '1', 100, '0', '1000')"
    )
    await db.conn.execute(
        "INSERT INTO daily_summary (date, starting_balance, ending_balance, realized_pnl, total_trades, win_trades, loss_trades, max_drawdown_pct) "
        "VALUES ('2026-04-06', '10000000', '10500000', '500000', 5, 3, 2, '0.02')"
    )
    await db.conn.execute(
        "INSERT INTO risk_state (id, consecutive_losses, cooldown_until, daily_loss, daily_trades, current_day, updated_at) "
        "VALUES (1, 3, 0, '100000', 5, '2026-04-06', 100)"
    )
    await db.conn.execute(
        "INSERT INTO signals (market, signal_type, confidence, timestamp) "
        "VALUES ('KRW-BTC', 'BUY', 0.75, 1700000000)"
    )
    await db.conn.commit()

    # Reset
    await db.reset_trading_data()

    # Verify all trading tables are empty
    for table in ("orders", "positions", "account_state", "daily_summary", "risk_state", "signals"):
        cursor = await db.conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        assert row[0] == 0, f"{table} should be empty after reset"

    # Verify candles table still exists and is untouched
    cursor = await db.conn.execute("SELECT COUNT(*) FROM candles")
    row = await cursor.fetchone()
    assert row[0] == 0  # was empty, still exists

    await db.close()


async def test_get_config(client):
    resp = await client.get("/api/control/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "paper_trading" in data
    assert "risk" in data
    assert "screening" in data
    assert "strategy" in data
    assert "tick_stream" in data
    assert "data" in data


async def test_strategy_signals(client):
    resp = await client.get("/api/strategy/signals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_strategy_signals_with_params(client):
    resp = await client.get("/api/strategy/signals?limit=10&include_hold=true")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_strategy_model_status(client):
    resp = await client.get("/api/strategy/model-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "last_retrain" in data
    assert "next_retrain_hours" in data


async def test_reset(client):
    resp = await client.post("/api/control/reset", json={
        "paper_trading": {
            "initial_balance": 5000000,
            "max_position_pct": 0.25,
            "max_open_positions": 4,
            "fee_rate": 0.0005,
            "slippage_rate": 0.0005,
            "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015,
            "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50,
            "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000,
            "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0,
            "max_coins": 10,
            "refresh_interval_min": 30,
            "always_include": ["KRW-BTC"],
        },
        "strategy": {
            "lookahead_seconds": 30,
            "threshold_pct": 0.3,
            "retrain_interval_hours": 6,
            "min_confidence": 0.6,
            "signal_confirm_seconds": 3,
            "signal_confirm_min_confidence": 0.7,
        },
        "tick_stream": {
            "max_markets": 3,
            "reconnect_max_seconds": 30,
            "candle_retention_hours": 24,
        },
        "data": {
            "db_path": "data/paper_trader.db",
            "model_dir": "data/models",
            "stale_candle_days": 7,
            "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"

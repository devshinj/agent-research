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

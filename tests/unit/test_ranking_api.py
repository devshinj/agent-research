from __future__ import annotations

import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from fastapi.testclient import TestClient

from src.types.models import RankingEntry


def _make_app():
    """Create a test FastAPI app with ranking router."""
    from src.ui.api.routes.ranking import router
    from fastapi import FastAPI

    app = FastAPI()
    app.include_router(router, prefix="/api/ranking", tags=["ranking"])
    return app


def _mock_app_state(ranking_entries: list[RankingEntry]):
    """Create a mock app state with ranking_repo."""
    mock_ranking_repo = AsyncMock()
    mock_ranking_repo.get_ranking.return_value = ranking_entries

    mock_app = MagicMock()
    mock_app.ranking_repo = mock_ranking_repo
    mock_app.user_repo = AsyncMock()
    return mock_app


@pytest.fixture
def sample_entries():
    return [
        RankingEntry(
            rank=1, user_id=1, nickname="Alice",
            return_pct=Decimal("15.23"), realized_pnl=Decimal("152300"),
            initial_balance=Decimal("1000000"), total_equity=Decimal("1152300"),
            win_rate=Decimal("68.50"),
            total_trades=42, max_drawdown_pct=Decimal("3.70"),
            daily_equities=(Decimal("1000000"), Decimal("1050000"), Decimal("1152300")),
            is_me=False,
        ),
        RankingEntry(
            rank=2, user_id=2, nickname="Bob",
            return_pct=Decimal("10.00"), realized_pnl=Decimal("100000"),
            initial_balance=Decimal("1000000"), total_equity=Decimal("1100000"),
            win_rate=Decimal("55.00"),
            total_trades=20, max_drawdown_pct=Decimal("5.10"),
            daily_equities=(Decimal("1000000"), Decimal("1100000")),
            is_me=True,
        ),
    ]


def test_ranking_endpoint(sample_entries):
    app = _make_app()
    mock_state = _mock_app_state(sample_entries)

    # Patch auth dependency
    from src.ui.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": 2, "nickname": "Bob"}

    app.state.app = mock_state
    mock_state.user_repo.get_by_id.return_value = {"id": 2, "is_active": 1}

    client = TestClient(app)
    resp = client.get("/api/ranking/")
    assert resp.status_code == 200
    data = resp.json()

    assert data["total_users"] == 2
    assert data["my_rank"] == 2
    assert len(data["rankings"]) == 2

    first = data["rankings"][0]
    assert first["rank"] == 1
    assert first["nickname"] == "Alice"
    assert first["return_pct"] == "15.23"
    assert first["is_me"] is False

    second = data["rankings"][1]
    assert second["is_me"] is True
    assert len(second["daily_equities"]) == 2


def test_ranking_endpoint_empty():
    app = _make_app()
    mock_state = _mock_app_state([])

    from src.ui.api.auth import get_current_user
    app.dependency_overrides[get_current_user] = lambda: {"id": 1, "nickname": "X"}

    app.state.app = mock_state
    mock_state.user_repo.get_by_id.return_value = {"id": 1, "is_active": 1}

    client = TestClient(app)
    resp = client.get("/api/ranking/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["rankings"] == []
    assert data["my_rank"] is None
    assert data["total_users"] == 0

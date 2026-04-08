from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.ui.api.server import create_app


@pytest.fixture
def app():
    fastapi_app = create_app()
    # Set up a minimal app state so get_current_user can resolve the user
    mock_app = MagicMock()
    mock_app.user_repo.get_by_id = AsyncMock(
        return_value={"id": 1, "email": "user@test.com", "is_active": True, "is_admin": False}
    )
    # Ensure _get_gemini_key finds no key in settings
    mock_app.settings.agent.gemini_api_key = ""
    fastapi_app.state.app = mock_app
    return fastapi_app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def auth_header():
    from src.ui.api.auth import create_access_token
    token = create_access_token(user_id=1)
    return {"Authorization": f"Bearer {token}"}


def test_agent_chat_requires_auth(client):
    res = client.post("/api/agent/chat", json={"market": "KRW-BTC", "message": "hi"})
    assert res.status_code == 401


def test_agent_chat_no_api_key(client, auth_header):
    """Returns 503 when no Gemini API key is configured."""
    with patch.dict(os.environ, {}, clear=True), \
         patch("src.ui.api.routes.agent.Path") as mock_path:
        mock_path.return_value.exists.return_value = False
        res = client.post(
            "/api/agent/chat",
            json={"market": "KRW-BTC", "message": "hi", "history": []},
            headers=auth_header,
        )
    assert res.status_code == 503
    assert "Gemini API key" in res.json()["detail"]


def test_agent_chat_validation(client, auth_header):
    """Missing required fields returns 422."""
    res = client.post(
        "/api/agent/chat",
        json={},
        headers=auth_header,
    )
    assert res.status_code == 422

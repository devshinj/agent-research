import pytest
from datetime import timedelta
from src.ui.api.auth import create_access_token, create_refresh_token, decode_token


def test_create_and_decode_access_token():
    token = create_access_token(
        user_id=1, secret="test-secret", expires_delta=timedelta(minutes=30)
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == 1
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token(
        user_id=1, secret="test-secret", expires_delta=timedelta(days=7)
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == 1
    assert payload["type"] == "refresh"


def test_expired_token():
    token = create_access_token(
        user_id=1, secret="s", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(ValueError, match="expired"):
        decode_token(token, secret="s")


def test_invalid_secret():
    token = create_access_token(
        user_id=1, secret="s1", expires_delta=timedelta(minutes=30)
    )
    with pytest.raises(ValueError):
        decode_token(token, secret="wrong")

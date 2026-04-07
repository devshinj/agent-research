import asyncio
import json
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.service.upbit_ws import UpbitWebSocketService


def test_parse_ticker_message() -> None:
    service = UpbitWebSocketService()
    raw = {
        "type": "ticker",
        "code": "KRW-BTC",
        "trade_price": 50000000,
        "change": "RISE",
        "signed_change_rate": 0.025,
        "signed_change_price": 1200000,
        "acc_trade_volume_24h": 1234.5,
        "acc_trade_price_24h": 61725000000000,
        "timestamp": 1712500000000,
    }
    ticker = service._parse_ws_ticker(raw)
    assert ticker["market"] == "KRW-BTC"
    assert ticker["price"] == Decimal("50000000")
    assert ticker["change"] == "RISE"
    assert ticker["change_rate"] == Decimal("0.025")
    assert ticker["change_price"] == Decimal("1200000")
    assert ticker["volume_24h"] == Decimal("1234.5")
    assert ticker["acc_trade_price_24h"] == Decimal("61725000000000")
    assert ticker["timestamp"] == 1712500000


def test_get_snapshot_returns_cached_data() -> None:
    service = UpbitWebSocketService()
    service._cache["KRW-BTC"] = {
        "market": "KRW-BTC",
        "price": Decimal("50000000"),
        "change": "RISE",
        "change_rate": Decimal("0.025"),
        "change_price": Decimal("1200000"),
        "volume_24h": Decimal("1234.5"),
        "acc_trade_price_24h": Decimal("61725000000000"),
        "timestamp": 1712500000,
    }
    snapshot = service.get_snapshot()
    assert "KRW-BTC" in snapshot
    assert snapshot["KRW-BTC"]["price"] == Decimal("50000000")


def test_get_price_returns_none_for_unknown_market() -> None:
    service = UpbitWebSocketService()
    assert service.get_price("KRW-UNKNOWN") is None


def test_get_price_returns_cached_price() -> None:
    service = UpbitWebSocketService()
    service._cache["KRW-BTC"] = {
        "market": "KRW-BTC",
        "price": Decimal("50000000"),
        "change": "RISE",
        "change_rate": Decimal("0.025"),
        "change_price": Decimal("1200000"),
        "volume_24h": Decimal("1234.5"),
        "acc_trade_price_24h": Decimal("61725000000000"),
        "timestamp": 1712500000,
    }
    assert service.get_price("KRW-BTC") == Decimal("50000000")

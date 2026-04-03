# tests/unit/test_upbit_client.py
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, patch

from src.service.upbit_client import UpbitClient


@pytest.fixture
def client():
    return UpbitClient()


async def test_parse_markets_response(client):
    raw = [
        {"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
        {"market": "KRW-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
        {"market": "BTC-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
    ]
    result = client.filter_krw_markets(raw)
    assert len(result) == 2
    assert result[0] == "KRW-BTC"
    assert result[1] == "KRW-ETH"


async def test_extract_korean_names(client):
    raw = [
        {"market": "KRW-BTC", "korean_name": "비트코인", "english_name": "Bitcoin"},
        {"market": "KRW-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
        {"market": "BTC-ETH", "korean_name": "이더리움", "english_name": "Ethereum"},
    ]
    names = client.extract_korean_names(raw)
    assert names == {"KRW-BTC": "비트코인", "KRW-ETH": "이더리움"}
    assert "BTC-ETH" not in names


async def test_parse_candle_response(client):
    raw = {
        "market": "KRW-BTC",
        "candle_date_time_utc": "2026-04-03T12:00:00",
        "opening_price": 50000000,
        "high_price": 50100000,
        "low_price": 49900000,
        "trade_price": 50050000,
        "candle_acc_trade_volume": 1.5,
        "timestamp": 1700000000000,
    }
    candle = client.parse_candle(raw, timeframe="1m")
    assert candle.market == "KRW-BTC"
    assert candle.close == Decimal("50050000")
    assert candle.timestamp == 1700000000


async def test_parse_ticker_response(client):
    raw = {
        "market": "KRW-BTC",
        "trade_price": 50050000,
        "acc_trade_price_24h": 5000000000,
        "signed_change_rate": 0.015,
        "highest_52_week_price": 80000000,
        "lowest_52_week_price": 30000000,
        "timestamp": 1700000000000,
    }
    ticker = client.parse_ticker(raw)
    assert ticker["market"] == "KRW-BTC"
    assert ticker["price"] == Decimal("50050000")
    assert ticker["volume_24h"] == Decimal("5000000000")
    assert ticker["change_rate"] == Decimal("0.015")

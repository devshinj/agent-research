import json
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

from src.service.tick_stream import TickStream
from src.types.models import Trade


def test_tick_stream_creation():
    ts = TickStream(max_markets=3, reconnect_max_seconds=30)
    assert ts._max_markets == 3
    assert ts._reconnect_max_seconds == 30
    assert ts.on_tick is None


def test_parse_trade_message():
    raw = {
        "cd": "KRW-BTC",
        "tp": 50000000,
        "tv": 0.001,
        "tms": 1700000000123,
        "ab": "BID",
    }
    trade = TickStream.parse_trade(raw)
    assert trade.market == "KRW-BTC"
    assert trade.price == Decimal("50000000")
    assert trade.volume == Decimal("0.001")
    assert trade.timestamp == 1700000000
    assert trade.ask_bid == "BID"


def test_build_subscribe_message():
    msg = TickStream.build_subscribe_message(["KRW-BTC", "KRW-ETH"])
    parsed = json.loads(msg)
    assert len(parsed) == 2
    assert parsed[0]["ticket"]
    assert parsed[1]["type"] == "trade"
    assert parsed[1]["codes"] == ["KRW-BTC", "KRW-ETH"]


def test_max_markets_enforced():
    ts = TickStream(max_markets=2, reconnect_max_seconds=30)
    with pytest.raises(ValueError, match="max_markets"):
        ts._validate_markets(["KRW-BTC", "KRW-ETH", "KRW-XRP"])

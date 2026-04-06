import pytest
from collections.abc import Sequence
from decimal import Decimal
from unittest.mock import AsyncMock

from src.runtime.event_bus import EventBus
from src.service.candle_builder import CandleBuilder
from src.types.events import NewCandleEvent
from src.types.models import Candle, Trade


@pytest.fixture
def event_bus() -> EventBus:
    return EventBus()


@pytest.fixture
def builder(event_bus: EventBus) -> CandleBuilder:
    return CandleBuilder(event_bus)


def _make_trade(price: str, volume: str, timestamp: int, market: str = "KRW-BTC") -> Trade:
    return Trade(market, Decimal(price), Decimal(volume), timestamp, "BID")


# --- Time-based candle tests ---

async def test_1s_candle_emitted_on_new_second(builder: CandleBuilder, event_bus: EventBus):
    received: list[NewCandleEvent] = []

    async def handler(event: NewCandleEvent) -> None:
        received.append(event)

    event_bus.subscribe(NewCandleEvent, handler)

    # Two trades in second 100, one in second 101
    await builder.on_trade(_make_trade("100", "1.0", 100))
    await builder.on_trade(_make_trade("105", "2.0", 100))
    assert len(received) == 0  # not yet — same second

    await builder.on_trade(_make_trade("110", "1.5", 101))
    # The second-100 candle should now be emitted
    candle_1s = [e.candle for e in received if e.candle.timeframe == "1s"]
    assert len(candle_1s) == 1
    c = candle_1s[0]
    assert c.open == Decimal("100")
    assert c.high == Decimal("105")
    assert c.low == Decimal("100")
    assert c.close == Decimal("105")
    assert c.volume == Decimal("3.0")
    assert c.timestamp == 100


async def test_1m_candle_emitted_on_new_minute(builder: CandleBuilder, event_bus: EventBus):
    received: list[NewCandleEvent] = []

    async def handler(event: NewCandleEvent) -> None:
        received.append(event)

    event_bus.subscribe(NewCandleEvent, handler)

    # Minute boundary: 60 = start of minute 1, 120 = start of minute 2
    await builder.on_trade(_make_trade("100", "1.0", 60))
    await builder.on_trade(_make_trade("200", "1.0", 119))
    assert len([e for e in received if e.candle.timeframe == "1m"]) == 0

    await builder.on_trade(_make_trade("150", "1.0", 120))
    candle_1m = [e.candle for e in received if e.candle.timeframe == "1m"]
    assert len(candle_1m) == 1
    c = candle_1m[0]
    assert c.open == Decimal("100")
    assert c.high == Decimal("200")
    assert c.close == Decimal("200")
    assert c.timestamp == 60


# --- Tick-based candle tests ---

async def test_10tick_candle_emitted_after_10_trades(builder: CandleBuilder, event_bus: EventBus):
    received: list[NewCandleEvent] = []

    async def handler(event: NewCandleEvent) -> None:
        received.append(event)

    event_bus.subscribe(NewCandleEvent, handler)

    for i in range(10):
        await builder.on_trade(_make_trade(str(100 + i), "1.0", 100 + i))

    candle_10t = [e.candle for e in received if e.candle.timeframe == "10tick"]
    assert len(candle_10t) == 1
    c = candle_10t[0]
    assert c.open == Decimal("100")
    assert c.high == Decimal("109")
    assert c.low == Decimal("100")
    assert c.close == Decimal("109")
    assert c.volume == Decimal("10.0")


async def test_30tick_candle_emitted_after_30_trades(builder: CandleBuilder, event_bus: EventBus):
    received: list[NewCandleEvent] = []

    async def handler(event: NewCandleEvent) -> None:
        received.append(event)

    event_bus.subscribe(NewCandleEvent, handler)

    for i in range(30):
        await builder.on_trade(_make_trade(str(100 + i), "1.0", 100 + i))

    candle_30t = [e.candle for e in received if e.candle.timeframe == "30tick"]
    assert len(candle_30t) == 1


# --- Memory / get_recent tests ---

async def test_get_recent_returns_completed_candles(builder: CandleBuilder, event_bus: EventBus):
    # Generate 3 completed 1s candles
    for sec in range(4):  # seconds 0,1,2,3 — completes candles for 0,1,2
        await builder.on_trade(_make_trade(str(100 + sec), "1.0", sec))

    recent = builder.get_recent("KRW-BTC", "1s", limit=10)
    assert len(recent) == 3
    # Most recent first
    assert recent[0].timestamp == 2
    assert recent[-1].timestamp == 0


async def test_get_recent_respects_limit(builder: CandleBuilder, event_bus: EventBus):
    for sec in range(10):
        await builder.on_trade(_make_trade("100", "1.0", sec))

    recent = builder.get_recent("KRW-BTC", "1s", limit=3)
    assert len(recent) == 3


async def test_separate_markets(builder: CandleBuilder, event_bus: EventBus):
    await builder.on_trade(Trade("KRW-BTC", Decimal("100"), Decimal("1"), 0, "BID"))
    await builder.on_trade(Trade("KRW-ETH", Decimal("200"), Decimal("2"), 0, "ASK"))
    await builder.on_trade(Trade("KRW-BTC", Decimal("110"), Decimal("1"), 1, "BID"))
    await builder.on_trade(Trade("KRW-ETH", Decimal("210"), Decimal("2"), 1, "ASK"))

    btc = builder.get_recent("KRW-BTC", "1s", 10)
    eth = builder.get_recent("KRW-ETH", "1s", 10)
    assert len(btc) == 1
    assert len(eth) == 1
    assert btc[0].open == Decimal("100")
    assert eth[0].open == Decimal("200")

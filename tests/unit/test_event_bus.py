# tests/unit/test_event_bus.py
import asyncio

from src.runtime.event_bus import EventBus
from src.types.events import NewCandleEvent, SignalEvent
from src.types.enums import SignalType
from src.types.models import Candle
from decimal import Decimal


async def test_subscribe_and_publish():
    bus = EventBus()
    received: list = []

    async def handler(event: SignalEvent) -> None:
        received.append(event)

    bus.subscribe(SignalEvent, handler)
    event = SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000)
    await bus.publish(event)

    assert len(received) == 1
    assert received[0].market == "KRW-BTC"


async def test_multiple_subscribers():
    bus = EventBus()
    count = {"a": 0, "b": 0}

    async def handler_a(event: SignalEvent) -> None:
        count["a"] += 1

    async def handler_b(event: SignalEvent) -> None:
        count["b"] += 1

    bus.subscribe(SignalEvent, handler_a)
    bus.subscribe(SignalEvent, handler_b)

    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert count["a"] == 1
    assert count["b"] == 1


async def test_different_event_types_isolated():
    bus = EventBus()
    signal_received: list = []
    candle_received: list = []

    async def signal_handler(event: SignalEvent) -> None:
        signal_received.append(event)

    async def candle_handler(event: NewCandleEvent) -> None:
        candle_received.append(event)

    bus.subscribe(SignalEvent, signal_handler)
    bus.subscribe(NewCandleEvent, candle_handler)

    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert len(signal_received) == 1
    assert len(candle_received) == 0

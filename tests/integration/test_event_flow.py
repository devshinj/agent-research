import asyncio
from decimal import Decimal

from src.runtime.event_bus import EventBus
from src.types.events import SignalEvent, TradeEvent
from src.types.enums import SignalType, OrderSide, OrderStatus, OrderType
from src.types.models import Order


async def test_signal_to_trade_event_flow():
    """EventBus를 통해 Signal -> Trade 이벤트 체인이 작동하는지 검증"""
    bus = EventBus()
    trade_events: list[TradeEvent] = []

    async def on_signal(event: SignalEvent) -> None:
        # 시그널 수신 -> 트레이드 이벤트 발행 (간략화)
        order = Order(
            id="test-order", market=event.market, side=OrderSide.BUY,
            order_type=OrderType.MARKET, price=Decimal("50000000"),
            quantity=Decimal("0.001"), status=OrderStatus.FILLED,
            signal_confidence=event.confidence, reason="ML_SIGNAL",
            created_at=event.timestamp, fill_price=Decimal("50025000"),
            filled_at=event.timestamp, fee=Decimal("25"),
        )
        await bus.publish(TradeEvent(order, event.timestamp))

    async def on_trade(event: TradeEvent) -> None:
        trade_events.append(event)

    bus.subscribe(SignalEvent, on_signal)
    bus.subscribe(TradeEvent, on_trade)

    # 시그널 발행
    await bus.publish(SignalEvent("KRW-BTC", SignalType.BUY, 0.8, 1700000000))

    assert len(trade_events) == 1
    assert trade_events[0].order.market == "KRW-BTC"

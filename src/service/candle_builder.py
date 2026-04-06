from __future__ import annotations

import logging
from collections import deque
from collections.abc import Awaitable, Callable

from src.types.models import Candle, Trade

logger = logging.getLogger(__name__)

# Timeframe configs: (name, interval_seconds)
_TIME_FRAMES: list[tuple[str, int]] = [
    ("1s", 1),
    ("1m", 60),
]
_TICK_FRAMES: list[tuple[str, int]] = [
    ("10tick", 10),
    ("30tick", 30),
]

_DEQUE_LIMITS: dict[str, int] = {
    "1s": 3600,
    "1m": 1440,
    "10tick": 1000,
    "30tick": 1000,
}


class _CandleAccumulator:
    """Mutable candle being built from incoming trades."""

    __slots__ = ("market", "timeframe", "timestamp", "open", "high", "low", "close", "volume")

    def __init__(self, trade: Trade, timeframe: str, timestamp: int) -> None:
        self.market = trade.market
        self.timeframe = timeframe
        self.timestamp = timestamp
        self.open = trade.price
        self.high = trade.price
        self.low = trade.price
        self.close = trade.price
        self.volume = trade.volume

    def update(self, trade: Trade) -> None:
        if trade.price > self.high:
            self.high = trade.price
        if trade.price < self.low:
            self.low = trade.price
        self.close = trade.price
        self.volume += trade.volume

    def to_candle(self) -> Candle:
        return Candle(
            market=self.market,
            timeframe=self.timeframe,
            timestamp=self.timestamp,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
        )


class CandleBuilder:
    def __init__(self, on_candle: Callable[[Candle], Awaitable[None]]) -> None:
        self._on_candle = on_candle
        # Completed candles: (market, timeframe) -> deque[Candle]
        self._completed: dict[tuple[str, str], deque[Candle]] = {}
        # In-progress time-based candles: (market, timeframe) -> _CandleAccumulator
        self._time_building: dict[tuple[str, str], _CandleAccumulator] = {}
        # In-progress tick-based candles: (market, timeframe) -> (_CandleAccumulator, count)
        self._tick_building: dict[tuple[str, str], tuple[_CandleAccumulator, int]] = {}

    async def on_trade(self, trade: Trade) -> None:
        for tf_name, interval in _TIME_FRAMES:
            await self._handle_time_candle(trade, tf_name, interval)
        for tf_name, tick_count in _TICK_FRAMES:
            await self._handle_tick_candle(trade, tf_name, tick_count)

    async def _handle_time_candle(
        self, trade: Trade, tf_name: str, interval: int,
    ) -> None:
        key = (trade.market, tf_name)
        bucket = (trade.timestamp // interval) * interval

        current = self._time_building.get(key)
        if current is None:
            self._time_building[key] = _CandleAccumulator(trade, tf_name, bucket)
            return

        if bucket == current.timestamp:
            current.update(trade)
        else:
            # Emit completed candle
            await self._emit(current.to_candle())
            self._time_building[key] = _CandleAccumulator(trade, tf_name, bucket)

    async def _handle_tick_candle(
        self, trade: Trade, tf_name: str, tick_count: int,
    ) -> None:
        key = (trade.market, tf_name)

        entry = self._tick_building.get(key)
        if entry is None:
            acc = _CandleAccumulator(trade, tf_name, trade.timestamp)
            self._tick_building[key] = (acc, 1)
            return

        acc, count = entry
        acc.update(trade)
        count += 1

        if count >= tick_count:
            await self._emit(acc.to_candle())
            del self._tick_building[key]
        else:
            self._tick_building[key] = (acc, count)

    async def _emit(self, candle: Candle) -> None:
        key = (candle.market, candle.timeframe)
        if key not in self._completed:
            maxlen = _DEQUE_LIMITS.get(candle.timeframe, 1000)
            self._completed[key] = deque(maxlen=maxlen)
        self._completed[key].append(candle)
        await self._on_candle(candle)

    def get_recent(self, market: str, timeframe: str, limit: int) -> list[Candle]:
        key = (market, timeframe)
        buf = self._completed.get(key)
        if buf is None:
            return []
        # Return most recent first
        items = list(buf)
        items.reverse()
        return items[:limit]

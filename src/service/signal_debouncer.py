from __future__ import annotations

from collections import deque

from src.types.enums import SignalType
from src.types.models import Signal


class SignalDebouncer:
    def __init__(self, confirm_seconds: int, min_confidence: float) -> None:
        self._confirm_n = confirm_seconds
        self._min_confidence = min_confidence
        # market -> deque of recent signals
        self._buffers: dict[str, deque[Signal]] = {}

    def on_raw_signal(self, signal: Signal) -> Signal | None:
        if signal.signal_type == SignalType.HOLD:
            self._buffers.pop(signal.market, None)
            return None

        buf = self._buffers.get(signal.market)
        if buf is None:
            buf = deque(maxlen=self._confirm_n)
            self._buffers[signal.market] = buf

        # Direction change resets buffer
        if buf and buf[-1].signal_type != signal.signal_type:
            buf.clear()

        buf.append(signal)

        if len(buf) < self._confirm_n:
            return None

        avg_conf = sum(s.confidence for s in buf) / len(buf)
        if avg_conf < self._min_confidence:
            return None

        # Confirmed — clear buffer to avoid re-triggering
        buf.clear()
        return Signal(
            market=signal.market,
            signal_type=signal.signal_type,
            confidence=avg_conf,
            timestamp=signal.timestamp,
        )

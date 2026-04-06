from src.service.signal_debouncer import SignalDebouncer
from src.types.enums import SignalType
from src.types.models import Signal


def _signal(signal_type: SignalType, confidence: float, ts: int = 0) -> Signal:
    return Signal("KRW-BTC", signal_type, confidence, ts)


def test_no_signal_until_enough_consecutive():
    d = SignalDebouncer(confirm_seconds=3, min_confidence=0.7)

    assert d.on_raw_signal(_signal(SignalType.BUY, 0.8, 1)) is None
    assert d.on_raw_signal(_signal(SignalType.BUY, 0.8, 2)) is None
    result = d.on_raw_signal(_signal(SignalType.BUY, 0.8, 3))
    assert result is not None
    assert result.signal_type == SignalType.BUY


def test_mixed_directions_reset_buffer():
    d = SignalDebouncer(confirm_seconds=3, min_confidence=0.7)

    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 1))
    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 2))
    d.on_raw_signal(_signal(SignalType.SELL, 0.8, 3))  # breaks the chain
    d.on_raw_signal(_signal(SignalType.SELL, 0.8, 4))
    assert d.on_raw_signal(_signal(SignalType.SELL, 0.8, 5)) is not None


def test_low_confidence_not_confirmed():
    d = SignalDebouncer(confirm_seconds=3, min_confidence=0.7)

    d.on_raw_signal(_signal(SignalType.BUY, 0.5, 1))
    d.on_raw_signal(_signal(SignalType.BUY, 0.5, 2))
    result = d.on_raw_signal(_signal(SignalType.BUY, 0.5, 3))
    assert result is None  # avg confidence 0.5 < 0.7


def test_hold_resets_buffer():
    d = SignalDebouncer(confirm_seconds=3, min_confidence=0.7)

    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 1))
    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 2))
    d.on_raw_signal(_signal(SignalType.HOLD, 0.5, 3))  # reset
    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 4))
    d.on_raw_signal(_signal(SignalType.BUY, 0.8, 5))
    result = d.on_raw_signal(_signal(SignalType.BUY, 0.8, 6))
    assert result is not None


def test_sell_confirmed():
    d = SignalDebouncer(confirm_seconds=2, min_confidence=0.6)

    d.on_raw_signal(_signal(SignalType.SELL, 0.9, 1))
    result = d.on_raw_signal(_signal(SignalType.SELL, 0.9, 2))
    assert result is not None
    assert result.signal_type == SignalType.SELL


def test_separate_markets():
    d = SignalDebouncer(confirm_seconds=2, min_confidence=0.7)

    d.on_raw_signal(Signal("KRW-BTC", SignalType.BUY, 0.8, 1))
    d.on_raw_signal(Signal("KRW-ETH", SignalType.BUY, 0.8, 1))
    # Only one signal each — neither should be confirmed yet
    assert d.on_raw_signal(Signal("KRW-BTC", SignalType.BUY, 0.8, 2)) is not None
    assert d.on_raw_signal(Signal("KRW-ETH", SignalType.SELL, 0.8, 2)) is None  # direction changed

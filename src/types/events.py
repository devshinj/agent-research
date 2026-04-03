from dataclasses import dataclass
from decimal import Decimal

from src.types.enums import SignalType
from src.types.models import Candle, Order, ScreeningResult


@dataclass(frozen=True)
class NewCandleEvent:
    candle: Candle


@dataclass(frozen=True)
class ScreenedCoinsEvent:
    results: list[ScreeningResult]
    timestamp: int


@dataclass(frozen=True)
class SignalEvent:
    market: str
    signal_type: SignalType
    confidence: float
    timestamp: int


@dataclass(frozen=True)
class TradeEvent:
    order: Order
    timestamp: int


@dataclass(frozen=True)
class PriceUpdateEvent:
    market: str
    price: Decimal
    change_pct: Decimal
    timestamp: int

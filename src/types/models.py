from dataclasses import dataclass, field
from decimal import Decimal

from src.types.enums import OrderSide, OrderStatus, OrderType, SignalType


@dataclass(frozen=True)
class Candle:
    market: str
    timeframe: str
    timestamp: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


@dataclass
class Position:
    market: str
    side: OrderSide
    entry_price: Decimal
    quantity: Decimal
    entry_time: int
    unrealized_pnl: Decimal
    highest_price: Decimal


@dataclass
class Order:
    id: str
    market: str
    side: OrderSide
    order_type: OrderType
    price: Decimal
    quantity: Decimal
    status: OrderStatus
    signal_confidence: float
    reason: str
    created_at: int
    fill_price: Decimal | None
    filled_at: int | None
    fee: Decimal


@dataclass
class PaperAccount:
    initial_balance: Decimal
    cash_balance: Decimal
    positions: dict[str, Position] = field(default_factory=dict)


@dataclass(frozen=True)
class Signal:
    market: str
    signal_type: SignalType
    confidence: float
    timestamp: int


@dataclass(frozen=True)
class ScreeningResult:
    market: str
    volume_krw: Decimal
    volatility: Decimal
    score: Decimal
    timestamp: int


@dataclass(frozen=True)
class DailySummary:
    date: str
    starting_balance: Decimal
    ending_balance: Decimal
    realized_pnl: Decimal
    total_trades: int
    win_trades: int
    loss_trades: int
    max_drawdown_pct: Decimal

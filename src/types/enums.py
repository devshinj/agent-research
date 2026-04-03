from enum import Enum


class SignalType(Enum):
    BUY = 1
    HOLD = 0
    SELL = -1


class OrderSide(Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderStatus(Enum):
    PENDING = "PENDING"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"


class OrderType(Enum):
    MARKET = "MARKET"


class WSMessageType(Enum):
    PRICE_UPDATE = "price_update"
    POSITION_UPDATE = "position_update"
    TRADE_EXECUTED = "trade_executed"
    SIGNAL_FIRED = "signal_fired"
    RISK_ALERT = "risk_alert"
    SUMMARY_UPDATE = "summary_update"

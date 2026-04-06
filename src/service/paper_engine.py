from __future__ import annotations

import time
import uuid
from decimal import ROUND_DOWN, Decimal

from src.config.settings import PaperTradingConfig
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order, PaperAccount, Position

_ONE = Decimal("1")
_ZERO = Decimal("0")


def _truncate_krw(value: Decimal) -> Decimal:
    """Truncate to integer KRW (floor toward zero). Real exchanges never settle fractional won."""
    return value.to_integral_value(rounding=ROUND_DOWN)


def _quantize_quantity(invest_krw: Decimal, fill_price: Decimal) -> Decimal:
    """Calculate coin quantity so that quantity * fill_price is an integer KRW.

    Strategy: compute raw quantity, then floor it so the total cost
    (quantity * price) never exceeds invest_krw and is always whole won.
    """
    raw = invest_krw / fill_price
    # Floor quantity to 8 decimal places (Upbit precision), then
    # further reduce so that quantity * fill_price is integer KRW.
    quantized = raw.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    # Ensure the actual KRW spend is a whole number
    actual_krw = _truncate_krw(quantized * fill_price)
    # Recompute quantity from the truncated KRW to be precise
    if fill_price > _ZERO:
        quantized = actual_krw / fill_price
        quantized = quantized.quantize(Decimal("0.00000001"), rounding=ROUND_DOWN)
    return quantized


class PaperEngine:
    def __init__(self, config: PaperTradingConfig) -> None:
        self._config = config

    def update_config(self, config: PaperTradingConfig) -> None:
        self._config = config

    def execute_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        invest_amount: Decimal,
        confidence: float,
    ) -> Order:
        fill_price = current_price * (_ONE + self._config.slippage_rate)
        quantity = _quantize_quantity(invest_amount, fill_price)
        actual_spend = _truncate_krw(quantity * fill_price)
        fee = _truncate_krw(actual_spend * self._config.fee_rate)
        total_cost = actual_spend + fee
        now = int(time.time())

        account.cash_balance -= total_cost

        account.positions[market] = Position(
            market=market,
            side=OrderSide.BUY,
            entry_price=fill_price,
            quantity=quantity,
            entry_time=now,
            unrealized_pnl=_ZERO,
            highest_price=fill_price,
        )

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=quantity,
            status=OrderStatus.FILLED,
            signal_confidence=confidence,
            reason="ML_SIGNAL",
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )

    def execute_sell(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        reason: str,
    ) -> Order:
        position = account.positions[market]
        fill_price = current_price * (_ONE - self._config.slippage_rate)
        proceeds = _truncate_krw(fill_price * position.quantity)
        fee = _truncate_krw(proceeds * self._config.fee_rate)
        net_proceeds = proceeds - fee
        now = int(time.time())

        account.cash_balance += net_proceeds

        del account.positions[market]

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=position.quantity,
            status=OrderStatus.FILLED,
            signal_confidence=0,
            reason=reason,
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )

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

    def safe_buy_amount(self, cash_balance: Decimal) -> Decimal:
        """Return the maximum invest_amount that won't exceed cash after fees + slippage."""
        overhead = (_ONE + self._config.slippage_rate) * (_ONE + self._config.fee_rate)
        return (cash_balance / overhead).to_integral_value(rounding=ROUND_DOWN)

    def execute_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        invest_amount: Decimal,
        confidence: float,
        reason: str | None = None,
    ) -> Order:
        fill_price = current_price * (_ONE + self._config.slippage_rate)
        quantity = _quantize_quantity(invest_amount, fill_price)
        actual_spend = _truncate_krw(quantity * fill_price)
        fee = _truncate_krw(actual_spend * self._config.fee_rate)
        total_cost = actual_spend + fee
        now = int(time.time())

        account.cash_balance -= total_cost

        trade_mode = "MANUAL" if reason == "MANUAL" else "AUTO"

        existing = account.positions.get(market)
        if existing is not None:
            # 추가매수: 가중평균 entry_price 계산
            new_total_invested = existing.total_invested + actual_spend
            new_quantity = existing.quantity + quantity
            new_entry_price = (
                new_total_invested / new_quantity
                if new_quantity > _ZERO else fill_price
            )
            existing.entry_price = new_entry_price
            existing.quantity = new_quantity
            existing.total_invested = new_total_invested
            existing.add_count += 1
            existing.highest_price = max(existing.highest_price, fill_price)
            if reason == "MANUAL":
                existing.trade_mode = "MANUAL"
            order_reason = reason if reason else "ADDITIONAL_BUY"
        else:
            account.positions[market] = Position(
                market=market,
                side=OrderSide.BUY,
                entry_price=fill_price,
                quantity=quantity,
                entry_time=now,
                unrealized_pnl=_ZERO,
                highest_price=fill_price,
                add_count=0,
                total_invested=actual_spend,
                trade_mode=trade_mode,
            )
            order_reason = reason if reason else "ML_SIGNAL"

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=quantity,
            status=OrderStatus.FILLED,
            signal_confidence=confidence,
            reason=order_reason,
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

    def execute_partial_sell(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        fraction: Decimal,
        reason: str | None = None,
    ) -> Order:
        """fraction(0~1) 비율만큼 수량을 매도. 잔여 포지션 유지."""
        position = account.positions[market]
        sell_quantity = (position.quantity * fraction).quantize(
            Decimal("0.00000001"), rounding=ROUND_DOWN,
        )
        remaining = position.quantity - sell_quantity

        fill_price = current_price * (_ONE - self._config.slippage_rate)
        proceeds = _truncate_krw(fill_price * sell_quantity)
        fee = _truncate_krw(proceeds * self._config.fee_rate)
        net_proceeds = proceeds - fee
        now = int(time.time())

        account.cash_balance += net_proceeds

        # 잔여 수량이 min_order_krw 미만이면 전량 청산
        remaining_value = remaining * position.entry_price
        if remaining_value < self._config.min_order_krw:
            # 잔여분도 매도
            extra_proceeds = _truncate_krw(fill_price * remaining)
            extra_fee = _truncate_krw(extra_proceeds * self._config.fee_rate)
            account.cash_balance += extra_proceeds - extra_fee
            sell_quantity = position.quantity
            fee += extra_fee
            del account.positions[market]
        else:
            position.quantity = remaining
            # total_invested 비례 감소
            if position.quantity > _ZERO:
                ratio = remaining / (remaining + sell_quantity)
                position.total_invested = _truncate_krw(position.total_invested * ratio)
            position.partial_sold = True

        order_reason = reason if reason else "PARTIAL_TAKE_PROFIT"

        return Order(
            id=str(uuid.uuid4()),
            market=market,
            side=OrderSide.SELL,
            order_type=OrderType.MARKET,
            price=current_price,
            quantity=sell_quantity,
            status=OrderStatus.FILLED,
            signal_confidence=0,
            reason=order_reason,
            created_at=now,
            fill_price=fill_price,
            filled_at=now,
            fee=fee,
        )

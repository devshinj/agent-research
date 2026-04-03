from __future__ import annotations

import uuid
import time
from decimal import Decimal

from src.config.settings import PaperTradingConfig
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order, PaperAccount, Position


class PaperEngine:
    def __init__(self, config: PaperTradingConfig) -> None:
        self._config = config

    def execute_buy(
        self,
        account: PaperAccount,
        market: str,
        current_price: Decimal,
        invest_amount: Decimal,
        confidence: float,
    ) -> Order:
        fill_price = current_price * (Decimal("1") + self._config.slippage_rate)
        quantity = invest_amount / fill_price
        fee = invest_amount * self._config.fee_rate
        total_cost = invest_amount + fee
        now = int(time.time())

        account.cash_balance -= total_cost

        account.positions[market] = Position(
            market=market,
            side=OrderSide.BUY,
            entry_price=fill_price,
            quantity=quantity,
            entry_time=now,
            unrealized_pnl=Decimal("0"),
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
        fill_price = current_price * (Decimal("1") - self._config.slippage_rate)
        proceeds = fill_price * position.quantity
        fee = proceeds * self._config.fee_rate
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

from __future__ import annotations

from decimal import Decimal

from src.config.settings import RiskConfig
from src.types.models import PaperAccount, Position


class PortfolioManager:
    def __init__(self, risk_config: RiskConfig) -> None:
        self._risk = risk_config

    def update_position(self, position: Position, current_price: Decimal) -> None:
        position.unrealized_pnl = (
            (current_price - position.entry_price) / position.entry_price * Decimal("100")
        )
        if current_price > position.highest_price:
            position.highest_price = current_price

    def check_exit_conditions(self, position: Position, current_price: Decimal) -> str | None:
        pnl_pct = (current_price - position.entry_price) / position.entry_price

        if pnl_pct <= -self._risk.stop_loss_pct:
            return "STOP_LOSS"

        if position.highest_price > position.entry_price:
            drop_from_high = (
                (position.highest_price - current_price) / position.highest_price
            )
            if drop_from_high >= self._risk.trailing_stop_pct:
                return "TRAILING_STOP"

        if pnl_pct >= self._risk.take_profit_pct:
            return "TAKE_PROFIT"

        return None

    def check_manual_exit(self, position: Position, current_price: Decimal) -> str | None:
        """Check MANUAL position exit orders. Returns reason or None."""
        if position.trade_mode != "MANUAL":
            return None
        if position.stop_loss_price is not None and current_price <= position.stop_loss_price:
            return "MANUAL_STOP_LOSS"
        if position.take_profit_price is not None and current_price >= position.take_profit_price:
            return "MANUAL_TAKE_PROFIT"
        return None

    def calculate_total_equity(
        self, account: PaperAccount, current_prices: dict[str, Decimal]
    ) -> Decimal:
        position_value = sum(
            (current_prices.get(market, pos.entry_price) * pos.quantity
             for market, pos in account.positions.items()),
            Decimal("0"),
        )
        return account.cash_balance + position_value

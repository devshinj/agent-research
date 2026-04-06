# src/service/risk_manager.py
from __future__ import annotations

import time
from decimal import Decimal

from src.config.settings import PaperTradingConfig, RiskConfig
from src.types.enums import SignalType
from src.types.models import PaperAccount, Signal


class RiskManager:
    def __init__(self, risk_config: RiskConfig, pt_config: PaperTradingConfig) -> None:
        self._risk = risk_config
        self._pt = pt_config
        self._consecutive_losses = 0
        self._cooldown_until = 0
        self._daily_loss = Decimal("0")
        self._daily_trades = 0
        self._current_day = ""

    def update_config(self, risk_config: RiskConfig) -> None:
        self._risk = risk_config

    def approve(self, signal: Signal, account: PaperAccount) -> tuple[bool, str]:
        # SELL은 보유 중이면 허용
        if signal.signal_type == SignalType.SELL:
            if signal.market in account.positions:
                return True, "OK"
            return False, "매도할 포지션 없음"

        # HOLD는 무시
        if signal.signal_type == SignalType.HOLD:
            return False, "HOLD 시그널"

        # BUY 체크
        # [1] 서킷 브레이커
        if self._consecutive_losses >= self._risk.consecutive_loss_limit:
            if time.time() < self._cooldown_until:
                return False, "서킷 브레이커 발동 — 쿨다운 중"
            self._consecutive_losses = 0  # 쿨다운 종료

        # [2] 일일 한도
        if self._daily_trades >= self._risk.max_daily_trades:
            return False, "일일 최대 거래 횟수 도달"

        # [3] 포지션 한도
        if len(account.positions) >= self._pt.max_open_positions:
            return False, "포지션 한도 도달"

        if signal.market in account.positions:
            return False, f"{signal.market} 이미 보유 중 — 중복 매수 불가"

        # [4] 최소 주문 금액
        invest_amount = self.calculate_position_size(account)
        if invest_amount < self._pt.min_order_krw:
            return False, f"최소 주문 금액({self._pt.min_order_krw}원) 미달"

        return True, "OK"

    def calculate_position_size(self, account: PaperAccount) -> Decimal:
        from decimal import ROUND_DOWN

        total_equity = account.cash_balance + sum(
            p.entry_price * p.quantity for p in account.positions.values()
        )
        max_amount = total_equity * self._pt.max_position_pct
        # Reserve room for slippage + fee so total cost never exceeds cash
        overhead = (Decimal("1") + self._pt.slippage_rate) * (Decimal("1") + self._pt.fee_rate)
        safe_cash = (account.cash_balance / overhead).to_integral_value(
            rounding=ROUND_DOWN,
        )
        # Truncate to integer KRW — real exchanges never settle fractional won
        return min(safe_cash, max_amount).to_integral_value(
            rounding=ROUND_DOWN,
        )

    def record_loss(self) -> None:
        self._consecutive_losses += 1
        if self._consecutive_losses >= self._risk.consecutive_loss_limit:
            self._cooldown_until = int(time.time()) + self._risk.cooldown_minutes * 60

    def record_win(self) -> None:
        self._consecutive_losses = 0

    def record_trade(self) -> None:
        self._daily_trades += 1

    def reset_daily(self) -> None:
        self._daily_loss = Decimal("0")
        self._daily_trades = 0

    def dump_state(self) -> dict[str, object]:
        return {
            "consecutive_losses": self._consecutive_losses,
            "cooldown_until": self._cooldown_until,
            "daily_loss": self._daily_loss,
            "daily_trades": self._daily_trades,
            "current_day": self._current_day,
        }

    def load_state(self, state: dict[str, object]) -> None:
        self._consecutive_losses = int(state["consecutive_losses"])  # type: ignore[arg-type]
        self._cooldown_until = int(state["cooldown_until"])  # type: ignore[arg-type]
        self._daily_loss = Decimal(str(state["daily_loss"]))
        self._daily_trades = int(state["daily_trades"])  # type: ignore[arg-type]
        self._current_day = str(state["current_day"])

from __future__ import annotations

import time
from decimal import Decimal

from src.repository.database import Database
from src.types.enums import OrderSide
from src.types.models import DailySummary, PaperAccount, Position


class PortfolioRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save_daily_summary(self, summary: DailySummary, user_id: int) -> None:
        await self._db.conn.execute(
            """INSERT INTO daily_summary
               (date, starting_balance, ending_balance, realized_pnl,
                total_trades, win_trades, loss_trades, max_drawdown_pct, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(date, user_id) DO UPDATE SET
                 ending_balance=excluded.ending_balance,
                 realized_pnl=excluded.realized_pnl,
                 total_trades=excluded.total_trades,
                 win_trades=excluded.win_trades,
                 loss_trades=excluded.loss_trades,
                 max_drawdown_pct=excluded.max_drawdown_pct""",
            (summary.date, str(summary.starting_balance), str(summary.ending_balance),
             str(summary.realized_pnl), summary.total_trades, summary.win_trades,
             summary.loss_trades, str(summary.max_drawdown_pct), user_id),
        )
        await self._db.conn.commit()

    async def get_daily_summary(self, date: str, user_id: int) -> DailySummary | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM daily_summary WHERE date=? AND user_id=?", (date, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_summary(row)

    async def get_daily_summaries(self, start_date: str, end_date: str, user_id: int) -> list[DailySummary]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM daily_summary WHERE user_id = ? AND date >= ? AND date <= ? ORDER BY date",
            (user_id, start_date, end_date),
        )
        rows = await cursor.fetchall()
        return [self._row_to_summary(r) for r in rows]

    @staticmethod
    def _row_to_summary(row: tuple) -> DailySummary:  # type: ignore[type-arg]
        return DailySummary(
            date=row[0], starting_balance=Decimal(row[1]),
            ending_balance=Decimal(row[2]), realized_pnl=Decimal(row[3]),
            total_trades=int(row[4]), win_trades=int(row[5]),
            loss_trades=int(row[6]), max_drawdown_pct=Decimal(row[7]),
        )

    # ── Account State Persistence ──

    async def save_account(self, account: PaperAccount, user_id: int) -> None:
        now = int(time.time())
        await self._db.conn.execute(
            """INSERT INTO account_state (user_id, cash_balance, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 cash_balance=excluded.cash_balance,
                 updated_at=excluded.updated_at""",
            (user_id, str(account.cash_balance), now),
        )
        await self._db.conn.execute(
            "DELETE FROM positions WHERE user_id = ?", (user_id,)
        )
        if account.positions:
            await self._db.conn.executemany(
                """INSERT INTO positions
                   (market, side, entry_price, quantity, entry_time, unrealized_pnl,
                    highest_price, add_count, total_invested, partial_sold,
                    trade_mode, stop_loss_price, take_profit_price, user_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                [
                    (market, p.side.value, str(p.entry_price), str(p.quantity),
                     p.entry_time, str(p.unrealized_pnl), str(p.highest_price),
                     p.add_count, str(p.total_invested), int(p.partial_sold),
                     p.trade_mode,
                     str(p.stop_loss_price) if p.stop_loss_price is not None else None,
                     str(p.take_profit_price) if p.take_profit_price is not None else None,
                     user_id)
                    for market, p in account.positions.items()
                ],
            )
        await self._db.conn.commit()

    async def load_account(self, user_id: int) -> PaperAccount | None:
        cursor = await self._db.conn.execute(
            "SELECT cash_balance FROM account_state WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None

        cash_balance = Decimal(row[0])

        cursor = await self._db.conn.execute(
            "SELECT market, side, entry_price, quantity, entry_time, unrealized_pnl,"
            " highest_price, add_count, total_invested, partial_sold,"
            " trade_mode, stop_loss_price, take_profit_price FROM positions WHERE user_id = ?",
            (user_id,),
        )
        pos_rows = await cursor.fetchall()
        positions = {
            r[0]: Position(
                market=r[0],
                side=OrderSide(r[1]),
                entry_price=Decimal(r[2]),
                quantity=Decimal(r[3]),
                entry_time=int(r[4]),
                unrealized_pnl=Decimal(r[5]),
                highest_price=Decimal(r[6]),
                add_count=int(r[7]),
                total_invested=Decimal(r[8]),
                partial_sold=bool(r[9]),
                trade_mode=str(r[10]),
                stop_loss_price=Decimal(r[11]) if r[11] is not None else None,
                take_profit_price=Decimal(r[12]) if r[12] is not None else None,
            )
            for r in pos_rows
        }

        # Note: initial_balance is not stored in account_state,
        # it comes from user_settings. Use cash_balance as placeholder.
        return PaperAccount(
            initial_balance=cash_balance,
            cash_balance=cash_balance,
            positions=positions,
        )

    # ── Risk State Persistence ──

    async def save_risk_state(self, state: dict[str, object], user_id: int) -> None:
        now = int(time.time())
        await self._db.conn.execute(
            """INSERT INTO risk_state
               (user_id, consecutive_losses, cooldown_until, daily_loss, daily_trades, current_day, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 consecutive_losses=excluded.consecutive_losses,
                 cooldown_until=excluded.cooldown_until,
                 daily_loss=excluded.daily_loss,
                 daily_trades=excluded.daily_trades,
                 current_day=excluded.current_day,
                 updated_at=excluded.updated_at""",
            (user_id, state["consecutive_losses"], state["cooldown_until"],
             str(state["daily_loss"]), state["daily_trades"], state["current_day"], now),
        )
        await self._db.conn.commit()

    async def load_risk_state(self, user_id: int) -> dict[str, object] | None:
        cursor = await self._db.conn.execute(
            "SELECT consecutive_losses, cooldown_until, daily_loss, daily_trades, current_day"
            " FROM risk_state WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return {
            "consecutive_losses": int(row[0]),
            "cooldown_until": int(row[1]),
            "daily_loss": Decimal(row[2]),
            "daily_trades": int(row[3]),
            "current_day": str(row[4]),
        }

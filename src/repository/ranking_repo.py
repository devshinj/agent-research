from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from src.repository.database import Database
from src.types.models import RankingEntry


class RankingRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def get_ranking(self, requesting_user_id: int) -> list[RankingEntry]:
        conn = self._db.conn

        # Get active users with their initial_balance and current cash_balance
        cursor = await conn.execute(
            """
            SELECT u.id, u.nickname,
                   COALESCE(us.initial_balance, '0') AS initial_balance,
                   COALESCE(a.cash_balance, '0') AS cash_balance
            FROM users u
            LEFT JOIN user_settings us ON us.user_id = u.id
            LEFT JOIN account_state a ON a.user_id = u.id
            WHERE u.is_active = 1
            """
        )
        users = await cursor.fetchall()

        if not users:
            return []

        entries: list[RankingEntry] = []
        for row in users:
            uid, nickname, initial_str, cash_str = row
            initial_balance = Decimal(initial_str)
            cash_balance = Decimal(cash_str)

            # Get latest ending_balance from daily_summary
            cursor = await conn.execute(
                "SELECT ending_balance FROM daily_summary"
                " WHERE user_id = ? ORDER BY date DESC LIMIT 1",
                (uid,),
            )
            latest = await cursor.fetchone()
            if latest:
                total_equity = Decimal(latest[0])
            else:
                total_equity = cash_balance

            # Return percentage
            if initial_balance > 0:
                return_pct = (
                    (total_equity - initial_balance) / initial_balance * 100
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                return_pct = Decimal("0")

            # Aggregated trade stats from daily_summary
            cursor = await conn.execute(
                "SELECT COALESCE(SUM(total_trades), 0),"
                "       COALESCE(SUM(win_trades), 0),"
                "       COALESCE(SUM(loss_trades), 0),"
                "       COALESCE(MAX(max_drawdown_pct), '0')"
                " FROM daily_summary WHERE user_id = ?",
                (uid,),
            )
            stats = await cursor.fetchone()
            total_trades = int(stats[0])
            win_trades = int(stats[1])
            loss_trades = int(stats[2])
            max_drawdown_pct = Decimal(stats[3])

            total_decided = win_trades + loss_trades
            if total_decided > 0:
                win_rate = (
                    Decimal(win_trades) / Decimal(total_decided) * 100
                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            else:
                win_rate = Decimal("0")

            # Last 30 days of ending_balance for sparkline
            cursor = await conn.execute(
                "SELECT ending_balance FROM daily_summary"
                " WHERE user_id = ? ORDER BY date DESC LIMIT 30",
                (uid,),
            )
            equity_rows = await cursor.fetchall()
            daily_equities = tuple(
                Decimal(r[0]) for r in reversed(equity_rows)
            )

            entries.append(RankingEntry(
                rank=0,  # assigned after sorting
                user_id=uid,
                nickname=nickname,
                return_pct=return_pct,
                win_rate=win_rate,
                total_trades=total_trades,
                max_drawdown_pct=max_drawdown_pct,
                daily_equities=daily_equities,
                is_me=(uid == requesting_user_id),
            ))

        # Sort by return_pct descending, assign ranks
        entries.sort(key=lambda e: e.return_pct, reverse=True)
        ranked: list[RankingEntry] = []
        for i, entry in enumerate(entries, start=1):
            ranked.append(RankingEntry(
                rank=i,
                user_id=entry.user_id,
                nickname=entry.nickname,
                return_pct=entry.return_pct,
                win_rate=entry.win_rate,
                total_trades=entry.total_trades,
                max_drawdown_pct=entry.max_drawdown_pct,
                daily_equities=entry.daily_equities,
                is_me=entry.is_me,
            ))

        return ranked

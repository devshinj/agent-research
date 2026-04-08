from __future__ import annotations

import time
from decimal import Decimal
from typing import TYPE_CHECKING

from src.types.models import PaperAccount, PendingOrder

if TYPE_CHECKING:
    from src.repository.database import Database


class PendingOrderRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(self, order: PendingOrder, account: PaperAccount) -> None:
        """Insert pending order and deduct cash in a single transaction."""
        account.cash_balance -= order.amount_krw
        await self._db.conn.execute("BEGIN")
        try:
            await self._db.conn.execute(
                """INSERT INTO pending_orders
                   (id, user_id, market, side, limit_price, amount_krw,
                    status, created_at, expires_at, filled_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (order.id, order.user_id, order.market, order.side,
                 str(order.limit_price), str(order.amount_krw),
                 order.status, order.created_at, order.expires_at,
                 order.filled_at),
            )
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), order.user_id),
            )
            await self._db.conn.execute("COMMIT")
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance += order.amount_krw
            raise

    async def fill(self, order_id: str) -> bool:
        """Mark order as FILLED using CAS. Returns False if already processed."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """UPDATE pending_orders SET status = 'FILLED', filled_at = ?
               WHERE id = ? AND status = 'PENDING'""",
            (now, order_id),
        )
        await self._db.conn.commit()
        return cursor.rowcount > 0

    async def cancel(self, order_id: str, account: PaperAccount, user_id: int) -> bool:
        """Cancel order and refund cash in a single transaction."""
        cursor = await self._db.conn.execute(
            "SELECT amount_krw FROM pending_orders WHERE id = ? AND user_id = ? AND status = 'PENDING'",
            (order_id, user_id),
        )
        row = await cursor.fetchone()
        if not row:
            return False

        amount = Decimal(row[0])
        await self._db.conn.execute("BEGIN")
        try:
            cur = await self._db.conn.execute(
                """UPDATE pending_orders SET status = 'CANCELLED'
                   WHERE id = ? AND status = 'PENDING'""",
                (order_id,),
            )
            if cur.rowcount == 0:
                await self._db.conn.execute("ROLLBACK")
                return False
            account.cash_balance += amount
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), user_id),
            )
            await self._db.conn.execute("COMMIT")
            return True
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance -= amount
            raise

    async def expire_all(self, user_id: int, account: PaperAccount) -> int:
        """Expire all overdue PENDING orders for a user, refund cash."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """SELECT id, amount_krw FROM pending_orders
               WHERE user_id = ? AND status = 'PENDING' AND expires_at < ?""",
            (user_id, now),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0

        total_refund = sum(Decimal(r[1]) for r in rows)
        ids = [r[0] for r in rows]

        await self._db.conn.execute("BEGIN")
        try:
            placeholders = ",".join("?" for _ in ids)
            await self._db.conn.execute(
                f"""UPDATE pending_orders SET status = 'EXPIRED'
                    WHERE id IN ({placeholders}) AND status = 'PENDING'""",
                ids,
            )
            account.cash_balance += total_refund
            await self._db.conn.execute(
                """UPDATE account_state SET cash_balance = ?, updated_at = ?
                   WHERE user_id = ?""",
                (str(account.cash_balance), int(time.time()), user_id),
            )
            await self._db.conn.execute("COMMIT")
            return len(rows)
        except Exception:
            await self._db.conn.execute("ROLLBACK")
            account.cash_balance -= total_refund
            raise

    async def get_pending_by_user(self, user_id: int) -> list[PendingOrder]:
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE user_id = ? AND status = 'PENDING'
               ORDER BY created_at DESC""",
            (user_id,),
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    async def get_all_pending(self) -> list[PendingOrder]:
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE status = 'PENDING'"""
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    async def load_unexpired(self) -> list[PendingOrder]:
        """Load PENDING orders that haven't expired yet (for server restart recovery)."""
        now = int(time.time())
        cursor = await self._db.conn.execute(
            """SELECT id, user_id, market, side, limit_price, amount_krw,
                      status, created_at, expires_at, filled_at
               FROM pending_orders WHERE status = 'PENDING' AND expires_at >= ?""",
            (now,),
        )
        return [self._row_to_order(r) for r in await cursor.fetchall()]

    @staticmethod
    def _row_to_order(row: tuple) -> PendingOrder:  # type: ignore[type-arg]
        return PendingOrder(
            id=row[0], user_id=int(row[1]), market=row[2], side=row[3],
            limit_price=Decimal(row[4]), amount_krw=Decimal(row[5]),
            status=row[6], created_at=int(row[7]), expires_at=int(row[8]),
            filled_at=int(row[9]) if row[9] is not None else None,
        )

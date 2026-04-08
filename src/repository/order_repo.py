from __future__ import annotations

from decimal import Decimal

from src.repository.database import Database
from src.types.enums import OrderSide, OrderStatus, OrderType
from src.types.models import Order


class OrderRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, order: Order, user_id: int) -> None:
        await self._db.conn.execute(
            """INSERT INTO orders (id, market, side, order_type, price, fill_price,
               quantity, fee, status, signal_confidence, reason, created_at, filled_at, user_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 fill_price=excluded.fill_price, fee=excluded.fee,
                 status=excluded.status, filled_at=excluded.filled_at""",
            (order.id, order.market, order.side.value, order.order_type.value,
             str(order.price), str(order.fill_price) if order.fill_price else None,
             str(order.quantity), str(order.fee), order.status.value,
             order.signal_confidence, order.reason, order.created_at, order.filled_at, user_id),
        )
        await self._db.conn.commit()

    async def get_by_id(self, order_id: str) -> Order | None:
        cursor = await self._db.conn.execute(
            "SELECT * FROM orders WHERE id=?", (order_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return self._row_to_order(row)

    async def get_recent(self, user_id: int, limit: int = 10) -> list[Order]:
        cursor = await self._db.conn.execute(
            "SELECT * FROM orders WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [self._row_to_order(r) for r in rows]

    async def count_since(self, user_id: int, timestamp: int) -> int:
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM orders WHERE user_id = ? AND created_at >= ?",
            (user_id, timestamp),
        )
        row = await cursor.fetchone()
        return int(row[0]) if row else 0

    async def delete_older_than(self, timestamp: int) -> int:
        cursor = await self._db.conn.execute(
            "DELETE FROM orders WHERE created_at < ?", (timestamp,)
        )
        await self._db.conn.commit()
        return cursor.rowcount

    @staticmethod
    def _row_to_order(row: tuple) -> Order:  # type: ignore[type-arg]
        return Order(
            id=row[0], market=row[1], side=OrderSide(row[2]),
            order_type=OrderType(row[3]), price=Decimal(row[4]),
            fill_price=Decimal(row[5]) if row[5] else None,
            quantity=Decimal(row[6]), fee=Decimal(row[7]),
            status=OrderStatus(row[8]), signal_confidence=float(row[9]) if row[9] else 0.0,
            reason=row[10] or "", created_at=row[11],
            filled_at=row[12],
        )

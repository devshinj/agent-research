from __future__ import annotations

import time
from typing import Any

from src.repository.database import Database


class NotificationRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(
        self,
        user_id: int,
        market: str,
        action: str,
        result: str,
        reason: str,
        confidence: float | None = None,
    ) -> None:
        await self._db.conn.execute(
            """INSERT INTO trade_notifications
               (user_id, market, action, result, reason, confidence, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, market, action, result, reason, confidence, int(time.time())),
        )
        await self._db.conn.commit()

    async def get_list(
        self, user_id: int, limit: int = 50,
    ) -> list[dict[str, Any]]:
        cursor = await self._db.conn.execute(
            """SELECT id, market, action, result, reason, confidence, created_at, is_read
               FROM trade_notifications WHERE user_id=?
               ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        )
        rows = await cursor.fetchall()
        return [
            {
                "id": r[0], "market": r[1], "action": r[2],
                "result": r[3], "reason": r[4], "confidence": r[5],
                "created_at": r[6], "is_read": bool(r[7]),
            }
            for r in rows
        ]

    async def count_unread(self, user_id: int) -> int:
        cursor = await self._db.conn.execute(
            "SELECT COUNT(*) FROM trade_notifications WHERE user_id=? AND is_read=0",
            (user_id,),
        )
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def mark_all_read(self, user_id: int) -> None:
        await self._db.conn.execute(
            "UPDATE trade_notifications SET is_read=1 WHERE user_id=? AND is_read=0",
            (user_id,),
        )
        await self._db.conn.commit()

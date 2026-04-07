from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.repository.database import Database


class SignalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(
        self, market: str, signal_type: str, confidence: float, timestamp: int,
        basis: str | None = None,
    ) -> None:
        await self._db.conn.execute(
            "INSERT INTO signals (market, signal_type, confidence, timestamp, basis) "
            "VALUES (?, ?, ?, ?, ?)",
            (market, signal_type, confidence, timestamp, basis),
        )
        await self._db.conn.commit()

    async def get_recent(
        self, limit: int = 50, include_hold: bool = False,
    ) -> list[dict[str, object]]:
        if include_hold:
            cursor = await self._db.conn.execute(
                "SELECT market, signal_type, confidence, timestamp, basis "
                "FROM signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = await self._db.conn.execute(
                "SELECT market, signal_type, confidence, timestamp, basis "
                "FROM signals WHERE signal_type != 'HOLD' "
                "ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        rows = await cursor.fetchall()
        return [
            {
                "market": r[0],
                "signal_type": r[1],
                "confidence": r[2],
                "timestamp": r[3],
                "basis": r[4],
            }
            for r in rows
        ]

    async def get_stats_by_market(self, market: str) -> dict[str, object]:
        cursor = await self._db.conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN signal_type = 'HOLD' THEN 1 ELSE 0 END), "
            "  AVG(confidence) "
            "FROM signals WHERE market = ?",
            (market,),
        )
        row = await cursor.fetchone()
        if row is None or row[0] == 0:
            return {
                "total_signals": 0,
                "buy_count": 0,
                "sell_count": 0,
                "hold_count": 0,
                "avg_confidence": 0.0,
            }
        return {
            "total_signals": row[0],
            "buy_count": row[1],
            "sell_count": row[2],
            "hold_count": row[3],
            "avg_confidence": round(row[4], 4),
        }

from __future__ import annotations

from decimal import Decimal

from src.repository.database import Database
from src.types.models import Candle


class CandleRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, candle: Candle) -> None:
        await self._db.conn.execute(
            """INSERT INTO candles (market, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(market, timeframe, timestamp) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            (candle.market, candle.timeframe, candle.timestamp,
             str(candle.open), str(candle.high), str(candle.low),
             str(candle.close), str(candle.volume)),
        )
        await self._db.conn.commit()

    async def save_many(self, candles: list[Candle]) -> None:
        await self._db.conn.executemany(
            """INSERT INTO candles (market, timeframe, timestamp, open, high, low, close, volume)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(market, timeframe, timestamp) DO UPDATE SET
                 open=excluded.open, high=excluded.high, low=excluded.low,
                 close=excluded.close, volume=excluded.volume""",
            [(c.market, c.timeframe, c.timestamp,
              str(c.open), str(c.high), str(c.low),
              str(c.close), str(c.volume)) for c in candles],
        )
        await self._db.conn.commit()

    async def get_latest(self, market: str, timeframe: str, limit: int = 200) -> list[Candle]:
        cursor = await self._db.conn.execute(
            """SELECT market, timeframe, timestamp, open, high, low, close, volume
               FROM candles WHERE market=? AND timeframe=?
               ORDER BY timestamp DESC LIMIT ?""",
            (market, timeframe, limit),
        )
        rows = await cursor.fetchall()
        return [
            Candle(
                market=r[0], timeframe=r[1], timestamp=r[2],
                open=Decimal(r[3]), high=Decimal(r[4]), low=Decimal(r[5]),
                close=Decimal(r[6]), volume=Decimal(r[7]),
            )
            for r in rows
        ]

    async def delete_older_than(self, timestamp: int) -> int:
        cursor = await self._db.conn.execute(
            "DELETE FROM candles WHERE timestamp < ?", (timestamp,)
        )
        await self._db.conn.commit()
        return cursor.rowcount

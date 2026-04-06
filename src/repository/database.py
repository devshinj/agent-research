from __future__ import annotations

import aiosqlite

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candles (
    market     TEXT NOT NULL,
    timeframe  TEXT NOT NULL,
    timestamp  INTEGER NOT NULL,
    open       TEXT NOT NULL,
    high       TEXT NOT NULL,
    low        TEXT NOT NULL,
    close      TEXT NOT NULL,
    volume     TEXT NOT NULL,
    PRIMARY KEY (market, timeframe, timestamp)
);

CREATE TABLE IF NOT EXISTS orders (
    id                TEXT PRIMARY KEY,
    market            TEXT NOT NULL,
    side              TEXT NOT NULL,
    order_type        TEXT NOT NULL,
    price             TEXT NOT NULL,
    fill_price        TEXT,
    quantity          TEXT NOT NULL,
    fee               TEXT NOT NULL,
    status            TEXT NOT NULL,
    signal_confidence REAL,
    reason            TEXT,
    created_at        INTEGER NOT NULL,
    filled_at         INTEGER
);

CREATE TABLE IF NOT EXISTS daily_summary (
    date             TEXT PRIMARY KEY,
    starting_balance TEXT NOT NULL,
    ending_balance   TEXT NOT NULL,
    realized_pnl     TEXT NOT NULL,
    total_trades     INTEGER NOT NULL,
    win_trades       INTEGER NOT NULL,
    loss_trades      INTEGER NOT NULL,
    max_drawdown_pct TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS screening_log (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp  INTEGER NOT NULL,
    market     TEXT NOT NULL,
    volume_krw TEXT NOT NULL,
    volatility TEXT NOT NULL,
    score      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS account_state (
    id            INTEGER PRIMARY KEY CHECK (id = 1),
    cash_balance  TEXT NOT NULL,
    updated_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    market         TEXT PRIMARY KEY,
    side           TEXT NOT NULL,
    entry_price    TEXT NOT NULL,
    quantity       TEXT NOT NULL,
    entry_time     INTEGER NOT NULL,
    unrealized_pnl TEXT NOT NULL,
    highest_price  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_state (
    id                  INTEGER PRIMARY KEY CHECK (id = 1),
    consecutive_losses  INTEGER NOT NULL,
    cooldown_until      INTEGER NOT NULL,
    daily_loss          TEXT NOT NULL,
    daily_trades        INTEGER NOT NULL,
    current_day         TEXT NOT NULL,
    updated_at          INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    timestamp   INTEGER NOT NULL,
    outcome     TEXT
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._conn = await aiosqlite.connect(self._db_path, isolation_level=None)
        await self._conn.executescript(SCHEMA_SQL)
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA busy_timeout=5000")

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    async def reset_trading_data(self) -> None:
        """Delete all trading data. Preserves candles and screening_log."""
        await self.conn.executescript(
            "DELETE FROM orders;"
            "DELETE FROM positions;"
            "DELETE FROM account_state;"
            "DELETE FROM daily_summary;"
            "DELETE FROM risk_state;"
            "DELETE FROM signals;"
        )
        await self.conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

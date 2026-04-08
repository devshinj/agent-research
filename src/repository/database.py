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
    date             TEXT NOT NULL,
    starting_balance TEXT NOT NULL,
    ending_balance   TEXT NOT NULL,
    realized_pnl     TEXT NOT NULL,
    total_trades     INTEGER NOT NULL,
    win_trades       INTEGER NOT NULL,
    loss_trades      INTEGER NOT NULL,
    max_drawdown_pct TEXT NOT NULL,
    user_id          INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (date, user_id)
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
    user_id       INTEGER PRIMARY KEY,
    cash_balance  TEXT NOT NULL,
    updated_at    INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS positions (
    market            TEXT PRIMARY KEY,
    side              TEXT NOT NULL,
    entry_price       TEXT NOT NULL,
    quantity          TEXT NOT NULL,
    entry_time        INTEGER NOT NULL,
    unrealized_pnl    TEXT NOT NULL,
    highest_price     TEXT NOT NULL,
    add_count         INTEGER NOT NULL DEFAULT 0,
    total_invested    TEXT NOT NULL DEFAULT '0',
    partial_sold      INTEGER NOT NULL DEFAULT 0,
    trade_mode        TEXT NOT NULL DEFAULT 'AUTO',
    stop_loss_price   TEXT,
    take_profit_price TEXT
);

CREATE TABLE IF NOT EXISTS risk_state (
    user_id              INTEGER PRIMARY KEY,
    consecutive_losses   INTEGER NOT NULL,
    cooldown_until       INTEGER NOT NULL,
    daily_loss           TEXT NOT NULL,
    daily_trades         INTEGER NOT NULL,
    current_day          TEXT NOT NULL,
    updated_at           INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    timestamp   INTEGER NOT NULL,
    outcome     TEXT,
    basis       TEXT
);

CREATE TABLE IF NOT EXISTS users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname      TEXT NOT NULL,
    is_admin      INTEGER NOT NULL DEFAULT 0,
    is_active     INTEGER NOT NULL DEFAULT 1,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id              INTEGER PRIMARY KEY REFERENCES users(id),
    initial_balance      TEXT NOT NULL DEFAULT '0',
    max_position_pct     TEXT NOT NULL DEFAULT '0.25',
    max_open_positions   INTEGER NOT NULL DEFAULT 4,
    stop_loss_pct        TEXT NOT NULL DEFAULT '0.03',
    take_profit_pct      TEXT NOT NULL DEFAULT '0.08',
    trailing_stop_pct    TEXT NOT NULL DEFAULT '0.015',
    max_daily_loss_pct   TEXT NOT NULL DEFAULT '0.05',
    trading_enabled      INTEGER NOT NULL DEFAULT 0
);
"""


class Database:
    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._conn: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        conn = await aiosqlite.connect(self._db_path, isolation_level=None)
        try:
            await conn.executescript(SCHEMA_SQL)
            await conn.execute("PRAGMA journal_mode=WAL")
            await conn.execute("PRAGMA busy_timeout=5000")
            self._conn = conn
            await self._migrate()
        except Exception:
            await conn.close()
            self._conn = None
            raise

    async def _migrate(self) -> None:
        """Add missing columns to existing tables."""
        assert self._conn is not None

        # positions table migrations
        cursor = await self._conn.execute("PRAGMA table_info(positions)")
        pos_cols = {row[1] for row in await cursor.fetchall()}
        pos_migrations = [
            ("add_count", "ALTER TABLE positions ADD COLUMN add_count INTEGER NOT NULL DEFAULT 0"),
            ("total_invested", "ALTER TABLE positions ADD COLUMN total_invested TEXT NOT NULL DEFAULT '0'"),
            ("partial_sold", "ALTER TABLE positions ADD COLUMN partial_sold INTEGER NOT NULL DEFAULT 0"),
            ("trade_mode", "ALTER TABLE positions ADD COLUMN trade_mode TEXT NOT NULL DEFAULT 'AUTO'"),
            ("stop_loss_price", "ALTER TABLE positions ADD COLUMN stop_loss_price TEXT"),
            ("take_profit_price", "ALTER TABLE positions ADD COLUMN take_profit_price TEXT"),
        ]
        for col_name, sql in pos_migrations:
            if col_name not in pos_cols:
                await self._conn.execute(sql)

        # signals table migrations
        cursor = await self._conn.execute("PRAGMA table_info(signals)")
        sig_cols = {row[1] for row in await cursor.fetchall()}
        sig_migrations = [
            ("basis", "ALTER TABLE signals ADD COLUMN basis TEXT"),
        ]
        for col_name, sql in sig_migrations:
            if col_name not in sig_cols:
                await self._conn.execute(sql)

        # Multi-user migration: add user_id to tenant tables
        tenant_tables = {
            "orders": "user_id INTEGER NOT NULL DEFAULT 1",
            "positions": "user_id INTEGER NOT NULL DEFAULT 1",
            "account_state": "user_id INTEGER NOT NULL DEFAULT 1",
            "daily_summary": "user_id INTEGER NOT NULL DEFAULT 1",
            "risk_state": "user_id INTEGER NOT NULL DEFAULT 1",
        }
        for table, col_def in tenant_tables.items():
            cursor = await self._conn.execute(f"PRAGMA table_info({table})")
            columns = [row[1] for row in await cursor.fetchall()]
            if "user_id" not in columns:
                await self._conn.execute(
                    f"ALTER TABLE {table} ADD COLUMN {col_def}"
                )

        # Remove CHECK(id=1) singleton constraint from account_state and risk_state
        # by recreating tables without the constraint (SQLite doesn't support DROP CHECK)
        cursor = await self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='account_state'"
        )
        row = await cursor.fetchone()
        if row and "CHECK" in row[0]:
            await self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS account_state_new (
                    user_id       INTEGER PRIMARY KEY,
                    cash_balance  TEXT NOT NULL,
                    updated_at    INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO account_state_new (user_id, cash_balance, updated_at)
                    SELECT user_id, cash_balance, updated_at FROM account_state;
                DROP TABLE account_state;
                ALTER TABLE account_state_new RENAME TO account_state;
            """)

        cursor = await self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='risk_state'"
        )
        row = await cursor.fetchone()
        if row and "CHECK" in row[0]:
            await self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS risk_state_new (
                    user_id              INTEGER PRIMARY KEY,
                    consecutive_losses   INTEGER NOT NULL,
                    cooldown_until       INTEGER NOT NULL,
                    daily_loss           TEXT NOT NULL,
                    daily_trades         INTEGER NOT NULL,
                    current_day          TEXT NOT NULL,
                    updated_at           INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO risk_state_new
                    (user_id, consecutive_losses, cooldown_until, daily_loss,
                     daily_trades, current_day, updated_at)
                    SELECT user_id, consecutive_losses, cooldown_until, daily_loss,
                           daily_trades, current_day, updated_at
                    FROM risk_state;
                DROP TABLE risk_state;
                ALTER TABLE risk_state_new RENAME TO risk_state;
            """)

        # Migrate daily_summary: change PRIMARY KEY from (date) to (date, user_id)
        cursor = await self._conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='daily_summary'"
        )
        row = await cursor.fetchone()
        if row and "PRIMARY KEY (date," not in row[0] and '"date" TEXT PRIMARY KEY' not in row[0].replace("date TEXT PRIMARY KEY", '"date" TEXT PRIMARY KEY'):
            # Check if it still has date as sole primary key (old schema)
            tbl_sql: str = row[0]
            if "PRIMARY KEY (date, user_id)" not in tbl_sql:
                await self._conn.executescript("""
                    CREATE TABLE IF NOT EXISTS daily_summary_new (
                        date             TEXT NOT NULL,
                        starting_balance TEXT NOT NULL,
                        ending_balance   TEXT NOT NULL,
                        realized_pnl     TEXT NOT NULL,
                        total_trades     INTEGER NOT NULL,
                        win_trades       INTEGER NOT NULL,
                        loss_trades      INTEGER NOT NULL,
                        max_drawdown_pct TEXT NOT NULL,
                        user_id          INTEGER NOT NULL DEFAULT 1,
                        PRIMARY KEY (date, user_id)
                    );
                    INSERT OR IGNORE INTO daily_summary_new
                        (date, starting_balance, ending_balance, realized_pnl,
                         total_trades, win_trades, loss_trades, max_drawdown_pct, user_id)
                        SELECT date, starting_balance, ending_balance, realized_pnl,
                               total_trades, win_trades, loss_trades, max_drawdown_pct, user_id
                        FROM daily_summary;
                    DROP TABLE daily_summary;
                    ALTER TABLE daily_summary_new RENAME TO daily_summary;
                """)

        # ── Reset initial_balance default from 5000000 to 0 ──
        await self._conn.execute(
            "UPDATE user_settings SET initial_balance = '0'"
            " WHERE initial_balance = '5000000'"
        )

        # ── balance_ledger table ──
        await self._conn.execute("""
            CREATE TABLE IF NOT EXISTS balance_ledger (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL REFERENCES users(id),
                admin_id   INTEGER NOT NULL REFERENCES users(id),
                amount     TEXT NOT NULL,
                balance_after TEXT NOT NULL,
                memo       TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database not initialized. Call initialize() first.")
        return self._conn

    async def delete_screening_log_older_than(self, timestamp: int) -> int:
        cursor = await self.conn.execute(
            "DELETE FROM screening_log WHERE timestamp < ?", (timestamp,)
        )
        await self.conn.commit()
        return cursor.rowcount

    async def reset_trading_data(self, user_id: int | None = None) -> None:
        """Delete all trading data. Preserves candles and screening_log."""
        tables = ["orders", "positions", "account_state",
                  "daily_summary", "risk_state", "signals"]
        for table in tables:
            if user_id is not None and table != "signals":
                await self.conn.execute(
                    f"DELETE FROM {table} WHERE user_id = ?", (user_id,)
                )
            else:
                await self.conn.execute(f"DELETE FROM {table}")
        await self.conn.commit()

    async def close(self) -> None:
        if self._conn:
            await self._conn.close()
            self._conn = None

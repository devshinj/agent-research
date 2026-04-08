from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from src.repository.database import Database

_SETTINGS_FIELDS = (
    "initial_balance", "max_position_pct", "max_open_positions",
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    "max_daily_loss_pct", "trading_enabled",
)


class UserRepo:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def create(
        self, *, email: str, password_hash: str, nickname: str,
    ) -> dict:
        conn = self._db.conn
        # Check duplicate
        cursor = await conn.execute(
            "SELECT id FROM users WHERE email = ?", (email,)
        )
        if await cursor.fetchone():
            raise ValueError(f"Duplicate email: {email}")

        # First user becomes admin
        cursor = await conn.execute("SELECT COUNT(*) FROM users")
        count = (await cursor.fetchone())[0]
        is_admin = 1 if count == 0 else 0

        now = datetime.now(UTC).isoformat()
        cursor = await conn.execute(
            "INSERT INTO users (email, password_hash, nickname, is_admin, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (email, password_hash, nickname, is_admin, now),
        )
        user_id = cursor.lastrowid
        await conn.commit()

        # Create default settings
        await conn.execute(
            "INSERT INTO user_settings (user_id) VALUES (?)", (user_id,)
        )
        # Create default account_state (user_id is PK after migration)
        await conn.execute(
            "INSERT OR IGNORE INTO account_state (user_id, cash_balance, updated_at)"
            " VALUES (?, '5000000', ?)",
            (user_id, now),
        )
        # Create default risk_state (user_id is PK after migration)
        await conn.execute(
            "INSERT OR IGNORE INTO risk_state"
            " (user_id, consecutive_losses, cooldown_until, daily_loss,"
            "  daily_trades, current_day, updated_at)"
            " VALUES (?, 0, 0, '0', 0, ?, ?)",
            (user_id, now[:10], now),
        )
        await conn.commit()

        return {
            "id": user_id, "email": email, "nickname": nickname,
            "is_admin": is_admin, "is_active": 1, "created_at": now,
        }

    async def get_by_email(self, email: str) -> dict | None:
        cursor = await self._db.conn.execute(
            "SELECT id, email, password_hash, nickname, is_admin, is_active, created_at"
            " FROM users WHERE email = ?",
            (email,),
        )
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def get_by_id(self, user_id: int) -> dict | None:
        cursor = await self._db.conn.execute(
            "SELECT id, email, password_hash, nickname, is_admin, is_active, created_at"
            " FROM users WHERE id = ?",
            (user_id,),
        )
        row = await cursor.fetchone()
        return self._row_to_dict(row) if row else None

    async def list_all(self) -> list[dict]:
        cursor = await self._db.conn.execute(
            "SELECT id, email, password_hash, nickname, is_admin, is_active, created_at"
            " FROM users ORDER BY id"
        )
        return [self._row_to_dict(row) for row in await cursor.fetchall()]

    async def get_cash_balance(self, user_id: int) -> Decimal:
        cursor = await self._db.conn.execute(
            "SELECT cash_balance FROM account_state WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            raise ValueError(f"account_state not found for user_id={user_id}")
        return Decimal(row[0])

    async def adjust_balance(
        self, *, user_id: int, admin_id: int, amount: Decimal, memo: str = ""
    ) -> dict:
        if amount == Decimal("0"):
            raise ValueError("금액은 0이 될 수 없습니다")
        current = await self.get_cash_balance(user_id)
        new_balance = current + amount
        if new_balance < Decimal("0"):
            raise ValueError("잔고 부족: 차감 후 잔고가 음수가 됩니다")
        now = datetime.now(UTC).isoformat()
        conn = self._db.conn
        await conn.execute(
            "UPDATE account_state SET cash_balance = ?, updated_at = ? WHERE user_id = ?",
            (str(new_balance), now, user_id),
        )
        await conn.execute(
            "INSERT INTO balance_ledger (user_id, admin_id, amount, balance_after, memo, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, admin_id, str(amount), str(new_balance), memo, now),
        )
        await conn.commit()
        return {
            "user_id": user_id,
            "balance_before": current,
            "balance_after": new_balance,
            "amount": amount,
        }

    async def get_balance_history(self, user_id: int) -> list[dict]:
        cursor = await self._db.conn.execute(
            "SELECT bl.id, bl.admin_id, u.nickname AS admin_nickname,"
            " bl.amount, bl.balance_after, bl.memo, bl.created_at"
            " FROM balance_ledger bl"
            " JOIN users u ON u.id = bl.admin_id"
            " WHERE bl.user_id = ?"
            " ORDER BY bl.id DESC",
            (user_id,),
        )
        rows = await cursor.fetchall()
        keys = ("id", "admin_id", "admin_nickname", "amount", "balance_after", "memo", "created_at")
        return [dict(zip(keys, row, strict=False)) for row in rows]

    async def set_active(self, user_id: int, active: bool) -> None:
        await self._db.conn.execute(
            "UPDATE users SET is_active = ? WHERE id = ?",
            (1 if active else 0, user_id),
        )
        await self._db.conn.commit()

    async def get_active_user_ids(self) -> list[int]:
        cursor = await self._db.conn.execute(
            "SELECT id FROM users WHERE is_active = 1 ORDER BY id"
        )
        return [row[0] for row in await cursor.fetchall()]

    async def get_settings(self, user_id: int) -> dict:
        cursor = await self._db.conn.execute(
            "SELECT * FROM user_settings WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return {}
        desc = [d[0] for d in cursor.description]
        return dict(zip(desc, row))

    async def update_settings(self, user_id: int, patches: dict) -> None:
        allowed = set(_SETTINGS_FIELDS)
        sets = []
        values = []
        for k, v in patches.items():
            if k in allowed:
                sets.append(f"{k} = ?")
                values.append(v)
        if not sets:
            return
        values.append(user_id)
        await self._db.conn.execute(
            f"UPDATE user_settings SET {', '.join(sets)} WHERE user_id = ?",
            values,
        )
        await self._db.conn.commit()

    @staticmethod
    def _row_to_dict(row: tuple) -> dict:
        keys = (
            "id", "email", "password_hash", "nickname",
            "is_admin", "is_active", "created_at",
        )
        return dict(zip(keys, row))

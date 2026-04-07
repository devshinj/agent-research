# Multi-User Deployment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 단일 사용자 로컬 앱을 멀티유저 서버 배포 가능한 시스템으로 전환한다.

**Architecture:** SQLite 유지 + 기존 테이블에 user_id 추가하여 멀티테넌트 구현. JWT 인증 미들웨어로 전 API 보호. 시장 데이터/ML은 공유, 매매 설정/포트폴리오만 사용자별 분리. Docker Compose로 배포 (FastAPI + Nginx/React).

**Tech Stack:** bcrypt (비밀번호), PyJWT (토큰), FastAPI Depends (인증 미들웨어), Docker multi-stage build, Nginx (SSL + reverse proxy)

---

## File Structure

### 새로 생성하는 파일

| 파일 | 역할 |
|------|------|
| `src/repository/user_repo.py` | 사용자 CRUD (users, user_settings 테이블) |
| `src/ui/api/auth.py` | JWT 생성/검증, 인증 의존성 (get_current_user) |
| `src/ui/api/routes/auth.py` | 회원가입/로그인/refresh 엔드포인트 |
| `src/ui/api/routes/admin.py` | 관리자 전용: 사용자 목록/활성화 |
| `src/ui/frontend/src/hooks/useAuth.ts` | 인증 상태 관리, 토큰 자동 refresh |
| `src/ui/frontend/src/pages/Login.tsx` | 로그인 페이지 |
| `src/ui/frontend/src/pages/Register.tsx` | 회원가입 페이지 |
| `deploy/Dockerfile` | 멀티스테이지 빌드 (py-builder, web-builder, web, app) |
| `deploy/docker-compose.yml` | app + web 컨테이너 |
| `deploy/nginx/default.conf` | Nginx 설정 (SSL, 프록시, SPA) |
| `deploy/ssl/generate-cert.sh` | 자체 서명 인증서 생성 |
| `deploy/.env.example` | 환경변수 템플릿 |
| `deploy/docker-build-guide.md` | 빌드/배포 가이드 |

### 수정하는 파일

| 파일 | 변경 내용 |
|------|-----------|
| `src/repository/database.py` | users, user_settings 테이블 추가, 기존 테이블에 user_id 컬럼 마이그레이션 |
| `src/repository/order_repo.py` | 모든 메서드에 user_id 파라미터 추가 |
| `src/repository/portfolio_repo.py` | user_id 기반 계좌/포지션/일일요약 분리 |
| `src/types/models.py` | PaperAccount에 user_id 필드 추가 |
| `src/runtime/app.py` | user_accounts dict, user_risk dict, _on_signal 멀티유저 분기 |
| `src/ui/api/server.py` | 인증 미들웨어, auth/admin 라우터 등록 |
| `src/ui/api/routes/dashboard.py` | user_id 기반 데이터 조회 |
| `src/ui/api/routes/portfolio.py` | user_id 기반 데이터 조회 |
| `src/ui/api/routes/exchange.py` | user_id 기반 매매 실행 |
| `src/ui/api/routes/control.py` | 사용자별 trading_enabled, 관리자 전용 글로벌 설정 |
| `src/ui/api/routes/risk.py` | user_id 기반 리스크 상태 |
| `src/ui/frontend/src/App.tsx` | 인증 가드, useAuth 통합, 로그아웃 |
| `src/ui/frontend/src/hooks/useApi.ts` | Authorization 헤더 자동 첨부, 401 처리 |
| `src/ui/frontend/src/hooks/useWebSocket.ts` | 토큰 쿼리 파라미터 추가 |
| `src/ui/frontend/src/pages/System.tsx` | 사용자별 설정 수정, 관리자 사용자 관리 탭 |
| `src/config/settings.py` | AuthConfig 추가 (invite_code 등 환경변수 오버라이드) |
| `config/settings.yaml` | auth 섹션 추가 |
| `pyproject.toml` | bcrypt, PyJWT 의존성 추가 |

---

## Task 1: Python 의존성 추가

**Files:**
- Modify: `pyproject.toml:8-24`

- [ ] **Step 1: 의존성 추가**

`pyproject.toml`의 dependencies에 추가:

```toml
bcrypt>=4.2
PyJWT>=2.9
```

- [ ] **Step 2: 설치 확인**

Run: `uv sync`
Expected: 성공적으로 설치

- [ ] **Step 3: 커밋**

```bash
git add pyproject.toml uv.lock
git commit -m "deps: add bcrypt and PyJWT for authentication"
```

---

## Task 2: DB 스키마 변경 — users, user_settings 테이블 및 기존 테이블 user_id 마이그레이션

**Files:**
- Modify: `src/repository/database.py`

- [ ] **Step 1: SCHEMA_SQL에 users, user_settings 테이블 추가**

`src/repository/database.py`의 SCHEMA_SQL 문자열 끝에 추가:

```sql
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    nickname TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS user_settings (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    initial_balance TEXT NOT NULL DEFAULT '5000000',
    max_position_pct TEXT NOT NULL DEFAULT '0.25',
    max_open_positions INTEGER NOT NULL DEFAULT 4,
    stop_loss_pct TEXT NOT NULL DEFAULT '0.03',
    take_profit_pct TEXT NOT NULL DEFAULT '0.08',
    trailing_stop_pct TEXT NOT NULL DEFAULT '0.015',
    max_daily_loss_pct TEXT NOT NULL DEFAULT '0.05',
    trading_enabled INTEGER NOT NULL DEFAULT 0
);
```

- [ ] **Step 2: 기존 테이블에 user_id 컬럼 마이그레이션 추가**

`_migrate()` 메서드에 추가. 기존 마이그레이션(라인 110-137) 뒤에:

```python
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
```

- [ ] **Step 3: account_state PK 변경 처리**

기존 account_state는 `id=1` 싱글톤이므로, 마이그레이션에서 user_id를 추가한 후 기존 레코드의 user_id=1로 설정됨 (DEFAULT 1). 이후 코드에서 `WHERE user_id = ?` 로 쿼리.

positions 테이블도 마찬가지: 기존 PK가 `market`이었으나, user_id 추가 후 `WHERE user_id = ? AND market = ?` 로 쿼리.

- [ ] **Step 4: reset_trading_data에 user_id 파라미터 추가**

```python
async def reset_trading_data(self, user_id: int | None = None) -> None:
    tables = ["orders", "positions", "account_state",
              "daily_summary", "risk_state", "signals"]
    for table in tables:
        if user_id is not None and table != "signals":
            await self._conn.execute(
                f"DELETE FROM {table} WHERE user_id = ?", (user_id,)
            )
        else:
            await self._conn.execute(f"DELETE FROM {table}")
    await self._conn.commit()
```

- [ ] **Step 5: 커밋**

```bash
git add src/repository/database.py
git commit -m "schema: add users/user_settings tables, add user_id to tenant tables"
```

---

## Task 3: User Repository 생성

**Files:**
- Create: `src/repository/user_repo.py`
- Create: `tests/unit/test_user_repo.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_user_repo.py
import pytest
import pytest_asyncio
from src.repository.database import Database
from src.repository.user_repo import UserRepo


@pytest_asyncio.fixture
async def repo(tmp_path):
    db = Database(str(tmp_path / "test.db"))
    await db.initialize()
    repo = UserRepo(db)
    yield repo
    await db.close()


@pytest.mark.asyncio
async def test_create_and_get_user(repo: UserRepo):
    user = await repo.create(
        email="test@example.com",
        password_hash="hashed_pw",
        nickname="tester",
    )
    assert user["id"] == 1
    assert user["email"] == "test@example.com"
    assert user["is_admin"] == 0

    fetched = await repo.get_by_email("test@example.com")
    assert fetched is not None
    assert fetched["nickname"] == "tester"


@pytest.mark.asyncio
async def test_first_user_is_admin(repo: UserRepo):
    user = await repo.create(
        email="admin@example.com",
        password_hash="hashed",
        nickname="admin",
    )
    assert user["is_admin"] == 1

    user2 = await repo.create(
        email="user2@example.com",
        password_hash="hashed",
        nickname="user2",
    )
    assert user2["is_admin"] == 0


@pytest.mark.asyncio
async def test_duplicate_email_raises(repo: UserRepo):
    await repo.create(email="dup@test.com", password_hash="h", nickname="a")
    with pytest.raises(ValueError, match="email"):
        await repo.create(email="dup@test.com", password_hash="h", nickname="b")


@pytest.mark.asyncio
async def test_get_settings_defaults(repo: UserRepo):
    user = await repo.create(email="s@t.com", password_hash="h", nickname="s")
    settings = await repo.get_settings(user["id"])
    assert settings["initial_balance"] == "5000000"
    assert settings["max_open_positions"] == 4
    assert settings["trading_enabled"] == 0


@pytest.mark.asyncio
async def test_update_settings(repo: UserRepo):
    user = await repo.create(email="s@t.com", password_hash="h", nickname="s")
    await repo.update_settings(user["id"], {"stop_loss_pct": "0.05"})
    settings = await repo.get_settings(user["id"])
    assert settings["stop_loss_pct"] == "0.05"


@pytest.mark.asyncio
async def test_list_users(repo: UserRepo):
    await repo.create(email="a@t.com", password_hash="h", nickname="a")
    await repo.create(email="b@t.com", password_hash="h", nickname="b")
    users = await repo.list_all()
    assert len(users) == 2


@pytest.mark.asyncio
async def test_set_active(repo: UserRepo):
    user = await repo.create(email="a@t.com", password_hash="h", nickname="a")
    await repo.set_active(user["id"], False)
    fetched = await repo.get_by_id(user["id"])
    assert fetched["is_active"] == 0


@pytest.mark.asyncio
async def test_get_all_active_user_ids(repo: UserRepo):
    u1 = await repo.create(email="a@t.com", password_hash="h", nickname="a")
    u2 = await repo.create(email="b@t.com", password_hash="h", nickname="b")
    await repo.set_active(u2["id"], False)
    active = await repo.get_active_user_ids()
    assert active == [u1["id"]]
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_user_repo.py -v`
Expected: FAIL (user_repo 모듈 없음)

- [ ] **Step 3: UserRepo 구현**

```python
# src/repository/user_repo.py
from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone

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

        now = datetime.now(timezone.utc).isoformat()
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
        # Create default account_state
        await conn.execute(
            "INSERT OR IGNORE INTO account_state (user_id, cash_balance, updated_at)"
            " VALUES (?, '5000000', ?)",
            (user_id, now),
        )
        # Create default risk_state
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
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_user_repo.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/repository/user_repo.py tests/unit/test_user_repo.py
git commit -m "feat: add UserRepo with CRUD, settings, and active user management"
```

---

## Task 4: JWT 인증 모듈 생성

**Files:**
- Create: `src/ui/api/auth.py`
- Create: `tests/unit/test_auth.py`

- [ ] **Step 1: 테스트 작성**

```python
# tests/unit/test_auth.py
import pytest
from datetime import timedelta
from src.ui.api.auth import create_access_token, create_refresh_token, decode_token


def test_create_and_decode_access_token():
    token = create_access_token(
        user_id=1, secret="test-secret", expires_delta=timedelta(minutes=30)
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == 1
    assert payload["type"] == "access"


def test_create_and_decode_refresh_token():
    token = create_refresh_token(
        user_id=1, secret="test-secret", expires_delta=timedelta(days=7)
    )
    payload = decode_token(token, secret="test-secret")
    assert payload["sub"] == 1
    assert payload["type"] == "refresh"


def test_expired_token():
    token = create_access_token(
        user_id=1, secret="s", expires_delta=timedelta(seconds=-1)
    )
    with pytest.raises(ValueError, match="expired"):
        decode_token(token, secret="s")


def test_invalid_secret():
    token = create_access_token(
        user_id=1, secret="s1", expires_delta=timedelta(minutes=30)
    )
    with pytest.raises(ValueError):
        decode_token(token, secret="wrong")
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: FAIL

- [ ] **Step 3: auth 모듈 구현**

```python
# src/ui/api/auth.py
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request

JWT_SECRET = os.environ.get("JWT_SECRET", "change-me-in-production")
INVITE_CODE = os.environ.get("INVITE_CODE", "")
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "")

ACCESS_TOKEN_EXPIRE = timedelta(minutes=30)
REFRESH_TOKEN_EXPIRE = timedelta(days=7)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_access_token(
    user_id: int,
    secret: str = JWT_SECRET,
    expires_delta: timedelta = ACCESS_TOKEN_EXPIRE,
) -> str:
    payload = {
        "sub": user_id,
        "type": "access",
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    user_id: int,
    secret: str = JWT_SECRET,
    expires_delta: timedelta = REFRESH_TOKEN_EXPIRE,
) -> str:
    payload = {
        "sub": user_id,
        "type": "refresh",
        "exp": datetime.now(timezone.utc) + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str = JWT_SECRET) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        raise ValueError("Token expired")
    except jwt.InvalidTokenError:
        raise ValueError("Invalid token")
    return payload


async def get_current_user(request: Request) -> dict:
    """FastAPI dependency: extract and validate JWT from Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing token")

    token = auth_header[7:]
    try:
        payload = decode_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    return user


async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if not user["is_admin"]:
        raise HTTPException(status_code=403, detail="Admin required")
    return user
```

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/unit/test_auth.py -v`
Expected: ALL PASS

- [ ] **Step 5: 커밋**

```bash
git add src/ui/api/auth.py tests/unit/test_auth.py
git commit -m "feat: add JWT auth module with password hashing and FastAPI dependencies"
```

---

## Task 5: Auth API 라우터 생성

**Files:**
- Create: `src/ui/api/routes/auth.py`

- [ ] **Step 1: auth 라우터 구현**

```python
# src/ui/api/routes/auth.py
from __future__ import annotations

from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, HTTPException, Request

from src.ui.api.auth import (
    INVITE_CODE,
    hash_password,
    verify_password,
    create_access_token,
    create_refresh_token,
    decode_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str
    invite_code: str


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    if not INVITE_CODE or body.invite_code != INVITE_CODE:
        raise HTTPException(status_code=400, detail="Invalid invite code")

    if len(body.password) < 8:
        raise HTTPException(
            status_code=400, detail="Password must be at least 8 characters"
        )

    app = request.app.state.app
    try:
        user = await app.user_repo.create(
            email=body.email,
            password_hash=hash_password(body.password),
            nickname=body.nickname,
        )
    except ValueError:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Initialize user account in the running app
    await app.load_user(user["id"])

    return {
        "id": user["id"],
        "email": user["email"],
        "nickname": user["nickname"],
    }


@router.post("/login")
async def login(body: LoginRequest, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_email(body.email)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    if not user["is_active"]:
        raise HTTPException(status_code=403, detail="Account is deactivated")

    if not verify_password(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(user["id"])
    refresh_token = create_refresh_token(user["id"])

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "user": {
            "id": user["id"],
            "email": user["email"],
            "nickname": user["nickname"],
            "is_admin": bool(user["is_admin"]),
        },
    }


@router.post("/refresh")
async def refresh(body: RefreshRequest, request: Request):
    try:
        payload = decode_token(body.refresh_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(user_id)
    return {"access_token": access_token}
```

- [ ] **Step 2: 커밋**

```bash
git add src/ui/api/routes/auth.py
git commit -m "feat: add auth API routes (register, login, refresh)"
```

---

## Task 6: Admin API 라우터 생성

**Files:**
- Create: `src/ui/api/routes/admin.py`

- [ ] **Step 1: admin 라우터 구현**

```python
# src/ui/api/routes/admin.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.ui.api.auth import require_admin

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


class SetActiveRequest(BaseModel):
    is_active: bool


@router.get("/users")
async def list_users(request: Request):
    app = request.app.state.app
    users = await app.user_repo.list_all()
    return [
        {
            "id": u["id"],
            "email": u["email"],
            "nickname": u["nickname"],
            "is_admin": bool(u["is_admin"]),
            "is_active": bool(u["is_active"]),
            "created_at": u["created_at"],
        }
        for u in users
    ]


@router.patch("/users/{user_id}")
async def update_user(user_id: int, body: SetActiveRequest, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user["is_admin"]:
        raise HTTPException(status_code=400, detail="Cannot deactivate admin")

    await app.user_repo.set_active(user_id, body.is_active)

    if not body.is_active and user_id in app.user_accounts:
        del app.user_accounts[user_id]
        del app.user_risk[user_id]

    return {"id": user_id, "is_active": body.is_active}
```

- [ ] **Step 2: 커밋**

```bash
git add src/ui/api/routes/admin.py
git commit -m "feat: add admin API routes (list users, activate/deactivate)"
```

---

## Task 7: Repository 레이어 — user_id 파라미터 추가

**Files:**
- Modify: `src/repository/order_repo.py`
- Modify: `src/repository/portfolio_repo.py`

- [ ] **Step 1: order_repo.py 수정**

모든 메서드에 `user_id: int` 파라미터 추가. `save()`의 INSERT에 user_id 컬럼 추가, `get_recent()`과 `count_since()`에 `WHERE user_id = ?` 조건 추가.

`save()` 메서드 (라인 14-27):
```python
async def save(self, order: Order, user_id: int) -> None:
    await self._db.conn.execute(
        "INSERT INTO orders"
        " (id, market, side, order_type, price, fill_price,"
        "  quantity, fee, status, signal_confidence, reason,"
        "  created_at, filled_at, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(id) DO UPDATE SET"
        "  fill_price=excluded.fill_price, fee=excluded.fee,"
        "  status=excluded.status, filled_at=excluded.filled_at",
        (
            order.id, order.market, order.side.value,
            order.order_type.value, str(order.price),
            str(order.fill_price) if order.fill_price else None,
            str(order.quantity), str(order.fee),
            order.status.value, order.signal_confidence,
            order.reason, order.created_at,
            order.filled_at, user_id,
        ),
    )
    await self._db.conn.commit()
```

`get_recent()` 메서드 (라인 38-43):
```python
async def get_recent(self, user_id: int, limit: int = 50) -> list[Order]:
    cursor = await self._db.conn.execute(
        "SELECT * FROM orders WHERE user_id = ?"
        " ORDER BY created_at DESC LIMIT ?",
        (user_id, limit),
    )
    return [self._row_to_order(r) for r in await cursor.fetchall()]
```

`count_since()` 메서드 (라인 45-50):
```python
async def count_since(self, user_id: int, since: str) -> int:
    cursor = await self._db.conn.execute(
        "SELECT COUNT(*) FROM orders"
        " WHERE user_id = ? AND created_at >= ?",
        (user_id, since),
    )
    return (await cursor.fetchone())[0]
```

`get_by_id()` 메서드는 user_id 불필요 (주문 ID는 UUID로 유니크).

- [ ] **Step 2: portfolio_repo.py 수정**

모든 메서드에 `user_id: int` 파라미터 추가.

`save_daily_summary()` — INSERT/UPDATE에 user_id 추가:
```python
async def save_daily_summary(self, summary: DailySummary, user_id: int) -> None:
    await self._db.conn.execute(
        "INSERT INTO daily_summary"
        " (date, starting_balance, ending_balance, realized_pnl,"
        "  total_trades, win_trades, loss_trades, max_drawdown_pct, user_id)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        " ON CONFLICT(date, user_id) DO UPDATE SET"
        "  ending_balance=excluded.ending_balance,"
        "  realized_pnl=excluded.realized_pnl,"
        "  total_trades=excluded.total_trades,"
        "  win_trades=excluded.win_trades,"
        "  loss_trades=excluded.loss_trades,"
        "  max_drawdown_pct=excluded.max_drawdown_pct",
        (
            summary.date,
            str(summary.starting_balance), str(summary.ending_balance),
            str(summary.realized_pnl),
            summary.total_trades, summary.win_trades,
            summary.loss_trades, str(summary.max_drawdown_pct),
            user_id,
        ),
    )
    await self._db.conn.commit()
```

주의: daily_summary의 ON CONFLICT를 `(date, user_id)`로 변경하려면 UNIQUE 인덱스 추가 필요. `_migrate()`에 추가:
```python
await self._conn.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_summary_user_date"
    " ON daily_summary(user_id, date)"
)
```

`get_daily_summaries()`:
```python
async def get_daily_summaries(
    self, user_id: int, since_date: str,
) -> list[DailySummary]:
    cursor = await self._db.conn.execute(
        "SELECT date, starting_balance, ending_balance, realized_pnl,"
        " total_trades, win_trades, loss_trades, max_drawdown_pct"
        " FROM daily_summary WHERE user_id = ? AND date >= ?"
        " ORDER BY date",
        (user_id, since_date),
    )
    return [self._row_to_summary(r) for r in await cursor.fetchall()]
```

`save_account()`:
```python
async def save_account(self, account: PaperAccount, user_id: int) -> None:
    await self._db.conn.execute(
        "INSERT INTO account_state (user_id, cash_balance, updated_at)"
        " VALUES (?, ?, datetime('now'))"
        " ON CONFLICT(user_id) DO UPDATE SET"
        "  cash_balance=excluded.cash_balance,"
        "  updated_at=excluded.updated_at",
        (user_id, str(account.cash_balance)),
    )
    await self._db.conn.execute(
        "DELETE FROM positions WHERE user_id = ?", (user_id,)
    )
    if account.positions:
        await self._db.conn.executemany(
            "INSERT INTO positions"
            " (market, side, entry_price, quantity, entry_time,"
            "  unrealized_pnl, highest_price, add_count, total_invested,"
            "  partial_sold, trade_mode, stop_loss_price,"
            "  take_profit_price, user_id)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    m, p.side.value, str(p.entry_price), str(p.quantity),
                    p.entry_time, str(p.unrealized_pnl), str(p.highest_price),
                    p.add_count, str(p.total_invested),
                    1 if p.partial_sold else 0, p.trade_mode,
                    str(p.stop_loss_price) if p.stop_loss_price else None,
                    str(p.take_profit_price) if p.take_profit_price else None,
                    user_id,
                )
                for m, p in account.positions.items()
            ],
        )
    await self._db.conn.commit()
```

`load_account()`:
```python
async def load_account(self, user_id: int) -> PaperAccount | None:
    cursor = await self._db.conn.execute(
        "SELECT cash_balance FROM account_state WHERE user_id = ?",
        (user_id,),
    )
    row = await cursor.fetchone()
    if not row:
        return None
    cash = Decimal(row[0])

    cursor = await self._db.conn.execute(
        "SELECT market, side, entry_price, quantity, entry_time,"
        " unrealized_pnl, highest_price, add_count, total_invested,"
        " partial_sold, trade_mode, stop_loss_price, take_profit_price"
        " FROM positions WHERE user_id = ?",
        (user_id,),
    )
    # ... 나머지 동일 (포지션 딕셔너리 복원)
```

`save_risk_state()` 및 `load_risk_state()`도 동일 패턴으로 `WHERE user_id = ?` 추가.

- [ ] **Step 3: account_state PK 마이그레이션 처리**

`database.py`의 `_migrate()`에 account_state의 user_id UNIQUE 인덱스 추가:
```python
await self._conn.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_account_state_user"
    " ON account_state(user_id)"
)
await self._conn.execute(
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_risk_state_user"
    " ON risk_state(user_id)"
)
```

- [ ] **Step 4: 기존 테스트 수정 및 실행**

Run: `uv run pytest tests/ -v`
Expected: 기존 테스트 중 repo 호출하는 부분이 user_id 누락으로 실패할 수 있음. 수정 필요.

- [ ] **Step 5: 커밋**

```bash
git add src/repository/order_repo.py src/repository/portfolio_repo.py src/repository/database.py
git commit -m "feat: add user_id parameter to all tenant repository methods"
```

---

## Task 8: PaperAccount 모델 변경 없이 App 멀티유저 구조 전환

**Files:**
- Modify: `src/runtime/app.py`

이 태스크가 가장 큰 변경입니다. App 클래스를 단일 account에서 user_accounts dict로 전환합니다.

- [ ] **Step 1: App.__init__에 멀티유저 상태 추가**

기존 (라인 86-88):
```python
self.account = PaperAccount(...)
```

변경:
```python
# Multi-user state
self.user_accounts: dict[int, PaperAccount] = {}
self.user_risk: dict[int, RiskManager] = {}
self.user_pnl: dict[int, dict] = {}  # {user_id: {realized, wins, losses}}

# Keep single account as fallback for backward compat during migration
self.account = PaperAccount(
    initial_balance=settings.paper_trading.initial_balance,
    cash_balance=settings.paper_trading.initial_balance,
)
```

UserRepo 인스턴스 추가:
```python
from src.repository.user_repo import UserRepo
# __init__에서:
self.user_repo = UserRepo(self.db)
```

- [ ] **Step 2: load_user() 메서드 추가**

```python
async def load_user(self, user_id: int) -> None:
    """Load or reload a user's account and risk manager."""
    settings_row = await self.user_repo.get_settings(user_id)
    if not settings_row:
        return

    # Load account
    account = await self.portfolio_repo.load_account(user_id)
    if account is None:
        initial = Decimal(settings_row["initial_balance"])
        account = PaperAccount(
            initial_balance=initial, cash_balance=initial,
        )
    self.user_accounts[user_id] = account

    # Load risk manager with user settings
    risk_config = dataclasses.replace(
        self.settings.risk,
        stop_loss_pct=Decimal(settings_row["stop_loss_pct"]),
        take_profit_pct=Decimal(settings_row["take_profit_pct"]),
        trailing_stop_pct=Decimal(settings_row["trailing_stop_pct"]),
        max_daily_loss_pct=Decimal(settings_row["max_daily_loss_pct"]),
    )
    rm = RiskManager(risk_config, self.settings.paper_trading)
    risk_state = await self.portfolio_repo.load_risk_state(user_id)
    if risk_state:
        rm.load_state(risk_state)
    self.user_risk[user_id] = rm

    # Init daily PnL tracking
    self.user_pnl[user_id] = {
        "realized": Decimal("0"), "wins": 0, "losses": 0,
    }
```

- [ ] **Step 3: start() 메서드 수정 — 모든 활성 사용자 로드**

기존 start()의 account 복원 부분 (라인 126-134) 을 대체:
```python
# Load all active users
active_ids = await self.user_repo.get_active_user_ids()
for uid in active_ids:
    await self.load_user(uid)
```

- [ ] **Step 4: _on_signal() 수정 — 모든 활성 사용자에게 신호 전달**

기존 _on_signal은 단일 account로 매매 판단. 변경:

```python
async def _on_signal(self, event: dict) -> None:
    if self.paused:
        return

    signal = event["signal"]
    market = signal.market

    for user_id, account in self.user_accounts.items():
        settings_row = await self.user_repo.get_settings(user_id)
        if not settings_row or not settings_row["trading_enabled"]:
            continue

        rm = self.user_risk.get(user_id)
        if rm is None:
            continue

        # 기존 매매 로직을 user_id 컨텍스트로 실행
        await self._process_signal_for_user(
            signal, market, user_id, account, rm,
        )
```

`_process_signal_for_user()`는 기존 `_on_signal`의 매매 로직을 user_id 파라미터 포함하여 추출한 것:
```python
async def _process_signal_for_user(
    self, signal, market, user_id, account, rm,
) -> None:
    # SELL
    if signal.signal_type == SignalType.SELL:
        if market not in account.positions:
            return
        pos = account.positions[market]
        if pos.trade_mode != "AUTO":
            return
        price = await self._get_current_price(market)
        order = self.paper_engine.execute_sell(
            account, market, price, signal.confidence, "SIGNAL_SELL",
        )
        await self.order_repo.save(order, user_id)
        self._record_trade_result_for_user(
            user_id, pos.entry_price, order.fill_price, pos.quantity,
        )
        await self._save_user_state(user_id)
        return

    # BUY
    if signal.signal_type != SignalType.BUY:
        return

    approved, reason = rm.approve(signal, account)
    if not approved:
        return

    is_additional = market in account.positions
    if is_additional:
        if not rm.should_additional_buy(
            account.positions[market], await self._get_current_price(market),
        ):
            return
    else:
        score = self.entry_analyzer.score_entry(...)
        if score < self.settings.entry_analyzer.min_entry_score:
            return

    size = rm.calculate_position_size(
        account, signal.confidence, is_additional,
    )
    if size < self.settings.paper_trading.min_order_krw:
        return

    price = await self._get_current_price(market)
    order = self.paper_engine.execute_buy(
        account, market, price, size, signal.confidence, "SIGNAL_BUY",
    )
    await self.order_repo.save(order, user_id)
    rm.record_trade()
    await self._save_user_state(user_id)
```

- [ ] **Step 5: _monitor_positions() 수정 — 모든 사용자 포지션 순회**

```python
async def _monitor_positions(self) -> None:
    if self.paused:
        return

    for user_id, account in list(self.user_accounts.items()):
        if not account.positions:
            continue
        await self._monitor_user_positions(user_id, account)
```

`_monitor_user_positions()`는 기존 `_monitor_positions`의 로직을 user_id 컨텍스트로 추출.

- [ ] **Step 6: _save_state() → _save_user_state(user_id) 로 변경**

```python
async def _save_user_state(self, user_id: int) -> None:
    account = self.user_accounts.get(user_id)
    rm = self.user_risk.get(user_id)
    if not account or not rm:
        return
    await self.portfolio_repo.save_account(account, user_id)
    await self.portfolio_repo.save_risk_state(rm.dump_state(), user_id)
    await self._snapshot_daily_summary_for_user(user_id)

async def _save_all_states(self) -> None:
    for user_id in self.user_accounts:
        await self._save_user_state(user_id)
```

- [ ] **Step 7: stop() 및 reset() 수정**

`stop()`: `_save_state()` → `_save_all_states()`
`reset()`: user_id 파라미터 추가하여 특정 사용자만 초기화 가능.

- [ ] **Step 8: 기존 테스트 수정 및 실행**

Run: `uv run pytest tests/ -v`
Expected: PASS (기존 테스트가 단일 사용자로 돌아가도록 호환성 유지)

- [ ] **Step 9: 커밋**

```bash
git add src/runtime/app.py
git commit -m "feat: convert App to multi-user with user_accounts/user_risk dicts"
```

---

## Task 9: API 라우터에 인증 적용 및 user_id 주입

**Files:**
- Modify: `src/ui/api/server.py`
- Modify: `src/ui/api/routes/dashboard.py`
- Modify: `src/ui/api/routes/portfolio.py`
- Modify: `src/ui/api/routes/exchange.py`
- Modify: `src/ui/api/routes/control.py`
- Modify: `src/ui/api/routes/risk.py`
- Modify: `src/ui/api/routes/strategy.py`

- [ ] **Step 1: server.py — auth, admin 라우터 등록 + CORS 수정**

`src/ui/api/server.py`에서:

```python
from src.ui.api.routes import auth as auth_router
from src.ui.api.routes import admin as admin_router

# create_app() 내부에 라우터 추가:
app.include_router(auth_router.router)
app.include_router(admin_router.router)
```

CORS origins 수정: 환경변수 `CORS_ORIGINS`로 설정 가능하게:
```python
import os
origins = os.environ.get("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    ...
)
```

- [ ] **Step 2: WebSocket 인증 추가**

`server.py`의 WebSocket 핸들러 (라인 33-78):
```python
from src.ui.api.auth import decode_token

@app.websocket("/ws/live")
async def websocket_live(websocket: WebSocket):
    # Authenticate via query param
    token = websocket.query_params.get("token")
    if not token:
        await websocket.close(code=4001, reason="Missing token")
        return
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("Invalid token type")
    except ValueError:
        await websocket.close(code=4001, reason="Invalid token")
        return

    user_id = payload["sub"]
    await websocket.accept()
    # ... 나머지 기존 로직
```

- [ ] **Step 3: dashboard.py — user_id 주입**

모든 엔드포인트에 `user: dict = Depends(get_current_user)` 추가.

`GET /api/dashboard/summary`:
```python
from src.ui.api.auth import get_current_user
from fastapi import Depends

@router.get("/summary")
async def summary(request: Request, user: dict = Depends(get_current_user)):
    app = request.app.state.app
    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if not account:
        return {"error": "Account not initialized"}
    # 기존 로직에서 app.account → account 로 대체
    ...
```

- [ ] **Step 4: portfolio.py — user_id 주입**

```python
@router.get("/positions")
async def positions(request: Request, user: dict = Depends(get_current_user)):
    app = request.app.state.app
    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    # 기존 app.account.positions → account.positions
    ...

@router.get("/history")
async def history(request: Request, user: dict = Depends(get_current_user), ...):
    # order_repo.get_recent(user_id, ...)
    ...

@router.get("/daily")
async def daily(request: Request, user: dict = Depends(get_current_user), ...):
    # portfolio_repo.get_daily_summaries(user_id, ...)
    ...
```

- [ ] **Step 5: exchange.py — user_id 주입**

```python
@router.post("/buy")
async def buy(body: BuyRequest, request: Request, user: dict = Depends(get_current_user)):
    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    # paper_engine.execute_buy(account, ...)
    # order_repo.save(order, user_id)
    # _save_user_state(user_id)
    ...

@router.post("/sell")
async def sell(body: SellRequest, request: Request, user: dict = Depends(get_current_user)):
    # 동일 패턴
    ...
```

- [ ] **Step 6: control.py — 사용자별 trading_enabled + 관리자 전용 글로벌 설정**

사용자별 trading start/stop:
```python
@router.post("/trading/start")
async def start_trading(request: Request, user: dict = Depends(get_current_user)):
    app = request.app.state.app
    await app.user_repo.update_settings(user["id"], {"trading_enabled": 1})
    return {"trading_enabled": True}
```

글로벌 설정 (PATCH /config)은 관리자만:
```python
@router.patch("/config")
async def patch_config(request: Request, user: dict = Depends(require_admin)):
    # 기존 hot_reload 로직
    ...
```

사용자별 설정 수정 엔드포인트 추가:
```python
@router.patch("/user-config")
async def patch_user_config(request: Request, user: dict = Depends(get_current_user)):
    body = await request.json()
    allowed = {"stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
               "max_daily_loss_pct", "max_position_pct", "max_open_positions"}
    patches = {k: v for k, v in body.items() if k in allowed}
    await app.user_repo.update_settings(user["id"], patches)
    # Reload user's risk manager
    await app.load_user(user["id"])
    return {"updated": list(patches.keys())}
```

- [ ] **Step 7: risk.py — user_id 주입**

```python
@router.get("/status")
async def status(request: Request, user: dict = Depends(get_current_user)):
    rm = app.user_risk.get(user["id"])
    # 기존 로직에서 app.risk_manager → rm
    ...
```

- [ ] **Step 8: strategy.py — 인증만 추가 (데이터는 공유)**

신호, 스크리닝, 모델 상태는 공유 데이터이므로 user_id 필터 불필요. 인증만 추가:
```python
@router.get("/screening")
async def screening(request: Request, user: dict = Depends(get_current_user)):
    # 기존 로직 그대로
    ...
```

- [ ] **Step 9: 커밋**

```bash
git add src/ui/api/server.py src/ui/api/routes/
git commit -m "feat: add auth middleware to all API routes, inject user_id"
```

---

## Task 10: 프론트엔드 — useAuth 훅 및 useApi 수정

**Files:**
- Create: `src/ui/frontend/src/hooks/useAuth.ts`
- Modify: `src/ui/frontend/src/hooks/useApi.ts`
- Modify: `src/ui/frontend/src/hooks/useWebSocket.ts`

- [ ] **Step 1: useAuth 훅 생성**

```typescript
// src/ui/frontend/src/hooks/useAuth.ts
import { useState, useEffect, useCallback } from "react";

interface User {
  id: number;
  email: string;
  nickname: string;
  is_admin: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
}

const API_BASE = import.meta.env.VITE_API_URL || "";

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>(() => {
    const stored = localStorage.getItem("auth");
    return stored ? JSON.parse(stored) : { user: null, accessToken: null, refreshToken: null };
  });

  useEffect(() => {
    if (auth.user) {
      localStorage.setItem("auth", JSON.stringify(auth));
    } else {
      localStorage.removeItem("auth");
    }
  }, [auth]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    setAuth({
      user: data.user,
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    });
  }, []);

  const register = useCallback(async (
    email: string, password: string, nickname: string, inviteCode: string,
  ) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email, password, nickname, invite_code: inviteCode,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }
    return await res.json();
  }, []);

  const refresh = useCallback(async () => {
    if (!auth.refreshToken) return false;
    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: auth.refreshToken }),
      });
      if (!res.ok) throw new Error("Refresh failed");
      const data = await res.json();
      setAuth(prev => ({ ...prev, accessToken: data.access_token }));
      return true;
    } catch {
      logout();
      return false;
    }
  }, [auth.refreshToken]);

  const logout = useCallback(() => {
    setAuth({ user: null, accessToken: null, refreshToken: null });
  }, []);

  return {
    user: auth.user,
    accessToken: auth.accessToken,
    isAuthenticated: !!auth.user,
    isAdmin: auth.user?.is_admin ?? false,
    login,
    register,
    refresh,
    logout,
  };
}
```

- [ ] **Step 2: useApi 수정 — Authorization 헤더 + 401 처리**

```typescript
// src/ui/frontend/src/hooks/useApi.ts
const API_BASE = import.meta.env.VITE_API_URL || "";

export function useApi(accessToken: string | null, onUnauthorized: () => void) {
  const headers = (): Record<string, string> => {
    const h: Record<string, string> = {};
    if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
    return h;
  };

  const handleResponse = async <T>(res: Response): Promise<T> => {
    if (res.status === 401) {
      onUnauthorized();
      throw new Error("Unauthorized");
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  };

  const get = async <T>(path: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, { headers: headers() });
    return handleResponse<T>(res);
  };

  const post = async <T>(path: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST", headers: headers(),
    });
    return handleResponse<T>(res);
  };

  const postJson = async <T>(path: string, body: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  };

  const patchJson = async <T>(path: string, body: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  };

  return { get, post, postJson, patchJson };
}
```

- [ ] **Step 3: useWebSocket 수정 — 토큰 쿼리 파라미터**

```typescript
// src/ui/frontend/src/hooks/useWebSocket.ts 변경
// 기존: useWebSocket(url: string)
// 변경: useWebSocket(url: string, token: string | null)

export function useWebSocket(url: string, token: string | null) {
  // ...
  useEffect(() => {
    if (!token) return;
    const wsUrl = `${url}?token=${token}`;
    const ws = new WebSocket(wsUrl);
    // ... 나머지 동일
  }, [url, token]);
  // ...
}
```

- [ ] **Step 4: 커밋**

```bash
git add src/ui/frontend/src/hooks/
git commit -m "feat: add useAuth hook, add auth to useApi and useWebSocket"
```

---

## Task 11: 프론트엔드 — 로그인/회원가입 페이지

**Files:**
- Create: `src/ui/frontend/src/pages/Login.tsx`
- Create: `src/ui/frontend/src/pages/Register.tsx`

- [ ] **Step 1: Login.tsx 생성**

```tsx
// src/ui/frontend/src/pages/Login.tsx
import { useState, FormEvent } from "react";
import { Link } from "react-router-dom";

interface Props {
  onLogin: (email: string, password: string) => Promise<void>;
}

export default function Login({ onLogin }: Props) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await onLogin(email, password);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">Paper Trader</h1>
        <p className="auth-subtitle">로그인</p>
        <form onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="form-group">
            <label>이메일</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "로그인 중..." : "로그인"}
          </button>
        </form>
        <p className="auth-link">
          계정이 없으신가요? <Link to="/register">회원가입</Link>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Register.tsx 생성**

```tsx
// src/ui/frontend/src/pages/Register.tsx
import { useState, FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";

interface Props {
  onRegister: (
    email: string, password: string, nickname: string, inviteCode: string,
  ) => Promise<any>;
}

export default function Register({ onRegister }: Props) {
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [nickname, setNickname] = useState("");
  const [inviteCode, setInviteCode] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다");
      return;
    }
    setLoading(true);
    try {
      await onRegister(email, password, nickname, inviteCode);
      navigate("/login");
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="auth-container">
      <div className="auth-card">
        <h1 className="auth-title">Paper Trader</h1>
        <p className="auth-subtitle">회원가입</p>
        <form onSubmit={handleSubmit}>
          {error && <div className="auth-error">{error}</div>}
          <div className="form-group">
            <label>이메일</label>
            <input
              type="email"
              value={email}
              onChange={e => setEmail(e.target.value)}
              required
              autoFocus
            />
          </div>
          <div className="form-group">
            <label>닉네임</label>
            <input
              type="text"
              value={nickname}
              onChange={e => setNickname(e.target.value)}
              required
            />
          </div>
          <div className="form-group">
            <label>비밀번호</label>
            <input
              type="password"
              value={password}
              onChange={e => setPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <div className="form-group">
            <label>초대 코드</label>
            <input
              type="text"
              value={inviteCode}
              onChange={e => setInviteCode(e.target.value)}
              required
            />
          </div>
          <button type="submit" className="btn btn-primary auth-btn" disabled={loading}>
            {loading ? "가입 중..." : "가입하기"}
          </button>
        </form>
        <p className="auth-link">
          이미 계정이 있으신가요? <Link to="/login">로그인</Link>
        </p>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: 커밋**

```bash
git add src/ui/frontend/src/pages/Login.tsx src/ui/frontend/src/pages/Register.tsx
git commit -m "feat: add Login and Register pages"
```

---

## Task 12: 프론트엔드 — App.tsx 인증 가드 통합

**Files:**
- Modify: `src/ui/frontend/src/App.tsx`

- [ ] **Step 1: App.tsx 전면 수정**

```tsx
// src/ui/frontend/src/App.tsx
import { BrowserRouter, Routes, Route, Navigate, NavLink } from "react-router-dom";
import { useAuth } from "./hooks/useAuth";
import { useApi } from "./hooks/useApi";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./pages/Dashboard";
import Exchange from "./pages/Exchange";
import Strategy from "./pages/Strategy";
import Risk from "./pages/Risk";
import System from "./pages/System";
import Login from "./pages/Login";
import Register from "./pages/Register";
import { useEffect, useState } from "react";

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

export default function App() {
  const auth = useAuth();
  const api = useApi(auth.accessToken, async () => {
    const ok = await auth.refresh();
    if (!ok) auth.logout();
  });

  // If not authenticated, show login/register
  if (!auth.isAuthenticated) {
    return (
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<Login onLogin={auth.login} />} />
          <Route path="/register" element={<Register onRegister={auth.register} />} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </BrowserRouter>
    );
  }

  // Authenticated app
  return (
    <BrowserRouter>
      <AuthenticatedApp auth={auth} api={api} />
    </BrowserRouter>
  );
}

function AuthenticatedApp({ auth, api }: { auth: ReturnType<typeof useAuth>; api: ReturnType<typeof useApi> }) {
  const wsMsg = useWebSocket(`${WS_BASE}/ws/live`, auth.accessToken);
  const [tradingEnabled, setTradingEnabled] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);

  // Poll status
  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.get<any>("/api/control/status");
        setTradingEnabled(data.trading_enabled);
      } catch { /* ignore */ }
    };
    fetchStatus();
    const iv = setInterval(fetchStatus, 5000);
    return () => clearInterval(iv);
  }, []);

  // Trade toast
  useEffect(() => {
    if (wsMsg.lastMessage?.type === "trade_executed") {
      const d = wsMsg.lastMessage.data;
      const id = Date.now();
      setToasts(prev => [...prev, { id, msg: `${d.side} ${d.market} 체결` }]);
      setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 5000);
    }
  }, [wsMsg.lastMessage]);

  return (
    <div className="layout">
      <aside className="sidebar">
        <div className="brand">
          <span className="brand-icon">◈</span>
          <span>Paper Trader</span>
        </div>
        <nav className="nav-list">
          <NavLink to="/" end className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>Dashboard</NavLink>
          <NavLink to="/exchange" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>Exchange</NavLink>
          <NavLink to="/strategy" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>Strategy</NavLink>
          <NavLink to="/risk" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>Risk</NavLink>
          <NavLink to="/system" className={({ isActive }) => isActive ? "nav-item active" : "nav-item"}>System</NavLink>
        </nav>
        <div className="sidebar-footer">
          <div className="user-info">
            <span className="user-nickname">{auth.user?.nickname}</span>
            <span className="user-email">{auth.user?.email}</span>
          </div>
          <button className="btn btn-sm" onClick={auth.logout}>로그아웃</button>
          <div className={`status-dot ${tradingEnabled ? "active" : ""}`} />
          <span className="status-label">{tradingEnabled ? "자동매매 ON" : "자동매매 OFF"}</span>
          <div className={`status-dot ${wsMsg.isConnected ? "connected" : ""}`} />
          <span className="status-label">{wsMsg.isConnected ? "실시간" : "연결 끊김"}</span>
        </div>
      </aside>
      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard api={api} wsMsg={wsMsg} />} />
          <Route path="/exchange" element={<Exchange api={api} wsMsg={wsMsg} />} />
          <Route path="/strategy" element={<Strategy api={api} />} />
          <Route path="/risk" element={<Risk api={api} />} />
          <Route path="/system" element={<System api={api} isAdmin={auth.isAdmin} />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      {toasts.length > 0 && (
        <div className="toast-container">
          {toasts.map(t => <div key={t.id} className="toast">{t.msg}</div>)}
        </div>
      )}
    </div>
  );
}
```

주의: 기존 페이지 컴포넌트들이 `useApi()`를 직접 호출하고 있었다면, props로 `api` 객체를 전달받도록 수정해야 합니다. 또는 React Context로 제공할 수도 있습니다. 기존 코드를 확인하여 각 페이지의 API 호출 방식에 맞게 조정합니다.

- [ ] **Step 2: 기존 페이지에서 useApi() 호출을 props 기반으로 변경**

각 페이지 (Dashboard, Exchange, Strategy, Risk, System)에서:
- `const { get, post, ... } = useApi()` → props에서 받은 `api` 객체 사용
- 또는 AuthContext를 만들어 전역 제공 (이 방식이 기존 코드 변경을 최소화)

AuthContext 방식을 추천:

```tsx
// src/ui/frontend/src/context/AuthContext.tsx
import { createContext, useContext } from "react";
import { useAuth } from "../hooks/useAuth";
import { useApi } from "../hooks/useApi";

interface AuthContextType {
  auth: ReturnType<typeof useAuth>;
  api: ReturnType<typeof useApi>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const api = useApi(auth.accessToken, async () => {
    const ok = await auth.refresh();
    if (!ok) auth.logout();
  });
  return (
    <AuthContext.Provider value={{ auth, api }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be inside AuthProvider");
  return ctx;
}
```

이렇게 하면 기존 페이지에서 `useApi()` → `useAuthContext().api`로만 바꾸면 됩니다.

- [ ] **Step 3: 커밋**

```bash
git add src/ui/frontend/src/
git commit -m "feat: integrate auth guard in App.tsx, add AuthContext"
```

---

## Task 13: 프론트엔드 — System 페이지에 사용자 관리 탭 (관리자 전용)

**Files:**
- Modify: `src/ui/frontend/src/pages/System.tsx`

- [ ] **Step 1: 관리자 사용자 관리 섹션 추가**

System.tsx에 `isAdmin` prop (또는 AuthContext에서 가져옴)이 true일 때만 보이는 사용자 관리 섹션 추가:

```tsx
// System.tsx 하단에 추가
{isAdmin && (
  <section className="card">
    <h2 className="section-title">사용자 관리</h2>
    <table className="data-table">
      <thead>
        <tr>
          <th>닉네임</th>
          <th>이메일</th>
          <th>상태</th>
          <th>가입일</th>
          <th>관리</th>
        </tr>
      </thead>
      <tbody>
        {users.map(u => (
          <tr key={u.id}>
            <td>{u.nickname}</td>
            <td>{u.email}</td>
            <td>{u.is_active ? "활성" : "비활성"}</td>
            <td>{new Date(u.created_at).toLocaleDateString()}</td>
            <td>
              {!u.is_admin && (
                <button
                  className={`btn btn-sm ${u.is_active ? "btn-danger" : "btn-primary"}`}
                  onClick={() => toggleUser(u.id, !u.is_active)}
                >
                  {u.is_active ? "비활성화" : "활성화"}
                </button>
              )}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>
)}
```

상태 및 핸들러:
```tsx
const [users, setUsers] = useState<any[]>([]);

useEffect(() => {
  if (isAdmin) {
    api.get<any[]>("/api/admin/users").then(setUsers).catch(() => {});
  }
}, [isAdmin]);

const toggleUser = async (userId: number, active: boolean) => {
  await api.patchJson(`/api/admin/users/${userId}`, { is_active: active });
  setUsers(prev => prev.map(u => u.id === userId ? { ...u, is_active: active } : u));
};
```

- [ ] **Step 2: 사용자별 설정 수정 UI 추가**

기존 글로벌 설정 수정 UI를 사용자 설정 수정으로 전환:

```tsx
// 사용자 매매 설정 섹션
<section className="card">
  <h2 className="section-title">내 매매 설정</h2>
  {/* stop_loss_pct, take_profit_pct 등 슬라이더/입력 */}
  {/* PATCH /api/control/user-config */}
</section>
```

- [ ] **Step 3: 커밋**

```bash
git add src/ui/frontend/src/pages/System.tsx
git commit -m "feat: add admin user management and per-user settings in System page"
```

---

## Task 14: 프론트엔드 — 인증 관련 CSS 추가

**Files:**
- Modify: `src/ui/frontend/src/index.css`

- [ ] **Step 1: 로그인/회원가입 스타일 추가**

```css
/* Auth pages */
.auth-container {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: var(--bg-deep);
}

.auth-card {
  background: var(--bg-card);
  border: 1px solid var(--border);
  border-radius: var(--card-radius);
  padding: 40px;
  width: 100%;
  max-width: 400px;
}

.auth-title {
  font-family: var(--font-display);
  font-size: 1.8rem;
  color: var(--accent);
  text-align: center;
  margin-bottom: 4px;
}

.auth-subtitle {
  text-align: center;
  color: var(--text-secondary);
  margin-bottom: 24px;
}

.auth-error {
  background: rgba(255, 68, 102, 0.1);
  border: 1px solid var(--loss);
  color: var(--loss);
  padding: 8px 12px;
  border-radius: 6px;
  font-size: 0.85rem;
  margin-bottom: 16px;
}

.auth-btn {
  width: 100%;
  margin-top: 8px;
}

.auth-link {
  text-align: center;
  margin-top: 16px;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.auth-link a {
  color: var(--accent);
  text-decoration: none;
}

.auth-link a:hover {
  text-decoration: underline;
}

/* User info in sidebar */
.user-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 8px;
}

.user-nickname {
  font-weight: 600;
  color: var(--text-primary);
}

.user-email {
  font-size: 0.75rem;
  color: var(--text-secondary);
}
```

- [ ] **Step 2: 커밋**

```bash
git add src/ui/frontend/src/index.css
git commit -m "feat: add auth page styles and sidebar user info styles"
```

---

## Task 15: 설정 파일 — auth 섹션 추가

**Files:**
- Modify: `config/settings.yaml`
- Modify: `src/config/settings.py`

- [ ] **Step 1: settings.yaml에 auth 섹션 추가**

```yaml
auth:
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
```

환경변수 오버라이드: `JWT_SECRET`, `INVITE_CODE`, `ADMIN_EMAIL`은 환경변수에서만 관리 (YAML에 넣지 않음).

- [ ] **Step 2: settings.py에 AuthConfig 추가**

```python
@dataclasses.dataclass(frozen=True)
class AuthConfig:
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
```

Settings에 추가:
```python
@dataclasses.dataclass(frozen=True)
class Settings:
    # ... 기존 필드
    auth: AuthConfig = dataclasses.field(default_factory=AuthConfig)
```

`from_yaml()` / `from_dict()`에 auth 파싱 추가.

- [ ] **Step 3: 커밋**

```bash
git add config/settings.yaml src/config/settings.py
git commit -m "feat: add auth config section to settings"
```

---

## Task 16: Docker 배포 파일 생성

**Files:**
- Create: `deploy/Dockerfile`
- Create: `deploy/docker-compose.yml`
- Create: `deploy/nginx/default.conf`
- Create: `deploy/ssl/generate-cert.sh`
- Create: `deploy/.env.example`
- Create: `deploy/docker-build-guide.md`

- [ ] **Step 1: Dockerfile 생성**

```dockerfile
# deploy/Dockerfile

# ── Stage 1: Python 패키지 빌드 ──
FROM python:3.12-slim AS py-builder

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install uv && uv pip install --system --no-cache-dir -r pyproject.toml

# ── Stage 2: React 프론트엔드 빌드 ──
FROM node:22-slim AS web-builder

WORKDIR /app/frontend

COPY src/ui/frontend/package.json src/ui/frontend/package-lock.json ./
RUN npm ci

COPY src/ui/frontend/ ./

ARG VITE_API_URL
ARG VITE_WS_URL

RUN npm run build

# ── Stage 3: Nginx (프론트엔드 + 리버스 프록시) ──
FROM nginx:alpine AS web

RUN rm /etc/nginx/conf.d/default.conf
COPY deploy/nginx/default.conf /etc/nginx/conf.d/default.conf
COPY --from=web-builder /app/frontend/dist /usr/share/nginx/html

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]

# ── Stage 4: FastAPI 런타임 ──
FROM python:3.12-slim AS app

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY --from=py-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=py-builder /usr/local/bin /usr/local/bin

RUN groupadd --gid 1001 appuser \
    && useradd --uid 1001 --gid appuser --no-create-home appuser

COPY src/ ./src/
COPY config/ ./config/

RUN mkdir -p data/models && chown -R appuser:appuser /app
USER appuser

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["uvicorn", "src.ui.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: docker-compose.yml 생성**

```yaml
# deploy/docker-compose.yml
services:
  app:
    image: agent-research-app:latest
    ports:
      - "${API_PORT:-8001}:8000"
    env_file: .env
    volumes:
      - ./data:/app/data
      - ./config:/app/config
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/health"]
      interval: 30s
      timeout: 5s
      start_period: 10s
      retries: 3

  web:
    image: agent-research-web:latest
    ports:
      - "${WEB_PORT:-443}:443"
      - "${HTTP_PORT:-80}:80"
    volumes:
      - ./ssl:/etc/ssl/app
    depends_on:
      app:
        condition: service_healthy
    restart: unless-stopped
```

- [ ] **Step 3: Nginx 설정 생성**

```nginx
# deploy/nginx/default.conf
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/ssl/app/cert.pem;
    ssl_certificate_key /etc/ssl/app/key.pem;

    # React SPA
    root /usr/share/nginx/html;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # API reverse proxy
    location /api/ {
        proxy_pass http://app:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket reverse proxy
    location /ws/ {
        proxy_pass http://app:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_read_timeout 86400;
    }
}
```

- [ ] **Step 4: SSL 인증서 생성 스크립트**

```bash
#!/bin/bash
# deploy/ssl/generate-cert.sh
mkdir -p "$(dirname "$0")"
openssl req -x509 -nodes -days 365 \
    -newkey rsa:2048 \
    -keyout "$(dirname "$0")/key.pem" \
    -out "$(dirname "$0")/cert.pem" \
    -subj "/CN=paper-trader/O=Local/C=KR"
echo "Self-signed certificate generated."
```

- [ ] **Step 5: .env.example 생성**

```env
# deploy/.env.example
JWT_SECRET=change-me-to-random-string
INVITE_CODE=your-invite-code
ADMIN_EMAIL=admin@example.com
API_PORT=8001
WEB_PORT=443
HTTP_PORT=80
CORS_ORIGINS=https://192.168.102.150
```

- [ ] **Step 6: docker-build-guide.md 생성**

```markdown
# Docker Build & Deploy Guide

## 로컬에서 빌드

### API
docker build --platform linux/amd64 --target app -t agent-research-app:latest -f deploy/Dockerfile .

### Web
docker build --platform linux/amd64 --target web -t agent-research-web:latest \
  --build-arg VITE_API_URL=https://192.168.102.150 \
  --build-arg VITE_WS_URL=wss://192.168.102.150 \
  -f deploy/Dockerfile .

## 이미지 저장 & 전송

docker save agent-research-app:latest | gzip > agent-research-app.tar.gz
docker save agent-research-web:latest | gzip > agent-research-web.tar.gz

scp agent-research-*.tar.gz user@192.168.102.150:~/agent-research/

## 서버에서 실행

cd ~/agent-research
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz

# 초기 설정 (최초 1회)
cp deploy/.env.example .env
# .env 편집: JWT_SECRET, INVITE_CODE 설정
bash deploy/ssl/generate-cert.sh

# 실행
docker compose -f deploy/docker-compose.yml up -d

# 로그 확인
docker compose -f deploy/docker-compose.yml logs -f app

# 업데이트
docker compose -f deploy/docker-compose.yml down
docker load < agent-research-app.tar.gz
docker load < agent-research-web.tar.gz
docker compose -f deploy/docker-compose.yml up -d
```

- [ ] **Step 7: 커밋**

```bash
git add deploy/
git commit -m "feat: add Docker deployment files (Dockerfile, compose, nginx, ssl)"
```

---

## Task 17: health 엔드포인트 확인 및 구조 테스트

**Files:**
- Modify: `src/ui/api/server.py` (이미 /api/health 존재, 확인만)

- [ ] **Step 1: 구조 테스트 업데이트**

기존 `tests/structural/` 테스트가 새 파일들의 레이어 규칙을 검증하는지 확인.

Run: `uv run pytest tests/structural/ -v`
Expected: PASS (새 파일들이 레이어 규칙을 따르는지 확인)

- [ ] **Step 2: 린트 및 타입 체크**

Run: `uv run ruff check src/`
Run: `uv run mypy src/`
Expected: 오류 없음 (또는 기존 오류만)

- [ ] **Step 3: 전체 테스트**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: 커밋 (필요한 수정이 있으면)**

```bash
git add -A
git commit -m "fix: resolve lint/type/test issues from multi-user changes"
```

---

## Task 18: .gitignore 및 보안 파일 정리

**Files:**
- Modify: `.gitignore`

- [ ] **Step 1: .gitignore에 민감 파일 추가**

```
# Deploy secrets
deploy/.env
deploy/ssl/*.pem
*.tar.gz
```

- [ ] **Step 2: 커밋**

```bash
git add .gitignore
git commit -m "chore: add deploy secrets and images to gitignore"
```

---

## 실행 순서 요약

| Task | 내용 | 의존성 |
|------|------|--------|
| 1 | Python 의존성 추가 | 없음 |
| 2 | DB 스키마 변경 | 없음 |
| 3 | UserRepo 생성 | Task 2 |
| 4 | JWT 인증 모듈 | Task 1 |
| 5 | Auth API 라우터 | Task 3, 4 |
| 6 | Admin API 라우터 | Task 4 |
| 7 | Repository user_id 추가 | Task 2 |
| 8 | App 멀티유저 전환 | Task 3, 7 |
| 9 | API 라우터 인증 적용 | Task 4, 5, 6, 8 |
| 10 | 프론트엔드 훅 수정 | 없음 |
| 11 | 로그인/회원가입 페이지 | Task 10 |
| 12 | App.tsx 인증 가드 | Task 10, 11 |
| 13 | System 사용자 관리 | Task 12 |
| 14 | CSS 추가 | Task 11 |
| 15 | 설정 auth 섹션 | 없음 |
| 16 | Docker 배포 파일 | 없음 |
| 17 | 테스트 검증 | Task 1-15 |
| 18 | gitignore 정리 | 없음 |

**병렬 실행 가능 그룹:**
- Group A: Task 1, 2, 15, 16, 18 (독립)
- Group B: Task 3, 4, 7 (Task 1, 2 이후)
- Group C: Task 5, 6, 10 (Task 3, 4 이후)
- Group D: Task 8 (Task 3, 7 이후)
- Group E: Task 9, 11 (Task 5, 6, 8, 10 이후)
- Group F: Task 12, 14 (Task 10, 11 이후)
- Group G: Task 13 (Task 12 이후)
- Group H: Task 17 (모든 작업 이후)

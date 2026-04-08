from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

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
        "sub": str(user_id),
        "type": "access",
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def create_refresh_token(
    user_id: int,
    secret: str = JWT_SECRET,
    expires_delta: timedelta = REFRESH_TOKEN_EXPIRE,
) -> str:
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "exp": datetime.now(UTC) + expires_delta,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def decode_token(token: str, secret: str = JWT_SECRET) -> dict:
    try:
        payload = jwt.decode(token, secret, algorithms=["HS256"])
    except jwt.ExpiredSignatureError as exc:
        raise ValueError("Token expired") from exc
    except jwt.InvalidTokenError as exc:
        raise ValueError("Invalid token") from exc
    # Convert sub back to int to maintain user_id as integer
    if "sub" in payload:
        try:
            payload["sub"] = int(payload["sub"])
        except (ValueError, TypeError):
            pass
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
        raise HTTPException(status_code=401, detail=str(e)) from e

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

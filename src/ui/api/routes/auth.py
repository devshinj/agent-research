from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from src.ui.api.auth import (
    INVITE_CODE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/info")
async def auth_info():
    return {"invite_required": bool(INVITE_CODE)}


class RegisterRequest(BaseModel):
    email: str
    password: str
    nickname: str
    invite_code: str = ""


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/register")
async def register(body: RegisterRequest, request: Request):
    if INVITE_CODE and body.invite_code != INVITE_CODE:
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
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Email already registered") from exc

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
        raise HTTPException(status_code=401, detail=str(e)) from e

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload["sub"]
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user or not user["is_active"]:
        raise HTTPException(status_code=401, detail="User not found or inactive")

    access_token = create_access_token(user_id)
    return {"access_token": access_token}

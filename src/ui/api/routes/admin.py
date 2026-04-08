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


class AdjustBalanceRequest(BaseModel):
    amount: str
    memo: str = ""


@router.get("/users")
async def list_users(request: Request):
    app = request.app.state.app
    users = await app.user_repo.list_all()
    result = []
    for u in users:
        balance = await app.user_repo.get_cash_balance(u["id"])
        result.append({
            "id": u["id"],
            "email": u["email"],
            "nickname": u["nickname"],
            "is_admin": bool(u["is_admin"]),
            "is_active": bool(u["is_active"]),
            "created_at": u["created_at"],
            "cash_balance": str(balance),
        })
    return result


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


@router.get("/users/{user_id}/settings")
async def get_user_settings(user_id: int, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    settings = await app.user_repo.get_settings(user_id)
    return settings


@router.patch("/users/{user_id}/settings")
async def update_user_settings(user_id: int, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    body = await request.json()
    allowed = {
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
        "max_daily_loss_pct", "max_position_pct", "max_open_positions",
        "initial_balance", "trading_enabled",
    }
    patches = {k: v for k, v in body.items() if k in allowed}
    if not patches:
        raise HTTPException(status_code=400, detail="No valid fields")
    await app.user_repo.update_settings(user_id, patches)
    if user_id in app.user_accounts:
        await app.load_user(user_id)
    return {"updated": list(patches.keys())}


@router.post("/users/{user_id}/balance")
async def adjust_balance(
    user_id: int,
    body: AdjustBalanceRequest,
    request: Request,
    admin: dict = Depends(require_admin),  # noqa: B008
):
    from decimal import Decimal, InvalidOperation

    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        amount = Decimal(body.amount)
    except InvalidOperation as exc:
        raise HTTPException(status_code=400, detail="Invalid amount") from exc

    try:
        result = await app.user_repo.adjust_balance(
            user_id=user_id,
            admin_id=admin["id"],
            amount=amount,
            memo=body.memo,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Sync runtime memory
    if user_id in app.user_accounts:
        app.user_accounts[user_id].cash_balance = result["balance_after"]

    return {
        "user_id": user_id,
        "balance_before": str(result["balance_before"]),
        "balance_after": str(result["balance_after"]),
        "amount": str(result["amount"]),
    }


@router.get("/users/{user_id}/balance-history")
async def get_balance_history(user_id: int, request: Request):
    app = request.app.state.app
    user = await app.user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    history = await app.user_repo.get_balance_history(user_id)
    return {"history": history}

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

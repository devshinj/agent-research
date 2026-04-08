from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.ui.api.auth import get_current_user

router = APIRouter()


@router.get("/status")
async def get_risk_status(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {
            "circuit_breaker_active": False,
            "consecutive_losses": 0,
            "daily_trades": 0,
            "daily_loss_pct": "0",
            "cooldown_until": None,
        }

    import time

    user_id = user["id"]
    rm = app.user_risk.get(user_id)
    if rm is None:
        return {
            "circuit_breaker_active": False,
            "consecutive_losses": 0,
            "daily_trades": 0,
            "daily_loss_pct": "0",
            "cooldown_until": None,
        }

    cooldown_active = rm._cooldown_until > time.time()
    return {
        "circuit_breaker_active": cooldown_active,
        "consecutive_losses": rm._consecutive_losses,
        "daily_trades": rm._daily_trades,
        "daily_loss_pct": str(rm._daily_loss),
        "cooldown_until": rm._cooldown_until if cooldown_active else None,
    }

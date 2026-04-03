from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/status")
async def get_risk_status(request: Request) -> dict:
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

    rm = app.risk_manager
    cooldown_active = rm._cooldown_until > time.time()
    return {
        "circuit_breaker_active": cooldown_active,
        "consecutive_losses": rm._consecutive_losses,
        "daily_trades": rm._daily_trades,
        "daily_loss_pct": str(rm._daily_loss),
        "cooldown_until": rm._cooldown_until if cooldown_active else None,
    }

from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.post("/pause")
async def pause(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = True
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = False
    return {"status": "running"}

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from src.config.settings import Settings

router = APIRouter()

_CONFIG_PATH = Path("config/settings.yaml")


@router.post("/pause")
async def pause(request: Request) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = True
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = False
    return {"status": "running"}


@router.get("/config")
async def get_config(request: Request) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        result: dict[str, Any] = app.settings.to_dict()
        return result
    settings = Settings.from_yaml(_CONFIG_PATH)
    return settings.to_dict()


@router.post("/reset")
async def reset(request: Request) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)
    body = await request.json()
    new_settings = Settings.from_dict(body)

    # Write to YAML
    new_settings.to_yaml(_CONFIG_PATH)

    # Reset app state
    if app is not None:
        await app.reset(new_settings)

    return {"status": "running"}


@router.patch("/config")
async def patch_config(request: Request) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        raise HTTPException(status_code=503, detail="App not initialized")

    body = await request.json()

    try:
        updated_fields = app.hot_reload(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # Persist to YAML
    app.settings.to_yaml(_CONFIG_PATH)

    result: dict[str, Any] = {
        "status": "updated",
        "updated_fields": updated_fields,
        "config": app.settings.to_dict(),
    }
    return result

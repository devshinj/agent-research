from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request

from src.config.settings import Settings
from src.ui.api.auth import get_current_user, require_admin

router = APIRouter()

_CONFIG_PATH = Path("config/settings.yaml")


@router.post("/pause")
async def pause(request: Request, _: dict = Depends(require_admin)) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = True
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request, _: dict = Depends(require_admin)) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = False
    return {"status": "running"}


@router.post("/trading/start")
async def trading_start(
    request: Request, user: dict = Depends(get_current_user)
) -> dict[str, object]:
    app = getattr(request.app.state, "app", None)
    if not app:
        raise HTTPException(status_code=503, detail="Not ready")
    await app.user_repo.update_settings(user["id"], {"trading_enabled": 1})
    return {"trading_enabled": True}


@router.post("/trading/stop")
async def trading_stop(
    request: Request, user: dict = Depends(get_current_user)
) -> dict[str, object]:
    app = getattr(request.app.state, "app", None)
    if not app:
        raise HTTPException(status_code=503, detail="Not ready")
    await app.user_repo.update_settings(user["id"], {"trading_enabled": 0})
    return {"trading_enabled": False}


@router.get("/status")
async def get_status(
    request: Request, user: dict = Depends(get_current_user)
) -> dict[str, object]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"paused": True, "trading_enabled": False}
    settings = await app.user_repo.get_settings(user["id"])
    trading_enabled = bool(settings.get("trading_enabled", 0))
    return {
        "paused": app.paused,
        "trading_enabled": trading_enabled,
    }


@router.get("/config")
async def get_config(
    request: Request, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        result: dict[str, Any] = app.settings.to_dict()
        return result
    settings = Settings.from_yaml(_CONFIG_PATH)
    return settings.to_dict()


@router.post("/reset")
async def reset(
    request: Request, _: dict = Depends(require_admin)
) -> dict[str, str]:
    app = getattr(request.app.state, "app", None)

    # Reset app state using current settings (don't overwrite YAML)
    if app is not None:
        await app.reset(app.settings)

    return {"status": "running"}


@router.patch("/config")
async def patch_config(
    request: Request, _: dict = Depends(require_admin)
) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        raise HTTPException(status_code=503, detail="App not initialized")

    body = await request.json()

    try:
        updated_fields = app.hot_reload(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None

    # Persist only changed fields to YAML (merge, not overwrite)
    _merge_yaml(_CONFIG_PATH, body)

    result: dict[str, Any] = {
        "status": "updated",
        "updated_fields": updated_fields,
        "config": app.settings.to_dict(),
    }
    return result


@router.patch("/user-config")
async def patch_user_config(
    request: Request, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if not app:
        raise HTTPException(status_code=503, detail="Not ready")
    body = await request.json()
    allowed = {
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
        "max_daily_loss_pct", "max_position_pct", "max_open_positions",
    }
    patches = {k: v for k, v in body.items() if k in allowed}
    if not patches:
        raise HTTPException(status_code=400, detail="No valid fields")
    await app.user_repo.update_settings(user["id"], patches)
    await app.load_user(user["id"])
    return {"updated": list(patches.keys())}


def _merge_yaml(path: Path, patch: dict[str, Any]) -> None:
    """Read existing YAML, merge patch into it, write back."""
    if path.exists():
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
    else:
        data = {}

    for section, values in patch.items():
        if isinstance(values, dict) and isinstance(data.get(section), dict):
            data[section].update(values)
        else:
            data[section] = values

    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

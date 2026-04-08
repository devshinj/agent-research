from __future__ import annotations

import json
import time
from datetime import UTC, datetime, timezone, timedelta
from typing import Any

from fastapi import APIRouter, Depends, Request

from src.ui.api.auth import get_current_user

router = APIRouter()


@router.get("/screening")
async def get_screening(
    request: Request, user: dict = Depends(get_current_user)
) -> list[dict[str, Any]]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    if not app.screened_markets or not app.collector.markets:
        return []

    tickers = await app.upbit.fetch_tickers(app.collector.markets)
    results = app.screener.screen(tickers, app.collector.korean_names)
    return [
        {
            "market": r.market,
            "korean_name": r.korean_name,
            "price": str(r.price),
            "volume_krw": str(r.volume_krw),
            "volatility_pct": str(r.volatility),
            "score": float(r.score),
        }
        for r in results
    ]


@router.get("/signals")
async def get_signals(
    request: Request,
    limit: int = 50,
    include_hold: bool = False,
    user: dict = Depends(get_current_user),
) -> list[dict[str, Any]]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    rows = await app.signal_repo.get_recent(limit=limit, include_hold=include_hold)
    screened = set(app.screened_markets) if app.screened_markets else set()
    return [
        {
            "market": r["market"],
            "signal_type": r["signal_type"],
            "confidence": r["confidence"],
            "created_at": datetime.fromtimestamp(
                r["timestamp"], tz=timezone(timedelta(hours=9)),
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "basis": json.loads(r["basis"]) if r.get("basis") else None,
        }
        for r in rows
        if not screened or r["market"] in screened
    ]


@router.get("/model-status")
async def get_model_status(
    request: Request, user: dict = Depends(get_current_user)
) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"models": {}, "last_retrain": None, "next_retrain_hours": None}

    models = {}
    last_retrain: str | None = None
    last_retrain_epoch: int = 0

    for market in app.predictor._models:
        meta = app.predictor.get_model_meta(market)
        accuracy = meta.get("accuracy", 0)
        n_train = meta.get("n_train", 0)
        n_val = meta.get("n_val", 0)
        timestamp = meta.get("timestamp", "")

        last_train = ""
        if timestamp:
            last_train = (
                f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
                f" {timestamp[9:11]}:{timestamp[11:13]}"
            )
            if last_retrain is None or timestamp > (last_retrain or ""):
                last_retrain = timestamp

        # Signal stats from DB
        stats = await app.signal_repo.get_stats_by_market(market)

        models[market] = {
            "accuracy": accuracy,
            "last_train": last_train,
            "n_train": n_train,
            "n_val": n_val,
            "total_signals": stats["total_signals"],
            "buy_count": stats["buy_count"],
            "sell_count": stats["sell_count"],
            "hold_count": stats["hold_count"],
            "avg_confidence": stats["avg_confidence"],
        }

    formatted_retrain: str | None = None
    if last_retrain:
        formatted_retrain = (
            f"{last_retrain[:4]}-{last_retrain[4:6]}-{last_retrain[6:8]}"
            f" {last_retrain[9:11]}:{last_retrain[11:13]}"
        )
        try:
            dt = datetime(
                int(last_retrain[:4]), int(last_retrain[4:6]),
                int(last_retrain[6:8]), int(last_retrain[9:11]),
                int(last_retrain[11:13]), tzinfo=UTC,
            )
            last_retrain_epoch = int(dt.timestamp())
        except (ValueError, IndexError):
            last_retrain_epoch = 0

    next_retrain_hours: float | None = None
    if last_retrain_epoch > 0:
        retrain_interval_s = app.settings.strategy.retrain_interval_hours * 3600
        next_retrain_epoch = last_retrain_epoch + retrain_interval_s
        remaining_s = next_retrain_epoch - int(time.time())
        next_retrain_hours = round(max(0, remaining_s / 3600), 1)

    # Training-in-progress info
    now = time.time()
    training: dict[str, float] = {}
    for market, started_at in app.training_in_progress.items():
        training[market] = round(now - started_at, 1)

    return {
        "models": models,
        "last_retrain": formatted_retrain,
        "next_retrain_hours": next_retrain_hours,
        "training": training,
    }

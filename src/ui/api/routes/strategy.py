from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/screening")
async def get_screening(request: Request) -> list:
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
            "volume_krw": str(r.volume_krw),
            "volatility_pct": str(r.volatility * 100),
            "score": str(r.score),
        }
        for r in results
    ]


@router.get("/signals")
async def get_signals(request: Request) -> list:
    # Signals are ephemeral events; return empty until we add a signal log
    return []


@router.get("/model-status")
async def get_model_status(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"models": {}, "last_retrain": None}

    models = {}
    for market, model in app.predictor._models.items():
        models[market] = {"loaded": True}

    return {"models": models, "last_retrain": None}

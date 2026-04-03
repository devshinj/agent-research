from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/markets")
async def get_markets(request: Request) -> list[dict[str, str]]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []
    names = app.collector.korean_names
    return [
        {"market": m, "korean_name": names.get(m, m.replace("KRW-", ""))}
        for m in app.screened_markets
    ]


@router.get("/candles")
async def get_candles(request: Request, market: str, limit: int = 200) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    timeframe = f"{app.settings.collector.candle_timeframe}m"
    candles = await app.candle_repo.get_latest(market, timeframe, limit=limit)

    return [
        {
            "timestamp": c.timestamp,
            "open": str(c.open),
            "high": str(c.high),
            "low": str(c.low),
            "close": str(c.close),
            "volume": str(c.volume),
        }
        for c in reversed(candles)
    ]


@router.get("/summary")
async def get_summary(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {
            "total_equity": "10000000",
            "cash_balance": "10000000",
            "daily_pnl": "0",
            "total_return_pct": "0",
            "open_positions": 0,
        }

    account = app.account
    # Get current prices for equity calculation
    current_prices: dict = {}
    if account.positions:
        tickers = await app.upbit.fetch_tickers(list(account.positions.keys()))
        for t in tickers:
            current_prices[t["market"]] = t["price"]

    total_equity = app.portfolio_manager.calculate_total_equity(account, current_prices)
    daily_pnl = total_equity - account.initial_balance
    if account.initial_balance:
        total_return_pct = (total_equity - account.initial_balance) / account.initial_balance * 100
    else:
        total_return_pct = 0

    return {
        "total_equity": str(total_equity),
        "cash_balance": str(account.cash_balance),
        "daily_pnl": str(daily_pnl),
        "total_return_pct": str(total_return_pct),
        "open_positions": len(account.positions),
    }

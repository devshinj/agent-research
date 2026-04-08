from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from src.ui.api.auth import get_current_user

router = APIRouter()


@router.get("/markets")
async def get_markets(
    request: Request, user: dict = Depends(get_current_user)
) -> list[dict[str, str]]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []
    names = app.collector.korean_names
    return [
        {"market": m, "korean_name": names.get(m, m.replace("KRW-", ""))}
        for m in app.screened_markets
    ]


@router.get("/candles")
async def get_candles(
    request: Request,
    market: str,
    limit: int = 200,
    timeframe: str | None = None,
    user: dict = Depends(get_current_user),
) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    # For timeframes we don't cache, fetch directly from Upbit
    if timeframe == "1D":
        candles = await app.upbit.fetch_daily_candles(market, count=limit)
    elif timeframe is not None and int(timeframe) != app.settings.collector.candle_timeframe:
        candles = await app.upbit.fetch_candles(market, timeframe=int(timeframe), count=limit)
    else:
        tf_str = f"{app.settings.collector.candle_timeframe}m"
        candles = await app.candle_repo.get_latest(market, tf_str, limit=limit)

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
async def get_summary(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {
            "total_equity": "10000000",
            "cash_balance": "10000000",
            "daily_pnl": "0",
            "total_pnl": "0",
            "total_return_pct": "0",
            "open_positions": 0,
            "initial_balance": "10000000",
        }

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {
            "total_equity": "10000000",
            "cash_balance": "10000000",
            "daily_pnl": "0",
            "total_pnl": "0",
            "total_return_pct": "0",
            "open_positions": 0,
            "initial_balance": "10000000",
        }

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

    # Total unrealized PnL = equity - initial_balance
    total_pnl = total_equity - account.initial_balance

    # Truncate KRW values to integers — real exchanges never settle fractional won
    from decimal import ROUND_DOWN
    total_equity_int = total_equity.to_integral_value(rounding=ROUND_DOWN)
    cash_int = account.cash_balance.to_integral_value(rounding=ROUND_DOWN)
    pnl_int = daily_pnl.to_integral_value(rounding=ROUND_DOWN)
    total_pnl_int = total_pnl.to_integral_value(rounding=ROUND_DOWN)

    initial_int = account.initial_balance.to_integral_value(rounding=ROUND_DOWN)

    settings = await app.user_repo.get_settings(user_id)
    trading_enabled = bool(settings.get("trading_enabled", 0))

    return {
        "total_equity": str(total_equity_int),
        "cash_balance": str(cash_int),
        "daily_pnl": str(pnl_int),
        "total_pnl": str(total_pnl_int),
        "total_return_pct": str(total_return_pct),
        "open_positions": len(account.positions),
        "initial_balance": str(initial_int),
        "trading_enabled": trading_enabled,
    }

from __future__ import annotations

from decimal import ROUND_DOWN, Decimal

from fastapi import APIRouter, Request

router = APIRouter()


def _truncate_krw(value: Decimal) -> Decimal:
    return value.to_integral_value(rounding=ROUND_DOWN)


@router.get("/positions")
async def get_positions(request: Request) -> list:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    korean_names: dict[str, str] = app.collector.korean_names
    account = app.account
    current_prices: dict = {}
    if account.positions:
        tickers = await app.upbit.fetch_tickers(list(account.positions.keys()))
        for t in tickers:
            current_prices[t["market"]] = t["price"]

    result = []
    for market, pos in account.positions.items():
        current_price = current_prices.get(market, pos.entry_price)
        app.portfolio_manager.update_position(pos, current_price)
        pnl_pct = (
            (current_price - pos.entry_price) / pos.entry_price * 100
            if pos.entry_price else 0
        )
        eval_amount = _truncate_krw(current_price * pos.quantity)
        unrealized_krw = _truncate_krw(
            (current_price - pos.entry_price) * pos.quantity
        )
        result.append({
            "market": market,
            "korean_name": korean_names.get(market, market.replace("KRW-", "")),
            "quantity": str(pos.quantity),
            "avg_price": str(pos.entry_price),
            "current_price": str(current_price),
            "unrealized_pnl": str(unrealized_krw),
            "pnl_pct": str(pnl_pct),
            "eval_amount": str(eval_amount),
            "add_count": pos.add_count,
            "total_invested": str(_truncate_krw(pos.total_invested)),
            "partial_sold": pos.partial_sold,
            "highest_price": str(pos.highest_price),
        })
    return result


@router.get("/history")
async def get_history(request: Request, page: int = 1, size: int = 20) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"items": [], "page": page, "size": size, "total": 0}

    korean_names: dict[str, str] = app.collector.korean_names
    orders = await app.order_repo.get_recent(limit=size * page)
    start = (page - 1) * size
    page_orders = orders[start:start + size]

    items = []
    for o in page_orders:
        fill_price = o.fill_price or o.price
        total_amount = _truncate_krw(fill_price * o.quantity)
        # filled_at can be None for unfilled orders; fall back to created_at
        filled_ts: int = o.filled_at if o.filled_at is not None else o.created_at
        items.append({
            "id": o.id,
            "filled_at": filled_ts,
            "market": o.market,
            "korean_name": korean_names.get(o.market, o.market.replace("KRW-", "")),
            "side": o.side.value,
            "quantity": str(o.quantity),
            "price": str(fill_price),
            "total_amount": str(total_amount),
        })

    total = await app.order_repo.count_since(0)
    return {"items": items, "page": page, "size": size, "total": total}


@router.get("/daily")
async def get_daily(request: Request, period: str = "24h") -> list:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    from datetime import date, timedelta

    today = date.today()
    if period == "week":
        start = today - timedelta(days=7)
    elif period == "month":
        start = today - timedelta(days=30)
    elif period == "day":
        start = today - timedelta(days=1)
    else:  # "24h" default
        start = today - timedelta(days=1)

    summaries = await app.portfolio_repo.get_daily_summaries(
        start.isoformat(), today.isoformat()
    )
    return [
        {
            "date": s.date,
            "equity": str(_truncate_krw(s.ending_balance)),
            "pnl": str(_truncate_krw(s.realized_pnl)),
        }
        for s in summaries
    ]

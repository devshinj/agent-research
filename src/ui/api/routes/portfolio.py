from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/positions")
async def get_positions(request: Request) -> list:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

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
        result.append({
            "market": market,
            "side": pos.side.value,
            "quantity": str(pos.quantity),
            "avg_price": str(pos.entry_price),
            "current_price": str(current_price),
            "unrealized_pnl": str(pos.unrealized_pnl),
            "pnl_pct": str(pnl_pct),
        })
    return result


@router.get("/history")
async def get_history(request: Request, page: int = 1, size: int = 20) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"items": [], "page": page, "size": size, "total": 0}

    orders = await app.order_repo.get_recent(limit=size * page)
    start = (page - 1) * size
    page_orders = orders[start:start + size]

    items = []
    for o in page_orders:
        items.append({
            "time": o.created_at,
            "market": o.market,
            "side": o.side.value,
            "quantity": str(o.quantity),
            "price": str(o.fill_price or o.price),
        })

    total = await app.order_repo.count_since(0)
    return {"items": items, "page": page, "size": size, "total": total}


@router.get("/daily")
async def get_daily(request: Request) -> list:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    summaries = await app.portfolio_repo.get_daily_summaries("2000-01-01", "2099-12-31")
    return [
        {
            "date": s.date,
            "equity": str(s.ending_balance),
            "pnl": str(s.realized_pnl),
        }
        for s in summaries
    ]

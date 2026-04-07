from __future__ import annotations

from decimal import Decimal

from fastapi import APIRouter, Request
from pydantic import BaseModel

router = APIRouter()


class BuyRequest(BaseModel):
    market: str
    amount_krw: str


class SellRequest(BaseModel):
    market: str
    fraction: str


class ModeRequest(BaseModel):
    trade_mode: str


class ExitOrdersRequest(BaseModel):
    stop_loss_price: str | None = None
    take_profit_price: str | None = None


@router.get("/markets")
async def get_exchange_markets(request: Request) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    names = app.collector.korean_names
    screened = set(app.screened_markets)
    snapshot = app.upbit_ws.get_snapshot()

    result = []
    for market in app.collector.markets:
        ticker = snapshot.get(market, {})
        result.append({
            "market": market,
            "korean_name": names.get(market, market.replace("KRW-", "")),
            "price": str(ticker.get("price", "0")),
            "change": ticker.get("change", "EVEN"),
            "change_rate": str(ticker.get("change_rate", "0")),
            "acc_trade_price_24h": str(ticker.get("acc_trade_price_24h", "0")),
            "is_screened": market in screened,
        })

    result.sort(key=lambda x: (not x["is_screened"], -float(x["acc_trade_price_24h"] or "0")))
    return result


@router.post("/buy")
async def manual_buy(request: Request, body: BuyRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    amount = Decimal(body.amount_krw)

    if amount < app.settings.paper_trading.min_order_krw:
        return {"success": False, "error": f"최소 주문 금액({app.settings.paper_trading.min_order_krw}원) 미달"}

    existing = app.account.positions.get(body.market)
    if existing is None and len(app.account.positions) >= app.settings.paper_trading.max_open_positions:
        return {"success": False, "error": "포지션 한도 도달"}

    if amount > app.account.cash_balance:
        return {"success": False, "error": "잔고 부족"}

    price = app.upbit_ws.get_price(body.market)
    if price is None:
        tickers = await app.upbit.fetch_tickers([body.market])
        if not tickers:
            return {"success": False, "error": "가격 조회 실패"}
        price = tickers[0]["price"]

    order = app.paper_engine.execute_buy(
        app.account, body.market, price, amount, 0.0, reason="MANUAL",
    )
    await app.order_repo.save(order)
    app.risk_manager.record_trade()
    await app._save_state()
    app._ws_outbox.append({
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })

    pos = app.account.positions.get(body.market)
    return {
        "success": True,
        "order": {
            "id": order.id,
            "market": order.market,
            "side": order.side.value,
            "price": str(order.fill_price),
            "quantity": str(order.quantity),
            "fee": str(order.fee),
            "reason": order.reason,
        },
        "position": _serialize_position(pos) if pos else None,
    }


@router.post("/sell")
async def manual_sell(request: Request, body: SellRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if body.market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = app.account.positions[body.market]
    entry_price = position.entry_price
    quantity = position.quantity
    fraction = Decimal(body.fraction)

    price = app.upbit_ws.get_price(body.market)
    if price is None:
        tickers = await app.upbit.fetch_tickers([body.market])
        if not tickers:
            return {"success": False, "error": "가격 조회 실패"}
        price = tickers[0]["price"]

    if fraction >= Decimal("1"):
        order = app.paper_engine.execute_sell(app.account, body.market, price, "MANUAL")
    else:
        order = app.paper_engine.execute_partial_sell(
            app.account, body.market, price, fraction, reason="MANUAL",
        )

    await app.order_repo.save(order)
    app.risk_manager.record_trade()
    assert order.fill_price is not None
    app._record_trade_result(entry_price, order.fill_price, quantity if fraction >= Decimal("1") else order.quantity)
    await app._save_state()
    app._ws_outbox.append({
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })

    pos = app.account.positions.get(body.market)
    return {
        "success": True,
        "order": {
            "id": order.id,
            "market": order.market,
            "side": order.side.value,
            "price": str(order.fill_price),
            "quantity": str(order.quantity),
            "fee": str(order.fee),
            "reason": order.reason,
        },
        "position": _serialize_position(pos) if pos else None,
    }


@router.patch("/position/{market}/mode")
async def update_position_mode(request: Request, market: str, body: ModeRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    if body.trade_mode not in ("AUTO", "MANUAL"):
        return {"success": False, "error": "유효하지 않은 모드"}

    position = app.account.positions[market]
    position.trade_mode = body.trade_mode

    if body.trade_mode == "AUTO":
        position.stop_loss_price = None
        position.take_profit_price = None

    await app._save_state()
    return {"success": True, "position": _serialize_position(position)}


@router.patch("/position/{market}/exit-orders")
async def update_exit_orders(request: Request, market: str, body: ExitOrdersRequest) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    if market not in app.account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = app.account.positions[market]
    position.stop_loss_price = Decimal(body.stop_loss_price) if body.stop_loss_price else None
    position.take_profit_price = Decimal(body.take_profit_price) if body.take_profit_price else None
    await app._save_state()
    return {"success": True, "position": _serialize_position(position)}


def _serialize_position(pos) -> dict:  # type: ignore[type-arg]
    return {
        "market": pos.market,
        "entry_price": str(pos.entry_price),
        "quantity": str(pos.quantity),
        "unrealized_pnl": str(pos.unrealized_pnl),
        "add_count": pos.add_count,
        "total_invested": str(pos.total_invested),
        "partial_sold": pos.partial_sold,
        "trade_mode": pos.trade_mode,
        "stop_loss_price": str(pos.stop_loss_price) if pos.stop_loss_price else None,
        "take_profit_price": str(pos.take_profit_price) if pos.take_profit_price else None,
    }

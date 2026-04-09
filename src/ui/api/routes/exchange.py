from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from src.types.models import PendingOrder
from src.ui.api.auth import get_current_user

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


class LimitBuyRequest(BaseModel):
    market: str
    limit_price: str
    amount_krw: str


@router.get("/markets")
async def get_exchange_markets(
    request: Request, user: dict = Depends(get_current_user)
) -> list[dict]:
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
async def manual_buy(
    request: Request, body: BuyRequest, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    risk_manager = app.user_risk.get(user_id)
    if risk_manager is None:
        return {"success": False, "error": "Risk manager not found"}

    amount = Decimal(body.amount_krw)

    if amount < app.settings.paper_trading.min_order_krw:
        return {"success": False, "error": f"최소 주문 금액({app.settings.paper_trading.min_order_krw}원) 미달"}

    existing = account.positions.get(body.market)
    if existing is None and len(account.positions) >= app.settings.paper_trading.max_open_positions:
        return {"success": False, "error": "포지션 한도 도달"}

    safe_max = app.paper_engine.safe_buy_amount(account.cash_balance)
    if amount > safe_max:
        return {"success": False, "error": f"잔고 부족 (수수료 포함 최대 {safe_max:,.0f}원)"}

    price = app.upbit_ws.get_price(body.market)
    if price is None:
        tickers = await app.upbit.fetch_tickers([body.market])
        if not tickers:
            return {"success": False, "error": "가격 조회 실패"}
        price = tickers[0]["price"]

    order = app.paper_engine.execute_buy(
        account, body.market, price, amount, 0.0, reason="MANUAL",
    )
    await app.order_repo.save(order, user_id)
    risk_manager.record_trade()
    await app.notification_repo.save(
        user_id, body.market, "BUY", "SUCCESS",
        f"수동 매수 완료 — {int(amount):,}원",
    )
    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })

    pos = account.positions.get(body.market)
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
async def manual_sell(
    request: Request, body: SellRequest, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    risk_manager = app.user_risk.get(user_id)
    if risk_manager is None:
        return {"success": False, "error": "Risk manager not found"}

    if body.market not in account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = account.positions[body.market]
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
        order = app.paper_engine.execute_sell(account, body.market, price, "MANUAL")
    else:
        order = app.paper_engine.execute_partial_sell(
            account, body.market, price, fraction, reason="MANUAL",
        )

    await app.order_repo.save(order, user_id)
    risk_manager.record_trade()
    assert order.fill_price is not None
    app._record_trade_result_for_user(user_id, entry_price, order.fill_price, quantity if fraction >= Decimal("1") else order.quantity)
    pnl_pct = (price - entry_price) / entry_price * 100
    await app.notification_repo.save(
        user_id, body.market, "SELL", "SUCCESS",
        f"수동 매도 완료 — 수익률 {float(pnl_pct):+.1f}%",
    )
    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "order_filled",
        "data": {
            "market": order.market,
            "side": order.side.value,
            "reason": order.reason,
            "price": str(order.fill_price),
        },
    })

    pos = account.positions.get(body.market)
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
async def update_position_mode(
    request: Request, market: str, body: ModeRequest, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    if market not in account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    if body.trade_mode not in ("AUTO", "MANUAL"):
        return {"success": False, "error": "유효하지 않은 모드"}

    position = account.positions[market]
    position.trade_mode = body.trade_mode

    if body.trade_mode == "AUTO":
        position.stop_loss_price = None
        position.take_profit_price = None

    await app._save_user_state(user_id)
    return {"success": True, "position": _serialize_position(position)}


@router.patch("/position/{market}/exit-orders")
async def update_exit_orders(
    request: Request, market: str, body: ExitOrdersRequest, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    if market not in account.positions:
        return {"success": False, "error": "보유하지 않은 코인입니다"}

    position = account.positions[market]
    position.stop_loss_price = Decimal(body.stop_loss_price) if body.stop_loss_price else None
    position.take_profit_price = Decimal(body.take_profit_price) if body.take_profit_price else None
    await app._save_user_state(user_id)
    return {"success": True, "position": _serialize_position(position)}


@router.get("/max-buy-amount")
async def max_buy_amount(
    request: Request, user: dict = Depends(get_current_user)
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"amount": "0", "cash_balance": "0", "fee_rate": "0", "slippage_rate": "0"}
    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"amount": "0", "cash_balance": "0", "fee_rate": "0", "slippage_rate": "0"}
    safe = app.paper_engine.safe_buy_amount(account.cash_balance)
    pt = app.settings.paper_trading
    return {
        "amount": str(safe),
        "cash_balance": str(account.cash_balance),
        "fee_rate": str(pt.fee_rate),
        "slippage_rate": str(pt.slippage_rate),
    }


def _end_of_day_kst() -> int:
    """Return Unix timestamp for 23:59:59 KST today."""
    kst = timezone(timedelta(hours=9))
    now_kst = datetime.now(kst)
    eod = now_kst.replace(hour=23, minute=59, second=59, microsecond=0)
    return int(eod.timestamp())


@router.post("/limit-buy")
async def create_limit_buy(
    request: Request, body: LimitBuyRequest, user: dict = Depends(get_current_user),
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    amount = Decimal(body.amount_krw)
    limit_price = Decimal(body.limit_price)

    if limit_price <= 0:
        return {"success": False, "error": "지정가는 0보다 커야 합니다"}

    if amount < app.settings.paper_trading.min_order_krw:
        return {"success": False, "error": f"최소 주문 금액({app.settings.paper_trading.min_order_krw}원) 미달"}

    safe_max = app.paper_engine.safe_buy_amount(account.cash_balance)
    if amount > safe_max:
        return {"success": False, "error": f"잔고 부족 (수수료 포함 최대 {safe_max:,.0f}원)"}

    existing = account.positions.get(body.market)
    if existing is None and len(account.positions) >= app.settings.paper_trading.max_open_positions:
        return {"success": False, "error": "포지션 한도 도달"}

    now = int(time.time())
    pending_order = PendingOrder(
        id=str(uuid.uuid4()),
        user_id=user_id,
        market=body.market,
        side="BUY",
        limit_price=limit_price,
        amount_krw=amount,
        status="PENDING",
        created_at=now,
        expires_at=_end_of_day_kst(),
    )

    await app.pending_order_repo.create(pending_order, account)
    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "pending_order_placed",
        "data": {
            "order_id": pending_order.id,
            "market": pending_order.market,
            "limit_price": str(pending_order.limit_price),
            "amount_krw": str(pending_order.amount_krw),
        },
    })

    return {
        "success": True,
        "pending_order": {
            "id": pending_order.id,
            "market": pending_order.market,
            "limit_price": str(pending_order.limit_price),
            "amount_krw": str(pending_order.amount_krw),
            "status": pending_order.status,
            "created_at": pending_order.created_at,
            "expires_at": pending_order.expires_at,
        },
    }


@router.delete("/limit-buy/{order_id}")
async def cancel_limit_buy(
    request: Request, order_id: str, user: dict = Depends(get_current_user),
) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"success": False, "error": "App not running"}

    user_id = user["id"]
    account = app.user_accounts.get(user_id)
    if account is None:
        return {"success": False, "error": "User account not found"}

    result = await app.pending_order_repo.cancel(order_id, account, user_id)
    if not result:
        return {"success": False, "error": "주문을 찾을 수 없거나 이미 처리되었습니다"}

    await app._save_user_state(user_id)
    app._push_ws_message(user_id, {
        "type": "pending_order_cancelled",
        "data": {"order_id": order_id},
    })
    return {"success": True}


@router.get("/pending-orders")
async def get_pending_orders(
    request: Request, user: dict = Depends(get_current_user),
) -> list[dict]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    user_id = user["id"]
    orders = await app.pending_order_repo.get_pending_by_user(user_id)
    return [
        {
            "id": o.id,
            "market": o.market,
            "limit_price": str(o.limit_price),
            "amount_krw": str(o.amount_krw),
            "status": o.status,
            "created_at": o.created_at,
            "expires_at": o.expires_at,
        }
        for o in orders
    ]


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

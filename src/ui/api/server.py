from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.ui.api.auth import configure_auth, decode_token
from src.ui.api.routes import control, dashboard, exchange, portfolio, risk, strategy
from src.ui.api.routes import auth as auth_router
from src.ui.api.routes import admin as admin_router
from src.ui.api.routes import agent as agent_router
from src.ui.api.routes import ranking as ranking_router


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Paper Trader", version="0.1.0")

    origins = os.environ.get("CORS_ORIGINS", "*").split(",")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(auth_router.router)
    app.include_router(admin_router.router)
    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
    app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
    app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])
    app.include_router(exchange.router, prefix="/api/exchange", tags=["exchange"])
    app.include_router(agent_router.router, prefix="/api/agent", tags=["agent"])
    app.include_router(ranking_router.router, prefix="/api/ranking", tags=["ranking"])

    @app.on_event("startup")
    async def _configure_auth_on_startup() -> None:
        app_instance = getattr(app.state, "app", None)
        if app_instance:
            cfg = app_instance.settings.auth
            configure_auth(cfg.access_token_expire_minutes, cfg.refresh_token_expire_days)

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket) -> None:
        token = ws.query_params.get("token")
        if not token:
            await ws.close(code=4001, reason="Missing token")
            return
        try:
            payload = decode_token(token)
            if payload.get("type") != "access":
                raise ValueError("Invalid token type")
        except ValueError:
            await ws.close(code=4001, reason="Invalid token")
            return
        user_id = payload["sub"]
        await ws.accept()
        try:
            prev_snapshot: dict[str, dict] = {}
            while True:
                messages: list[dict] = [{"type": "heartbeat", "data": {}}]

                # Relay ticker deltas from Upbit WS
                app_instance = getattr(app.state, "app", None)
                if app_instance and hasattr(app_instance, "upbit_ws"):
                    snapshot = app_instance.upbit_ws.get_snapshot()
                    for market, ticker in snapshot.items():
                        prev = prev_snapshot.get(market)
                        if prev is None or prev.get("price") != ticker.get("price"):
                            messages.append({
                                "type": "ticker",
                                "data": {
                                    "market": ticker["market"],
                                    "price": str(ticker["price"]),
                                    "change": ticker["change"],
                                    "change_rate": str(ticker["change_rate"]),
                                    "change_price": str(ticker["change_price"]),
                                    "volume_24h": str(ticker.get("volume_24h", "0")),
                                    "acc_trade_price_24h": str(ticker.get("acc_trade_price_24h", "0")),
                                    "timestamp": ticker["timestamp"],
                                },
                            })
                    prev_snapshot = dict(snapshot)

                    # Relay WS connection status
                    messages.append({
                        "type": "ws_status",
                        "data": {"upbit": app_instance.upbit_ws.status},
                    })

                # Relay queued events (order fills, etc.)
                if app_instance and hasattr(app_instance, "_ws_outbox"):
                    for msg in app_instance._pop_ws_messages(user_id):
                        messages.append(msg)

                for msg in messages:
                    await ws.send_text(json.dumps(msg))
                await asyncio.sleep(0.5)
        except WebSocketDisconnect:
            if app_instance and hasattr(app_instance, "_clear_ws_outbox"):
                app_instance._clear_ws_outbox(user_id)

    return app

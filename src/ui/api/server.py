from __future__ import annotations

import asyncio
import json
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.ui.api.auth import decode_token
from src.ui.api.routes import control, dashboard, exchange, portfolio, risk, strategy
from src.ui.api.routes import auth as auth_router
from src.ui.api.routes import admin as admin_router


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
                    while app_instance._ws_outbox:
                        messages.append(app_instance._ws_outbox.pop(0))

                for msg in messages:
                    await ws.send_text(json.dumps(msg))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass

    return app

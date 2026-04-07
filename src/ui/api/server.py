from __future__ import annotations

import asyncio
import json

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from src.ui.api.routes import control, dashboard, portfolio, risk, strategy


def create_app() -> FastAPI:
    app = FastAPI(title="Crypto Paper Trader", version="0.1.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(dashboard.router, prefix="/api/dashboard", tags=["dashboard"])
    app.include_router(portfolio.router, prefix="/api/portfolio", tags=["portfolio"])
    app.include_router(strategy.router, prefix="/api/strategy", tags=["strategy"])
    app.include_router(risk.router, prefix="/api/risk", tags=["risk"])
    app.include_router(control.router, prefix="/api/control", tags=["control"])

    @app.get("/api/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.websocket("/ws/live")
    async def websocket_live(ws: WebSocket) -> None:
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

                for msg in messages:
                    await ws.send_text(json.dumps(msg))
                await asyncio.sleep(1)
        except WebSocketDisconnect:
            pass

    return app

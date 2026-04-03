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
            while True:
                await ws.send_text(json.dumps({
                    "type": "heartbeat",
                    "data": {},
                }))
                await asyncio.sleep(5)
        except WebSocketDisconnect:
            pass

    return app

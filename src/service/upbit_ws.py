from __future__ import annotations

import asyncio
import json
import logging
import time
from decimal import Decimal
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from src.service.upbit_client import UpbitClient

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
logger = logging.getLogger(__name__)


class UpbitWebSocketService:
    def __init__(self, upbit_client: UpbitClient | None = None) -> None:
        self._client = upbit_client
        self._cache: dict[str, dict[str, Any]] = {}
        self._ws: ClientConnection | None = None
        self._markets: list[str] = []
        self._running = False
        self._last_recv_time: float = 0
        self._reconnect_delay: float = 1.0
        self._max_reconnect_delay: float = 60.0
        self._consecutive_failures: int = 0
        self._fallback_polling = False
        self._poll_task: asyncio.Task[None] | None = None
        self.status: str = "disconnected"

    def _parse_ws_ticker(self, raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": str(raw["code"]),
            "price": Decimal(str(raw["trade_price"])),
            "change": str(raw["change"]),
            "change_rate": Decimal(str(raw["signed_change_rate"])),
            "change_price": Decimal(str(raw["signed_change_price"])),
            "volume_24h": Decimal(str(raw["acc_trade_volume_24h"])),
            "acc_trade_price_24h": Decimal(str(raw["acc_trade_price_24h"])),
            "timestamp": int(raw["timestamp"]) // 1000,
        }

    def get_snapshot(self) -> dict[str, dict[str, Any]]:
        return dict(self._cache)

    def get_price(self, market: str) -> Decimal | None:
        ticker = self._cache.get(market)
        return ticker["price"] if ticker else None

    async def start(self, markets: list[str]) -> None:
        self._markets = markets
        self._running = True
        asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        if self._ws:
            await self._ws.close()
            self._ws = None
        self.status = "disconnected"

    def update_markets(self, markets: list[str]) -> None:
        self._markets = markets

    async def _run_loop(self) -> None:
        while self._running:
            try:
                await self._connect_and_recv()
            except Exception as e:
                logger.warning("Upbit WS error: %s", e)
                self._consecutive_failures += 1
                if self._consecutive_failures >= 3 and not self._fallback_polling:
                    logger.info("Switching to REST polling fallback")
                    self._fallback_polling = True
                    self.status = "polling"
                    self._poll_task = asyncio.create_task(self._poll_loop())
                    return
                delay = min(
                    self._reconnect_delay * (2 ** (self._consecutive_failures - 1)),
                    self._max_reconnect_delay,
                )
                logger.info("Reconnecting in %.1fs...", delay)
                self.status = "disconnected"
                await asyncio.sleep(delay)

    async def _connect_and_recv(self) -> None:
        async with websockets.connect(UPBIT_WS_URL) as ws:
            self._ws = ws
            self._consecutive_failures = 0
            self._reconnect_delay = 1.0
            self.status = "connected"

            if self._fallback_polling:
                self._fallback_polling = False
                if self._poll_task and not self._poll_task.done():
                    self._poll_task.cancel()

            subscribe_msg = self._build_subscribe(self._markets)
            await ws.send(subscribe_msg)
            logger.info(
                "Upbit WS connected, subscribed to %d markets", len(self._markets)
            )

            self._last_recv_time = time.time()
            health_task = asyncio.create_task(self._health_check())

            try:
                async for message in ws:
                    self._last_recv_time = time.time()
                    if isinstance(message, bytes):
                        data = json.loads(message.decode("utf-8"))
                    else:
                        data = json.loads(message)

                    if data.get("type") == "ticker":
                        ticker = self._parse_ws_ticker(data)
                        self._cache[ticker["market"]] = ticker
            finally:
                health_task.cancel()

    async def _health_check(self) -> None:
        while self._running:
            await asyncio.sleep(10)
            if time.time() - self._last_recv_time > 30:
                logger.warning("No WS data for 30s, forcing reconnect")
                if self._ws:
                    await self._ws.close()
                return

    async def _poll_loop(self) -> None:
        while self._running and self._fallback_polling and self._client:
            try:
                if self._markets:
                    for i in range(0, len(self._markets), 100):
                        chunk = self._markets[i : i + 100]
                        tickers = await self._client.fetch_tickers(chunk)
                        for t in tickers:
                            market = t["market"]
                            self._cache[market] = {
                                "market": market,
                                "price": t["price"],
                                "change": "EVEN",
                                "change_rate": t["change_rate"],
                                "change_price": Decimal("0"),
                                "volume_24h": Decimal("0"),
                                "acc_trade_price_24h": t["volume_24h"],
                                "timestamp": t["timestamp"],
                            }
            except Exception as e:
                logger.warning("REST polling error: %s", e)
            await asyncio.sleep(10)

            try:
                async with websockets.connect(UPBIT_WS_URL) as ws:
                    logger.info("WS reconnected from polling fallback")
                    self._fallback_polling = False
                    self.status = "connected"
                    await ws.close()
                    asyncio.create_task(self._run_loop())
                    return
            except Exception:
                pass

    @staticmethod
    def _build_subscribe(markets: list[str]) -> str:
        payload = [
            {"ticket": "crypto-paper-trader-live"},
            {"type": "ticker", "codes": markets, "isOnlyRealtime": True},
            {"format": "DEFAULT"},
        ]
        return json.dumps(payload)

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import websockets

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

from src.types.models import Trade

logger = logging.getLogger(__name__)

UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"


class TickStream:
    def __init__(self, max_markets: int, reconnect_max_seconds: int) -> None:
        self._max_markets = max_markets
        self._reconnect_max_seconds = reconnect_max_seconds
        self._markets: list[str] = []
        self._ws: websockets.WebSocketClientProtocol | None = None  # type: ignore[name-defined]
        self._task: asyncio.Task[None] | None = None
        self._running = False
        self.on_tick: Callable[[Trade], Awaitable[None]] | None = None

    def _validate_markets(self, markets: list[str]) -> None:
        if len(markets) > self._max_markets:
            msg = f"Cannot subscribe to {len(markets)} markets (max_markets={self._max_markets})"
            raise ValueError(msg)

    async def start(self, markets: list[str]) -> None:
        self._validate_markets(markets)
        self._markets = list(markets)
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        logger.info("TickStream started for %s", markets)

    async def update_markets(self, markets: list[str]) -> None:
        self._validate_markets(markets)
        self._markets = list(markets)
        if self._ws is not None:
            msg = self.build_subscribe_message(self._markets)
            await self._ws.send(msg)
            logger.info("Updated subscription to %s", markets)

    async def stop(self) -> None:
        self._running = False
        if self._ws is not None:
            await self._ws.close()
            self._ws = None
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        logger.info("TickStream stopped")

    async def _run_loop(self) -> None:
        backoff = 1
        while self._running:
            try:
                async with websockets.connect(UPBIT_WS_URL) as ws:
                    self._ws = ws
                    backoff = 1  # reset on successful connect
                    msg = self.build_subscribe_message(self._markets)
                    await ws.send(msg)
                    logger.info("WebSocket connected, subscribed to %s", self._markets)

                    async for raw_msg in ws:
                        if not self._running:
                            break
                        try:
                            data = json.loads(raw_msg)
                            trade = self.parse_trade(data)
                            if self.on_tick is not None:
                                await self.on_tick(trade)
                        except (json.JSONDecodeError, KeyError):
                            logger.debug("Skipped unparseable message")
            except asyncio.CancelledError:
                break
            except Exception:
                self._ws = None
                if not self._running:
                    break
                logger.warning("WebSocket disconnected, reconnecting in %ds", backoff)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, self._reconnect_max_seconds)

    @staticmethod
    def parse_trade(raw: dict) -> Trade:  # type: ignore[type-arg]
        return Trade(
            market=str(raw["cd"]),
            price=Decimal(str(raw["tp"])),
            volume=Decimal(str(raw["tv"])),
            timestamp=int(raw["tms"]) // 1000,
            ask_bid=str(raw["ab"]),
        )

    @staticmethod
    def build_subscribe_message(markets: list[str]) -> str:
        return json.dumps([
            {"ticket": str(uuid.uuid4())},
            {"type": "trade", "codes": markets},
        ])

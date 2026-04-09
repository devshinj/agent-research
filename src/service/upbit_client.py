# src/service/upbit_client.py
from __future__ import annotations

import asyncio
import json
from decimal import Decimal
from typing import Any

import httpx

from src.types.models import Candle

UPBIT_REST_URL = "https://api.upbit.com/v1"
UPBIT_WS_URL = "wss://api.upbit.com/websocket/v1"
REST_RATE_LIMIT = 10  # requests per second


class UpbitClient:
    def __init__(self) -> None:
        self._http: httpx.AsyncClient | None = None
        self._semaphore = asyncio.Semaphore(REST_RATE_LIMIT)

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(
                base_url=UPBIT_REST_URL,
                timeout=10.0,
            )
        return self._http

    async def close(self) -> None:
        if self._http and not self._http.is_closed:
            await self._http.aclose()

    # ── REST API ──

    async def fetch_markets(self) -> tuple[list[str], dict[str, str]]:
        """Return (market_codes, {market_code: korean_name})."""
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get("/market/all", params={"isDetails": "false"})
            resp.raise_for_status()
        raw = resp.json()
        codes = self.filter_krw_markets(raw)
        names = self.extract_korean_names(raw)
        return codes, names

    async def fetch_candles(
        self, market: str, timeframe: int = 1, count: int = 200
    ) -> list[Candle]:
        client = await self._get_http()
        tf_str = f"{timeframe}m"
        if count <= 200:
            async with self._semaphore:
                resp = await client.get(
                    f"/candles/minutes/{timeframe}",
                    params={"market": market, "count": count},
                )
                resp.raise_for_status()
            return [self.parse_candle(raw, tf_str) for raw in resp.json()]

        # Paginate for count > 200
        all_candles: list[Candle] = []
        remaining = count
        to: str | None = None
        while remaining > 0:
            batch = min(remaining, 200)
            params: dict[str, str | int] = {"market": market, "count": batch}
            if to is not None:
                params["to"] = to
            async with self._semaphore:
                resp = await client.get(
                    f"/candles/minutes/{timeframe}", params=params,
                )
                resp.raise_for_status()
            rows = resp.json()
            if not rows:
                break
            all_candles.extend(self.parse_candle(raw, tf_str) for raw in rows)
            remaining -= len(rows)
            # Upbit returns newest first; last item is oldest — use its time as 'to'
            to = rows[-1]["candle_date_time_utc"] + "Z"
            await asyncio.sleep(0.11)  # rate limit
        return all_candles

    async def fetch_daily_candles(
        self, market: str, count: int = 200
    ) -> list[Candle]:
        client = await self._get_http()
        async with self._semaphore:
            resp = await client.get(
                "/candles/days",
                params={"market": market, "count": count},
            )
            resp.raise_for_status()
        return [self.parse_candle(raw, "1D") for raw in resp.json()]

    async def fetch_tickers(self, markets: list[str]) -> list[dict[str, Any]]:
        client = await self._get_http()
        for attempt in range(3):
            async with self._semaphore:
                resp = await client.get(
                    "/ticker",
                    params={"markets": ",".join(markets)},
                )
            if resp.status_code == 429:
                await asyncio.sleep(1.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            return [self.parse_ticker(raw) for raw in resp.json()]
        resp.raise_for_status()
        return []  # unreachable

    # ── Parsers ──

    @staticmethod
    def filter_krw_markets(raw_markets: list[dict[str, Any]]) -> list[str]:
        return [m["market"] for m in raw_markets if m["market"].startswith("KRW-")]

    @staticmethod
    def extract_korean_names(raw_markets: list[dict[str, Any]]) -> dict[str, str]:
        return {
            m["market"]: m["korean_name"]
            for m in raw_markets
            if m["market"].startswith("KRW-") and "korean_name" in m
        }

    @staticmethod
    def parse_candle(raw: dict[str, Any], timeframe: str) -> Candle:
        return Candle(
            market=str(raw["market"]),
            timeframe=timeframe,
            timestamp=int(raw["timestamp"]) // 1000,
            open=Decimal(str(raw["opening_price"])),
            high=Decimal(str(raw["high_price"])),
            low=Decimal(str(raw["low_price"])),
            close=Decimal(str(raw["trade_price"])),
            volume=Decimal(str(raw["candle_acc_trade_volume"])),
        )

    @staticmethod
    def parse_ticker(raw: dict[str, Any]) -> dict[str, Any]:
        return {
            "market": str(raw["market"]),
            "price": Decimal(str(raw["trade_price"])),
            "volume_24h": Decimal(str(raw["acc_trade_price_24h"])),
            "change_rate": Decimal(str(raw["signed_change_rate"])),
            "timestamp": int(raw["timestamp"]) // 1000,
        }

    # ── WebSocket ──

    @staticmethod
    def build_ws_subscribe_message(
        markets: list[str], types: list[str] | None = None
    ) -> str:
        if types is None:
            types = ["ticker"]
        payload: list[dict[str, Any]] = [{"ticket": "crypto-paper-trader"}]
        for t in types:
            payload.append({"type": t, "codes": markets})
        return json.dumps(payload)

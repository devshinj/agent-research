from __future__ import annotations

import asyncio
import logging

from src.repository.candle_repo import CandleRepository
from src.service.upbit_client import UpbitClient

logger = logging.getLogger(__name__)


class Collector:
    def __init__(
        self,
        upbit_client: UpbitClient,
        candle_repo: CandleRepository,
        timeframe: int,
        max_candles: int,
    ) -> None:
        self._client = upbit_client
        self._repo = candle_repo
        self._timeframe = timeframe
        self._max_candles = max_candles
        self._markets: list[str] = []
        self._korean_names: dict[str, str] = {}

    @property
    def markets(self) -> list[str]:
        return self._markets

    @property
    def korean_names(self) -> dict[str, str]:
        return self._korean_names

    async def refresh_markets(self) -> list[str]:
        self._markets, self._korean_names = await self._client.fetch_markets()
        logger.info("Refreshed markets: %d KRW markets found", len(self._markets))
        return self._markets

    async def collect_candles(self, markets: list[str]) -> None:
        for market in markets:
            try:
                candles = await self._client.fetch_candles(
                    market, self._timeframe, self._max_candles
                )
                if candles:
                    await self._repo.save_many(candles, commit=False)
                    logger.info("Collected %d candles for %s", len(candles), market)
            except Exception:
                logger.exception("Failed to collect candles for %s", market)
            await asyncio.sleep(0.11)  # rate limit: ~9 req/s
        await self._repo.commit()

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
        train_timeframe: int = 15,
        train_candles: int = 960,
        daily_candles: int = 30,
    ) -> None:
        self._client = upbit_client
        self._repo = candle_repo
        self._timeframe = timeframe
        self._max_candles = max_candles
        self._train_timeframe = train_timeframe
        self._train_candles = train_candles
        self._daily_candles = daily_candles
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
            await asyncio.sleep(0.11)
        await self._repo.commit()

    async def collect_train_candles(self, markets: list[str]) -> None:
        """15분봉 + 일봉 수집 (학습용)."""
        for market in markets:
            try:
                candles_15m = await self._client.fetch_candles(
                    market, self._train_timeframe, self._train_candles
                )
                if candles_15m:
                    await self._repo.save_many(candles_15m, commit=False)
                    logger.info(
                        "Collected %d %dm candles for %s",
                        len(candles_15m),
                        self._train_timeframe,
                        market,
                    )
            except Exception:
                logger.exception(
                    "Failed to collect %dm candles for %s",
                    self._train_timeframe,
                    market,
                )

            try:
                candles_daily = await self._client.fetch_daily_candles(
                    market, self._daily_candles
                )
                if candles_daily:
                    await self._repo.save_many(candles_daily, commit=False)
                    logger.info(
                        "Collected %d daily candles for %s",
                        len(candles_daily),
                        market,
                    )
            except Exception:
                logger.exception(
                    "Failed to collect daily candles for %s", market
                )

            await asyncio.sleep(0.11)
        await self._repo.commit()

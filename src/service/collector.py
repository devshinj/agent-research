from __future__ import annotations

import asyncio
import logging
from typing import Sequence

from src.config.settings import ContextTimeframe
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
        train_timeframe: int = 5,
        train_candles: int = 2880,
        daily_candles: int = 30,
        context_timeframes: Sequence[ContextTimeframe] = (),
    ) -> None:
        self._client = upbit_client
        self._repo = candle_repo
        self._timeframe = timeframe
        self._max_candles = max_candles
        self._train_timeframe = train_timeframe
        self._train_candles = train_candles
        self._daily_candles = daily_candles
        self._context_timeframes = list(context_timeframes)
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
        """학습용 메인 타임프레임 + 일봉 수집."""
        for market in markets:
            try:
                candles = await self._client.fetch_candles(
                    market, self._train_timeframe, self._train_candles
                )
                if candles:
                    await self._repo.save_many(candles, commit=False)
                    logger.info(
                        "Collected %d %dm candles for %s",
                        len(candles), self._train_timeframe, market,
                    )
            except Exception:
                logger.exception("Failed to collect %dm candles for %s", self._train_timeframe, market)

            try:
                daily = await self._client.fetch_daily_candles(market, self._daily_candles)
                if daily:
                    await self._repo.save_many(daily, commit=False)
            except Exception:
                logger.exception("Failed to collect daily candles for %s", market)

            await asyncio.sleep(0.11)
        await self._repo.commit()

    async def collect_context_candles(
        self, markets: list[str], interval_sec: int,
    ) -> None:
        """특정 interval_sec에 해당하는 context 타임프레임 수집."""
        targets = [ct for ct in self._context_timeframes if ct.interval_sec == interval_sec]
        if not targets:
            return

        for market in markets:
            for ct in targets:
                try:
                    candles = await self._client.fetch_candles(
                        market, ct.minutes, ct.candles
                    )
                    if candles:
                        await self._repo.save_many(candles, commit=False)
                except Exception:
                    logger.exception(
                        "Failed to collect %dm candles for %s", ct.minutes, market,
                    )
                await asyncio.sleep(0.11)
        await self._repo.commit()

    async def collect_all_context(self, markets: list[str]) -> None:
        """모든 context 타임프레임 + 일봉 한번에 수집 (초기 시딩용)."""
        for market in markets:
            for ct in self._context_timeframes:
                try:
                    candles = await self._client.fetch_candles(
                        market, ct.minutes, ct.candles
                    )
                    if candles:
                        await self._repo.save_many(candles, commit=False)
                        logger.info("Seeded %d %dm candles for %s", len(candles), ct.minutes, market)
                except Exception:
                    logger.exception("Failed to seed %dm candles for %s", ct.minutes, market)
                await asyncio.sleep(0.11)

            try:
                daily = await self._client.fetch_daily_candles(market, self._daily_candles)
                if daily:
                    await self._repo.save_many(daily, commit=False)
                    logger.info("Seeded %d daily candles for %s", len(daily), market)
            except Exception:
                logger.exception("Failed to seed daily candles for %s", market)
            await asyncio.sleep(0.11)
        await self._repo.commit()

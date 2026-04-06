from __future__ import annotations

from decimal import Decimal
from typing import Any

from src.config.settings import ScreeningConfig
from src.types.models import ScreeningResult


class Screener:
    def __init__(self, config: ScreeningConfig) -> None:
        self._config = config

    def update_config(self, config: ScreeningConfig) -> None:
        self._config = config

    def screen(
        self,
        tickers: list[dict[str, Any]],
        korean_names: dict[str, str] | None = None,
    ) -> list[ScreeningResult]:
        names = korean_names or {}
        candidates: list[ScreeningResult] = []

        for t in tickers:
            volume_24h: Decimal = t["volume_24h"]
            change_rate: Decimal = abs(t["change_rate"]) * Decimal("100")
            timestamp: int = t["timestamp"]
            market: str = t["market"]

            is_forced = market in self._config.always_include

            if not is_forced:
                if volume_24h < self._config.min_volume_krw:
                    continue
                if change_rate < self._config.min_volatility_pct:
                    continue
                if change_rate > self._config.max_volatility_pct:
                    continue

            score = (volume_24h / Decimal("1000000000")) * change_rate

            candidates.append(ScreeningResult(
                market=market,
                korean_name=names.get(market, market.replace("KRW-", "")),
                volume_krw=volume_24h,
                volatility=change_rate,
                score=score,
                timestamp=timestamp,
            ))

        # Sort: forced coins first, then by score descending
        forced_set = set(self._config.always_include)
        candidates.sort(
            key=lambda x: (x.market not in forced_set, -x.score),
        )
        return candidates[: self._config.max_coins]

# src/config/settings.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import yaml


@dataclass(frozen=True)
class PaperTradingConfig:
    initial_balance: Decimal
    max_position_pct: Decimal
    max_open_positions: int
    fee_rate: Decimal
    slippage_rate: Decimal
    min_order_krw: int


@dataclass(frozen=True)
class RiskConfig:
    stop_loss_pct: Decimal
    take_profit_pct: Decimal
    trailing_stop_pct: Decimal
    max_daily_loss_pct: Decimal
    max_daily_trades: int
    consecutive_loss_limit: int
    cooldown_minutes: int


@dataclass(frozen=True)
class ScreeningConfig:
    min_volume_krw: Decimal
    min_volatility_pct: Decimal
    max_volatility_pct: Decimal
    max_coins: int
    refresh_interval_min: int
    always_include: tuple[str, ...] = ()


@dataclass(frozen=True)
class StrategyConfig:
    lookahead_minutes: int
    threshold_pct: Decimal
    retrain_interval_hours: int
    min_confidence: Decimal


@dataclass(frozen=True)
class CollectorConfig:
    candle_timeframe: int
    max_candles_per_market: int
    market_refresh_interval_min: int


@dataclass(frozen=True)
class DataConfig:
    db_path: str
    model_dir: str
    stale_candle_days: int
    stale_model_days: int
    stale_order_days: int


@dataclass(frozen=True)
class Settings:
    paper_trading: PaperTradingConfig
    risk: RiskConfig
    screening: ScreeningConfig
    strategy: StrategyConfig
    collector: CollectorConfig
    data: DataConfig

    @staticmethod
    def from_yaml(path: Path) -> Settings:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return Settings(
            paper_trading=PaperTradingConfig(
                initial_balance=Decimal(str(raw["paper_trading"]["initial_balance"])),
                max_position_pct=Decimal(str(raw["paper_trading"]["max_position_pct"])),
                max_open_positions=int(raw["paper_trading"]["max_open_positions"]),
                fee_rate=Decimal(str(raw["paper_trading"]["fee_rate"])),
                slippage_rate=Decimal(str(raw["paper_trading"]["slippage_rate"])),
                min_order_krw=int(raw["paper_trading"]["min_order_krw"]),
            ),
            risk=RiskConfig(
                stop_loss_pct=Decimal(str(raw["risk"]["stop_loss_pct"])),
                take_profit_pct=Decimal(str(raw["risk"]["take_profit_pct"])),
                trailing_stop_pct=Decimal(str(raw["risk"]["trailing_stop_pct"])),
                max_daily_loss_pct=Decimal(str(raw["risk"]["max_daily_loss_pct"])),
                max_daily_trades=int(raw["risk"]["max_daily_trades"]),
                consecutive_loss_limit=int(raw["risk"]["consecutive_loss_limit"]),
                cooldown_minutes=int(raw["risk"]["cooldown_minutes"]),
            ),
            screening=ScreeningConfig(
                min_volume_krw=Decimal(str(raw["screening"]["min_volume_krw"])),
                min_volatility_pct=Decimal(str(raw["screening"]["min_volatility_pct"])),
                max_volatility_pct=Decimal(str(raw["screening"]["max_volatility_pct"])),
                max_coins=int(raw["screening"]["max_coins"]),
                refresh_interval_min=int(raw["screening"]["refresh_interval_min"]),
                always_include=tuple(raw["screening"].get("always_include", [])),
            ),
            strategy=StrategyConfig(
                lookahead_minutes=int(raw["strategy"]["lookahead_minutes"]),
                threshold_pct=Decimal(str(raw["strategy"]["threshold_pct"])),
                retrain_interval_hours=int(raw["strategy"]["retrain_interval_hours"]),
                min_confidence=Decimal(str(raw["strategy"]["min_confidence"])),
            ),
            collector=CollectorConfig(
                candle_timeframe=int(raw["collector"]["candle_timeframe"]),
                max_candles_per_market=int(raw["collector"]["max_candles_per_market"]),
                market_refresh_interval_min=int(raw["collector"]["market_refresh_interval_min"]),
            ),
            data=DataConfig(
                db_path=str(raw["data"]["db_path"]),
                model_dir=str(raw["data"]["model_dir"]),
                stale_candle_days=int(raw["data"]["stale_candle_days"]),
                stale_model_days=int(raw["data"]["stale_model_days"]),
                stale_order_days=int(raw["data"]["stale_order_days"]),
            ),
        )

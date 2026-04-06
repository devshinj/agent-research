# src/config/settings.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any

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
    lookahead_seconds: int
    threshold_pct: Decimal
    retrain_interval_hours: int
    min_confidence: Decimal
    signal_confirm_seconds: int
    signal_confirm_min_confidence: Decimal


@dataclass(frozen=True)
class TickStreamConfig:
    max_markets: int
    reconnect_max_seconds: int
    candle_retention_hours: int


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
    tick_stream: TickStreamConfig
    data: DataConfig

    @staticmethod
    def from_yaml(path: Path) -> Settings:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)

        return Settings.from_dict(raw)

    @staticmethod
    def from_dict(raw: dict[str, Any]) -> Settings:
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
                lookahead_seconds=int(raw["strategy"]["lookahead_seconds"]),
                threshold_pct=Decimal(str(raw["strategy"]["threshold_pct"])),
                retrain_interval_hours=int(raw["strategy"]["retrain_interval_hours"]),
                min_confidence=Decimal(str(raw["strategy"]["min_confidence"])),
                signal_confirm_seconds=int(raw["strategy"]["signal_confirm_seconds"]),
                signal_confirm_min_confidence=Decimal(str(raw["strategy"]["signal_confirm_min_confidence"])),
            ),
            tick_stream=TickStreamConfig(
                max_markets=int(raw["tick_stream"]["max_markets"]),
                reconnect_max_seconds=int(raw["tick_stream"]["reconnect_max_seconds"]),
                candle_retention_hours=int(raw["tick_stream"]["candle_retention_hours"]),
            ),
            data=DataConfig(
                db_path=str(raw["data"]["db_path"]),
                model_dir=str(raw["data"]["model_dir"]),
                stale_candle_days=int(raw["data"]["stale_candle_days"]),
                stale_model_days=int(raw["data"]["stale_model_days"]),
                stale_order_days=int(raw["data"]["stale_order_days"]),
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return settings as a plain dict (for JSON API responses)."""
        return {
            "paper_trading": {
                "initial_balance": int(self.paper_trading.initial_balance),
                "max_position_pct": float(self.paper_trading.max_position_pct),
                "max_open_positions": self.paper_trading.max_open_positions,
                "fee_rate": float(self.paper_trading.fee_rate),
                "slippage_rate": float(self.paper_trading.slippage_rate),
                "min_order_krw": self.paper_trading.min_order_krw,
            },
            "risk": {
                "stop_loss_pct": float(self.risk.stop_loss_pct),
                "take_profit_pct": float(self.risk.take_profit_pct),
                "trailing_stop_pct": float(self.risk.trailing_stop_pct),
                "max_daily_loss_pct": float(self.risk.max_daily_loss_pct),
                "max_daily_trades": self.risk.max_daily_trades,
                "consecutive_loss_limit": self.risk.consecutive_loss_limit,
                "cooldown_minutes": self.risk.cooldown_minutes,
            },
            "screening": {
                "min_volume_krw": int(self.screening.min_volume_krw),
                "min_volatility_pct": float(self.screening.min_volatility_pct),
                "max_volatility_pct": float(self.screening.max_volatility_pct),
                "max_coins": self.screening.max_coins,
                "refresh_interval_min": self.screening.refresh_interval_min,
                "always_include": list(self.screening.always_include),
            },
            "strategy": {
                "lookahead_seconds": self.strategy.lookahead_seconds,
                "threshold_pct": float(self.strategy.threshold_pct),
                "retrain_interval_hours": self.strategy.retrain_interval_hours,
                "min_confidence": float(self.strategy.min_confidence),
                "signal_confirm_seconds": self.strategy.signal_confirm_seconds,
                "signal_confirm_min_confidence": float(self.strategy.signal_confirm_min_confidence),
            },
            "tick_stream": {
                "max_markets": self.tick_stream.max_markets,
                "reconnect_max_seconds": self.tick_stream.reconnect_max_seconds,
                "candle_retention_hours": self.tick_stream.candle_retention_hours,
            },
            "data": {
                "db_path": self.data.db_path,
                "model_dir": self.data.model_dir,
                "stale_candle_days": self.data.stale_candle_days,
                "stale_model_days": self.data.stale_model_days,
                "stale_order_days": self.data.stale_order_days,
            },
        }

    def to_yaml(self, path: Path) -> None:
        data = self.to_dict()
        with open(path, "w", encoding="utf-8") as f:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

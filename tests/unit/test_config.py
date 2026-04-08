# tests/unit/test_config.py
from pathlib import Path
from decimal import Decimal

from src.config.settings import Settings


def test_load_settings_from_yaml(tmp_path: Path) -> None:
    yaml_content = """
paper_trading:
  initial_balance: 10000000
  max_position_pct: 0.25
  max_open_positions: 4
  fee_rate: 0.0005
  slippage_rate: 0.0005
  min_order_krw: 5000

risk:
  stop_loss_pct: 0.02
  take_profit_pct: 0.05
  trailing_stop_pct: 0.015
  max_daily_loss_pct: 0.05
  max_daily_trades: 50
  consecutive_loss_limit: 5
  cooldown_minutes: 60

screening:
  min_volume_krw: 500000000
  min_volatility_pct: 1.0
  max_volatility_pct: 15.0
  max_coins: 10
  refresh_interval_min: 30

strategy:
  lookahead_minutes: 5
  threshold_pct: 0.3
  retrain_interval_hours: 6
  min_confidence: 0.6

collector:
  candle_timeframe: 1
  max_candles_per_market: 200
  market_refresh_interval_min: 60

data:
  db_path: "data/paper_trader.db"
  model_dir: "data/models"
  stale_candle_days: 7
  stale_model_days: 30
  stale_order_days: 90
"""
    config_file = tmp_path / "settings.yaml"
    config_file.write_text(yaml_content)
    settings = Settings.from_yaml(config_file)

    assert settings.paper_trading.initial_balance == Decimal("10000000")
    assert settings.paper_trading.max_position_pct == Decimal("0.25")
    assert settings.risk.stop_loss_pct == Decimal("0.02")
    assert settings.screening.min_volume_krw == Decimal("500000000")
    assert settings.strategy.lookahead_minutes == 5
    assert settings.collector.candle_timeframe == 1
    assert settings.data.db_path == "data/paper_trader.db"


def test_settings_max_open_positions_matches_pct() -> None:
    """max_open_positions * max_position_pct <= 1.0"""
    settings = Settings.from_yaml(Path("config/settings.yaml"))
    total = settings.paper_trading.max_open_positions * settings.paper_trading.max_position_pct
    assert total <= Decimal("1.0")


def test_collector_multi_timeframe_fields() -> None:
    settings = Settings.from_dict({
        "paper_trading": {
            "initial_balance": 10000000, "max_position_pct": 0.25,
            "max_open_positions": 4, "fee_rate": 0.0005,
            "slippage_rate": 0.0005, "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02, "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015, "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50, "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000, "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0, "max_coins": 10,
            "refresh_interval_min": 30,
        },
        "strategy": {
            "lookahead_minutes": 5, "threshold_pct": 0.3,
            "retrain_interval_hours": 6, "min_confidence": 0.6,
        },
        "collector": {
            "candle_timeframe": 1, "max_candles_per_market": 500,
            "market_refresh_interval_min": 60,
            "train_timeframe": 15, "train_candles": 960,
            "daily_candles": 30,
        },
        "data": {
            "db_path": "data/paper_trader.db", "model_dir": "data/models",
            "stale_candle_days": 7, "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert settings.collector.train_timeframe == 15
    assert settings.collector.train_candles == 960
    assert settings.collector.daily_candles == 30


def test_collector_multi_timeframe_defaults() -> None:
    settings = Settings.from_dict({
        "paper_trading": {
            "initial_balance": 10000000, "max_position_pct": 0.25,
            "max_open_positions": 4, "fee_rate": 0.0005,
            "slippage_rate": 0.0005, "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02, "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015, "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50, "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000, "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0, "max_coins": 10,
            "refresh_interval_min": 30,
        },
        "strategy": {
            "lookahead_minutes": 5, "threshold_pct": 0.3,
            "retrain_interval_hours": 6, "min_confidence": 0.6,
        },
        "collector": {
            "candle_timeframe": 1, "max_candles_per_market": 200,
            "market_refresh_interval_min": 60,
        },
        "data": {
            "db_path": "data/paper_trader.db", "model_dir": "data/models",
            "stale_candle_days": 7, "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert settings.collector.train_timeframe == 15
    assert settings.collector.train_candles == 960
    assert settings.collector.daily_candles == 30

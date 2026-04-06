from pathlib import Path
from decimal import Decimal

from src.config.settings import Settings, TickStreamConfig, StrategyConfig


def test_tick_stream_config():
    cfg = TickStreamConfig(
        max_markets=3,
        reconnect_max_seconds=30,
        candle_retention_hours=24,
    )
    assert cfg.max_markets == 3
    assert cfg.reconnect_max_seconds == 30
    assert cfg.candle_retention_hours == 24


def test_strategy_config_has_seconds():
    cfg = StrategyConfig(
        lookahead_seconds=30,
        threshold_pct=Decimal("0.0005"),
        retrain_interval_hours=6,
        min_confidence=Decimal("0.6"),
        signal_confirm_seconds=3,
        signal_confirm_min_confidence=Decimal("0.7"),
    )
    assert cfg.lookahead_seconds == 30
    assert cfg.signal_confirm_seconds == 3


def test_settings_from_dict_new_structure():
    raw = {
        "paper_trading": {
            "initial_balance": 100000000,
            "max_position_pct": 0.25,
            "max_open_positions": 10,
            "fee_rate": 0.0005,
            "slippage_rate": 0.0005,
            "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015,
            "max_daily_loss_pct": 0.05,
            "max_daily_trades": 200,
            "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 10000,
            "min_volatility_pct": 0.5,
            "max_volatility_pct": 10.0,
            "max_coins": 30,
            "refresh_interval_min": 1,
            "always_include": [],
        },
        "strategy": {
            "lookahead_seconds": 30,
            "threshold_pct": 0.0005,
            "retrain_interval_hours": 6,
            "min_confidence": 0.6,
            "signal_confirm_seconds": 3,
            "signal_confirm_min_confidence": 0.7,
        },
        "tick_stream": {
            "max_markets": 3,
            "reconnect_max_seconds": 30,
            "candle_retention_hours": 24,
        },
        "data": {
            "db_path": "data/paper_trader.db",
            "model_dir": "data/models",
            "stale_candle_days": 7,
            "stale_model_days": 30,
            "stale_order_days": 90,
        },
    }
    settings = Settings.from_dict(raw)
    assert settings.tick_stream.max_markets == 3
    assert settings.strategy.lookahead_seconds == 30
    assert settings.strategy.signal_confirm_seconds == 3
    assert not hasattr(settings, "collector")


def test_settings_max_open_positions_matches_pct() -> None:
    settings = Settings.from_yaml(Path("config/settings.yaml"))
    total = settings.paper_trading.max_open_positions * settings.paper_trading.max_position_pct
    assert total <= Decimal("1.0")

from __future__ import annotations

from decimal import Decimal

import pytest

from src.config.settings import PaperTradingConfig, RiskConfig, ScreeningConfig
from src.service.predictor import Predictor
from src.service.risk_manager import RiskManager
from src.service.screener import Screener


def _make_risk_config(**overrides) -> RiskConfig:
    defaults = {
        "stop_loss_pct": Decimal("0.02"),
        "take_profit_pct": Decimal("0.05"),
        "trailing_stop_pct": Decimal("0.015"),
        "max_daily_loss_pct": Decimal("0.05"),
        "max_daily_trades": 50,
        "consecutive_loss_limit": 5,
        "cooldown_minutes": 60,
    }
    defaults.update(overrides)
    return RiskConfig(**defaults)


def _make_pt_config(**overrides) -> PaperTradingConfig:
    defaults = {
        "initial_balance": Decimal("5000000"),
        "max_position_pct": Decimal("0.25"),
        "max_open_positions": 4,
        "fee_rate": Decimal("0.0005"),
        "slippage_rate": Decimal("0.0005"),
        "min_order_krw": 5000,
    }
    defaults.update(overrides)
    return PaperTradingConfig(**defaults)


def _make_screening_config(**overrides) -> ScreeningConfig:
    defaults = {
        "min_volume_krw": Decimal("500000000"),
        "min_volatility_pct": Decimal("1.0"),
        "max_volatility_pct": Decimal("15.0"),
        "max_coins": 10,
        "refresh_interval_min": 30,
        "always_include": (),
    }
    defaults.update(overrides)
    return ScreeningConfig(**defaults)


def test_risk_manager_update_config_preserves_state():
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    rm._consecutive_losses = 3
    rm._daily_trades = 7
    rm._cooldown_until = 9999

    new_risk = _make_risk_config(stop_loss_pct=Decimal("0.05"))
    rm.update_config(new_risk)

    assert rm._risk.stop_loss_pct == Decimal("0.05")
    assert rm._consecutive_losses == 3
    assert rm._daily_trades == 7
    assert rm._cooldown_until == 9999


def test_predictor_update_min_confidence():
    from src.service.features import FeatureBuilder

    fb = FeatureBuilder()
    p = Predictor(fb, 0.6)
    p._models["KRW-BTC"] = "fake_model"

    p.update_min_confidence(0.8)

    assert p._min_confidence == 0.8
    assert "KRW-BTC" in p._models


def test_screener_update_config():
    s = Screener(_make_screening_config())

    new_config = _make_screening_config(max_coins=5)
    s.update_config(new_config)

    assert s._config.max_coins == 5


import dataclasses

from src.config.settings import Settings, StrategyConfig, CollectorConfig, DataConfig


def _make_settings() -> Settings:
    return Settings(
        paper_trading=_make_pt_config(),
        risk=_make_risk_config(),
        screening=_make_screening_config(),
        strategy=StrategyConfig(
            lookahead_minutes=5,
            threshold_pct=Decimal("0.3"),
            retrain_interval_hours=6,
            min_confidence=Decimal("0.6"),
        ),
        collector=CollectorConfig(
            candle_timeframe=1,
            max_candles_per_market=200,
            market_refresh_interval_min=60,
        ),
        data=DataConfig(
            db_path=":memory:",
            model_dir="data/models",
            stale_candle_days=7,
            stale_model_days=30,
            stale_order_days=90,
        ),
    )


def test_hot_reload_updates_risk():
    """hot_reload with risk field updates risk_manager config."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)
    app.risk_manager._consecutive_losses = 3

    updated = app.hot_reload({"risk": {"stop_loss_pct": 0.05}})

    assert app.settings.risk.stop_loss_pct == Decimal("0.05")
    assert app.risk_manager._risk.stop_loss_pct == Decimal("0.05")
    assert app.risk_manager._consecutive_losses == 3
    assert "risk" in updated
    assert "stop_loss_pct" in updated["risk"]


def test_hot_reload_updates_min_confidence():
    """hot_reload with strategy.min_confidence updates predictor."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    app.hot_reload({"strategy": {"min_confidence": 0.8}})

    assert app.predictor._min_confidence == 0.8
    assert app.settings.strategy.min_confidence == Decimal("0.8")


def test_hot_reload_updates_screening():
    """hot_reload with screening fields updates screener config."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    app.hot_reload({"screening": {"max_coins": 5}})

    assert app.screener._config.max_coins == 5
    assert app.settings.screening.max_coins == 5


def test_hot_reload_rejects_forbidden_field():
    """hot_reload raises ValueError for non-hot-reloadable fields."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    with pytest.raises(ValueError, match="핫 리로드 불가"):
        app.hot_reload({"paper_trading": {"initial_balance": 10000000}})


def test_hot_reload_rejects_forbidden_section():
    """hot_reload raises ValueError for entirely forbidden sections."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    with pytest.raises(ValueError, match="핫 리로드 불가"):
        app.hot_reload({"collector": {"candle_timeframe": 5}})


def test_paper_engine_update_config():
    from src.service.paper_engine import PaperEngine

    engine = PaperEngine(_make_pt_config())
    assert engine._config.max_position_pct == Decimal("0.25")

    new_config = _make_pt_config(max_position_pct=Decimal("0.5"))
    engine.update_config(new_config)

    assert engine._config.max_position_pct == Decimal("0.5")
    assert engine._config.max_open_positions == 4  # unchanged fields preserved

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

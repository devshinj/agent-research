import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.service.features import FeatureBuilder
from src.types.enums import SignalType


def make_data(n=500):
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


@pytest.fixture
def trained_model(tmp_path):
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_data()
    result = trainer.train("KRW-BTC", df)
    return result["model_path"]


def test_predictor_returns_signal(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal = predictor.predict("KRW-BTC", df)
    assert signal.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1


def test_predictor_hold_on_low_confidence(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.99)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal = predictor.predict("KRW-BTC", df)
    assert signal.signal_type == SignalType.HOLD


def test_predictor_no_model_raises():
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.6)
    with pytest.raises(KeyError):
        predictor.predict("KRW-NONE", make_data(200))

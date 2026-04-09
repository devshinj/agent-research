import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.service.features import FeatureBuilder
from src.types.enums import SignalType
from src.types.models import SignalBasis


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


def test_predictor_returns_signal_and_basis(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1
    assert isinstance(basis, SignalBasis)
    if signal.signal_type != SignalType.HOLD:
        assert len(basis.top_features) == 5
        for name, shap_val, feat_val in basis.top_features:
            assert isinstance(name, str)
            assert isinstance(shap_val, float)
            assert isinstance(feat_val, float)


def test_predictor_hold_returns_empty_basis(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.99)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    assert signal.signal_type == SignalType.HOLD
    assert basis.top_features == ()


def test_predictor_no_model_raises():
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.6)
    with pytest.raises(KeyError):
        predictor.predict("KRW-NONE", make_data(200))


def test_predictor_basis_sorted_by_abs_shap(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    if signal.signal_type != SignalType.HOLD and len(basis.top_features) > 1:
        abs_shaps = [abs(s) for _, s, _ in basis.top_features]
        assert abs_shaps == sorted(abs_shaps, reverse=True)


def make_daily(n=30):
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 500000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 200000,
        "high": close + np.abs(np.random.randn(n)) * 500000,
        "low": close - np.abs(np.random.randn(n)) * 500000,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 10,
    })


@pytest.fixture
def trained_model_with_context(tmp_path):
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_data()
    context_dfs = {
        "1m": make_data(100), "3m": make_data(100),
        "10m": make_data(100), "15m": make_data(100),
        "60m": make_data(100), "1D": make_daily(),
    }
    result = trainer.train("KRW-BTC", df, context_dfs=context_dfs)
    return result["model_path"]


def test_predictor_with_multi_context(trained_model_with_context):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model_with_context)
    df = make_data(200)
    context_dfs = {
        "1m": make_data(100), "3m": make_data(100),
        "10m": make_data(100), "15m": make_data(100),
        "60m": make_data(100), "1D": make_daily(30),
    }
    signal, basis = predictor.predict("KRW-BTC", df, context_dfs=context_dfs)
    assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1

import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.service.features import FeatureBuilder
from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.types.enums import SignalType


def make_candle_df(n: int = 600) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_train_then_predict(tmp_path):
    """Trainer produces a model that Predictor can use to generate signals."""
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), lookahead_minutes=5, threshold_pct=0.3)
    predictor = Predictor(fb, min_confidence=0.0)

    df = make_candle_df(600)
    result = trainer.train("KRW-BTC", df)

    assert result["model_path"] is not None, "Training should succeed with 600 candles"
    assert result["accuracy"] > 0

    predictor.load_model("KRW-BTC", result["model_path"])
    signal, _basis = predictor.predict("KRW-BTC", df.tail(200).reset_index(drop=True))

    assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
    assert signal.market == "KRW-BTC"


def test_model_persisted_and_reloadable(tmp_path):
    """Model saved by Trainer can be loaded by a fresh Predictor instance."""
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_candle_df(600)
    result = trainer.train("KRW-BTC", df)

    # Fresh predictor loads the saved model
    predictor2 = Predictor(FeatureBuilder(), min_confidence=0.0)
    predictor2.load_model("KRW-BTC", result["model_path"])

    signal, _basis = predictor2.predict("KRW-BTC", df.tail(200).reset_index(drop=True))
    assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)

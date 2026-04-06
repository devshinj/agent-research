import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.features import FeatureBuilder


def make_training_data(n: int = 500) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_trainer_creates_model(tmp_path):
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(
        feature_builder=feature_builder,
        model_dir=str(tmp_path),
        lookahead_minutes=5,
        threshold_pct=0.3,
    )
    result = trainer.train("KRW-BTC", df)
    assert result["accuracy"] > 0
    assert result["model_path"].exists()


def test_trainer_saves_metadata(tmp_path):
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    meta_path = result["model_path"].with_suffix(".json")
    assert meta_path.exists()


def test_trainer_with_insufficient_data(tmp_path):
    df = make_training_data(20)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    assert result["accuracy"] == 0
    assert result["model_path"] is None

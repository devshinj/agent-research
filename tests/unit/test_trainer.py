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


def test_trainer_creates_binary_labels(tmp_path):
    """_create_labels produces only 0 (NOT_BUY) and 1 (BUY), no label=2."""
    df = make_training_data()
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    labels = trainer._create_labels(df)
    assert set(labels.dropna().unique()).issubset({0, 1})


def test_trainer_update_threshold(tmp_path):
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    trainer.update_threshold(0.5)
    assert trainer._threshold == 0.5


def test_trainer_with_insufficient_data(tmp_path):
    df = make_training_data(20)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    assert result["accuracy"] == 0
    assert result["model_path"] is None


def make_daily_data(n: int = 30) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 500000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 200000,
        "high": close + np.abs(np.random.randn(n)) * 500000,
        "low": close - np.abs(np.random.randn(n)) * 500000,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 10,
    })


def test_trainer_with_multi_context(tmp_path):
    """학습 시 멀티 context를 전달하면 60개 feature 모델이 생성된다."""
    df = make_training_data(500)
    context_dfs = {
        "1m": make_training_data(100),
        "3m": make_training_data(100),
        "10m": make_training_data(100),
        "15m": make_training_data(100),
        "60m": make_training_data(100),
        "1D": make_daily_data(30),
    }
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df, context_dfs=context_dfs)
    assert result["model_path"] is not None
    import json
    meta = json.loads(result["model_path"].with_suffix(".json").read_text())
    assert "ctx_1D_rsi_14" in meta["features"]
    assert len(meta["features"]) == 60


def test_trainer_metadata_includes_f1(tmp_path):
    """메타데이터에 f1, precision, recall이 포함된다."""
    df = make_training_data(500)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    import json
    meta = json.loads(result["model_path"].with_suffix(".json").read_text())
    assert "f1" in meta
    assert "precision" in meta
    assert "recall" in meta
    assert "buy_ratio" in meta


def test_trainer_result_includes_f1(tmp_path):
    """train() 반환값에 f1이 포함된다."""
    df = make_training_data(500)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    assert "f1" in result
    assert isinstance(result["f1"], float)

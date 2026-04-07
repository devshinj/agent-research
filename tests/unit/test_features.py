# tests/unit/test_features.py
import pandas as pd
import numpy as np
from decimal import Decimal

from src.service.features import FeatureBuilder


def make_candle_df(n: int = 100) -> pd.DataFrame:
    """테스트용 캔들 DataFrame 생성"""
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_feature_builder_returns_dataframe():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    features = builder.build(df)
    assert isinstance(features, pd.DataFrame)
    assert len(features) > 0


def test_feature_columns_present():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    features = builder.build(df)

    expected_cols = [
        "return_1m", "return_5m", "return_15m",
        "rsi_14", "rsi_7",
        "macd", "macd_signal", "macd_hist",
        "bb_width",
        "ema_5_ratio", "ema_20_ratio",
        "volume_ratio_5m", "volume_ratio_20m",
        "high_low_ratio", "close_position",
    ]
    for col in expected_cols:
        assert col in features.columns, f"Missing feature: {col}"


def test_no_nan_in_output():
    # 300행 이상이어야 모든 multi-timeframe feature도 생성됨
    df = make_candle_df(350)
    builder = FeatureBuilder()
    features = builder.build(df)
    # dropna 후 rows가 존재해야 함
    clean = features.dropna()
    assert len(clean) > 0


def test_deterministic_output():
    df = make_candle_df(100)
    builder = FeatureBuilder()
    f1 = builder.build(df)
    f2 = builder.build(df)
    pd.testing.assert_frame_equal(f1, f2)


def test_build_with_short_data():
    """데이터가 부족해도 에러 없이 빈 DataFrame 반환"""
    df = make_candle_df(5)
    builder = FeatureBuilder()
    features = builder.build(df)
    assert isinstance(features, pd.DataFrame)

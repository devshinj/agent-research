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


def make_daily_df(n: int = 30) -> pd.DataFrame:
    """테스트용 일봉 DataFrame 생성"""
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 500000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 200000,
        "high": close + np.abs(np.random.randn(n)) * 500000,
        "low": close - np.abs(np.random.randn(n)) * 500000,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 10,
    })


def test_build_daily_context_returns_series():
    df = make_daily_df(30)
    builder = FeatureBuilder()
    ctx = builder.build_daily_context(df)
    assert isinstance(ctx, pd.Series)
    expected_keys = [
        "daily_rsi_14", "daily_ema_5_ratio", "daily_ema_20_ratio",
        "daily_volume_ratio", "daily_trend", "daily_atr_ratio",
    ]
    for key in expected_keys:
        assert key in ctx.index, f"Missing daily context feature: {key}"


def test_build_daily_context_no_nan_with_enough_data():
    df = make_daily_df(30)
    builder = FeatureBuilder()
    ctx = builder.build_daily_context(df)
    assert not ctx.isna().any(), f"NaN found in daily context: {ctx[ctx.isna()].index.tolist()}"


def test_build_daily_context_short_data_returns_nan():
    df = make_daily_df(5)
    builder = FeatureBuilder()
    ctx = builder.build_daily_context(df)
    assert isinstance(ctx, pd.Series)
    assert len(ctx) == 6


def test_get_feature_names_includes_daily():
    builder = FeatureBuilder()
    names = builder.get_feature_names()
    assert "daily_rsi_14" in names
    assert "daily_trend" in names
    assert len(names) == 30

# tests/unit/test_multi_timeframe.py
"""Phase 5: 다중 시간축 분석 테스트."""
import numpy as np
import pandas as pd

from src.service.features import FeatureBuilder


def _make_df(n: int) -> pd.DataFrame:
    np.random.seed(42)
    base = 50000000.0
    prices = base + np.cumsum(np.random.normal(0, base * 0.001, n))
    noise = np.random.normal(0, base * 0.0005, n)
    return pd.DataFrame({
        "open": prices + noise,
        "high": prices + abs(noise) + base * 0.001,
        "low": prices - abs(noise) - base * 0.001,
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
    })


def test_24_features_with_300_rows() -> None:
    """300행 이상 DataFrame에서 24개 feature 모두 생성."""
    fb = FeatureBuilder()
    df = _make_df(350)
    features = fb.build(df)
    expected_names = fb.get_feature_names()
    assert len(expected_names) == 24
    for name in expected_names:
        assert name in features.columns, f"Missing feature: {name}"
    # 마지막 행에서 multi-tf feature가 NaN이 아님
    last = features.iloc[-1]
    assert pd.notna(last["ema_30m"])
    assert pd.notna(last["rsi_14_5m"])
    assert pd.notna(last["ema_1h"])
    assert pd.notna(last["trend_1h"])


def test_under_60_rows_multi_tf_nan() -> None:
    """60행 미만에서 multi-timeframe feature가 NaN (에러 없이)."""
    fb = FeatureBuilder()
    df = _make_df(50)
    features = fb.build(df)
    assert "ema_30m" in features.columns
    assert "rsi_14_5m" in features.columns
    assert features["ema_30m"].isna().all()
    assert features["rsi_14_5m"].isna().all()


def test_resample_5m_ohlcv() -> None:
    """1분봉 5개 → 5분봉 1개의 OHLCV 정합성."""
    fb = FeatureBuilder()
    df = pd.DataFrame({
        "open": [100.0, 101.0, 99.0, 102.0, 98.0],
        "high": [105.0, 106.0, 104.0, 107.0, 103.0],
        "low": [95.0, 96.0, 94.0, 97.0, 93.0],
        "close": [101.0, 99.0, 102.0, 98.0, 100.0],
        "volume": [10.0, 20.0, 15.0, 25.0, 30.0],
    })
    resampled = fb._resample(df, 5)
    assert len(resampled) == 1
    row = resampled.iloc[0]
    assert row["open"] == 100.0   # first open
    assert row["high"] == 107.0   # max high
    assert row["low"] == 93.0     # min low
    assert row["close"] == 100.0  # last close
    assert row["volume"] == 100.0  # sum volume


def test_between_60_and_300_partial_features() -> None:
    """60~299행: 5분봉 feature는 있고, 15분봉 feature는 NaN."""
    fb = FeatureBuilder()
    df = _make_df(150)
    features = fb.build(df)
    # 5분봉 feature 존재
    assert pd.notna(features["ema_30m"].iloc[-1])
    assert pd.notna(features["rsi_14_5m"].iloc[-1])
    # 15분봉 feature는 NaN
    assert features["ema_1h"].isna().all()
    assert features["trend_1h"].isna().all()

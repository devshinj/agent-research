# tests/unit/test_entry_analyzer.py
"""Phase 3: EntryAnalyzer 저점 매수 스코어링 테스트."""
from decimal import Decimal

import numpy as np
import pandas as pd

from src.config.settings import EntryAnalyzerConfig
from src.service.entry_analyzer import EntryAnalyzer
from src.service.features import FeatureBuilder


def _make_df(n: int, trend: str = "flat") -> pd.DataFrame:
    """Generate synthetic candle data.

    trend: 'flat', 'up', 'down', 'v_recovery'
    """
    np.random.seed(42)
    base = 50000000.0
    if trend == "down":
        prices = np.linspace(base, base * 0.85, n)
    elif trend == "up":
        prices = np.linspace(base * 0.85, base, n)
    elif trend == "v_recovery":
        half = n // 2
        down = np.linspace(base, base * 0.80, half)
        up = np.linspace(base * 0.80, base * 0.82, n - half)
        prices = np.concatenate([down, up])
    else:
        prices = np.full(n, base) + np.random.normal(0, base * 0.002, n)

    noise = np.random.normal(0, base * 0.001, n)
    return pd.DataFrame({
        "open": prices + noise,
        "high": prices + abs(noise) + base * 0.002,
        "low": prices - abs(noise) - base * 0.002,
        "close": prices,
        "volume": np.random.uniform(100, 1000, n),
    })


def test_high_price_low_score() -> None:
    """가격이 60봉 최고점일 때 score < 0.5 → 매수 거부."""
    config = EntryAnalyzerConfig(min_entry_score=Decimal("0.5"), price_lookback_candles=60)
    analyzer = EntryAnalyzer(config)
    fb = FeatureBuilder()

    # 상승 추세: 현재가가 최고점 근처
    df = _make_df(100, trend="up")
    features = fb.build(df)
    score = analyzer.score_entry(df, features)
    assert score < Decimal("0.5"), f"Score at high should be < 0.5, got {score}"


def test_down_trend_higher_score_than_up_trend() -> None:
    """하락 추세(저점 근처)의 score가 상승 추세(고점 근처)보다 높아야 함."""
    config = EntryAnalyzerConfig(min_entry_score=Decimal("0.5"), price_lookback_candles=60)
    analyzer = EntryAnalyzer(config)
    fb = FeatureBuilder()

    df_down = _make_df(100, trend="down")
    score_down = analyzer.score_entry(df_down, fb.build(df_down))

    df_up = _make_df(100, trend="up")
    score_up = analyzer.score_entry(df_up, fb.build(df_up))

    assert score_down > score_up, (
        f"Down trend score ({score_down}) should be > up trend score ({score_up})"
    )


def test_insufficient_data_returns_zero() -> None:
    """데이터 부족 시 score = 0."""
    config = EntryAnalyzerConfig(min_entry_score=Decimal("0.5"), price_lookback_candles=60)
    analyzer = EntryAnalyzer(config)

    df = _make_df(30)  # 60봉 미만
    features = pd.DataFrame()
    score = analyzer.score_entry(df, features)
    assert score == Decimal("0")


def test_score_in_range() -> None:
    """score는 항상 0~1 사이."""
    config = EntryAnalyzerConfig(min_entry_score=Decimal("0.5"), price_lookback_candles=60)
    analyzer = EntryAnalyzer(config)
    fb = FeatureBuilder()

    for trend in ("flat", "up", "down", "v_recovery"):
        df = _make_df(100, trend=trend)
        features = fb.build(df)
        score = analyzer.score_entry(df, features)
        assert Decimal("0") <= score <= Decimal("1"), f"Score out of range for {trend}: {score}"


def test_reuses_feature_builder_features() -> None:
    """FeatureBuilder의 기존 feature(rsi_14, macd_hist, ema_20_ratio)를 재사용."""
    fb = FeatureBuilder()
    df = _make_df(100)
    features = fb.build(df)
    assert "rsi_14" in features.columns
    assert "macd_hist" in features.columns
    assert "ema_20_ratio" in features.columns

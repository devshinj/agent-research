# src/service/features.py
from __future__ import annotations

import numpy as np
import pandas as pd
import ta


class FeatureBuilder:
    """단일 피처 빌더 — 학습과 예측 모두 이 클래스를 사용한다."""

    def build(self, df: pd.DataFrame) -> pd.DataFrame:
        if len(df) < 30:
            return pd.DataFrame()

        features = pd.DataFrame(index=df.index)

        # ① Price Action
        features["return_1m"] = df["close"].pct_change(1)
        features["return_5m"] = df["close"].pct_change(5)
        features["return_15m"] = df["close"].pct_change(15)
        features["return_60m"] = df["close"].pct_change(60)
        features["high_low_ratio"] = (df["high"] - df["low"]) / df["low"]
        features["close_position"] = (df["close"] - df["low"]) / (
            df["high"] - df["low"]
        ).replace(0, np.nan)

        # ② Technical Indicators
        features["rsi_14"] = ta.momentum.rsi(df["close"], window=14)
        features["rsi_7"] = ta.momentum.rsi(df["close"], window=7)

        macd_indicator = ta.trend.MACD(df["close"])
        features["macd"] = macd_indicator.macd()
        features["macd_signal"] = macd_indicator.macd_signal()
        features["macd_hist"] = macd_indicator.macd_diff()

        bb = ta.volatility.BollingerBands(df["close"], window=20)
        features["bb_upper"] = (df["close"] - bb.bollinger_hband()) / df["close"]
        features["bb_lower"] = (df["close"] - bb.bollinger_lband()) / df["close"]
        features["bb_width"] = bb.bollinger_wband()

        features["ema_5_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=5) - 1
        features["ema_20_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=20) - 1
        features["ema_60_ratio"] = df["close"] / ta.trend.ema_indicator(df["close"], window=60) - 1

        # ③ Volume
        features["volume_ratio_5m"] = df["volume"] / df["volume"].rolling(5).mean()
        features["volume_ratio_20m"] = df["volume"] / df["volume"].rolling(20).mean()
        features["volume_trend"] = (
            df["volume"].rolling(10).apply(
                lambda x: np.polyfit(range(len(x)), x, 1)[0] if len(x) == 10 else 0,
                raw=True,
            )
        )

        return features

    def get_feature_names(self) -> list[str]:
        return [
            "return_1m", "return_5m", "return_15m", "return_60m",
            "high_low_ratio", "close_position",
            "rsi_14", "rsi_7",
            "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_lower", "bb_width",
            "ema_5_ratio", "ema_20_ratio", "ema_60_ratio",
            "volume_ratio_5m", "volume_ratio_20m", "volume_trend",
        ]

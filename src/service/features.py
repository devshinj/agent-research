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

        # ④ Multi-timeframe features (리샘플링)
        if len(df) >= 60:
            df_5m = self._resample(df, 5)
            if len(df_5m) >= 14:
                ema_30m = ta.trend.ema_indicator(df_5m["close"], window=6)  # 6 * 5min = 30min
                features["ema_30m"] = self._align_higher_tf(ema_30m, df, 5)
                rsi_5m = ta.momentum.rsi(df_5m["close"], window=14)
                features["rsi_14_5m"] = self._align_higher_tf(rsi_5m, df, 5)
            else:
                features["ema_30m"] = np.nan
                features["rsi_14_5m"] = np.nan
        else:
            features["ema_30m"] = np.nan
            features["rsi_14_5m"] = np.nan

        if len(df) >= 300:
            df_15m = self._resample(df, 15)
            if len(df_15m) >= 14:
                ema_1h = ta.trend.ema_indicator(df_15m["close"], window=4)  # 4 * 15min = 1h
                features["ema_1h"] = self._align_higher_tf(ema_1h, df, 15)
                # trend_1h: 1이면 상승, -1이면 하락 (EMA 기울기)
                ema_1h_diff = ema_1h.diff()
                trend_1h = ema_1h_diff.apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
                features["trend_1h"] = self._align_higher_tf(trend_1h, df, 15)
            else:
                features["ema_1h"] = np.nan
                features["trend_1h"] = np.nan
        else:
            features["ema_1h"] = np.nan
            features["trend_1h"] = np.nan

        return features

    @staticmethod
    def _resample(df: pd.DataFrame, minutes: int) -> pd.DataFrame:
        """1분봉 DataFrame을 N분봉으로 리샘플링."""
        n = len(df)
        # 뒤에서부터 minutes 단위로 그룹
        groups = n // minutes
        if groups == 0:
            return pd.DataFrame()
        # 앞쪽 남는 행 버림
        start = n - groups * minutes
        trimmed = df.iloc[start:].reset_index(drop=True)

        result_rows: list[dict[str, float]] = []
        for i in range(groups):
            chunk = trimmed.iloc[i * minutes : (i + 1) * minutes]
            result_rows.append({
                "open": chunk["open"].iloc[0],
                "high": chunk["high"].max(),
                "low": chunk["low"].min(),
                "close": chunk["close"].iloc[-1],
                "volume": chunk["volume"].sum(),
            })
        return pd.DataFrame(result_rows)

    @staticmethod
    def _align_higher_tf(
        higher_series: pd.Series,  # type: ignore[type-arg]
        df_1m: pd.DataFrame,
        minutes: int,
    ) -> pd.Series:  # type: ignore[type-arg]
        """고시간축 시리즈를 1분봉 인덱스에 맞춰 forward-fill."""
        n = len(df_1m)
        groups = n // minutes
        start = n - groups * minutes
        result = pd.Series(np.nan, index=df_1m.index)
        for i, val in enumerate(higher_series):
            bar_start = start + i * minutes
            bar_end = start + (i + 1) * minutes
            result.iloc[bar_start:bar_end] = val
        return result

    # ── Context timeframe labels (order matters for feature naming) ──
    CONTEXT_TIMEFRAMES: list[str] = ["1m", "3m", "10m", "15m", "60m", "1D"]

    def _build_tf_context(self, df: pd.DataFrame, prefix: str) -> dict[str, float]:
        """단일 타임프레임에서 6개 context feature를 추출한다."""
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        result: dict[str, float] = {}

        rsi = ta.momentum.rsi(close, window=14)
        result[f"{prefix}_rsi_14"] = float(rsi.iloc[-1])

        ema5 = ta.trend.ema_indicator(close, window=5)
        result[f"{prefix}_ema_5_ratio"] = float(close.iloc[-1] / ema5.iloc[-1] - 1)

        ema20 = ta.trend.ema_indicator(close, window=20)
        result[f"{prefix}_ema_20_ratio"] = float(close.iloc[-1] / ema20.iloc[-1] - 1)

        vol_ma5 = volume.rolling(5).mean()
        result[f"{prefix}_volume_ratio"] = float(volume.iloc[-1] / vol_ma5.iloc[-1])

        ema5_diff = ema5.diff().iloc[-1]
        if ema5_diff > 0:
            result[f"{prefix}_trend"] = 1.0
        elif ema5_diff < 0:
            result[f"{prefix}_trend"] = -1.0
        else:
            result[f"{prefix}_trend"] = 0.0

        atr = ta.volatility.average_true_range(high, low, close, window=14)
        current_range = float(high.iloc[-1] - low.iloc[-1])
        atr_val = float(atr.iloc[-1])
        result[f"{prefix}_atr_ratio"] = current_range / atr_val if atr_val != 0 else 0.0

        return result

    def build_multi_context(
        self, context_dfs: dict[str, pd.DataFrame],
    ) -> pd.Series:  # type: ignore[type-arg]
        """여러 타임프레임의 context feature를 합쳐서 반환한다.
        Keys: "1m", "3m", "10m", "15m", "60m", "1D" 등.
        """
        result: dict[str, float] = {}
        for tf in self.CONTEXT_TIMEFRAMES:
            prefix = f"ctx_{tf.replace('m', 'M').replace('D', 'D')}"
            df = context_dfs.get(tf)
            if df is not None and len(df) >= 20:
                result.update(self._build_tf_context(df, prefix))
            else:
                for name in self._context_feature_suffixes():
                    result[f"{prefix}_{name}"] = np.nan
        return pd.Series(result, dtype=float)

    @staticmethod
    def _context_feature_suffixes() -> list[str]:
        return ["rsi_14", "ema_5_ratio", "ema_20_ratio",
                "volume_ratio", "trend", "atr_ratio"]

    @staticmethod
    def context_feature_names() -> list[str]:
        names: list[str] = []
        for tf in FeatureBuilder.CONTEXT_TIMEFRAMES:
            prefix = f"ctx_{tf.replace('m', 'M').replace('D', 'D')}"
            for suffix in FeatureBuilder._context_feature_suffixes():
                names.append(f"{prefix}_{suffix}")
        return names

    def get_feature_names(self) -> list[str]:
        return [
            "return_1m", "return_5m", "return_15m", "return_60m",
            "high_low_ratio", "close_position",
            "rsi_14", "rsi_7",
            "macd", "macd_signal", "macd_hist",
            "bb_upper", "bb_lower", "bb_width",
            "ema_5_ratio", "ema_20_ratio", "ema_60_ratio",
            "volume_ratio_5m", "volume_ratio_20m", "volume_trend",
            "ema_30m", "rsi_14_5m",
            "ema_1h", "trend_1h",
        ] + self.context_feature_names()

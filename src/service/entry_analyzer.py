# src/service/entry_analyzer.py
from __future__ import annotations

from decimal import Decimal

import pandas as pd

from src.config.settings import EntryAnalyzerConfig


class EntryAnalyzer:
    """ML BUY 신호 + 기술적 지표를 종합하여 저점 매수 적합도(0~1)를 스코어링."""

    def __init__(self, config: EntryAnalyzerConfig) -> None:
        self._config = config

    def score_entry(self, df: pd.DataFrame, features: pd.DataFrame) -> Decimal:
        """Return a score in [0, 1]. Higher means better entry point.

        Scoring weights:
          - 가격 위치 (40%): 최근 N봉 중 현재가가 저점에 가까울수록 높음
          - RSI 회복 (30%): RSI 과매도(30 이하) 상태에서 회복 중일수록 높음
          - 추세 전환 (30%): MACD 히스토그램 상승 전환 + EMA 아래일수록 높음
        """
        if len(df) < self._config.price_lookback_candles or features.empty:
            return Decimal("0")

        lookback = self._config.price_lookback_candles
        score = Decimal("0")

        # ── 가격 위치 (40%) ──
        recent_close = df["close"].iloc[-lookback:]
        high = recent_close.max()
        low = recent_close.min()
        current = df["close"].iloc[-1]
        if high != low:
            # 0 = 최고점, 1 = 최저점
            price_position = Decimal(str((high - current) / (high - low)))
        else:
            price_position = Decimal("0.5")
        score += price_position * Decimal("0.4")

        # ── RSI 회복 (30%) ──
        rsi_col = "rsi_14"
        if rsi_col in features.columns:
            rsi_val = features[rsi_col].iloc[-1]
            if pd.notna(rsi_val):
                rsi_val = float(rsi_val)
                if rsi_val <= 30:
                    # 과매도 상태 — 높은 점수
                    rsi_score = Decimal("1.0")
                elif rsi_val <= 40:
                    # 과매도 회복 중
                    rsi_score = Decimal(str((40 - rsi_val) / 10))
                elif rsi_val >= 70:
                    # 과매수 — 낮은 점수
                    rsi_score = Decimal("0.0")
                else:
                    # 중립
                    rsi_score = Decimal(str(max(0, (50 - rsi_val) / 50)))
            else:
                rsi_score = Decimal("0.3")
        else:
            rsi_score = Decimal("0.3")
        score += rsi_score * Decimal("0.3")

        # ── 추세 전환 (30%) ──
        trend_score = Decimal("0")
        if "macd_hist" in features.columns and len(features) >= 2:
            hist_curr = features["macd_hist"].iloc[-1]
            hist_prev = features["macd_hist"].iloc[-2]
            if pd.notna(hist_curr) and pd.notna(hist_prev):
                # MACD 히스토그램 상승 전환
                if hist_curr > hist_prev:
                    trend_score += Decimal("0.5")
                # 현재가가 EMA 아래 (ema_20_ratio < 0)
                if "ema_20_ratio" in features.columns:
                    ema_ratio = features["ema_20_ratio"].iloc[-1]
                    if pd.notna(ema_ratio) and float(ema_ratio) < 0:
                        trend_score += Decimal("0.5")
        score += trend_score * Decimal("0.3")

        # ── 다중 시간축 보너스 ──
        # 5분 RSI 과매도 + 1시간 상승추세 = 가산점 (최대 0.1)
        mtf_bonus = Decimal("0")
        if "rsi_14_5m" in features.columns:
            rsi_5m_val = features["rsi_14_5m"].iloc[-1]
            if pd.notna(rsi_5m_val) and float(rsi_5m_val) <= 35:
                mtf_bonus += Decimal("0.05")
        if "trend_1h" in features.columns:
            trend_val = features["trend_1h"].iloc[-1]
            if pd.notna(trend_val) and float(trend_val) > 0:
                mtf_bonus += Decimal("0.05")
        score += mtf_bonus

        # Clamp to [0, 1]
        return max(Decimal("0"), min(Decimal("1"), score))

from __future__ import annotations

import logging
import time
from pathlib import Path

import joblib
import pandas as pd

from src.service.features import FeatureBuilder
from src.types.enums import SignalType
from src.types.models import Signal

logger = logging.getLogger(__name__)

LABEL_TO_SIGNAL = {0: SignalType.SELL, 1: SignalType.HOLD, 2: SignalType.BUY}


class Predictor:
    def __init__(self, feature_builder: FeatureBuilder, min_confidence: float) -> None:
        self._fb = feature_builder
        self._min_confidence = min_confidence
        self._models: dict[str, object] = {}

    def load_model(self, market: str, model_path: Path) -> None:
        self._models[market] = joblib.load(model_path)
        logger.info("Loaded model for %s from %s", market, model_path)

    def predict(self, market: str, candle_df: pd.DataFrame) -> Signal:
        if market not in self._models:
            raise KeyError(f"No model loaded for {market}")

        model = self._models[market]
        features = self._fb.build(candle_df)

        if features.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time()))

        latest = features.dropna().iloc[-1:]
        if latest.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time()))

        proba = model.predict_proba(latest)[0]  # type: ignore[union-attr]
        pred_class = int(proba.argmax())
        confidence = float(proba.max())

        if confidence < self._min_confidence:
            return Signal(market, SignalType.HOLD, confidence, int(time.time()))

        signal_type = LABEL_TO_SIGNAL[pred_class]
        return Signal(market, signal_type, confidence, int(time.time()))

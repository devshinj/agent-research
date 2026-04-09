from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd

from src.service.features import FeatureBuilder
from src.types.enums import SignalType
from src.types.models import Signal, SignalBasis

logger = logging.getLogger(__name__)

LABEL_TO_SIGNAL = {0: SignalType.HOLD, 1: SignalType.BUY}

_EMPTY_BASIS = SignalBasis(top_features=())


class Predictor:
    def __init__(self, feature_builder: FeatureBuilder, min_confidence: float) -> None:
        self._fb = feature_builder
        self._min_confidence = min_confidence
        self._models: dict[str, object] = {}
        self._model_meta: dict[str, dict[str, Any]] = {}

    def update_min_confidence(self, value: float) -> None:
        self._min_confidence = value

    def load_model(self, market: str, model_path: Path) -> None:
        meta_path = model_path.with_suffix(".json")
        meta: dict[str, Any] = {}
        if meta_path.exists():
            meta = json.loads(meta_path.read_text())

        # Feature 불일치 감지: 모델이 학습된 feature 목록과 현재 FeatureBuilder 비교
        model_features = meta.get("features")
        current_features = self._fb.get_feature_names()
        if model_features is not None and not set(model_features).issubset(
            set(current_features)
        ):
            logger.warning(
                "Feature mismatch for %s — model has %d features, builder has %d. "
                "Skipping load (will retrain).",
                market, len(model_features), len(current_features),
            )
            return

        self._models[market] = joblib.load(model_path)
        self._model_meta[market] = meta
        logger.info("Loaded model for %s from %s", market, model_path)

    def get_model_meta(self, market: str) -> dict[str, Any]:
        return self._model_meta.get(market, {})

    def predict(
        self,
        market: str,
        candle_df: pd.DataFrame,
        context_dfs: dict[str, pd.DataFrame] | None = None,
    ) -> tuple[Signal, SignalBasis]:
        if market not in self._models:
            raise KeyError(f"No model loaded for {market}")

        model = self._models[market]
        features = self._fb.build(candle_df)

        if features.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time())), _EMPTY_BASIS

        # 멀티 타임프레임 context feature 합류
        if context_dfs:
            ctx = self._fb.build_multi_context(context_dfs)
            for col_name, val in ctx.items():
                features[col_name] = val

        features = features.ffill()

        # 모델 학습 시 사용한 feature 목록으로 컬럼 정렬/선택
        meta = self._model_meta.get(market, {})
        model_feature_names: list[str] | None = meta.get("features")
        if model_feature_names is not None:
            for col in model_feature_names:
                if col not in features.columns:
                    features[col] = np.nan
            features = features[model_feature_names]

        latest = features.iloc[-1:]
        if latest.isna().any(axis=1).iloc[0]:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time())), _EMPTY_BASIS

        proba = model.predict_proba(latest)[0]  # type: ignore[union-attr]
        pred_class = int(proba.argmax())
        confidence = float(proba.max())

        if confidence < self._min_confidence:
            return Signal(market, SignalType.HOLD, confidence, int(time.time())), _EMPTY_BASIS

        signal_type = LABEL_TO_SIGNAL[pred_class]
        basis = self._compute_basis(model, latest, pred_class, features.columns.tolist())

        return Signal(market, signal_type, confidence, int(time.time())), basis

    def _compute_basis(
        self,
        model: object,
        latest: pd.DataFrame,
        pred_class: int,
        feature_names: list[str],
    ) -> SignalBasis:
        n_features = len(feature_names)
        contrib_raw = model.predict(latest, pred_contrib=True)  # type: ignore[union-attr]
        contrib = np.array(contrib_raw).reshape(1, -1)
        # LightGBM multiclass: flat (1, (n_features+1)*n_classes)
        # reshape to (n_classes, n_features+1)
        n_classes = contrib.shape[1] // (n_features + 1)
        if n_classes <= pred_class:
            return _EMPTY_BASIS
        reshaped = contrib[0].reshape(n_classes, n_features + 1)
        # Get contributions for predicted class, exclude bias (last element)
        class_contrib = reshaped[pred_class, :n_features]

        # Top 5 by absolute value
        top_indices = np.argsort(np.abs(class_contrib))[::-1][:5]
        feature_values = latest.iloc[0]

        top_features = tuple(
            (
                feature_names[i],
                float(class_contrib[i]),
                float(feature_values.iloc[i]),
            )
            for i in top_indices
        )
        return SignalBasis(top_features=top_features)

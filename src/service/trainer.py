from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd

from src.service.features import FeatureBuilder

logger = logging.getLogger(__name__)


class Trainer:
    def __init__(
        self,
        feature_builder: FeatureBuilder,
        model_dir: str,
        lookahead_seconds: int,
        threshold_pct: float,
    ) -> None:
        self._fb = feature_builder
        self._model_dir = Path(model_dir)
        self._lookahead = lookahead_seconds
        self._threshold = threshold_pct

    def _create_labels(self, df: pd.DataFrame) -> pd.Series:
        future_return = (
            df["close"].shift(-self._lookahead) / df["close"] - 1
        ) * 100
        labels = pd.Series(1, index=df.index)  # default HOLD=1
        labels[future_return > self._threshold] = 2   # BUY
        labels[future_return < -self._threshold] = 0  # SELL
        return labels

    def train(self, market: str, candle_df: pd.DataFrame) -> dict[str, Any]:
        features = self._fb.build(candle_df)
        if features.empty:
            logger.warning("Insufficient data for %s", market)
            return {"accuracy": 0, "model_path": None}

        labels = self._create_labels(candle_df).loc[features.index]

        # Drop NaN
        valid_mask = features.notna().all(axis=1) & labels.notna()
        features = features[valid_mask]
        labels = labels[valid_mask]

        if len(features) < 1000:
            logger.warning("Not enough valid samples for %s: %d", market, len(features))
            return {"accuracy": 0, "model_path": None}

        # Time-series split (80/20, no shuffle)
        split_idx = int(len(features) * 0.8)
        X_train, X_val = features.iloc[:split_idx], features.iloc[split_idx:]
        y_train, y_val = labels.iloc[:split_idx], labels.iloc[split_idx:]

        model = lgb.LGBMClassifier(
            n_estimators=200,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
            n_jobs=1,
        )
        model.fit(X_train, y_train)

        val_pred = model.predict(X_val)
        accuracy = float(np.mean(val_pred == y_val))

        # Save model
        timestamp = time.strftime("%Y%m%d_%H%M")
        market_dir = self._model_dir / market.replace("-", "_")
        market_dir.mkdir(parents=True, exist_ok=True)
        model_path = market_dir / f"model_{timestamp}.pkl"

        joblib.dump(model, model_path)

        meta = {
            "market": market,
            "accuracy": accuracy,
            "n_train": len(X_train),
            "n_val": len(X_val),
            "features": list(features.columns),
            "timestamp": timestamp,
        }
        meta_path = model_path.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info("Trained %s — accuracy: %.3f, saved: %s", market, accuracy, model_path)
        return {"accuracy": accuracy, "model_path": model_path}

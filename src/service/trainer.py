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
from sklearn.metrics import f1_score, precision_score, recall_score

from src.service.features import FeatureBuilder

logger = logging.getLogger(__name__)


class Trainer:
    def __init__(
        self,
        feature_builder: FeatureBuilder,
        model_dir: str,
        lookahead_minutes: int,
        threshold_pct: float,
        train_timeframe: int = 5,
    ) -> None:
        self._fb = feature_builder
        self._model_dir = Path(model_dir)
        self._lookahead_minutes = lookahead_minutes
        self._train_timeframe = train_timeframe
        self._lookahead = max(1, lookahead_minutes // train_timeframe)
        self._threshold = threshold_pct

    def update_threshold(self, value: float) -> None:
        self._threshold = value

    def _create_labels(self, df: pd.DataFrame) -> pd.Series:
        future_return = (
            df["close"].shift(-self._lookahead) / df["close"] - 1
        ) * 100
        labels = pd.Series(0, index=df.index)  # default NOT_BUY=0
        labels[future_return > self._threshold] = 1  # BUY
        return labels

    def train(
        self,
        market: str,
        candle_df: pd.DataFrame,
        context_dfs: dict[str, pd.DataFrame] | None = None,
    ) -> dict[str, Any]:
        features = self._fb.build(candle_df)
        if features.empty:
            logger.warning("Insufficient data for %s", market)
            return {"accuracy": 0, "f1": 0.0, "model_path": None}

        # 멀티 타임프레임 context feature 합류
        if context_dfs:
            ctx = self._fb.build_multi_context(context_dfs)
            for col_name, val in ctx.items():
                features[col_name] = val

        labels = self._create_labels(candle_df).loc[features.index]

        # Drop NaN
        valid_mask = features.notna().all(axis=1) & labels.notna()
        features = features[valid_mask]
        labels = labels[valid_mask]

        if len(features) < 100:
            logger.warning("Not enough valid samples for %s: %d", market, len(features))
            return {"accuracy": 0, "f1": 0.0, "model_path": None}

        # Time-series split (80/20, no shuffle)
        split_idx = int(len(features) * 0.8)
        X_train, X_val = features.iloc[:split_idx], features.iloc[split_idx:]
        y_train, y_val = labels.iloc[:split_idx], labels.iloc[split_idx:]

        # 라벨 불균형 대응
        n_hold = int((y_train == 0).sum())
        n_buy = int((y_train == 1).sum())
        spw = n_hold / max(n_buy, 1)
        logger.info(
            "Training %s — samples: %d (train=%d, val=%d), "
            "buy_ratio: %.1f%% (train_buy=%d, train_hold=%d, spw=%.2f), features: %d",
            market, len(features), len(X_train), len(X_val),
            float(labels.mean()) * 100, n_buy, n_hold, spw, X_train.shape[1],
        )

        model = lgb.LGBMClassifier(
            n_estimators=500,
            learning_rate=0.05,
            max_depth=6,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            scale_pos_weight=spw,
            random_state=42,
            verbose=-1,
            n_jobs=1,
        )
        model.fit(
            X_train, y_train,
            eval_set=[(X_val, y_val)],
            callbacks=[lgb.early_stopping(30), lgb.log_evaluation(0)],
        )

        val_pred = model.predict(X_val)
        accuracy = float(np.mean(val_pred == y_val))
        val_f1 = float(f1_score(y_val, val_pred, zero_division=0))
        val_precision = float(precision_score(y_val, val_pred, zero_division=0))
        val_recall = float(recall_score(y_val, val_pred, zero_division=0))
        buy_ratio = float(labels.mean())

        # Save model
        timestamp = time.strftime("%Y%m%d_%H%M")
        market_dir = self._model_dir / market.replace("-", "_")
        market_dir.mkdir(parents=True, exist_ok=True)
        model_path = market_dir / f"model_{timestamp}.pkl"

        joblib.dump(model, model_path)

        meta = {
            "market": market,
            "accuracy": accuracy,
            "f1": val_f1,
            "precision": val_precision,
            "recall": val_recall,
            "buy_ratio": buy_ratio,
            "scale_pos_weight": round(spw, 2),
            "n_train": len(X_train),
            "n_val": len(X_val),
            "best_iteration": model.best_iteration_ if hasattr(model, "best_iteration_") else -1,
            "features": list(features.columns),
            "timestamp": timestamp,
        }
        meta_path = model_path.with_suffix(".json")
        meta_path.write_text(json.dumps(meta, indent=2))

        logger.info(
            "Trained %s — f1: %.3f, precision: %.3f, recall: %.3f, accuracy: %.3f, "
            "buy_ratio: %.3f, spw: %.1f, saved: %s",
            market, val_f1, val_precision, val_recall, accuracy,
            buy_ratio, spw, model_path,
        )
        return {"accuracy": accuracy, "f1": val_f1, "model_path": model_path}

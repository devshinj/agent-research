# Multi-Timeframe Collection & Training Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 멀티 타임프레임(1분/15분/일봉) 수집과 학습 파이프라인 개선으로 모델이 BUY 신호를 적절히 생성하도록 한다.

**Architecture:** Collector가 15분봉+일봉을 추가 수집하고, Trainer가 15분봉 기반으로 학습하며 일봉 context feature를 결합한다. 라벨 불균형 대응(scale_pos_weight), early stopping, F1 검증을 추가한다.

**Tech Stack:** Python 3.12+, LightGBM, pandas, ta, sklearn.metrics, SQLite (aiosqlite)

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `config/settings.yaml` | 멀티 타임프레임 설정값 | Modify |
| `src/config/settings.py` | `CollectorConfig` dataclass | Modify |
| `src/service/collector.py` | 15분봉+일봉 수집 메서드 | Modify |
| `src/service/features.py` | 일봉 context feature 빌더 | Modify |
| `src/service/trainer.py` | 학습 파이프라인 개선 | Modify |
| `src/service/predictor.py` | 예측 시 일봉 feature 포함 | Modify |
| `src/runtime/app.py` | 스케줄러+학습/예측 플로우 | Modify |
| `tests/unit/test_config.py` | 설정 파싱 테스트 | Modify |
| `tests/unit/test_collector.py` | 수집 테스트 | Modify |
| `tests/unit/test_features.py` | 일봉 feature 테스트 | Modify |
| `tests/unit/test_trainer.py` | 학습 파이프라인 테스트 | Modify |
| `tests/unit/test_predictor.py` | 예측 테스트 | Modify |

---

### Task 1: CollectorConfig 확장

**Files:**
- Modify: `config/settings.yaml:34-37`
- Modify: `src/config/settings.py:63-67`
- Modify: `src/config/settings.py:142-145`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_config.py`, add a test that verifies the new fields parse correctly:

```python
def test_collector_multi_timeframe_fields() -> None:
    settings = Settings.from_dict({
        "paper_trading": {
            "initial_balance": 10000000, "max_position_pct": 0.25,
            "max_open_positions": 4, "fee_rate": 0.0005,
            "slippage_rate": 0.0005, "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02, "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015, "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50, "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000, "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0, "max_coins": 10,
            "refresh_interval_min": 30,
        },
        "strategy": {
            "lookahead_minutes": 5, "threshold_pct": 0.3,
            "retrain_interval_hours": 6, "min_confidence": 0.6,
        },
        "collector": {
            "candle_timeframe": 1, "max_candles_per_market": 500,
            "market_refresh_interval_min": 60,
            "train_timeframe": 15, "train_candles": 960,
            "daily_candles": 30,
        },
        "data": {
            "db_path": "data/paper_trader.db", "model_dir": "data/models",
            "stale_candle_days": 7, "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert settings.collector.train_timeframe == 15
    assert settings.collector.train_candles == 960
    assert settings.collector.daily_candles == 30


def test_collector_multi_timeframe_defaults() -> None:
    """train_timeframe 등이 없어도 기본값으로 파싱된다."""
    settings = Settings.from_dict({
        "paper_trading": {
            "initial_balance": 10000000, "max_position_pct": 0.25,
            "max_open_positions": 4, "fee_rate": 0.0005,
            "slippage_rate": 0.0005, "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02, "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015, "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50, "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000, "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0, "max_coins": 10,
            "refresh_interval_min": 30,
        },
        "strategy": {
            "lookahead_minutes": 5, "threshold_pct": 0.3,
            "retrain_interval_hours": 6, "min_confidence": 0.6,
        },
        "collector": {
            "candle_timeframe": 1, "max_candles_per_market": 200,
            "market_refresh_interval_min": 60,
        },
        "data": {
            "db_path": "data/paper_trader.db", "model_dir": "data/models",
            "stale_candle_days": 7, "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert settings.collector.train_timeframe == 15
    assert settings.collector.train_candles == 960
    assert settings.collector.daily_candles == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_config.py::test_collector_multi_timeframe_fields tests/unit/test_config.py::test_collector_multi_timeframe_defaults -v`
Expected: FAIL — `CollectorConfig` has no `train_timeframe` field

- [ ] **Step 3: Add fields to CollectorConfig**

In `src/config/settings.py`, update the `CollectorConfig` dataclass (line 63-67):

```python
@dataclass(frozen=True)
class CollectorConfig:
    candle_timeframe: int
    max_candles_per_market: int
    market_refresh_interval_min: int
    train_timeframe: int = 15
    train_candles: int = 960
    daily_candles: int = 30
```

In the same file, update `from_dict()` (inside the `collector=CollectorConfig(...)` block, around line 142):

```python
collector=CollectorConfig(
    candle_timeframe=int(raw["collector"]["candle_timeframe"]),
    max_candles_per_market=int(raw["collector"]["max_candles_per_market"]),
    market_refresh_interval_min=int(raw["collector"]["market_refresh_interval_min"]),
    train_timeframe=int(raw["collector"].get("train_timeframe", 15)),
    train_candles=int(raw["collector"].get("train_candles", 960)),
    daily_candles=int(raw["collector"].get("daily_candles", 30)),
),
```

In `to_dict()` (inside the `"collector"` dict, around line 203):

```python
"collector": {
    "candle_timeframe": self.collector.candle_timeframe,
    "max_candles_per_market": self.collector.max_candles_per_market,
    "market_refresh_interval_min": self.collector.market_refresh_interval_min,
    "train_timeframe": self.collector.train_timeframe,
    "train_candles": self.collector.train_candles,
    "daily_candles": self.collector.daily_candles,
},
```

- [ ] **Step 4: Update settings.yaml**

In `config/settings.yaml`, update the `collector` section (lines 34-37):

```yaml
collector:
  candle_timeframe: 1
  max_candles_per_market: 500
  train_timeframe: 15
  train_candles: 960
  daily_candles: 30
  market_refresh_interval_min: 60
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_config.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add config/settings.yaml src/config/settings.py tests/unit/test_config.py
git commit -m "feat: add multi-timeframe fields to CollectorConfig"
```

---

### Task 2: Collector — 15분봉+일봉 수집 메서드

**Files:**
- Modify: `src/service/collector.py`
- Test: `tests/unit/test_collector.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_collector.py`, add:

```python
@pytest.fixture
def mock_upbit_client_multi():
    client = AsyncMock()
    client.fetch_markets.return_value = (
        ["KRW-BTC", "KRW-ETH"],
        {"KRW-BTC": "비트코인", "KRW-ETH": "이더리움"},
    )
    client.fetch_candles.return_value = [
        Candle("KRW-BTC", "15m", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("1.5")),
    ]
    client.fetch_daily_candles.return_value = [
        Candle("KRW-BTC", "1D", 1700000000,
               Decimal("50000000"), Decimal("50100000"),
               Decimal("49900000"), Decimal("50050000"), Decimal("100.0")),
    ]
    return client


async def test_collect_train_candles(mock_upbit_client_multi, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client_multi,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=500,
        train_timeframe=15,
        train_candles=960,
        daily_candles=30,
    )
    await collector.collect_train_candles(["KRW-BTC"])
    # 15분봉 + 일봉 각각 fetch 호출
    mock_upbit_client_multi.fetch_candles.assert_awaited_once_with("KRW-BTC", 15, 960)
    mock_upbit_client_multi.fetch_daily_candles.assert_awaited_once_with("KRW-BTC", 30)
    # save_many가 2번 호출 (15분봉 + 일봉)
    assert mock_candle_repo.save_many.await_count == 2
    mock_candle_repo.commit.assert_awaited_once()


def test_collector_creation_with_train_params(mock_upbit_client, mock_candle_repo):
    collector = Collector(
        upbit_client=mock_upbit_client,
        candle_repo=mock_candle_repo,
        timeframe=1,
        max_candles=200,
        train_timeframe=15,
        train_candles=960,
        daily_candles=30,
    )
    assert collector._train_timeframe == 15
    assert collector._train_candles == 960
    assert collector._daily_candles == 30
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_collector.py::test_collect_train_candles tests/unit/test_collector.py::test_collector_creation_with_train_params -v`
Expected: FAIL — `Collector.__init__()` got unexpected keyword argument

- [ ] **Step 3: Implement collect_train_candles**

Replace the entire `src/service/collector.py`:

```python
from __future__ import annotations

import asyncio
import logging

from src.repository.candle_repo import CandleRepository
from src.service.upbit_client import UpbitClient

logger = logging.getLogger(__name__)


class Collector:
    def __init__(
        self,
        upbit_client: UpbitClient,
        candle_repo: CandleRepository,
        timeframe: int,
        max_candles: int,
        train_timeframe: int = 15,
        train_candles: int = 960,
        daily_candles: int = 30,
    ) -> None:
        self._client = upbit_client
        self._repo = candle_repo
        self._timeframe = timeframe
        self._max_candles = max_candles
        self._train_timeframe = train_timeframe
        self._train_candles = train_candles
        self._daily_candles = daily_candles
        self._markets: list[str] = []
        self._korean_names: dict[str, str] = {}

    @property
    def markets(self) -> list[str]:
        return self._markets

    @property
    def korean_names(self) -> dict[str, str]:
        return self._korean_names

    async def refresh_markets(self) -> list[str]:
        self._markets, self._korean_names = await self._client.fetch_markets()
        logger.info("Refreshed markets: %d KRW markets found", len(self._markets))
        return self._markets

    async def collect_candles(self, markets: list[str]) -> None:
        for market in markets:
            try:
                candles = await self._client.fetch_candles(
                    market, self._timeframe, self._max_candles
                )
                if candles:
                    await self._repo.save_many(candles, commit=False)
                    logger.info("Collected %d candles for %s", len(candles), market)
            except Exception:
                logger.exception("Failed to collect candles for %s", market)
            await asyncio.sleep(0.11)  # rate limit: ~9 req/s
        await self._repo.commit()

    async def collect_train_candles(self, markets: list[str]) -> None:
        """15분봉 + 일봉 수집 (학습용)."""
        for market in markets:
            try:
                candles_15m = await self._client.fetch_candles(
                    market, self._train_timeframe, self._train_candles
                )
                if candles_15m:
                    await self._repo.save_many(candles_15m, commit=False)
                    logger.info(
                        "Collected %d %dm candles for %s",
                        len(candles_15m), self._train_timeframe, market,
                    )
            except Exception:
                logger.exception("Failed to collect %dm candles for %s", self._train_timeframe, market)

            try:
                candles_daily = await self._client.fetch_daily_candles(
                    market, self._daily_candles
                )
                if candles_daily:
                    await self._repo.save_many(candles_daily, commit=False)
                    logger.info("Collected %d daily candles for %s", len(candles_daily), market)
            except Exception:
                logger.exception("Failed to collect daily candles for %s", market)

            await asyncio.sleep(0.11)
        await self._repo.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_collector.py -v`
Expected: ALL PASS (기존 테스트도 통과 — 새 파라미터에 기본값 있음)

- [ ] **Step 5: Commit**

```bash
git add src/service/collector.py tests/unit/test_collector.py
git commit -m "feat: add collect_train_candles for 15m + daily collection"
```

---

### Task 3: FeatureBuilder — 일봉 context feature

**Files:**
- Modify: `src/service/features.py`
- Test: `tests/unit/test_features.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_features.py`, add:

```python
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
    """일봉 데이터가 부족하면 NaN이 포함된 Series 반환"""
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_features.py::test_build_daily_context_returns_series tests/unit/test_features.py::test_get_feature_names_includes_daily -v`
Expected: FAIL — `FeatureBuilder` has no attribute `build_daily_context`

- [ ] **Step 3: Implement build_daily_context**

In `src/service/features.py`, add the following method to the `FeatureBuilder` class (after the `_align_higher_tf` method, before `get_feature_names`):

```python
    def build_daily_context(self, daily_df: pd.DataFrame) -> pd.Series:
        """일봉 DataFrame에서 최신 context feature 1행(Series)을 반환한다."""
        result: dict[str, float] = {}

        if len(daily_df) < 20:
            # 데이터 부족 시 NaN으로 채운 Series 반환
            return pd.Series(
                {k: np.nan for k in self._daily_feature_names()},
                dtype=float,
            )

        close = daily_df["close"]
        high = daily_df["high"]
        low = daily_df["low"]
        volume = daily_df["volume"]

        # daily_rsi_14
        rsi = ta.momentum.rsi(close, window=14)
        result["daily_rsi_14"] = float(rsi.iloc[-1])

        # daily_ema_5_ratio
        ema5 = ta.trend.ema_indicator(close, window=5)
        result["daily_ema_5_ratio"] = float(close.iloc[-1] / ema5.iloc[-1] - 1)

        # daily_ema_20_ratio
        ema20 = ta.trend.ema_indicator(close, window=20)
        result["daily_ema_20_ratio"] = float(close.iloc[-1] / ema20.iloc[-1] - 1)

        # daily_volume_ratio
        vol_ma5 = volume.rolling(5).mean()
        result["daily_volume_ratio"] = float(volume.iloc[-1] / vol_ma5.iloc[-1])

        # daily_trend: EMA(5) 기울기 → 1(상승), 0(횡보), -1(하락)
        ema5_diff = ema5.diff().iloc[-1]
        if ema5_diff > 0:
            result["daily_trend"] = 1.0
        elif ema5_diff < 0:
            result["daily_trend"] = -1.0
        else:
            result["daily_trend"] = 0.0

        # daily_atr_ratio
        atr = ta.volatility.average_true_range(high, low, close, window=14)
        current_range = float(high.iloc[-1] - low.iloc[-1])
        atr_val = float(atr.iloc[-1])
        result["daily_atr_ratio"] = current_range / atr_val if atr_val != 0 else 0.0

        return pd.Series(result, dtype=float)

    @staticmethod
    def _daily_feature_names() -> list[str]:
        return [
            "daily_rsi_14", "daily_ema_5_ratio", "daily_ema_20_ratio",
            "daily_volume_ratio", "daily_trend", "daily_atr_ratio",
        ]
```

Update `get_feature_names()` to include daily features:

```python
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
        ] + self._daily_feature_names()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_features.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/features.py tests/unit/test_features.py
git commit -m "feat: add daily context features to FeatureBuilder"
```

---

### Task 4: Trainer — 학습 파이프라인 개선

**Files:**
- Modify: `src/service/trainer.py`
- Test: `tests/unit/test_trainer.py`

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_trainer.py`, add:

```python
def make_daily_data(n: int = 30) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 500000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 200000,
        "high": close + np.abs(np.random.randn(n)) * 500000,
        "low": close - np.abs(np.random.randn(n)) * 500000,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 10,
    })


def test_trainer_with_daily_context(tmp_path):
    """학습 시 일봉 context를 전달하면 30개 feature 모델이 생성된다."""
    df = make_training_data(500)
    daily_df = make_daily_data(30)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df, daily_df=daily_df)
    assert result["model_path"] is not None
    # 메타데이터에 daily feature가 포함되어야 함
    import json
    meta = json.loads(result["model_path"].with_suffix(".json").read_text())
    assert "daily_rsi_14" in meta["features"]
    assert len(meta["features"]) == 30


def test_trainer_metadata_includes_f1(tmp_path):
    """메타데이터에 f1, precision, recall이 포함된다."""
    df = make_training_data(500)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    import json
    meta = json.loads(result["model_path"].with_suffix(".json").read_text())
    assert "f1" in meta
    assert "precision" in meta
    assert "recall" in meta
    assert "buy_ratio" in meta


def test_trainer_result_includes_f1(tmp_path):
    """train() 반환값에 f1이 포함된다."""
    df = make_training_data(500)
    feature_builder = FeatureBuilder()
    trainer = Trainer(feature_builder, str(tmp_path), 5, 0.3)
    result = trainer.train("KRW-BTC", df)
    assert "f1" in result
    assert isinstance(result["f1"], float)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_trainer.py::test_trainer_with_daily_context tests/unit/test_trainer.py::test_trainer_metadata_includes_f1 tests/unit/test_trainer.py::test_trainer_result_includes_f1 -v`
Expected: FAIL — `train()` got unexpected keyword argument `daily_df`

- [ ] **Step 3: Implement trainer improvements**

Replace the entire `src/service/trainer.py`:

```python
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
    ) -> None:
        self._fb = feature_builder
        self._model_dir = Path(model_dir)
        self._lookahead = lookahead_minutes
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
        daily_df: pd.DataFrame | None = None,
    ) -> dict[str, Any]:
        features = self._fb.build(candle_df)
        if features.empty:
            logger.warning("Insufficient data for %s", market)
            return {"accuracy": 0, "f1": 0.0, "model_path": None}

        # 일봉 context feature 합류
        if daily_df is not None and len(daily_df) >= 20:
            daily_ctx = self._fb.build_daily_context(daily_df)
            for col_name, val in daily_ctx.items():
                features[col_name] = val
        else:
            for col_name in self._fb._daily_feature_names():
                features[col_name] = np.nan

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
```

- [ ] **Step 4: Run all trainer tests**

Run: `uv run pytest tests/unit/test_trainer.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/trainer.py tests/unit/test_trainer.py
git commit -m "feat: improve training pipeline — scale_pos_weight, early stopping, F1 metrics"
```

---

### Task 5: Predictor — 일봉 context feature 포함

**Files:**
- Modify: `src/service/predictor.py`
- Test: `tests/unit/test_predictor.py`

- [ ] **Step 1: Write the failing test**

In `tests/unit/test_predictor.py`, add:

```python
def make_daily(n=30):
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 500000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 200000,
        "high": close + np.abs(np.random.randn(n)) * 500000,
        "low": close - np.abs(np.random.randn(n)) * 500000,
        "close": close,
        "volume": np.random.rand(n) * 1000 + 10,
    })


@pytest.fixture
def trained_model_with_daily(tmp_path):
    """일봉 context 포함하여 학습된 모델 (30 features)"""
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_data()
    daily_df = make_daily()
    result = trainer.train("KRW-BTC", df, daily_df=daily_df)
    return result["model_path"]


def test_predictor_with_daily_context(trained_model_with_daily):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model_with_daily)
    df = make_data(200)
    daily_df = make_daily(30)
    signal, basis = predictor.predict("KRW-BTC", df, daily_df=daily_df)
    assert signal.signal_type in (SignalType.BUY, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_predictor.py::test_predictor_with_daily_context -v`
Expected: FAIL — `predict()` got unexpected keyword argument `daily_df`

- [ ] **Step 3: Update predictor**

In `src/service/predictor.py`, update the `predict` method (line 58):

Replace the entire `predict` method:

```python
    def predict(
        self,
        market: str,
        candle_df: pd.DataFrame,
        daily_df: pd.DataFrame | None = None,
    ) -> tuple[Signal, SignalBasis]:
        if market not in self._models:
            raise KeyError(f"No model loaded for {market}")

        model = self._models[market]
        features = self._fb.build(candle_df)

        if features.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time())), _EMPTY_BASIS

        # 일봉 context feature 합류
        if daily_df is not None and len(daily_df) >= 20:
            daily_ctx = self._fb.build_daily_context(daily_df)
            for col_name, val in daily_ctx.items():
                features[col_name] = val
        else:
            for col_name in self._fb._daily_feature_names():
                features[col_name] = np.nan

        features = features.ffill()
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
```

Also add `import numpy as np` at the top of the file if not already present.

- [ ] **Step 4: Run all predictor tests**

Run: `uv run pytest tests/unit/test_predictor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/predictor.py tests/unit/test_predictor.py
git commit -m "feat: add daily context feature support to Predictor"
```

---

### Task 6: App.py — 멀티 타임프레임 수집 스케줄 + 학습/예측 플로우

**Files:**
- Modify: `src/runtime/app.py`

- [ ] **Step 1: Update Collector initialization**

In `src/runtime/app.py`, update the Collector constructor (around line 80-83):

Replace:
```python
self.collector = Collector(
    self.upbit, self.candle_repo,
    settings.collector.candle_timeframe, settings.collector.max_candles_per_market,
)
```

With:
```python
self.collector = Collector(
    self.upbit, self.candle_repo,
    settings.collector.candle_timeframe, settings.collector.max_candles_per_market,
    train_timeframe=settings.collector.train_timeframe,
    train_candles=settings.collector.train_candles,
    daily_candles=settings.collector.daily_candles,
)
```

- [ ] **Step 2: Add _collect_train_data method and schedule**

In `app.py`, add the new method after `_collect_and_predict` (around line 545):

```python
    async def _collect_train_data(self) -> None:
        """15분봉 + 일봉 수집 (학습 데이터용)."""
        if not self.screened_markets:
            return
        async with self._db_lock:
            await self.collector.collect_train_candles(self.screened_markets)
```

In the `start()` method, after the existing `schedule_interval` calls (around line 228), add:

```python
        self.scheduler.schedule_interval(
            "collect_train_data", self._collect_train_data,
            interval_seconds=900,  # 15분마다
        )
```

- [ ] **Step 3: Update startup to seed train data**

In `start()`, after the existing `collect_candles` call (around line 205), add:

```python
            logger.info("Seeding training data (15m + daily) for %d markets...", len(self.screened_markets))
            await self.collector.collect_train_candles(self.screened_markets)
```

- [ ] **Step 4: Update _train_missing_models to use 15m + daily**

Replace the `_train_missing_models` method (lines 266-291):

```python
    async def _train_missing_models(self) -> None:
        """Train models for screened markets that don't have a loaded model."""
        train_tf = f"{self.settings.collector.train_timeframe}m"
        pending: dict[str, tuple[pd.DataFrame, pd.DataFrame | None]] = {}

        async with self._db_lock:
            for market in self.screened_markets:
                if market in self.predictor._models:
                    continue
                candles = await self.candle_repo.get_latest(
                    market, train_tf, self.settings.collector.train_candles,
                )
                if len(candles) < 200:
                    logger.info("Not enough %s candles for %s: %d", train_tf, market, len(candles))
                    continue
                df = self._candles_to_df(candles)

                daily_candles = await self.candle_repo.get_latest(
                    market, "1D", self.settings.collector.daily_candles,
                )
                daily_df = self._candles_to_df(daily_candles) if len(daily_candles) >= 20 else None
                pending[market] = (df, daily_df)

        for market, (df, daily_df) in pending.items():
            self.training_in_progress[market] = time.time()
            try:
                result = self.trainer.train(market, df, daily_df=daily_df)
                if result["model_path"] is not None:
                    self.predictor.load_model(market, result["model_path"])
                    logger.info(
                        "Trained and loaded model for %s (f1: %.3f, accuracy: %.3f)",
                        market, result["f1"], result["accuracy"],
                    )
                else:
                    logger.info("Training skipped for %s: insufficient valid samples", market)
            finally:
                self.training_in_progress.pop(market, None)
```

- [ ] **Step 5: Update _retrain to use 15m + daily**

Replace the `_retrain` method (lines 293-320):

```python
    async def _retrain(self) -> None:
        """Retrain models for all screened markets one at a time to limit memory."""
        if not self.screened_markets:
            return

        logger.info("Starting periodic retrain for %d markets", len(self.screened_markets))
        train_tf = f"{self.settings.collector.train_timeframe}m"
        trained = 0
        total = 0

        for market in list(self.screened_markets):
            async with self._db_lock:
                candles = await self.candle_repo.get_latest(
                    market, train_tf, self.settings.collector.train_candles,
                )
                daily_candles = await self.candle_repo.get_latest(
                    market, "1D", self.settings.collector.daily_candles,
                )
            if len(candles) < 200:
                continue
            total += 1
            df = self._candles_to_df(candles)
            daily_df = self._candles_to_df(daily_candles) if len(daily_candles) >= 20 else None

            self.training_in_progress[market] = time.time()
            try:
                result = self.trainer.train(market, df, daily_df=daily_df)
                if result["model_path"] is not None:
                    self.predictor.load_model(market, result["model_path"])
                    trained += 1
            finally:
                self.training_in_progress.pop(market, None)
            del df

        logger.info("Retrain complete: %d/%d markets updated", trained, total)
```

- [ ] **Step 6: Update _collect_and_predict to pass daily context to predictor**

In the `_collect_and_predict` method, update the prediction loop. Replace the inner `for market` loop (around lines 515-544):

```python
            for market in self.screened_markets:
                candles = await self.candle_repo.get_latest(
                    market, f"{self.settings.collector.candle_timeframe}m"
                )
                if len(candles) < 60:
                    logger.warning(
                        "%s: insufficient candles (%d/60) — skipping prediction",
                        market, len(candles),
                    )
                    continue

                df = self._candles_to_df(candles)

                # 일봉 context 조회
                daily_candles = await self.candle_repo.get_latest(
                    market, "1D", self.settings.collector.daily_candles,
                )
                daily_df = self._candles_to_df(daily_candles) if len(daily_candles) >= 20 else None

                try:
                    signal, basis = self.predictor.predict(market, df, daily_df=daily_df)
                    basis_json: str | None = None
                    if basis.top_features:
                        basis_json = json.dumps([
                            {"feature": f, "shap": round(s, 4), "value": round(v, 4)}
                            for f, s, v in basis.top_features
                        ])
                    await self.signal_repo.save(
                        signal.market, signal.signal_type.name,
                        signal.confidence, signal.timestamp, basis_json,
                    )
                    await self.event_bus.publish(SignalEvent(
                        signal.market, signal.signal_type, signal.confidence, signal.timestamp,
                    ))
                except KeyError:
                    logger.warning("%s: no trained model loaded — skipping prediction", market)
```

- [ ] **Step 7: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 8: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: integrate multi-timeframe collection and training in App"
```

---

### Task 7: Integration Verification

- [ ] **Step 1: Run full test suite with coverage**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 3: Run type checker**

Run: `uv run mypy src/`
Expected: No new errors

- [ ] **Step 4: Fix any issues found in steps 1-3**

Address any failures, lint errors, or type errors.

- [ ] **Step 5: Final commit if any fixes were needed**

```bash
git add -u
git commit -m "fix: resolve lint/type issues from multi-timeframe integration"
```

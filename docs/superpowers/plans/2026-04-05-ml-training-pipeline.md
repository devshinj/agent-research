# ML Training Pipeline — App Integration Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire the existing `Trainer` into `App` so models are auto-loaded on startup, trained when missing, and retrained every 6 hours — enabling the trading pipeline to actually execute trades.

**Architecture:** `App.__init__` creates a `Trainer` instance. `App.start()` loads existing models from `data/models/`, trains missing ones, and schedules periodic retraining. The existing `Predictor`, `FeatureBuilder`, and `Trainer` classes are unchanged.

**Tech Stack:** Python 3.12, LightGBM (already in deps), joblib, asyncio

---

### Task 1: Add Trainer to App.__init__

**Files:**
- Modify: `src/runtime/app.py:1-60`

- [ ] **Step 1: Add Trainer import**

Add to the imports section of `src/runtime/app.py`:

```python
from src.service.trainer import Trainer
```

- [ ] **Step 2: Create Trainer instance in __init__**

Add after `self.portfolio_manager = PortfolioManager(settings.risk)` (line 52):

```python
self.trainer = Trainer(
    self.feature_builder,
    settings.data.model_dir,
    settings.strategy.lookahead_minutes,
    float(settings.strategy.threshold_pct),
)
```

- [ ] **Step 3: Verify import works**

Run: `uv run python -c "from src.runtime.app import App; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: add Trainer instance to App.__init__"
```

---

### Task 2: Load existing models on startup

**Files:**
- Modify: `src/runtime/app.py:62-103` (App.start method)

- [ ] **Step 1: Add _load_existing_models method**

Add this method to the `App` class, after the `start()` method:

```python
async def _load_existing_models(self) -> int:
    """Load all .pkl models from data/models/ into predictor."""
    model_dir = Path(self.settings.data.model_dir)
    if not model_dir.exists():
        model_dir.mkdir(parents=True, exist_ok=True)
        return 0

    loaded = 0
    for market_dir in model_dir.iterdir():
        if not market_dir.is_dir():
            continue
        # Find most recent model file
        model_files = sorted(market_dir.glob("model_*.pkl"), reverse=True)
        if not model_files:
            continue
        market = market_dir.name.replace("_", "-")
        self.predictor.load_model(market, model_files[0])
        loaded += 1
    return loaded
```

- [ ] **Step 2: Call _load_existing_models in start()**

In `App.start()`, add after the event handler wiring (after line 84) and before `await self.collector.refresh_markets()`:

```python
loaded = await self._load_existing_models()
logger.info("Loaded %d existing models", loaded)
```

- [ ] **Step 3: Verify no errors on startup with empty model dir**

Run: `uv run python -c "
import asyncio
from pathlib import Path
from src.config.settings import Settings
from src.runtime.app import App
s = Settings.from_yaml(Path('config/settings.yaml'))
app = App(s)
print('Trainer:', type(app.trainer).__name__)
print('Model dir:', app.settings.data.model_dir)
"`
Expected: prints Trainer class name and model dir path without errors.

- [ ] **Step 4: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: load existing ML models on App startup"
```

---

### Task 3: Train missing models on startup

**Files:**
- Modify: `src/runtime/app.py:62-103` (App.start method)

- [ ] **Step 1: Add _train_missing_models method**

Add this method to the `App` class:

```python
async def _train_missing_models(self) -> None:
    """Train models for screened markets that don't have a loaded model."""
    timeframe = f"{self.settings.collector.candle_timeframe}m"
    for market in self.screened_markets:
        if market in self.predictor._models:
            continue
        candles = await self.candle_repo.get_latest(market, timeframe, limit=2000)
        if len(candles) < 200:
            logger.info("Not enough candles for %s: %d", market, len(candles))
            continue

        import pandas as pd
        df = pd.DataFrame([
            {"open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close),
             "volume": float(c.volume)}
            for c in reversed(candles)
        ])

        result = self.trainer.train(market, df)
        if result["model_path"] is not None:
            self.predictor.load_model(market, result["model_path"])
            logger.info("Trained and loaded model for %s (accuracy: %.3f)", market, result["accuracy"])
        else:
            logger.info("Training skipped for %s: insufficient valid samples", market)
```

- [ ] **Step 2: Call _train_missing_models in start()**

In `App.start()`, add after the initial screening. Restructure the end of `start()` so screening runs first, then training. After `await self.collector.refresh_markets()` (line 87), add:

```python
# Initial screening + model training
await self._refresh_screening()
await self._train_missing_models()
```

- [ ] **Step 3: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: train missing models on App startup after screening"
```

---

### Task 4: Schedule periodic retraining

**Files:**
- Modify: `src/runtime/app.py:89-103` (scheduler section of start)

- [ ] **Step 1: Add _retrain method**

Add this method to the `App` class:

```python
async def _retrain(self) -> None:
    """Retrain models for all screened markets."""
    if self.paused or not self.screened_markets:
        return

    logger.info("Starting periodic retrain for %d markets", len(self.screened_markets))
    timeframe = f"{self.settings.collector.candle_timeframe}m"
    trained = 0
    for market in self.screened_markets:
        candles = await self.candle_repo.get_latest(market, timeframe, limit=2000)
        if len(candles) < 200:
            continue

        import pandas as pd
        df = pd.DataFrame([
            {"open": float(c.open), "high": float(c.high),
             "low": float(c.low), "close": float(c.close),
             "volume": float(c.volume)}
            for c in reversed(candles)
        ])

        result = self.trainer.train(market, df)
        if result["model_path"] is not None:
            self.predictor.load_model(market, result["model_path"])
            trained += 1

    logger.info("Retrain complete: %d/%d markets updated", trained, len(self.screened_markets))
```

- [ ] **Step 2: Register retrain schedule in start()**

Add after the existing `schedule_interval` calls (after line 101):

```python
self.scheduler.schedule_interval(
    "retrain_models", self._retrain,
    interval_seconds=self.settings.strategy.retrain_interval_hours * 3600,
)
```

- [ ] **Step 3: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: schedule periodic model retraining every 6 hours"
```

---

### Task 5: Extract shared candle-to-DataFrame helper

**Files:**
- Modify: `src/runtime/app.py`

The candle-to-DataFrame conversion is now repeated in `_collect_and_predict`, `_train_missing_models`, and `_retrain`. Extract a static helper to DRY this up.

- [ ] **Step 1: Add _candles_to_df static method**

Add to the `App` class:

```python
@staticmethod
def _candles_to_df(candles: list) -> pd.DataFrame:
    import pandas as pd
    return pd.DataFrame([
        {"open": float(c.open), "high": float(c.high),
         "low": float(c.low), "close": float(c.close),
         "volume": float(c.volume)}
        for c in reversed(candles)
    ])
```

- [ ] **Step 2: Replace inline conversions**

Replace the DataFrame construction in `_collect_and_predict` (lines 132-139), `_train_missing_models`, and `_retrain` with:

```python
df = self._candles_to_df(candles)
```

Also move the `import pandas as pd` to the top-level imports of `app.py`, and remove the inline `from decimal import Decimal` import in `_collect_and_predict` (it's unused).

- [ ] **Step 3: Run existing tests**

Run: `uv run pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 4: Commit**

```bash
git add src/runtime/app.py
git commit -m "refactor: extract _candles_to_df helper to DRY app.py"
```

---

### Task 6: Integration test — training triggers trade pipeline

**Files:**
- Create: `tests/integration/test_training_integration.py`

- [ ] **Step 1: Write integration test**

```python
import pytest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import AsyncMock, patch

from src.service.features import FeatureBuilder
from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.types.enums import SignalType


def make_candle_df(n: int = 600) -> pd.DataFrame:
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


def test_train_then_predict(tmp_path):
    """Trainer produces a model that Predictor can use to generate signals."""
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), lookahead_minutes=5, threshold_pct=0.3)
    predictor = Predictor(fb, min_confidence=0.0)

    df = make_candle_df(600)
    result = trainer.train("KRW-BTC", df)

    assert result["model_path"] is not None, "Training should succeed with 600 candles"
    assert result["accuracy"] > 0

    predictor.load_model("KRW-BTC", result["model_path"])
    signal = predictor.predict("KRW-BTC", df.tail(200).reset_index(drop=True))

    assert signal.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert signal.market == "KRW-BTC"


def test_model_persisted_and_reloadable(tmp_path):
    """Model saved by Trainer can be loaded by a fresh Predictor instance."""
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_candle_df(600)
    result = trainer.train("KRW-BTC", df)

    # Fresh predictor loads the saved model
    predictor2 = Predictor(FeatureBuilder(), min_confidence=0.0)
    predictor2.load_model("KRW-BTC", result["model_path"])

    signal = predictor2.predict("KRW-BTC", df.tail(200).reset_index(drop=True))
    assert signal.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
```

- [ ] **Step 2: Run the integration test**

Run: `uv run pytest tests/integration/test_training_integration.py -v`
Expected: both tests pass

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_training_integration.py
git commit -m "test: add training-to-prediction integration test"
```

---

### Task 7: Verify full system

- [ ] **Step 1: Run all tests**

Run: `uv run pytest tests/ -v`
Expected: all tests pass

- [ ] **Step 2: Run linter and type check**

Run: `uv run ruff check src/runtime/app.py`
Run: `uv run mypy src/runtime/app.py`
Fix any issues.

- [ ] **Step 3: Final commit if any fixes**

```bash
git add -A
git commit -m "fix: address lint/type issues in app.py"
```

# Signal Basis Tooltip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show per-signal SHAP-based reasoning as a hover tooltip on the active signals table, so users understand why each BUY/SELL signal was generated.

**Architecture:** Extend `Predictor.predict()` to compute LightGBM TreeSHAP contributions via `predict(pred_contrib=True)`, store top-5 features as JSON in the `signals` DB table, serve through existing API, and render as CSS hover tooltip in Strategy.tsx.

**Tech Stack:** Python (LightGBM pred_contrib, dataclasses), SQLite (basis column), React/TypeScript (CSS tooltip)

---

## File Structure

| File | Change | Responsibility |
|------|--------|---------------|
| `src/types/models.py` | Add `SignalBasis` | Data structure for top-5 SHAP features |
| `src/service/predictor.py` | Modify `predict()` | Compute SHAP, return `(Signal, SignalBasis)` |
| `src/repository/database.py` | Modify schema | Add `basis TEXT` column |
| `src/repository/signal_repo.py` | Modify `save()`, `get_recent()` | Store/retrieve basis JSON |
| `src/runtime/app.py` | Modify `_collect_and_predict()` | Unpack tuple, serialize basis |
| `src/ui/api/routes/strategy.py` | Modify `get_signals()` | Include basis in response |
| `src/ui/frontend/src/pages/Strategy.tsx` | Add tooltip UI | Hover tooltip with SHAP reasoning |
| `src/ui/frontend/src/index.css` | Add tooltip styles | CSS for signal tooltip |
| `tests/unit/test_predictor.py` | Modify existing tests | Adapt to tuple return |
| `tests/unit/test_signal_repo.py` | Add basis tests | Test basis storage |

---

### Task 1: Add `SignalBasis` dataclass

**Files:**
- Modify: `src/types/models.py:54-59`

- [ ] **Step 1: Add SignalBasis dataclass**

In `src/types/models.py`, add after the `Signal` class (after line 59):

```python
@dataclass(frozen=True)
class SignalBasis:
    """Top contributing features for a signal prediction (SHAP values)."""
    top_features: tuple[tuple[str, float, float], ...]
    # Each tuple: (feature_name, shap_value, feature_value)
```

- [ ] **Step 2: Run structural tests**

Run: `uv run pytest tests/structural/ -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/types/models.py
git commit -m "feat: add SignalBasis dataclass for SHAP reasoning"
```

---

### Task 2: Extend `Predictor.predict()` to return SHAP contributions

**Files:**
- Modify: `src/service/predictor.py:43-65`
- Test: `tests/unit/test_predictor.py`

- [ ] **Step 1: Update existing tests to expect tuple return**

Replace the entire `tests/unit/test_predictor.py`:

```python
import pytest
import numpy as np
import pandas as pd
from pathlib import Path

from src.service.trainer import Trainer
from src.service.predictor import Predictor
from src.service.features import FeatureBuilder
from src.types.enums import SignalType
from src.types.models import SignalBasis


def make_data(n=500):
    np.random.seed(42)
    close = 50000000 + np.cumsum(np.random.randn(n) * 100000)
    return pd.DataFrame({
        "open": close - np.random.rand(n) * 50000,
        "high": close + np.abs(np.random.randn(n)) * 100000,
        "low": close - np.abs(np.random.randn(n)) * 100000,
        "close": close,
        "volume": np.random.rand(n) * 10 + 0.1,
    })


@pytest.fixture
def trained_model(tmp_path):
    fb = FeatureBuilder()
    trainer = Trainer(fb, str(tmp_path), 5, 0.3)
    df = make_data()
    result = trainer.train("KRW-BTC", df)
    return result["model_path"]


def test_predictor_returns_signal_and_basis(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    assert signal.signal_type in (SignalType.BUY, SignalType.SELL, SignalType.HOLD)
    assert 0 <= signal.confidence <= 1
    assert isinstance(basis, SignalBasis)
    if signal.signal_type != SignalType.HOLD:
        assert len(basis.top_features) == 5
        for name, shap_val, feat_val in basis.top_features:
            assert isinstance(name, str)
            assert isinstance(shap_val, float)
            assert isinstance(feat_val, float)


def test_predictor_hold_returns_empty_basis(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.99)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    assert signal.signal_type == SignalType.HOLD
    assert basis.top_features == ()


def test_predictor_no_model_raises():
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.6)
    with pytest.raises(KeyError):
        predictor.predict("KRW-NONE", make_data(200))


def test_predictor_basis_sorted_by_abs_shap(trained_model):
    fb = FeatureBuilder()
    predictor = Predictor(fb, min_confidence=0.0)
    predictor.load_model("KRW-BTC", trained_model)
    df = make_data(200)
    signal, basis = predictor.predict("KRW-BTC", df)
    if signal.signal_type != SignalType.HOLD and len(basis.top_features) > 1:
        abs_shaps = [abs(s) for _, s, _ in basis.top_features]
        assert abs_shaps == sorted(abs_shaps, reverse=True)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_predictor.py -v`
Expected: FAIL (predict returns Signal, not tuple)

- [ ] **Step 3: Implement SHAP contribution in predict()**

Replace the `predict` method in `src/service/predictor.py` (lines 43-65) and add the import:

```python
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

LABEL_TO_SIGNAL = {0: SignalType.SELL, 1: SignalType.HOLD, 2: SignalType.BUY}

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
        self._models[market] = joblib.load(model_path)
        meta_path = model_path.with_suffix(".json")
        if meta_path.exists():
            self._model_meta[market] = json.loads(meta_path.read_text())
        else:
            self._model_meta[market] = {}
        logger.info("Loaded model for %s from %s", market, model_path)

    def get_model_meta(self, market: str) -> dict[str, Any]:
        return self._model_meta.get(market, {})

    def predict(self, market: str, candle_df: pd.DataFrame) -> tuple[Signal, SignalBasis]:
        if market not in self._models:
            raise KeyError(f"No model loaded for {market}")

        model = self._models[market]
        features = self._fb.build(candle_df)

        if features.empty:
            return Signal(market, SignalType.HOLD, 0.0, int(time.time())), _EMPTY_BASIS

        latest = features.dropna().iloc[-1:]
        if latest.empty:
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_predictor.py -v`
Expected: ALL PASS

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: FAIL — `app.py` and other callers still expect single return value. This is expected; we fix those in later tasks.

- [ ] **Step 6: Commit**

```bash
git add src/service/predictor.py tests/unit/test_predictor.py
git commit -m "feat: add SHAP basis computation to Predictor.predict()"
```

---

### Task 3: Extend signals DB schema and repository

**Files:**
- Modify: `src/repository/database.py:80-87`
- Modify: `src/repository/signal_repo.py:13-48`
- Test: `tests/unit/test_signal_repo.py`

- [ ] **Step 1: Add test for basis storage**

Add at the end of `tests/unit/test_signal_repo.py`:

```python
import json


async def test_save_and_get_with_basis(signal_repo):
    basis_json = json.dumps([
        {"feature": "rsi_14", "shap": 0.15, "value": 72.3},
        {"feature": "volume_ratio_5m", "shap": 0.12, "value": 2.4},
    ])
    await signal_repo.save("KRW-BTC", "BUY", 0.82, 1700000000, basis_json)
    await signal_repo.save("KRW-ETH", "SELL", 0.65, 1700000001, None)

    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 2

    # KRW-ETH is newer
    assert results[0]["basis"] is None
    # KRW-BTC has basis
    assert results[1]["basis"] == basis_json


async def test_save_without_basis_backward_compat(signal_repo):
    """Existing callers can still call save without basis argument."""
    await signal_repo.save("KRW-BTC", "BUY", 0.75, 1700000000)
    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 1
    assert results[0]["basis"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_signal_repo.py::test_save_and_get_with_basis tests/unit/test_signal_repo.py::test_save_without_basis_backward_compat -v`
Expected: FAIL (save() doesn't accept basis parameter)

- [ ] **Step 3: Update database schema**

In `src/repository/database.py`, the schema string already has `basis TEXT` in the signals table (line 86: `outcome TEXT`). Replace the signals table definition (lines 80-87):

```sql
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    timestamp   INTEGER NOT NULL,
    outcome     TEXT,
    basis       TEXT
);
```

- [ ] **Step 4: Update SignalRepository.save()**

In `src/repository/signal_repo.py`, replace the `save` method (lines 13-21):

```python
async def save(
    self, market: str, signal_type: str, confidence: float, timestamp: int,
    basis: str | None = None,
) -> None:
    await self._db.conn.execute(
        "INSERT INTO signals (market, signal_type, confidence, timestamp, basis) "
        "VALUES (?, ?, ?, ?, ?)",
        (market, signal_type, confidence, timestamp, basis),
    )
    await self._db.conn.commit()
```

- [ ] **Step 5: Update SignalRepository.get_recent()**

In `src/repository/signal_repo.py`, replace the `get_recent` method (lines 23-48):

```python
async def get_recent(
    self, limit: int = 50, include_hold: bool = False,
) -> list[dict[str, object]]:
    if include_hold:
        cursor = await self._db.conn.execute(
            "SELECT market, signal_type, confidence, timestamp, basis "
            "FROM signals ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    else:
        cursor = await self._db.conn.execute(
            "SELECT market, signal_type, confidence, timestamp, basis "
            "FROM signals WHERE signal_type != 'HOLD' "
            "ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        )
    rows = await cursor.fetchall()
    return [
        {
            "market": r[0],
            "signal_type": r[1],
            "confidence": r[2],
            "timestamp": r[3],
            "basis": r[4],
        }
        for r in rows
    ]
```

- [ ] **Step 6: Run signal repo tests**

Run: `uv run pytest tests/unit/test_signal_repo.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/repository/database.py src/repository/signal_repo.py tests/unit/test_signal_repo.py
git commit -m "feat: add basis column to signals table and repository"
```

---

### Task 4: Update App._collect_and_predict() for tuple return

**Files:**
- Modify: `src/runtime/app.py:375-385`

- [ ] **Step 1: Add json import if not present**

At top of `src/runtime/app.py`, ensure `import json` is present. Check existing imports first.

- [ ] **Step 2: Update _collect_and_predict()**

In `src/runtime/app.py`, replace lines 375-385 (the try/except block inside the for loop):

```python
                try:
                    signal, basis = self.predictor.predict(market, df)
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
                    pass  # model not loaded
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 4: Run linter and type checker**

Run: `uv run ruff check src/ && uv run mypy src/`
Expected: No new errors

- [ ] **Step 5: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: serialize signal basis to DB in collect_and_predict"
```

---

### Task 5: Add basis to API response

**Files:**
- Modify: `src/ui/api/routes/strategy.py:35-54`

- [ ] **Step 1: Update get_signals() to include basis**

In `src/ui/api/routes/strategy.py`, add `import json` at the top (after existing imports), then replace the return list comprehension in `get_signals()` (lines 44-54):

```python
    return [
        {
            "market": r["market"],
            "signal_type": r["signal_type"],
            "confidence": r["confidence"],
            "created_at": datetime.fromtimestamp(
                r["timestamp"], tz=UTC,
            ).strftime("%Y-%m-%d %H:%M:%S"),
            "basis": json.loads(r["basis"]) if r.get("basis") else None,
        }
        for r in rows
    ]
```

- [ ] **Step 2: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 3: Commit**

```bash
git add src/ui/api/routes/strategy.py
git commit -m "feat: include signal basis in API response"
```

---

### Task 6: Add tooltip CSS styles

**Files:**
- Modify: `src/ui/frontend/src/index.css`

- [ ] **Step 1: Append tooltip CSS**

Append to the end of `src/ui/frontend/src/index.css`:

```css
/* ── Signal Tooltip ───────────────────────────── */
.signal-row {
  position: relative;
  cursor: default;
}

.signal-tooltip {
  display: none;
  position: absolute;
  top: 100%;
  left: 16px;
  z-index: 100;
  min-width: 320px;
  padding: 14px 16px;
  background: var(--bg-card);
  border: 1px solid var(--border-bright);
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.4);
  font-family: var(--font-mono);
  font-size: 12px;
}

.signal-row:hover .signal-tooltip {
  display: block;
}

.signal-tooltip-title {
  font-family: var(--font-display);
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  color: var(--accent);
  margin-bottom: 10px;
}

.signal-tooltip-row {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 4px 0;
}

.signal-tooltip-arrow {
  font-size: 13px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.signal-tooltip-arrow.up { color: var(--profit); }
.signal-tooltip-arrow.down { color: var(--loss); }

.signal-tooltip-name {
  color: var(--text-dim);
  flex: 1;
}

.signal-tooltip-val {
  color: var(--text);
  min-width: 60px;
  text-align: right;
}

.signal-tooltip-shap {
  min-width: 55px;
  text-align: right;
  font-weight: 600;
}

.signal-tooltip-shap.positive { color: var(--profit); }
.signal-tooltip-shap.negative { color: var(--loss); }
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/frontend/src/index.css
git commit -m "style: add signal tooltip CSS"
```

---

### Task 7: Update Strategy.tsx with tooltip UI

**Files:**
- Modify: `src/ui/frontend/src/pages/Strategy.tsx:14-19, 160-194`

- [ ] **Step 1: Add feature label mapping and update Signal interface**

In `src/ui/frontend/src/pages/Strategy.tsx`, replace the `Signal` interface (lines 14-19) with:

```typescript
interface BasisEntry {
  feature: string;
  shap: number;
  value: number;
}

interface Signal {
  market: string;
  signal_type: string;
  confidence: number;
  created_at: string;
  basis: BasisEntry[] | null;
}

const FEATURE_LABELS: Record<string, string> = {
  return_1m: "1분 수익률",
  return_5m: "5분 수익률",
  return_15m: "15분 수익률",
  return_60m: "60분 수익률",
  high_low_ratio: "고저 비율",
  close_position: "종가 위치",
  rsi_14: "RSI(14)",
  rsi_7: "RSI(7)",
  macd: "MACD",
  macd_signal: "MACD 시그널",
  macd_hist: "MACD 히스토그램",
  bb_upper: "볼린저 상단",
  bb_lower: "볼린저 하단",
  bb_width: "볼린저 폭",
  ema_5_ratio: "EMA(5) 비율",
  ema_20_ratio: "EMA(20) 비율",
  ema_60_ratio: "EMA(60) 비율",
  volume_ratio_5m: "거래량(5분)",
  volume_ratio_20m: "거래량(20분)",
  volume_trend: "거래량 추세",
};
```

- [ ] **Step 2: Update signal table rows with tooltip**

In `src/ui/frontend/src/pages/Strategy.tsx`, replace the signal table tbody (lines 169-192):

```tsx
            <tbody>
              {signals.map((s, i) => (
                <tr key={i} className="signal-row">
                  <td>{s.created_at}</td>
                  <td style={{ color: "var(--text)", fontWeight: 600 }}>{s.market}</td>
                  <td>
                    <span className={`badge ${s.signal_type === "BUY" ? "profit" : "loss"}`}>
                      {s.signal_type}
                    </span>
                  </td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div className="progress-bar" style={{ flex: 1, maxWidth: 80 }}>
                        <div
                          className={`fill ${s.confidence >= 0.7 ? "accent" : "warn"}`}
                          style={{ width: `${s.confidence * 100}%` }}
                        />
                      </div>
                      <span>{(s.confidence * 100).toFixed(0)}%</span>
                    </div>
                  </td>
                  {s.basis && (
                    <td style={{ padding: 0, position: "relative" }}>
                      <div className="signal-tooltip">
                        <div className="signal-tooltip-title">신호 근거</div>
                        {s.basis.map((b) => (
                          <div key={b.feature} className="signal-tooltip-row">
                            <span className={`signal-tooltip-arrow ${b.shap >= 0 ? "up" : "down"}`}>
                              {b.shap >= 0 ? "\u2191" : "\u2193"}
                            </span>
                            <span className="signal-tooltip-name">
                              {FEATURE_LABELS[b.feature] ?? b.feature}
                            </span>
                            <span className="signal-tooltip-val">
                              {Math.abs(b.value) >= 1 ? b.value.toFixed(1) : b.value.toFixed(4)}
                            </span>
                            <span className={`signal-tooltip-shap ${b.shap >= 0 ? "positive" : "negative"}`}>
                              {b.shap >= 0 ? "+" : ""}{b.shap.toFixed(3)}
                            </span>
                          </div>
                        ))}
                      </div>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
```

- [ ] **Step 3: Verify frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Strategy.tsx
git commit -m "feat: add SHAP basis tooltip to active signals table"
```

---

### Task 8: Full integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run full Python test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter and type checker**

Run: `uv run ruff check src/ && uv run mypy src/`
Expected: No new errors

- [ ] **Step 3: Run frontend build**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Final commit if any fixes needed**

Only if previous steps required fixes.

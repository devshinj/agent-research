# Signal & Model Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist all ML signals to SQLite and expose them via API, plus extend model status with training metadata and signal statistics for continuous monitoring.

**Architecture:** New `SignalRepository` in the repository layer stores signals; `App._collect_and_predict()` saves every signal before publishing events; the strategy API routes query the repository for display data; frontend Strategy page renders real signal data and enriched model cards.

**Tech Stack:** Python 3.12, aiosqlite, FastAPI, React/TypeScript

---

### Task 1: DB Schema — Add `signals` Table

**Files:**
- Modify: `src/repository/database.py`
- Test: `tests/unit/test_api.py` (existing reset test)

- [ ] **Step 1: Add `signals` table to SCHEMA_SQL**

In `src/repository/database.py`, add this table definition at the end of `SCHEMA_SQL` (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS signals (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    market      TEXT NOT NULL,
    signal_type TEXT NOT NULL,
    confidence  REAL NOT NULL,
    timestamp   INTEGER NOT NULL,
    outcome     TEXT
);
```

- [ ] **Step 2: Add `DELETE FROM signals;` to `reset_trading_data()`**

In `Database.reset_trading_data()`, add `"DELETE FROM signals;"` to the executescript string, after `"DELETE FROM risk_state;"`.

- [ ] **Step 3: Update existing reset test to verify signals table is cleared**

In `tests/unit/test_api.py::test_reset_trading_data`, add a signals insert before reset and verify it's empty after:

```python
    await db.conn.execute(
        "INSERT INTO signals (market, signal_type, confidence, timestamp) "
        "VALUES ('KRW-BTC', 'BUY', 0.75, 1700000000)"
    )
    await db.conn.commit()
```

Add `"signals"` to the `for table in (...)` verification loop.

- [ ] **Step 4: Run tests to verify**

Run: `uv run pytest tests/unit/test_api.py::test_reset_trading_data -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repository/database.py tests/unit/test_api.py
git commit -m "feat: add signals table to schema and reset"
```

---

### Task 2: SignalRepository — Save and Query Signals

**Files:**
- Create: `src/repository/signal_repo.py`
- Test: `tests/unit/test_signal_repo.py`

- [ ] **Step 1: Write the test file**

Create `tests/unit/test_signal_repo.py`:

```python
import pytest

from src.repository.database import Database
from src.repository.signal_repo import SignalRepository


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def signal_repo(db):
    return SignalRepository(db)


async def test_save_and_get_recent(signal_repo):
    await signal_repo.save("KRW-BTC", "BUY", 0.75, 1700000000)
    await signal_repo.save("KRW-ETH", "HOLD", 0.55, 1700000001)
    await signal_repo.save("KRW-BTC", "SELL", 0.68, 1700000002)

    # Default: exclude HOLD
    results = await signal_repo.get_recent(limit=10)
    assert len(results) == 2
    assert results[0]["signal_type"] == "SELL"  # newest first
    assert results[1]["signal_type"] == "BUY"

    # Include HOLD
    results_all = await signal_repo.get_recent(limit=10, include_hold=True)
    assert len(results_all) == 3


async def test_get_stats_by_market(signal_repo):
    await signal_repo.save("KRW-BTC", "BUY", 0.80, 1700000000)
    await signal_repo.save("KRW-BTC", "HOLD", 0.55, 1700000001)
    await signal_repo.save("KRW-BTC", "HOLD", 0.52, 1700000002)
    await signal_repo.save("KRW-BTC", "SELL", 0.70, 1700000003)

    stats = await signal_repo.get_stats_by_market("KRW-BTC")
    assert stats["total_signals"] == 4
    assert stats["buy_count"] == 1
    assert stats["sell_count"] == 1
    assert stats["hold_count"] == 2
    assert 0.64 < stats["avg_confidence"] < 0.65  # (0.80+0.55+0.52+0.70)/4


async def test_get_stats_empty_market(signal_repo):
    stats = await signal_repo.get_stats_by_market("KRW-NONE")
    assert stats["total_signals"] == 0
    assert stats["buy_count"] == 0
    assert stats["sell_count"] == 0
    assert stats["hold_count"] == 0
    assert stats["avg_confidence"] == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_signal_repo.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement SignalRepository**

Create `src/repository/signal_repo.py`:

```python
from __future__ import annotations

from src.repository.database import Database


class SignalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(
        self, market: str, signal_type: str, confidence: float, timestamp: int,
    ) -> None:
        await self._db.conn.execute(
            "INSERT INTO signals (market, signal_type, confidence, timestamp) "
            "VALUES (?, ?, ?, ?)",
            (market, signal_type, confidence, timestamp),
        )
        await self._db.conn.commit()

    async def get_recent(
        self, limit: int = 50, include_hold: bool = False,
    ) -> list[dict[str, object]]:
        if include_hold:
            cursor = await self._db.conn.execute(
                "SELECT market, signal_type, confidence, timestamp "
                "FROM signals ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            )
        else:
            cursor = await self._db.conn.execute(
                "SELECT market, signal_type, confidence, timestamp "
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
            }
            for r in rows
        ]

    async def get_stats_by_market(self, market: str) -> dict[str, object]:
        cursor = await self._db.conn.execute(
            "SELECT "
            "  COUNT(*) AS total, "
            "  SUM(CASE WHEN signal_type = 'BUY' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN signal_type = 'SELL' THEN 1 ELSE 0 END), "
            "  SUM(CASE WHEN signal_type = 'HOLD' THEN 1 ELSE 0 END), "
            "  AVG(confidence) "
            "FROM signals WHERE market = ?",
            (market,),
        )
        row = await cursor.fetchone()
        if row is None or row[0] == 0:
            return {
                "total_signals": 0,
                "buy_count": 0,
                "sell_count": 0,
                "hold_count": 0,
                "avg_confidence": 0.0,
            }
        return {
            "total_signals": row[0],
            "buy_count": row[1],
            "sell_count": row[2],
            "hold_count": row[3],
            "avg_confidence": round(row[4], 4),
        }
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_signal_repo.py -v`
Expected: all 3 tests PASS

- [ ] **Step 5: Run linter and type checker**

Run: `uv run ruff check src/repository/signal_repo.py && uv run mypy src/repository/signal_repo.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/repository/signal_repo.py tests/unit/test_signal_repo.py
git commit -m "feat: add SignalRepository for persisting ML signals"
```

---

### Task 3: App Integration — Save Signals in Prediction Cycle

**Files:**
- Modify: `src/runtime/app.py`
- Test: `tests/integration/test_signal_to_trade.py` (verify existing integration still works)

- [ ] **Step 1: Add SignalRepository to App**

In `src/runtime/app.py`, add import:

```python
from src.repository.signal_repo import SignalRepository
```

In `App.__init__()`, after `self.portfolio_repo = PortfolioRepository(self.db)`, add:

```python
self.signal_repo = SignalRepository(self.db)
```

- [ ] **Step 2: Save signal in `_collect_and_predict()`**

In `App._collect_and_predict()`, replace the `try` block:

```python
            try:
                signal = self.predictor.predict(market, df)
                await self.signal_repo.save(
                    signal.market, signal.signal_type.name,
                    signal.confidence, signal.timestamp,
                )
                await self.event_bus.publish(SignalEvent(
                    signal.market, signal.signal_type, signal.confidence, signal.timestamp,
                ))
            except KeyError:
                pass  # model not loaded
```

- [ ] **Step 3: Run existing integration tests**

Run: `uv run pytest tests/integration/ -v`
Expected: PASS (no behavioral change to event flow)

- [ ] **Step 4: Run full test suite**

Run: `uv run pytest -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/runtime/app.py
git commit -m "feat: persist signals to DB in prediction cycle"
```

---

### Task 4: Strategy API — Signals Endpoint

**Files:**
- Modify: `src/ui/api/routes/strategy.py`
- Test: `tests/unit/test_api.py`

- [ ] **Step 1: Write the test**

Add to `tests/unit/test_api.py`:

```python
async def test_strategy_signals(client):
    resp = await client.get("/api/strategy/signals")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_strategy_signals_with_params(client):
    resp = await client.get("/api/strategy/signals?limit=10&include_hold=true")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api.py::test_strategy_signals -v`
Expected: PASS (endpoint exists but returns []) — actually this passes already. The real change is data. Let's verify the new params don't break.

Run: `uv run pytest tests/unit/test_api.py::test_strategy_signals_with_params -v`
Expected: FAIL (query params not handled yet)

- [ ] **Step 3: Implement signals endpoint**

Replace the `get_signals` function in `src/ui/api/routes/strategy.py`:

```python
from datetime import datetime, timezone


@router.get("/signals")
async def get_signals(
    request: Request, limit: int = 50, include_hold: bool = False,
) -> list:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return []

    rows = await app.signal_repo.get_recent(limit=limit, include_hold=include_hold)
    return [
        {
            "market": r["market"],
            "signal_type": r["signal_type"],
            "confidence": r["confidence"],
            "created_at": datetime.fromtimestamp(
                r["timestamp"], tz=timezone.utc,
            ).strftime("%Y-%m-%d %H:%M:%S"),
        }
        for r in rows
    ]
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add src/ui/api/routes/strategy.py tests/unit/test_api.py
git commit -m "feat: signals endpoint returns persisted signal data"
```

---

### Task 5: Strategy API — Extended Model Status

**Files:**
- Modify: `src/ui/api/routes/strategy.py`
- Test: `tests/unit/test_api.py`

- [ ] **Step 1: Write the test**

Add to `tests/unit/test_api.py`:

```python
async def test_strategy_model_status(client):
    resp = await client.get("/api/strategy/model-status")
    assert resp.status_code == 200
    data = resp.json()
    assert "models" in data
    assert "last_retrain" in data
    assert "next_retrain_hours" in data
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api.py::test_strategy_model_status -v`
Expected: FAIL (no `next_retrain_hours` key)

- [ ] **Step 3: Implement extended model status**

Replace the `get_model_status` function in `src/ui/api/routes/strategy.py`:

```python
import time


@router.get("/model-status")
async def get_model_status(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is None:
        return {"models": {}, "last_retrain": None, "next_retrain_hours": None}

    models = {}
    last_retrain: str | None = None
    last_retrain_epoch: int = 0

    for market in app.predictor._models:
        meta = app.predictor.get_model_meta(market)
        accuracy = meta.get("accuracy", 0)
        n_train = meta.get("n_train", 0)
        n_val = meta.get("n_val", 0)
        timestamp = meta.get("timestamp", "")

        last_train = ""
        if timestamp:
            last_train = (
                f"{timestamp[:4]}-{timestamp[4:6]}-{timestamp[6:8]}"
                f" {timestamp[9:11]}:{timestamp[11:13]}"
            )
            if last_retrain is None or timestamp > (last_retrain or ""):
                last_retrain = timestamp

        # Signal stats from DB
        stats = await app.signal_repo.get_stats_by_market(market)

        models[market] = {
            "accuracy": accuracy,
            "last_train": last_train,
            "n_train": n_train,
            "n_val": n_val,
            "total_signals": stats["total_signals"],
            "buy_count": stats["buy_count"],
            "sell_count": stats["sell_count"],
            "hold_count": stats["hold_count"],
            "avg_confidence": stats["avg_confidence"],
        }

    formatted_retrain: str | None = None
    if last_retrain:
        formatted_retrain = (
            f"{last_retrain[:4]}-{last_retrain[4:6]}-{last_retrain[6:8]}"
            f" {last_retrain[9:11]}:{last_retrain[11:13]}"
        )
        # Parse timestamp to epoch for next_retrain calculation
        try:
            from datetime import datetime, timezone

            dt = datetime(
                int(last_retrain[:4]), int(last_retrain[4:6]),
                int(last_retrain[6:8]), int(last_retrain[9:11]),
                int(last_retrain[11:13]), tzinfo=timezone.utc,
            )
            last_retrain_epoch = int(dt.timestamp())
        except (ValueError, IndexError):
            last_retrain_epoch = 0

    # Calculate next retrain
    next_retrain_hours: float | None = None
    if last_retrain_epoch > 0:
        retrain_interval_s = app.settings.strategy.retrain_interval_hours * 3600
        next_retrain_epoch = last_retrain_epoch + retrain_interval_s
        remaining_s = next_retrain_epoch - int(time.time())
        next_retrain_hours = round(max(0, remaining_s / 3600), 1)

    return {
        "models": models,
        "last_retrain": formatted_retrain,
        "next_retrain_hours": next_retrain_hours,
    }
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: all PASS

- [ ] **Step 5: Run linter and type checker on changed files**

Run: `uv run ruff check src/ui/api/routes/strategy.py && uv run mypy src/ui/api/routes/strategy.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/ui/api/routes/strategy.py tests/unit/test_api.py
git commit -m "feat: extend model-status API with signal stats and retrain countdown"
```

---

### Task 6: Frontend — Live Signals Table

**Files:**
- Modify: `src/ui/frontend/src/pages/Strategy.tsx`

- [ ] **Step 1: Update Signal interface**

Remove `predicted_pct` from the `Signal` interface since raw signals don't carry prediction percentages:

```typescript
interface Signal {
  market: string;
  signal_type: string;
  confidence: number;
  created_at: string;
}
```

- [ ] **Step 2: Update signals table columns**

Replace the signals table `<thead>` and `<tbody>` to remove the 예측 column:

```tsx
          <table className="data-table">
            <thead>
              <tr>
                <th>시간</th>
                <th>코인</th>
                <th>신호</th>
                <th>신뢰도</th>
              </tr>
            </thead>
            <tbody>
              {signals.map((s, i) => (
                <tr key={i}>
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
                </tr>
              ))}
            </tbody>
          </table>
```

- [ ] **Step 3: Verify by building the frontend**

Run: `cd src/ui/frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Strategy.tsx
git commit -m "feat: update signals table to use persisted signal data"
```

---

### Task 7: Frontend — Enhanced Model Status Cards

**Files:**
- Modify: `src/ui/frontend/src/pages/Strategy.tsx`

- [ ] **Step 1: Update ModelStatus interface**

Replace the existing interfaces:

```typescript
interface ModelInfo {
  accuracy: number;
  last_train: string;
  n_train: number;
  n_val: number;
  total_signals: number;
  buy_count: number;
  sell_count: number;
  hold_count: number;
  avg_confidence: number;
}

interface ModelStatus {
  models: Record<string, ModelInfo>;
  last_retrain: string | null;
  next_retrain_hours: number | null;
}
```

- [ ] **Step 2: Add next retrain badge to panel header**

Update the model status panel header to show next retrain countdown:

```tsx
        <div className="panel-header">
          <h3>모델 상태</h3>
          <div style={{ display: "flex", gap: 8 }}>
            {modelStatus?.next_retrain_hours != null && (
              <span className="badge info">
                다음 학습: {modelStatus.next_retrain_hours}h
              </span>
            )}
            {modelStatus?.last_retrain && (
              <span className="badge neutral">
                최근 학습: {modelStatus.last_retrain}
              </span>
            )}
          </div>
        </div>
```

- [ ] **Step 3: Enhance model cards with signal stats**

Replace the model card rendering (`modelEntries.map(...)` block) with:

```tsx
              {modelEntries.map(([name, info]) => {
                const total = info.total_signals || 0;
                const buyPct = total > 0 ? (info.buy_count / total) * 100 : 0;
                const sellPct = total > 0 ? (info.sell_count / total) * 100 : 0;
                const holdPct = total > 0 ? (info.hold_count / total) * 100 : 0;

                return (
                  <div key={name} className="card">
                    <div className="label">{name}</div>
                    <div className="value" style={{ fontSize: 20 }}>
                      {(info.accuracy * 100).toFixed(1)}%
                    </div>

                    {/* Training metadata */}
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 8, fontFamily: "var(--font-mono)" }}>
                      학습일: {info.last_train}
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 2, fontFamily: "var(--font-mono)" }}>
                      학습: {info.n_train.toLocaleString()} / 검증: {info.n_val.toLocaleString()}
                    </div>

                    {/* Signal distribution bar */}
                    {total > 0 && (
                      <div style={{ marginTop: 12 }}>
                        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 4 }}>
                          신호 분포 ({total}건)
                        </div>
                        <div style={{
                          display: "flex", height: 8, borderRadius: 4, overflow: "hidden",
                          background: "var(--bg-tertiary)",
                        }}>
                          {buyPct > 0 && (
                            <div style={{ width: `${buyPct}%`, background: "var(--profit)" }} />
                          )}
                          {holdPct > 0 && (
                            <div style={{ width: `${holdPct}%`, background: "var(--text-muted)" }} />
                          )}
                          {sellPct > 0 && (
                            <div style={{ width: `${sellPct}%`, background: "var(--loss)" }} />
                          )}
                        </div>
                        <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11, color: "var(--text-muted)", marginTop: 2 }}>
                          <span style={{ color: "var(--profit)" }}>BUY {info.buy_count}</span>
                          <span>HOLD {info.hold_count}</span>
                          <span style={{ color: "var(--loss)" }}>SELL {info.sell_count}</span>
                        </div>
                      </div>
                    )}

                    {/* Avg confidence */}
                    {total > 0 && (
                      <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 8, fontFamily: "var(--font-mono)" }}>
                        평균 신뢰도: {(info.avg_confidence * 100).toFixed(1)}%
                      </div>
                    )}
                  </div>
                );
              })}
```

- [ ] **Step 4: Verify by building the frontend**

Run: `cd src/ui/frontend && npm run build`
Expected: build succeeds with no TypeScript errors

- [ ] **Step 5: Commit**

```bash
git add src/ui/frontend/src/pages/Strategy.tsx
git commit -m "feat: enhanced model status cards with signal stats and retrain countdown"
```

---

### Task 8: Final Verification

**Files:** none (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests PASS

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/`
Expected: no errors

- [ ] **Step 3: Run type checker**

Run: `uv run mypy src/`
Expected: no errors

- [ ] **Step 4: Run structural tests**

Run: `uv run pytest tests/structural/ -v`
Expected: PASS (layer dependency check passes — SignalRepository only depends on Database)

- [ ] **Step 5: Build frontend**

Run: `cd src/ui/frontend && npm run build`
Expected: build succeeds

- [ ] **Step 6: Commit any remaining fixes if needed**

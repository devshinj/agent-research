# Signal & Model Monitoring Design

## Problem

ML predictor generates signals every 60 seconds, but they are ephemeral — never stored, never displayed. The `/api/strategy/signals` endpoint returns an empty list. Model status shows only accuracy and training date, missing training metadata and real-world signal statistics.

## Goal

Persist all signals (BUY/SELL/HOLD) to SQLite for continuous monitoring. Extend model status API with training metadata and signal-derived statistics. Update the frontend to display real data.

## Approach

**SignalRepository** — new repository following existing OrderRepository pattern, persisting signals to a new `signals` table and providing aggregation queries for the model status API.

---

## 1. DB Schema

Add `signals` table to `SCHEMA_SQL` in `src/repository/database.py`:

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

- Every prediction cycle (60s) writes one row per screened market
- `signal_type`: "BUY" / "HOLD" / "SELL" (stored as string, matching `SignalType.name`)
- `outcome`: reserved for future post-hoc accuracy verification (NULL for now)

Add `DELETE FROM signals;` to `Database.reset_trading_data()` so that reset clears signal history alongside orders.

## 2. SignalRepository

New file: `src/repository/signal_repo.py`

```python
class SignalRepository:
    def __init__(self, db: Database) -> None:
        self._db = db

    async def save(self, market: str, signal_type: str, confidence: float, timestamp: int) -> None:
        """Insert a signal record."""

    async def get_recent(self, limit: int = 50, include_hold: bool = False) -> list[dict]:
        """Return most recent signals, newest first.
        Default excludes HOLD signals for UI display."""

    async def get_stats_by_market(self, market: str) -> dict:
        """Aggregate stats: total_signals, buy_count, sell_count, hold_count, avg_confidence."""
```

## 3. App Integration

In `App.__init__()`:
- Create `self.signal_repo = SignalRepository(self.db)`

In `App._collect_and_predict()`, save signal before publishing event:
```python
signal = self.predictor.predict(market, df)
await self.signal_repo.save(
    signal.market, signal.signal_type.name, signal.confidence, signal.timestamp,
)
await self.event_bus.publish(SignalEvent(...))
```

In `App.reset()`:
- No extra work needed — `Database.reset_trading_data()` already handles it once we add `DELETE FROM signals`.

## 4. API Changes

### `GET /api/strategy/signals`

Query params:
- `limit` (int, default 50): max results
- `include_hold` (bool, default false): include HOLD signals

Response (list):
```json
[
  {
    "market": "KRW-BTC",
    "signal_type": "BUY",
    "confidence": 0.73,
    "created_at": "2026-04-06 14:30:00"
  }
]
```

### `GET /api/strategy/model-status`

Response (extended):
```json
{
  "models": {
    "KRW-BTC": {
      "accuracy": 0.582,
      "last_train": "2026-04-06 12:30",
      "n_train": 1600,
      "n_val": 400,
      "total_signals": 142,
      "buy_count": 28,
      "sell_count": 19,
      "hold_count": 95,
      "avg_confidence": 0.64
    }
  },
  "last_retrain": "2026-04-06 12:30",
  "next_retrain_hours": 4.2
}
```

New fields per model:
- `n_train`, `n_val`: from model metadata JSON (already stored)
- `total_signals`, `buy_count`, `sell_count`, `hold_count`, `avg_confidence`: aggregated from signals table via `SignalRepository.get_stats_by_market()`

New top-level field:
- `next_retrain_hours`: computed from scheduler's retrain interval and `last_retrain` timestamp

## 5. Frontend Changes

### Strategy.tsx — Signals Table

No structural changes needed. The existing table columns (시간, 코인, 신호, 신뢰도, 예측) already match the API response shape. The `predicted_pct` field is not available from the signal alone, so replace it with the raw confidence display or remove the column.

Updated `Signal` interface:
```typescript
interface Signal {
  market: string;
  signal_type: string;   // "BUY" | "SELL"
  confidence: number;
  created_at: string;
}
```

Remove `predicted_pct` column, keep: 시간, 코인, 신호, 신뢰도.

### Strategy.tsx — Model Status Cards

Extend `ModelStatus` interface:
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

Each model card shows:
- Accuracy (existing)
- Training date (existing)
- Training / validation sample counts
- Signal distribution as a stacked bar (BUY green / HOLD gray / SELL red)
- Average confidence
- Next retrain countdown (top-level, shown in panel header badge)

## 6. Layer Architecture Compliance

```
types      — no changes (Signal dataclass already exists)
config     — no changes
repository — new SignalRepository (depends on Database only) ✓
service    — no changes (Predictor already returns Signal)
runtime    — App gains signal_repo, saves signals in _collect_and_predict ✓
ui         — API routes query signal_repo, frontend displays data ✓
```

## 7. Reset Behavior

`Database.reset_trading_data()` gains `DELETE FROM signals;` so that trading reset clears signal history along with orders, positions, and account state. This is consistent with the existing reset scope.

## 8. Future Extensions

- **Outcome verification**: A scheduled task compares signal timestamp + market price at `lookahead_minutes` to determine if the signal was correct. Updates `outcome` column to "WIN" / "LOSS".
- **Real hit rate**: Once outcomes are populated, `model-status` API can return actual hit rate alongside training accuracy.
- **Signal alerts**: WebSocket push for BUY/SELL signals to the frontend for real-time notifications.

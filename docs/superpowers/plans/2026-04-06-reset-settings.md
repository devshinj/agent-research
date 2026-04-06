# Reset & Settings Adjustment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to reset trading data (balance, orders, positions) and adjust all config values from the Settings UI, then restart the system with new settings.

**Architecture:** Single `POST /api/control/reset` endpoint receives new config, truncates trading tables, writes `config/settings.yaml`, reinitializes in-memory state. `GET /api/config` serves current YAML for form population. Frontend toggles between read-only and edit mode with confirmation modal.

**Tech Stack:** Python/FastAPI, aiosqlite, PyYAML, React/TypeScript

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/repository/database.py` | Add `reset_trading_data()` method |
| Modify | `src/runtime/app.py` | Add `reset()` method |
| Modify | `src/ui/api/routes/control.py` | Add `GET /config` and `POST /reset` endpoints |
| Modify | `src/ui/frontend/src/hooks/useApi.ts` | Add `postJson()` for sending JSON body |
| Modify | `src/ui/frontend/src/pages/Settings.tsx` | Edit mode, form, confirmation modal |
| Modify | `tests/unit/test_api.py` | Tests for new endpoints |

---

### Task 1: Database — `reset_trading_data()`

**Files:**
- Modify: `src/repository/database.py:82-102`
- Test: `tests/unit/test_api.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_api.py`:

```python
from src.repository.database import Database

async def test_reset_trading_data():
    db = Database(":memory:")
    await db.initialize()

    # Insert dummy data into each trading table
    await db.conn.execute(
        "INSERT INTO account_state (id, cash_balance, updated_at) VALUES (1, '5000000', 100)"
    )
    await db.conn.execute(
        "INSERT INTO orders (id, market, side, order_type, price, quantity, fee, status, created_at) "
        "VALUES ('o1', 'KRW-BTC', 'BUY', 'MARKET', '1000', '1', '0.5', 'FILLED', 100)"
    )
    await db.conn.execute(
        "INSERT INTO positions (market, side, entry_price, quantity, entry_time, unrealized_pnl, highest_price) "
        "VALUES ('KRW-BTC', 'BUY', '1000', '1', 100, '0', '1000')"
    )
    await db.conn.execute(
        "INSERT INTO daily_summary (date, starting_balance, ending_balance, realized_pnl, total_trades, win_trades, loss_trades, max_drawdown_pct) "
        "VALUES ('2026-04-06', '10000000', '10500000', '500000', 5, 3, 2, '0.02')"
    )
    await db.conn.execute(
        "INSERT INTO risk_state (id, consecutive_losses, cooldown_until, daily_loss, daily_trades, current_day, updated_at) "
        "VALUES (1, 3, 0, '100000', 5, '2026-04-06', 100)"
    )
    await db.conn.commit()

    # Reset
    await db.reset_trading_data()

    # Verify all trading tables are empty
    for table in ("orders", "positions", "account_state", "daily_summary", "risk_state"):
        cursor = await db.conn.execute(f"SELECT COUNT(*) FROM {table}")  # noqa: S608
        row = await cursor.fetchone()
        assert row[0] == 0, f"{table} should be empty after reset"

    # Verify candles table still exists and is untouched
    cursor = await db.conn.execute("SELECT COUNT(*) FROM candles")
    row = await cursor.fetchone()
    assert row[0] == 0  # was empty, still exists

    await db.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api.py::test_reset_trading_data -v`
Expected: FAIL with `AttributeError: 'Database' object has no attribute 'reset_trading_data'`

- [ ] **Step 3: Implement `reset_trading_data`**

Add this method to the `Database` class in `src/repository/database.py`, after the `conn` property:

```python
async def reset_trading_data(self) -> None:
    """Delete all trading data. Preserves candles and screening_log."""
    await self.conn.executescript(
        "DELETE FROM orders;"
        "DELETE FROM positions;"
        "DELETE FROM account_state;"
        "DELETE FROM daily_summary;"
        "DELETE FROM risk_state;"
    )
    await self.conn.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api.py::test_reset_trading_data -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/repository/database.py tests/unit/test_api.py
git commit -m "feat: add Database.reset_trading_data() method"
```

---

### Task 2: App — `reset()` method and YAML write

**Files:**
- Modify: `src/runtime/app.py:30-69` (App.__init__ and new reset method)
- Modify: `src/config/settings.py` (add `to_yaml` staticmethod)

- [ ] **Step 1: Add `to_yaml` to Settings**

Add this method at the end of the `Settings` class in `src/config/settings.py`:

```python
def to_yaml(self, path: Path) -> None:
    data = {
        "paper_trading": {
            "initial_balance": int(self.paper_trading.initial_balance),
            "max_position_pct": float(self.paper_trading.max_position_pct),
            "max_open_positions": self.paper_trading.max_open_positions,
            "fee_rate": float(self.paper_trading.fee_rate),
            "slippage_rate": float(self.paper_trading.slippage_rate),
            "min_order_krw": self.paper_trading.min_order_krw,
        },
        "risk": {
            "stop_loss_pct": float(self.risk.stop_loss_pct),
            "take_profit_pct": float(self.risk.take_profit_pct),
            "trailing_stop_pct": float(self.risk.trailing_stop_pct),
            "max_daily_loss_pct": float(self.risk.max_daily_loss_pct),
            "max_daily_trades": self.risk.max_daily_trades,
            "consecutive_loss_limit": self.risk.consecutive_loss_limit,
            "cooldown_minutes": self.risk.cooldown_minutes,
        },
        "screening": {
            "min_volume_krw": int(self.screening.min_volume_krw),
            "min_volatility_pct": float(self.screening.min_volatility_pct),
            "max_volatility_pct": float(self.screening.max_volatility_pct),
            "max_coins": self.screening.max_coins,
            "refresh_interval_min": self.screening.refresh_interval_min,
            "always_include": list(self.screening.always_include),
        },
        "strategy": {
            "lookahead_minutes": self.strategy.lookahead_minutes,
            "threshold_pct": float(self.strategy.threshold_pct),
            "retrain_interval_hours": self.strategy.retrain_interval_hours,
            "min_confidence": float(self.strategy.min_confidence),
        },
        "collector": {
            "candle_timeframe": self.collector.candle_timeframe,
            "max_candles_per_market": self.collector.max_candles_per_market,
            "market_refresh_interval_min": self.collector.market_refresh_interval_min,
        },
        "data": {
            "db_path": self.data.db_path,
            "model_dir": self.data.model_dir,
            "stale_candle_days": self.data.stale_candle_days,
            "stale_model_days": self.data.stale_model_days,
            "stale_order_days": self.data.stale_order_days,
        },
    }
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

- [ ] **Step 2: Add `to_dict` to Settings**

Add this method to the `Settings` class, right before `to_yaml`:

```python
def to_dict(self) -> dict:
    """Return settings as a plain dict (for JSON API responses)."""
    return {
        "paper_trading": {
            "initial_balance": int(self.paper_trading.initial_balance),
            "max_position_pct": float(self.paper_trading.max_position_pct),
            "max_open_positions": self.paper_trading.max_open_positions,
            "fee_rate": float(self.paper_trading.fee_rate),
            "slippage_rate": float(self.paper_trading.slippage_rate),
            "min_order_krw": self.paper_trading.min_order_krw,
        },
        "risk": {
            "stop_loss_pct": float(self.risk.stop_loss_pct),
            "take_profit_pct": float(self.risk.take_profit_pct),
            "trailing_stop_pct": float(self.risk.trailing_stop_pct),
            "max_daily_loss_pct": float(self.risk.max_daily_loss_pct),
            "max_daily_trades": self.risk.max_daily_trades,
            "consecutive_loss_limit": self.risk.consecutive_loss_limit,
            "cooldown_minutes": self.risk.cooldown_minutes,
        },
        "screening": {
            "min_volume_krw": int(self.screening.min_volume_krw),
            "min_volatility_pct": float(self.screening.min_volatility_pct),
            "max_volatility_pct": float(self.screening.max_volatility_pct),
            "max_coins": self.screening.max_coins,
            "refresh_interval_min": self.screening.refresh_interval_min,
            "always_include": list(self.screening.always_include),
        },
        "strategy": {
            "lookahead_minutes": self.strategy.lookahead_minutes,
            "threshold_pct": float(self.strategy.threshold_pct),
            "retrain_interval_hours": self.strategy.retrain_interval_hours,
            "min_confidence": float(self.strategy.min_confidence),
        },
        "collector": {
            "candle_timeframe": self.collector.candle_timeframe,
            "max_candles_per_market": self.collector.max_candles_per_market,
            "market_refresh_interval_min": self.collector.market_refresh_interval_min,
        },
        "data": {
            "db_path": self.data.db_path,
            "model_dir": self.data.model_dir,
            "stale_candle_days": self.data.stale_candle_days,
            "stale_model_days": self.data.stale_model_days,
            "stale_order_days": self.data.stale_order_days,
        },
    }
```

- [ ] **Step 3: Add `from_dict` to Settings**

Add this staticmethod to the `Settings` class, right after `from_yaml`:

```python
@staticmethod
def from_dict(raw: dict) -> Settings:
    return Settings(
        paper_trading=PaperTradingConfig(
            initial_balance=Decimal(str(raw["paper_trading"]["initial_balance"])),
            max_position_pct=Decimal(str(raw["paper_trading"]["max_position_pct"])),
            max_open_positions=int(raw["paper_trading"]["max_open_positions"]),
            fee_rate=Decimal(str(raw["paper_trading"]["fee_rate"])),
            slippage_rate=Decimal(str(raw["paper_trading"]["slippage_rate"])),
            min_order_krw=int(raw["paper_trading"]["min_order_krw"]),
        ),
        risk=RiskConfig(
            stop_loss_pct=Decimal(str(raw["risk"]["stop_loss_pct"])),
            take_profit_pct=Decimal(str(raw["risk"]["take_profit_pct"])),
            trailing_stop_pct=Decimal(str(raw["risk"]["trailing_stop_pct"])),
            max_daily_loss_pct=Decimal(str(raw["risk"]["max_daily_loss_pct"])),
            max_daily_trades=int(raw["risk"]["max_daily_trades"]),
            consecutive_loss_limit=int(raw["risk"]["consecutive_loss_limit"]),
            cooldown_minutes=int(raw["risk"]["cooldown_minutes"]),
        ),
        screening=ScreeningConfig(
            min_volume_krw=Decimal(str(raw["screening"]["min_volume_krw"])),
            min_volatility_pct=Decimal(str(raw["screening"]["min_volatility_pct"])),
            max_volatility_pct=Decimal(str(raw["screening"]["max_volatility_pct"])),
            max_coins=int(raw["screening"]["max_coins"]),
            refresh_interval_min=int(raw["screening"]["refresh_interval_min"]),
            always_include=tuple(raw["screening"].get("always_include", [])),
        ),
        strategy=StrategyConfig(
            lookahead_minutes=int(raw["strategy"]["lookahead_minutes"]),
            threshold_pct=Decimal(str(raw["strategy"]["threshold_pct"])),
            retrain_interval_hours=int(raw["strategy"]["retrain_interval_hours"]),
            min_confidence=Decimal(str(raw["strategy"]["min_confidence"])),
        ),
        collector=CollectorConfig(
            candle_timeframe=int(raw["collector"]["candle_timeframe"]),
            max_candles_per_market=int(raw["collector"]["max_candles_per_market"]),
            market_refresh_interval_min=int(raw["collector"]["market_refresh_interval_min"]),
        ),
        data=DataConfig(
            db_path=str(raw["data"]["db_path"]),
            model_dir=str(raw["data"]["model_dir"]),
            stale_candle_days=int(raw["data"]["stale_candle_days"]),
            stale_model_days=int(raw["data"]["stale_model_days"]),
            stale_order_days=int(raw["data"]["stale_order_days"]),
        ),
    )
```

- [ ] **Step 4: Add `reset()` to App**

Add this method to the `App` class in `src/runtime/app.py`, after the `stop()` method:

```python
async def reset(self, new_settings: Settings) -> None:
    """Reset trading data and reinitialize with new settings."""
    self.paused = True
    await self.db.reset_trading_data()

    self.settings = new_settings
    self.risk_manager = RiskManager(new_settings.risk, new_settings.paper_trading)
    self.paper_engine = PaperEngine(new_settings.paper_trading)
    self.portfolio_manager = PortfolioManager(new_settings.risk)
    self.screener = Screener(new_settings.screening)
    self.predictor = Predictor(self.feature_builder, float(new_settings.strategy.min_confidence))
    self.trainer = Trainer(
        self.feature_builder,
        new_settings.data.model_dir,
        new_settings.strategy.lookahead_minutes,
        float(new_settings.strategy.threshold_pct),
    )

    self.account = PaperAccount(
        initial_balance=new_settings.paper_trading.initial_balance,
        cash_balance=new_settings.paper_trading.initial_balance,
    )
    self.paused = False
```

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/config/settings.py src/runtime/app.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/config/settings.py src/runtime/app.py
git commit -m "feat: add Settings.to_dict/from_dict/to_yaml and App.reset()"
```

---

### Task 3: API Endpoints — `GET /config` and `POST /reset`

**Files:**
- Modify: `src/ui/api/routes/control.py`
- Test: `tests/unit/test_api.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_api.py`:

```python
async def test_get_config(client):
    resp = await client.get("/api/control/config")
    assert resp.status_code == 200
    data = resp.json()
    assert "paper_trading" in data
    assert "risk" in data
    assert "screening" in data
    assert "strategy" in data
    assert "collector" in data
    assert "data" in data


async def test_reset(client):
    resp = await client.post("/api/control/reset", json={
        "paper_trading": {
            "initial_balance": 5000000,
            "max_position_pct": 0.25,
            "max_open_positions": 4,
            "fee_rate": 0.0005,
            "slippage_rate": 0.0005,
            "min_order_krw": 5000,
        },
        "risk": {
            "stop_loss_pct": 0.02,
            "take_profit_pct": 0.05,
            "trailing_stop_pct": 0.015,
            "max_daily_loss_pct": 0.05,
            "max_daily_trades": 50,
            "consecutive_loss_limit": 5,
            "cooldown_minutes": 60,
        },
        "screening": {
            "min_volume_krw": 500000000,
            "min_volatility_pct": 1.0,
            "max_volatility_pct": 15.0,
            "max_coins": 10,
            "refresh_interval_min": 30,
            "always_include": ["KRW-BTC"],
        },
        "strategy": {
            "lookahead_minutes": 5,
            "threshold_pct": 0.3,
            "retrain_interval_hours": 6,
            "min_confidence": 0.6,
        },
        "collector": {
            "candle_timeframe": 1,
            "max_candles_per_market": 200,
            "market_refresh_interval_min": 60,
        },
        "data": {
            "db_path": "data/paper_trader.db",
            "model_dir": "data/models",
            "stale_candle_days": 7,
            "stale_model_days": 30,
            "stale_order_days": 90,
        },
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api.py::test_get_config tests/unit/test_api.py::test_reset -v`
Expected: FAIL (404 — routes don't exist yet)

- [ ] **Step 3: Implement endpoints**

Replace `src/ui/api/routes/control.py` with:

```python
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request

from src.config.settings import Settings

router = APIRouter()

_CONFIG_PATH = Path("config/settings.yaml")


@router.post("/pause")
async def pause(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = True
    return {"status": "paused"}


@router.post("/resume")
async def resume(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        app.paused = False
    return {"status": "running"}


@router.get("/config")
async def get_config(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    if app is not None:
        return app.settings.to_dict()
    settings = Settings.from_yaml(_CONFIG_PATH)
    return settings.to_dict()


@router.post("/reset")
async def reset(request: Request) -> dict:
    app = getattr(request.app.state, "app", None)
    body = await request.json()
    new_settings = Settings.from_dict(body)

    # Write to YAML
    new_settings.to_yaml(_CONFIG_PATH)

    # Reset app state
    if app is not None:
        await app.reset(new_settings)

    return {"status": "running"}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: all tests PASS

- [ ] **Step 5: Run linter**

Run: `uv run ruff check src/ui/api/routes/control.py`
Expected: no errors

- [ ] **Step 6: Commit**

```bash
git add src/ui/api/routes/control.py tests/unit/test_api.py
git commit -m "feat: add GET /config and POST /reset API endpoints"
```

---

### Task 4: Frontend — `useApi` JSON support

**Files:**
- Modify: `src/ui/frontend/src/hooks/useApi.ts`

- [ ] **Step 1: Add `postJson` to useApi hook**

Edit `src/ui/frontend/src/hooks/useApi.ts` — add a `postJson` function alongside the existing `post`:

```typescript
const postJson = useCallback(async <T>(path: string, body: unknown): Promise<T> => {
  const resp = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return resp.json();
}, []);
```

Update the return to include it:

```typescript
return { get, post, postJson };
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/frontend/src/hooks/useApi.ts
git commit -m "feat: add postJson to useApi hook"
```

---

### Task 5: Frontend — Settings.tsx edit mode, form, and confirmation modal

**Files:**
- Modify: `src/ui/frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Rewrite Settings.tsx**

Replace the entire contents of `src/ui/frontend/src/pages/Settings.tsx` with the code below. Key changes:
- Loads config from `GET /api/config` on mount
- "초기화 & 재설정" button pauses system and enters edit mode
- All settings become editable `<input>` fields
- "적용 & 시작" triggers confirmation modal
- On confirm, sends `POST /api/control/reset` with form values
- Returns to read-only mode on success

```tsx
import { useCallback, useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

type SystemStatus = "running" | "paused" | "unknown";

type ConfigValues = {
  paper_trading: {
    initial_balance: number;
    max_position_pct: number;
    max_open_positions: number;
    fee_rate: number;
    slippage_rate: number;
    min_order_krw: number;
  };
  risk: {
    stop_loss_pct: number;
    take_profit_pct: number;
    trailing_stop_pct: number;
    max_daily_loss_pct: number;
    max_daily_trades: number;
    consecutive_loss_limit: number;
    cooldown_minutes: number;
  };
  screening: {
    min_volume_krw: number;
    min_volatility_pct: number;
    max_volatility_pct: number;
    max_coins: number;
    refresh_interval_min: number;
    always_include: string[];
  };
  strategy: {
    lookahead_minutes: number;
    threshold_pct: number;
    retrain_interval_hours: number;
    min_confidence: number;
  };
  collector: {
    candle_timeframe: number;
    max_candles_per_market: number;
    market_refresh_interval_min: number;
  };
  data: {
    db_path: string;
    model_dir: string;
    stale_candle_days: number;
    stale_model_days: number;
    stale_order_days: number;
  };
};

const FIELD_META: {
  section: keyof ConfigValues;
  label: string;
  fields: { key: string; label: string; type: "number" | "text"; suffix?: string }[];
}[] = [
  {
    section: "paper_trading",
    label: "모의매매",
    fields: [
      { key: "initial_balance", label: "초기 잔고", type: "number", suffix: "KRW" },
      { key: "max_position_pct", label: "최대 포지션 비중", type: "number" },
      { key: "max_open_positions", label: "최대 동시 포지션", type: "number" },
      { key: "fee_rate", label: "수수료율", type: "number" },
      { key: "slippage_rate", label: "슬리피지율", type: "number" },
      { key: "min_order_krw", label: "최소 주문금액", type: "number", suffix: "KRW" },
    ],
  },
  {
    section: "risk",
    label: "리스크",
    fields: [
      { key: "stop_loss_pct", label: "손절 비율", type: "number" },
      { key: "take_profit_pct", label: "익절 비율", type: "number" },
      { key: "trailing_stop_pct", label: "트레일링 스탑", type: "number" },
      { key: "max_daily_loss_pct", label: "일일 최대 손실", type: "number" },
      { key: "max_daily_trades", label: "일일 최대 거래", type: "number" },
      { key: "consecutive_loss_limit", label: "연속 손실 한도", type: "number" },
      { key: "cooldown_minutes", label: "쿨다운 시간", type: "number", suffix: "분" },
    ],
  },
  {
    section: "screening",
    label: "스크리닝",
    fields: [
      { key: "min_volume_krw", label: "최소 거래량", type: "number", suffix: "KRW" },
      { key: "min_volatility_pct", label: "최소 변동성", type: "number", suffix: "%" },
      { key: "max_volatility_pct", label: "최대 변동성", type: "number", suffix: "%" },
      { key: "max_coins", label: "최대 코인 수", type: "number" },
      { key: "refresh_interval_min", label: "갱신 주기", type: "number", suffix: "분" },
      { key: "always_include", label: "항상 포함", type: "text" },
    ],
  },
  {
    section: "strategy",
    label: "전략",
    fields: [
      { key: "lookahead_minutes", label: "예측 시간", type: "number", suffix: "분" },
      { key: "threshold_pct", label: "임계값", type: "number" },
      { key: "retrain_interval_hours", label: "재학습 주기", type: "number", suffix: "시간" },
      { key: "min_confidence", label: "최소 신뢰도", type: "number" },
    ],
  },
  {
    section: "collector",
    label: "수집",
    fields: [
      { key: "candle_timeframe", label: "캔들 주기", type: "number", suffix: "분" },
      { key: "max_candles_per_market", label: "마켓당 최대 캔들", type: "number" },
      { key: "market_refresh_interval_min", label: "마켓 갱신 주기", type: "number", suffix: "분" },
    ],
  },
  {
    section: "data",
    label: "데이터",
    fields: [
      { key: "db_path", label: "DB 경로", type: "text" },
      { key: "model_dir", label: "모델 디렉토리", type: "text" },
      { key: "stale_candle_days", label: "캔들 유효기간", type: "number", suffix: "일" },
      { key: "stale_model_days", label: "모델 유효기간", type: "number", suffix: "일" },
      { key: "stale_order_days", label: "주문 유효기간", type: "number", suffix: "일" },
    ],
  },
];

function formatDisplay(section: string, key: string, value: unknown): string {
  if (key === "always_include" && Array.isArray(value)) return value.join(", ");
  if (key === "initial_balance" || key === "min_order_krw")
    return `\u20A9${Number(value).toLocaleString()}`;
  if (key === "min_volume_krw") return `\u20A9${(Number(value) / 1e6).toFixed(0)}M`;
  if (key.endsWith("_pct") && section !== "screening")
    return `${(Number(value) * 100).toFixed(2)}%`;
  if (key.endsWith("_pct") && section === "screening") return `${value}%`;
  return String(value);
}

export default function Settings() {
  const { get, post, postJson } = useApi();
  const [status, setStatus] = useState<SystemStatus>("running");
  const [loading, setLoading] = useState(false);
  const [editMode, setEditMode] = useState(false);
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [form, setForm] = useState<ConfigValues | null>(null);
  const [showConfirm, setShowConfirm] = useState(false);

  useEffect(() => {
    get<ConfigValues>("/api/control/config").then((data) => {
      setConfig(data);
      setForm(structuredClone(data));
    });
  }, [get]);

  const handlePause = async () => {
    setLoading(true);
    const res = await post<{ status: string }>("/api/control/pause");
    setStatus(res.status as SystemStatus);
    setLoading(false);
  };

  const handleResume = async () => {
    setLoading(true);
    const res = await post<{ status: string }>("/api/control/resume");
    setStatus(res.status as SystemStatus);
    setLoading(false);
  };

  const handleStartReset = async () => {
    await handlePause();
    setEditMode(true);
  };

  const handleCancelReset = async () => {
    setEditMode(false);
    setForm(config ? structuredClone(config) : null);
    await handleResume();
  };

  const handleConfirmReset = async () => {
    if (!form) return;
    setShowConfirm(false);
    setLoading(true);
    const res = await postJson<{ status: string }>("/api/control/reset", form);
    setStatus(res.status as SystemStatus);
    setConfig(structuredClone(form));
    setEditMode(false);
    setLoading(false);
  };

  const updateField = useCallback(
    (section: keyof ConfigValues, key: string, value: string) => {
      setForm((prev) => {
        if (!prev) return prev;
        const next = structuredClone(prev);
        const sec = next[section] as Record<string, unknown>;
        if (key === "always_include") {
          sec[key] = value.split(",").map((s) => s.trim()).filter(Boolean);
        } else if (key === "db_path" || key === "model_dir") {
          sec[key] = value;
        } else {
          const num = Number(value);
          if (!isNaN(num)) sec[key] = num;
        }
        return next;
      });
    },
    [],
  );

  const inputValue = (section: keyof ConfigValues, key: string): string => {
    if (!form) return "";
    const sec = form[section] as Record<string, unknown>;
    const val = sec[key];
    if (key === "always_include" && Array.isArray(val)) return val.join(", ");
    return String(val ?? "");
  };

  return (
    <div>
      <div className="page-header">
        <h2>설정</h2>
        <div className="page-sub">시스템 제어 및 구성</div>
      </div>

      {/* ── System Control ─────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>시스템 제어</h3>
          <span
            className={`badge ${status === "running" ? "profit" : status === "paused" ? "warn" : "neutral"}`}
          >
            {status.toUpperCase()}
          </span>
        </div>
        <div className="panel-body">
          <div style={{ display: "flex", alignItems: "center", gap: 20, padding: "18px 0" }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", letterSpacing: "-0.01em" }}>
                모의매매 엔진
              </div>
              <div style={{ fontSize: 14, color: "var(--text-dim)", marginTop: 6, lineHeight: 1.5 }}>
                {editMode
                  ? "시스템이 일시 정지되었습니다. 설정을 조정한 후 적용하세요."
                  : status === "running"
                    ? "엔진이 시장을 모니터링하며 모의매매를 실행 중입니다."
                    : status === "paused"
                      ? "매매가 일시 중지되었습니다. 새로운 포지션이 개시되지 않습니다."
                      : "시스템 상태를 알 수 없습니다."}
              </div>
            </div>
            <div style={{ display: "flex", gap: 12 }}>
              {!editMode && (
                <>
                  {status === "running" ? (
                    <button className="btn btn-danger" onClick={handlePause} disabled={loading}>
                      {loading ? "..." : "일시정지"}
                    </button>
                  ) : (
                    <button className="btn btn-primary" onClick={handleResume} disabled={loading}>
                      {loading ? "..." : "재개"}
                    </button>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Configuration ──────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>매매 설정</h3>
          {editMode ? (
            <span className="badge warn">편집 중</span>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <button className="btn btn-danger" onClick={handleStartReset} disabled={loading}>
                초기화 &amp; 재설정
              </button>
            </div>
          )}
        </div>
        <div className="panel-body">
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
              gap: 8,
              fontFamily: "var(--font-mono)",
              fontSize: 14,
            }}
          >
            {FIELD_META.map(({ section, label, fields }) => (
              <div key={section} style={{ padding: "14px 0" }}>
                <div
                  style={{
                    fontSize: 12.5,
                    fontWeight: 700,
                    textTransform: "uppercase",
                    letterSpacing: "0.05em",
                    color: "var(--accent)",
                    marginBottom: 14,
                    fontFamily: "var(--font-ui)",
                  }}
                >
                  {label}
                </div>
                {fields.map(({ key, label: fieldLabel, type }) => (
                  <div
                    key={key}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      alignItems: "center",
                      padding: "8px 0",
                      borderBottom: "1px solid rgba(31, 45, 64, 0.4)",
                    }}
                  >
                    <span style={{ color: "var(--text-dim)" }}>{fieldLabel}</span>
                    {editMode && form ? (
                      <input
                        type={type}
                        value={inputValue(section, key)}
                        onChange={(e) => updateField(section, key, e.target.value)}
                        style={{
                          width: 160,
                          padding: "4px 8px",
                          background: "var(--card)",
                          border: "1px solid var(--border)",
                          borderRadius: 4,
                          color: "var(--text)",
                          fontFamily: "var(--font-mono)",
                          fontSize: 13,
                          textAlign: "right",
                        }}
                      />
                    ) : (
                      <span style={{ color: "var(--text)" }}>
                        {config ? formatDisplay(section, key, (config[section] as Record<string, unknown>)[key]) : "..."}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            ))}
          </div>

          {editMode && (
            <div
              style={{
                display: "flex",
                justifyContent: "flex-end",
                gap: 12,
                marginTop: 20,
                paddingTop: 16,
                borderTop: "1px solid var(--border)",
              }}
            >
              <button className="btn" onClick={handleCancelReset} disabled={loading}>
                취소
              </button>
              <button
                className="btn btn-primary"
                onClick={() => setShowConfirm(true)}
                disabled={loading}
              >
                적용 &amp; 시작
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── About ──────────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>정보</h3>
        </div>
        <div className="panel-body">
          <div
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 14,
              color: "var(--text-dim)",
              lineHeight: 2.0,
            }}
          >
            <div>Crypto Paper Trader v0.1.0</div>
            <div>Upbit ML Strategy &mdash; LightGBM / XGBoost</div>
            <div>
              6-Layer Architecture: types &rarr; config &rarr; repository &rarr; service &rarr;
              runtime &rarr; ui
            </div>
          </div>
        </div>
      </div>

      {/* ── Confirmation Modal ─────────────── */}
      {showConfirm && (
        <div
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0, 0, 0, 0.6)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
          }}
          onClick={() => setShowConfirm(false)}
        >
          <div
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              borderRadius: 12,
              padding: 32,
              maxWidth: 420,
              width: "90%",
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 12px", color: "var(--text)" }}>초기화 확인</h3>
            <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 24px" }}>
              잔고와 거래내역이 모두 초기화됩니다.
              <br />
              학습 데이터와 모델은 유지됩니다.
              <br />
              진행하시겠습니까?
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button className="btn" onClick={() => setShowConfirm(false)}>
                취소
              </button>
              <button className="btn btn-danger" onClick={handleConfirmReset}>
                확인
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd src/ui/frontend && npm run build`
Expected: BUILD succeeds with no type errors

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Settings.tsx
git commit -m "feat: Settings page edit mode with reset and confirmation modal"
```

---

### Task 6: Integration test and lint pass

**Files:**
- All modified files

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: all tests pass

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/`
Expected: no errors

- [ ] **Step 3: Run type check**

Run: `uv run mypy src/`
Expected: no errors (or only pre-existing ones)

- [ ] **Step 4: Final commit if any fixups needed**

```bash
git add -u
git commit -m "fix: address lint/type issues from reset feature"
```

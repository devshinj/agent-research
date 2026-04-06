# Hot Reload Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow runtime config changes (risk, min_confidence, screening) without stopping the trading engine, while keeping full-reset for infrastructure-level settings.

**Architecture:** Add `PATCH /api/control/config` endpoint that validates fields against a whitelist, uses `dataclasses.replace()` to create new frozen config objects, and calls lightweight update methods on affected services. Frontend gets a second edit mode for hot-reload fields.

**Tech Stack:** Python 3.12, FastAPI, dataclasses.replace(), React/TypeScript

**Spec:** `docs/superpowers/specs/2026-04-06-hot-reload-settings-design.md`

---

### Task 1: Service update methods

**Files:**
- Modify: `src/service/risk_manager.py:12-20`
- Modify: `src/service/predictor.py:21-25`
- Modify: `src/service/screener.py:10-12`
- Test: `tests/unit/test_hot_reload.py` (create)

- [ ] **Step 1: Write failing tests for service update methods**

Create `tests/unit/test_hot_reload.py`:

```python
from __future__ import annotations

from decimal import Decimal

import pytest

from src.config.settings import PaperTradingConfig, RiskConfig, ScreeningConfig
from src.service.predictor import Predictor
from src.service.risk_manager import RiskManager
from src.service.screener import Screener


def _make_risk_config(**overrides) -> RiskConfig:
    defaults = {
        "stop_loss_pct": Decimal("0.02"),
        "take_profit_pct": Decimal("0.05"),
        "trailing_stop_pct": Decimal("0.015"),
        "max_daily_loss_pct": Decimal("0.05"),
        "max_daily_trades": 50,
        "consecutive_loss_limit": 5,
        "cooldown_minutes": 60,
    }
    defaults.update(overrides)
    return RiskConfig(**defaults)


def _make_pt_config(**overrides) -> PaperTradingConfig:
    defaults = {
        "initial_balance": Decimal("5000000"),
        "max_position_pct": Decimal("0.25"),
        "max_open_positions": 4,
        "fee_rate": Decimal("0.0005"),
        "slippage_rate": Decimal("0.0005"),
        "min_order_krw": 5000,
    }
    defaults.update(overrides)
    return PaperTradingConfig(**defaults)


def _make_screening_config(**overrides) -> ScreeningConfig:
    defaults = {
        "min_volume_krw": Decimal("500000000"),
        "min_volatility_pct": Decimal("1.0"),
        "max_volatility_pct": Decimal("15.0"),
        "max_coins": 10,
        "refresh_interval_min": 30,
        "always_include": (),
    }
    defaults.update(overrides)
    return ScreeningConfig(**defaults)


def test_risk_manager_update_config_preserves_state():
    rm = RiskManager(_make_risk_config(), _make_pt_config())
    rm._consecutive_losses = 3
    rm._daily_trades = 7
    rm._cooldown_until = 9999

    new_risk = _make_risk_config(stop_loss_pct=Decimal("0.05"))
    rm.update_config(new_risk)

    assert rm._risk.stop_loss_pct == Decimal("0.05")
    assert rm._consecutive_losses == 3
    assert rm._daily_trades == 7
    assert rm._cooldown_until == 9999


def test_predictor_update_min_confidence():
    from src.service.features import FeatureBuilder

    fb = FeatureBuilder()
    p = Predictor(fb, 0.6)
    p._models["KRW-BTC"] = "fake_model"

    p.update_min_confidence(0.8)

    assert p._min_confidence == 0.8
    assert "KRW-BTC" in p._models


def test_screener_update_config():
    s = Screener(_make_screening_config())

    new_config = _make_screening_config(max_coins=5)
    s.update_config(new_config)

    assert s._config.max_coins == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_hot_reload.py -v`
Expected: FAIL — `AttributeError: 'RiskManager' object has no attribute 'update_config'` (and similar for Predictor, Screener)

- [ ] **Step 3: Add `update_config` to RiskManager**

In `src/service/risk_manager.py`, add after `__init__`:

```python
def update_config(self, risk_config: RiskConfig) -> None:
    self._risk = risk_config
```

- [ ] **Step 4: Add `update_min_confidence` to Predictor**

In `src/service/predictor.py`, add after `__init__`:

```python
def update_min_confidence(self, value: float) -> None:
    self._min_confidence = value
```

- [ ] **Step 5: Add `update_config` to Screener**

In `src/service/screener.py`, add after `__init__`:

```python
def update_config(self, config: ScreeningConfig) -> None:
    self._config = config
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_hot_reload.py -v`
Expected: 3 passed

- [ ] **Step 7: Commit**

```bash
git add src/service/risk_manager.py src/service/predictor.py src/service/screener.py tests/unit/test_hot_reload.py
git commit -m "feat: add update methods to services for hot reload"
```

---

### Task 2: `App.hot_reload()` method

**Files:**
- Modify: `src/runtime/app.py:33-73`
- Test: `tests/unit/test_hot_reload.py` (append)

- [ ] **Step 1: Write failing tests for `App.hot_reload()`**

Append to `tests/unit/test_hot_reload.py`:

```python
import dataclasses

from src.config.settings import Settings, StrategyConfig


def _make_settings(**section_overrides) -> Settings:
    base = Settings(
        paper_trading=_make_pt_config(),
        risk=_make_risk_config(),
        screening=_make_screening_config(),
        strategy=StrategyConfig(
            lookahead_minutes=5,
            threshold_pct=Decimal("0.3"),
            retrain_interval_hours=6,
            min_confidence=Decimal("0.6"),
        ),
        collector=__import__("src.config.settings", fromlist=["CollectorConfig"]).CollectorConfig(
            candle_timeframe=1,
            max_candles_per_market=200,
            market_refresh_interval_min=60,
        ),
        data=__import__("src.config.settings", fromlist=["DataConfig"]).DataConfig(
            db_path=":memory:",
            model_dir="data/models",
            stale_candle_days=7,
            stale_model_days=30,
            stale_order_days=90,
        ),
    )
    return base


def test_hot_reload_updates_risk():
    """hot_reload with risk field updates risk_manager config."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)
    app.risk_manager._consecutive_losses = 3

    updated = app.hot_reload({"risk": {"stop_loss_pct": 0.05}})

    assert app.settings.risk.stop_loss_pct == Decimal("0.05")
    assert app.risk_manager._risk.stop_loss_pct == Decimal("0.05")
    assert app.risk_manager._consecutive_losses == 3
    assert "risk" in updated
    assert "stop_loss_pct" in updated["risk"]


def test_hot_reload_updates_min_confidence():
    """hot_reload with strategy.min_confidence updates predictor."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    app.hot_reload({"strategy": {"min_confidence": 0.8}})

    assert app.predictor._min_confidence == 0.8
    assert app.settings.strategy.min_confidence == Decimal("0.8")


def test_hot_reload_updates_screening():
    """hot_reload with screening fields updates screener config."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    app.hot_reload({"screening": {"max_coins": 5}})

    assert app.screener._config.max_coins == 5
    assert app.settings.screening.max_coins == 5


def test_hot_reload_rejects_forbidden_field():
    """hot_reload raises ValueError for non-hot-reloadable fields."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    with pytest.raises(ValueError, match="핫 리로드 불가"):
        app.hot_reload({"paper_trading": {"initial_balance": 10000000}})


def test_hot_reload_rejects_forbidden_section():
    """hot_reload raises ValueError for entirely forbidden sections."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    with pytest.raises(ValueError, match="핫 리로드 불가"):
        app.hot_reload({"collector": {"candle_timeframe": 5}})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_hot_reload.py::test_hot_reload_updates_risk -v`
Expected: FAIL — `AttributeError: 'App' object has no attribute 'hot_reload'`

- [ ] **Step 3: Implement `App.hot_reload()`**

In `src/runtime/app.py`, add two things:

1. Class-level constant after `class App:` line:

```python
HOT_RELOAD_FIELDS: dict[str, set[str]] = {
    "risk": {
        "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
        "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
    },
    "strategy": {"min_confidence"},
    "screening": {
        "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
        "max_coins", "always_include",
    },
}
```

2. Add `import dataclasses` at top of file, then add method after `reset()`:

```python
def hot_reload(self, patches: dict[str, dict[str, object]]) -> dict[str, list[str]]:
    """Apply partial config update without resetting trading state."""
    # Validate all fields are allowed
    for section, fields in patches.items():
        allowed = self.HOT_RELOAD_FIELDS.get(section)
        if allowed is None:
            bad = ", ".join(f"{section}.{k}" for k in fields)
            raise ValueError(f"핫 리로드 불가 필드: {bad} — 완전 초기화를 사용하세요")
        for key in fields:
            if key not in allowed:
                raise ValueError(
                    f"핫 리로드 불가 필드: {section}.{key} — 완전 초기화를 사용하세요"
                )

    updated: dict[str, list[str]] = {}

    # Build new config sections using dataclasses.replace()
    new_risk = self.settings.risk
    new_screening = self.settings.screening
    new_strategy = self.settings.strategy

    if "risk" in patches:
        coerced = {}
        for k, v in patches["risk"].items():
            field_type = next(
                f.type for f in dataclasses.fields(type(new_risk)) if f.name == k
            )
            coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(v)
        new_risk = dataclasses.replace(new_risk, **coerced)
        updated["risk"] = list(patches["risk"].keys())

    if "screening" in patches:
        coerced = {}
        for k, v in patches["screening"].items():
            if k == "always_include":
                coerced[k] = tuple(v) if isinstance(v, list) else v
            else:
                field_type = next(
                    f.type for f in dataclasses.fields(type(new_screening)) if f.name == k
                )
                coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(v)
        new_screening = dataclasses.replace(new_screening, **coerced)
        updated["screening"] = list(patches["screening"].keys())

    if "strategy" in patches:
        coerced = {}
        for k, v in patches["strategy"].items():
            coerced[k] = Decimal(str(v))
        new_strategy = dataclasses.replace(new_strategy, **coerced)
        updated["strategy"] = list(patches["strategy"].keys())

    # Update settings object
    self.settings = dataclasses.replace(
        self.settings,
        risk=new_risk,
        screening=new_screening,
        strategy=new_strategy,
    )

    # Push to services
    if "risk" in patches:
        self.risk_manager.update_config(new_risk)
        self.portfolio_manager._risk = new_risk
    if "strategy" in patches:
        self.predictor.update_min_confidence(float(new_strategy.min_confidence))
    if "screening" in patches:
        self.screener.update_config(new_screening)

    return updated
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_hot_reload.py -v`
Expected: 8 passed

- [ ] **Step 5: Commit**

```bash
git add src/runtime/app.py tests/unit/test_hot_reload.py
git commit -m "feat: add App.hot_reload() for runtime config updates"
```

---

### Task 3: PATCH API endpoint

**Files:**
- Modify: `src/ui/api/routes/control.py`
- Test: `tests/unit/test_api.py` (append)

- [ ] **Step 1: Write failing tests for PATCH endpoint**

Append to `tests/unit/test_api.py`:

```python
async def test_patch_config_hot_reload(client):
    resp = await client.patch("/api/control/config", json={
        "risk": {"stop_loss_pct": 0.03},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "updated"
    assert "risk" in data["updated_fields"]
    assert "stop_loss_pct" in data["updated_fields"]["risk"]
    assert data["config"]["risk"]["stop_loss_pct"] == 0.03


async def test_patch_config_rejects_forbidden(client):
    resp = await client.patch("/api/control/config", json={
        "paper_trading": {"initial_balance": 10000000},
    })
    assert resp.status_code == 400
    assert "핫 리로드 불가" in resp.json()["detail"]


async def test_patch_config_multiple_sections(client):
    resp = await client.patch("/api/control/config", json={
        "risk": {"take_profit_pct": 0.08},
        "screening": {"max_coins": 5},
    })
    assert resp.status_code == 200
    data = resp.json()
    assert "risk" in data["updated_fields"]
    assert "screening" in data["updated_fields"]
    assert data["config"]["risk"]["take_profit_pct"] == 0.08
    assert data["config"]["screening"]["max_coins"] == 5
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api.py::test_patch_config_hot_reload -v`
Expected: FAIL — 405 Method Not Allowed (no PATCH route)

- [ ] **Step 3: Implement PATCH route**

In `src/ui/api/routes/control.py`, add after the existing `reset` function:

```python
from fastapi import HTTPException


@router.patch("/config")
async def patch_config(request: Request) -> dict[str, Any]:
    app = getattr(request.app.state, "app", None)
    if app is None:
        raise HTTPException(status_code=503, detail="App not initialized")

    body = await request.json()

    try:
        updated_fields = app.hot_reload(body)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Persist to YAML
    app.settings.to_yaml(_CONFIG_PATH)

    result: dict[str, Any] = {
        "status": "updated",
        "updated_fields": updated_fields,
        "config": app.settings.to_dict(),
    }
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_api.py -v`
Expected: All tests pass (existing + 3 new)

- [ ] **Step 5: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 6: Commit**

```bash
git add src/ui/api/routes/control.py tests/unit/test_api.py
git commit -m "feat: add PATCH /api/control/config endpoint for hot reload"
```

---

### Task 4: Frontend — hot reload edit mode

**Files:**
- Modify: `src/ui/frontend/src/pages/Settings.tsx`

- [ ] **Step 1: Add HOT_RELOAD_FIELDS constant and hotEditMode state**

At the top of `Settings.tsx`, after the `FIELD_META` array, add:

```typescript
const HOT_RELOAD_FIELDS: Record<string, Set<string>> = {
  risk: new Set([
    "stop_loss_pct", "take_profit_pct", "trailing_stop_pct",
    "max_daily_trades", "consecutive_loss_limit", "cooldown_minutes",
  ]),
  strategy: new Set(["min_confidence"]),
  screening: new Set([
    "min_volume_krw", "min_volatility_pct", "max_volatility_pct",
    "max_coins", "always_include",
  ]),
};

function isHotReloadable(section: string, key: string): boolean {
  return HOT_RELOAD_FIELDS[section]?.has(key) ?? false;
}
```

Inside the `Settings` component, add state after existing state declarations:

```typescript
const [hotEditMode, setHotEditMode] = useState(false);
```

- [ ] **Step 2: Add patchJson to useApi hook**

Read `src/ui/frontend/src/hooks/useApi.ts` to check existing methods. Add a `patchJson` method if not present. In the `useApi` hook return, add:

```typescript
const patchJson = useCallback(async <T>(url: string, body: unknown): Promise<T> => {
  const res = await fetch(`${BASE_URL}${url}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${url} failed: ${res.status}`);
  return res.json();
}, []);
```

Return it alongside existing methods: `return { get, post, postJson, patchJson }`.

- [ ] **Step 3: Add hot-reload handlers**

In the `Settings` component, add these handlers:

```typescript
const handleStartHotEdit = () => {
  setHotEditMode(true);
  setForm(config ? structuredClone(config) : null);
};

const handleCancelHotEdit = () => {
  setHotEditMode(false);
  setForm(config ? structuredClone(config) : null);
};

const handleApplyHotReload = async () => {
  if (!form || !config) return;
  setLoading(true);

  // Build patch with only changed hot-reloadable fields
  const patch: Record<string, Record<string, unknown>> = {};
  for (const { section, fields } of FIELD_META) {
    for (const { key } of fields) {
      if (!isHotReloadable(section, key)) continue;
      const oldVal = (config[section] as Record<string, unknown>)[key];
      const newVal = (form[section] as Record<string, unknown>)[key];
      if (JSON.stringify(oldVal) !== JSON.stringify(newVal)) {
        if (!patch[section]) patch[section] = {};
        patch[section][key] = newVal;
      }
    }
  }

  if (Object.keys(patch).length === 0) {
    setHotEditMode(false);
    setLoading(false);
    return;
  }

  const res = await patchJson<{ status: string; config: ConfigValues }>("/api/control/config", patch);
  setConfig(res.config);
  setForm(structuredClone(res.config));
  setHotEditMode(false);
  setLoading(false);
};
```

- [ ] **Step 4: Update the UI buttons area**

Replace the existing button area inside the `매매 설정` panel header (around line 273-280) with:

```tsx
{editMode ? (
  <span className="badge warn">초기화 편집 중</span>
) : hotEditMode ? (
  <span className="badge" style={{ background: "var(--accent)", color: "#fff" }}>설정 변경 중</span>
) : (
  <div style={{ display: "flex", gap: 8 }}>
    <button className="btn btn-primary" onClick={handleStartHotEdit} disabled={loading}>
      설정 변경
    </button>
    <button className="btn btn-danger" onClick={handleStartReset} disabled={loading}>
      초기화 &amp; 재설정
    </button>
  </div>
)}
```

- [ ] **Step 5: Update the field rendering to support hot-edit mode**

Replace the input/display conditional (around line 320-340) with:

```tsx
{(editMode || hotEditMode) && form ? (
  <input
    type={type}
    value={inputValue(section, key)}
    onChange={(e) => updateField(section, key, e.target.value)}
    disabled={hotEditMode && !isHotReloadable(section, key)}
    style={{
      width: 160,
      padding: "4px 8px",
      background: hotEditMode && !isHotReloadable(section, key)
        ? "var(--bg)" : "var(--card)",
      border: "1px solid var(--border)",
      borderRadius: 4,
      color: hotEditMode && !isHotReloadable(section, key)
        ? "var(--text-dim)" : "var(--text)",
      fontFamily: "var(--font-mono)",
      fontSize: 13,
      textAlign: "right",
      opacity: hotEditMode && !isHotReloadable(section, key) ? 0.5 : 1,
    }}
  />
) : (
  <span style={{ color: "var(--text)" }}>
    {config ? formatDisplay(section, key, (config[section] as Record<string, unknown>)[key]) : "..."}
  </span>
)}
```

- [ ] **Step 6: Update the bottom action buttons**

Replace the existing `{editMode && (...)}` block (around line 348-370) with:

```tsx
{(editMode || hotEditMode) && (
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
    <button
      className="btn"
      onClick={editMode ? handleCancelReset : handleCancelHotEdit}
      disabled={loading}
    >
      취소
    </button>
    {editMode ? (
      <button
        className="btn btn-primary"
        onClick={() => setShowConfirm(true)}
        disabled={loading}
      >
        적용 &amp; 시작
      </button>
    ) : (
      <button
        className="btn btn-primary"
        onClick={handleApplyHotReload}
        disabled={loading}
      >
        적용
      </button>
    )}
  </div>
)}
```

- [ ] **Step 7: Verify in browser**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds with no TypeScript errors

- [ ] **Step 8: Commit**

```bash
git add src/ui/frontend/src/pages/Settings.tsx src/ui/frontend/src/hooks/useApi.ts
git commit -m "feat: add hot-reload edit mode to Settings page"
```

---

### Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest -v`
Expected: All tests pass

- [ ] **Step 2: Run linter**

Run: `uv run ruff check src/`
Expected: No errors

- [ ] **Step 3: Run type checker**

Run: `uv run mypy src/`
Expected: No errors (or only pre-existing ones)

- [ ] **Step 4: Run structural tests**

Run: `uv run pytest tests/structural/ -v`
Expected: All pass (layer dependency + decimal enforcement)

- [ ] **Step 5: Commit any fixes if needed**

If any lint/type issues, fix and commit:
```bash
git add -u
git commit -m "fix: resolve lint/type issues from hot-reload feature"
```

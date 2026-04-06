# Risk Slider UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded risk rules in Risk.tsx with interactive sliders that adjust trading frequency/volume parameters via hot-reload, and fix metric card limit mismatches.

**Architecture:** Extend backend hot-reload to support `paper_trading` section (2 fields). Add `update_config` to PaperEngine. Replace Risk.tsx hardcoded panel with slider form that fetches config on load and patches on apply. Sync metric card limits with actual config values.

**Tech Stack:** Python (dataclasses, FastAPI), React (TypeScript), existing `PATCH /api/control/config` endpoint.

---

### Task 1: Add `update_config` to PaperEngine

**Files:**
- Modify: `src/service/paper_engine.py:39-41`
- Test: `tests/unit/test_hot_reload.py`

- [ ] **Step 1: Write failing test for PaperEngine.update_config**

Add to `tests/unit/test_hot_reload.py`:

```python
def test_paper_engine_update_config():
    from src.service.paper_engine import PaperEngine

    engine = PaperEngine(_make_pt_config())
    assert engine._config.max_position_pct == Decimal("0.25")

    new_config = _make_pt_config(max_position_pct=Decimal("0.5"))
    engine.update_config(new_config)

    assert engine._config.max_position_pct == Decimal("0.5")
    assert engine._config.max_open_positions == 4  # unchanged fields preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_hot_reload.py::test_paper_engine_update_config -v`
Expected: FAIL with `AttributeError: 'PaperEngine' object has no attribute 'update_config'`

- [ ] **Step 3: Implement update_config**

Add to `src/service/paper_engine.py` in the `PaperEngine` class, after `__init__`:

```python
def update_config(self, config: PaperTradingConfig) -> None:
    self._config = config
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_hot_reload.py::test_paper_engine_update_config -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/service/paper_engine.py tests/unit/test_hot_reload.py
git commit -m "feat: add update_config to PaperEngine for hot reload"
```

---

### Task 2: Extend hot-reload to support `paper_trading` section

**Files:**
- Modify: `src/runtime/app.py:38-48` (HOT_RELOAD_FIELDS)
- Modify: `src/runtime/app.py:263-327` (hot_reload method)
- Test: `tests/unit/test_hot_reload.py`

- [ ] **Step 1: Write failing test for paper_trading hot reload**

Add to `tests/unit/test_hot_reload.py`:

```python
def test_hot_reload_updates_paper_trading():
    """hot_reload with paper_trading fields updates PaperEngine and RiskManager."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    updated = app.hot_reload({"paper_trading": {"max_position_pct": 0.5, "max_open_positions": 8}})

    assert app.settings.paper_trading.max_position_pct == Decimal("0.5")
    assert app.settings.paper_trading.max_open_positions == 8
    assert app.paper_engine._config.max_position_pct == Decimal("0.5")
    assert app.risk_manager._pt.max_position_pct == Decimal("0.5")
    assert "paper_trading" in updated
    assert "max_position_pct" in updated["paper_trading"]
    assert "max_open_positions" in updated["paper_trading"]
```

- [ ] **Step 2: Write test that forbidden paper_trading fields still rejected**

Add to `tests/unit/test_hot_reload.py`:

```python
def test_hot_reload_rejects_forbidden_paper_trading_field():
    """hot_reload raises ValueError for non-allowed paper_trading fields."""
    from src.runtime.app import App

    settings = _make_settings()
    app = App(settings)

    with pytest.raises(ValueError, match="핫 리로드 불가"):
        app.hot_reload({"paper_trading": {"initial_balance": 999999}})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_hot_reload.py::test_hot_reload_updates_paper_trading tests/unit/test_hot_reload.py::test_hot_reload_rejects_forbidden_paper_trading_field -v`
Expected: First test FAIL (paper_trading not in HOT_RELOAD_FIELDS). Second test may pass or fail depending on error path.

- [ ] **Step 4: Add paper_trading to HOT_RELOAD_FIELDS**

In `src/runtime/app.py`, change the `HOT_RELOAD_FIELDS` dict (line 38-48):

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
    "paper_trading": {"max_position_pct", "max_open_positions"},
}
```

- [ ] **Step 5: Add paper_trading handling in hot_reload method**

In `src/runtime/app.py`, in the `hot_reload` method, after the `new_strategy` initialization (around line 280) add:

```python
new_pt = self.settings.paper_trading
```

After the `if "strategy" in patches:` block (around line 305-310), add:

```python
if "paper_trading" in patches:
    pt_coerced: dict[str, Any] = {}
    for k, v in patches["paper_trading"].items():
        field_type = next(
            f.type for f in dataclasses.fields(type(new_pt)) if f.name == k
        )
        pt_coerced[k] = Decimal(str(v)) if field_type == "Decimal" else int(str(v))
    new_pt = dataclasses.replace(new_pt, **pt_coerced)
    updated["paper_trading"] = list(patches["paper_trading"].keys())
```

In the `dataclasses.replace(self.settings, ...)` call (around line 312-317), add `paper_trading=new_pt`:

```python
self.settings = dataclasses.replace(
    self.settings,
    risk=new_risk,
    screening=new_screening,
    strategy=new_strategy,
    paper_trading=new_pt,
)
```

After the existing propagation blocks (around line 319-325), add:

```python
if "paper_trading" in patches:
    self.risk_manager._pt = new_pt
    self.paper_engine.update_config(new_pt)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_hot_reload.py -v`
Expected: ALL PASS

- [ ] **Step 7: Update the existing rejection test**

The existing `test_hot_reload_rejects_forbidden_field` tests `paper_trading.initial_balance` — this should still be rejected since `initial_balance` is not in the allowed set. Verify:

Run: `uv run pytest tests/unit/test_hot_reload.py::test_hot_reload_rejects_forbidden_field -v`
Expected: PASS (initial_balance is not in the allowed set, so it raises ValueError)

- [ ] **Step 8: Run full test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 9: Run linter and type checker**

Run: `uv run ruff check src/ && uv run mypy src/`
Expected: No errors

- [ ] **Step 10: Commit**

```bash
git add src/runtime/app.py tests/unit/test_hot_reload.py
git commit -m "feat: extend hot-reload to support paper_trading config"
```

---

### Task 3: Add slider CSS styles

**Files:**
- Modify: `src/ui/frontend/src/index.css`

- [ ] **Step 1: Add range slider styles**

Append to the end of `src/ui/frontend/src/index.css`:

```css
/* ── Range Slider ─────────────────────────────── */
.slider-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 0;
  border-bottom: 1px solid var(--border);
  gap: 16px;
}
.slider-row:last-child { border-bottom: none; }

.slider-label {
  color: var(--text-dim);
  font-size: 13px;
  min-width: 120px;
  flex-shrink: 0;
}

.slider-track {
  flex: 1;
  min-width: 120px;
}

.slider-value {
  color: var(--text);
  font-family: var(--font-mono);
  font-size: 14px;
  font-weight: 600;
  min-width: 70px;
  text-align: right;
  flex-shrink: 0;
}

input[type="range"] {
  -webkit-appearance: none;
  appearance: none;
  width: 100%;
  height: 4px;
  background: var(--border-bright);
  border-radius: 2px;
  outline: none;
  cursor: pointer;
}

input[type="range"]::-webkit-slider-thumb {
  -webkit-appearance: none;
  appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-card);
  box-shadow: 0 0 6px var(--accent-glow);
  cursor: pointer;
  transition: transform 0.15s var(--ease);
}

input[type="range"]::-webkit-slider-thumb:hover {
  transform: scale(1.2);
}

input[type="range"]::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--accent);
  border: 2px solid var(--bg-card);
  box-shadow: 0 0 6px var(--accent-glow);
  cursor: pointer;
}

.slider-buttons {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  margin-top: 20px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/ui/frontend/src/index.css
git commit -m "style: add range slider CSS for risk page"
```

---

### Task 4: Update Risk.tsx with slider UI and dynamic metric cards

**Files:**
- Modify: `src/ui/frontend/src/pages/Risk.tsx`

- [ ] **Step 1: Rewrite Risk.tsx**

Replace the entire content of `src/ui/frontend/src/pages/Risk.tsx` with:

```tsx
import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface RiskStatus {
  circuit_breaker_active: boolean;
  consecutive_losses: number;
  daily_trades: number;
  daily_loss_pct: string;
  cooldown_until: string | null;
}

interface ConfigValues {
  risk: {
    max_daily_loss_pct: number;
    max_daily_trades: number;
    consecutive_loss_limit: number;
    cooldown_minutes: number;
  };
  paper_trading: {
    max_position_pct: number;
    max_open_positions: number;
  };
}

interface SliderDef {
  section: "risk" | "paper_trading";
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
}

const SLIDERS: SliderDef[] = [
  {
    section: "risk", key: "max_daily_trades", label: "일일 최대 거래",
    min: 10, max: 500, step: 10,
    format: (v) => `${v}회`,
  },
  {
    section: "risk", key: "consecutive_loss_limit", label: "연속 손실 한도",
    min: 3, max: 20, step: 1,
    format: (v) => `${v}회`,
  },
  {
    section: "risk", key: "cooldown_minutes", label: "쿨다운 시간",
    min: 5, max: 120, step: 5,
    format: (v) => `${v}분`,
  },
  {
    section: "paper_trading", key: "max_position_pct", label: "포지션 최대 비중",
    min: 0.1, max: 1.0, step: 0.05,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    section: "paper_trading", key: "max_open_positions", label: "동시 포지션 수",
    min: 1, max: 10, step: 1,
    format: (v) => `${v}개`,
  },
];

export default function Risk() {
  const { get, patchJson } = useApi();
  const [status, setStatus] = useState<RiskStatus | null>(null);
  const [config, setConfig] = useState<ConfigValues | null>(null);
  const [form, setForm] = useState<Record<string, Record<string, number>>>({});
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<string | null>(null);

  // Fetch risk status
  useEffect(() => {
    get<RiskStatus>("/api/risk/status").then(setStatus);
    const interval = setInterval(() => {
      get<RiskStatus>("/api/risk/status").then(setStatus);
    }, 10_000);
    return () => clearInterval(interval);
  }, [get]);

  // Fetch config
  useEffect(() => {
    get<ConfigValues>("/api/control/config").then((data) => {
      setConfig(data);
      setForm({
        risk: { ...data.risk },
        paper_trading: { ...data.paper_trading },
      });
    });
  }, [get]);

  const handleSlider = (section: string, key: string, value: number) => {
    setForm((prev) => ({
      ...prev,
      [section]: { ...prev[section], [key]: value },
    }));
  };

  const hasChanges = (): boolean => {
    if (!config) return false;
    return SLIDERS.some(({ section, key }) => {
      const orig = (config[section] as Record<string, number>)[key];
      return form[section]?.[key] !== orig;
    });
  };

  const handleReset = () => {
    if (!config) return;
    setForm({
      risk: { ...config.risk },
      paper_trading: { ...config.paper_trading },
    });
  };

  const handleApply = async () => {
    if (!config) return;
    setSaving(true);
    setFeedback(null);

    const patch: Record<string, Record<string, number>> = {};
    for (const { section, key } of SLIDERS) {
      const orig = (config[section] as Record<string, number>)[key];
      const curr = form[section]?.[key];
      if (curr !== undefined && curr !== orig) {
        if (!patch[section]) patch[section] = {};
        patch[section][key] = curr;
      }
    }

    try {
      const res = await patchJson<{ config: ConfigValues }>("/api/control/config", patch);
      setConfig(res.config);
      setForm({
        risk: { ...res.config.risk },
        paper_trading: { ...res.config.paper_trading },
      });
      setFeedback("적용 완료");
      setTimeout(() => setFeedback(null), 3000);
    } catch {
      setFeedback("적용 실패");
    } finally {
      setSaving(false);
    }
  };

  // Derive limits from config (with fallbacks matching settings.yaml defaults)
  const dailyLossLimit = config?.risk.max_daily_loss_pct ?? 10;
  const consecutiveLossLimit = form.risk?.consecutive_loss_limit ?? config?.risk.consecutive_loss_limit ?? 10;
  const dailyTradesLimit = form.risk?.max_daily_trades ?? config?.risk.max_daily_trades ?? 200;

  if (!status) return <div className="loading">리스크 데이터 로딩 중...</div>;

  const lossLevel = Math.abs(Number(status.daily_loss_pct));
  const lossBarWidth = Math.min(lossLevel / dailyLossLimit, 1) * 100;
  const lossBarClass = lossLevel >= dailyLossLimit * 0.8 ? "danger" : lossLevel >= dailyLossLimit * 0.4 ? "warn" : "accent";

  const lossBars = 5;
  const activeBars = Math.min(status.consecutive_losses, lossBars);

  return (
    <div>
      <div className="page-header">
        <h2>리스크 관리</h2>
        <div className="page-sub">서킷 브레이커 상태 및 위험 지표</div>
      </div>

      {/* ── Circuit Breaker ────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>서킷 브레이커</h3>
          <span className={`badge ${status.circuit_breaker_active ? "loss" : "profit"}`}>
            {status.circuit_breaker_active ? "발동" : "정상"}
          </span>
        </div>
        <div className="panel-body">
          {status.circuit_breaker_active ? (
            <div style={{
              padding: "20px",
              background: "var(--loss-bg)",
              borderRadius: 8,
              border: "1px solid rgba(255, 68, 102, 0.15)",
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}>
              <span style={{ fontSize: 28 }}>&#9888;</span>
              <div>
                <div style={{ color: "var(--loss)", fontWeight: 600, fontSize: 14 }}>
                  매매 중단
                </div>
                <div style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 4 }}>
                  {status.cooldown_until
                    ? `${status.cooldown_until}까지 대기`
                    : "서킷 브레이커 발동 — 수동 재개 또는 대기 시간 만료를 기다리는 중입니다."}
                </div>
              </div>
            </div>
          ) : (
            <div style={{
              padding: "20px",
              background: "var(--profit-bg)",
              borderRadius: 8,
              border: "1px solid rgba(0, 224, 175, 0.1)",
              display: "flex",
              alignItems: "center",
              gap: 16,
            }}>
              <span style={{ fontSize: 28 }}>&#10003;</span>
              <div>
                <div style={{ color: "var(--profit)", fontWeight: 600, fontSize: 14 }}>
                  이상 없음
                </div>
                <div style={{ color: "var(--text-dim)", fontSize: 13, marginTop: 4 }}>
                  리스크 지표가 허용 범위 이내입니다. 매매가 활성화되어 있습니다.
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* ── Risk Metrics ───────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16, marginBottom: 20 }}>
        {/* Daily Loss */}
        <div className="card">
          <div className="label">일일 손실</div>
          <div className="value" style={{ fontSize: 20, color: lossLevel > 0 ? "var(--loss)" : "var(--text)" }}>
            {status.daily_loss_pct}%
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="progress-bar">
              <div className={`fill ${lossBarClass}`} style={{ width: `${lossBarWidth}%` }} />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              <span>0%</span>
              <span>-{dailyLossLimit}% 한도</span>
            </div>
          </div>
        </div>

        {/* Consecutive Losses */}
        <div className="card">
          <div className="label">연속 손실</div>
          <div className="value" style={{ fontSize: 20 }}>
            {status.consecutive_losses} / {consecutiveLossLimit}
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="risk-meter">
              {Array.from({ length: lossBars }, (_, i) => {
                const h = 10 + i * 5;
                const isActive = i < activeBars;
                const level = i < 2 ? "low" : i < 4 ? "med" : "high";
                return (
                  <div
                    key={i}
                    className={`bar ${isActive ? `active ${level}` : ""}`}
                    style={{ height: h }}
                  />
                );
              })}
            </div>
          </div>
        </div>

        {/* Daily Trades */}
        <div className="card">
          <div className="label">일일 거래 횟수</div>
          <div className="value" style={{ fontSize: 20 }}>
            {status.daily_trades} / {dailyTradesLimit}
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="progress-bar">
              <div
                className={`fill ${status.daily_trades >= dailyTradesLimit * 0.8 ? "danger" : status.daily_trades >= dailyTradesLimit * 0.5 ? "warn" : "accent"}`}
                style={{ width: `${(status.daily_trades / dailyTradesLimit) * 100}%` }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              <span>0</span>
              <span>{dailyTradesLimit} 한도</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Risk Sliders ──────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>투자 성향 조절</h3>
          {feedback && (
            <span className={`badge ${feedback === "적용 완료" ? "profit" : "loss"}`}>
              {feedback}
            </span>
          )}
        </div>
        <div className="panel-body">
          {SLIDERS.map(({ section, key, label, min, max, step, format }) => (
            <div key={key} className="slider-row">
              <span className="slider-label">{label}</span>
              <div className="slider-track">
                <input
                  type="range"
                  min={min}
                  max={max}
                  step={step}
                  value={form[section]?.[key] ?? min}
                  onChange={(e) => handleSlider(section, key, Number(e.target.value))}
                />
              </div>
              <span className="slider-value">{format(form[section]?.[key] ?? min)}</span>
            </div>
          ))}

          <div className="slider-buttons">
            <button className="btn" onClick={handleReset} disabled={saving || !hasChanges()}>
              초기화
            </button>
            <button className="btn btn-primary" onClick={handleApply} disabled={saving || !hasChanges()}>
              {saving ? "적용 중..." : "적용"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds with no errors

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Risk.tsx
git commit -m "feat: replace hardcoded risk rules with interactive sliders"
```

---

### Task 5: Update Settings.tsx HOT_RELOAD_FIELDS to include paper_trading

**Files:**
- Modify: `src/ui/frontend/src/pages/Settings.tsx:126-136`

- [ ] **Step 1: Add paper_trading to HOT_RELOAD_FIELDS**

In `src/ui/frontend/src/pages/Settings.tsx`, update the `HOT_RELOAD_FIELDS` constant (line 126-136):

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
  paper_trading: new Set(["max_position_pct", "max_open_positions"]),
};
```

- [ ] **Step 2: Verify the frontend builds**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Settings.tsx
git commit -m "feat: add paper_trading to Settings hot-reload fields"
```

---

### Task 6: Full integration verification

**Files:** None (verification only)

- [ ] **Step 1: Run full Python test suite**

Run: `uv run pytest -v`
Expected: ALL PASS

- [ ] **Step 2: Run linter and type checker**

Run: `uv run ruff check src/ && uv run mypy src/`
Expected: No errors

- [ ] **Step 3: Run frontend build**

Run: `cd src/ui/frontend && npm run build`
Expected: Build succeeds

- [ ] **Step 4: Final commit if any fixes needed**

Only if previous steps required fixes.

# Frontend UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프론트엔드를 6페이지→4페이지로 재구성. 대시보드를 메인 콕핏으로 통합, 전략/리스크에 인라인 설정 편집 추가, 설정 페이지를 시스템 제어 전용으로 축소.

**Architecture:** Charts.tsx와 Portfolio.tsx를 Dashboard.tsx에 흡수. 포지션 행 클릭 시 캔들차트 아코디언 펼침. Strategy.tsx에 screening/strategy/entry_analyzer 설정 인라인 편집 추가. Risk.tsx에 리스크/매매 설정 필드 확장. Settings.tsx → System.tsx로 리네임하여 엔진 제어 전용으로 축소.

**Tech Stack:** React 18, TypeScript, Vite, lightweight-charts, recharts, CSS variables

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `src/ui/frontend/src/App.tsx` | 4개 라우트, 4개 사이드바 메뉴 |
| Rewrite | `src/ui/frontend/src/pages/Dashboard.tsx` | 메인 콕핏: KPI + 자산추이 + 포지션(아코디언 차트) + 거래내역 |
| Modify | `src/ui/frontend/src/pages/Strategy.tsx` | 기존 + 전략 설정 인라인 편집 패널 추가 |
| Modify | `src/ui/frontend/src/pages/Risk.tsx` | 슬라이더 필드 확장 (stop_loss_pct, additional_buy 등) |
| Create | `src/ui/frontend/src/pages/System.tsx` | 엔진 제어 + 전체 초기화 + 읽기전용 정보 |
| Delete | `src/ui/frontend/src/pages/Charts.tsx` | 대시보드에 흡수 |
| Delete | `src/ui/frontend/src/pages/Portfolio.tsx` | 대시보드에 흡수 |

---

### Task 1: App.tsx — 라우트 및 사이드바 축소

**Files:**
- Modify: `src/ui/frontend/src/App.tsx`

- [ ] **Step 1: 라우트를 4개로 변경, 사이드바 메뉴 4개로 축소**

```tsx
import { useState, useEffect, useCallback } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./pages/Dashboard";
import Strategy from "./pages/Strategy";
import Risk from "./pages/Risk";
import System from "./pages/System";

function App() {
  const { isConnected } = useWebSocket("ws://localhost:8000/ws/live");
  const [tradingEnabled, setTradingEnabled] = useState(false);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/control/status");
      if (res.ok) {
        const data = await res.json();
        setTradingEnabled(data.trading_enabled);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const toggleTrading = async () => {
    const endpoint = tradingEnabled ? "/api/control/trading/stop" : "/api/control/trading/start";
    try {
      const res = await fetch(endpoint, { method: "POST" });
      if (res.ok) {
        setTradingEnabled(!tradingEnabled);
      }
    } catch { /* ignore */ }
  };

  return (
    <BrowserRouter>
      <div className="app-layout">
        <aside className="sidebar">
          <div className="sidebar-brand">
            <h1>CRYPTO<br />PAPER TRADER</h1>
            <div className="brand-sub">Upbit ML Strategy v0.1</div>
          </div>

          <ul className="sidebar-nav">
            <li>
              <NavLink to="/" end>
                <span className="nav-icon">&#9632;</span>
                대시보드
              </NavLink>
            </li>
            <li>
              <NavLink to="/strategy">
                <span className="nav-icon">&#9650;</span>
                전략
              </NavLink>
            </li>
            <li>
              <NavLink to="/risk">
                <span className="nav-icon">&#9679;</span>
                리스크
              </NavLink>
            </li>
            <li>
              <NavLink to="/system">
                <span className="nav-icon">&#9881;</span>
                시스템
              </NavLink>
            </li>
          </ul>

          <div className="sidebar-trading">
            <button
              className={`trading-toggle ${tradingEnabled ? "active" : ""}`}
              onClick={toggleTrading}
            >
              {tradingEnabled ? "매매 중지" : "매매 시작"}
            </button>
          </div>

          <div className="sidebar-status">
            <span className={`status-dot ${isConnected ? "live" : "offline"}`} />
            <span className="status-label">
              {isConnected ? "실시간" : "오프라인"}
            </span>
          </div>
        </aside>

        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/strategy" element={<Strategy />} />
            <Route path="/risk" element={<Risk />} />
            <Route path="/system" element={<System />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
```

- [ ] **Step 2: TypeScript 체크**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: System.tsx 관련 에러 (아직 미생성) — Task 5에서 해결

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/App.tsx
git commit -m "refactor: reduce sidebar to 4 pages (dashboard, strategy, risk, system)"
```

---

### Task 2: Dashboard.tsx — 메인 콕핏 (KPI + 자산추이 + 포지션 아코디언 차트 + 거래내역)

**Files:**
- Rewrite: `src/ui/frontend/src/pages/Dashboard.tsx`

이 파일은 기존 Dashboard + Portfolio + Charts를 통합하므로 전체 재작성합니다. 코드가 길어 핵심 구조만 기술합니다.

- [ ] **Step 1: Dashboard.tsx 전체 재작성**

파일 구조:
```
Dashboard.tsx
├── Interfaces: Summary, DailyRecord, PositionItem, HistoryItem, HistoryPage, CandleData
├── Helper functions: formatKRW, formatPct, formatQty, formatTime, pnlClass, pnlBadge
├── Component: Dashboard
│   ├── State: summary, daily, positions, history, period, expandedMarket, chartRefs
│   ├── Effects: fetchSummary (30s poll + WS), fetchPositions (30s), fetchDaily, fetchHistory
│   ├── Section 1: KPI cards (4-grid) — 매매 상태 배지 포함
│   ├── Section 2: Equity chart (AreaChart + period buttons)
│   ├── Section 3: Position table — 행 클릭 → expandedMarket 토글
│   │   └── Accordion row: lightweight-charts 캔들차트 (해당 마켓)
│   └── Section 4: Trade history table + pagination
```

핵심 로직 — 포지션 아코디언 차트:
```tsx
// State
const [expandedMarket, setExpandedMarket] = useState<string | null>(null);
const chartContainerRef = useRef<HTMLDivElement>(null);
const chartRef = useRef<IChartApi | null>(null);

// 행 클릭 핸들러
const handlePositionClick = (market: string) => {
  setExpandedMarket((prev) => (prev === market ? null : market));
};

// 차트 생성/업데이트 effect
useEffect(() => {
  if (!expandedMarket || !chartContainerRef.current) return;

  // 이전 차트 제거
  if (chartRef.current) {
    chartRef.current.remove();
    chartRef.current = null;
  }

  // lightweight-charts 생성 (Charts.tsx와 동일한 옵션)
  const chart = createChart(chartContainerRef.current, {
    layout: { background: { color: "#0b1018" }, textColor: "#4a5a70", fontFamily: "'JetBrains Mono', monospace", fontSize: 11 },
    grid: { vertLines: { color: "#1a2332" }, horzLines: { color: "#1a2332" } },
    rightPriceScale: { borderColor: "#1e2a3a", scaleMargins: { top: 0.1, bottom: 0.25 } },
    timeScale: { borderColor: "#1e2a3a", timeVisible: true, secondsVisible: false },
  });
  const candleSeries = chart.addSeries(CandlestickSeries, {
    upColor: "#00e0af", downColor: "#ff4466",
    borderUpColor: "#00e0af", borderDownColor: "#ff4466",
    wickUpColor: "#00e0af", wickDownColor: "#ff4466",
  });
  const volumeSeries = chart.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
  volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
  chartRef.current = chart;

  // 데이터 로드
  get<CandleData[]>(`/api/dashboard/candles?market=${expandedMarket}&limit=100`).then((raw) => {
    candleSeries.setData(raw.map((c) => ({
      time: c.timestamp as CandlestickData["time"],
      open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close),
    })));
    volumeSeries.setData(raw.map((c) => ({
      time: c.timestamp as HistogramData["time"],
      value: Number(c.volume),
      color: Number(c.close) >= Number(c.open) ? "rgba(0,224,175,0.3)" : "rgba(255,68,102,0.3)",
    })));
    chart.timeScale().fitContent();
  });

  return () => { chart.remove(); chartRef.current = null; };
}, [expandedMarket, get]);
```

포지션 테이블 렌더링 (아코디언 포함):
```tsx
{positions.map((pos) => (
  <React.Fragment key={pos.market}>
    <tr
      onClick={() => handlePositionClick(pos.market)}
      style={{ cursor: "pointer" }}
    >
      {/* 코인, 평단가, 현재가, 손익, 수익률, 수량, 총투자금, 평가금액, 상태 */}
    </tr>
    {expandedMarket === pos.market && (
      <tr>
        <td colSpan={9} style={{ padding: 0 }}>
          <div ref={chartContainerRef} style={{ height: 300, width: "100%" }} />
        </td>
      </tr>
    )}
  </React.Fragment>
))}
```

거래내역 섹션은 기존 Portfolio.tsx의 거래내역 코드를 그대로 가져옵니다 (HistoryItem interface, formatTime, pagination 포함).

- [ ] **Step 2: 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: System.tsx 관련 에러만 남음

- [ ] **Step 3: Commit**

```bash
git add src/ui/frontend/src/pages/Dashboard.tsx
git commit -m "feat: dashboard cockpit with positions, accordion chart, trade history"
```

---

### Task 3: Strategy.tsx — 전략 설정 인라인 편집 추가

**Files:**
- Modify: `src/ui/frontend/src/pages/Strategy.tsx`

기존 코드(스크리닝, 신호, 모델 상태)는 그대로 유지. 하단에 전략 설정 인라인 편집 패널을 추가.

- [ ] **Step 1: 설정 편집 상태 및 타입 추가**

파일 상단 import에 추가:
```tsx
import { useCallback, useEffect, useMemo, useState } from "react";
```

interface 추가 (기존 interface 블록 뒤에):
```tsx
interface StrategyConfig {
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
  entry_analyzer: {
    min_entry_score: number;
    price_lookback_candles: number;
  };
}

interface SettingFieldDef {
  section: "screening" | "strategy" | "entry_analyzer";
  key: string;
  label: string;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  hotReload: boolean;
}

const STRATEGY_FIELDS: SettingFieldDef[] = [
  // 스크리닝
  { section: "screening", key: "min_volume_krw", label: "최소 거래대금", min: 100000000, max: 5000000000, step: 100000000, format: (v) => `₩${(v / 100000000).toFixed(0)}억`, hotReload: true },
  { section: "screening", key: "min_volatility_pct", label: "최소 변동성", min: 0.5, max: 10, step: 0.5, format: (v) => `${v}%`, hotReload: true },
  { section: "screening", key: "max_volatility_pct", label: "최대 변동성", min: 5, max: 50, step: 1, format: (v) => `${v}%`, hotReload: true },
  { section: "screening", key: "max_coins", label: "최대 코인 수", min: 1, max: 20, step: 1, format: (v) => `${v}개`, hotReload: true },
  // ML 전략
  { section: "strategy", key: "min_confidence", label: "최소 신뢰도", min: 0.3, max: 0.95, step: 0.05, format: (v) => `${(v * 100).toFixed(0)}%`, hotReload: true },
  { section: "strategy", key: "threshold_pct", label: "분류 임계값", min: 0.1, max: 1.0, step: 0.05, format: (v) => `±${v}%`, hotReload: false },
  { section: "strategy", key: "retrain_interval_hours", label: "재학습 주기", min: 1, max: 24, step: 1, format: (v) => `${v}시간`, hotReload: false },
  // 진입 분석
  { section: "entry_analyzer", key: "min_entry_score", label: "최소 진입 스코어", min: 0.1, max: 0.9, step: 0.05, format: (v) => `${v}`, hotReload: false },
  { section: "entry_analyzer", key: "price_lookback_candles", label: "가격 참조 캔들", min: 20, max: 200, step: 10, format: (v) => `${v}개`, hotReload: false },
];
```

- [ ] **Step 2: 컴포넌트 내에 설정 상태 및 핸들러 추가**

Strategy 컴포넌트 내, 기존 state 선언 뒤에 추가:
```tsx
const [config, setConfig] = useState<StrategyConfig | null>(null);
const [form, setForm] = useState<Record<string, Record<string, number>>>({});
const [saving, setSaving] = useState(false);
const [feedback, setFeedback] = useState<string | null>(null);

// config 로드
useEffect(() => {
  get<StrategyConfig>("/api/control/config").then((data) => {
    setConfig(data);
    setForm({
      screening: { ...data.screening, always_include: undefined } as unknown as Record<string, number>,
      strategy: { ...data.strategy } as unknown as Record<string, number>,
      entry_analyzer: { ...data.entry_analyzer } as unknown as Record<string, number>,
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
  return STRATEGY_FIELDS.some(({ section, key }) => {
    const orig = (config[section] as Record<string, unknown>)[key];
    return form[section]?.[key] !== undefined && form[section][key] !== orig;
  });
};

const handleReset = () => {
  if (!config) return;
  setForm({
    screening: { ...config.screening, always_include: undefined } as unknown as Record<string, number>,
    strategy: { ...config.strategy } as unknown as Record<string, number>,
    entry_analyzer: { ...config.entry_analyzer } as unknown as Record<string, number>,
  });
};

const handleApply = async () => {
  if (!config) return;
  setSaving(true);
  setFeedback(null);

  const patch: Record<string, Record<string, number>> = {};
  for (const { section, key, hotReload } of STRATEGY_FIELDS) {
    if (!hotReload) continue;
    const orig = (config[section] as Record<string, unknown>)[key];
    const curr = form[section]?.[key];
    if (curr !== undefined && curr !== orig) {
      if (!patch[section]) patch[section] = {};
      patch[section][key] = curr;
    }
  }

  if (Object.keys(patch).length === 0) {
    setSaving(false);
    setFeedback("변경 사항 없음");
    setTimeout(() => setFeedback(null), 2000);
    return;
  }

  try {
    const res = await patchJson<{ config: StrategyConfig }>("/api/control/config", patch);
    setConfig(res.config);
    setFeedback("적용 완료");
    setTimeout(() => setFeedback(null), 3000);
  } catch {
    setFeedback("적용 실패");
  } finally {
    setSaving(false);
  }
};
```

`useApi` destructure에 `patchJson` 추가:
```tsx
const { get, patchJson } = useApi();
```

- [ ] **Step 3: 모델 상태 패널 아래에 설정 편집 UI 추가**

기존 JSX 마지막 `</div>` 직전에 추가:
```tsx
{/* ── Strategy Settings ───────────── */}
<div className="panel">
  <div className="panel-header">
    <h3>전략 설정</h3>
    <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
      {feedback && (
        <span className={`badge ${feedback === "적용 완료" ? "profit" : feedback === "적용 실패" ? "loss" : "neutral"}`}>
          {feedback}
        </span>
      )}
    </div>
  </div>
  <div className="panel-body">
    {STRATEGY_FIELDS.map(({ section, key, label, min, max, step, format, hotReload }) => (
      <div key={`${section}.${key}`} className="slider-row">
        <span className="slider-label">
          {label}
          {!hotReload && <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>(초기화 필요)</span>}
        </span>
        <div className="slider-track">
          <input
            type="range"
            min={min}
            max={max}
            step={step}
            value={form[section]?.[key] ?? min}
            onChange={(e) => handleSlider(section, key, Number(e.target.value))}
            disabled={!hotReload}
            style={{ opacity: hotReload ? 1 : 0.4 }}
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
```

- [ ] **Step 4: 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`

- [ ] **Step 5: Commit**

```bash
git add src/ui/frontend/src/pages/Strategy.tsx
git commit -m "feat: add inline strategy settings editor to strategy page"
```

---

### Task 4: Risk.tsx — 리스크/매매 설정 필드 확장

**Files:**
- Modify: `src/ui/frontend/src/pages/Risk.tsx`

기존 SLIDERS 배열에 누락된 필드를 추가하고, ConfigValues 타입을 확장.

- [ ] **Step 1: SLIDERS 배열을 전체 교체**

기존 `SLIDERS` 배열을 아래로 교체:
```tsx
const SLIDERS: SliderDef[] = [
  // 리스크
  {
    section: "risk", key: "stop_loss_pct", label: "손절 기준",
    min: 0.005, max: 0.1, step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    section: "risk", key: "take_profit_pct", label: "전량 익절 기준",
    min: 0.02, max: 0.2, step: 0.01,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
  {
    section: "risk", key: "trailing_stop_pct", label: "트레일링 스톱",
    min: 0.005, max: 0.05, step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    section: "risk", key: "partial_take_profit_pct", label: "부분 익절 기준",
    min: 0.01, max: 0.1, step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    section: "risk", key: "partial_sell_fraction", label: "부분 매도 비율",
    min: 0.1, max: 0.9, step: 0.1,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
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
  // 매매
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
  {
    section: "paper_trading", key: "max_additional_buys", label: "최대 추가매수 횟수",
    min: 0, max: 10, step: 1,
    format: (v) => `${v}회`,
  },
  {
    section: "paper_trading", key: "additional_buy_drop_pct", label: "추가매수 하락률",
    min: 0.01, max: 0.1, step: 0.005,
    format: (v) => `${(v * 100).toFixed(1)}%`,
  },
  {
    section: "paper_trading", key: "additional_buy_ratio", label: "추가매수 비율",
    min: 0.1, max: 1.0, step: 0.05,
    format: (v) => `${(v * 100).toFixed(0)}%`,
  },
];
```

- [ ] **Step 2: ConfigValues에 새 필드 추가**

```tsx
interface ConfigValues {
  risk: {
    stop_loss_pct: number;
    take_profit_pct: number;
    trailing_stop_pct: number;
    max_daily_loss_pct: number;
    max_daily_trades: number;
    consecutive_loss_limit: number;
    cooldown_minutes: number;
    partial_take_profit_pct: number;
    partial_sell_fraction: number;
  };
  paper_trading: {
    max_position_pct: number;
    max_open_positions: number;
    max_additional_buys: number;
    additional_buy_drop_pct: number;
    additional_buy_ratio: number;
  };
}
```

- [ ] **Step 3: 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/Risk.tsx
git commit -m "feat: expand risk page with all risk/trading sliders"
```

---

### Task 5: System.tsx — 엔진 제어 전용 페이지 생성

**Files:**
- Create: `src/ui/frontend/src/pages/System.tsx`
- Delete: `src/ui/frontend/src/pages/Settings.tsx`

- [ ] **Step 1: System.tsx 생성**

엔진 제어(매매 시작/중지, 일시정지/재개) + 전체 초기화(확인 모달) + 읽기전용 시스템 정보 + About.

```tsx
import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

type SystemStatus = "running" | "paused" | "unknown";

interface SystemConfig {
  paper_trading: {
    initial_balance: number;
    fee_rate: number;
    slippage_rate: number;
    min_order_krw: number;
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
}

interface TradingStatus {
  paused: boolean;
  trading_enabled: boolean;
}

const INFO_FIELDS: { section: keyof SystemConfig; label: string; fields: { key: string; label: string }[] }[] = [
  {
    section: "collector", label: "수집",
    fields: [
      { key: "candle_timeframe", label: "캔들 주기 (분)" },
      { key: "max_candles_per_market", label: "마켓당 최대 캔들" },
      { key: "market_refresh_interval_min", label: "마켓 갱신 주기 (분)" },
    ],
  },
  {
    section: "data", label: "데이터",
    fields: [
      { key: "db_path", label: "DB 경로" },
      { key: "model_dir", label: "모델 디렉토리" },
      { key: "stale_candle_days", label: "캔들 유효기간 (일)" },
      { key: "stale_model_days", label: "모델 유효기간 (일)" },
      { key: "stale_order_days", label: "주문 유효기간 (일)" },
    ],
  },
];

export default function System() {
  const { get, post, postJson } = useApi();
  const [status, setStatus] = useState<SystemStatus>("unknown");
  const [tradingEnabled, setTradingEnabled] = useState(false);
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [loading, setLoading] = useState(false);
  const [showReset, setShowReset] = useState(false);

  useEffect(() => {
    get<TradingStatus>("/api/control/status").then((s) => {
      setStatus(s.paused ? "paused" : "running");
      setTradingEnabled(s.trading_enabled);
    });
    get<SystemConfig>("/api/control/config").then(setConfig);
  }, [get]);

  const handlePause = async () => {
    setLoading(true);
    await post("/api/control/pause");
    setStatus("paused");
    setLoading(false);
  };

  const handleResume = async () => {
    setLoading(true);
    await post("/api/control/resume");
    setStatus("running");
    setLoading(false);
  };

  const handleTradingToggle = async () => {
    const endpoint = tradingEnabled ? "/api/control/trading/stop" : "/api/control/trading/start";
    setLoading(true);
    await post(endpoint);
    setTradingEnabled(!tradingEnabled);
    setLoading(false);
  };

  const handleReset = async () => {
    if (!config) return;
    setShowReset(false);
    setLoading(true);
    // Full config needed for reset — fetch current and pass through
    const fullConfig = await get("/api/control/config");
    await postJson("/api/control/reset", fullConfig);
    setStatus("running");
    setLoading(false);
  };

  return (
    <div>
      <div className="page-header">
        <h2>시스템</h2>
        <div className="page-sub">매매 엔진 제어 및 시스템 정보</div>
      </div>

      {/* ── Engine Control ─────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>매매 엔진</h3>
          <div style={{ display: "flex", gap: 8 }}>
            <span className={`badge ${status === "running" ? "profit" : "warn"}`}>
              {status === "running" ? "실행 중" : status === "paused" ? "일시정지" : "알 수 없음"}
            </span>
            <span className={`badge ${tradingEnabled ? "profit" : "neutral"}`}>
              {tradingEnabled ? "매매 활성" : "매매 비활성"}
            </span>
          </div>
        </div>
        <div className="panel-body">
          <div style={{ display: "flex", gap: 12, padding: "12px 0" }}>
            {status === "running" ? (
              <button className="btn btn-danger" onClick={handlePause} disabled={loading}>
                일시정지
              </button>
            ) : (
              <button className="btn btn-primary" onClick={handleResume} disabled={loading}>
                재개
              </button>
            )}
            <button
              className={`btn ${tradingEnabled ? "btn-danger" : "btn-primary"}`}
              onClick={handleTradingToggle}
              disabled={loading}
            >
              {tradingEnabled ? "매매 중지" : "매매 시작"}
            </button>
          </div>
        </div>
      </div>

      {/* ── Reset ──────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>전체 초기화</h3>
          <span className="badge loss">위험</span>
        </div>
        <div className="panel-body">
          <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 16px" }}>
            잔고와 거래내역이 모두 초기화됩니다. 학습 데이터와 모델은 유지됩니다.
          </p>
          <button className="btn btn-danger" onClick={() => setShowReset(true)} disabled={loading}>
            초기화 실행
          </button>
        </div>
      </div>

      {/* ── System Info ────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>시스템 정보</h3>
        </div>
        <div className="panel-body">
          {config && INFO_FIELDS.map(({ section, label, fields }) => (
            <div key={section} style={{ marginBottom: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.05em", color: "var(--accent)", marginBottom: 8 }}>
                {label}
              </div>
              {fields.map(({ key, label: fieldLabel }) => (
                <div key={key} style={{ display: "flex", justifyContent: "space-between", padding: "6px 0", borderBottom: "1px solid rgba(31, 45, 64, 0.4)", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                  <span style={{ color: "var(--text-dim)" }}>{fieldLabel}</span>
                  <span style={{ color: "var(--text)" }}>{String((config[section] as Record<string, unknown>)[key])}</span>
                </div>
              ))}
            </div>
          ))}
        </div>
      </div>

      {/* ── About ──────────────────────── */}
      <div className="panel">
        <div className="panel-header"><h3>정보</h3></div>
        <div className="panel-body">
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 14, color: "var(--text-dim)", lineHeight: 2.0 }}>
            <div>Crypto Paper Trader v0.1.0</div>
            <div>Upbit ML Strategy — LightGBM</div>
            <div>6-Layer Architecture: types → config → repository → service → runtime → ui</div>
          </div>
        </div>
      </div>

      {/* ── Reset Modal ────────────────── */}
      {showReset && (
        <div style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }} onClick={() => setShowReset(false)}>
          <div style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 420, width: "90%" }} onClick={(e) => e.stopPropagation()}>
            <h3 style={{ margin: "0 0 12px", color: "var(--text)" }}>초기화 확인</h3>
            <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 24px" }}>
              잔고와 거래내역이 모두 초기화됩니다.<br />학습 데이터와 모델은 유지됩니다.<br />진행하시겠습니까?
            </p>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12 }}>
              <button className="btn" onClick={() => setShowReset(false)}>취소</button>
              <button className="btn btn-danger" onClick={handleReset}>확인</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Settings.tsx 삭제**

```bash
rm src/ui/frontend/src/pages/Settings.tsx
```

- [ ] **Step 3: 빌드 확인**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: 에러 없음

- [ ] **Step 4: Commit**

```bash
git add src/ui/frontend/src/pages/System.tsx
git rm src/ui/frontend/src/pages/Settings.tsx
git commit -m "feat: replace Settings with System page (engine control only)"
```

---

### Task 6: Charts.tsx, Portfolio.tsx 삭제 + 최종 검증

**Files:**
- Delete: `src/ui/frontend/src/pages/Charts.tsx`
- Delete: `src/ui/frontend/src/pages/Portfolio.tsx`

- [ ] **Step 1: 파일 삭제**

```bash
rm src/ui/frontend/src/pages/Charts.tsx
rm src/ui/frontend/src/pages/Portfolio.tsx
```

- [ ] **Step 2: TypeScript 체크**

Run: `cd src/ui/frontend && npx tsc --noEmit`
Expected: 에러 없음 (App.tsx에서 이미 import 제거됨)

- [ ] **Step 3: 프론트엔드 빌드**

Run: `cd src/ui/frontend && npm run build`
Expected: `✓ built in Xs`

- [ ] **Step 4: 백엔드 테스트**

Run: `uv run pytest`
Expected: 143 passed (프론트엔드 변경이므로 백엔드 영향 없음)

- [ ] **Step 5: Commit**

```bash
git rm src/ui/frontend/src/pages/Charts.tsx
git rm src/ui/frontend/src/pages/Portfolio.tsx
git commit -m "refactor: remove Charts and Portfolio pages (absorbed into Dashboard)"
```

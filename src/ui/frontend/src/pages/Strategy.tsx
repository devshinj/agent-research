import { useCallback, useEffect, useMemo, useState } from "react";
import { createPortal } from "react-dom";
import { useAuthContext } from "../context/AuthContext";

const REFRESH_INTERVAL_MS = 15_000;

interface ScreeningResult {
  market: string;
  korean_name: string;
  price: string;
  volume_krw: string;
  volatility_pct: string;
  score: number;
}

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
  training: Record<string, number>;
}

interface StrategyConfig {
  screening: { min_volume_krw: number; min_volatility_pct: number; max_volatility_pct: number; max_coins: number; refresh_interval_min: number; always_include: string[] };
  strategy: { lookahead_minutes: number; threshold_pct: number; retrain_interval_hours: number; min_confidence: number };
  entry_analyzer: { min_entry_score: number; price_lookback_candles: number };
}

interface SettingFieldDef {
  section: "screening" | "strategy" | "entry_analyzer";
  key: string;
  label: string;
  desc: string;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
  hotReload: boolean;
}

const STRATEGY_FIELDS: SettingFieldDef[] = [
  { section: "screening", key: "min_volume_krw", label: "최소 거래대금", desc: "24시간 거래대금이 이 금액 미만인 코인은 스크리닝에서 제외됩니다", min: 100000000, max: 5000000000, step: 100000000, format: (v) => `₩${(v / 100000000).toFixed(0)}억`, hotReload: true },
  { section: "screening", key: "min_volatility_pct", label: "최소 변동성", desc: "변동성이 이 값보다 낮은 코인은 매매 기회가 적어 제외됩니다", min: 0.5, max: 10, step: 0.5, format: (v) => `${v}%`, hotReload: true },
  { section: "screening", key: "max_volatility_pct", label: "최대 변동성", desc: "변동성이 이 값을 초과하는 코인은 위험이 높아 제외됩니다", min: 5, max: 50, step: 1, format: (v) => `${v}%`, hotReload: true },
  { section: "screening", key: "max_coins", label: "최대 코인 수", desc: "스크리닝 결과에서 상위 N개 코인만 선택합니다", min: 1, max: 20, step: 1, format: (v) => `${v}개`, hotReload: true },
  { section: "strategy", key: "min_confidence", label: "최소 신뢰도", desc: "ML 모델의 예측 신뢰도가 이 값 이하이면 HOLD로 처리합니다", min: 0.3, max: 0.95, step: 0.05, format: (v) => `${(v * 100).toFixed(0)}%`, hotReload: true },
  { section: "strategy", key: "threshold_pct", label: "분류 임계값", desc: "이 비율 이상 상승이 예상되면 BUY로 분류합니다 (변경 시 자동 재학습)", min: 0.1, max: 1.0, step: 0.05, format: (v) => `${v}%`, hotReload: true },
  { section: "strategy", key: "retrain_interval_hours", label: "재학습 주기", desc: "ML 모델을 자동으로 재학습하는 간격입니다", min: 1, max: 24, step: 1, format: (v) => `${v}시간`, hotReload: false },
  { section: "entry_analyzer", key: "min_entry_score", label: "최소 진입 스코어", desc: "가격위치/RSI/추세를 종합한 스코어가 이 값 미만이면 매수를 거부합니다 (0~1)", min: 0.1, max: 0.9, step: 0.05, format: (v) => `${v}`, hotReload: false },
  { section: "entry_analyzer", key: "price_lookback_candles", label: "가격 참조 캔들", desc: "현재 가격의 상대적 위치를 판단할 때 참조하는 최근 캔들 수입니다", min: 20, max: 200, step: 10, format: (v) => `${v}개`, hotReload: false },
];

type SortKey = "price" | "volume_krw" | "volatility_pct" | "score";
type SortDir = "asc" | "desc";

export default function Strategy() {
  const { auth, api } = useAuthContext();
  const { get, patchJson } = api;
  const [screening, setScreening] = useState<ScreeningResult[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [tooltipSignal, setTooltipSignal] = useState<{ basis: BasisEntry[]; x: number; y: number } | null>(null);
  const [config, setConfig] = useState<StrategyConfig | null>(null);
  const [form, setForm] = useState<Record<string, Record<string, number>>>({});
  const [saving, setSaving] = useState(false);
  const [settingsFeedback, setSettingsFeedback] = useState<string | null>(null);
  const [includeHold, setIncludeHold] = useState(false);
  const [signalPage, setSignalPage] = useState(0);
  const SIGNALS_PER_PAGE = 10;

  const refreshAll = useCallback(() => {
    get<ScreeningResult[]>("/api/strategy/screening").then(setScreening);
    get<Signal[]>(`/api/strategy/signals?include_hold=${includeHold}`).then(setSignals);
    get<ModelStatus>("/api/strategy/model-status").then(setModelStatus);
  }, [get, includeHold]);

  // Initial load + polling every 30s (including model-status for training state)
  useEffect(() => {
    refreshAll();
    const id = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshAll]);

  useEffect(() => {
    if (!auth.isAdmin) return;
    get<StrategyConfig>("/api/control/config").then((data) => {
      setConfig(data);
      setForm({
        screening: { min_volume_krw: data.screening.min_volume_krw, min_volatility_pct: data.screening.min_volatility_pct, max_volatility_pct: data.screening.max_volatility_pct, max_coins: data.screening.max_coins },
        strategy: { min_confidence: data.strategy.min_confidence, threshold_pct: data.strategy.threshold_pct, retrain_interval_hours: data.strategy.retrain_interval_hours },
        entry_analyzer: { min_entry_score: data.entry_analyzer.min_entry_score, price_lookback_candles: data.entry_analyzer.price_lookback_candles },
      });
    });
  }, [get, auth.isAdmin]);

  const handleSlider = (section: string, key: string, value: number) => {
    setForm((prev) => ({ ...prev, [section]: { ...prev[section], [key]: value } }));
  };

  const hasSettingsChanges = (): boolean => {
    if (!config) return false;
    return STRATEGY_FIELDS.some(({ section, key }) => {
      const orig = (config[section] as Record<string, unknown>)[key];
      return form[section]?.[key] !== undefined && form[section][key] !== orig;
    });
  };

  const handleSettingsReset = () => {
    if (!config) return;
    setForm({
      screening: { min_volume_krw: config.screening.min_volume_krw, min_volatility_pct: config.screening.min_volatility_pct, max_volatility_pct: config.screening.max_volatility_pct, max_coins: config.screening.max_coins },
      strategy: { min_confidence: config.strategy.min_confidence, threshold_pct: config.strategy.threshold_pct, retrain_interval_hours: config.strategy.retrain_interval_hours },
      entry_analyzer: { min_entry_score: config.entry_analyzer.min_entry_score, price_lookback_candles: config.entry_analyzer.price_lookback_candles },
    });
  };

  const handleSettingsApply = async () => {
    if (!config) return;
    setSaving(true);
    setSettingsFeedback(null);
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
      setSettingsFeedback("변경 사항 없음");
      setTimeout(() => setSettingsFeedback(null), 2000);
      return;
    }
    try {
      const res = await patchJson<{ config: StrategyConfig }>("/api/control/config", patch);
      setConfig(res.config);
      setSettingsFeedback("적용 완료");
      setTimeout(() => setSettingsFeedback(null), 3000);
    } catch {
      setSettingsFeedback("적용 실패");
    } finally {
      setSaving(false);
    }
  };

  const toggleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
  };

  const sortedScreening = useMemo(() => {
    const arr = [...screening];
    const mul = sortDir === "desc" ? -1 : 1;
    arr.sort((a, b) => mul * (Number(a[sortKey]) - Number(b[sortKey])));
    return arr;
  }, [screening, sortKey, sortDir]);

  const sortIndicator = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? " \u25BC" : " \u25B2") : "";

  const modelEntries = modelStatus
    ? Object.entries(modelStatus.models)
    : [];

  const trainingMarkets = modelStatus?.training ?? {};
  const trainingCount = Object.keys(trainingMarkets).length;

  return (
    <div>
      <div className="page-header">
        <h2>전략</h2>
        <div className="page-sub">마켓 스크리닝, ML 신호, 모델 성능</div>
      </div>

      {/* ── Screening ──────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>마켓 스크리닝</h3>
          <span className="badge info">{screening.length} coins</span>
        </div>
        {screening.length === 0 ? (
          <div className="panel-body">
            <div className="empty-state">
              <div className="empty-icon">&#9650;</div>
              <div className="empty-text">
                스크리닝된 마켓이 없습니다. 스크리너가 거래량 및 변동성 기준으로 코인을 필터링합니다.
              </div>
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>코인</th>
                <th style={{ cursor: "pointer" }} onClick={() => toggleSort("price")}>현재가{sortIndicator("price")}</th>
                <th style={{ cursor: "pointer" }} onClick={() => toggleSort("volume_krw")}>거래량 (KRW){sortIndicator("volume_krw")}</th>
                <th style={{ cursor: "pointer" }} onClick={() => toggleSort("volatility_pct")}>변동성{sortIndicator("volatility_pct")}</th>
                <th style={{ cursor: "pointer" }} onClick={() => toggleSort("score")}>점수{sortIndicator("score")}</th>
              </tr>
            </thead>
            <tbody>
              {sortedScreening.map((s) => (
                <tr key={s.market}>
                  <td style={{ color: "var(--text)", fontWeight: 600 }}>
                    {s.korean_name} <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 12.5, marginLeft: 6 }}>({s.market.replace("KRW-", "")})</span>
                  </td>
                  <td>{`\u20A9${Number(s.price).toLocaleString("ko-KR")}`}</td>
                  <td>{`\u20A9${Math.floor(Number(s.volume_krw)).toLocaleString("ko-KR")}`}</td>
                  <td>{Number(s.volatility_pct).toFixed(2)}%</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span style={{ fontWeight: 600, color: Number(s.score) >= 50 ? "var(--accent)" : Number(s.score) >= 20 ? "var(--warn)" : "var(--danger)" }}>
                        {Number(s.score).toFixed(1)}
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Signals ────────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>활성 신호</h3>
          <span className="badge neutral">{signals.length}</span>
          <label style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 6, fontSize: 13, cursor: "pointer" }}>
            <input
              type="checkbox"
              checked={includeHold}
              onChange={(e) => { setIncludeHold(e.target.checked); setSignalPage(0); }}
            />
            HOLD 포함
          </label>
        </div>
        {signals.length === 0 ? (
          <div className="panel-body">
            <div className="empty-state">
              <div className="empty-icon">&#9889;</div>
              <div className="empty-text">
                활성 신호가 없습니다. 캔들 수집 후 ML 예측이 시작되면 BUY/SELL 신호가 표시됩니다.
              </div>
            </div>
          </div>
        ) : (
          <>
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
                {signals.slice(signalPage * SIGNALS_PER_PAGE, (signalPage + 1) * SIGNALS_PER_PAGE).map((s, i) => (
                  <tr
                    key={i}
                    className="signal-row"
                    onMouseEnter={(e) => {
                      if (s.basis) {
                        const rect = e.currentTarget.getBoundingClientRect();
                        setTooltipSignal({ basis: s.basis, x: rect.left, y: rect.bottom + 4 });
                      }
                    }}
                    onMouseLeave={() => setTooltipSignal(null)}
                  >
                    <td>{s.created_at}</td>
                    <td style={{ color: "var(--text)", fontWeight: 600 }}>{s.market}</td>
                    <td>
                      <span className={`badge ${s.signal_type === "BUY" ? "profit" : s.signal_type === "SELL" ? "loss" : "neutral"}`}>
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
            {signals.length > SIGNALS_PER_PAGE && (
              <div style={{ display: "flex", justifyContent: "center", alignItems: "center", gap: 12, padding: "8px 0" }}>
                <button
                  className="btn btn-sm"
                  disabled={signalPage === 0}
                  onClick={() => setSignalPage((p) => p - 1)}
                >
                  &lt;
                </button>
                <span style={{ fontSize: 13 }}>
                  {signalPage + 1} / {Math.ceil(signals.length / SIGNALS_PER_PAGE)}
                </span>
                <button
                  className="btn btn-sm"
                  disabled={(signalPage + 1) * SIGNALS_PER_PAGE >= signals.length}
                  onClick={() => setSignalPage((p) => p + 1)}
                >
                  &gt;
                </button>
              </div>
            )}
          </>
        )}
      </div>

      {tooltipSignal && createPortal(
        <div
          className="signal-tooltip"
          style={{ display: "block", position: "fixed", left: tooltipSignal.x, top: tooltipSignal.y }}
        >
          <div className="signal-tooltip-title">신호 근거</div>
          {tooltipSignal.basis.map((b) => (
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
        </div>,
        document.body,
      )}

      {/* ── Strategy Settings (admin only) ── */}
      {auth.isAdmin && (
        <div className="panel">
          <div className="panel-header">
            <h3>전략 설정</h3>
            {settingsFeedback && (
              <span className={`badge ${settingsFeedback === "적용 완료" ? "profit" : settingsFeedback === "적용 실패" ? "loss" : "neutral"}`}>
                {settingsFeedback}
              </span>
            )}
          </div>
          <div className="panel-body">
            {STRATEGY_FIELDS.map(({ section, key, label, desc, min, max, step, format, hotReload }) => (
              <div key={`${section}.${key}`} className="slider-row">
                <span className="slider-label" data-tooltip={desc}>
                  {label}
                  {!hotReload && <span style={{ fontSize: 10, color: "var(--text-muted)", marginLeft: 6 }}>(초기화 필요)</span>}
                </span>
                <div className="slider-track">
                  <input
                    type="range" min={min} max={max} step={step}
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
              <button className="btn" onClick={handleSettingsReset} disabled={saving || !hasSettingsChanges()}>초기화</button>
              <button className="btn btn-primary" onClick={handleSettingsApply} disabled={saving || !hasSettingsChanges()}>
                {saving ? "적용 중..." : "적용"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Model Status ───────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>모델 상태</h3>
          <div style={{ display: "flex", gap: 8 }}>
            {trainingCount > 0 && (
              <span className="badge warn" style={{ animation: "pulse 1.5s ease-in-out infinite" }}>
                학습 중: {trainingCount}개 마켓
              </span>
            )}
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
        <div className="panel-body">
          {modelEntries.length === 0 && trainingCount === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">&#9881;</div>
              <div className="empty-text">
                학습된 모델이 없습니다. 충분한 캔들 데이터가 수집되면 모델 학습이 시작됩니다.
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 20 }}>
              {/* Cards for markets currently training without an existing model */}
              {Object.entries(trainingMarkets)
                .filter(([m]) => !modelStatus?.models[m])
                .map(([market, elapsed]) => (
                  <div key={market} className="card" style={{ opacity: 0.85 }}>
                    <div className="label">{market}</div>
                    <div className="value" style={{ fontSize: 16, color: "var(--warn)" }}>
                      <span style={{ animation: "pulse 1.5s ease-in-out infinite", display: "inline-block" }}>
                        학습 중...
                      </span>
                    </div>
                    <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 8, fontFamily: "var(--font-mono)" }}>
                      경과: {Math.floor(elapsed)}초
                    </div>
                  </div>
                ))}
              {modelEntries.map(([name, info]) => {
                const total = info.total_signals || 0;
                const buyPct = total > 0 ? (info.buy_count / total) * 100 : 0;
                const sellPct = total > 0 ? (info.sell_count / total) * 100 : 0;
                const holdPct = total > 0 ? (info.hold_count / total) * 100 : 0;
                const isTraining = name in trainingMarkets;

                return (
                  <div key={name} className="card">
                    <div className="label" style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      {name}
                      {isTraining && (
                        <span className="badge warn" style={{ fontSize: 10, padding: "1px 6px", animation: "pulse 1.5s ease-in-out infinite" }}>
                          재학습 중 ({Math.floor(trainingMarkets[name])}초)
                        </span>
                      )}
                    </div>
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
            </div>
          )}
        </div>
      </div>

      
    </div>
  );
}

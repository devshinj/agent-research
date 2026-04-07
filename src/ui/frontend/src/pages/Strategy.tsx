import { useCallback, useEffect, useMemo, useState } from "react";
import { useApi } from "../hooks/useApi";

const REFRESH_INTERVAL_MS = 30_000;

interface ScreeningResult {
  market: string;
  korean_name: string;
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

type SortKey = "volume_krw" | "volatility_pct" | "score";
type SortDir = "asc" | "desc";

export default function Strategy() {
  const { get } = useApi();
  const [screening, setScreening] = useState<ScreeningResult[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);
  const [sortKey, setSortKey] = useState<SortKey>("score");
  const [sortDir, setSortDir] = useState<SortDir>("desc");

  const refreshAll = useCallback(() => {
    get<ScreeningResult[]>("/api/strategy/screening").then(setScreening);
    get<Signal[]>("/api/strategy/signals").then(setSignals);
    get<ModelStatus>("/api/strategy/model-status").then(setModelStatus);
  }, [get]);

  // Initial load + polling every 30s (including model-status for training state)
  useEffect(() => {
    refreshAll();
    const id = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshAll]);

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
        </div>
        {signals.length === 0 ? (
          <div className="panel-body">
            <div className="empty-state">
              <div className="empty-icon">&#9889;</div>
              <div className="empty-text">
                활성 신호가 없습니다. ML 예측기가 학습된 모델을 기반으로 매수/매도 신호를 생성합니다.
              </div>
            </div>
          </div>
        ) : (
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
          </table>
        )}
      </div>

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

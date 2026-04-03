import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface ScreeningResult {
  market: string;
  korean_name: string;
  volume_krw: string;
  volatility_pct: string;
  score: number;
}

interface Signal {
  market: string;
  signal_type: string;
  confidence: number;
  predicted_pct: string;
  created_at: string;
}

interface ModelStatus {
  models: Record<string, { accuracy: number; last_train: string }>;
  last_retrain: string | null;
}

export default function Strategy() {
  const { get } = useApi();
  const [screening, setScreening] = useState<ScreeningResult[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [modelStatus, setModelStatus] = useState<ModelStatus | null>(null);

  useEffect(() => {
    get<ScreeningResult[]>("/api/strategy/screening").then(setScreening);
    get<Signal[]>("/api/strategy/signals").then(setSignals);
    get<ModelStatus>("/api/strategy/model-status").then(setModelStatus);
  }, [get]);

  const modelEntries = modelStatus
    ? Object.entries(modelStatus.models)
    : [];

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
                <th>거래량 (KRW)</th>
                <th>변동성</th>
                <th>점수</th>
              </tr>
            </thead>
            <tbody>
              {screening.map((s) => (
                <tr key={s.market}>
                  <td style={{ color: "var(--text)", fontWeight: 600 }}>
                    {s.korean_name} <span style={{ color: "var(--text-muted)", fontWeight: 400, fontSize: 12 }}>({s.market.replace("KRW-", "")})</span>
                  </td>
                  <td>{`\u20A9${Number(s.volume_krw).toLocaleString("ko-KR")}`}</td>
                  <td>{s.volatility_pct}%</td>
                  <td>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <div className="progress-bar" style={{ flex: 1, maxWidth: 100 }}>
                        <div
                          className={`fill ${s.score >= 0.7 ? "accent" : s.score >= 0.4 ? "warn" : "danger"}`}
                          style={{ width: `${s.score * 100}%` }}
                        />
                      </div>
                      <span>{(s.score * 100).toFixed(0)}</span>
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
                <th>예측</th>
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
                  <td style={{ color: Number(s.predicted_pct) >= 0 ? "var(--profit)" : "var(--loss)" }}>
                    {Number(s.predicted_pct) > 0 ? "+" : ""}{s.predicted_pct}%
                  </td>
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
          {modelStatus?.last_retrain && (
            <span className="badge neutral">
              최근 학습: {modelStatus.last_retrain}
            </span>
          )}
        </div>
        <div className="panel-body">
          {modelEntries.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">&#9881;</div>
              <div className="empty-text">
                학습된 모델이 없습니다. 충분한 캔들 데이터가 수집되면 모델 학습이 시작됩니다.
              </div>
            </div>
          ) : (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(260px, 1fr))", gap: 16 }}>
              {modelEntries.map(([name, info]) => (
                <div key={name} className="card">
                  <div className="label">{name}</div>
                  <div className="value" style={{ fontSize: 18 }}>
                    {(info.accuracy * 100).toFixed(1)}%
                  </div>
                  <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 6, fontFamily: "var(--font-mono)" }}>
                    학습일: {info.last_train}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

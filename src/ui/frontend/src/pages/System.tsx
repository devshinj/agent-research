import { useEffect, useState } from "react";
import { useAuthContext } from "../context/AuthContext";

type SystemStatus = "running" | "paused" | "unknown";

interface TradingStatus {
  paused: boolean;
  trading_enabled: boolean;
}

interface SystemConfig {
  paper_trading: { initial_balance: number; fee_rate: number; slippage_rate: number; min_order_krw: number };
  collector: { candle_timeframe: number; max_candles_per_market: number; market_refresh_interval_min: number };
  data: { db_path: string; model_dir: string; stale_candle_days: number; stale_model_days: number; stale_order_days: number };
}

const INFO_FIELDS: { section: keyof SystemConfig; label: string; fields: { key: string; label: string }[] }[] = [
  {
    section: "paper_trading", label: "모의매매",
    fields: [
      { key: "initial_balance", label: "초기 잔고 (KRW)" },
      { key: "fee_rate", label: "수수료율" },
      { key: "slippage_rate", label: "슬리피지율" },
      { key: "min_order_krw", label: "최소 주문금액 (KRW)" },
    ],
  },
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
  const { api } = useAuthContext();
  const { get, post, postJson } = api;
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
    setShowReset(false);
    setLoading(true);
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

      {/* ── Engine Status ─────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>엔진 상태</h3>
          <span className={`badge ${status === "running" ? "profit" : "warn"}`}>
            {status === "running" ? "가동 중" : status === "paused" ? "일시정지" : "알 수 없음"}
          </span>
        </div>
        <div className="panel-body">
          <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 12px", fontSize: 13 }}>
            엔진을 일시정지하면 데이터 수집, ML 신호 생성, 포지션 모니터링이 모두 중단됩니다.
            수동 매매는 영향받지 않습니다.
          </p>
          <div style={{ display: "flex", gap: 12 }}>
            {status === "running" ? (
              <button className="btn btn-ghost" onClick={handlePause} disabled={loading}>
                엔진 일시정지
              </button>
            ) : (
              <button className="btn btn-primary" onClick={handleResume} disabled={loading}>
                엔진 재개
              </button>
            )}
          </div>
        </div>
      </div>

      {/* ── Auto Trading ────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>자동매매</h3>
          <span className={`badge ${tradingEnabled ? "profit" : "neutral"}`}>
            {tradingEnabled ? "ON" : "OFF"}
          </span>
        </div>
        <div className="panel-body">
          <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 12px", fontSize: 13 }}>
            {tradingEnabled
              ? "ML 신호에 따라 자동으로 매수/매도를 실행합니다. 중지해도 데이터 수집과 신호 생성은 계속됩니다."
              : "자동매매가 꺼져 있습니다. ML 신호는 생성되지만 주문이 실행되지 않습니다. 수동 매매는 가능합니다."}
          </p>
          <button
            className={`btn ${tradingEnabled ? "btn-danger" : "btn-primary"}`}
            onClick={handleTradingToggle}
            disabled={loading}
          >
            {tradingEnabled ? "자동매매 중지" : "자동매매 시작"}
          </button>
        </div>
      </div>

      {/* ── Reset ──────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>계좌 초기화</h3>
          <span className="badge loss">위험</span>
        </div>
        <div className="panel-body">
          <p style={{ color: "var(--text-dim)", lineHeight: 1.6, margin: "0 0 16px", fontSize: 13 }}>
            잔고와 거래내역이 모두 초기화됩니다. 보유 포지션이 전부 삭제됩니다.
            학습된 모델과 캔들 데이터는 유지됩니다.
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

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

import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface RiskStatus {
  circuit_breaker_active: boolean;
  consecutive_losses: number;
  daily_trades: number;
  daily_loss_pct: string;
  cooldown_until: string | null;
}

export default function Risk() {
  const { get } = useApi();
  const [status, setStatus] = useState<RiskStatus | null>(null);

  useEffect(() => {
    get<RiskStatus>("/api/risk/status").then(setStatus);
    const interval = setInterval(() => {
      get<RiskStatus>("/api/risk/status").then(setStatus);
    }, 10_000);
    return () => clearInterval(interval);
  }, [get]);

  if (!status) return <div className="loading">리스크 데이터 로딩 중...</div>;

  const lossLevel = Math.abs(Number(status.daily_loss_pct));
  const lossBarWidth = Math.min(lossLevel / 5, 1) * 100; // 5% = full bar
  const lossBarClass = lossLevel >= 4 ? "danger" : lossLevel >= 2 ? "warn" : "accent";

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
              <span>-5% 한도</span>
            </div>
          </div>
        </div>

        {/* Consecutive Losses */}
        <div className="card">
          <div className="label">연속 손실</div>
          <div className="value" style={{ fontSize: 20 }}>
            {status.consecutive_losses} / 5
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
            {status.daily_trades} / 50
          </div>
          <div style={{ marginTop: 12 }}>
            <div className="progress-bar">
              <div
                className={`fill ${status.daily_trades >= 40 ? "danger" : status.daily_trades >= 25 ? "warn" : "accent"}`}
                style={{ width: `${(status.daily_trades / 50) * 100}%` }}
              />
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", marginTop: 6, fontSize: 10, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
              <span>0</span>
              <span>50 한도</span>
            </div>
          </div>
        </div>
      </div>

      {/* ── Risk Rules ─────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>리스크 규칙</h3>
        </div>
        <div className="panel-body">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, fontFamily: "var(--font-mono)", fontSize: 13 }}>
            {[
              ["손절매", "2.0%"],
              ["익절매", "5.0%"],
              ["추적 손절", "1.5%"],
              ["일일 최대 손실", "5.0%"],
              ["일일 최대 거래", "50"],
              ["연속 손실 한도", "5"],
              ["대기 시간", "60분"],
              ["최대 포지션 비중", "25%"],
            ].map(([rule, val]) => (
              <div key={rule} style={{ display: "flex", justifyContent: "space-between", padding: "8px 0", borderBottom: "1px solid var(--border)" }}>
                <span style={{ color: "var(--text-dim)" }}>{rule}</span>
                <span style={{ color: "var(--text)" }}>{val}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

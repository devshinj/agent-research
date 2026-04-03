import { useState } from "react";
import { useApi } from "../hooks/useApi";

type SystemStatus = "running" | "paused" | "unknown";

export default function Settings() {
  const { post } = useApi();
  const [status, setStatus] = useState<SystemStatus>("running");
  const [loading, setLoading] = useState(false);

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
          <span className={`badge ${status === "running" ? "profit" : status === "paused" ? "warn" : "neutral"}`}>
            {status.toUpperCase()}
          </span>
        </div>
        <div className="panel-body">
          <div style={{
            display: "flex",
            alignItems: "center",
            gap: 16,
            padding: "16px 0",
          }}>
            <div style={{ flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text)" }}>
                모의매매 엔진
              </div>
              <div style={{ fontSize: 13, color: "var(--text-dim)", marginTop: 4 }}>
                {status === "running"
                  ? "엔진이 시장을 모니터링하며 모의매매를 실행 중입니다."
                  : status === "paused"
                    ? "매매가 일시 중지되었습니다. 새로운 포지션이 개시되지 않습니다."
                    : "시스템 상태를 알 수 없습니다."}
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              {status === "running" ? (
                <button className="btn btn-danger" onClick={handlePause} disabled={loading}>
                  {loading ? "..." : "일시정지"}
                </button>
              ) : (
                <button className="btn btn-primary" onClick={handleResume} disabled={loading}>
                  {loading ? "..." : "재개"}
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* ── Configuration ──────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>매매 설정</h3>
          <span className="badge neutral">읽기 전용</span>
        </div>
        <div className="panel-body">
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 0, fontFamily: "var(--font-mono)", fontSize: 13 }}>
            {[
              { section: "모의매매", items: [
                ["초기 잔고", "\u20A910,000,000"],
                ["최대 포지션 비중", "25%"],
                ["최대 동시 포지션", "4"],
                ["수수료율", "0.05%"],
                ["최소 주문금액", "\u20A95,000"],
              ]},
              { section: "전략", items: [
                ["예측 시간", "5분"],
                ["임계값", "0.3%"],
                ["재학습 주기", "6시간"],
                ["최소 신뢰도", "60%"],
              ]},
              { section: "스크리닝", items: [
                ["최소 거래량", "\u20A9500M"],
                ["변동성 범위", "1.0% ~ 15.0%"],
                ["최대 코인 수", "10"],
                ["갱신 주기", "30분"],
              ]},
              { section: "데이터", items: [
                ["캔들 주기", "1분"],
                ["마켓당 최대 캔들", "200"],
                ["캔들 유효기간", "7일"],
                ["모델 유효기간", "30일"],
              ]},
            ].map(({ section, items }) => (
              <div key={section} style={{ padding: "12px 0" }}>
                <div style={{
                  fontSize: 11,
                  fontWeight: 600,
                  textTransform: "uppercase",
                  letterSpacing: "0.06em",
                  color: "var(--accent)",
                  marginBottom: 10,
                  fontFamily: "var(--font-display)",
                }}>
                  {section}
                </div>
                {items.map(([label, val]) => (
                  <div
                    key={label}
                    style={{
                      display: "flex",
                      justifyContent: "space-between",
                      padding: "6px 0",
                      borderBottom: "1px solid rgba(30, 42, 58, 0.4)",
                    }}
                  >
                    <span style={{ color: "var(--text-dim)" }}>{label}</span>
                    <span style={{ color: "var(--text)" }}>{val}</span>
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ── About ──────────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>정보</h3>
        </div>
        <div className="panel-body">
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text-dim)", lineHeight: 1.8 }}>
            <div>Crypto Paper Trader v0.1.0</div>
            <div>Upbit ML Strategy &mdash; LightGBM / XGBoost</div>
            <div>6-Layer Architecture: types &rarr; config &rarr; repository &rarr; service &rarr; runtime &rarr; ui</div>
          </div>
        </div>
      </div>
    </div>
  );
}

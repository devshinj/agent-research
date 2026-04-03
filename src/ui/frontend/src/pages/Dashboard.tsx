import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

interface Summary {
  total_equity: string;
  cash_balance: string;
  daily_pnl: string;
  total_return_pct: string;
  open_positions: number;
}

interface DailyRecord {
  date: string;
  equity: number;
}

const formatKRW = (val: string) =>
  `\u20A9${Number(val).toLocaleString("ko-KR")}`;

const pnlClass = (val: string) => {
  const n = Number(val);
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "";
};

export default function Dashboard() {
  const { get } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [daily, setDaily] = useState<DailyRecord[]>([]);

  useEffect(() => {
    get<Summary>("/api/dashboard/summary").then(setSummary);
    get<DailyRecord[]>("/api/portfolio/daily").then((d) =>
      setDaily(
        d.length > 0
          ? d
          : Array.from({ length: 14 }, (_, i) => ({
              date: `D-${14 - i}`,
              equity: 10_000_000,
            }))
      )
    );
  }, [get]);

  useEffect(() => {
    if (lastMessage?.type === "summary_update") {
      setSummary(lastMessage.data as unknown as Summary);
    }
  }, [lastMessage]);

  if (!summary) return <div className="loading">대시보드 로딩 중...</div>;

  return (
    <div>
      <div className="page-header">
        <h2>대시보드</h2>
        <div className="page-sub">모의투자 계좌 실시간 현황</div>
      </div>

      {/* ── KPI Cards ──────────────────────── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">총 자산</div>
          <div className="kpi-value">{formatKRW(summary.total_equity)}</div>
          <div className="kpi-sub">Total Equity</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">현금 잔고</div>
          <div className="kpi-value">{formatKRW(summary.cash_balance)}</div>
          <div className="kpi-sub">Cash Balance</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">금일 손익</div>
          <div className={`kpi-value ${pnlClass(summary.daily_pnl)}`}>
            {formatKRW(summary.daily_pnl)}
          </div>
          <div className="kpi-sub">Daily P&L</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">총 수익률</div>
          <div className={`kpi-value ${pnlClass(summary.total_return_pct)}`}>
            {summary.total_return_pct}%
          </div>
          <div className="kpi-sub">Total Return</div>
        </div>
      </div>

      {/* ── Equity Chart ───────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>자산 추이</h3>
          <span className="badge neutral">{daily.length}일</span>
        </div>
        <div className="panel-body" style={{ height: 280 }}>
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={daily}>
              <defs>
                <linearGradient id="eqGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#00e0af" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="#00e0af" stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 11, fill: "#4a5a70" }}
                axisLine={{ stroke: "#1e2a3a" }}
                tickLine={false}
              />
              <YAxis
                tick={{ fontSize: 11, fill: "#4a5a70" }}
                axisLine={false}
                tickLine={false}
                tickFormatter={(v: number) => `${(v / 1_000_000).toFixed(1)}M`}
              />
              <Tooltip
                contentStyle={{
                  background: "#151d28",
                  border: "1px solid #2a3a50",
                  borderRadius: 6,
                  fontFamily: "'JetBrains Mono', monospace",
                  fontSize: 12,
                  color: "#e8edf4",
                }}
              />
              <Area
                type="monotone"
                dataKey="equity"
                stroke="#00e0af"
                strokeWidth={2}
                fill="url(#eqGrad)"
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* ── Quick Stats ────────────────────── */}
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 16 }}>
        <div className="panel">
          <div className="panel-header">
            <h3>보유 포지션</h3>
            <span className="badge info">{summary.open_positions}</span>
          </div>
          <div className="panel-body">
            {summary.open_positions === 0 ? (
              <div className="empty-state">
                <div className="empty-icon">&#9670;</div>
                <div className="empty-text">보유 포지션 없음. ML 모델이 기회를 포착하면 신호가 표시됩니다.</div>
              </div>
            ) : (
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 13, color: "var(--text-dim)" }}>
                {summary.open_positions}개 활성 포지션
              </div>
            )}
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <h3>시스템 상태</h3>
            <span className="badge profit">정상</span>
          </div>
          <div className="panel-body">
            <div style={{ display: "grid", gap: 12, fontFamily: "var(--font-mono)", fontSize: 13 }}>
              <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-dim)" }}>
                <span>모의매매 엔진</span>
                <span style={{ color: "var(--profit)" }}>실행 중</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-dim)" }}>
                <span>데이터 수집기</span>
                <span style={{ color: "var(--profit)" }}>활성</span>
              </div>
              <div style={{ display: "flex", justifyContent: "space-between", color: "var(--text-dim)" }}>
                <span>리스크 관리자</span>
                <span style={{ color: "var(--profit)" }}>정상</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

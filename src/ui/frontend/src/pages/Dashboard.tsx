import { useCallback, useEffect, useRef, useState } from "react";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";

const REFRESH_INTERVAL_MS = 30_000;

interface Summary {
  total_equity: string;
  cash_balance: string;
  daily_pnl: string;
  total_pnl: string;
  total_return_pct: string;
  open_positions: number;
  initial_balance: string;
}

interface DailyRecord {
  date: string;
  equity: number;
}

interface PositionItem {
  market: string;
  korean_name: string;
  quantity: string;
  avg_price: string;
  current_price: string;
  unrealized_pnl: string;
  pnl_pct: string;
  eval_amount: string;
}

type Period = "24h" | "day" | "week" | "month";

const PERIOD_LABELS: Record<Period, string> = {
  "24h": "24시간",
  day: "1일",
  week: "1주",
  month: "1개월",
};

const formatKRW = (val: string | undefined | null) => {
  if (val == null) return "\u20A90";
  const n = Number(val);
  if (Number.isNaN(n)) return "\u20A90";
  return `\u20A9${Math.floor(n).toLocaleString("ko-KR")}`;
};

const formatPct = (val: string) => {
  const n = Number(val);
  if (Number.isNaN(n)) return "0.00%";
  const prefix = n > 0 ? "+" : "";
  return `${prefix}${n.toFixed(2)}%`;
};

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
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [period, setPeriod] = useState<Period>("24h");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [refreshing, setRefreshing] = useState(false);
  const periodRef = useRef(period);
  periodRef.current = period;

  const fetchDaily = useCallback(
    (p: Period) =>
      get<DailyRecord[]>(`/api/portfolio/daily?period=${p}`).then((d) =>
        setDaily(
          d.length > 0
            ? d
            : Array.from({ length: 14 }, (_, i) => ({
                date: `D-${14 - i}`,
                equity: 10_000_000,
              }))
        )
      ),
    [get]
  );

  const refreshAll = useCallback(() => {
    setRefreshing(true);
    Promise.all([
      get<Summary>("/api/dashboard/summary").then(setSummary),
      get<PositionItem[]>("/api/portfolio/positions").then(setPositions),
      fetchDaily(periodRef.current),
    ]).finally(() => {
      setLastRefresh(new Date());
      setRefreshing(false);
    });
  }, [get, fetchDaily]);

  // Initial load + auto-refresh every 30s
  useEffect(() => {
    refreshAll();
    const id = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshAll]);

  // Re-fetch chart when period changes
  useEffect(() => {
    fetchDaily(period);
  }, [period, fetchDaily]);

  useEffect(() => {
    if (lastMessage?.type === "summary_update") {
      setSummary(lastMessage.data as unknown as Summary);
      setLastRefresh(new Date());
    }
  }, [lastMessage]);

  const handlePeriod = (p: Period) => {
    setPeriod(p);
  };

  if (!summary) return <div className="loading">대시보드 로딩 중...</div>;

  return (
    <div>
      <div className="page-header" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h2>대시보드</h2>
          <div className="page-sub">모의투자 계좌 실시간 현황</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
            {lastRefresh.toLocaleTimeString("ko-KR")} 갱신
          </span>
          <button
            className="btn btn-ghost"
            style={{ padding: "6px 14px", fontSize: 12 }}
            onClick={refreshAll}
            disabled={refreshing}
          >
            {refreshing ? "갱신 중..." : "새로고침"}
          </button>
        </div>
      </div>

      {/* ── KPI Cards ──────────────────────── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div className="kpi-label">총 평가 자산</div>
          <div className={`kpi-value ${pnlClass(String(Number(summary.total_equity) - Number(summary.initial_balance)))}`}>
            {formatKRW(summary.total_equity)}
          </div>
          <div className="kpi-sub" style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}>
            투자 원금 {formatKRW(summary.initial_balance)}
          </div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">투자 가능 금액</div>
          <div className="kpi-value">{formatKRW(summary.cash_balance)}</div>
          <div className="kpi-sub">Available Cash</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">총 평가 손익</div>
          <div className={`kpi-value ${pnlClass(summary.total_pnl)}`}>
            {formatKRW(summary.total_pnl)}
          </div>
          <div className="kpi-sub">Total P&amp;L</div>
        </div>
        <div className="kpi-card">
          <div className="kpi-label">총 수익률</div>
          <div className={`kpi-value ${pnlClass(summary.total_return_pct)}`}>
            {formatPct(summary.total_return_pct)}
          </div>
          <div className="kpi-sub">Total Return</div>
        </div>
      </div>

      {/* ── Equity Chart ───────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>자산 추이</h3>
          <div className="period-switch">
            {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
              <button
                key={p}
                className={`period-btn${period === p ? " active" : ""}`}
                onClick={() => handlePeriod(p)}
              >
                {PERIOD_LABELS[p]}
              </button>
            ))}
          </div>
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

      {/* ── Positions Table ────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>보유 포지션</h3>
          <span className="badge info">{positions.length}개</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {positions.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">&#9670;</div>
              <div className="empty-text">
                보유 포지션 없음. ML 모델이 기회를 포착하면 신호가 표시됩니다.
              </div>
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>코인</th>
                  <th style={{ textAlign: "right" }}>보유 수량</th>
                  <th style={{ textAlign: "right" }}>평균 매수가</th>
                  <th style={{ textAlign: "right" }}>현재가</th>
                  <th style={{ textAlign: "right" }}>평가 금액</th>
                  <th style={{ textAlign: "right" }}>평가 손익</th>
                  <th style={{ textAlign: "right" }}>수익률</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <tr key={pos.market}>
                    <td>
                      <div style={{ fontWeight: 600, color: "var(--text)" }}>
                        {pos.korean_name}
                      </div>
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--text-muted)",
                          marginTop: 2,
                        }}
                      >
                        {pos.market}
                      </div>
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {Number(pos.quantity).toFixed(8).replace(/0+$/, "").replace(/\.$/, "")}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {formatKRW(pos.avg_price)}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {formatKRW(pos.current_price)}
                    </td>
                    <td style={{ textAlign: "right" }}>
                      {formatKRW(pos.eval_amount)}
                    </td>
                    <td
                      style={{ textAlign: "right" }}
                      className={pnlClass(pos.unrealized_pnl)}
                    >
                      {formatKRW(pos.unrealized_pnl)}
                    </td>
                    <td
                      style={{ textAlign: "right" }}
                      className={pnlClass(pos.pnl_pct)}
                    >
                      {formatPct(pos.pnl_pct)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  );
}

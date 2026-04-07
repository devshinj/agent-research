import { useCallback, useEffect, useRef, useState, Fragment } from "react";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer,
} from "recharts";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type CandlestickData,
  type HistogramData,
} from "lightweight-charts";

const REFRESH_INTERVAL_MS = 30_000;

/* ── Types ──────────────────────────────────────── */

interface Summary {
  total_equity: string;
  cash_balance: string;
  daily_pnl: string;
  total_pnl: string;
  total_return_pct: string;
  open_positions: number;
  initial_balance: string;
  trading_enabled?: boolean;
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
  add_count: number;
  total_invested: string;
  partial_sold: boolean;
  highest_price: string;
}

interface CandleRaw {
  timestamp: string;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

interface HistoryItem {
  id: number;
  filled_at: string;
  market: string;
  korean_name: string;
  side: string;
  quantity: string;
  price: string;
  total_amount: string;
}

interface HistoryResponse {
  items: HistoryItem[];
  page: number;
  size: number;
  total: number;
}

type Period = "24h" | "day" | "week" | "month";

const PERIOD_LABELS: Record<Period, string> = {
  "24h": "24시간",
  day: "1일",
  week: "1주",
  month: "1개월",
};

/* ── Helpers ────────────────────────────────────── */

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

/* ── Component ──────────────────────────────────── */

export default function Dashboard() {
  const { get } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");

  // Core state
  const [summary, setSummary] = useState<Summary | null>(null);
  const [daily, setDaily] = useState<DailyRecord[]>([]);
  const [positions, setPositions] = useState<PositionItem[]>([]);
  const [period, setPeriod] = useState<Period>("24h");
  const [lastRefresh, setLastRefresh] = useState<Date>(new Date());
  const [refreshing, setRefreshing] = useState(false);
  const periodRef = useRef(period);
  periodRef.current = period;

  // Accordion state
  const [expandedMarket, setExpandedMarket] = useState<string | null>(null);
  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartInstanceRef = useRef<IChartApi | null>(null);

  // Trade history state
  const [history, setHistory] = useState<HistoryResponse | null>(null);
  const [historyPage, setHistoryPage] = useState(1);

  /* ── Data fetching ───────────────────────────── */

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

  const fetchHistory = useCallback(
    (page: number) =>
      get<HistoryResponse>(`/api/portfolio/history?page=${page}&size=20`).then(
        setHistory
      ),
    [get]
  );

  const refreshAll = useCallback(() => {
    setRefreshing(true);
    Promise.all([
      get<Summary>("/api/dashboard/summary").then(setSummary),
      get<PositionItem[]>("/api/portfolio/positions").then(setPositions),
      fetchDaily(periodRef.current),
      fetchHistory(1),
    ]).finally(() => {
      setLastRefresh(new Date());
      setRefreshing(false);
      setHistoryPage(1);
    });
  }, [get, fetchDaily, fetchHistory]);

  // Initial load + polling
  useEffect(() => {
    refreshAll();
    const id = setInterval(refreshAll, REFRESH_INTERVAL_MS);
    return () => clearInterval(id);
  }, [refreshAll]);

  // Re-fetch equity chart when period changes
  useEffect(() => {
    fetchDaily(period);
  }, [period, fetchDaily]);

  // Re-fetch history when page changes
  useEffect(() => {
    fetchHistory(historyPage);
  }, [historyPage, fetchHistory]);

  // WebSocket summary updates
  useEffect(() => {
    if (lastMessage?.type === "summary_update") {
      setSummary(lastMessage.data as unknown as Summary);
      setLastRefresh(new Date());
    }
  }, [lastMessage]);

  /* ── Accordion candlestick chart ─────────────── */

  useEffect(() => {
    // Clean up previous chart
    if (chartInstanceRef.current) {
      chartInstanceRef.current.remove();
      chartInstanceRef.current = null;
    }

    if (!expandedMarket || !chartContainerRef.current) return;

    const container = chartContainerRef.current;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 360,
      layout: {
        background: { color: "#0b1018" },
        textColor: "#4a5a70",
        fontFamily: "'JetBrains Mono', monospace",
        fontSize: 11,
      },
      grid: {
        vertLines: { color: "#1a2332" },
        horzLines: { color: "#1a2332" },
      },
      crosshair: {
        vertLine: { color: "#2a3a50", labelBackgroundColor: "#151d28" },
        horzLine: { color: "#2a3a50", labelBackgroundColor: "#151d28" },
      },
      timeScale: {
        borderColor: "#1a2332",
        timeVisible: true,
      },
      rightPriceScale: {
        borderColor: "#1a2332",
      },
    });

    chartInstanceRef.current = chart;

    const candleSeries = chart.addSeries(CandlestickSeries, {
      upColor: "#00e0af",
      downColor: "#ff4466",
      borderUpColor: "#00e0af",
      borderDownColor: "#ff4466",
      wickUpColor: "#00e0af",
      wickDownColor: "#ff4466",
    });

    const volumeSeries = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    get<CandleRaw[]>(
      `/api/dashboard/candles?market=${expandedMarket}&limit=100`
    ).then((candles) => {
      const candleData: CandlestickData[] = candles.map((c) => ({
        time: (Number(c.timestamp) / 1000) as unknown as CandlestickData["time"],
        open: Number(c.open),
        high: Number(c.high),
        low: Number(c.low),
        close: Number(c.close),
      }));

      const volumeData: HistogramData[] = candles.map((c) => ({
        time: (Number(c.timestamp) / 1000) as unknown as HistogramData["time"],
        value: Number(c.volume),
        color:
          Number(c.close) >= Number(c.open)
            ? "rgba(0, 224, 175, 0.3)"
            : "rgba(255, 68, 102, 0.3)",
      }));

      candleSeries.setData(candleData);
      volumeSeries.setData(volumeData);
      chart.timeScale().fitContent();
    });

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartInstanceRef.current = null;
    };
  }, [expandedMarket, get]);

  /* ── Handlers ────────────────────────────────── */

  const handleRowClick = (market: string) => {
    setExpandedMarket((prev) => (prev === market ? null : market));
  };

  const totalHistoryPages = history
    ? Math.ceil(history.total / history.size)
    : 1;

  /* ── Render ──────────────────────────────────── */

  if (!summary) return <div className="loading">대시보드 로딩 중...</div>;

  return (
    <div>
      {/* ── Page Header ─────────────────────── */}
      <div
        className="page-header"
        style={{
          display: "flex",
          alignItems: "flex-start",
          justifyContent: "space-between",
        }}
      >
        <div>
          <h2>대시보드</h2>
          <div className="page-sub">모의투자 계좌 실시간 현황</div>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: "var(--text-muted)",
            }}
          >
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

      {/* ── KPI Cards ───────────────────────── */}
      <div className="kpi-grid">
        <div className="kpi-card">
          <div
            className="kpi-label"
            style={{ display: "flex", alignItems: "center", gap: 8 }}
          >
            총 평가 자산
            <span
              className={`badge ${summary.trading_enabled ? "profit" : "neutral"}`}
              style={{ fontSize: 10, padding: "2px 6px" }}
            >
              {summary.trading_enabled ? "매매 활성" : "매매 비활성"}
            </span>
          </div>
          <div
            className={`kpi-value ${pnlClass(String(Number(summary.total_equity) - Number(summary.initial_balance)))}`}
          >
            {formatKRW(summary.total_equity)}
          </div>
          <div
            className="kpi-sub"
            style={{ marginTop: 4, fontSize: 12, color: "var(--text-muted)" }}
          >
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

      {/* ── Equity Chart ────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>자산 추이</h3>
          <div className="period-switch">
            {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
              <button
                key={p}
                className={`period-btn${period === p ? " active" : ""}`}
                onClick={() => setPeriod(p)}
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

      {/* ── Position Table with Accordion ──── */}
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
                  <th style={{ textAlign: "right" }}>평단가</th>
                  <th style={{ textAlign: "right" }}>현재가</th>
                  <th style={{ textAlign: "right" }}>손익</th>
                  <th style={{ textAlign: "right" }}>수익률</th>
                  <th style={{ textAlign: "right" }}>수량</th>
                  <th style={{ textAlign: "right" }}>총 투자금</th>
                  <th style={{ textAlign: "right" }}>평가금액</th>
                  <th style={{ textAlign: "center" }}>상태</th>
                </tr>
              </thead>
              <tbody>
                {positions.map((pos) => (
                  <Fragment key={pos.market}>
                    <tr
                      onClick={() => handleRowClick(pos.market)}
                      style={{ cursor: "pointer" }}
                    >
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
                        {formatKRW(pos.avg_price)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {formatKRW(pos.current_price)}
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
                      <td style={{ textAlign: "right" }}>
                        {Number(pos.quantity)
                          .toFixed(8)
                          .replace(/0+$/, "")
                          .replace(/\.$/, "")}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {formatKRW(pos.total_invested)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {formatKRW(pos.eval_amount)}
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <div
                          style={{
                            display: "flex",
                            gap: 4,
                            justifyContent: "center",
                            flexWrap: "wrap",
                          }}
                        >
                          {pos.add_count > 0 && (
                            <span
                              className="badge info"
                              style={{ fontSize: 10, padding: "1px 5px" }}
                            >
                              +{pos.add_count}차
                            </span>
                          )}
                          {pos.partial_sold && (
                            <span
                              className="badge warn"
                              style={{ fontSize: 10, padding: "1px 5px" }}
                            >
                              부분익절
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                    {expandedMarket === pos.market && (
                      <tr>
                        <td
                          colSpan={9}
                          style={{
                            padding: 0,
                            background: "#0b1018",
                            borderBottom: "1px solid var(--border)",
                          }}
                        >
                          <div
                            ref={chartContainerRef}
                            style={{
                              width: "100%",
                              height: 360,
                              padding: "8px 0",
                            }}
                          />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Trade History ────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>거래 내역</h3>
          {history && (
            <span className="badge info">총 {history.total}건</span>
          )}
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {!history || history.items.length === 0 ? (
            <div className="empty-state">
              <div className="empty-icon">&#9671;</div>
              <div className="empty-text">거래 내역이 없습니다.</div>
            </div>
          ) : (
            <>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>체결 시간</th>
                    <th>코인</th>
                    <th style={{ textAlign: "center" }}>매매</th>
                    <th style={{ textAlign: "right" }}>체결 가격</th>
                    <th style={{ textAlign: "right" }}>수량</th>
                    <th style={{ textAlign: "right" }}>거래 금액</th>
                  </tr>
                </thead>
                <tbody>
                  {history.items.map((item) => (
                    <tr key={item.id}>
                      <td
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 12,
                          color: "var(--text-muted)",
                        }}
                      >
                        {new Date(item.filled_at).toLocaleString("ko-KR", {
                          month: "2-digit",
                          day: "2-digit",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td>
                        <div
                          style={{ fontWeight: 600, color: "var(--text)" }}
                        >
                          {item.korean_name}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: "var(--text-muted)",
                            marginTop: 2,
                          }}
                        >
                          {item.market}
                        </div>
                      </td>
                      <td style={{ textAlign: "center" }}>
                        <span
                          className={`badge ${item.side === "bid" ? "profit" : "loss"}`}
                          style={{ fontSize: 10, padding: "2px 8px" }}
                        >
                          {item.side === "bid" ? "매수" : "매도"}
                        </span>
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {formatKRW(item.price)}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {Number(item.quantity)
                          .toFixed(8)
                          .replace(/0+$/, "")
                          .replace(/\.$/, "")}
                      </td>
                      <td style={{ textAlign: "right" }}>
                        {formatKRW(item.total_amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>

              {/* Pagination */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: 12,
                  padding: "14px 16px",
                  borderTop: "1px solid var(--border)",
                }}
              >
                <button
                  className="btn btn-ghost"
                  style={{ padding: "5px 14px", fontSize: 12 }}
                  disabled={historyPage <= 1}
                  onClick={() => setHistoryPage((p) => p - 1)}
                >
                  이전
                </button>
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 12,
                    color: "var(--text-dim)",
                  }}
                >
                  {historyPage} / {totalHistoryPages}
                </span>
                <button
                  className="btn btn-ghost"
                  style={{ padding: "5px 14px", fontSize: 12 }}
                  disabled={historyPage >= totalHistoryPages}
                  onClick={() => setHistoryPage((p) => p + 1)}
                >
                  다음
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

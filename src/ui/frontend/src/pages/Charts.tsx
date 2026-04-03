import { useEffect, useState, useCallback, useRef } from "react";
import { useApi } from "../hooks/useApi";
import { createChart, CandlestickSeries, HistogramSeries, type IChartApi, type ISeriesApi, type CandlestickData, type HistogramData } from "lightweight-charts";

interface CandleData {
  timestamp: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

const formatPrice = (v: number) =>
  v >= 1000 ? v.toLocaleString("ko-KR") : v.toFixed(2);

export default function Charts() {
  const { get } = useApi();
  const [markets, setMarkets] = useState<{ market: string; korean_name: string }[]>([]);
  const [selected, setSelected] = useState("");
  const [loading, setLoading] = useState(false);
  const [lastPrice, setLastPrice] = useState<{ close: number; change: number; changePct: string } | null>(null);
  const [stats, setStats] = useState<{ high: number; low: number; avgVol: number; count: number } | null>(null);

  const chartContainerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Create chart once
  useEffect(() => {
    if (!chartContainerRef.current) return;

    const chart = createChart(chartContainerRef.current, {
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
        vertLine: { color: "#4499ff", width: 1, style: 2, labelBackgroundColor: "#1e2a3a" },
        horzLine: { color: "#4499ff", width: 1, style: 2, labelBackgroundColor: "#1e2a3a" },
      },
      rightPriceScale: {
        borderColor: "#1e2a3a",
        scaleMargins: { top: 0.1, bottom: 0.25 },
      },
      timeScale: {
        borderColor: "#1e2a3a",
        timeVisible: true,
        secondsVisible: false,
      },
    });

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
      priceScaleId: "",
    });
    volumeSeries.priceScale().applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    chartRef.current = chart;
    candleSeriesRef.current = candleSeries;
    volumeSeriesRef.current = volumeSeries;

    const handleResize = () => {
      if (chartContainerRef.current) {
        chart.applyOptions({ width: chartContainerRef.current.clientWidth });
      }
    };
    window.addEventListener("resize", handleResize);

    return () => {
      window.removeEventListener("resize", handleResize);
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, []);

  useEffect(() => {
    get<{ market: string; korean_name: string }[]>("/api/dashboard/markets").then((m) => {
      setMarkets(m);
      if (m.length > 0 && !selected) setSelected(m[0].market);
    });
  }, [get, selected]);

  const fetchCandles = useCallback(async (market: string) => {
    if (!market || !candleSeriesRef.current || !volumeSeriesRef.current) return;
    setLoading(true);

    const raw = await get<CandleData[]>(`/api/dashboard/candles?market=${market}&limit=100`);

    const candleData: CandlestickData[] = raw.map((c) => ({
      time: c.timestamp as CandlestickData["time"],
      open: Number(c.open),
      high: Number(c.high),
      low: Number(c.low),
      close: Number(c.close),
    }));

    const volumeData: HistogramData[] = raw.map((c) => ({
      time: c.timestamp as HistogramData["time"],
      value: Number(c.volume),
      color: Number(c.close) >= Number(c.open) ? "rgba(0,224,175,0.3)" : "rgba(255,68,102,0.3)",
    }));

    candleSeriesRef.current.setData(candleData);
    volumeSeriesRef.current.setData(volumeData);
    chartRef.current?.timeScale().fitContent();

    // Compute stats
    if (candleData.length > 0) {
      const last = candleData[candleData.length - 1];
      const prev = candleData.length > 1 ? candleData[candleData.length - 2] : null;
      const change = prev ? last.close - prev.close : 0;
      const pct = prev && prev.close ? ((change / prev.close) * 100).toFixed(2) : "0.00";
      setLastPrice({ close: last.close, change, changePct: pct });

      const high = Math.max(...candleData.map((c) => c.high));
      const low = Math.min(...candleData.map((c) => c.low));
      const avgVol = Math.round(volumeData.reduce((s, v) => s + v.value, 0) / volumeData.length);
      setStats({ high, low, avgVol, count: candleData.length });
    }

    setLoading(false);
  }, [get]);

  useEffect(() => {
    if (selected) fetchCandles(selected);
  }, [selected, fetchCandles]);

  // Auto-refresh every 60s
  useEffect(() => {
    if (!selected) return;
    const id = setInterval(() => fetchCandles(selected), 60_000);
    return () => clearInterval(id);
  }, [selected, fetchCandles]);

  return (
    <div>
      <div className="page-header">
        <h2>차트</h2>
        <div className="page-sub">스크리닝 마켓 분봉 차트</div>
      </div>

      {/* Market selector */}
      <div className="panel">
        <div className="panel-header">
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            <h3>마켓</h3>
            <select
              value={selected}
              onChange={(e) => setSelected(e.target.value)}
              style={{
                background: "var(--bg-raised)",
                color: "var(--text)",
                border: "1px solid var(--border-bright)",
                borderRadius: 6,
                padding: "6px 12px",
                fontFamily: "var(--font-mono)",
                fontSize: 13,
                cursor: "pointer",
                outline: "none",
              }}
            >
              {markets.map((m) => (
                <option key={m.market} value={m.market}>{m.korean_name} ({m.market.replace("KRW-", "")})</option>
              ))}
            </select>
            <button
              className="btn btn-ghost"
              onClick={() => fetchCandles(selected)}
              style={{ padding: "6px 14px", fontSize: 12 }}
            >
              새로고침
            </button>
          </div>
          {lastPrice && (
            <div style={{ display: "flex", alignItems: "center", gap: 12, fontFamily: "var(--font-mono)", fontSize: 13 }}>
              <span style={{ color: "var(--text)", fontWeight: 600 }}>
                {formatPrice(lastPrice.close)}
              </span>
              <span className={`badge ${lastPrice.change >= 0 ? "profit" : "loss"}`}>
                {lastPrice.change >= 0 ? "+" : ""}{lastPrice.changePct}%
              </span>
            </div>
          )}
        </div>

        <div className="panel-body" style={{ height: 400, position: "relative" }}>
          {loading && (
            <div className="loading" style={{ position: "absolute", top: "50%", left: "50%", transform: "translate(-50%, -50%)", zIndex: 10 }}>
              캔들 로딩 중...
            </div>
          )}
          <div ref={chartContainerRef} style={{ width: "100%", height: "100%" }} />
        </div>
      </div>

      {/* OHLCV summary */}
      {stats && (
        <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16 }}>
          <div className="kpi-card">
            <div className="kpi-label">고가</div>
            <div className="kpi-value" style={{ color: "var(--profit)", fontSize: 18 }}>
              {formatPrice(stats.high)}
            </div>
            <div className="kpi-sub">기간 최고가</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">저가</div>
            <div className="kpi-value" style={{ color: "var(--loss)", fontSize: 18 }}>
              {formatPrice(stats.low)}
            </div>
            <div className="kpi-sub">기간 최저가</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">평균 거래량</div>
            <div className="kpi-value" style={{ fontSize: 18 }}>
              {stats.avgVol.toLocaleString("ko-KR")}
            </div>
            <div className="kpi-sub">캔들당</div>
          </div>
          <div className="kpi-card">
            <div className="kpi-label">캔들 수</div>
            <div className="kpi-value" style={{ fontSize: 18 }}>
              {stats.count}
            </div>
            <div className="kpi-sub">로드됨</div>
          </div>
        </div>
      )}
    </div>
  );
}

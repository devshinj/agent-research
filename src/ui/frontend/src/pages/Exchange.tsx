import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type CandlestickData,
  type HistogramData,
} from "lightweight-charts";
import { useApi } from "../hooks/useApi";
import { useWebSocket } from "../hooks/useWebSocket";

/* ── Types ──────────────────────────────────────── */

interface MarketItem {
  market: string;
  korean_name: string;
  price: string;
  change: string;
  change_rate: string;
  acc_trade_price_24h: string;
  is_screened: boolean;
}

interface TickerWS {
  market: string;
  price: string;
  change: string;
  change_rate: string;
  change_price: string;
  volume_24h: string;
  acc_trade_price_24h: string;
  timestamp: number;
}

interface CandleRaw {
  timestamp: number;
  open: string;
  high: string;
  low: string;
  close: string;
  volume: string;
}

interface PositionInfo {
  market: string;
  entry_price: string;
  quantity: string;
  unrealized_pnl: string;
  add_count: number;
  total_invested: string;
  partial_sold: boolean;
  trade_mode: string;
  stop_loss_price: string | null;
  take_profit_price: string | null;
}

interface PortfolioPosition {
  market: string;
  quantity: string;
  avg_price: string;
  current_price: string;
  unrealized_pnl: string;
  pnl_pct: string;
  eval_amount: string;
  add_count: number;
  total_invested: string;
  partial_sold: boolean;
  trade_mode: string;
  stop_loss_price: string | null;
  take_profit_price: string | null;
}

interface SummaryData {
  cash_balance: string;
}

interface HistoryItem {
  id: number;
  filled_at: number;
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

interface OrderResult {
  success: boolean;
  error?: string;
  order?: {
    id: string;
    market: string;
    side: string;
    price: string;
    quantity: string;
    fee: string;
    reason: string;
  };
  position?: PositionInfo | null;
}

type Timeframe = 1 | 5 | 15 | 60 | 240;
type DailyTf = "1D";
const TIMEFRAMES: { label: string; value: Timeframe | DailyTf }[] = [
  { label: "1분", value: 1 },
  { label: "5분", value: 5 },
  { label: "15분", value: 15 },
  { label: "1시간", value: 60 },
  { label: "4시간", value: 240 },
  { label: "일봉", value: "1D" },
];

/* ── Helpers ────────────────────────────────────── */

function formatKRW(val: string | number): string {
  const n = typeof val === "string" ? Number(val) : val;
  if (n === 0) return "₩0";
  if (n >= 1_000_000_000_000) return `₩${(n / 1_000_000_000_000).toFixed(1)}조`;
  if (n >= 100_000_000) return `₩${(n / 100_000_000).toFixed(0)}억`;
  if (n >= 10_000) return `₩${(n / 10_000).toFixed(0)}만`;
  return `₩${n.toLocaleString("ko-KR")}`;
}

function formatPrice(val: string): string {
  const n = Number(val);
  if (n >= 1000) return n.toLocaleString("ko-KR");
  if (n >= 1) return n.toFixed(2);
  return n.toFixed(4);
}

function formatPct(val: string): string {
  const n = Number(val) * 100;
  return `${n >= 0 ? "+" : ""}${n.toFixed(2)}%`;
}

function pnlClass(val: string | number): string {
  const n = typeof val === "string" ? Number(val) : val;
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "";
}

function changeClass(change: string): string {
  if (change === "RISE" || change === "EVEN") return "positive";
  if (change === "FALL") return "negative";
  const n = Number(change);
  if (n > 0) return "positive";
  if (n < 0) return "negative";
  return "";
}

/* ── MarketRow ──────────────────────────────────── */

function MarketRow({
  item,
  selected,
  onClick,
  flash,
}: {
  item: MarketItem;
  selected: boolean;
  onClick: () => void;
  flash: string;
}) {
  const cls = changeClass(item.change);
  return (
    <div
      className={`exchange-market-row${selected ? " selected" : ""}${item.is_screened ? " exchange-screened-row" : ""} ${flash}`}
      onClick={onClick}
    >
      <div className="market-name">
        <span className="market-korean">{item.korean_name}</span>
        <span className="market-ticker">{item.market}</span>
      </div>
      <div className="market-data">
        <span className={`market-price ${cls}`}>{formatPrice(item.price)}</span>
        <span className={`market-change ${cls}`}>{formatPct(item.change_rate)}</span>
        <span className="market-volume">{formatKRW(item.acc_trade_price_24h)}</span>
      </div>
    </div>
  );
}

/* ── RecentTrades ───────────────────────────────── */

function RecentTrades({ market, get }: { market: string; get: <T>(path: string) => Promise<T> }) {
  const [trades, setTrades] = useState<HistoryItem[]>([]);

  useEffect(() => {
    get<HistoryResponse>("/api/portfolio/history?page=1&size=50").then((res) => {
      setTrades(res.items.filter((t) => t.market === market));
    });
  }, [market, get]);

  if (trades.length === 0) return null;

  return (
    <div className="recent-trades-section">
      <h4>최근 거래</h4>
      <table className="table">
        <thead>
          <tr>
            <th>시간</th>
            <th>구분</th>
            <th>가격</th>
            <th>수량</th>
            <th>금액</th>
          </tr>
        </thead>
        <tbody>
          {trades.slice(0, 10).map((t) => (
            <tr key={t.id}>
              <td>{new Date(t.filled_at).toLocaleString("ko-KR", { hour: "2-digit", minute: "2-digit" })}</td>
              <td className={t.side === "BUY" ? "positive" : "negative"}>
                {t.side === "BUY" ? "매수" : "매도"}
              </td>
              <td>{formatPrice(t.price)}</td>
              <td>{Number(t.quantity).toFixed(6)}</td>
              <td>{formatKRW(t.total_amount)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ── OrderPanel ─────────────────────────────────── */

function OrderPanel({
  market,
  price,
  position,
  cashBalance,
}: {
  market: string;
  price: string;
  position: PositionInfo | null;
  cashBalance: string;
}) {
  const { postJson, patchJson, get } = useApi();
  const [tab, setTab] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [result, setResult] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [slPrice, setSlPrice] = useState("");
  const [tpPrice, setTpPrice] = useState("");

  useEffect(() => {
    if (position) {
      setSlPrice(position.stop_loss_price ?? "");
      setTpPrice(position.take_profit_price ?? "");
    } else {
      setSlPrice("");
      setTpPrice("");
    }
  }, [position]);

  const showResult = (type: "success" | "error", msg: string) => {
    setResult({ type, msg });
    setTimeout(() => setResult(null), 4000);
  };

  const handleBuy = async () => {
    if (!amount || Number(amount) <= 0) return;
    try {
      const res = await postJson<OrderResult>("/api/exchange/buy", {
        market,
        amount_krw: amount,
      });
      if (res.success) {
        showResult("success", `매수 완료 — ${Number(res.order!.quantity).toFixed(6)} @ ₩${formatPrice(res.order!.price)}`);
        setAmount("");
      } else {
        showResult("error", res.error ?? "매수 실패");
      }
    } catch {
      showResult("error", "요청 실패");
    }
  };

  const handleSell = async (fraction: string) => {
    try {
      const res = await postJson<OrderResult>("/api/exchange/sell", {
        market,
        fraction,
      });
      if (res.success) {
        showResult("success", `매도 완료 — ${Number(res.order!.quantity).toFixed(6)} @ ₩${formatPrice(res.order!.price)}`);
      } else {
        showResult("error", res.error ?? "매도 실패");
      }
    } catch {
      showResult("error", "요청 실패");
    }
  };

  const handleSaveExitOrders = async () => {
    try {
      await patchJson(`/api/exchange/position/${market}/exit-orders`, {
        stop_loss_price: slPrice || null,
        take_profit_price: tpPrice || null,
      });
      showResult("success", "손절/익절 설정 완료");
    } catch {
      showResult("error", "설정 실패");
    }
  };

  const setPreset = (pct: number) => {
    const cash = Number(cashBalance);
    setAmount(String(Math.floor(cash * pct)));
  };

  const estimatedQty = Number(amount) > 0 && Number(price) > 0
    ? (Number(amount) / Number(price)).toFixed(8)
    : "0";

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="tab-group">
          <button className={`tab-btn${tab === "buy" ? " active" : ""}`} onClick={() => setTab("buy")}>
            매수
          </button>
          <button className={`tab-btn${tab === "sell" ? " active" : ""}`} onClick={() => setTab("sell")}>
            매도
          </button>
        </div>
      </div>
      <div className="panel-body" style={{ padding: "16px" }}>
        {tab === "buy" ? (
          <div className="order-form">
            <div className="order-info-row">
              <span className="order-label">보유 현금</span>
              <span className="order-value">{formatKRW(cashBalance)}</span>
            </div>
            <div className="order-info-row">
              <span className="order-label">현재가</span>
              <span className="order-value">{formatPrice(price)}</span>
            </div>
            <input
              className="order-input"
              type="number"
              placeholder="투자 금액 (KRW)"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
            <div className="order-presets">
              <button className="btn btn-ghost" onClick={() => setPreset(0.25)}>25%</button>
              <button className="btn btn-ghost" onClick={() => setPreset(0.50)}>50%</button>
              <button className="btn btn-ghost" onClick={() => setPreset(0.75)}>75%</button>
              <button className="btn btn-ghost" onClick={() => setPreset(1.00)}>100%</button>
            </div>
            <div className="order-info-row">
              <span className="order-label">예상 수량</span>
              <span className="order-value">{estimatedQty}</span>
            </div>
            <button className="btn btn-accent order-submit" onClick={handleBuy}>
              매수 주문
            </button>
          </div>
        ) : (
          <div className="order-form">
            {position ? (
              <>
                <div className="order-info-row">
                  <span className="order-label">보유 수량</span>
                  <span className="order-value">{Number(position.quantity).toFixed(6)}</span>
                </div>
                <div className="order-info-row">
                  <span className="order-label">평균 매수가</span>
                  <span className="order-value">{formatPrice(position.entry_price)}</span>
                </div>
                <div className="order-info-row">
                  <span className="order-label">미실현 손익</span>
                  <span className={`order-value ${pnlClass(position.unrealized_pnl)}`}>
                    {formatKRW(position.unrealized_pnl)}
                  </span>
                </div>
                <div className="order-presets">
                  <button className="btn btn-ghost" onClick={() => handleSell("0.25")}>25%</button>
                  <button className="btn btn-ghost" onClick={() => handleSell("0.50")}>50%</button>
                  <button className="btn btn-ghost" onClick={() => handleSell("0.75")}>75%</button>
                  <button className="btn btn-sell" onClick={() => handleSell("1")}>전량</button>
                </div>

                <div className="exit-orders-section">
                  <h4>손절 / 익절 설정</h4>
                  <div className="order-info-row">
                    <span className="order-label">손절가</span>
                    <input
                      className="order-input-sm"
                      type="number"
                      placeholder="미설정"
                      value={slPrice}
                      onChange={(e) => setSlPrice(e.target.value)}
                    />
                  </div>
                  <div className="order-info-row">
                    <span className="order-label">익절가</span>
                    <input
                      className="order-input-sm"
                      type="number"
                      placeholder="미설정"
                      value={tpPrice}
                      onChange={(e) => setTpPrice(e.target.value)}
                    />
                  </div>
                  <button className="btn btn-accent" onClick={handleSaveExitOrders} style={{ marginTop: 8, width: "100%" }}>
                    저장
                  </button>
                </div>
              </>
            ) : (
              <p style={{ color: "var(--text-dim)", textAlign: "center", padding: "20px 0" }}>
                보유 중인 포지션이 없습니다
              </p>
            )}
          </div>
        )}

        {result && (
          <div className={`order-result ${result.type}`}>
            {result.msg}
          </div>
        )}

        <RecentTrades market={market} get={get} />
      </div>
    </div>
  );
}

/* ── ExchangeDetail ─────────────────────────────── */

function ExchangeDetail({
  market,
  koreanName,
  ticker,
}: {
  market: string;
  koreanName: string;
  ticker: MarketItem | null;
}) {
  const { get } = useApi();
  const [tf, setTf] = useState<Timeframe | DailyTf>(15);
  const [position, setPosition] = useState<PositionInfo | null>(null);
  const [cashBalance, setCashBalance] = useState("0");

  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);

  // Fetch position & cash
  useEffect(() => {
    get<SummaryData>("/api/dashboard/summary").then((s) => setCashBalance(s.cash_balance));
    get<PortfolioPosition[]>("/api/portfolio/positions").then((positions) => {
      const pos = positions.find((p) => p.market === market);
      if (pos) {
        setPosition({
          market: pos.market,
          entry_price: pos.avg_price,
          quantity: pos.quantity,
          unrealized_pnl: pos.unrealized_pnl,
          add_count: pos.add_count ?? 0,
          total_invested: pos.total_invested ?? pos.eval_amount,
          partial_sold: pos.partial_sold ?? false,
          trade_mode: pos.trade_mode ?? "AUTO",
          stop_loss_price: pos.stop_loss_price ?? null,
          take_profit_price: pos.take_profit_price ?? null,
        });
      } else {
        setPosition(null);
      }
    });
  }, [market, get]);

  // Chart setup
  useEffect(() => {
    const container = chartContainerRef.current;
    if (!container) return;

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 420,
      layout: {
        background: { color: "#0b0f16" },
        textColor: "#7a8ba3",
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

    chartRef.current = chart;

    const cs = chart.addSeries(CandlestickSeries, {
      upColor: "#00e0af",
      downColor: "#ff4466",
      borderUpColor: "#00e0af",
      borderDownColor: "#ff4466",
      wickUpColor: "#00e0af",
      wickDownColor: "#ff4466",
    });
    candleSeriesRef.current = cs;

    const vs = chart.addSeries(HistogramSeries, {
      priceFormat: { type: "volume" },
      priceScaleId: "volume",
    });
    volumeSeriesRef.current = vs;

    chart.priceScale("volume").applyOptions({
      scaleMargins: { top: 0.8, bottom: 0 },
    });

    const handleResize = () => {
      chart.applyOptions({ width: container.clientWidth });
    };
    const resizeObserver = new ResizeObserver(handleResize);
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      candleSeriesRef.current = null;
      volumeSeriesRef.current = null;
    };
  }, [market]);

  // Load candle data when market or timeframe changes
  useEffect(() => {
    const tfParam = tf === "1D" ? "1D" : String(tf);
    get<CandleRaw[]>(`/api/dashboard/candles?market=${market}&limit=200&timeframe=${tfParam}`).then(
      (candles) => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;

        const candleData: CandlestickData[] = candles.map((c) => ({
          time: (c.timestamp / 1000) as unknown as CandlestickData["time"],
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));

        const volumeData: HistogramData[] = candles.map((c) => ({
          time: (c.timestamp / 1000) as unknown as HistogramData["time"],
          value: Number(c.volume),
          color:
            Number(c.close) >= Number(c.open)
              ? "rgba(0, 224, 175, 0.3)"
              : "rgba(255, 68, 102, 0.3)",
        }));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volumeData);

        // Position overlay lines
        if (position) {
          const markers: { price: number; color: string; title: string }[] = [
            { price: Number(position.entry_price), color: "#3b82f6", title: "매수가" },
          ];
          if (position.stop_loss_price) {
            markers.push({ price: Number(position.stop_loss_price), color: "#ff4466", title: "손절" });
          }
          if (position.take_profit_price) {
            markers.push({ price: Number(position.take_profit_price), color: "#00e0af", title: "익절" });
          }
          markers.forEach((m) => {
            candleSeriesRef.current!.createPriceLine({
              price: m.price,
              color: m.color,
              lineWidth: 1,
              lineStyle: 2,
              axisLabelVisible: true,
              title: m.title,
            });
          });
        }

        chartRef.current?.timeScale().fitContent();
      }
    );
  }, [market, tf, get, position]);

  const curPrice = ticker?.price ?? "0";
  const curChange = ticker?.change ?? "EVEN";
  const curChangeRate = ticker?.change_rate ?? "0";
  const cls = changeClass(curChange);

  return (
    <div className="exchange-right">
      {/* Header */}
      <div className="panel">
        <div className="panel-body" style={{ padding: "20px 24px" }}>
          <h2 style={{ margin: 0, fontSize: "1.1rem", marginBottom: 8 }}>
            {koreanName} <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>{market}</span>
          </h2>
          <div className="exchange-detail-price">
            <span className={`detail-price ${cls}`}>₩{formatPrice(curPrice)}</span>
            <span className={`detail-change ${cls}`}>{formatPct(curChangeRate)}</span>
          </div>

          {/* Timeframe selector */}
          <div className="tab-group" style={{ marginBottom: 12 }}>
            {TIMEFRAMES.map((t) => (
              <button
                key={t.value}
                className={`tab-btn${tf === t.value ? " active" : ""}`}
                onClick={() => setTf(t.value)}
              >
                {t.label}
              </button>
            ))}
          </div>

          {/* Chart */}
          <div ref={chartContainerRef} style={{ width: "100%", borderRadius: 8, overflow: "hidden" }} />
        </div>
      </div>

      {/* Order Panel */}
      <div style={{ marginTop: 16 }}>
        <OrderPanel market={market} price={curPrice} position={position} cashBalance={cashBalance} />
      </div>
    </div>
  );
}

/* ── Main Exchange Component ────────────────────── */

export default function Exchange() {
  const { get } = useApi();
  const { lastMessage } = useWebSocket("ws://localhost:8000/ws/live");
  const [markets, setMarkets] = useState<MarketItem[]>([]);
  const [search, setSearch] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);
  const [flashes, setFlashes] = useState<Record<string, string>>({});
  const prevPrices = useRef<Record<string, string>>({});

  // Fetch markets
  const fetchMarkets = useCallback(() => {
    get<MarketItem[]>("/api/exchange/markets").then(setMarkets);
  }, [get]);

  useEffect(() => {
    fetchMarkets();
    const id = setInterval(fetchMarkets, 30_000);
    return () => clearInterval(id);
  }, [fetchMarkets]);

  // WebSocket ticker updates
  useEffect(() => {
    if (!lastMessage || lastMessage.type !== "ticker") return;
    const t = lastMessage.data as unknown as TickerWS;
    if (!t.market) return;

    setMarkets((prev) =>
      prev.map((m) =>
        m.market === t.market
          ? {
              ...m,
              price: t.price,
              change: t.change,
              change_rate: t.change_rate,
              acc_trade_price_24h: t.acc_trade_price_24h,
            }
          : m
      )
    );

    // Flash animation
    const oldPrice = prevPrices.current[t.market];
    if (oldPrice && oldPrice !== t.price) {
      const direction = Number(t.price) > Number(oldPrice) ? "flash-up" : "flash-down";
      setFlashes((prev) => ({ ...prev, [t.market]: direction }));
      setTimeout(() => {
        setFlashes((prev) => {
          const next = { ...prev };
          delete next[t.market];
          return next;
        });
      }, 500);
    }
    prevPrices.current[t.market] = t.price;
  }, [lastMessage]);

  // Filter & group markets
  const filtered = useMemo(() => {
    if (!search) return markets;
    const q = search.toLowerCase();
    return markets.filter(
      (m) =>
        m.korean_name.toLowerCase().includes(q) ||
        m.market.toLowerCase().includes(q)
    );
  }, [markets, search]);

  const screened = useMemo(() => filtered.filter((m) => m.is_screened), [filtered]);
  const all = useMemo(() => filtered.filter((m) => !m.is_screened), [filtered]);

  const selectedItem = markets.find((m) => m.market === selectedMarket) ?? null;

  return (
    <div className="exchange-layout">
      {/* Left Panel — Market List */}
      <div className="exchange-left">
        <div className="panel">
          <div className="panel-header">
            <h3>마켓</h3>
          </div>
          <div className="panel-body">
            <div className="exchange-search">
              <input
                placeholder="코인 검색..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="exchange-market-list">
              {screened.length > 0 && (
                <>
                  <div className="exchange-section-label screened-section">스크리닝 통과 ({screened.length})</div>
                  {screened.map((m) => (
                    <MarketRow
                      key={m.market}
                      item={m}
                      selected={selectedMarket === m.market}
                      onClick={() => setSelectedMarket(m.market)}
                      flash={flashes[m.market] ?? ""}
                    />
                  ))}
                  <div className="exchange-screened-divider" />
                </>
              )}
              <div className="exchange-section-label">전체</div>
              {all.map((m) => (
                <MarketRow
                  key={m.market}
                  item={m}
                  selected={selectedMarket === m.market}
                  onClick={() => setSelectedMarket(m.market)}
                  flash={flashes[m.market] ?? ""}
                />
              ))}
              {filtered.length === 0 && (
                <p style={{ textAlign: "center", color: "var(--text-muted)", padding: 20 }}>
                  검색 결과 없음
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Right Panel — Detail */}
      {selectedMarket && selectedItem ? (
        <ExchangeDetail
          market={selectedMarket}
          koreanName={selectedItem.korean_name}
          ticker={selectedItem}
        />
      ) : (
        <div className="exchange-right" style={{ display: "flex", alignItems: "center", justifyContent: "center" }}>
          <p style={{ color: "var(--text-muted)", fontSize: "1.1rem" }}>
            마켓을 선택하세요
          </p>
        </div>
      )}
    </div>
  );
}

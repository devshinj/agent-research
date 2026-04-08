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
import Markdown from "react-markdown";
import { useAuthContext } from "../context/AuthContext";
import { useWebSocket } from "../hooks/useWebSocket";

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

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

/* ── Sort types ─────────────────────────────────── */

type SortKey = "name" | "price" | "change" | "volume";
type SortDir = "asc" | "desc";
type MarketFilter = "all" | "screened" | "holding";

function sortMarkets(
  items: MarketItem[],
  key: SortKey,
  dir: SortDir,
  filter: MarketFilter,
  holdingMarkets: Set<string>,
): MarketItem[] {
  let list = [...items];

  if (filter === "screened") {
    list = list.filter((m) => m.is_screened);
  } else if (filter === "holding") {
    list = list.filter((m) => holdingMarkets.has(m.market));
  }

  list.sort((a, b) => {
    switch (key) {
      case "name":
        return a.korean_name.localeCompare(b.korean_name, "ko");
      case "price":
        return Number(a.price) - Number(b.price);
      case "change":
        return Number(a.change_rate) - Number(b.change_rate);
      case "volume":
        return Number(a.acc_trade_price_24h) - Number(b.acc_trade_price_24h);
      default:
        return 0;
    }
  });
  return dir === "desc" ? list.reverse() : list;
}

/* ── MarketRow ──────────────────────────────────── */

function MarketRow({
  item,
  selected,
  onClick,
  flash,
  holding,
}: {
  item: MarketItem;
  selected: boolean;
  onClick: () => void;
  flash: string;
  holding: boolean;
}) {
  const changeNum = Number(item.change_rate);
  const cls = changeNum > 0 ? "positive" : changeNum < 0 ? "negative" : "";
  return (
    <div
      className={`market-row${selected ? " selected" : ""}${holding ? " holding" : ""} ${flash}`}
      onClick={onClick}
    >
      <div className="market-col-name">
        <span className="market-korean">
          {item.korean_name}
          {holding && <span className="holding-dot" />}
          {item.is_screened && <span className="screened-badge">AI</span>}
        </span>
        <span className="market-ticker">{item.market.replace("KRW-", "")}</span>
      </div>
      <div className="market-col-price">
        <span className={`market-price ${cls}`}>{formatPrice(item.price)}</span>
      </div>
      <div className="market-col-change">
        <span className={`market-change ${cls}`}>{formatPct(item.change_rate)}</span>
      </div>
      <div className="market-col-volume">
        <span className="market-volume">{formatKRW(item.acc_trade_price_24h)}</span>
      </div>
    </div>
  );
}

/* ── RecentTrades ───────────────────────────────── */

function RecentTrades({ market, get, refreshKey }: { market: string; get: <T>(path: string) => Promise<T>; refreshKey: number }) {
  const [trades, setTrades] = useState<HistoryItem[]>([]);

  useEffect(() => {
    get<HistoryResponse>("/api/portfolio/history?page=1&size=50").then((res) => {
      setTrades(res.items.filter((t) => t.market === market));
    });
  }, [market, get, refreshKey]);

  if (trades.length === 0) return null;

  return (
    <div className="recent-trades-section">
      <h4>최근 거래</h4>
      <div className="recent-trades-list">
        {trades.slice(0, 10).map((t) => {
          const isBuy = t.side === "BUY";
          return (
            <div key={t.id} className={`recent-trade-item ${isBuy ? "buy" : "sell"}`}>
              <div className="recent-trade-left">
                <span className={`recent-trade-side ${isBuy ? "positive" : "negative"}`}>
                  {isBuy ? "매수" : "매도"}
                </span>
                <span className="recent-trade-time">
                  {new Date(Number(t.filled_at) * 1000).toLocaleString("ko-KR", {
                    month: "2-digit",
                    day: "2-digit",
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </span>
              </div>
              <div className="recent-trade-right">
                <span className="recent-trade-price">₩{formatPrice(t.price)}</span>
                <span className="recent-trade-detail">
                  {Number(t.quantity).toFixed(6)} · {formatKRW(t.total_amount)}
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ── OrderConfirmModal ──────────────────────────── */

interface ConfirmInfo {
  side: "buy" | "sell";
  market: string;
  price: string;
  quantity: string;
  amount: string;
  fraction?: string;
}

function OrderConfirmModal({
  info,
  onConfirm,
  onCancel,
}: {
  info: ConfirmInfo;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const isBuy = info.side === "buy";
  return (
    <div className="order-confirm-overlay" onClick={onCancel}>
      <div className="order-confirm-modal" onClick={(e) => e.stopPropagation()}>
        <h3 className={`order-confirm-title ${isBuy ? "positive" : "negative"}`}>
          {isBuy ? "매수" : "매도"} 주문 확인
        </h3>
        <div className="order-confirm-body">
          <div className="order-confirm-row">
            <span className="order-confirm-label">마켓</span>
            <span className="order-confirm-value">{info.market}</span>
          </div>
          <div className="order-confirm-row">
            <span className="order-confirm-label">현재가</span>
            <span className="order-confirm-value">₩{formatPrice(info.price)}</span>
          </div>
          {isBuy ? (
            <>
              <div className="order-confirm-row">
                <span className="order-confirm-label">투자 금액</span>
                <span className="order-confirm-value">₩{Number(info.amount).toLocaleString("ko-KR")}</span>
              </div>
              <div className="order-confirm-row">
                <span className="order-confirm-label">예상 수량</span>
                <span className="order-confirm-value">{info.quantity}</span>
              </div>
            </>
          ) : (
            <>
              <div className="order-confirm-row">
                <span className="order-confirm-label">매도 비율</span>
                <span className="order-confirm-value">
                  {info.fraction === "1" ? "전량" : `${Number(info.fraction) * 100}%`}
                </span>
              </div>
              <div className="order-confirm-row">
                <span className="order-confirm-label">매도 수량</span>
                <span className="order-confirm-value">{info.quantity}</span>
              </div>
              <div className="order-confirm-row">
                <span className="order-confirm-label">예상 금액</span>
                <span className="order-confirm-value">₩{Number(info.amount).toLocaleString("ko-KR")}</span>
              </div>
            </>
          )}
        </div>
        <div className="order-confirm-actions">
          <button className="btn btn-ghost order-confirm-cancel" onClick={onCancel}>
            취소
          </button>
          <button
            className={`btn order-confirm-submit ${isBuy ? "btn-accent" : "btn-sell"}`}
            onClick={onConfirm}
          >
            {isBuy ? "매수 확인" : "매도 확인"}
          </button>
        </div>
      </div>
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
  const { api } = useAuthContext();
  const { postJson, patchJson, get } = api;
  const [tab, setTab] = useState<"buy" | "sell">("buy");
  const [amount, setAmount] = useState("");
  const [result, setResult] = useState<{ type: "success" | "error"; msg: string } | null>(null);
  const [slPrice, setSlPrice] = useState("");
  const [tpPrice, setTpPrice] = useState("");
  const [confirm, setConfirm] = useState<ConfirmInfo | null>(null);
  const [tradesRefresh, setTradesRefresh] = useState(0);
  const [feeRate, setFeeRate] = useState<number | null>(null);
  const [slippageRate, setSlippageRate] = useState<number | null>(null);
  const [maxBuyAmount, setMaxBuyAmount] = useState<number | null>(null);

  // Fetch fee/slippage info
  useEffect(() => {
    get<{ amount: string; fee_rate?: string; slippage_rate?: string }>("/api/exchange/max-buy-amount").then((res) => {
      setMaxBuyAmount(Number(res.amount) || 0);
      if (res.fee_rate != null) setFeeRate(Number(res.fee_rate));
      if (res.slippage_rate != null) setSlippageRate(Number(res.slippage_rate));
    });
  }, [get, cashBalance]);

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

  const executeBuy = async () => {
    if (!amount || Number(amount) <= 0) return;
    setConfirm(null);
    try {
      const res = await postJson<OrderResult>("/api/exchange/buy", {
        market,
        amount_krw: amount,
      });
      if (res.success) {
        showResult("success", `매수 완료 — ${Number(res.order!.quantity).toFixed(6)} @ ₩${formatPrice(res.order!.price)}`);
        setAmount("");
        setTradesRefresh((n) => n + 1);
      } else {
        showResult("error", res.error ?? "매수 실패");
      }
    } catch {
      showResult("error", "요청 실패");
    }
  };

  const executeSell = async (fraction: string) => {
    setConfirm(null);
    try {
      const res = await postJson<OrderResult>("/api/exchange/sell", {
        market,
        fraction,
      });
      if (res.success) {
        showResult("success", `매도 완료 — ${Number(res.order!.quantity).toFixed(6)} @ ₩${formatPrice(res.order!.price)}`);
        setTradesRefresh((n) => n + 1);
      } else {
        showResult("error", res.error ?? "매도 실패");
      }
    } catch {
      showResult("error", "요청 실패");
    }
  };

  const handleBuy = () => {
    if (!amount || Number(amount) <= 0) return;
    const qty = (Number(amount) / Number(price)).toFixed(8);
    setConfirm({
      side: "buy",
      market,
      price,
      quantity: qty,
      amount,
    });
  };

  const handleSell = (fraction: string) => {
    if (!position) return;
    const qty = (Number(position.quantity) * Number(fraction)).toFixed(6);
    const est = Math.round(Number(qty) * Number(price));
    setConfirm({
      side: "sell",
      market,
      price,
      quantity: qty,
      amount: String(est),
      fraction,
    });
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

  const setPreset = async (pct: number) => {
    if (pct >= 1) {
      // 전량 매수: 서버에서 수수료/슬리피지 고려한 최대 금액 조회
      try {
        const res = await get<{ amount: string }>("/api/exchange/max-buy-amount");
        setAmount(res.amount);
      } catch {
        const cash = Number(cashBalance);
        setAmount(String(Math.floor(cash)));
      }
    } else {
      // 부분 매수: safe amount 기준으로 비율 적용
      try {
        const res = await get<{ amount: string }>("/api/exchange/max-buy-amount");
        setAmount(String(Math.floor(Number(res.amount) * pct)));
      } catch {
        const cash = Number(cashBalance);
        setAmount(String(Math.floor(cash * pct)));
      }
    }
  };

  const amountNum = Number(amount);
  const estimatedQty = amountNum > 0 && Number(price) > 0
    ? (amountNum / Number(price)).toFixed(8)
    : "0";
  const hasFeeInfo = feeRate != null && slippageRate != null;
  const estimatedFee = amountNum > 0 && feeRate != null ? Math.ceil(amountNum * feeRate) : 0;
  const estimatedSlippage = amountNum > 0 && slippageRate != null ? Math.ceil(amountNum * slippageRate) : 0;
  const totalCost = amountNum + estimatedFee + estimatedSlippage;
  const exceedsCash = amountNum > 0 && maxBuyAmount != null && amountNum > maxBuyAmount;

  return (
    <div className="panel">
      <div className="panel-header">
        <div className="order-tab-group">
          <button className={`order-tab-btn buy${tab === "buy" ? " active" : ""}`} onClick={() => setTab("buy")}>
            매수
          </button>
          <button className={`order-tab-btn sell${tab === "sell" ? " active" : ""}`} onClick={() => setTab("sell")}>
            매도
          </button>
        </div>
      </div>
      <div className="panel-body" style={{ padding: "16px" }}>
        {tab === "buy" ? (
          <div className="order-form">
            <div className="order-info-row">
              <span className="order-label">보유 현금</span>
              <span className="order-value">₩{Number(cashBalance).toLocaleString("ko-KR")}</span>
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
              <button className="btn btn-buy-light" onClick={() => setPreset(0.25)}>25%</button>
              <button className="btn btn-buy-light" onClick={() => setPreset(0.50)}>50%</button>
              <button className="btn btn-buy-light" onClick={() => setPreset(0.75)}>75%</button>
              <button className="btn btn-buy-light" onClick={() => setPreset(1.00)}>100%</button>
            </div>
            <div className="order-info-row">
              <span className="order-label">예상 수량</span>
              <span className="order-value">{estimatedQty}</span>
            </div>
            {amountNum > 0 && hasFeeInfo && (
              <div className="order-fee-info">
                <div className="order-info-row">
                  <span className="order-label">수수료 ({(feeRate! * 100).toFixed(2)}%)</span>
                  <span className="order-value">₩{estimatedFee.toLocaleString("ko-KR")}</span>
                </div>
                <div className="order-info-row">
                  <span className="order-label">슬리피지 ({(slippageRate! * 100).toFixed(2)}%)</span>
                  <span className="order-value">₩{estimatedSlippage.toLocaleString("ko-KR")}</span>
                </div>
                <div className="order-info-row" style={{ fontWeight: 600 }}>
                  <span className="order-label">총 예상 비용</span>
                  <span className="order-value">₩{totalCost.toLocaleString("ko-KR")}</span>
                </div>
              </div>
            )}
            {exceedsCash && (
              <div className="order-warning">
                잔고가 부족합니다. 수수료·슬리피지 포함 최대 ₩{maxBuyAmount!.toLocaleString("ko-KR")}까지 매수할 수 있습니다.
              </div>
            )}
            <button className="btn btn-accent order-submit" onClick={handleBuy} disabled={exceedsCash || amountNum <= 0}>
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
                  <button className="btn btn-sell-light" onClick={() => handleSell("0.25")}>25%</button>
                  <button className="btn btn-sell-light" onClick={() => handleSell("0.50")}>50%</button>
                  <button className="btn btn-sell-light" onClick={() => handleSell("0.75")}>75%</button>
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

        {confirm && (
          <OrderConfirmModal
            info={confirm}
            onConfirm={() =>
              confirm.side === "buy"
                ? executeBuy()
                : executeSell(confirm.fraction!)
            }
            onCancel={() => setConfirm(null)}
          />
        )}

        {result && (
          <div className={`order-result ${result.type}`}>
            {result.msg}
          </div>
        )}

        <RecentTrades market={market} get={get} refreshKey={tradesRefresh} />
      </div>
    </div>
  );
}

/* ── AgentChat ─────────────────────────────────── */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  sources?: { title: string; url: string }[];
}

function AgentChat({ market, accessToken }: { market: string; accessToken: string | null }) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [isCollapsed, setIsCollapsed] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const prevMarketRef = useRef(market);

  const API_BASE = import.meta.env.VITE_API_URL || "";

  // Reset messages when market changes
  useEffect(() => {
    if (prevMarketRef.current !== market) {
      setMessages([]);
      setInput("");
      prevMarketRef.current = market;
    }
  }, [market]);

  // Auto-scroll to bottom
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const sendMessage = useCallback(async (text: string) => {
    if (!text.trim() || isStreaming || !accessToken) return;

    const userMsg: ChatMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsStreaming(true);

    // Build history from existing messages (last 20 turns)
    const history = [...messages, userMsg]
      .slice(-40)
      .map((m) => ({ role: m.role, content: m.content }));

    // Add placeholder assistant message
    setMessages((prev) => [...prev, { role: "assistant", content: "" }]);

    try {
      const res = await fetch(`${API_BASE}/api/agent/chat`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${accessToken}`,
        },
        body: JSON.stringify({ market, message: text, history: history.slice(0, -1) }),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "요청 실패" }));
        setMessages((prev) => {
          const updated = [...prev];
          updated[updated.length - 1] = {
            role: "assistant",
            content: `오류: ${err.detail || "AI 응답을 받지 못했습니다."}`,
          };
          return updated;
        });
        setIsStreaming(false);
        return;
      }

      const reader = res.body?.getReader();
      if (!reader) { setIsStreaming(false); return; }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() || "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data: ")) continue;
          const payload = trimmed.slice(6);

          if (payload === "[DONE]") continue;

          try {
            const data = JSON.parse(payload);
            if (data.token) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + data.token };
                return updated;
              });
            }
            if (data.grounding_sources) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, sources: data.grounding_sources };
                return updated;
              });
            }
            if (data.error) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                updated[updated.length - 1] = { ...last, content: last.content + `\n\n${data.error}` };
                return updated;
              });
            }
          } catch {
            // skip malformed JSON
          }
        }
      }
    } catch {
      setMessages((prev) => {
        const updated = [...prev];
        updated[updated.length - 1] = {
          role: "assistant",
          content: "네트워크 오류가 발생했습니다.",
        };
        return updated;
      });
    } finally {
      setIsStreaming(false);
    }
  }, [isStreaming, accessToken, messages, market, API_BASE]);

  const handleAnalyze = () => {
    sendMessage("이 코인의 현재 트렌드, 전망, 커뮤니티 여론을 분석하고 매매 추천을 해주세요.");
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    sendMessage(input);
  };

  return (
    <div className="panel agent-chat">
      <div className="agent-chat-header" onClick={() => setIsCollapsed(!isCollapsed)}>
        <span className="agent-chat-title">AI 에이전트</span>
        <span className="agent-chat-toggle">{isCollapsed ? "▼" : "▲"}</span>
      </div>
      {!isCollapsed && (
        <div className="agent-chat-body">
          {messages.length === 0 && !isStreaming && (
            <div className="agent-chat-empty">
              <button className="btn btn-accent agent-analyze-btn" onClick={handleAnalyze}>
                분석 요청
              </button>
              <p className="agent-chat-hint">AI에게 이 코인의 분석을 요청하세요</p>
            </div>
          )}
          {messages.length > 0 && (
            <div className="agent-chat-messages">
              {messages.map((msg, i) => (
                <div key={i} className={`agent-msg agent-msg-${msg.role}`}>
                  <div className="agent-msg-content">
                    {msg.role === "assistant" ? (
                      <>
                        <Markdown>{msg.content}</Markdown>
                        {isStreaming && i === messages.length - 1 && (
                          <span className="streaming-cursor" />
                        )}
                      </>
                    ) : (
                      msg.content
                    )}
                  </div>
                  {msg.sources && msg.sources.length > 0 && (
                    <div className="agent-msg-sources">
                      {msg.sources.map((s, j) => (
                        <a key={j} href={s.url} target="_blank" rel="noopener noreferrer" className="agent-source-chip">
                          {s.title || new URL(s.url).hostname}
                        </a>
                      ))}
                    </div>
                  )}
                </div>
              ))}
              <div ref={messagesEndRef} />
            </div>
          )}
          <form className="agent-input-area" onSubmit={handleSubmit}>
            <input
              className="agent-input"
              type="text"
              placeholder="질문을 입력하세요..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              disabled={isStreaming}
            />
            <button className="btn btn-accent agent-send-btn" type="submit" disabled={isStreaming || !input.trim()}>
              전송
            </button>
          </form>
        </div>
      )}
    </div>
  );
}

/* ── ExchangeDetail ─────────────────────────────── */

function ExchangeDetail({
  market,
  koreanName,
  ticker,
  lastMessage,
}: {
  market: string;
  koreanName: string;
  ticker: MarketItem | null;
  lastMessage: { type: string; data: unknown } | null;
}) {
  const { api, auth } = useAuthContext();
  const { get } = api;
  const [tf, setTf] = useState<Timeframe | DailyTf>(15);
  const [position, setPosition] = useState<PositionInfo | null>(null);
  const [cashBalance, setCashBalance] = useState("0");

  const chartContainerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeriesRef = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volumeSeriesRef = useRef<ISeriesApi<"Histogram"> | null>(null);
  const lastCandleTimeRef = useRef<number>(0);

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

  // Chart setup — only recreate when market changes
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
      lastCandleTimeRef.current = 0;
    };
  }, [market]);

  // Load candle data when market or timeframe changes (NOT position)
  useEffect(() => {
    const tfParam = tf === "1D" ? "1D" : String(tf);
    get<CandleRaw[]>(`/api/dashboard/candles?market=${market}&limit=200&timeframe=${tfParam}`).then(
      (candles) => {
        if (!candleSeriesRef.current || !volumeSeriesRef.current) return;

        const candleData: CandlestickData[] = candles.map((c) => ({
          time: (c.timestamp + 32400) as unknown as CandlestickData["time"],
          open: Number(c.open),
          high: Number(c.high),
          low: Number(c.low),
          close: Number(c.close),
        }));

        const volumeData: HistogramData[] = candles.map((c) => ({
          time: (c.timestamp + 32400) as unknown as HistogramData["time"],
          value: Number(c.volume),
          color:
            Number(c.close) >= Number(c.open)
              ? "rgba(0, 224, 175, 0.3)"
              : "rgba(255, 68, 102, 0.3)",
        }));

        candleSeriesRef.current.setData(candleData);
        volumeSeriesRef.current.setData(volumeData);

        if (candles.length > 0) {
          lastCandleTimeRef.current = candles[candles.length - 1].timestamp + 32400;
        }

        chartRef.current?.timeScale().fitContent();
      }
    );
  }, [market, tf, get]);

  // Draw position overlay lines (separate effect, no chart reset)
  useEffect(() => {
    if (!candleSeriesRef.current || !position) return;
    const cs = candleSeriesRef.current;

    const lines: { price: number; color: string; title: string }[] = [
      { price: Number(position.entry_price), color: "#3b82f6", title: "매수가" },
    ];
    if (position.stop_loss_price) {
      lines.push({ price: Number(position.stop_loss_price), color: "#ff4466", title: "손절" });
    }
    if (position.take_profit_price) {
      lines.push({ price: Number(position.take_profit_price), color: "#00e0af", title: "익절" });
    }

    const priceLines = lines.map((l) =>
      cs.createPriceLine({
        price: l.price,
        color: l.color,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: l.title,
      })
    );

    return () => {
      priceLines.forEach((pl) => cs.removePriceLine(pl));
    };
  }, [position]);

  // Real-time candle update from WebSocket ticker
  useEffect(() => {
    if (!lastMessage || lastMessage.type !== "ticker") return;
    const t = lastMessage.data as unknown as TickerWS;
    if (t.market !== market) return;
    if (!candleSeriesRef.current) return;

    const price = Number(t.price);
    const tfSeconds = tf === "1D" ? 86400 : (tf as number) * 60;
    const now = Math.floor(t.timestamp);
    const kstNow = now + 32400;
    const candleTime = Math.floor(kstNow / tfSeconds) * tfSeconds;

    if (candleTime < lastCandleTimeRef.current) return;

    candleSeriesRef.current.update({
      time: candleTime as unknown as CandlestickData["time"],
      open: candleTime > lastCandleTimeRef.current ? price : undefined as unknown as number,
      high: price,
      low: price,
      close: price,
    });

    if (candleTime > lastCandleTimeRef.current) {
      lastCandleTimeRef.current = candleTime;
    }
  }, [lastMessage, market, tf]);

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

      {/* AI Agent Chat */}
      <div style={{ marginTop: 16 }}>
        <AgentChat market={market} accessToken={auth.accessToken} />
      </div>
    </div>
  );
}

/* ── Main Exchange Component ────────────────────── */

export default function Exchange() {
  const { api, auth } = useAuthContext();
  const { get } = api;
  const { lastMessage } = useWebSocket(`${WS_BASE}/ws/live`, auth.accessToken);
  const [markets, setMarkets] = useState<MarketItem[]>([]);
  const [search, setSearch] = useState("");
  const [selectedMarket, setSelectedMarket] = useState<string | null>(null);
  const [flashes, setFlashes] = useState<Record<string, string>>({});
  const [holdingMarkets, setHoldingMarkets] = useState<Set<string>>(new Set());
  const [sortKey, setSortKey] = useState<SortKey>("volume");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [marketFilter, setMarketFilter] = useState<MarketFilter>("all");
  const prevPrices = useRef<Record<string, string>>({});

  // Fetch markets
  const fetchMarkets = useCallback(() => {
    get<MarketItem[]>("/api/exchange/markets").then(setMarkets);
  }, [get]);

  // Fetch holdings
  const fetchHoldings = useCallback(() => {
    get<{ market: string }[]>("/api/portfolio/positions").then((positions) => {
      setHoldingMarkets(new Set(positions.map((p) => p.market)));
    });
  }, [get]);

  useEffect(() => {
    fetchMarkets();
    fetchHoldings();
    const id = setInterval(fetchMarkets, 30_000);
    const id2 = setInterval(fetchHoldings, 10_000);
    return () => { clearInterval(id); clearInterval(id2); };
  }, [fetchMarkets, fetchHoldings]);

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

  // Filter & sort markets
  const filtered = useMemo(() => {
    let items = markets;
    if (search) {
      const q = search.toLowerCase();
      items = items.filter(
        (m) =>
          m.korean_name.toLowerCase().includes(q) ||
          m.market.toLowerCase().includes(q)
      );
    }
    return sortMarkets(items, sortKey, sortDir, marketFilter, holdingMarkets);
  }, [markets, search, sortKey, sortDir, marketFilter, holdingMarkets]);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir((d) => (d === "desc" ? "asc" : "desc"));
    } else {
      setSortKey(key);
      setSortDir(key === "name" ? "asc" : "desc");
    }
  };

  const sortIcon = (key: SortKey) =>
    sortKey === key ? (sortDir === "desc" ? " ▾" : " ▴") : "";

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
            <div className="market-filter-bar">
              <button
                className={`market-filter-btn${marketFilter === "all" ? " active" : ""}`}
                onClick={() => setMarketFilter("all")}
              >
                전체
              </button>
              <button
                className={`market-filter-btn${marketFilter === "screened" ? " active" : ""}`}
                onClick={() => setMarketFilter("screened")}
              >
                AI 스크리닝
              </button>
              <button
                className={`market-filter-btn${marketFilter === "holding" ? " active" : ""}`}
                onClick={() => setMarketFilter("holding")}
              >
                보유
              </button>
            </div>
            <div className="exchange-search">
              <input
                placeholder="코인 검색..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <div className="market-header">
              <div className="market-col-name" onClick={() => handleSort("name")}>
                코인명{sortIcon("name")}
              </div>
              <div className="market-col-price" onClick={() => handleSort("price")}>
                현재가{sortIcon("price")}
              </div>
              <div className="market-col-change" onClick={() => handleSort("change")}>
                전일대비{sortIcon("change")}
              </div>
              <div className="market-col-volume" onClick={() => handleSort("volume")}>
                거래대금{sortIcon("volume")}
              </div>
            </div>
            <div className="exchange-market-list">
              {filtered.map((m) => (
                <MarketRow
                  key={m.market}
                  item={m}
                  selected={selectedMarket === m.market}
                  onClick={() => setSelectedMarket(m.market)}
                  flash={flashes[m.market] ?? ""}
                  holding={holdingMarkets.has(m.market)}
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
          lastMessage={lastMessage}
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

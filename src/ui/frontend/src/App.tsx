import { useState, useEffect, useCallback, useRef } from "react";
import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./pages/Dashboard";
import Exchange from "./pages/Exchange";
import Strategy from "./pages/Strategy";
import Risk from "./pages/Risk";
import System from "./pages/System";

function App() {
  const { lastMessage, isConnected } = useWebSocket("ws://localhost:8000/ws/live");
  const [tradingEnabled, setTradingEnabled] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
  const toastId = useRef(0);

  useEffect(() => {
    if (lastMessage?.type !== "order_filled") return;
    const d = lastMessage.data as { market: string; side: string; reason: string; price: string };
    const id = ++toastId.current;
    const msg =
      d.side === "SELL"
        ? `${d.market.replace("KRW-", "")} ${d.reason} — ₩${Number(d.price).toLocaleString("ko-KR")}에 매도 완료`
        : `${d.market.replace("KRW-", "")} 매수 완료 — ₩${Number(d.price).toLocaleString("ko-KR")}`;
    setToasts((prev) => [...prev, { id, msg }]);
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, 5000);
  }, [lastMessage]);

  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/control/status");
      if (res.ok) {
        const data = await res.json();
        setTradingEnabled(data.trading_enabled);
      }
    } catch { /* ignore */ }
  }, []);

  useEffect(() => {
    fetchStatus();
    const id = setInterval(fetchStatus, 5000);
    return () => clearInterval(id);
  }, [fetchStatus]);

  const toggleTrading = async () => {
    const endpoint = tradingEnabled ? "/api/control/trading/stop" : "/api/control/trading/start";
    try {
      const res = await fetch(endpoint, { method: "POST" });
      if (res.ok) {
        setTradingEnabled(!tradingEnabled);
      }
    } catch { /* ignore */ }
  };

  return (
    <BrowserRouter>
      <div className="app-layout">
        {/* ── Sidebar ────────────────────────── */}
        <aside className="sidebar">
          <div className="sidebar-brand">
            <h1>CRYPTO<br />PAPER TRADER</h1>
            <div className="brand-sub">Upbit ML Strategy v0.1</div>
          </div>

          <ul className="sidebar-nav">
            <li>
              <NavLink to="/" end>
                <span className="nav-icon">&#9632;</span>
                대시보드
              </NavLink>
            </li>
            <li>
              <NavLink to="/exchange" className={({ isActive }) => (isActive ? "active" : "")}>
                <span className="nav-icon">◇</span> 거래소
              </NavLink>
            </li>
            <li>
              <NavLink to="/strategy">
                <span className="nav-icon">&#9650;</span>
                전략
              </NavLink>
            </li>
            <li>
              <NavLink to="/risk">
                <span className="nav-icon">&#9679;</span>
                리스크
              </NavLink>
            </li>
            <li>
              <NavLink to="/system">
                <span className="nav-icon">&#9881;</span>
                시스템
              </NavLink>
            </li>
          </ul>

          <div className="sidebar-trading">
            <button
              className={`trading-toggle ${tradingEnabled ? "active" : ""}`}
              onClick={toggleTrading}
            >
              {tradingEnabled ? "매매 중지" : "매매 시작"}
            </button>
          </div>

          <div className="sidebar-status">
            <span className={`status-dot ${isConnected ? "live" : "offline"}`} />
            <span className="status-label">
              {isConnected ? "실시간" : "오프라인"}
            </span>
          </div>
        </aside>

        {/* ── Main content ───────────────────── */}
        <main className="main-content">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/exchange" element={<Exchange />} />
            <Route path="/strategy" element={<Strategy />} />
            <Route path="/risk" element={<Risk />} />
            <Route path="/system" element={<System />} />
          </Routes>
        </main>

        {/* ── Toast notifications ──────────── */}
        <div className="toast-container">
          {toasts.map((t) => (
            <div key={t.id} className="toast">{t.msg}</div>
          ))}
        </div>
      </div>
    </BrowserRouter>
  );
}

export default App;

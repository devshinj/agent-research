import { BrowserRouter, Routes, Route, Navigate, NavLink } from "react-router-dom";
import { useEffect, useState, useRef, useCallback } from "react";
import { AuthProvider, useAuthContext } from "./context/AuthContext";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./pages/Dashboard";
import Exchange from "./pages/Exchange";
import Strategy from "./pages/Strategy";
import Risk from "./pages/Risk";
import System from "./pages/System";
import Admin from "./pages/Admin";
import Login from "./pages/Login";
import Register from "./pages/Register";

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRouter />
      </AuthProvider>
    </BrowserRouter>
  );
}

function AppRouter() {
  const { auth } = useAuthContext();

  if (!auth.isAuthenticated) {
    return (
      <Routes>
        <Route path="/login" element={<Login onLogin={auth.login} />} />
        <Route path="/register" element={<Register onRegister={auth.register} />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return <AuthenticatedApp />;
}

function AuthenticatedApp() {
  const { auth, api } = useAuthContext();
  const handleWsAuthError = useCallback(async () => {
    const ok = await auth.refresh();
    if (!ok) auth.logout();
  }, [auth]);
  const { lastMessage, isConnected } = useWebSocket(`${WS_BASE}/ws/live`, auth.accessToken, handleWsAuthError);
  const [tradingEnabled, setTradingEnabled] = useState(false);
  const [toasts, setToasts] = useState<{ id: number; msg: string }[]>([]);
  const toastId = useRef(0);

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const data = await api.get<any>("/api/control/status");
        setTradingEnabled(data.trading_enabled);
      } catch { /* ignore */ }
    };
    fetchStatus();
    const iv = setInterval(fetchStatus, 5000);
    return () => clearInterval(iv);
  }, [api]);

  useEffect(() => {
    if (lastMessage?.type !== "order_filled") return;
    const d = lastMessage.data as { market: string; side: string; reason: string; price: string };
    const id = ++toastId.current;
    const msg =
      d.side === "SELL"
        ? `${d.market.replace("KRW-", "")} ${d.reason} — ₩${Number(d.price).toLocaleString("ko-KR")}에 매도 완료`
        : `${d.market.replace("KRW-", "")} 매수 완료 — ₩${Number(d.price).toLocaleString("ko-KR")}`;
    setToasts((prev) => [...prev, { id, msg }]);
    setTimeout(() => setToasts((prev) => prev.filter((t) => t.id !== id)), 5000);
  }, [lastMessage]);

  return (
    <div className="app-layout">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <h1>CRYPTO<br />PAPER TRADER</h1>
          <div className="brand-sub">Upbit ML Strategy v0.1</div>
        </div>

        <ul className="sidebar-nav">
          <li><NavLink to="/" end><span className="nav-icon">&#9632;</span> 대시보드</NavLink></li>
          <li><NavLink to="/exchange"><span className="nav-icon">◇</span> 거래소</NavLink></li>
          <li><NavLink to="/strategy"><span className="nav-icon">&#9650;</span> 전략</NavLink></li>
          <li><NavLink to="/risk"><span className="nav-icon">&#9679;</span> 리스크</NavLink></li>
          <li><NavLink to="/system"><span className="nav-icon">&#9881;</span> 시스템</NavLink></li>
          {auth.isAdmin && <li><NavLink to="/admin"><span className="nav-icon">&#9998;</span> 회원 관리</NavLink></li>}
        </ul>

        <div className="sidebar-trading">
          <div className={`trading-indicator ${tradingEnabled ? "on" : "off"}`}>
            <span className={`status-dot ${tradingEnabled ? "live" : "offline"}`} />
            <span>{tradingEnabled ? "자동매매 ON" : "자동매매 OFF"}</span>
          </div>
        </div>

        <div className="user-info">
          <span className="user-nickname">{auth.user?.nickname}</span>
          <span className="user-email">{auth.user?.email}</span>
        </div>
        <button className="btn btn-sm sidebar-logout" onClick={auth.logout}>로그아웃</button>

        <div className="sidebar-status">
          <span className={`status-dot ${isConnected ? "live" : "offline"}`} />
          <span className="status-label">{isConnected ? "실시간" : "오프라인"}</span>
        </div>
      </aside>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/exchange" element={<Exchange />} />
          <Route path="/strategy" element={<Strategy />} />
          <Route path="/risk" element={<Risk />} />
          <Route path="/system" element={<System />} />
          {auth.isAdmin && <Route path="/admin" element={<Admin />} />}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>

      <div className="toast-container">
        {toasts.map((t) => (
          <div key={t.id} className="toast">{t.msg}</div>
        ))}
      </div>
    </div>
  );
}

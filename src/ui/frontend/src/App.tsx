import { BrowserRouter, Routes, Route, NavLink } from "react-router-dom";
import { useWebSocket } from "./hooks/useWebSocket";
import Dashboard from "./pages/Dashboard";
import Charts from "./pages/Charts";
import Portfolio from "./pages/Portfolio";
import Strategy from "./pages/Strategy";
import Risk from "./pages/Risk";
import Settings from "./pages/Settings";

function App() {
  const { isConnected } = useWebSocket("ws://localhost:8000/ws/live");

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
              <NavLink to="/charts">
                <span className="nav-icon">&#9644;</span>
                차트
              </NavLink>
            </li>
            <li>
              <NavLink to="/portfolio">
                <span className="nav-icon">&#9670;</span>
                포트폴리오
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
              <NavLink to="/settings">
                <span className="nav-icon">&#9881;</span>
                설정
              </NavLink>
            </li>
          </ul>

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
            <Route path="/charts" element={<Charts />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/strategy" element={<Strategy />} />
            <Route path="/risk" element={<Risk />} />
            <Route path="/settings" element={<Settings />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;

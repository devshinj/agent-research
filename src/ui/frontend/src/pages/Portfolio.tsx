import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface Position {
  market: string;
  side: string;
  quantity: string;
  avg_price: string;
  current_price: string;
  unrealized_pnl: string;
  pnl_pct: string;
}

interface HistoryItem {
  id: string;
  market: string;
  side: string;
  quantity: string;
  price: string;
  filled_at: string;
}

interface HistoryPage {
  items: HistoryItem[];
  page: number;
  size: number;
  total: number;
}

const formatKRW = (val: string) =>
  `\u20A9${Number(val).toLocaleString("ko-KR")}`;

const pnlBadge = (pct: string) => {
  const n = Number(pct);
  if (n > 0) return "profit";
  if (n < 0) return "loss";
  return "neutral";
};

export default function Portfolio() {
  const { get } = useApi();
  const [positions, setPositions] = useState<Position[]>([]);
  const [history, setHistory] = useState<HistoryPage | null>(null);
  const [page, setPage] = useState(1);

  useEffect(() => {
    get<Position[]>("/api/portfolio/positions").then(setPositions);
  }, [get]);

  useEffect(() => {
    get<HistoryPage>(`/api/portfolio/history?page=${page}&size=20`).then(setHistory);
  }, [get, page]);

  return (
    <div>
      <div className="page-header">
        <h2>포트폴리오</h2>
        <div className="page-sub">현재 포지션 및 거래 내역</div>
      </div>

      {/* ── Positions ──────────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>보유 포지션</h3>
          <span className="badge info">{positions.length}</span>
        </div>
        {positions.length === 0 ? (
          <div className="panel-body">
            <div className="empty-state">
              <div className="empty-icon">&#9670;</div>
              <div className="empty-text">
                보유 포지션이 없습니다. 신호 발생 시 모의매매 엔진이 포지션을 개시합니다.
              </div>
            </div>
          </div>
        ) : (
          <table className="data-table">
            <thead>
              <tr>
                <th>마켓</th>
                <th>매매구분</th>
                <th>수량</th>
                <th>평균단가</th>
                <th>현재가</th>
                <th>미실현 손익</th>
                <th>%</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.market}>
                  <td style={{ color: "var(--text)", fontWeight: 600 }}>{p.market}</td>
                  <td>
                    <span className={`badge ${p.side === "BUY" ? "profit" : "loss"}`}>
                      {p.side}
                    </span>
                  </td>
                  <td>{p.quantity}</td>
                  <td>{formatKRW(p.avg_price)}</td>
                  <td>{formatKRW(p.current_price)}</td>
                  <td style={{ color: Number(p.unrealized_pnl) >= 0 ? "var(--profit)" : "var(--loss)" }}>
                    {formatKRW(p.unrealized_pnl)}
                  </td>
                  <td>
                    <span className={`badge ${pnlBadge(p.pnl_pct)}`}>
                      {Number(p.pnl_pct) > 0 ? "+" : ""}{p.pnl_pct}%
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {/* ── Trade History ──────────────────── */}
      <div className="panel">
        <div className="panel-header">
          <h3>거래 내역</h3>
          {history && (
            <span className="badge neutral">{history.total} total</span>
          )}
        </div>
        {!history || history.items.length === 0 ? (
          <div className="panel-body">
            <div className="empty-state">
              <div className="empty-icon">&#9776;</div>
              <div className="empty-text">
                거래 기록이 없습니다. 모의매매 엔진이 주문을 체결하면 내역이 표시됩니다.
              </div>
            </div>
          </div>
        ) : (
          <>
            <table className="data-table">
              <thead>
                <tr>
                  <th>시간</th>
                  <th>마켓</th>
                  <th>매매구분</th>
                  <th>수량</th>
                  <th>체결가</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((h) => (
                  <tr key={h.id}>
                    <td>{h.filled_at}</td>
                    <td style={{ color: "var(--text)", fontWeight: 600 }}>{h.market}</td>
                    <td>
                      <span className={`badge ${h.side === "BUY" ? "profit" : "loss"}`}>
                        {h.side}
                      </span>
                    </td>
                    <td>{h.quantity}</td>
                    <td>{formatKRW(h.price)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div style={{ padding: "16px 20px", display: "flex", justifyContent: "flex-end", gap: 8 }}>
              <button
                className="btn btn-ghost"
                disabled={page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
              >
                이전
              </button>
              <button
                className="btn btn-ghost"
                disabled={history.items.length < history.size}
                onClick={() => setPage((p) => p + 1)}
              >
                다음
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}

import { useEffect, useState } from "react";
import { useApi } from "../hooks/useApi";

interface Position {
  market: string;
  korean_name: string;
  quantity: string;
  avg_price: string;
  current_price: string;
  unrealized_pnl: string;
  pnl_pct: string;
  eval_amount: string;
}

interface HistoryItem {
  id: string;
  filled_at: number;
  market: string;
  korean_name: string;
  side: string;
  quantity: string;
  price: string;
  total_amount: string;
}

interface HistoryPage {
  items: HistoryItem[];
  page: number;
  size: number;
  total: number;
}

const formatKRW = (val: string | undefined | null) => {
  if (val == null) return "\u20A90";
  const n = Number(val);
  if (Number.isNaN(n)) return "\u20A90";
  return `\u20A9${Math.floor(n).toLocaleString("ko-KR")}`;
};

const formatQty = (val: string) => Number(val).toFixed(8);

const formatTime = (ts: number | null | undefined) => {
  if (!ts) return "-";
  const d = new Date(ts * 1000);
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
};

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
                <th>마켓명</th>
                <th>보유 평단가</th>
                <th>현재가</th>
                <th>손익</th>
                <th>수익률</th>
                <th>구매 수량</th>
                <th>평가 금액</th>
              </tr>
            </thead>
            <tbody>
              {positions.map((p) => (
                <tr key={p.market}>
                  <td style={{ color: "var(--text)", fontWeight: 600 }}>
                    {p.korean_name}
                    <span style={{ fontSize: "0.8em", opacity: 0.5, marginLeft: 6 }}>{p.market}</span>
                  </td>
                  <td>{formatKRW(p.avg_price)}</td>
                  <td>{formatKRW(p.current_price)}</td>
                  <td style={{ color: Number(p.unrealized_pnl) >= 0 ? "var(--profit)" : "var(--loss)" }}>
                    {formatKRW(p.unrealized_pnl)}
                  </td>
                  <td>
                    <span className={`badge ${pnlBadge(p.pnl_pct)}`}>
                      {Number(p.pnl_pct) > 0 ? "+" : ""}{Number(p.pnl_pct).toFixed(2)}%
                    </span>
                  </td>
                  <td>{formatQty(p.quantity)}</td>
                  <td>{formatKRW(p.eval_amount)}</td>
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
                  <th>거래 시간</th>
                  <th>마켓명</th>
                  <th>매매 구분</th>
                  <th>수량</th>
                  <th>체결 단가</th>
                  <th>총 거래 금액</th>
                </tr>
              </thead>
              <tbody>
                {history.items.map((h) => (
                  <tr key={h.id}>
                    <td>{formatTime(h.filled_at)}</td>
                    <td style={{ color: "var(--text)", fontWeight: 600 }}>
                      {h.korean_name}
                      <span style={{ fontSize: "0.8em", opacity: 0.5, marginLeft: 6 }}>{h.market}</span>
                    </td>
                    <td>
                      <span className={`badge ${h.side === "BUY" ? "profit" : "loss"}`}>
                        {h.side === "BUY" ? "매수" : "매도"}
                      </span>
                    </td>
                    <td>{formatQty(h.quantity)}</td>
                    <td>{formatKRW(h.price)}</td>
                    <td>{formatKRW(h.total_amount)}</td>
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

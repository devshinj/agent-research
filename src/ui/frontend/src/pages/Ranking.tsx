import { useEffect, useState, useCallback, useRef } from "react";
import { useAuthContext } from "../context/AuthContext";
import {
  ResponsiveContainer,
  LineChart,
  Line,
} from "recharts";

interface RankingEntry {
  rank: number;
  user_id: number;
  nickname: string;
  return_pct: string;
  realized_pnl: string;
  initial_balance: string;
  total_equity: string;
  win_rate: string;
  total_trades: number;
  max_drawdown_pct: string;
  daily_equities: string[];
  is_me: boolean;
}

interface RankingResponse {
  rankings: RankingEntry[];
  my_rank: number | null;
  total_users: number;
}

const fmtKrw = (v: string) => {
  const n = Math.trunc(Number(v));
  return n.toLocaleString("ko-KR");
};

export default function Ranking() {
  const { api } = useAuthContext();
  const [data, setData] = useState<RankingResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [tooltip, setTooltip] = useState<{ text: string; x: number; y: number } | null>(null);
  const tipTimer = useRef<ReturnType<typeof setTimeout>>(null);

  const showTip = (e: React.MouseEvent<HTMLSpanElement>) => {
    const text = (e.currentTarget as HTMLElement).dataset.tooltip;
    if (!text) return;
    const rect = e.currentTarget.getBoundingClientRect();
    tipTimer.current = setTimeout(
      () => setTooltip({ text, x: rect.left + rect.width / 2, y: rect.top }),
      200,
    );
  };
  const hideTip = () => {
    if (tipTimer.current) clearTimeout(tipTimer.current);
    setTooltip(null);
  };

  const fetchRanking = useCallback(async () => {
    try {
      const res = await api.get<RankingResponse>("/api/ranking/");
      setData(res);
    } catch {
      /* ignore */
    } finally {
      setLoading(false);
    }
  }, [api]);

  useEffect(() => {
    fetchRanking();
  }, [fetchRanking]);

  if (loading) return <div className="page-loading">로딩 중...</div>;
  if (!data) return <div className="page-error">데이터를 불러올 수 없습니다</div>;

  const myEntry = data.rankings.find((e) => e.is_me);

  return (
    <div className="ranking-page">
      <div className="page-header">
        <h2>투자 손익 랭킹</h2>
      </div>

      {myEntry && (
        <div className="ranking-my-summary">
          <div className="my-rank-card">
            <span className="my-rank-label">내 순위</span>
            <span className="my-rank-value">#{myEntry.rank}</span>
            <span className="my-rank-total">/ {data.total_users}명</span>
          </div>
          <div className="my-rank-card">
            <span className="my-rank-label">수익률</span>
            <span
              className={`my-rank-value ${
                Number(myEntry.return_pct) >= 0 ? "positive" : "negative"
              }`}
            >
              {Number(myEntry.return_pct) >= 0 ? "+" : ""}
              {myEntry.return_pct}%
            </span>
          </div>
          <div className="my-rank-card">
            <span className="my-rank-label">승률</span>
            <span className="my-rank-value">{myEntry.win_rate}%</span>
          </div>
        </div>
      )}

      <div className="ranking-table-wrap">
        <table className="ranking-table">
          <thead>
            <tr>
              <th>순위</th>
              <th>닉네임</th>
              <th>
                <span className="th-tip" data-tooltip="매매 완료된 거래의 누적 손익" onMouseEnter={showTip} onMouseLeave={hideTip}>실현 손익</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="현재 보유 현금 + 보유 종목 평가액" onMouseEnter={showTip} onMouseLeave={hideTip}>총 평가자산</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="누적 실현손익 ÷ 투자원금 × 100" onMouseEnter={showTip} onMouseLeave={hideTip}>수익률</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="수익 거래 수 ÷ (수익 + 손실) 거래 수 × 100" onMouseEnter={showTip} onMouseLeave={hideTip}>승률</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="전체 기간 누적 거래 횟수" onMouseEnter={showTip} onMouseLeave={hideTip}>거래</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="일간 시작잔고 대비 종료잔고 하락률 중 역대 최대값" onMouseEnter={showTip} onMouseLeave={hideTip}>최대 낙폭</span>
              </th>
              <th>
                <span className="th-tip" data-tooltip="최근 30일 일별 평가자산 추이" onMouseEnter={showTip} onMouseLeave={hideTip}>추이</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {data.rankings.map((entry) => {
              const pnlNum = Number(entry.realized_pnl);
              const returnNum = Number(entry.return_pct);
              const medal =
                entry.rank === 1
                  ? "🥇"
                  : entry.rank === 2
                  ? "🥈"
                  : entry.rank === 3
                  ? "🥉"
                  : `${entry.rank}`;

              const sparkData = entry.daily_equities.map((v, i) => ({
                i,
                v: Number(v),
              }));

              return (
                <tr
                  key={entry.user_id}
                  className={entry.is_me ? "ranking-row-me" : ""}
                >
                  <td className="ranking-rank">
                    {entry.is_me && <span className="me-bar" />}
                    {medal}
                  </td>
                  <td className="ranking-nickname">
                    {entry.nickname}
                    {entry.is_me && <span className="me-badge">나</span>}
                  </td>
                  <td
                    className={`ranking-money ${
                      pnlNum >= 0 ? "positive" : "negative"
                    }`}
                  >
                    {pnlNum >= 0 ? "+" : ""}₩{fmtKrw(entry.realized_pnl)}
                  </td>
                  <td className="ranking-money">₩{fmtKrw(entry.total_equity)}</td>
                  <td
                    className={`ranking-return ${
                      returnNum >= 0 ? "positive" : "negative"
                    }`}
                  >
                    {returnNum >= 0 ? "+" : ""}
                    {entry.return_pct}%
                  </td>
                  <td>{entry.win_rate}%</td>
                  <td>{entry.total_trades}회</td>
                  <td className="negative">-{Number(entry.max_drawdown_pct).toFixed(2)}%</td>
                  <td className="ranking-sparkline">
                    {sparkData.length > 1 ? (
                      <ResponsiveContainer width={80} height={28}>
                        <LineChart data={sparkData}>
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke={pnlNum >= 0 ? "#22c55e" : "#ef4444"}
                            strokeWidth={1.5}
                            dot={false}
                          />
                        </LineChart>
                      </ResponsiveContainer>
                    ) : (
                      <span className="no-data">—</span>
                    )}
                  </td>
                </tr>
              );
            })}
            {data.rankings.length === 0 && (
              <tr>
                <td colSpan={9} className="ranking-empty">
                  아직 랭킹 데이터가 없습니다
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {tooltip && (
        <div
          className="ranking-tooltip"
          style={{ left: tooltip.x, top: tooltip.y }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  );
}

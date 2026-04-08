import { useEffect, useState, useCallback } from "react";
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
  total_pnl: string;
  initial_balance: string;
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
              <th>투자금</th>
              <th>손익</th>
              <th>수익률</th>
              <th>승률</th>
              <th>거래</th>
              <th>최대 낙폭</th>
              <th>추이</th>
            </tr>
          </thead>
          <tbody>
            {data.rankings.map((entry) => {
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
                  <td className="ranking-money">₩{fmtKrw(entry.initial_balance)}</td>
                  <td
                    className={`ranking-money ${
                      Number(entry.total_pnl) >= 0 ? "positive" : "negative"
                    }`}
                  >
                    {Number(entry.total_pnl) >= 0 ? "+" : ""}₩{fmtKrw(entry.total_pnl)}
                  </td>
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
                  <td className="negative">-{entry.max_drawdown_pct}%</td>
                  <td className="ranking-sparkline">
                    {sparkData.length > 1 ? (
                      <ResponsiveContainer width={80} height={28}>
                        <LineChart data={sparkData}>
                          <Line
                            type="monotone"
                            dataKey="v"
                            stroke={returnNum >= 0 ? "#22c55e" : "#ef4444"}
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
    </div>
  );
}

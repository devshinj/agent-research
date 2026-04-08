import { useEffect, useState } from "react";
import { useAuthContext } from "../context/AuthContext";

interface UserItem {
  id: number;
  email: string;
  nickname: string;
  is_admin: boolean;
  is_active: boolean;
  created_at: string;
  cash_balance: string;
}

interface UserSettings {
  stop_loss_pct: number;
  take_profit_pct: number;
  trailing_stop_pct: number;
}

interface BalanceHistory {
  id: number;
  admin_id: number;
  admin_nickname: string;
  amount: string;
  balance_after: string;
  memo: string;
  created_at: string;
}

function formatKRW(value: string): string {
  return Number(value).toLocaleString("ko-KR") + " KRW";
}

export default function Admin() {
  const { api } = useAuthContext();
  const { get, patchJson, postJson } = api;

  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(false);

  // Settings modal
  const [settingsUser, setSettingsUser] = useState<UserItem | null>(null);
  const [settings, setSettings] = useState<UserSettings>({ stop_loss_pct: 0, take_profit_pct: 0, trailing_stop_pct: 0 });
  const [settingsLoading, setSettingsLoading] = useState(false);
  const [settingsError, setSettingsError] = useState("");

  // Balance modal
  const [balanceUser, setBalanceUser] = useState<UserItem | null>(null);
  const [balanceAmount, setBalanceAmount] = useState("");
  const [balanceMemo, setBalanceMemo] = useState("");
  const [balanceLoading, setBalanceLoading] = useState(false);
  const [balanceError, setBalanceError] = useState("");
  const [balanceHistory, setBalanceHistory] = useState<BalanceHistory[]>([]);

  const fetchUsers = () => {
    get<UserItem[]>("/api/admin/users").then(setUsers).catch(() => {});
  };

  useEffect(() => {
    fetchUsers();
  }, []);

  const handleToggleActive = async (user: UserItem) => {
    setLoading(true);
    try {
      await patchJson(`/api/admin/users/${user.id}`, { is_active: !user.is_active });
      fetchUsers();
    } catch { /* ignore */ } finally {
      setLoading(false);
    }
  };

  // ── Settings Modal ──
  const openSettings = async (user: UserItem) => {
    setSettingsUser(user);
    setSettingsError("");
    try {
      const s = await get<UserSettings>(`/api/admin/users/${user.id}/settings`);
      setSettings(s);
    } catch {
      setSettings({ stop_loss_pct: 0, take_profit_pct: 0, trailing_stop_pct: 0 });
    }
  };

  const handleSaveSettings = async () => {
    if (!settingsUser) return;
    setSettingsLoading(true);
    setSettingsError("");
    try {
      await patchJson(`/api/admin/users/${settingsUser.id}/settings`, settings);
      setSettingsUser(null);
    } catch (err: any) {
      setSettingsError(err.message || "저장 실패");
    } finally {
      setSettingsLoading(false);
    }
  };

  // ── Balance Modal ──
  const openBalance = async (user: UserItem) => {
    setBalanceUser(user);
    setBalanceAmount("");
    setBalanceMemo("");
    setBalanceError("");
    try {
      const data = await get<{ history: BalanceHistory[] }>(`/api/admin/users/${user.id}/balance-history`);
      setBalanceHistory(data.history);
    } catch {
      setBalanceHistory([]);
    }
  };

  const handleAdjustBalance = async () => {
    if (!balanceUser || !balanceAmount) return;
    setBalanceLoading(true);
    setBalanceError("");
    try {
      await postJson(`/api/admin/users/${balanceUser.id}/balance`, {
        amount: balanceAmount,
        memo: balanceMemo,
      });
      fetchUsers();
      const data = await get<{ history: BalanceHistory[] }>(`/api/admin/users/${balanceUser.id}/balance-history`);
      setBalanceHistory(data.history);
      const updated = await get<UserItem[]>("/api/admin/users");
      const refreshed = updated.find(u => u.id === balanceUser.id);
      if (refreshed) setBalanceUser(refreshed);
      setBalanceAmount("");
      setBalanceMemo("");
    } catch (err: any) {
      setBalanceError(err.message || "잔고 변경 실패");
    } finally {
      setBalanceLoading(false);
    }
  };

  return (
    <div>
      <div className="page-header">
        <h2>회원 관리</h2>
        <div className="page-sub">회원 상태, 설정, 잔고를 관리합니다</div>
      </div>

      {/* ── User Table ── */}
      <div className="panel">
        <div className="panel-header">
          <h3>회원 목록</h3>
          <span className="badge info">{users.length}명</span>
        </div>
        <div className="panel-body" style={{ padding: 0 }}>
          {users.length === 0 ? (
            <div className="empty-state"><div className="empty-text">사용자 없음</div></div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th>닉네임</th>
                  <th>이메일</th>
                  <th style={{ textAlign: "right" }}>잔고</th>
                  <th style={{ textAlign: "center" }}>상태</th>
                  <th style={{ textAlign: "center" }}>가입일</th>
                  <th style={{ textAlign: "center" }}>액션</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id}>
                    <td style={{ fontWeight: 600 }}>{u.nickname}</td>
                    <td style={{ color: "var(--text-dim)", fontSize: 13 }}>{u.email}</td>
                    <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", fontSize: 13 }}>
                      {formatKRW(u.cash_balance)}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <span className={`badge ${u.is_active ? "info" : "loss"}`} style={{ fontSize: 10 }}>
                        {u.is_active ? "활성" : "비활성"}
                      </span>
                    </td>
                    <td style={{ textAlign: "center", fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--text-muted)" }}>
                      {u.created_at ? new Date(u.created_at).toLocaleDateString("ko-KR") : "-"}
                    </td>
                    <td style={{ textAlign: "center" }}>
                      <div style={{ display: "flex", gap: 6, justifyContent: "center" }}>
                        <button
                          className="btn btn-sm btn-primary"
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => openBalance(u)}
                        >
                          잔고 관리
                        </button>
                        <button
                          className="btn btn-sm btn-ghost"
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => openSettings(u)}
                        >
                          설정
                        </button>
                        <button
                          className={`btn btn-sm ${u.is_active ? "btn-ghost" : "btn-primary"}`}
                          style={{ fontSize: 11, padding: "3px 10px" }}
                          onClick={() => handleToggleActive(u)}
                          disabled={loading || u.is_admin}
                        >
                          {u.is_active ? "비활성화" : "활성화"}
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── Balance Modal ── */}
      {balanceUser && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
          onClick={() => setBalanceUser(null)}
        >
          <div
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 560, width: "90%", maxHeight: "80vh", overflowY: "auto" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 4px", color: "var(--text)" }}>잔고 관리</h3>
            <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--text-dim)" }}>
              {balanceUser.nickname} ({balanceUser.email})
            </p>

            <div style={{ background: "var(--bg-darker)", borderRadius: 8, padding: "12px 16px", marginBottom: 20, fontFamily: "var(--font-mono)", fontSize: 15, textAlign: "center" }}>
              현재 잔고: <strong style={{ color: "var(--accent)" }}>{formatKRW(balanceUser.cash_balance)}</strong>
            </div>

            {balanceError && (
              <div className="auth-error" style={{ marginBottom: 12 }}>{balanceError}</div>
            )}

            <div style={{ display: "flex", gap: 12, marginBottom: 12 }}>
              <div className="form-group" style={{ flex: 2, marginBottom: 0 }}>
                <label>금액 (양수: 충전, 음수: 차감)</label>
                <input
                  type="text"
                  placeholder="예: 5000000 또는 -1000000"
                  value={balanceAmount}
                  onChange={(e) => setBalanceAmount(e.target.value)}
                />
              </div>
              <div className="form-group" style={{ flex: 1, marginBottom: 0 }}>
                <label>메모 (선택)</label>
                <input
                  type="text"
                  placeholder="사유"
                  value={balanceMemo}
                  onChange={(e) => setBalanceMemo(e.target.value)}
                />
              </div>
            </div>

            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginBottom: 24 }}>
              <button className="btn btn-ghost" onClick={() => setBalanceUser(null)}>닫기</button>
              <button className="btn btn-primary" onClick={handleAdjustBalance} disabled={balanceLoading || !balanceAmount}>
                {balanceLoading ? "처리 중..." : "적용"}
              </button>
            </div>

            {balanceHistory.length > 0 && (
              <>
                <h4 style={{ margin: "0 0 12px", fontSize: 13, color: "var(--text-dim)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  충전/차감 이력
                </h4>
                <table className="data-table" style={{ fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>일시</th>
                      <th style={{ textAlign: "right" }}>금액</th>
                      <th style={{ textAlign: "right" }}>변경 후</th>
                      <th>메모</th>
                      <th>처리자</th>
                    </tr>
                  </thead>
                  <tbody>
                    {balanceHistory.map((h) => (
                      <tr key={h.id}>
                        <td style={{ fontFamily: "var(--font-mono)", whiteSpace: "nowrap" }}>
                          {new Date(h.created_at).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)", color: Number(h.amount) >= 0 ? "var(--profit)" : "var(--loss)" }}>
                          {Number(h.amount) >= 0 ? "+" : ""}{Number(h.amount).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ textAlign: "right", fontFamily: "var(--font-mono)" }}>
                          {Number(h.balance_after).toLocaleString("ko-KR")}
                        </td>
                        <td style={{ color: "var(--text-dim)" }}>{h.memo || "-"}</td>
                        <td>{h.admin_nickname}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </>
            )}
          </div>
        </div>
      )}

      {/* ── Settings Modal ── */}
      {settingsUser && (
        <div
          style={{ position: "fixed", inset: 0, background: "rgba(0,0,0,0.6)", display: "flex", alignItems: "center", justifyContent: "center", zIndex: 1000 }}
          onClick={() => setSettingsUser(null)}
        >
          <div
            style={{ background: "var(--bg-card)", border: "1px solid var(--border)", borderRadius: 12, padding: 32, maxWidth: 420, width: "90%" }}
            onClick={(e) => e.stopPropagation()}
          >
            <h3 style={{ margin: "0 0 4px", color: "var(--text)" }}>사용자 설정</h3>
            <p style={{ margin: "0 0 20px", fontSize: 13, color: "var(--text-dim)" }}>{settingsUser.nickname} ({settingsUser.email})</p>
            {settingsError && (
              <div className="auth-error" style={{ marginBottom: 12 }}>{settingsError}</div>
            )}
            <div className="form-group">
              <label>손절 비율 (%)</label>
              <input type="number" step="0.1" value={settings.stop_loss_pct} onChange={e => setSettings(s => ({ ...s, stop_loss_pct: Number(e.target.value) }))} />
            </div>
            <div className="form-group">
              <label>익절 비율 (%)</label>
              <input type="number" step="0.1" value={settings.take_profit_pct} onChange={e => setSettings(s => ({ ...s, take_profit_pct: Number(e.target.value) }))} />
            </div>
            <div className="form-group">
              <label>트레일링 스탑 비율 (%)</label>
              <input type="number" step="0.1" value={settings.trailing_stop_pct} onChange={e => setSettings(s => ({ ...s, trailing_stop_pct: Number(e.target.value) }))} />
            </div>
            <div style={{ display: "flex", justifyContent: "flex-end", gap: 12, marginTop: 20 }}>
              <button className="btn btn-ghost" onClick={() => setSettingsUser(null)}>취소</button>
              <button className="btn btn-primary" onClick={handleSaveSettings} disabled={settingsLoading}>
                {settingsLoading ? "저장 중..." : "저장"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

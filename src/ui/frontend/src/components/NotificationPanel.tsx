import { useState, useEffect, useRef, useCallback } from "react";
import { useAuthContext } from "../context/AuthContext";

interface Notification {
  id: number;
  market: string;
  action: string;
  result: string;
  reason: string;
  confidence: number | null;
  created_at: number;
  is_read: boolean;
}

export default function NotificationPanel() {
  const { api } = useAuthContext();
  const [open, setOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);

  const fetchNotifications = useCallback(async () => {
    try {
      const data = await api.get<{ notifications: Notification[]; unread_count: number }>(
        "/api/dashboard/notifications?limit=50"
      );
      setNotifications(data.notifications);
      setUnreadCount(data.unread_count);
    } catch { /* ignore */ }
  }, [api]);

  useEffect(() => {
    fetchNotifications();
    const iv = setInterval(fetchNotifications, 10000);
    return () => clearInterval(iv);
  }, [fetchNotifications]);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    if (open) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const handleToggle = () => {
    setOpen((prev) => !prev);
  };

  const handleMarkAllRead = async () => {
    try {
      await api.post("/api/dashboard/notifications/read-all");
      setUnreadCount(0);
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
    } catch { /* ignore */ }
  };

  const formatTime = (ts: number) => {
    const d = new Date(ts * 1000);
    const hh = String(d.getHours()).padStart(2, "0");
    const mm = String(d.getMinutes()).padStart(2, "0");
    const MM = String(d.getMonth() + 1).padStart(2, "0");
    const DD = String(d.getDate()).padStart(2, "0");
    return `${MM}-${DD} ${hh}:${mm}`;
  };

  return (
    <div className="notification-wrapper" ref={panelRef}>
      <button className="notification-bell" onClick={handleToggle} title="알림">
        <span className="bell-icon">&#128276;</span>
        {unreadCount > 0 && <span className="notification-badge">{unreadCount}</span>}
      </button>

      {open && (
        <div className="notification-panel">
          <div className="notification-header">
            <span className="notification-title">매매 알림</span>
            {unreadCount > 0 && (
              <button className="notification-read-all" onClick={handleMarkAllRead}>
                모두 읽음
              </button>
            )}
          </div>
          <div className="notification-list">
            {notifications.length === 0 ? (
              <div className="notification-empty">알림이 없습니다</div>
            ) : (
              notifications.map((n) => (
                <div
                  key={n.id}
                  className={`notification-item ${n.is_read ? "" : "unread"} ${n.result === "SUCCESS" ? "success" : "rejected"}`}
                >
                  <div className="notification-item-top">
                    <span className="notification-result-icon">
                      {n.result === "SUCCESS" ? (n.action === "BUY" ? "+" : "-") : "!"}
                    </span>
                    <span className="notification-market">{n.market.replace("KRW-", "")}</span>
                    <span className="notification-action">{n.action}</span>
                    <span className="notification-time">{formatTime(n.created_at)}</span>
                  </div>
                  <div className="notification-reason">{n.reason}</div>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}

import { useEffect, useRef, useState } from "react";

interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

export function useWebSocket(
  url: string,
  token: string | null,
  onAuthError?: () => void,
) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);
  const onAuthErrorRef = useRef(onAuthError);
  onAuthErrorRef.current = onAuthError;

  useEffect(() => {
    if (!token) return;

    let disposed = false;
    let retryTimer: ReturnType<typeof setTimeout>;

    const connect = () => {
      if (disposed) return;
      const ws = new WebSocket(`${url}?token=${token}`);
      wsRef.current = ws;

      ws.onopen = () => setIsConnected(true);

      ws.onclose = (e) => {
        setIsConnected(false);
        if (disposed) return;

        // 403 Forbidden — token expired or invalid, don't retry
        if (e.code === 1006 && !e.wasClean) {
          // Server rejected before handshake (e.g. 403)
          // Could be auth error — notify parent
          onAuthErrorRef.current?.();
          return;
        }

        // Normal reconnect for other closures
        retryTimer = setTimeout(connect, 3000);
      };

      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as WSMessage;
        setLastMessage(msg);
      };
    };

    connect();

    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      wsRef.current?.close();
    };
  }, [url, token]);

  return { lastMessage, isConnected };
}

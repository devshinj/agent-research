import { useEffect, useRef, useState } from "react";

interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

export function useWebSocket(url: string, token: string | null) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!token) return;
    const wsUrl = `${url}?token=${token}`;

    const connect = () => {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => setIsConnected(true);
      ws.onclose = () => {
        setIsConnected(false);
        setTimeout(connect, 3000);
      };
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as WSMessage;
        setLastMessage(msg);
      };
    };

    connect();

    return () => {
      wsRef.current?.close();
    };
  }, [url, token]);

  return { lastMessage, isConnected };
}

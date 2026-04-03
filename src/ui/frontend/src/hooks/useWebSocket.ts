import { useEffect, useRef, useState } from "react";

interface WSMessage {
  type: string;
  data: Record<string, unknown>;
}

export function useWebSocket(url: string) {
  const [lastMessage, setLastMessage] = useState<WSMessage | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onopen = () => setIsConnected(true);
    ws.onclose = () => {
      setIsConnected(false);
      setTimeout(() => {
        wsRef.current = new WebSocket(url);
      }, 3000);
    };
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data) as WSMessage;
      setLastMessage(msg);
    };

    return () => ws.close();
  }, [url]);

  return { lastMessage, isConnected };
}

import { useCallback } from "react";

const API_BASE = "http://localhost:8000";

export function useApi() {
  const get = useCallback(async <T>(path: string): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`);
    return resp.json();
  }, []);

  const post = useCallback(async <T>(path: string): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`, { method: "POST" });
    return resp.json();
  }, []);

  return { get, post };
}

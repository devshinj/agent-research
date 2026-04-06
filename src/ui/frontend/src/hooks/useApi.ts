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

  const postJson = useCallback(async <T>(path: string, body: unknown): Promise<T> => {
    const resp = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return resp.json();
  }, []);

  const patchJson = useCallback(async <T>(url: string, body: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${url}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(`PATCH ${url} failed: ${res.status}`);
    return res.json();
  }, []);

  return { get, post, postJson, patchJson };
}

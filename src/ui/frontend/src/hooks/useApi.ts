import { useCallback } from "react";

const API_BASE = import.meta.env.VITE_API_URL || "";

export function useApi(accessToken: string | null, onUnauthorized: () => void) {
  const headers = useCallback((): Record<string, string> => {
    const h: Record<string, string> = {};
    if (accessToken) h["Authorization"] = `Bearer ${accessToken}`;
    return h;
  }, [accessToken]);

  const handleResponse = useCallback(async <T>(res: Response): Promise<T> => {
    if (res.status === 401) {
      onUnauthorized();
      throw new Error("Unauthorized");
    }
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return res.json();
  }, [onUnauthorized]);

  const get = useCallback(async <T>(path: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, { headers: headers() });
    return handleResponse<T>(res);
  }, [headers, handleResponse]);

  const post = useCallback(async <T>(path: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST", headers: headers(),
    });
    return handleResponse<T>(res);
  }, [headers, handleResponse]);

  const postJson = useCallback(async <T>(path: string, body: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  }, [headers, handleResponse]);

  const patchJson = useCallback(async <T>(path: string, body: unknown): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "PATCH",
      headers: { ...headers(), "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    return handleResponse<T>(res);
  }, [headers, handleResponse]);

  const del = useCallback(async <T>(path: string): Promise<T> => {
    const res = await fetch(`${API_BASE}${path}`, {
      method: "DELETE", headers: headers(),
    });
    return handleResponse<T>(res);
  }, [headers, handleResponse]);

  return { get, post, postJson, patchJson, del };
}

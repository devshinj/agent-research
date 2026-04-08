import { useState, useEffect, useCallback } from "react";

interface User {
  id: number;
  email: string;
  nickname: string;
  is_admin: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
}

const API_BASE = import.meta.env.VITE_API_URL || "";

export function useAuth() {
  const [auth, setAuth] = useState<AuthState>(() => {
    const stored = localStorage.getItem("auth");
    return stored ? JSON.parse(stored) : { user: null, accessToken: null, refreshToken: null };
  });

  useEffect(() => {
    if (auth.user) {
      localStorage.setItem("auth", JSON.stringify(auth));
    } else {
      localStorage.removeItem("auth");
    }
  }, [auth]);

  const login = useCallback(async (email: string, password: string) => {
    const res = await fetch(`${API_BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Login failed");
    }
    const data = await res.json();
    setAuth({
      user: data.user,
      accessToken: data.access_token,
      refreshToken: data.refresh_token,
    });
  }, []);

  const register = useCallback(async (
    email: string, password: string, nickname: string, inviteCode: string,
  ) => {
    const res = await fetch(`${API_BASE}/api/auth/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        email, password, nickname, invite_code: inviteCode,
      }),
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || "Registration failed");
    }
    return await res.json();
  }, []);

  const logout = useCallback(() => {
    setAuth({ user: null, accessToken: null, refreshToken: null });
  }, []);

  const refresh = useCallback(async () => {
    if (!auth.refreshToken) return false;
    try {
      const res = await fetch(`${API_BASE}/api/auth/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: auth.refreshToken }),
      });
      if (!res.ok) throw new Error("Refresh failed");
      const data = await res.json();
      setAuth(prev => ({ ...prev, accessToken: data.access_token }));
      return true;
    } catch {
      logout();
      return false;
    }
  }, [auth.refreshToken, logout]);

  return {
    user: auth.user,
    accessToken: auth.accessToken,
    isAuthenticated: !!auth.user,
    isAdmin: auth.user?.is_admin ?? false,
    login,
    register,
    refresh,
    logout,
  };
}

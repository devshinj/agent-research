import { createContext, useContext } from "react";
import { useAuth } from "../hooks/useAuth";
import { useApi } from "../hooks/useApi";

interface AuthContextType {
  auth: ReturnType<typeof useAuth>;
  api: ReturnType<typeof useApi>;
}

const AuthContext = createContext<AuthContextType | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const auth = useAuth();
  const api = useApi(auth.accessToken, async () => {
    const ok = await auth.refresh();
    if (!ok) auth.logout();
  });
  return (
    <AuthContext.Provider value={{ auth, api }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuthContext() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuthContext must be inside AuthProvider");
  return ctx;
}

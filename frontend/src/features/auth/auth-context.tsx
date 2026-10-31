/** Authentication state: JWT in localStorage, bootstrapped via /api/auth/me. */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import {
  apiFetch,
  getStoredToken,
  setStoredToken,
} from "@/lib/api";
import type { AuthResponse, RegisterInput, User } from "@/types/auth";

interface AuthContextValue {
  user: User | null;
  initializing: boolean;
  login: (email: string, password: string) => Promise<User>;
  register: (input: RegisterInput) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [initializing, setInitializing] = useState(true);

  useEffect(() => {
    const token = getStoredToken();
    if (!token) {
      setInitializing(false);
      return;
    }
    apiFetch<User>("/api/auth/me")
      .then(setUser)
      .catch(() => setStoredToken(null))
      .finally(() => setInitializing(false));
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const response = await apiFetch<AuthResponse>("/api/auth/login", {
      method: "POST",
      body: { email, password },
    });
    setStoredToken(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const register = useCallback(async (input: RegisterInput) => {
    const response = await apiFetch<AuthResponse>("/api/auth/register", {
      method: "POST",
      body: input,
    });
    setStoredToken(response.access_token);
    setUser(response.user);
    return response.user;
  }, []);

  const logout = useCallback(() => {
    // JWT is stateless server-side; the token is discarded client-side.
    setStoredToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, initializing, login, register, logout }),
    [user, initializing, login, register, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

"use client";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import { clearToken, getUser, saveToken, saveUser } from "@/lib/api";

export type AuthUser = {
  token: string;
  role: string;
  full_name: string | null;
};

type AuthContextValue = {
  user: AuthUser | null;
  ready: boolean; // becomes true once we've read localStorage on the client
  login: (u: AuthUser) => void;
  logout: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = getUser<AuthUser>();
    if (stored?.token) setUser(stored);
    setReady(true);
  }, []);

  function login(u: AuthUser) {
    saveToken(u.token);
    saveUser(u);
    setUser(u);
  }

  function logout() {
    clearToken();
    setUser(null);
  }

  return (
    <AuthContext.Provider value={{ user, ready, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

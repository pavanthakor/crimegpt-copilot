"use client";
import { createContext, useContext, useEffect, useState } from "react";
import type { ReactNode } from "react";

import {
  clearStepUpVerified,
  clearToken,
  getUser,
  isStepUpVerified,
  saveToken,
  saveUser,
  setStepUpVerified,
} from "@/lib/api";

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
  /**
   * Has this session cleared the step-up PIN?
   *
   * IN MEMORY ON PURPOSE, and never persisted. A step-up says "the person at the
   * terminal is still the officer who signed in" — a claim that cannot outlive the
   * session that made it. Putting it in localStorage would let it survive a sign-out,
   * an idle timeout, or another officer taking the machine over, which is exactly what
   * it exists to prevent. Idle-logout and the 401 redirect both reload the page, so this
   * dies with them; login() and logout() clear it explicitly for the client-side paths.
   */
  pinVerified: boolean;
  markPinVerified: () => void;
};

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const [pinVerified, setPinVerified] = useState(false);

  useEffect(() => {
    const stored = getUser<AuthUser>();
    if (stored?.token) setUser(stored);
    // Rehydrate the step-up across a page reload — the session has not changed, so
    // asking again would break "once per session".
    setPinVerified(isStepUpVerified());
    setReady(true);
  }, []);

  function login(u: AuthUser) {
    saveToken(u.token);
    saveUser(u);
    setUser(u);
    // A new session starts untrusted, even if the last one had stepped up — signing in
    // again is exactly when we must not assume the same person is still there.
    clearStepUpVerified();
    setPinVerified(false);
  }

  function logout() {
    clearToken(); // also drops the step-up
    setUser(null);
    setPinVerified(false);
  }

  function markPinVerified() {
    setStepUpVerified();
    setPinVerified(true);
  }

  return (
    <AuthContext.Provider
      value={{ user, ready, login, logout, pinVerified, markPinVerified }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}

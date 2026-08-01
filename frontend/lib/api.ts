import axios from "axios";

const TOKEN_KEY = "crimegpt_token";
const USER_KEY = "crimegpt_user";

// Axios instance pointed at the FastAPI backend.
export const api = axios.create({ baseURL: "http://localhost:8000" });

// Attach the JWT from localStorage to every request.
api.interceptors.request.use((config) => {
  if (typeof window !== "undefined") {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
  }
  return config;
});

// An expired/invalid JWT must land the officer on the login screen, not paint the
// authenticated shell around a "Could not validate credentials" message — on a machine
// idle for days that reads as a broken app, and recovery meant typing /login by hand.
//
// Deliberately narrow: ONLY 401 redirects. 403/404/500 and every 2xx are passed straight
// through to the caller untouched, so existing per-page error handling is unchanged.
api.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";

    // /api/auth/login answers 401 for a WRONG PASSWORD. That is not a stale session —
    // the login page catches it to show "invalid credentials", so it must not redirect
    // (that would wipe the message and bounce the page onto itself).
    const isLoginAttempt = url.includes("/api/auth/login");

    if (
      status === 401 &&
      !isLoginAttempt &&
      typeof window !== "undefined" &&
      window.location.pathname !== "/login"
    ) {
      clearToken(); // drop the stale token + cached user before leaving
      window.location.replace("/login"); // replace(), so Back can't return to the dead shell
    }

    // Always re-reject: callers' .catch() still runs and nothing else changes behaviour.
    return Promise.reject(error);
  },
);

export function saveToken(token: string): void {
  localStorage.setItem(TOKEN_KEY, token);
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function clearToken(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

export function saveUser(user: unknown): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUser<T = unknown>(): T | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as T) : null;
}

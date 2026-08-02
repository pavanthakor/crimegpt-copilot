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

/**
 * Leave for the login screen, dropping the session on the way out.
 *
 * Extracted so there is ONE definition of "this session is over". The 401 interceptor
 * below calls it when the server rejects a stale token; the idle watchdog calls it when
 * nobody has touched the terminal. Those are two different reasons to end a session, and
 * they must not become two different implementations of ending one.
 *
 * replace() rather than assign(), so Back cannot return to the dead authenticated shell.
 */
export function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  clearToken();
  if (window.location.pathname !== "/login") {
    window.location.replace("/login");
  }
}

// ---------------------------------------------------------------------------
// In-flight request tracking.
//
// The idle watchdog needs to tell "nobody is here" from "the officer is waiting on us".
// An intake extraction takes 12-40s and a document generation is not instant; during
// those the officer is sitting watching a spinner, which is the opposite of idle. Every
// request increments this on the way out and decrements on the way back, whatever the
// outcome, so a failed request cannot leak the counter upwards and wedge the session
// open for ever.
// ---------------------------------------------------------------------------
let pending = 0;
let busySince: number | null = null;

function requestStarted(): void {
  pending += 1;
  if (busySince === null) busySince = Date.now();
}

function requestSettled(): void {
  pending = Math.max(0, pending - 1);
  if (pending === 0) busySince = null;
}

/** How many requests are in flight right now. */
export function pendingRequests(): number {
  return pending;
}

/** How long requests have been CONTINUOUSLY in flight, in ms (0 when idle). */
export function busyForMs(): number {
  return busySince === null ? 0 : Date.now() - busySince;
}

api.interceptors.request.use(
  (config) => {
    requestStarted();
    return config;
  },
  (error) => {
    requestSettled();
    return Promise.reject(error);
  },
);

// An expired/invalid JWT must land the officer on the login screen, not paint the
// authenticated shell around a "Could not validate credentials" message — on a machine
// idle for days that reads as a broken app, and recovery meant typing /login by hand.
//
// Deliberately narrow: ONLY 401 redirects. 403/404/500 and every 2xx are passed straight
// through to the caller untouched, so existing per-page error handling is unchanged.
api.interceptors.response.use(
  (response) => {
    requestSettled();
    return response;
  },
  (error) => {
    requestSettled();
    const status = error?.response?.status;
    const url: string = error?.config?.url ?? "";

    // /api/auth/login answers 401 for a WRONG PASSWORD. That is not a stale session —
    // the login page catches it to show "invalid credentials", so it must not redirect
    // (that would wipe the message and bounce the page onto itself).
    const isLoginAttempt = url.includes("/api/auth/login");

    if (status === 401 && !isLoginAttempt) {
      redirectToLogin(); // the shared path: clears the token, then leaves
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

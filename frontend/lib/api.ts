import axios from "axios";

const TOKEN_KEY = "crimegpt_token";
const USER_KEY = "crimegpt_user";
// Whether this session has cleared its step-up PIN. SESSION storage, not local: it must
// survive a page reload — "once per session" would be a lie if F5 re-prompted — but must
// not outlive the tab, and must never be readable by a later session. It holds a boolean,
// never the PIN. clearToken() removes it, so every path that ends a session (sign out,
// idle-logout, the 401 redirect) drops the step-up with it.
const STEPUP_KEY = "crimegpt_stepup";

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
let settledAt = 0;

function requestStarted(): void {
  pending += 1;
  if (busySince === null) busySince = Date.now();
}

function requestSettled(): void {
  pending = Math.max(0, pending - 1);
  if (pending === 0) {
    busySince = null;
    // The moment the app goes quiet again counts as a fresh start for the idle clock.
    // Without this, an officer who waits 20s for an extraction is signed out the instant
    // it returns — the deadline passed while they were watching the spinner, so the
    // guard that held the session open expires the moment it stops applying, and they
    // never see what they waited for. Time spent waiting on us must not be charged
    // against them.
    settledAt = Date.now();
  }
}

/** When the app last finished being busy (0 if it never has). */
export function lastRequestSettledAt(): number {
  return settledAt;
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
  sessionStorage.removeItem(STEPUP_KEY); // a step-up never outlives its session
}

export function setStepUpVerified(): void {
  if (typeof window !== "undefined") sessionStorage.setItem(STEPUP_KEY, "1");
}

export function isStepUpVerified(): boolean {
  if (typeof window === "undefined") return false;
  return sessionStorage.getItem(STEPUP_KEY) === "1";
}

export function clearStepUpVerified(): void {
  if (typeof window !== "undefined") sessionStorage.removeItem(STEPUP_KEY);
}

export function saveUser(user: unknown): void {
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

export function getUser<T = unknown>(): T | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(USER_KEY);
  return raw ? (JSON.parse(raw) as T) : null;
}

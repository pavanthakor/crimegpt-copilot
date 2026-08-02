/**
 * Idle-session policy.
 *
 * A police terminal left open and unattended is a way into the case file: anyone
 * walking past can register a case, edit a person or generate a document under the
 * signed-in officer's name, and the audit trail will name that officer. Signing the
 * session out after a period with nobody there closes that.
 *
 * The DECISION lives here as a pure function, separate from the React component that
 * watches the clock, so the rule can be tested directly rather than by waiting out real
 * timeouts. Nothing in this file touches the DOM, storage or the network.
 */

/** Read a positive number from the environment, falling back when unset or malformed. */
function envNumber(raw: string | undefined, fallback: number): number {
  const n = Number(raw);
  return Number.isFinite(n) && n > 0 ? n : fallback;
}

// Tunable without a code change. Defaults are chosen so the app behaves sensibly with no
// env file at all — which is how it runs today. IDLE_TIMEOUT_SECONDS wins when set, so a
// demo can drop the timeout to 30s and show the whole behaviour inside a minute.
const TIMEOUT_MINUTES = envNumber(process.env.NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES, 15);
const TIMEOUT_SECONDS = envNumber(process.env.NEXT_PUBLIC_IDLE_TIMEOUT_SECONDS, 0);

export const IDLE_TIMEOUT_MS =
  TIMEOUT_SECONDS > 0 ? TIMEOUT_SECONDS * 1000 : TIMEOUT_MINUTES * 60 * 1000;

/** How long before the deadline the officer is warned. Never longer than the timeout. */
export const IDLE_WARNING_MS = Math.min(
  envNumber(process.env.NEXT_PUBLIC_IDLE_WARNING_SECONDS, 60) * 1000,
  Math.floor(IDLE_TIMEOUT_MS / 2),
);

/**
 * The longest a request in flight may hold the session open.
 *
 * A running operation means the officer is waiting on us, not absent — so an idle
 * deadline must never fire mid-extraction. But "a request is open" cannot postpone
 * logout for ever, or one hung connection quietly disables the whole safeguard. After
 * this the deadline applies regardless.
 */
export const IDLE_BUSY_GRACE_MS = 2 * 60 * 1000;

export type IdleState = "active" | "warning" | "expired";

/**
 * Decide what to do, given how long since the officer last did anything and whether the
 * app is mid-operation. Pure: same inputs, same answer, no clock of its own.
 */
export function evaluateIdle(input: {
  /** ms since the last genuine user action. */
  idleMs: number;
  /** how many requests are in flight. */
  pending: number;
  /** ms that requests have been continuously in flight (0 when none are). */
  busyMs: number;
}): IdleState {
  const { idleMs, pending, busyMs } = input;

  // Mid-operation: the system is working for them. Hold the session open — but only
  // up to the grace, so a stuck request cannot disable the safeguard entirely.
  if (pending > 0 && busyMs < IDLE_BUSY_GRACE_MS) return "active";

  if (idleMs >= IDLE_TIMEOUT_MS) return "expired";
  if (idleMs >= IDLE_TIMEOUT_MS - IDLE_WARNING_MS) return "warning";
  return "active";
}

/** Whole seconds left before sign-out, for the countdown in the warning notice. */
export function secondsRemaining(idleMs: number): number {
  return Math.max(0, Math.ceil((IDLE_TIMEOUT_MS - idleMs) / 1000));
}

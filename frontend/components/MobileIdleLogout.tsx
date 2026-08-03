"use client";
import { useEffect, useRef, useState } from "react";

import { busyForMs, clearToken, lastRequestSettledAt, pendingRequests } from "@/lib/api";
import { evaluateIdle, secondsRemaining } from "@/lib/idle";
import { useI18n } from "@/lib/i18n";

/**
 * Idle sign-out for the mobile field page.
 *
 * A phone left unlocked on a desk is the same unattended-terminal problem as a signed-in
 * workstation, so the field page gets the same safeguard. The DECISION is not re-invented:
 * `evaluateIdle` and `secondsRemaining` are the very functions the desktop watchdog uses,
 * so both surfaces expire on one policy and one set of tunables.
 *
 * WHY THIS IS NOT JUST <IdleLogout/>. That component ends a session with
 * `redirectToLogin()`, which hardcodes "/login" — the desktop password screen. Sending a
 * field officer there would ask them for a password they came to this page to avoid. This
 * clears the session with the same `clearToken()` that `redirectToLogin` calls and then
 * lands on /m, whose signed-out state IS the PIN screen. The desktop watchdog and
 * `redirectToLogin` itself are untouched.
 */
export default function MobileIdleLogout({ onExpired }: { onExpired: () => void }) {
  const { t } = useI18n();
  const lastActivity = useRef<number>(Date.now());
  const [warningSecs, setWarningSecs] = useState<number | null>(null);

  useEffect(() => {
    const markActive = () => {
      lastActivity.current = Date.now();
    };

    // Same deliberate-action set as the desktop watchdog, plus the touch events a phone
    // actually produces. `mousemove` stays excluded for the same reason it is there.
    const EVENTS = ["mousedown", "keydown", "wheel", "scroll", "touchstart", "touchmove"] as const;
    for (const e of EVENTS) window.addEventListener(e, markActive, { passive: true });

    const tick = window.setInterval(() => {
      const since = Math.max(lastActivity.current, lastRequestSettledAt());
      const idleMs = Date.now() - since;
      const state = evaluateIdle({
        idleMs,
        pending: pendingRequests(),
        busyMs: busyForMs(),
      });

      if (state === "expired") {
        window.clearInterval(tick);
        clearToken(); // the same session teardown redirectToLogin() performs
        onExpired(); // ...but back to the PIN screen, not the desktop password screen
        return;
      }
      setWarningSecs(state === "warning" ? secondsRemaining(idleMs) : null);
    }, 1000);

    return () => {
      for (const e of EVENTS) window.removeEventListener(e, markActive);
      window.clearInterval(tick);
    };
  }, [onExpired]);

  if (warningSecs === null) return null;

  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed inset-x-3 bottom-3 z-50 border border-secondary rounded bg-surface-container-low px-4 py-3 shadow-lg"
    >
      <p className="font-body-md text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined text-lg text-secondary">timer</span>
        {t("idle.warning", { sec: warningSecs })}
      </p>
      <p className="font-body-sm text-on-surface-variant mt-1">{t("idle.warning.hint")}</p>
    </div>
  );
}

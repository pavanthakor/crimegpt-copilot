"use client";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";

import { busyForMs, lastRequestSettledAt, pendingRequests, redirectToLogin } from "@/lib/api";
import { evaluateIdle, secondsRemaining } from "@/lib/idle";
import { useI18n } from "@/lib/i18n";

/**
 * Signs the officer out after a period with nobody at the terminal.
 *
 * Mounted inside the authenticated shell only, so it never runs on the login screen and
 * cannot bounce a signed-out visitor.
 *
 * WHY A CLOCK RATHER THAN A TIMER PER EVENT. Activity is recorded as a timestamp and a
 * single interval compares it against the wall clock. Resetting a setTimeout on every
 * keypress would mean tearing down and rebuilding a timer on each character typed, and a
 * laptop suspended with the lid shut would come back with its timer still pending —
 * comparing timestamps means a machine asleep past the deadline is expired the moment it
 * wakes, which is the behaviour a locked-terminal rule needs.
 *
 * The sign-out itself is `redirectToLogin()` from lib/api — the same function the 401
 * interceptor calls. This component decides WHEN a session ends; it does not implement
 * what ending one means, and it contains no auth logic of its own.
 */
export default function IdleLogout() {
  const { t } = useI18n();
  const pathname = usePathname() ?? "";
  const lastActivity = useRef<number>(Date.now());
  const [warningSecs, setWarningSecs] = useState<number | null>(null);

  // Navigating counts as activity — a page change is the officer doing something.
  useEffect(() => {
    lastActivity.current = Date.now();
    setWarningSecs(null);
  }, [pathname]);

  useEffect(() => {
    const markActive = () => {
      lastActivity.current = Date.now();
    };

    // Deliberate actions only. `mousemove` is excluded: a knocked desk or a drifting
    // cursor would keep an empty room signed in indefinitely, which is the exact
    // situation this exists to end.
    const EVENTS = ["mousedown", "keydown", "wheel", "scroll", "touchstart"] as const;
    for (const e of EVENTS) {
      window.addEventListener(e, markActive, { passive: true });
    }

    const tick = window.setInterval(() => {
      // Idle runs from the officer's last action OR from the moment the app last stopped
      // working for them, whichever is later — so a long operation does not eat the
      // window they need to read its result.
      const since = Math.max(lastActivity.current, lastRequestSettledAt());
      const idleMs = Date.now() - since;
      const state = evaluateIdle({
        idleMs,
        pending: pendingRequests(),
        busyMs: busyForMs(),
      });

      if (state === "expired") {
        window.clearInterval(tick);
        redirectToLogin(); // the shared path, identical to a 401
        return;
      }
      setWarningSecs(state === "warning" ? secondsRemaining(idleMs) : null);
    }, 1000);

    return () => {
      for (const e of EVENTS) window.removeEventListener(e, markActive);
      window.clearInterval(tick);
    };
  }, []);

  if (warningSecs === null) return null;

  // A notice, not a modal: it warns without blocking, and any real action dismisses it
  // because that same action resets the clock.
  return (
    <div
      role="status"
      aria-live="polite"
      className="fixed bottom-6 right-6 z-50 max-w-sm border border-secondary rounded bg-surface-container-low px-4 py-3 shadow-lg"
    >
      <p className="font-body-md text-on-surface flex items-center gap-2">
        <span className="material-symbols-outlined text-lg text-secondary">timer</span>
        {t("idle.warning", { sec: warningSecs })}
      </p>
      <p className="font-body-sm text-on-surface-variant mt-1">{t("idle.warning.hint")}</p>
    </div>
  );
}

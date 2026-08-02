"use client";
import { useState } from "react";
import type { ReactNode } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/lib/i18n";

/**
 * Step-up PIN for high-stakes actions — registering a case, finalizing a document.
 *
 * IT SITS IN FRONT OF THE EXISTING CONFIRMATION, it does not replace it. `guard(action)`
 * either runs the action straight away (session already stepped up) or holds it until a
 * PIN clears, then runs THAT SAME action. The write path underneath is untouched: there
 * is no second way to register a case or finalize a document, and nothing here knows how
 * to do either.
 *
 * ONCE PER SESSION. Clearing the PIN marks the session trusted in AuthProvider, so the
 * second high-stakes action of a shift does not ask again. That state is in memory and
 * dies with the session — see the note on `pinVerified`.
 *
 * A WRONG PIN WRITES NOTHING. The action is a callback held in state; it is invoked only
 * after the endpoint answers ok. There is no path where a failed verification and a
 * partial write can coexist, because the write has not begun.
 */
export function useStepUp() {
  const { pinVerified, markPinVerified } = useAuth();
  // The high-stakes action waiting on a PIN. Stored as a thunk, so React's functional
  // setState form is required or it would call the action instead of storing it.
  const [pending, setPending] = useState<(() => void) | null>(null);

  function guard(action: () => void) {
    if (pinVerified) {
      action();
      return;
    }
    setPending(() => action);
  }

  const prompt: ReactNode = pending ? (
    <PinPrompt
      onVerified={() => {
        const action = pending;
        setPending(null);
        markPinVerified();
        action?.();
      }}
      onCancel={() => setPending(null)}
    />
  ) : null;

  return { guard, prompt, pinVerified };
}

function PinPrompt({
  onVerified,
  onCancel,
}: {
  onVerified: () => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    if (busy || !pin.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/api/auth/verify-pin", { pin });
      if (res.data?.ok) {
        setPin("");           // never keep the PIN around once it has been used
        onVerified();
        return;
      }
      // A reason CODE comes back, not a sentence, so the officer reads it in their
      // own language. Anything unrecognised falls back to the generic wrong-PIN line.
      const reason = res.data?.reason;
      setError(
        reason === "locked"
          ? t("pin.error.locked")
          : reason === "no_pin_set"
          ? t("pin.error.noPin")
          : t("pin.error.wrong")
      );
      setPin("");
    } catch {
      setError(t("pin.error.failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border border-primary rounded p-4 bg-surface-container-low">
      <p className="font-body-md text-on-surface font-semibold flex items-center gap-2">
        <span className="material-symbols-outlined text-lg text-primary">lock</span>
        {t("pin.title")}
      </p>
      <p className="font-body-sm text-on-surface-variant mt-1">{t("pin.subtitle")}</p>

      <input
        type="password"
        inputMode="numeric"
        autoComplete="off"
        autoFocus
        value={pin}
        onChange={(e) => setPin(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter") submit();
        }}
        placeholder={t("pin.placeholder")}
        className="mt-3 w-40 bg-surface-container-low border border-outline-variant rounded px-4 py-2 font-mono-sm tracking-[0.4em] text-on-surface focus:outline-none focus:border-primary transition-colors"
      />

      {error && (
        <p className="font-body-sm text-error mt-2 flex items-center gap-1.5">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      <div className="flex gap-2 mt-3">
        <button
          type="button"
          onClick={submit}
          disabled={busy || !pin.trim()}
          className="bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-50"
        >
          {busy ? t("pin.verifying") : t("pin.verify")}
        </button>
        <button
          type="button"
          onClick={onCancel}
          className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
        >
          {t("pin.cancel")}
        </button>
      </div>
    </div>
  );
}

"use client";
import { useCallback, useState } from "react";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n, type TKey } from "@/lib/i18n";
import ExtractionProgress from "@/components/ExtractionProgress";
import MobileIdleLogout from "@/components/MobileIdleLogout";
import { PERSON_ROLES } from "@/lib/cases";

/**
 * Mobile field intake — register a case from a phone, on the station LAN.
 *
 * PURPOSE-BUILT, NOT THE DESKTOP PAGE SHRUNK. One column, large targets, no sidebar, no
 * tabs, no search. It captures a case in the field; evidence, documents, legal analysis
 * and the case diary stay on the desktop, where there is room for them.
 *
 * NOTHING NEW IS INVENTED BEHIND IT. The account is read by the same
 * `/api/intake/extract` the desktop calls, the wait is the same `ExtractionProgress`
 * component, and "Register case" is the same `/api/intake/commit` writing into the same
 * shared pool in one transaction — so a case entered on a phone is, from the moment it is
 * registered, indistinguishable from one entered at a desk.
 *
 * THE DRAFT LIVES IN THE PHONE'S BROWSER until the officer confirms, exactly as on the
 * desktop. Walk away and nothing was written.
 *
 * NO SECOND PIN AT REGISTER. The desktop asks for a step-up PIN before registering,
 * because the officer signed in with a password and a high-stakes action deserves a fresh
 * proof of identity. Here the PIN IS the sign-in — asking for it again seconds later would
 * be ceremony, not security. The confirmation itself remains: nothing is written until the
 * officer has read the draft and pressed the button. `useStepUp` is deliberately not used
 * here, and the desktop's step-up is untouched.
 */

type Draft = {
  case_number: string;
  case_type: string;
  title: string;
  fir_number: string;
  fir_date: string;
  police_station: string;
  district: string;
  incident_datetime: string;
  incident_location: string;
  complaint_narrative: string;
};

type PersonRow = {
  _key: string;
  _touched: boolean;
  role: string;
  full_name: string;
  alias: string;
  father_name: string;
  age: string;
  gender: string;
  address: string;
  phone: string;
  occupation: string;
};

type ItemRow = {
  _key: string;
  _touched: boolean;
  description: string;
  quantity: string;
  estimated_value: string;
  seized_from_name: string;
  seizure_datetime: string;
  seizure_location: string;
};

const EMPTY: Draft = {
  case_number: "",
  case_type: "CONVENTIONAL",
  title: "",
  fir_number: "",
  fir_date: "",
  police_station: "",
  district: "",
  incident_datetime: "",
  incident_location: "",
  complaint_narrative: "",
};

const EDITABLE: (keyof Draft)[] = [
  "title",
  "fir_number",
  "fir_date",
  "police_station",
  "district",
  "incident_datetime",
  "incident_location",
  "complaint_narrative",
];

let seq = 0;
const key = () => `m${++seq}`;
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
const norm = (v: string): string => v.trim().toLowerCase();
const orNull = (v: string): string | null => (v.trim() ? v.trim() : null);
const intOrNull = (v: string): number | null => {
  const n = parseInt(v.trim(), 10);
  return Number.isFinite(n) ? n : null;
};
const floatOrNull = (v: string): number | null => {
  const n = parseFloat(v.trim());
  return Number.isFinite(n) ? n : null;
};

/**
 * Fold a fresh extraction into the mobile draft.
 *
 * MUCH SIMPLER THAN THE DESKTOP MERGE, and legitimately so — it is not a trimmed copy of
 * it. The desktop has an "Add person" button, so a row there may have come from the
 * officer's own hand, and its merge needs provenance and a two-turn sweep to tell a row
 * the extractor retracted from one it never saw. This page has no such button: every row
 * originates from an extraction, so the latest extraction is simply the truth.
 *
 * The one thing that must still be protected is a field the officer has corrected by
 * hand. A row they have touched is kept exactly as they left it, and survives even if the
 * extractor stops mentioning it.
 */
function reconcile<T extends { _key: string; _touched: boolean }>(
  prev: T[],
  extracted: unknown[],
  identity: (row: T) => string,
  extractedIdentity: (raw: Record<string, unknown>) => string,
  build: (raw: Record<string, unknown>) => T,
): T[] {
  const fresh = extracted.map((raw) => {
    const e = raw as Record<string, unknown>;
    const existing = prev.find((p) => identity(p) === extractedIdentity(e));
    return existing && existing._touched ? existing : build(e);
  });
  // Rows the officer edited that this extraction no longer mentions are still theirs.
  const keptByHand = prev.filter(
    (p) => p._touched && !fresh.some((f) => f._key === p._key),
  );
  return [...fresh, ...keptByHand];
}

export default function MobilePage() {
  const { user, ready, login, logout } = useAuth();
  const [signedOutNotice, setSignedOutNotice] = useState(false);

  const onIdleExpired = useCallback(() => {
    logout();
    setSignedOutNotice(true);
  }, [logout]);

  if (!ready) return null;

  if (!user) {
    return <PinLogin onSignedIn={login} idleNotice={signedOutNotice} />;
  }
  return (
    <>
      <MobileIdleLogout onExpired={onIdleExpired} />
      <FieldIntake />
    </>
  );
}

/* ------------------------------- shell bits ------------------------------- */

function LangSwitch() {
  const { lang, setLang } = useI18n();
  const opts: [typeof lang, string][] = [
    ["EN", "EN"],
    ["HI", "हिं"],
    ["GU", "ગુ"],
  ];
  return (
    <div className="flex gap-1">
      {opts.map(([code, label]) => (
        <button
          key={code}
          type="button"
          onClick={() => setLang(code)}
          className={
            "min-w-[48px] min-h-[40px] px-3 rounded font-label-caps transition-colors " +
            (lang === code
              ? "bg-primary text-on-primary"
              : "bg-surface-container-low text-on-surface-variant border border-outline-variant")
          }
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function Header({ right }: { right?: React.ReactNode }) {
  const { t } = useI18n();
  return (
    <header className="flex items-center justify-between gap-3 mb-6">
      <div className="flex items-center gap-2">
        <span className="material-symbols-outlined text-primary text-2xl">shield_person</span>
        <span className="font-headline-md text-primary">{t("m.title")}</span>
      </div>
      {right}
    </header>
  );
}

/* -------------------------------- PIN login ------------------------------- */

function PinLogin({
  onSignedIn,
  idleNotice,
}: {
  onSignedIn: (u: { token: string; role: string; full_name: string | null }) => void;
  idleNotice: boolean;
}) {
  const { t } = useI18n();
  const [username, setUsername] = useState("");
  const [pin, setPin] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (busy || !username.trim() || !pin.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.post("/api/auth/login-pin", { username: username.trim(), pin });
      onSignedIn(res.data);
    } catch {
      // The server answers one 401 for every kind of failure — unknown officer, no PIN
      // set, wrong PIN, locked out — so there is one message to show. Saying more here
      // would leak exactly what the uniform answer exists to withhold.
      setError(t("m.loginError"));
      setPin("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="min-h-screen bg-background text-on-background px-4 py-6 max-w-md mx-auto">
      <Header right={<LangSwitch />} />

      {idleNotice && (
        <p role="status" className="font-body-md text-secondary mb-4 flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">timer_off</span>
          {t("m.idleSignedOut")}
        </p>
      )}

      <p className="font-body-md text-on-surface-variant mb-6">{t("m.signInHint")}</p>

      <form onSubmit={submit} className="space-y-4">
        <label className="block">
          <span className="font-label-caps text-on-surface-variant">{t("m.username")}</span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoCapitalize="none"
            autoCorrect="off"
            className="mt-1 w-full min-h-[56px] bg-surface-container-low border border-outline-variant rounded px-4 font-body-lg text-on-surface focus:outline-none focus:border-primary"
          />
        </label>

        <label className="block">
          <span className="font-label-caps text-on-surface-variant">{t("m.pin")}</span>
          <input
            value={pin}
            onChange={(e) => setPin(e.target.value)}
            type="password"
            // A phone should offer digits, not a qwerty keyboard, for a numeric PIN.
            inputMode="numeric"
            autoComplete="off"
            className="mt-1 w-full min-h-[56px] bg-surface-container-low border border-outline-variant rounded px-4 font-mono-lg tracking-[0.4em] text-on-surface focus:outline-none focus:border-primary"
          />
        </label>

        {error && (
          <p role="alert" className="font-body-md text-error flex items-center gap-2">
            <span className="material-symbols-outlined text-base">error</span>
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={busy || !username.trim() || !pin.trim()}
          className="w-full min-h-[56px] rounded bg-primary text-on-primary font-label-lg disabled:opacity-40 transition-opacity"
        >
          {busy ? t("m.signingIn") : t("m.signIn")}
        </button>
      </form>
    </div>
  );
}

/* ------------------------------ field intake ------------------------------ */

function FieldIntake() {
  const { user, logout } = useAuth();
  const { t, apiLang } = useI18n();

  const [messages, setMessages] = useState<{ role: string; content: string }[]>([]);
  const [input, setInput] = useState("");
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [persons, setPersons] = useState<PersonRow[]>([]);
  const [items, setItems] = useState<ItemRow[]>([]);
  const [touched, setTouched] = useState<Set<string>>(new Set());

  const [extracting, setExtracting] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [registered, setRegistered] = useState<{ id: number; case_number: string } | null>(null);

  const hasDraft =
    persons.length > 0 || items.length > 0 || EDITABLE.some((f) => draft[f].trim() !== "");

  async function send() {
    const text = input.trim();
    if (!text || extracting) return;
    const history = [...messages, { role: "officer", content: text }];
    setMessages(history);
    setInput("");
    setExtracting(true);
    setError(null);
    try {
      const res = await api.post("/api/intake/extract", { messages: history, lang: apiLang });
      merge(res.data.draft);
    } catch {
      setError(t("m.extractError"));
    } finally {
      setExtracting(false);
    }
  }

  function merge(d: {
    case: Record<string, unknown>;
    persons: unknown[];
    seized_items: unknown[];
  }) {
    setDraft((prev) => {
      const next = { ...prev };
      for (const f of EDITABLE) {
        if (touched.has(f)) continue; // the officer's own correction wins
        const raw = d.case?.[f];
        if (raw === null || raw === undefined || raw === "") continue;
        next[f] =
          f === "incident_datetime"
            ? str(raw).slice(0, 16)
            : f === "fir_date"
            ? str(raw).slice(0, 10)
            : str(raw);
      }
      return next;
    });

    setPersons((prev) =>
      reconcile<PersonRow>(
        prev,
        d.persons ?? [],
        (p) => norm(p.full_name || p.alias),
        (e) => norm(str(e.full_name) || str(e.alias)),
        (e) => ({
          _key: key(),
          _touched: false,
          role: str(e.role) || "ACCUSED",
          full_name: str(e.full_name),
          alias: str(e.alias),
          father_name: str(e.father_name),
          age: str(e.age),
          gender: str(e.gender),
          address: str(e.address),
          phone: str(e.phone),
          occupation: str(e.occupation),
        }),
      ),
    );

    setItems((prev) =>
      reconcile<ItemRow>(
        prev,
        d.seized_items ?? [],
        (i) => norm(i.description),
        (e) => norm(str(e.description)),
        (e) => ({
          _key: key(),
          _touched: false,
          description: str(e.description),
          quantity: str(e.quantity),
          estimated_value: str(e.estimated_value),
          seized_from_name: str(e.seized_from_name),
          seizure_datetime: str(e.seizure_datetime).slice(0, 16),
          seizure_location: str(e.seizure_location),
        }),
      ),
    );
  }

  function setField(f: keyof Draft, v: string) {
    setTouched((prev) => new Set(prev).add(f));
    setDraft((prev) => ({ ...prev, [f]: v }));
  }

  async function register() {
    if (committing) return;
    if (!draft.case_number.trim()) {
      setError(t("m.numberRequired"));
      return;
    }
    setCommitting(true);
    setError(null);
    try {
      const res = await api.post("/api/intake/commit", {
        case: {
          case_number: draft.case_number.trim(),
          case_type: draft.case_type,
          complaint_language: apiLang.toUpperCase(),
          title: orNull(draft.title),
          fir_number: orNull(draft.fir_number),
          fir_date: orNull(draft.fir_date),
          police_station: orNull(draft.police_station),
          district: orNull(draft.district),
          incident_datetime: orNull(draft.incident_datetime),
          incident_location: orNull(draft.incident_location),
          complaint_narrative: orNull(draft.complaint_narrative),
        },
        persons: persons.map((p) => ({
          role: p.role,
          full_name: orNull(p.full_name),
          alias: orNull(p.alias),
          father_name: orNull(p.father_name),
          age: intOrNull(p.age),
          gender: orNull(p.gender),
          address: orNull(p.address),
          phone: orNull(p.phone),
          occupation: orNull(p.occupation),
        })),
        seized_items: items.map((i) => ({
          description: orNull(i.description),
          quantity: intOrNull(i.quantity),
          estimated_value: floatOrNull(i.estimated_value),
          seized_from_name: orNull(i.seized_from_name),
          seizure_datetime: orNull(i.seizure_datetime),
          seizure_location: orNull(i.seizure_location),
        })),
      });
      setRegistered({ id: res.data.case.id, case_number: res.data.case.case_number });
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("m.commitError"));
      setCommitting(false);
    }
  }

  function startAnother() {
    setMessages([]);
    setInput("");
    setDraft(EMPTY);
    setPersons([]);
    setItems([]);
    setTouched(new Set());
    setRegistered(null);
    setCommitting(false);
    setError(null);
  }

  /* ---- registered ---- */
  if (registered) {
    return (
      <div className="min-h-screen bg-background text-on-background px-4 py-6 max-w-md mx-auto">
        <Header right={<LangSwitch />} />
        <div className="border border-primary rounded p-5 text-center">
          <span className="material-symbols-outlined text-primary text-5xl">task_alt</span>
          <p className="font-headline-md text-on-surface mt-2">{t("m.registered")}</p>
          <p className="font-mono-lg text-primary mt-1">{registered.case_number}</p>
          <p className="font-body-md text-on-surface-variant mt-3">{t("m.registeredHint")}</p>
        </div>
        <button
          onClick={startAnother}
          className="mt-6 w-full min-h-[56px] rounded bg-primary text-on-primary font-label-lg"
        >
          {t("m.another")}
        </button>
      </div>
    );
  }

  /* ---- capture ---- */
  return (
    <div className="min-h-screen bg-background text-on-background px-4 py-6 max-w-md mx-auto">
      <Header
        right={
          <button
            onClick={logout}
            className="min-h-[40px] px-3 rounded border border-outline-variant font-label-caps text-on-surface-variant"
          >
            {t("m.signOut")}
          </button>
        }
      />
      <p className="font-body-md text-on-surface-variant -mt-3 mb-5">
        {user?.full_name}
      </p>

      <LangSwitch />

      <section className="mt-5">
        <label className="font-label-caps text-on-surface-variant">{t("m.describe")}</label>
        <textarea
          rows={5}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder={t("m.placeholder")}
          className="mt-1 w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-lg text-on-surface focus:outline-none focus:border-primary resize-y"
        />
        <button
          onClick={send}
          disabled={extracting || !input.trim()}
          className="mt-3 w-full min-h-[56px] rounded bg-primary text-on-primary font-label-lg disabled:opacity-40"
        >
          {t("m.send")}
        </button>
      </section>

      <div className="mt-4">
        {/* The same wait the desktop shows — reused, not reimplemented. */}
        <ExtractionProgress active={extracting} />
      </div>

      {error && (
        <p role="alert" className="font-body-md text-error flex items-center gap-2 mt-4">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      {!hasDraft && !extracting && (
        <p className="font-body-md text-on-surface-variant mt-6">{t("m.empty")}</p>
      )}

      {hasDraft && (
        <>
          <div className="flex items-center gap-2 mt-8 mb-3">
            <h2 className="font-label-caps text-on-surface-variant">{t("m.case")}</h2>
            <div className="flex-1 border-t border-outline-variant" />
            <span className="font-label-caps text-[9px] text-secondary border border-secondary rounded px-2 py-0.5">
              {t("m.draftBadge")}
            </span>
          </div>

          <div className="space-y-4">
            <Field label={t("m.caseNumber")} required>
              <input
                value={draft.case_number}
                onChange={(e) => setField("case_number", e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label={t("m.firNumber")}>
              <input
                value={draft.fir_number}
                onChange={(e) => setField("fir_number", e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label={t("m.location")}>
              <input
                value={draft.incident_location}
                onChange={(e) => setField("incident_location", e.target.value)}
                className={inputCls}
              />
            </Field>
            <Field label={t("m.narrative")}>
              <textarea
                rows={4}
                value={draft.complaint_narrative}
                onChange={(e) => setField("complaint_narrative", e.target.value)}
                className={inputCls + " resize-y py-3"}
              />
            </Field>
            {(draft.police_station || draft.district) && (
              <p className="font-body-md text-on-surface-variant flex items-center gap-2">
                <span className="material-symbols-outlined text-base">local_police</span>
                {[draft.police_station, draft.district].filter(Boolean).join(" · ")}
              </p>
            )}
          </div>

          {persons.length > 0 && (
            <>
              <h2 className="font-label-caps text-on-surface-variant mt-8 mb-3">
                {t("m.people")}
              </h2>
              <div className="space-y-3">
                {persons.map((p) => (
                  <div key={p._key} className="border border-outline-variant rounded p-3 space-y-2">
                    <input
                      value={p.full_name}
                      onChange={(e) =>
                        setPersons((prev) =>
                          prev.map((r) =>
                            r._key === p._key
                              ? { ...r, full_name: e.target.value, _touched: true }
                              : r,
                          ),
                        )
                      }
                      className={inputCls}
                    />
                    <select
                      value={p.role}
                      onChange={(e) =>
                        setPersons((prev) =>
                          prev.map((r) =>
                            r._key === p._key ? { ...r, role: e.target.value, _touched: true } : r,
                          ),
                        )
                      }
                      className={inputCls}
                    >
                      {PERSON_ROLES.map((r) => (
                        <option key={r} value={r}>
                          {t(`person.${r}.one` as TKey)}
                        </option>
                      ))}
                    </select>
                  </div>
                ))}
              </div>
            </>
          )}

          {items.length > 0 && (
            <>
              <h2 className="font-label-caps text-on-surface-variant mt-8 mb-3">{t("m.items")}</h2>
              <div className="space-y-3">
                {items.map((i) => (
                  <input
                    key={i._key}
                    value={i.description}
                    onChange={(e) =>
                      setItems((prev) =>
                        prev.map((r) =>
                          r._key === i._key
                            ? { ...r, description: e.target.value, _touched: true }
                            : r,
                        ),
                      )
                    }
                    className={inputCls}
                  />
                ))}
              </div>
            </>
          )}

          <p className="font-body-md text-on-surface-variant mt-8">{t("m.confirmHint")}</p>
          <button
            onClick={register}
            disabled={committing}
            className="mt-3 mb-10 w-full min-h-[56px] rounded bg-primary text-on-primary font-label-lg disabled:opacity-40"
          >
            {committing ? t("m.registering") : t("m.register")}
          </button>
        </>
      )}
    </div>
  );
}

const inputCls =
  "w-full min-h-[48px] bg-surface-container-low border border-outline-variant rounded px-4 font-body-lg text-on-surface focus:outline-none focus:border-primary";

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  const { t } = useI18n();
  return (
    <label className="block">
      <span className="font-label-caps text-on-surface-variant">
        {label}
        {required && <span className="text-error ml-1">{t("m.required")}</span>}
      </span>
      <div className="mt-1">{children}</div>
    </label>
  );
}

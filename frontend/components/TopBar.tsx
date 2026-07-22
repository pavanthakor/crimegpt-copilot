"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { statusMeta } from "@/lib/cases";
import { LANGS, LANG_GLYPH, useI18n, type TKey } from "@/lib/i18n";
import { useAuth } from "./AuthProvider";

export default function TopBar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const { lang, setLang, t } = useI18n();

  // Role label keys are role.IO / role.SHO / role.LEGAL_ADVISOR; fall back to the raw
  // code for any unexpected role rather than showing a stray key.
  const roleTitle = user
    ? ["IO", "SHO", "LEGAL_ADVISOR"].includes(user.role)
      ? t(`role.${user.role}` as TKey)
      : user.role
    : "";

  return (
    <header className="fixed top-0 right-0 left-0 ml-[280px] h-16 bg-surface-bright border-b border-outline-variant flex items-center justify-between gap-4 px-edge-margin z-40">
      {/* Search — flex-1 + min-w-0 so it shrinks to give the right cluster room instead
          of forcing it to wrap onto a second line (the 1440px cramping bug). */}
      <div className="flex items-center min-w-0 flex-1 max-w-2xl">
        <GlobalSearch />
      </div>

      {/* Right cluster never wraps (shrink-0); the search yields space, not this. */}
      <div className="flex items-center gap-4 shrink-0">
        {/* DEMO_MODE toggle (SHO only) — always shows which mode is active at a glance. */}
        <DemoModeControl />

        {/* Language selector: EN | हिं | ગુ — drives the whole interface + AI lang param */}
        <div
          className="flex items-center rounded border border-outline-variant overflow-hidden"
          role="group"
          aria-label={t("topbar.langAria")}
        >
          {LANGS.map((code) => {
            const on = lang === code;
            return (
              <button
                key={code}
                type="button"
                onClick={() => setLang(code)}
                aria-pressed={on}
                className={
                  (on
                    ? "bg-primary text-on-primary "
                    : "bg-transparent text-on-surface-variant hover:bg-surface-container ") +
                  "px-3 py-1.5 font-body-md leading-none transition-colors"
                }
              >
                {LANG_GLYPH[code]}
              </button>
            );
          })}
        </div>

        {/* Officer name + role badge */}
        {user && (
          <div className="flex items-center gap-3 pl-2 border-l border-outline-variant">
            <div className="flex flex-col items-end min-w-0">
              <p className="font-body-md text-on-surface leading-none whitespace-nowrap">
                {user.full_name}
              </p>
              <span className="mt-1 font-label-caps text-[10px] text-secondary bg-secondary-container px-1.5 py-0.5 rounded">
                {roleTitle}
              </span>
            </div>
            <div className="h-9 w-9 bg-surface-container-highest border border-outline-variant flex items-center justify-center rounded">
              <span className="material-symbols-outlined text-primary">account_circle</span>
            </div>
          </div>
        )}

        {/* Sign out */}
        <button
          type="button"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="flex items-center gap-1 text-on-surface-variant hover:text-error transition-colors"
          title={t("topbar.signOut")}
        >
          <span className="material-symbols-outlined">logout</span>
          <span className="font-body-md">{t("topbar.signOut")}</span>
        </button>
      </div>
    </header>
  );
}

/* ---------------- DEMO_MODE toggle (SHO only) ---------------- */

// Shows the current inference mode unmistakably and toggles it at runtime (no backend
// restart). "Cached demo" = pre-generated instant outputs; "Live AI" = real model calls.
// The two states differ in colour, icon and label so the active mode is never ambiguous.
function DemoModeControl() {
  const { user } = useAuth();
  const { t } = useI18n();
  const [cached, setCached] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const isSho = user?.role === "SHO";

  useEffect(() => {
    if (!isSho) return;
    api
      .get<{ demo_mode: boolean }>("/api/system/demo-mode")
      .then((r) => setCached(r.data.demo_mode))
      .catch(() => setCached(null));
  }, [isSho]);

  // Not an SHO, or state not yet known -> render nothing (IO/Legal never see it).
  if (!isSho || cached === null) return null;

  async function toggle() {
    if (busy) return;
    setBusy(true);
    try {
      const r = await api.patch<{ demo_mode: boolean }>("/api/system/demo-mode", {
        demo_mode: !cached,
      });
      setCached(r.data.demo_mode);
    } catch {
      /* leave the displayed state unchanged on failure */
    } finally {
      setBusy(false);
    }
  }

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={busy}
      aria-pressed={cached}
      title={cached ? t("demo.switchToLive") : t("demo.switchToCached")}
      className={
        "flex items-center gap-2 rounded px-3 py-1.5 font-label-caps text-[10px] transition-colors disabled:opacity-60 " +
        (cached
          ? "bg-secondary-container text-on-secondary-container"
          : "bg-primary text-on-primary")
      }
    >
      <span
        className={
          "inline-block w-1.5 h-1.5 rounded-full " +
          (cached ? "bg-on-secondary-container" : "bg-surface-bright")
        }
      />
      <span className="material-symbols-outlined text-sm">
        {cached ? "inventory_2" : "bolt"}
      </span>
      {cached ? t("demo.cached") : t("demo.live")}
    </button>
  );
}

/* ---------------- Global search ---------------- */

// Backend contract (CLAUDE.md §7): GET /api/cases/search -> [SearchHit], each a matched
// case plus WHICH field matched and a context snippet — NOT a plain case list. We show
// the field and the context with the query highlighted so an officer sees why each case
// surfaced ("Person · Suresh Vaghela"), then click through to the case.
type CaseHit = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
};
type SearchHit = {
  case: CaseHit;
  matched_field: string;
  matched_value: string | null;
};

function GlobalSearch() {
  const router = useRouter();
  const { t } = useI18n();
  const [q, setQ] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [loading, setLoading] = useState(false);
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const boxRef = useRef<HTMLDivElement>(null);

  // Debounced search; a request id guards against out-of-order responses.
  useEffect(() => {
    const query = q.trim();
    if (query.length === 0) {
      setHits([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    const reqId = ++reqCounter;
    const timer = window.setTimeout(() => {
      api
        .get<SearchHit[]>("/api/cases/search", { params: { q: query } })
        .then((r) => {
          if (reqId !== reqCounter) return; // a newer keystroke superseded this
          setHits(r.data);
          setActive(0);
        })
        .catch(() => {
          if (reqId === reqCounter) setHits([]);
        })
        .finally(() => {
          if (reqId === reqCounter) setLoading(false);
        });
    }, 250);
    return () => window.clearTimeout(timer);
  }, [q]);

  // Close on outside click.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (boxRef.current && !boxRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  function go(hit: SearchHit) {
    setOpen(false);
    setQ("");
    setHits([]);
    router.push(`/cases/${hit.case.id}`);
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (!open) return;
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, hits.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter" && hits[active]) {
      e.preventDefault();
      go(hits[active]);
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  }

  const showPanel = open && q.trim().length > 0;

  return (
    <div ref={boxRef} className="relative flex-grow">
      <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-xl">
        search
      </span>
      <input
        type="text"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={onKeyDown}
        placeholder={t("topbar.searchPlaceholder")}
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="global-search-results"
        className="w-full bg-surface-container-low border-none rounded focus:ring-1 focus:ring-primary pl-12 pr-4 py-2 font-body-md text-on-surface placeholder:text-on-surface-variant"
      />

      {showPanel && (
        <div
          id="global-search-results"
          role="listbox"
          className="absolute left-0 right-0 top-full mt-2 bg-surface-bright border border-outline-variant rounded shadow-lg overflow-hidden z-50 max-h-[70vh] overflow-y-auto"
        >
          {loading && hits.length === 0 ? (
            <p className="px-4 py-3 font-body-md text-on-surface-variant flex items-center gap-2">
              <span className="material-symbols-outlined animate-spin text-lg">
                progress_activity
              </span>
              {t("topbar.searching")}
            </p>
          ) : hits.length === 0 ? (
            <p className="px-4 py-3 font-body-md text-on-surface-variant">
              {t("topbar.noMatch", { q: q.trim() })}
            </p>
          ) : (
            <ul>
              {hits.map((h, i) => {
                const meta = statusMeta(h.case.status);
                return (
                  <li key={`${h.case.id}-${h.matched_field}`} role="option" aria-selected={i === active}>
                    <button
                      type="button"
                      onMouseEnter={() => setActive(i)}
                      onClick={() => go(h)}
                      className={
                        "w-full text-left px-4 py-3 border-b border-outline-variant last:border-0 transition-colors " +
                        (i === active ? "bg-surface-container-low" : "hover:bg-surface-container-low")
                      }
                    >
                      <div className="flex items-center gap-2">
                        <span className="font-mono-data text-primary">{h.case.case_number}</span>
                        <span className={`inline-block w-1.5 h-1.5 rounded-full ${meta.dot}`} />
                        <span className="font-body-md text-on-surface truncate">
                          {h.case.title ?? t("common.untitled")}
                        </span>
                      </div>
                      <p className="font-body-md text-on-surface-variant mt-0.5 flex items-baseline gap-2">
                        <span className="font-label-caps text-[9px] text-on-surface-variant border border-outline-variant rounded px-1.5 py-0.5">
                          {fieldLabel(h.matched_field, t)}
                        </span>
                        <span className="truncate">
                          <Highlight text={h.matched_value ?? ""} query={q.trim()} />
                        </span>
                      </p>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function fieldLabel(field: string, t: (k: TKey) => string): string {
  const known = ["case_number", "title", "complaint_narrative", "person_name", "seized_item"];
  return known.includes(field) ? t(`search.field.${field}` as TKey) : field;
}

// Module-level counter so the newest keystroke's response always wins.
let reqCounter = 0;

// Wrap case-insensitive occurrences of `query` in <mark> so the officer sees exactly
// what matched inside the context snippet.
function Highlight({ text, query }: { text: string; query: string }) {
  if (!query || !text) return <>{text}</>;
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const parts: React.ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < text.length) {
    const idx = lower.indexOf(q, i);
    if (idx === -1) {
      parts.push(<span key={key++}>{text.slice(i)}</span>);
      break;
    }
    if (idx > i) parts.push(<span key={key++}>{text.slice(i, idx)}</span>);
    parts.push(
      <mark key={key++} className="bg-accent/[0.35] text-on-surface rounded-sm px-0.5">
        {text.slice(idx, idx + q.length)}
      </mark>
    );
    i = idx + q.length;
  }
  return <>{parts}</>;
}

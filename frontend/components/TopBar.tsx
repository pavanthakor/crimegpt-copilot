"use client";
import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { statusMeta } from "@/lib/cases";
import { useAuth } from "./AuthProvider";

type Lang = "EN" | "HI" | "GU";

// Label carries the native script so the selector itself exercises the Indic fonts.
const LANGS: { code: Lang; label: string }[] = [
  { code: "EN", label: "EN" },
  { code: "HI", label: "हिं" },
  { code: "GU", label: "ગુ" },
];

const ROLE_LABEL: Record<string, string> = {
  IO: "Investigating Officer",
  SHO: "Station House Officer",
  LEGAL_ADVISOR: "Legal Advisor",
};

export default function TopBar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  // State only for now — switching behaviour comes in a later slice.
  const [lang, setLang] = useState<Lang>("EN");

  const roleTitle = user ? ROLE_LABEL[user.role] ?? user.role : "";

  return (
    <header className="fixed top-0 right-0 left-0 ml-[280px] h-16 bg-surface-bright border-b border-outline-variant flex items-center justify-between px-edge-margin z-40">
      {/* Search */}
      <div className="flex items-center gap-8 w-full max-w-2xl">
        <GlobalSearch />
      </div>

      <div className="flex items-center gap-5">
        {/* Language selector: EN | हिं | ગુ */}
        <div
          className="flex items-center rounded border border-outline-variant overflow-hidden"
          role="group"
          aria-label="Language"
        >
          {LANGS.map((l) => {
            const on = lang === l.code;
            return (
              <button
                key={l.code}
                type="button"
                onClick={() => setLang(l.code)}
                aria-pressed={on}
                className={
                  (on
                    ? "bg-primary text-on-primary "
                    : "bg-transparent text-on-surface-variant hover:bg-surface-container ") +
                  "px-3 py-1.5 font-body-md leading-none transition-colors"
                }
              >
                {l.label}
              </button>
            );
          })}
        </div>

        {/* Officer name + role badge */}
        {user && (
          <div className="flex items-center gap-3 pl-2 border-l border-outline-variant">
            <div className="flex flex-col items-end">
              <p className="font-body-md text-on-surface leading-none">{user.full_name}</p>
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
          title="Sign out"
        >
          <span className="material-symbols-outlined">logout</span>
          <span className="font-body-md">Sign out</span>
        </button>
      </div>
    </header>
  );
}

/* ---------------- Global search ---------------- */

// Backend contract (CLAUDE.md §7): GET /api/cases/search -> [SearchHit], each a matched
// case plus WHICH field matched and a context snippet — NOT a plain case list. We show
// the field and the context with the query highlighted so an officer sees why each case
// surfaced ("accused · Suresh Vaghela"), then click through to the case.
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

const FIELD_LABEL: Record<string, string> = {
  case_number: "Case #",
  title: "Title",
  complaint_narrative: "Narrative",
  person_name: "Person",
  seized_item: "Seized item",
};

function GlobalSearch() {
  const router = useRouter();
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
    const t = window.setTimeout(() => {
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
    return () => window.clearTimeout(t);
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
        placeholder="Search cases, persons, or seized items…"
        role="combobox"
        aria-expanded={showPanel}
        aria-controls="global-search-results"
        className="w-full bg-surface-container-low border-none rounded focus:ring-1 focus:ring-primary pl-12 pr-4 py-2 font-body-md text-on-surface placeholder:text-outline"
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
              Searching…
            </p>
          ) : hits.length === 0 ? (
            <p className="px-4 py-3 font-body-md text-on-surface-variant">
              No cases match &ldquo;{q.trim()}&rdquo;.
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
                          {h.case.title ?? "Untitled case"}
                        </span>
                      </div>
                      <p className="font-body-md text-on-surface-variant mt-0.5 flex items-baseline gap-2">
                        <span className="font-label-caps text-[9px] text-on-surface-variant border border-outline-variant rounded px-1.5 py-0.5">
                          {FIELD_LABEL[h.matched_field] ?? h.matched_field}
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

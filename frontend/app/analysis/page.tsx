"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { CaseSelect, useCasePicker } from "@/components/CasePicker";
import { reasonRestatesTitle } from "@/lib/cases";

// A read-only AI overview: one place to see the legal-intelligence output for a case —
// accepted/suggested sections, landmark judgments, weak-charge alerts and the
// cross-document consistency check (CLAUDE.md §4 Tier 2 differentiators). Accept/reject
// still lives in the case workspace; this page links there rather than duplicating it.

type Section = {
  id: number;
  act: string;
  section_code: string | null;
  section_title: string | null;
  reason: string | null;
  confidence: number | null;
  status: "SUGGESTED" | "ACCEPTED" | "REJECTED";
};
type Judgment = {
  id: number;
  title: string | null;
  citation: string | null;
  court: string | null;
  relevance_reason: string | null;
};
type Inconsistency = {
  field: string;
  severity: string;
  values: Record<string, string | null>;
  note: string;
};
type ConsistencyResult = {
  inconsistencies: Inconsistency[];
  checked_documents: number;
  status: string;
};
type WeakAlert = {
  section_code: string | null;
  citation: string | null;
  missing_ingredients: string[];
  severity: string;
  suggestion: string | null;
};

const POOL_KEY = "current_pool";

export default function AnalysisPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const { cases, loading: casesLoading, error: casesError, selected, setSelected } =
    useCasePicker();

  const [sections, setSections] = useState<Section[] | null>(null);
  const [judgments, setJudgments] = useState<Judgment[] | null>(null);
  const [consistency, setConsistency] = useState<ConsistencyResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Load the cheap, read-only intelligence (sections / judgments / consistency are pure
  // DB reads). Weak charges runs a live LLM check, so it stays behind a button below.
  const load = useCallback(() => {
    if (selected == null) return;
    setLoading(true);
    setError(null);
    setSections(null);
    setJudgments(null);
    setConsistency(null);
    Promise.all([
      api.get<Section[]>(`/api/cases/${selected}/sections`),
      api.get<Judgment[]>(`/api/cases/${selected}/judgments`),
      api.get<ConsistencyResult>(`/api/cases/${selected}/consistency`),
    ])
      .then(([s, j, c]) => {
        setSections(s.data);
        setJudgments(j.data);
        setConsistency(c.data);
      })
      .catch((e) => setError(e?.response?.data?.detail ?? "Could not load the analysis."))
      .finally(() => setLoading(false));
  }, [selected]);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    load();
  }, [ready, user, router, load]);

  if (!ready || !user) return null;

  const accepted = (sections ?? []).filter((s) => s.status === "ACCEPTED");
  const suggested = (sections ?? []).filter((s) => s.status === "SUGGESTED");

  return (
    <div className="space-y-8">
      <div>
        <h1 className="font-headline-lg text-primary">AI analysis</h1>
        <p className="font-body-md text-on-surface-variant mt-1">
          The legal-intelligence picture for a case — sections, authorities, weak charges
          and cross-document consistency, in one place.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-4">
        {casesLoading ? (
          <span className="font-body-md text-on-surface-variant">Loading cases…</span>
        ) : cases.length === 0 ? (
          <span className="font-body-md text-on-surface-variant">No cases to analyse yet.</span>
        ) : (
          <>
            <CaseSelect cases={cases} value={selected} onChange={setSelected} />
            {selected != null && (
              <Link
                href={`/cases/${selected}?tab=sections`}
                className="flex items-center gap-1 font-body-md text-primary hover:underline"
              >
                Open in case workspace
                <span className="material-symbols-outlined text-lg">arrow_forward</span>
              </Link>
            )}
          </>
        )}
      </div>

      {casesError && <ErrorLine message={casesError} />}
      {error && <ErrorLine message={error} />}

      {selected == null ? null : loading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 animate-pulse">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-56 bg-surface-container-high rounded" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-start">
          {/* Sections */}
          <Panel
            icon="gavel"
            title="Legal sections"
            subtitle={`${accepted.length} accepted · ${suggested.length} suggested`}
          >
            {accepted.length === 0 && suggested.length === 0 ? (
              <Empty text="No sections analysed for this case yet." />
            ) : (
              <div className="space-y-3">
                {accepted.map((s) => (
                  <SectionRow key={s.id} s={s} />
                ))}
                {suggested.map((s) => (
                  <SectionRow key={s.id} s={s} />
                ))}
              </div>
            )}
          </Panel>

          {/* Judgments */}
          <Panel
            icon="menu_book"
            title="Landmark judgments"
            subtitle={`${judgments?.length ?? 0} on file`}
          >
            {!judgments || judgments.length === 0 ? (
              <Empty text="No judgments attached to this case yet." />
            ) : (
              <ul className="space-y-4">
                {judgments.map((j) => (
                  <li key={j.id} className="border-b border-outline-variant last:border-0 pb-4 last:pb-0">
                    <h4 className="font-serif text-body-lg text-primary">{j.title}</h4>
                    <p className="font-mono-data text-on-surface-variant mt-0.5">
                      {[j.citation, j.court].filter(Boolean).join("  ·  ")}
                    </p>
                    {j.relevance_reason && (
                      <p className="font-body-md text-on-surface mt-1.5 leading-relaxed">
                        {j.relevance_reason}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </Panel>

          {/* Consistency */}
          <ConsistencyPanel result={consistency} />

          {/* Weak charges (on-demand LLM) */}
          <WeakChargePanel caseId={selected} />
        </div>
      )}
    </div>
  );
}

function SectionRow({ s }: { s: Section }) {
  const accepted = s.status === "ACCEPTED";
  const conf = s.confidence != null ? Math.round(s.confidence * 100) : null;
  const reason = reasonRestatesTitle(s.reason, s.section_title) ? null : s.reason;
  return (
    <div
      className={
        "rounded p-4 " +
        (accepted
          ? "border-2 border-primary bg-surface-container-lowest"
          : "border border-outline-variant bg-surface-container-lowest")
      }
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="font-mono-data text-on-surface">
            {s.act} {s.section_code}
          </span>
          <h4 className="font-serif text-body-lg text-primary mt-0.5">
            {s.section_title ?? "—"}
          </h4>
        </div>
        <div className="text-right shrink-0">
          <span
            className={
              "inline-flex items-center gap-1 font-label-caps text-[10px] rounded px-2 py-0.5 " +
              (accepted
                ? "text-on-primary bg-primary"
                : "text-on-secondary-container bg-secondary-container")
            }
          >
            {accepted ? "Accepted" : "Suggested"}
          </span>
          {conf != null && (
            <p className="font-mono-sm text-on-surface-variant mt-1">{conf}% conf.</p>
          )}
        </div>
      </div>
      {reason && (
        <p className="font-body-md text-on-surface-variant mt-2 leading-relaxed">{reason}</p>
      )}
    </div>
  );
}

function ConsistencyPanel({ result }: { result: ConsistencyResult | null }) {
  const issues = result?.inconsistencies ?? [];
  return (
    <Panel
      icon="rule"
      title="Consistency check"
      subtitle={
        result
          ? `${result.checked_documents} document(s) checked`
          : "—"
      }
    >
      {!result ? (
        <Empty text="Consistency data unavailable." />
      ) : issues.length === 0 ? (
        <div className="flex items-center gap-2 font-body-md text-on-surface">
          <span className="material-symbols-outlined text-primary">verified</span>
          {result.checked_documents === 0
            ? "No documents generated yet — nothing to cross-check."
            : "Every document agrees with the current record."}
        </div>
      ) : (
        <ul className="space-y-4">
          {issues.map((inc, i) => (
            <InconsistencyCard key={i} inc={inc} />
          ))}
        </ul>
      )}
    </Panel>
  );
}

function InconsistencyCard({ inc }: { inc: Inconsistency }) {
  const high = inc.severity.toLowerCase() === "high";
  // Separate the live pool value ("current record") from each document's stale snapshot.
  const current = inc.values[POOL_KEY];
  const docEntries = Object.entries(inc.values).filter(([k]) => k !== POOL_KEY);
  return (
    <li
      className={
        "rounded border p-4 " +
        (high ? "border-error/40 bg-error-container/40" : "border-outline-variant bg-surface-container")
      }
    >
      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="font-mono-data text-primary">{inc.field}</span>
        <span
          className={
            "inline-flex items-center gap-1 font-label-caps text-[10px] rounded px-2 py-0.5 " +
            (high
              ? "text-on-error-container bg-error-container"
              : "text-on-surface-variant border border-outline-variant")
          }
        >
          <span className="material-symbols-outlined text-sm">
            {high ? "priority_high" : "info"}
          </span>
          {high ? "High" : "Low"}
        </span>
      </div>

      <div className="space-y-1.5">
        {docEntries.map(([label, value]) => (
          <div key={label} className="flex items-baseline gap-2 font-body-md">
            <span className="font-label-caps text-[9px] text-on-surface-variant w-32 shrink-0">
              {label}
            </span>
            <span className="text-on-surface-variant line-through">{value ?? "(empty)"}</span>
          </div>
        ))}
        {current !== undefined && (
          <div className="flex items-baseline gap-2 font-body-md pt-1.5 mt-1.5 border-t border-outline-variant">
            <span className="font-label-caps text-[9px] text-primary w-32 shrink-0">
              Current record
            </span>
            <span className="text-on-surface font-medium">{current ?? "(empty)"}</span>
          </div>
        )}
      </div>

      <p className="font-body-md text-on-surface-variant mt-2">{inc.note}</p>
    </li>
  );
}

function WeakChargePanel({ caseId }: { caseId: number }) {
  const [alerts, setAlerts] = useState<WeakAlert[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset when the selected case changes.
  useEffect(() => {
    setAlerts(null);
    setStatus(null);
    setError(null);
  }, [caseId]);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get(`/api/cases/${caseId}/weak-charges`);
      setAlerts(r.data.alerts ?? []);
      setStatus(r.data.status);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Could not run the weak-charge check.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <Panel
      icon="gpp_maybe"
      title="Weak-charge alerts"
      subtitle="Accepted charges not yet established by the file"
      action={
        <button
          type="button"
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-3 py-1.5 rounded font-body-md border border-outline-variant text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-60"
        >
          {loading ? (
            <>
              <span className="material-symbols-outlined animate-spin text-lg">
                progress_activity
              </span>
              Checking…
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-lg">bolt</span>
              {alerts ? "Re-check" : "Run check"}
            </>
          )}
        </button>
      }
    >
      {error && <ErrorLine message={error} />}
      {alerts == null && !loading && !error && (
        <Empty text="Run the check to test each accepted section's ingredients against the file. This calls the AI model." />
      )}
      {alerts != null && alerts.length === 0 && !error && (
        <div className="flex items-center gap-2 font-body-md text-on-surface">
          <span className="material-symbols-outlined text-primary">verified</span>
          {status === "no_issues"
            ? "Every accepted charge is supported by the file."
            : "No weak charges found."}
        </div>
      )}
      {alerts && alerts.length > 0 && (
        <ul className="space-y-3">
          {alerts.map((a, i) => {
            const high = (a.severity ?? "").toLowerCase() === "high";
            return (
              <li
                key={i}
                className={
                  "rounded border p-4 " +
                  (high
                    ? "border-error/40 bg-error-container/40"
                    : "border-outline-variant bg-surface-container")
                }
              >
                <div className="flex items-center justify-between gap-3 mb-2">
                  <span className="font-mono-data text-primary">
                    {a.citation ?? a.section_code}
                  </span>
                  <span
                    className={
                      "inline-flex items-center gap-1 font-label-caps text-[10px] rounded px-2 py-0.5 " +
                      (high
                        ? "text-on-error-container bg-error-container"
                        : "text-on-surface-variant border border-outline-variant")
                    }
                  >
                    {high ? "High risk" : "Low risk"}
                  </span>
                </div>
                {a.missing_ingredients.length > 0 && (
                  <ul className="space-y-1 mb-2">
                    {a.missing_ingredients.map((ing, j) => (
                      <li key={j} className="flex items-start gap-2 font-body-md text-on-surface">
                        <span className="material-symbols-outlined text-error text-base mt-0.5">
                          remove_circle
                        </span>
                        <span className="italic">&ldquo;{ing}&rdquo;</span>
                      </li>
                    ))}
                  </ul>
                )}
                {a.suggestion && (
                  <p className="font-body-md text-on-surface-variant">{a.suggestion}</p>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Panel>
  );
}

/* ---------------- shared bits ---------------- */

function Panel({
  icon,
  title,
  subtitle,
  action,
  children,
}: {
  icon: string;
  title: string;
  subtitle?: string;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="border border-outline-variant rounded bg-surface-container-lowest">
      <div className="flex items-center justify-between gap-3 px-5 py-4 border-b border-outline-variant">
        <div className="flex items-center gap-3 min-w-0">
          <span className="material-symbols-outlined text-primary">{icon}</span>
          <div className="min-w-0">
            <h3 className="font-headline-md text-primary leading-tight">{title}</h3>
            {subtitle && (
              <p className="font-body-md text-on-surface-variant leading-tight">{subtitle}</p>
            )}
          </div>
        </div>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <p className="font-body-md text-on-surface-variant">{text}</p>;
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-center gap-2 font-body-md text-error mb-3">
      <span className="material-symbols-outlined text-base">error</span>
      {message}
    </p>
  );
}

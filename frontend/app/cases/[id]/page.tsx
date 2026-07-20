"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { CASE_STATUSES, statusMeta } from "@/lib/cases";
import CaseDetailsTab from "./CaseDetailsTab";
import LegalSectionsTab from "./LegalSectionsTab";
import DocumentsTab from "./DocumentsTab";

type Person = {
  id: number;
  role: string;
  full_name: string | null;
  alias: string | null;
  father_name: string | null;
  age: number | null;
  gender: string | null;
  address: string | null;
  phone: string | null;
  occupation: string | null;
};
type Statement = {
  id: number;
  person_id: number | null;
  statement_type: string;
  statement_text: string | null;
  language: string | null;
  recorded_at: string | null;
};
type CaseDetail = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
  case_type: string;
  fir_number: string | null;
  fir_date: string | null;
  police_station: string | null;
  district: string | null;
  incident_datetime: string | null;
  incident_location: string | null;
  complaint_narrative: string | null;
  complaint_language: string | null;
  created_by_name: string | null;
  persons: Person[];
  seized_items: unknown[];
  statements: Statement[];
  documents: unknown[];
  diary_entries: unknown[];
};

type TabKey = "details" | "evidence" | "sections" | "documents" | "diary";
const TABS: { key: TabKey; label: string }[] = [
  { key: "details", label: "Case details" },
  { key: "evidence", label: "Evidence" },
  { key: "sections", label: "Legal sections" },
  { key: "documents", label: "Documents" },
  { key: "diary", label: "Case diary" },
];
const TAB_KEYS = TABS.map((t) => t.key);

export default function CaseWorkspacePage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const searchParams = useSearchParams();

  const [data, setData] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  // Counts not carried by the case detail payload (fetched alongside).
  const [evidenceCount, setEvidenceCount] = useState(0);
  const [sectionsCount, setSectionsCount] = useState(0);

  // Active tab lives in the URL (?tab=) so a reload keeps position.
  const rawTab = searchParams.get("tab");
  const tab: TabKey = (TAB_KEYS as string[]).includes(rawTab ?? "")
    ? (rawTab as TabKey)
    : "details";

  const setTab = useCallback(
    (key: TabKey) => {
      const p = new URLSearchParams(searchParams.toString());
      p.set("tab", key);
      router.replace(`/cases/${params.id}?${p.toString()}`, { scroll: false });
    },
    [router, params.id, searchParams]
  );

  // `silent` reloads after a mutation without flashing the skeleton, so the persons
  // list / stat strip / tab badges refresh in place.
  const load = useCallback(
    (silent = false) => {
      if (!silent) setLoading(true);
      setError(null);
      Promise.all([
        api.get<CaseDetail>(`/api/cases/${params.id}`),
        api.get<unknown[]>(`/api/cases/${params.id}/evidence`).catch(() => ({ data: [] })),
        api.get<unknown[]>(`/api/cases/${params.id}/sections`).catch(() => ({ data: [] })),
      ])
        .then(([c, ev, sec]) => {
          setData(c.data);
          setEvidenceCount((ev.data as unknown[]).length);
          setSectionsCount((sec.data as unknown[]).length);
        })
        .catch((e) =>
          setError(e?.response?.data?.detail ?? "The case could not be loaded.")
        )
        .finally(() => {
          if (!silent) setLoading(false);
        });
    },
    [params.id]
  );

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    load();
  }, [ready, user, router, load]);

  if (!ready || !user) return null;
  if (loading) return <WorkspaceSkeleton />;
  if (error || !data) return <WorkspaceError message={error} onRetry={load} />;

  const witnesses = data.persons.filter((p) => p.role === "WITNESS").length;
  const evidenceTotal = evidenceCount + data.seized_items.length;

  const stats = [
    { label: "Evidence", value: evidenceTotal, sub: `${data.seized_items.length} seized` },
    { label: "Documents", value: data.documents.length, sub: "generated" },
    { label: "Witnesses", value: witnesses, sub: `${data.statements.length} statements` },
    { label: "AI findings", value: sectionsCount, sub: "sections", accent: true },
  ];

  const tabCounts: Partial<Record<TabKey, number>> = {
    evidence: evidenceTotal,
    sections: sectionsCount,
    documents: data.documents.length,
    diary: data.diary_entries.length,
  };

  return (
    <div className="-mx-edge-margin -my-stack-lg">
      {/* A status change also appends a diary entry server-side; a silent reload keeps
          the status, diary badge and stat strip honest without a skeleton flash. */}
      <Header data={data} onStatusChanged={() => load(true)} />

      {/* Stat strip */}
      <div className="px-edge-margin py-6 bg-surface border-b border-outline-variant">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-px bg-outline-variant border border-outline-variant">
          {stats.map((s) => (
            <div key={s.label} className="bg-surface-container-lowest p-5">
              <p className="font-label-caps text-[10px] text-on-surface-variant mb-1">
                {s.label}
              </p>
              <div className="flex items-baseline gap-2">
                <span
                  className={`font-display-case text-3xl ${s.accent ? "text-primary" : "text-on-surface"}`}
                >
                  {String(s.value).padStart(2, "0")}
                </span>
                <span className="font-mono-sm text-on-surface-variant">{s.sub}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Tabs */}
      <div className="px-edge-margin bg-surface-bright border-b border-outline-variant flex overflow-x-auto">
        {TABS.map((t) => {
          const active = t.key === tab;
          const count = tabCounts[t.key];
          return (
            <button
              key={t.key}
              type="button"
              onClick={() => setTab(t.key)}
              className={
                "px-5 py-4 font-body-md whitespace-nowrap border-b-2 transition-colors flex items-center gap-2 " +
                (active
                  ? "border-primary text-primary font-bold"
                  : "border-transparent text-on-surface-variant hover:text-primary")
              }
              aria-current={active ? "page" : undefined}
            >
              {t.label}
              {count ? (
                <span
                  className={
                    "font-mono-sm px-1.5 py-0.5 rounded-full " +
                    (active
                      ? "bg-primary text-on-primary"
                      : "bg-surface-container-high text-on-surface-variant")
                  }
                >
                  {count}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Tab content */}
      <div className="px-edge-margin py-8">
        {tab === "details" ? (
          <CaseDetailsTab
            caseId={data.id}
            narrative={data.complaint_narrative}
            language={data.complaint_language}
            persons={data.persons}
            statements={data.statements}
            onPoolChanged={() => load(true)}
          />
        ) : tab === "sections" ? (
          <LegalSectionsTab
            caseId={data.id}
            narrative={data.complaint_narrative}
            onSectionsChanged={() => load(true)}
          />
        ) : tab === "documents" ? (
          <DocumentsTab
            caseId={data.id}
            role={user.role}
            onDocsChanged={() => load(true)}
          />
        ) : (
          <TabPlaceholder label={TABS.find((t) => t.key === tab)!.label} />
        )}
      </div>
    </div>
  );
}

function Header({
  data,
  onStatusChanged,
}: {
  data: CaseDetail;
  onStatusChanged: (status: string) => void;
}) {
  const router = useRouter();
  const [saving, setSaving] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  // Optimistic select value, kept in sync when the parent reloads.
  const [selected, setSelected] = useState(data.status);
  useEffect(() => setSelected(data.status), [data.status]);
  const meta = statusMeta(selected);

  async function changeStatus(next: string) {
    if (next === selected || saving) return;
    setSaving(true);
    setErr(null);
    setSelected(next); // optimistic — avoids a revert flicker
    try {
      await api.patch(`/api/cases/${data.id}`, { status: next });
      onStatusChanged(next);
      setToast(`Status set to ${statusMeta(next).label} — added to the case diary.`);
      window.setTimeout(() => setToast(null), 4000);
    } catch (e: any) {
      setSelected(data.status); // revert
      setErr(e?.response?.data?.detail ?? "Could not update status.");
    } finally {
      setSaving(false);
    }
  }

  const metaLine = [
    data.fir_number ? `FIR ${data.fir_number}` : null,
    data.police_station,
    data.created_by_name ? `IO ${data.created_by_name}` : null,
  ].filter(Boolean);

  return (
    <section className="px-edge-margin py-8 bg-surface border-b border-outline-variant">
      <button
        type="button"
        onClick={() => router.push("/cases")}
        className="flex items-center gap-1 font-body-md text-on-surface-variant hover:text-primary transition-colors mb-4"
      >
        <span className="material-symbols-outlined text-lg">arrow_back</span>
        Back to cases
      </button>

      <div className="flex flex-wrap justify-between items-start gap-4">
        <div className="min-w-0">
          {/* Case number is the largest element, in JetBrains Mono */}
          <p className="font-mono-data text-3xl md:text-4xl text-primary tracking-tight">
            {data.case_number}
          </p>
          <h1 className="font-headline-md text-primary mt-2">
            {data.title ?? "Untitled case"}
          </h1>
          {metaLine.length > 0 && (
            <p className="font-body-md text-on-surface-variant mt-2">
              {metaLine.join("  ·  ")}
            </p>
          )}
        </div>

        {/* Status control */}
        <div className="flex flex-col items-end gap-2">
          <span className="font-label-caps text-[10px] text-on-surface-variant">Status</span>
          <div className="flex items-center gap-2 border border-outline-variant rounded px-3 py-2 bg-surface-container-lowest">
            <span className={`inline-block w-2 h-2 rounded-full ${meta.dot}`} />
            <select
              value={selected}
              disabled={saving}
              onChange={(e) => changeStatus(e.target.value)}
              className="bg-transparent font-body-md text-on-surface focus:outline-none disabled:opacity-60"
              aria-label="Case status"
            >
              {CASE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {statusMeta(s).label}
                </option>
              ))}
            </select>
            {saving && (
              <span className="material-symbols-outlined animate-spin text-lg text-on-surface-variant">
                progress_activity
              </span>
            )}
          </div>
          {toast && (
            <p
              role="status"
              className="flex items-center gap-1.5 font-body-md text-on-secondary-container bg-secondary-container px-3 py-1.5 rounded"
            >
              <span className="material-symbols-outlined text-base">check_circle</span>
              {toast}
            </p>
          )}
          {err && (
            <p role="alert" className="flex items-center gap-1.5 font-body-md text-error">
              <span className="material-symbols-outlined text-base">error</span>
              {err}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

function TabPlaceholder({ label }: { label: string }) {
  return (
    <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-20 flex flex-col items-center gap-2 text-center">
      <span className="material-symbols-outlined text-4xl text-outline">construction</span>
      <p className="font-headline-md text-primary">{label}</p>
      <p className="font-body-md text-on-surface-variant">Coming in the next slice.</p>
    </div>
  );
}

function WorkspaceSkeleton() {
  return (
    <div className="-mx-edge-margin -my-stack-lg animate-pulse">
      <div className="px-edge-margin py-8 bg-surface border-b border-outline-variant space-y-3">
        <div className="h-4 w-24 bg-surface-container-high rounded" />
        <div className="h-10 w-72 bg-surface-container-high rounded" />
        <div className="h-5 w-96 bg-surface-container-high rounded" />
      </div>
      <div className="px-edge-margin py-6 bg-surface border-b border-outline-variant">
        <div className="grid grid-cols-4 gap-px">
          {Array.from({ length: 4 }).map((_, i) => (
            <div key={i} className="h-20 bg-surface-container-high rounded" />
          ))}
        </div>
      </div>
      <div className="px-edge-margin py-8 space-y-4">
        <div className="h-64 bg-surface-container-high rounded" />
      </div>
    </div>
  );
}

function WorkspaceError({
  message,
  onRetry,
}: {
  message: string | null;
  onRetry: () => void;
}) {
  const router = useRouter();
  return (
    <div className="py-20 flex flex-col items-center gap-3 text-center">
      <span className="material-symbols-outlined text-4xl text-error">error</span>
      <p className="font-headline-md text-primary">Could not load this case</p>
      <p className="font-body-md text-on-surface-variant">
        {message ?? "The server could not be reached."}
      </p>
      <div className="flex gap-3 mt-2">
        <button
          type="button"
          onClick={onRetry}
          className="flex items-center gap-2 border border-outline-variant px-4 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
        >
          <span className="material-symbols-outlined text-lg">refresh</span>
          Retry
        </button>
        <button
          type="button"
          onClick={() => router.push("/cases")}
          className="px-4 py-2 rounded font-body-md text-on-surface-variant hover:bg-surface-container-low transition-colors"
        >
          Back to cases
        </button>
      </div>
    </div>
  );
}

"use client";
import { useCallback, useEffect, useState } from "react";

import { api } from "@/lib/api";
import { formatUpdated } from "@/lib/cases";

type Doc = {
  id: number;
  doc_type: string;
  version: number | null;
  language: string | null;
  status: "DRAFT" | "FINALIZED";
  generated_by: number | null;
  generated_by_name: string | null;
  generated_at: string | null;
};
type VersionEntry = {
  version: number;
  status: string | null;
  language: string | null;
  generated_at: string | null;
  generated_by_name: string | null;
  diff_from_previous: {
    changed_fields: string[];
    changes: Record<string, { from: string | null; to: string | null }>;
  } | null;
};

// The six registered document types (matches templates/_registry.py).
const DOC_TYPES: { key: string; label: string; note?: string; icon: string }[] = [
  { key: "SEIZURE_RECEIPT", label: "Seizure Receipt", note: "Form IF4", icon: "receipt_long" },
  { key: "PANCHNAMA", label: "Panchnama", icon: "history_edu" },
  { key: "REMAND", label: "Remand Request", icon: "gavel" },
  { key: "MEDICAL_LETTER", label: "Medical Letter", icon: "medical_services" },
  { key: "LERS_PRESERVATION_REQUEST", label: "LERS Preservation Request", icon: "lock_clock" },
  { key: "LERS_RECORDS_REQUEST", label: "LERS Records Request", icon: "folder_data" },
];
const LABEL: Record<string, string> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.key, d.label])
);
const NOTE: Record<string, string | undefined> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.key, d.note])
);

const LANGS: { code: string; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "hi", label: "हिं" },
  { code: "gu", label: "ગુ" },
];

// Raw pool field keys -> officer-facing names (never show the code identifiers).
const FIELD_LABEL: Record<string, string> = {
  case_number: "case number",
  fir_number: "FIR number",
  fir_year: "FIR year",
  police_station: "police station",
  district: "district",
  io_name: "investigating officer",
  seizure_datetime: "seizure date and time",
  seizure_location: "seizure place",
  accused_name: "accused name",
  seized_items: "seized items",
  witnesses: "witnesses",
  panchnama_date: "panchnama date",
  panchnama_place: "panchnama place",
  sections_applied: "legal sections",
  investigation_done: "investigation summary",
  pending_investigation: "pending investigation",
  grounds_for_custody: "grounds for custody",
  subject_name: "subject name",
  examination_purpose: "examination purpose",
};
const friendly = (raw: string) => FIELD_LABEL[raw.trim()] ?? raw.trim().replace(/_/g, " ");

function parseMissing(detail: string | undefined): string[] | null {
  if (!detail) return null;
  const m = detail.match(/missing required field\(s\):\s*(.+)$/i);
  if (!m) return null;
  return m[1]
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

export default function DocumentsTab({
  caseId,
  role,
  onDocsChanged,
}: {
  caseId: number;
  role: string;
  onDocsChanged: () => void;
}) {
  const isSho = role === "SHO";
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [lang, setLang] = useState("en");
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState<{ docType: string; missing: string[] | null; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyDoc, setBusyDoc] = useState<number | null>(null);

  const load = useCallback(() => {
    api
      .get<Doc[]>(`/api/cases/${caseId}/documents`)
      .then((r) => setDocs(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? "Could not load documents."))
      .finally(() => setLoaded(true));
  }, [caseId]);

  useEffect(load, [load]);

  async function generate(docType: string) {
    setGenerating(docType);
    setGenError(null);
    setError(null);
    try {
      await api.post(`/api/cases/${caseId}/documents/${docType}?lang=${lang}`);
      load();
      onDocsChanged();
    } catch (e: any) {
      const detail: string | undefined = e?.response?.data?.detail;
      // 400 = missing pool data -> a designed panel, not a toast.
      setGenError({ docType, missing: parseMissing(detail), message: detail ?? "Generation failed." });
    } finally {
      setGenerating(null);
    }
  }

  return (
    <div className="space-y-8">
      {/* Generate row */}
      <section className="border border-outline-variant rounded bg-surface-container-lowest p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="font-headline-md text-primary">Generate a document</h2>
            <p className="font-body-md text-on-surface-variant">
              Every draft is pre-filled from the case pool and must be reviewed before filing.
            </p>
          </div>
          {/* Output language selector */}
          <div className="flex flex-col items-end gap-1">
            <span className="font-label-caps text-[10px] text-on-surface-variant">Output language</span>
            <div className="flex items-center rounded border border-outline-variant overflow-hidden" role="group" aria-label="Output language">
              {LANGS.map((l) => {
                const on = lang === l.code;
                return (
                  <button
                    key={l.code}
                    type="button"
                    onClick={() => setLang(l.code)}
                    aria-pressed={on}
                    className={
                      (on ? "bg-primary text-on-primary " : "bg-transparent text-on-surface-variant hover:bg-surface-container ") +
                      "px-3 py-1.5 font-body-md leading-none transition-colors"
                    }
                  >
                    {l.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {DOC_TYPES.map((d) => {
            const busy = generating === d.key;
            return (
              <button
                key={d.key}
                type="button"
                onClick={() => generate(d.key)}
                disabled={generating !== null}
                className="flex items-center gap-3 border border-outline-variant rounded px-4 py-3 text-left hover:border-primary hover:bg-surface-container-low transition-colors disabled:opacity-60"
              >
                <span className="material-symbols-outlined text-on-surface-variant">
                  {busy ? "progress_activity" : d.icon}
                </span>
                <span className="min-w-0">
                  <span className="block font-body-md text-primary">
                    {busy ? "Generating…" : d.label}
                  </span>
                  {d.note && (
                    <span className="block font-mono-sm text-on-surface-variant">{d.note}</span>
                  )}
                </span>
              </button>
            );
          })}
        </div>

        {/* Designed missing-fields panel (not a toast) */}
        {genError && (
          <div className="mt-5 border border-error/40 bg-error-container/40 rounded p-5">
            <div className="flex items-start gap-3">
              <span className="material-symbols-outlined text-error">report</span>
              <div className="min-w-0">
                {genError.missing ? (
                  <>
                    <p className="font-body-lg text-on-error-container">
                      Cannot generate the {LABEL[genError.docType].toLowerCase()} yet — add the
                      following first:
                    </p>
                    <p className="font-body-md text-on-surface mt-2">
                      {genError.missing.map(friendly).join("  ·  ")}
                    </p>
                  </>
                ) : (
                  <p className="font-body-md text-on-error-container">{genError.message}</p>
                )}
              </div>
            </div>
          </div>
        )}
      </section>

      {error && (
        <p role="alert" className="flex items-center gap-2 font-body-md text-error">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      {/* Documents table */}
      {!loaded ? (
        <DocsSkeleton />
      ) : docs.length === 0 ? (
        <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-16 flex flex-col items-center gap-2 text-center">
          <span className="material-symbols-outlined text-4xl text-outline">description</span>
          <p className="font-headline-md text-primary">No documents generated yet</p>
          <p className="font-body-md text-on-surface-variant">
            Use the buttons above to generate a draft.
          </p>
        </div>
      ) : (
        <div className="border border-outline-variant rounded overflow-hidden bg-surface-container-lowest">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
                <th className="px-4 py-3 font-label-caps">Document</th>
                <th className="px-4 py-3 font-label-caps w-[90px]">Version</th>
                <th className="px-4 py-3 font-label-caps w-[150px]">Status</th>
                <th className="px-4 py-3 font-label-caps w-[230px]">Generated</th>
                <th className="px-4 py-3 font-label-caps w-[260px] text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {docs.map((d) => (
                <DocRow
                  key={d.id}
                  doc={d}
                  isSho={isSho}
                  busy={busyDoc === d.id}
                  setBusy={setBusyDoc}
                  onChanged={() => {
                    load();
                    onDocsChanged();
                  }}
                  onError={setError}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function DocRow({
  doc,
  isSho,
  busy,
  setBusy,
  onChanged,
  onError,
}: {
  doc: Doc;
  isSho: boolean;
  busy: boolean;
  setBusy: (id: number | null) => void;
  onChanged: () => void;
  onError: (msg: string | null) => void;
}) {
  const [showVersions, setShowVersions] = useState(false);
  const [versions, setVersions] = useState<VersionEntry[] | null>(null);
  const [vLoading, setVLoading] = useState(false);
  const draft = doc.status === "DRAFT";

  async function download() {
    onError(null);
    try {
      const res = await api.get(`/api/documents/${doc.id}/download`, { responseType: "blob" });
      const cd: string = res.headers["content-disposition"] ?? "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : `${doc.doc_type}_${doc.id}.docx`;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch {
      onError("Could not download the document.");
    }
  }

  async function toggleVersions() {
    if (showVersions) {
      setShowVersions(false);
      return;
    }
    setShowVersions(true);
    if (versions == null) {
      setVLoading(true);
      try {
        const r = await api.get(`/api/documents/${doc.id}/versions`);
        setVersions(r.data.versions);
      } catch {
        onError("Could not load version history.");
      } finally {
        setVLoading(false);
      }
    }
  }

  async function finalize() {
    setBusy(doc.id);
    onError(null);
    try {
      await api.post(`/api/documents/${doc.id}/finalize`);
      setVersions(null); // history changed
      onChanged();
    } catch (e: any) {
      onError(e?.response?.data?.detail ?? "Could not finalize the document.");
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <tr className="align-top">
        <td className="px-4 py-4">
          <span className="font-serif text-body-lg text-primary">{LABEL[doc.doc_type] ?? doc.doc_type}</span>
          {NOTE[doc.doc_type] && (
            <span className="ml-2 font-mono-sm text-on-surface-variant">{NOTE[doc.doc_type]}</span>
          )}
          {draft && (
            <p className="font-body-md text-on-surface-variant italic mt-0.5">
              Draft — review and sign before filing.
            </p>
          )}
        </td>
        <td className="px-4 py-4 font-mono-data text-primary">v{doc.version ?? 1}</td>
        <td className="px-4 py-4">
          <StatusBadge status={doc.status} />
          {doc.language && (
            <span className="ml-2 font-mono-sm text-on-surface-variant uppercase">{doc.language}</span>
          )}
        </td>
        <td className="px-4 py-4">
          <p className="font-mono-sm text-on-surface-variant">{formatUpdated(doc.generated_at)}</p>
          <p className="font-body-md text-on-surface">{doc.generated_by_name ?? "—"}</p>
        </td>
        <td className="px-4 py-4">
          <div className="flex items-center justify-end gap-1 flex-wrap">
            <RowButton icon="download" label="Download" onClick={download} />
            <RowButton
              icon={showVersions ? "expand_less" : "history"}
              label="Versions"
              onClick={toggleVersions}
            />
            {isSho && draft && (
              <RowButton
                icon="draw"
                label={busy ? "Finalizing…" : "Finalize"}
                onClick={finalize}
                primary
                disabled={busy}
              />
            )}
          </div>
        </td>
      </tr>
      {showVersions && (
        <tr>
          <td colSpan={5} className="px-4 pb-5 bg-surface-container-low">
            {vLoading ? (
              <p className="font-body-md text-on-surface-variant py-4">Loading version history…</p>
            ) : (
              <VersionHistory versions={versions ?? []} />
            )}
          </td>
        </tr>
      )}
    </>
  );
}

function StatusBadge({ status }: { status: string }) {
  const finalized = status === "FINALIZED";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block w-2 h-2 rounded-full ${finalized ? "bg-success" : "bg-accent"}`} />
      <span className="font-body-md text-on-surface">{finalized ? "Finalized" : "Draft"}</span>
    </span>
  );
}

function RowButton({
  icon,
  label,
  onClick,
  primary,
  disabled,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  primary?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={
        "flex items-center gap-1 px-3 py-1.5 rounded font-body-md transition-colors disabled:opacity-60 " +
        (primary
          ? "bg-primary text-surface-bright hover:bg-inverse-surface"
          : "border border-outline-variant text-on-surface hover:bg-surface-container-low")
      }
    >
      <span className="material-symbols-outlined text-base">{icon}</span>
      {label}
    </button>
  );
}

function VersionHistory({ versions }: { versions: VersionEntry[] }) {
  if (!versions.length) {
    return <p className="font-body-md text-on-surface-variant py-4">No version history.</p>;
  }
  return (
    <div className="pt-4 space-y-4">
      <p className="font-label-caps text-[10px] text-on-surface-variant">Version history</p>
      {versions.map((v) => (
        <div key={v.version} className="border border-outline-variant rounded bg-surface-container-lowest p-4">
          <div className="flex flex-wrap items-center gap-3 mb-2">
            <span className="font-mono-data text-primary">v{v.version}</span>
            <StatusBadge status={v.status ?? "DRAFT"} />
            {v.language && (
              <span className="font-mono-sm text-on-surface-variant uppercase">{v.language}</span>
            )}
            <span className="font-mono-sm text-on-surface-variant">
              {formatUpdated(v.generated_at)}
              {v.generated_by_name ? `  ·  ${v.generated_by_name}` : ""}
            </span>
          </div>

          {v.diff_from_previous == null ? (
            <p className="font-body-md text-on-surface-variant italic">Initial version.</p>
          ) : v.diff_from_previous.changed_fields.length === 0 ? (
            <p className="font-body-md text-on-surface-variant italic">
              No field changes from the previous version.
            </p>
          ) : (
            <ul className="space-y-2">
              {v.diff_from_previous.changed_fields.map((f) => {
                const ch = v.diff_from_previous!.changes[f];
                return (
                  <li key={f} className="font-body-md">
                    <span className="font-label-caps text-[10px] text-on-surface-variant mr-2">
                      {friendly(f)}
                    </span>
                    {ch.from != null && (
                      <span className="line-through text-on-surface-variant mr-1">{ch.from}</span>
                    )}
                    {ch.to != null && (
                      <span className="bg-accent/[0.22] border-b border-accent px-0.5">{ch.to}</span>
                    )}
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}

function DocsSkeleton() {
  return (
    <div className="border border-outline-variant rounded overflow-hidden animate-pulse">
      {Array.from({ length: 3 }).map((_, i) => (
        <div key={i} className="h-16 border-b border-outline-variant bg-surface-container-high" />
      ))}
    </div>
  );
}

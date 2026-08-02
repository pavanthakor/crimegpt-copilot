"use client";
import { useCallback, useEffect, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { api } from "@/lib/api";
import { formatUpdated } from "@/lib/cases";
import { useI18n, type TKey } from "@/lib/i18n";
import { InfoTip } from "@/components/InfoTip";
import { PayloadSummary } from "@/components/PayloadSummary";
import { DOC_TYPES, fieldLabel, parseMissing } from "@/lib/docTypes";

// Fan-out: one case entry visibly produces many documents. The rows stagger in ~120ms
// apart when the list (re)renders after a generation. Respects prefers-reduced-motion.
const DOC_LIST_VARIANTS = {
  hidden: {},
  show: { transition: { staggerChildren: 0.12 } },
};
const DOC_ROW_VARIANTS = {
  hidden: { opacity: 0, y: 10 },
  show: { opacity: 1, y: 0, transition: { duration: 0.35, ease: "easeOut" } },
};

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

// Per-document state within a "Generate Full Case File" batch. A skipped document
// (usually missing pool fields -> 400) does not abort the batch; the rest continue.
type BatchOutcome =
  | { docType: string; state: "generating" }
  | { docType: string; state: "done" }
  | { docType: string; state: "skipped"; missing: string[] | null; message: string };

// The registered document types now live in lib/docTypes.ts — the case assistant needs
// the same list, and one source beats two that must be kept in step. `glossary` (when
// set) attaches an InfoTip explaining the acronym at its first appearance on this screen.
const NOTE: Record<string, string | undefined> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.key, d.note])
);

const LANGS: { code: string; label: string }[] = [
  { code: "en", label: "EN" },
  { code: "hi", label: "हिं" },
  { code: "gu", label: "ગુ" },
];

// Field names and the missing-field parser now come from lib/docTypes.ts, translated
// (EN/HI/GU) rather than the English-only map they used to be — the case assistant
// surfaces the same checklist and had to speak the officer's language.

export default function DocumentsTab({
  caseId,
  role,
  onDocsChanged,
}: {
  caseId: number;
  role: string;
  onDocsChanged: () => void;
}) {
  const { t, apiLang } = useI18n();
  const friendly = (raw: string) => fieldLabel(raw, t);
  const reduce = useReducedMotion();
  const isSho = role === "SHO";
  const [docs, setDocs] = useState<Doc[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [lang, setLang] = useState(apiLang);
  const docLabel = (key: string) => t(`docs.type.${key}` as TKey);
  const [generating, setGenerating] = useState<string | null>(null);
  const [genError, setGenError] = useState<{ docType: string; missing: string[] | null; message: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busyDoc, setBusyDoc] = useState<number | null>(null);
  // "Generate Full Case File" batch state.
  const [batchRunning, setBatchRunning] = useState(false);
  const [batchDone, setBatchDone] = useState(false);
  const [batchItems, setBatchItems] = useState<BatchOutcome[]>([]);

  const load = useCallback(() => {
    api
      .get<Doc[]>(`/api/cases/${caseId}/documents`)
      .then((r) => setDocs(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? t("docs.loadError")))
      .finally(() => setLoaded(true));
  }, [caseId, t]);

  useEffect(load, [load]);
  useEffect(() => setLang(apiLang), [apiLang]);

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
      setGenError({ docType, missing: parseMissing(detail), message: detail ?? t("docs.genFailed") });
    } finally {
      setGenerating(null);
    }
  }

  // Frontend-only orchestration: loop the existing single-document endpoint over every
  // registered doc type, in the selected language. Each result lands as it completes
  // (the docs table re-fans on every refresh); a missing-fields 400 skips that document
  // and the batch continues rather than failing as a whole.
  async function generateAll() {
    if (generating !== null || batchRunning) return;
    setBatchRunning(true);
    setBatchDone(false);
    setBatchItems([]);
    setGenError(null);
    setError(null);
    for (const d of DOC_TYPES) {
      setGenerating(d.key); // drives the matching grid button's spinner + disables all
      setBatchItems((prev) => [...prev, { docType: d.key, state: "generating" }]);
      try {
        await api.post(`/api/cases/${caseId}/documents/${d.key}?lang=${lang}`);
        setBatchItems((prev) =>
          prev.map((it) => (it.docType === d.key ? { docType: d.key, state: "done" } : it))
        );
        load(); // table grows live, re-triggering the fan-out stagger for each document
      } catch (e: any) {
        const detail: string | undefined = e?.response?.data?.detail;
        setBatchItems((prev) =>
          prev.map((it) =>
            it.docType === d.key
              ? { docType: d.key, state: "skipped", missing: parseMissing(detail), message: detail ?? t("docs.genFailed") }
              : it
          )
        );
      }
    }
    setGenerating(null);
    setBatchRunning(false);
    setBatchDone(true);
    onDocsChanged();
  }

  return (
    <div className="space-y-8">
      {/* Generate row */}
      <section className="border border-outline-variant rounded bg-surface-container-lowest p-6">
        <div className="flex items-center justify-between mb-5">
          <div>
            <h2 className="font-headline-md text-primary">{t("docs.generate.title")}</h2>
            <p className="font-body-md text-on-surface-variant">
              {t("docs.generate.subtitle")}
            </p>
          </div>
          {/* Output language selector */}
          <div className="flex flex-col items-end gap-1">
            <span className="font-label-caps text-[10px] text-on-surface-variant">{t("docs.outputLanguage")}</span>
            <div className="flex items-center rounded border border-outline-variant overflow-hidden" role="group" aria-label={t("docs.outputLanguage")}>
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

        {/* One click -> every applicable document, in the selected language. The
            per-document buttons below remain as the single-document fallback. */}
        <button
          type="button"
          onClick={generateAll}
          disabled={generating !== null || batchRunning}
          className="w-full flex items-center justify-center gap-2 bg-primary text-on-primary px-4 py-3 rounded font-label-caps text-[12px] hover:bg-inverse-surface disabled:opacity-60 transition-colors"
        >
          <span className={"material-symbols-outlined text-base" + (batchRunning ? " animate-spin" : "")}>
            {batchRunning ? "progress_activity" : "auto_awesome_motion"}
          </span>
          {batchRunning ? t("docs.batch.running") : t("docs.batch.button")}
        </button>

        {(batchRunning || batchItems.length > 0) && (
          <BatchPanel
            items={batchItems}
            running={batchRunning}
            done={batchDone}
            onDismiss={() => {
              setBatchItems([]);
              setBatchDone(false);
            }}
          />
        )}

        <p className="mt-6 mb-3 font-label-caps text-[10px] text-on-surface-variant">
          {t("docs.batch.orIndividual")}
        </p>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {DOC_TYPES.map((d) => {
            const busy = generating === d.key;
            return (
              <div key={d.key} className="relative">
                <button
                  type="button"
                  onClick={() => generate(d.key)}
                  disabled={generating !== null}
                  className="w-full h-full flex items-center gap-3 border border-outline-variant rounded px-4 py-3 text-left hover:border-primary hover:bg-surface-container-low transition-colors disabled:opacity-60"
                >
                  <span className="material-symbols-outlined text-on-surface-variant">
                    {busy ? "progress_activity" : d.icon}
                  </span>
                  <span className="min-w-0">
                    <span className="block font-body-md text-primary">
                      {busy ? t("docs.generating") : docLabel(d.key)}
                    </span>
                    {d.note && (
                      <span className="block font-mono-sm text-on-surface-variant">{d.note}</span>
                    )}
                  </span>
                </button>
                {d.glossary && (
                  <span className="absolute top-1.5 right-1.5">
                    <InfoTip term={d.glossary} text={t(`glossary.${d.glossary}` as TKey)} />
                  </span>
                )}
              </div>
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
                      {t("docs.cannotGenerate", { doc: docLabel(genError.docType) })}
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
        <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-16 flex flex-col items-center gap-3 text-center">
          <span className="material-symbols-outlined text-4xl text-outline">description</span>
          <p className="font-headline-md text-primary">{t("docs.empty.title")}</p>
          <p className="font-body-md text-on-surface-variant">
            {t("docs.empty.hint")}
          </p>
        </div>
      ) : (
        <div className="border border-outline-variant rounded overflow-x-auto bg-surface-container-lowest">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
                <th className="px-4 py-3 font-label-caps">{t("docs.col.document")}</th>
                <th className="px-4 py-3 font-label-caps w-[90px]">{t("docs.col.version")}</th>
                <th className="px-4 py-3 font-label-caps w-[150px]">{t("docs.col.status")}</th>
                <th className="px-4 py-3 font-label-caps w-[230px]">{t("docs.col.generated")}</th>
                <th className="px-4 py-3 font-label-caps w-[260px] text-right">{t("docs.col.actions")}</th>
              </tr>
            </thead>
            {/* key by count so a newly generated document re-triggers the fan-out. */}
            <motion.tbody
              key={docs.length}
              className="divide-y divide-outline-variant"
              variants={DOC_LIST_VARIANTS}
              initial={reduce ? "show" : "hidden"}
              animate="show"
            >
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
            </motion.tbody>
          </table>
        </div>
      )}

      {/* CCTNS mock export — IO/SHO only (LEGAL_ADVISOR is blocked server-side too). */}
      {role !== "LEGAL_ADVISOR" && <CctnsExport caseId={caseId} />}
    </div>
  );
}

// ---- Full-case-file batch progress -----------------------------------------
// Live per-document progress for "Generate Full Case File". Each row reuses the
// existing fan-out row animation, so as the batch walks the list the documents
// appear one after another; generating -> done (check) or skipped (reason inline).
function BatchPanel({
  items,
  running,
  done,
  onDismiss,
}: {
  items: BatchOutcome[];
  running: boolean;
  done: boolean;
  onDismiss: () => void;
}) {
  const { t } = useI18n();
  const friendly = (raw: string) => fieldLabel(raw, t);
  const reduce = useReducedMotion();
  const docLabel = (key: string) => t(`docs.type.${key}` as TKey);
  const generatedCount = items.filter((i) => i.state === "done").length;
  const skipped = items.filter(
    (i): i is Extract<BatchOutcome, { state: "skipped" }> => i.state === "skipped"
  );
  const allSkipsMissing = skipped.length > 0 && skipped.every((s) => s.missing);
  const summaryKey =
    skipped.length === 0
      ? "docs.batch.summaryClean"
      : allSkipsMissing
        ? "docs.batch.summaryMissing"
        : "docs.batch.summary";

  return (
    <div className="mt-4 border border-outline-variant rounded bg-surface-container-low p-5">
      <div className="flex items-center justify-between mb-3">
        <p className="font-label-caps text-[10px] text-on-surface-variant">
          {running ? t("docs.batch.running") : t("docs.batch.title")}
        </p>
        {done && (
          <button
            type="button"
            onClick={onDismiss}
            className="font-label-caps text-[10px] text-primary hover:underline"
          >
            {t("docs.batch.dismiss")}
          </button>
        )}
      </div>

      <ul className="space-y-2">
        {items.map((it) => (
          <motion.li
            key={it.docType}
            variants={DOC_ROW_VARIANTS}
            initial={reduce ? "show" : "hidden"}
            animate="show"
            className="flex items-start gap-3"
          >
            <span
              className={
                "material-symbols-outlined text-base " +
                (it.state === "generating"
                  ? "text-primary animate-spin"
                  : it.state === "done"
                    ? "text-success"
                    : "text-error")
              }
            >
              {it.state === "generating"
                ? "progress_activity"
                : it.state === "done"
                  ? "check_circle"
                  : "report"}
            </span>
            <span className="min-w-0">
              <span className="block font-body-md text-on-surface">
                {docLabel(it.docType)}
                <span className="ml-2 font-label-caps text-[10px] text-on-surface-variant">
                  {it.state === "generating"
                    ? t("docs.generating")
                    : it.state === "done"
                      ? t("docs.batch.generated")
                      : t("docs.batch.skipped")}
                </span>
              </span>
              {it.state === "skipped" && (
                <span className="block font-body-md text-on-surface-variant mt-0.5">
                  {it.missing ? it.missing.map(friendly).join("  ·  ") : it.message}
                </span>
              )}
            </span>
          </motion.li>
        ))}
      </ul>

      {done && (
        <div className="mt-4 pt-4 border-t border-outline-variant">
          <p className="font-body-lg text-primary">
            {t(summaryKey as TKey, { generated: generatedCount, skipped: skipped.length })}
          </p>
          {skipped.length > 0 && (
            <ul className="mt-2 space-y-1">
              {skipped.map((s) => (
                <li key={s.docType} className="font-body-md text-on-surface-variant">
                  <span className="text-on-surface">{docLabel(s.docType)}</span>
                  {"  —  "}
                  {s.missing ? s.missing.map(friendly).join("  ·  ") : s.message}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

// ---- CCTNS export (mock / demonstration gateway) ----------------------------
// Posts the case to the local mock CCTNS receiver and shows the returned mock FIR id
// plus the IIF-shaped payload. This is a DEMONSTRATION gateway, not a live government
// integration — the copy says so plainly. The backend already writes the audit + diary
// rows, so the panel just confirms that persistence happened.
type CctnsResult = {
  cctns_fir_id: string | null;
  mock_response: Record<string, unknown>;
  iif_payload: Record<string, unknown>;
};

function CctnsExport({ caseId }: { caseId: number }) {
  const { t } = useI18n();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<CctnsResult | null>(null);
  const [showPayload, setShowPayload] = useState(false);

  async function exportCctns() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.post<CctnsResult>(`/api/cases/${caseId}/export/cctns`);
      setResult(r.data);
      setShowPayload(false);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("cctns.error"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="border border-outline-variant rounded bg-surface-container-lowest p-6">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-on-surface-variant">cloud_upload</span>
            <h2 className="font-headline-md text-primary">{t("cctns.title")}</h2>
            <InfoTip term="CCTNS" text={t("glossary.CCTNS")} />
          </div>
          <p className="font-body-md text-on-surface-variant mt-1">
            {t("cctns.subtitle")}
            <span className="ml-1"><InfoTip term="IIF" text={t("glossary.IIF")} /></span>
          </p>
          {/* Unmistakable mock label — must not imply a live government link. */}
          <span className="mt-3 inline-flex items-center gap-1 font-label-caps text-[10px] text-on-secondary-container bg-secondary-container rounded px-2 py-0.5">
            <span className="material-symbols-outlined text-sm">science</span>
            {t("cctns.mockBadge")}
          </span>
        </div>
        <button
          type="button"
          onClick={exportCctns}
          disabled={busy}
          className="shrink-0 flex items-center gap-2 bg-primary text-on-primary px-4 py-2.5 rounded font-label-caps text-[11px] hover:bg-inverse-surface disabled:opacity-60 transition-colors"
        >
          <span
            className={
              "material-symbols-outlined text-base" + (busy ? " animate-spin" : "")
            }
          >
            {busy ? "progress_activity" : "cloud_upload"}
          </span>
          {busy ? t("cctns.exporting") : t("cctns.button")}
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 flex items-center gap-2 font-body-md text-error">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      {result && (
        <div className="mt-5 border-t border-outline-variant pt-5">
          <div className="flex flex-wrap items-center gap-x-6 gap-y-2">
            <div>
              <span className="block font-label-caps text-[9px] text-on-surface-variant">
                {t("cctns.firId")}
              </span>
              <span className="font-mono-data text-lg text-primary">
                {result.cctns_fir_id ?? "—"}
              </span>
            </div>
            <p className="flex items-center gap-1.5 font-body-md text-success">
              <span className="material-symbols-outlined text-base">check_circle</span>
              {t("cctns.confirmed")}
            </p>
          </div>

          <button
            type="button"
            onClick={() => setShowPayload((s) => !s)}
            className="mt-4 flex items-center gap-1 font-label-caps text-[11px] text-primary hover:underline"
          >
            <span className="material-symbols-outlined text-base">
              {showPayload ? "expand_less" : "expand_more"}
            </span>
            {showPayload ? t("cctns.hidePayload") : t("cctns.viewPayload")}
          </button>

          {showPayload && <PayloadSummary payload={result.iif_payload} />}
        </div>
      )}
    </section>
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
  const { t } = useI18n();
  const docLabel = (key: string) => t(`docs.type.${key}` as TKey);
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
      onError(t("docs.downloadError"));
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
        onError(t("docs.versionsError"));
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
      onError(e?.response?.data?.detail ?? t("docs.finalizeError"));
    } finally {
      setBusy(null);
    }
  }

  return (
    <>
      <motion.tr variants={DOC_ROW_VARIANTS} className="align-top">
        <td className="px-4 py-4">
          <span className="font-serif text-body-lg text-primary">{docLabel(doc.doc_type)}</span>
          {NOTE[doc.doc_type] && (
            <span className="ml-2 font-mono-sm text-on-surface-variant">{NOTE[doc.doc_type]}</span>
          )}
          {draft && (
            <p className="font-body-md text-on-surface-variant italic mt-0.5">
              {t("docs.draftNote")}
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
            <RowButton icon="download" label={t("common.download")} onClick={download} />
            <RowButton
              icon={showVersions ? "expand_less" : "history"}
              label={t("docs.action.versions")}
              onClick={toggleVersions}
            />
            {isSho && draft && (
              <RowButton
                icon="draw"
                label={busy ? t("docs.action.finalizing") : t("docs.action.finalize")}
                onClick={finalize}
                primary
                disabled={busy}
              />
            )}
          </div>
        </td>
      </motion.tr>
      {showVersions && (
        <tr>
          <td colSpan={5} className="px-4 pb-5 bg-surface-container-low">
            {vLoading ? (
              <p className="font-body-md text-on-surface-variant py-4">{t("docs.versions.loading")}</p>
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
  const { t } = useI18n();
  const finalized = status === "FINALIZED";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block w-2 h-2 rounded-full ${finalized ? "bg-success" : "bg-accent"}`} />
      <span className="font-body-md text-on-surface">{finalized ? t("docs.status.finalized") : t("docs.status.draft")}</span>
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
  const { t } = useI18n();
  const friendly = (raw: string) => fieldLabel(raw, t);
  if (!versions.length) {
    return <p className="font-body-md text-on-surface-variant py-4">{t("docs.versions.none")}</p>;
  }
  return (
    <div className="pt-4 space-y-4">
      <p className="font-label-caps text-[10px] text-on-surface-variant">{t("docs.versions.title")}</p>
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
            <p className="font-body-md text-on-surface-variant italic">{t("docs.versions.initial")}</p>
          ) : v.diff_from_previous.changed_fields.length === 0 ? (
            <p className="font-body-md text-on-surface-variant italic">
              {t("docs.versions.noChange")}
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

"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { motion, useReducedMotion } from "framer-motion";

import { api } from "@/lib/api";
import { reasonRestatesTitle } from "@/lib/cases";
import { useI18n, type TKey } from "@/lib/i18n";

type Section = {
  id: number;
  act: string;
  section_code: string | null;
  section_title: string | null;
  reason: string | null;
  triggering_phrase: string | null;
  confidence: number | null;
  status: "SUGGESTED" | "ACCEPTED" | "REJECTED";
};
type RejectedSection = {
  act: string | null;
  section_code: string | null;
  triggering_phrase: string | null;
  rejection_reason: string | null;
};
type Judgment = {
  id: number;
  title: string | null;
  citation: string | null;
  court: string | null;
  summary: string | null;
  relevance_reason: string | null;
  source_url: string | null;
};
type WeakAlert = {
  section_code: string | null;
  citation: string | null;
  missing_ingredients: string[];
  supported_ingredients: { ingredient: string; evidence_quote: string }[];
  severity: string;
  suggestion: string | null;
  note: string | null;
};

const STAGE_KEYS = [
  "legal.stage.searching",
  "legal.stage.retrieved",
  "legal.stage.matching",
  "legal.stage.verifying",
] as const;

export default function LegalSectionsTab({
  caseId,
  narrative,
  onSectionsChanged,
}: {
  caseId: number;
  narrative: string | null;
  onSectionsChanged: () => void;
}) {
  const { t, apiLang } = useI18n();
  const [sections, setSections] = useState<Section[]>([]);
  const [rejected, setRejected] = useState<RejectedSection[]>([]);
  const [analyzeStatus, setAnalyzeStatus] = useState<string | null>(null);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [running, setRunning] = useState(false);
  const [stage, setStage] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [activeId, setActiveId] = useState<number | null>(null);

  // Initial: load any already-persisted sections.
  useEffect(() => {
    api
      .get<Section[]>(`/api/cases/${caseId}/sections`)
      .then((r) => setSections(r.data))
      .catch(() => setError(t("legal.loadError")))
      .finally(() => setLoadedOnce(true));
  }, [caseId]);

  const analyze = useCallback(async () => {
    setRunning(true);
    setError(null);
    setStage(0);
    setAnalyzeStatus(null);
    const timers = [
      window.setTimeout(() => setStage(1), 1500),
      window.setTimeout(() => setStage(2), 3000),
      window.setTimeout(() => setStage(3), 5000),
    ];
    const started = Date.now();
    try {
      const r = await api.post(`/api/cases/${caseId}/analyze?lang=${apiLang}`);
      // Let the staged sequence play out even if the response is fast (demo cache).
      const MIN = 5200;
      const elapsed = Date.now() - started;
      if (elapsed < MIN) await new Promise((res) => setTimeout(res, MIN - elapsed));
      setStage(3);
      // Refetch the authoritative persisted list (suggestions + any prior decisions).
      const list = await api.get<Section[]>(`/api/cases/${caseId}/sections`);
      setSections(list.data);
      setRejected(r.data.rejected ?? []);
      setAnalyzeStatus(r.data.status);
      onSectionsChanged();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("legal.analyzeFailed"));
    } finally {
      timers.forEach(clearTimeout);
      setRunning(false);
    }
  }, [caseId, onSectionsChanged, apiLang, t]);

  async function decide(sid: number, decision: "ACCEPTED" | "REJECTED") {
    setError(null);
    try {
      const r = await api.patch<Section>(`/api/cases/${caseId}/sections/${sid}`, {
        status: decision,
      });
      setSections((prev) => prev.map((s) => (s.id === sid ? r.data : s)));
      onSectionsChanged();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("legal.updateError"));
    }
  }

  // Ordering: accepted first, then suggested, then officer-rejected (muted).
  const rank = { ACCEPTED: 0, SUGGESTED: 1, REJECTED: 2 } as const;
  const ordered = [...sections].sort((a, b) => rank[a.status] - rank[b.status]);
  const visibleOnNarrative = ordered.filter((s) => s.status !== "REJECTED");

  if (!loadedOnce) return <SectionsSkeleton />;

  // --- State: running ---
  if (running) {
    return (
      <div className="max-w-2xl mx-auto py-16">
        <AnalyzeStages stage={stage} />
      </div>
    );
  }

  // --- State: nothing analysed yet ---
  if (sections.length === 0 && analyzeStatus !== "no_grounded_match") {
    return (
      <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-16 flex flex-col items-center gap-3 text-center">
        <span className="material-symbols-outlined text-4xl text-outline">neurology</span>
        <p className="font-headline-md text-primary">{t("legal.empty.title")}</p>
        <p className="font-body-md text-on-surface-variant max-w-md">
          {t("legal.empty.hint")}
        </p>
        <AnalyzeButton onClick={analyze} label={t("legal.analyze")} />
        {error && <ErrorLine message={error} />}
      </div>
    );
  }

  return (
    <div className="space-y-10">
      {/* Re-run + errors */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="font-headline-md text-primary">{t("legal.title")}</h2>
          <p className="font-body-md text-on-surface-variant">
            {t("legal.subtitle")}
          </p>
        </div>
        <AnalyzeButton onClick={analyze} label={t("legal.reanalyse")} secondary />
      </div>
      {error && <ErrorLine message={error} />}

      {/* no_grounded_match — amber (khaki accent) review panel */}
      {analyzeStatus === "no_grounded_match" && sections.length === 0 && (
        <div className="flex items-start gap-3 border border-accent/50 bg-accent/[0.12] rounded p-5">
          <span className="material-symbols-outlined text-accent-strong">warning</span>
          <div>
            <p className="font-body-lg text-accent-strong">
              {t("legal.noMatch.title")}
            </p>
            <p className="font-body-md text-on-surface-variant">
              {t("legal.noMatch.hint")}
            </p>
          </div>
        </div>
      )}

      {/* Signature two-column: marked-up narrative + section cards */}
      {sections.length > 0 && (
        <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_minmax(0,460px)] gap-8 items-start">
          <MarkedNarrative
            narrative={narrative}
            sections={visibleOnNarrative}
            activeId={activeId}
            setActiveId={setActiveId}
          />
          <div className="space-y-4">
            {ordered.map((s) => (
              <SectionCard
                key={s.id}
                section={s}
                active={activeId === s.id}
                onHover={setActiveId}
                onDecide={decide}
              />
            ))}
            <RejectedByVerification rejected={rejected} />
          </div>
        </div>
      )}

      {/* Judgments + weak charges */}
      <JudgmentsPanel caseId={caseId} />
      <WeakChargePanel caseId={caseId} />
    </div>
  );
}

/* ---------------- Analyse action + staged progress ---------------- */

function AnalyzeButton({
  onClick,
  label = "Analyse with AI",
  secondary = false,
}: {
  onClick: () => void;
  label?: string;
  secondary?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={
        "flex items-center gap-2 px-5 py-2.5 rounded font-body-md font-semibold transition-colors " +
        (secondary
          ? "border border-outline-variant text-on-surface hover:bg-surface-container-low"
          : "bg-primary text-surface-bright hover:bg-inverse-surface")
      }
    >
      <span className="material-symbols-outlined text-xl">neurology</span>
      {label}
    </button>
  );
}

function AnalyzeStages({ stage }: { stage: number }) {
  const { t } = useI18n();
  const reduce = useReducedMotion();
  return (
    <div className="space-y-4">
      <p className="font-label-caps text-[10px] text-on-surface-variant text-center mb-8">
        {t("legal.grounded")}
      </p>
      {STAGE_KEYS.map((key, i) => {
        const done = i < stage;
        const current = i === stage;
        return (
          // Pending lines sit dimmed; each row eases up to full as it becomes active.
          <motion.div
            key={i}
            className="flex items-center gap-3"
            animate={{ opacity: done || current ? 1 : 0.45 }}
            transition={{ duration: reduce ? 0 : 0.25 }}
          >
            <span
              className={
                "shrink-0 w-6 h-6 rounded-full flex items-center justify-center " +
                (done
                  ? "bg-primary text-surface-bright"
                  : current
                  ? "bg-surface-container-high text-primary"
                  : "bg-surface-container text-on-surface-variant")
              }
            >
              {done ? (
                // The tick springs in the moment the stage completes.
                <motion.span
                  className="material-symbols-outlined text-base"
                  initial={reduce ? false : { scale: 0, opacity: 0 }}
                  animate={{ scale: 1, opacity: 1 }}
                  transition={{ type: "spring", stiffness: 500, damping: 22 }}
                >
                  check
                </motion.span>
              ) : current ? (
                <span className="material-symbols-outlined text-base animate-spin">
                  progress_activity
                </span>
              ) : (
                <span className="material-symbols-outlined text-base">circle</span>
              )}
            </span>
            <span
              className={
                "font-body-md " +
                (done || current ? "text-on-surface" : "text-on-surface-variant")
              }
            >
              {t(key as TKey)}
            </span>
          </motion.div>
        );
      })}
    </div>
  );
}

/* ---------------- Signature: marked-up narrative ---------------- */

type Segment = { text: string; id?: number };

function buildSegments(text: string, sections: Section[]): Segment[] {
  const lower = text.toLowerCase();
  const matches: { start: number; end: number; id: number }[] = [];
  for (const s of sections) {
    const ph = (s.triggering_phrase ?? "").trim();
    if (!ph) continue;
    const idx = lower.indexOf(ph.toLowerCase());
    if (idx === -1) continue;
    matches.push({ start: idx, end: idx + ph.length, id: s.id });
  }
  matches.sort((a, b) => a.start - b.start);
  const kept: typeof matches = [];
  let lastEnd = -1;
  for (const m of matches) {
    if (m.start >= lastEnd) {
      kept.push(m);
      lastEnd = m.end;
    }
  }
  const segs: Segment[] = [];
  let cursor = 0;
  for (const m of kept) {
    if (m.start > cursor) segs.push({ text: text.slice(cursor, m.start) });
    segs.push({ text: text.slice(m.start, m.end), id: m.id });
    cursor = m.end;
  }
  if (cursor < text.length) segs.push({ text: text.slice(cursor) });
  return segs;
}

function MarkedNarrative({
  narrative,
  sections,
  activeId,
  setActiveId,
}: {
  narrative: string | null;
  sections: Section[];
  activeId: number | null;
  setActiveId: (id: number | null) => void;
}) {
  const { t } = useI18n();
  const reduce = useReducedMotion();
  if (!narrative) {
    return (
      <section className="bg-surface-container-lowest border border-outline-variant rounded p-8">
        <p className="font-body-md text-on-surface-variant italic">
          {t("legal.marked.empty")}
        </p>
      </section>
    );
  }
  const segs = buildSegments(narrative, sections);
  const anyMatch = segs.some((s) => s.id != null);
  // Track a running index across highlighted phrases so the sweeps cascade in order.
  let markIndex = -1;

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded p-8">
      <h3 className="font-label-caps text-[10px] text-on-surface-variant mb-6 flex items-center gap-2">
        <span className="w-8 h-px bg-outline-variant" />
        {t("legal.marked.title")}
      </h3>
      <div className="font-serif text-body-lg leading-[1.9] text-on-surface max-w-[68ch] whitespace-pre-wrap">
        {segs.map((seg, i) => {
          if (seg.id == null) return <span key={i}>{seg.text}</span>;
          markIndex += 1;
          // Khaki marker drawn left-to-right: the wash is a no-repeat gradient whose
          // width animates 0% -> 100% (backgroundColor stays transparent so the browser's
          // default <mark> yellow never shows). Sweeps cascade ~90ms apart.
          const wash =
            activeId === seg.id ? "rgba(138,124,63,0.45)" : "rgba(138,124,63,0.22)";
          return (
            <motion.mark
              key={i}
              onMouseEnter={() => setActiveId(seg.id!)}
              onMouseLeave={() => setActiveId(null)}
              onClick={() => {
                setActiveId(seg.id!);
                document
                  .getElementById(`section-card-${seg.id}`)
                  ?.scrollIntoView({ behavior: "smooth", block: "center" });
              }}
              initial={reduce ? false : { backgroundSize: "0% 100%" }}
              animate={{ backgroundSize: "100% 100%" }}
              transition={{
                duration: reduce ? 0 : 0.4,
                ease: "easeInOut",
                delay: reduce ? 0 : Math.min(markIndex * 0.09, 0.9),
              }}
              style={{
                backgroundColor: "transparent",
                backgroundImage: `linear-gradient(${wash}, ${wash})`,
                backgroundRepeat: "no-repeat",
                backgroundPosition: "left center",
              }}
              className="cursor-pointer border-b-2 border-accent [box-decoration-break:clone] px-0.5 transition-colors"
            >
              {seg.text}
            </motion.mark>
          );
        })}
      </div>
      {!anyMatch && (
        <p className="font-body-md text-on-surface-variant italic mt-4">
          {t("legal.marked.notLocated")}
        </p>
      )}
    </section>
  );
}

/* ---------------- Section card ---------------- */


function SectionCard({
  section,
  active,
  onHover,
  onDecide,
}: {
  section: Section;
  active: boolean;
  onHover: (id: number | null) => void;
  onDecide: (id: number, decision: "ACCEPTED" | "REJECTED") => void;
}) {
  const { t } = useI18n();
  const accepted = section.status === "ACCEPTED";
  const officerRejected = section.status === "REJECTED";
  const conf = section.confidence != null ? Math.round(section.confidence * 100) : null;
  // The reason is often just the short statutory title, which the full title in the
  // heading already carries — showing both reads as a duplicated title. Suppress the
  // reason when it is a leading fragment of (or identical to) the heading title.
  const reason = reasonRestatesTitle(section.reason, section.section_title)
    ? null
    : section.reason;

  return (
    <div
      id={`section-card-${section.id}`}
      onMouseEnter={() => onHover(section.id)}
      onMouseLeave={() => onHover(null)}
      className={
        "rounded p-5 transition-all scroll-mt-24 " +
        (officerRejected
          ? "border border-outline-variant bg-surface-container opacity-60"
          : accepted
          ? "border-2 border-primary bg-surface-container-lowest"
          : "border border-outline-variant bg-surface-container-lowest") +
        (active ? " ring-2 ring-accent" : "")
      }
    >
      <div className="flex items-start justify-between gap-3 mb-2">
        <div className="min-w-0">
          <span className="font-mono-data text-lg text-primary">
            {section.act} {section.section_code}
          </span>
          <h4
            className={
              "font-serif text-body-lg text-primary mt-0.5 " +
              (officerRejected ? "line-through" : "")
            }
          >
            {section.section_title ?? "—"}
          </h4>
        </div>
        <div className="text-right shrink-0">
          {conf != null && (
            <>
              <div className="font-display-case text-2xl text-primary leading-none">
                {conf}%
              </div>
              <div className="font-label-caps text-[9px] text-on-surface-variant">
                {t("legal.confidence")}
              </div>
            </>
          )}
        </div>
      </div>

      {/* status pill */}
      <div className="mb-3">
        {accepted ? (
          <span className="inline-flex items-center gap-1 font-label-caps text-[10px] text-on-primary bg-primary rounded px-2 py-0.5">
            <span className="material-symbols-outlined text-sm">check</span>
            {t("legal.status.accepted")}
          </span>
        ) : officerRejected ? (
          <span className="inline-flex items-center gap-1 font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
            {t("legal.status.rejected")}
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 font-label-caps text-[10px] text-on-secondary-container bg-secondary-container rounded px-2 py-0.5">
            {t("legal.status.suggested")}
          </span>
        )}
      </div>

      {reason && (
        <p className="font-body-md text-on-surface-variant leading-relaxed mb-4">
          {reason}
        </p>
      )}

      {section.status === "SUGGESTED" ? (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={() => onDecide(section.id, "ACCEPTED")}
            className="flex-1 flex items-center justify-center gap-1 bg-primary text-surface-bright py-2 rounded font-label-caps text-[11px] hover:bg-inverse-surface transition-colors"
          >
            <span className="material-symbols-outlined text-base">check</span>
            {t("legal.accept")}
          </button>
          <button
            type="button"
            onClick={() => onDecide(section.id, "REJECTED")}
            className="flex-1 flex items-center justify-center gap-1 border border-outline-variant py-2 rounded font-label-caps text-[11px] text-on-surface hover:bg-surface-container-low transition-colors"
          >
            <span className="material-symbols-outlined text-base">close</span>
            {t("legal.reject")}
          </button>
        </div>
      ) : officerRejected ? (
        <button
          type="button"
          onClick={() => onDecide(section.id, "ACCEPTED")}
          className="font-label-caps text-[11px] text-primary hover:underline"
        >
          {t("legal.reinstate")}
        </button>
      ) : null}
    </div>
  );
}

/* ---------------- Rejected by verification (collapsible) ---------------- */

function RejectedByVerification({ rejected }: { rejected: RejectedSection[] }) {
  const { t } = useI18n();
  const [open, setOpen] = useState(false);
  if (!rejected.length) return null;
  return (
    <div className="border border-outline-variant rounded bg-surface-container">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="w-full flex items-center justify-between px-4 py-3 font-body-md text-on-surface-variant"
      >
        <span className="flex items-center gap-2">
          <span className="material-symbols-outlined text-lg">shield</span>
          {rejected.length === 1
            ? t("legal.rejectedByVerification.one", { n: rejected.length })
            : t("legal.rejectedByVerification.many", { n: rejected.length })}
        </span>
        <span className="material-symbols-outlined">
          {open ? "expand_less" : "expand_more"}
        </span>
      </button>
      {open && (
        <ul className="px-4 pb-4 space-y-3">
          {rejected.map((r, i) => (
            <li key={i} className="border-t border-outline-variant pt-3">
              <p className="font-mono-data text-on-surface-variant line-through">
                {r.act} {r.section_code}
              </p>
              <p className="font-body-md text-on-surface-variant">{r.rejection_reason}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/* ---------------- Judgments panel ---------------- */

function yearOf(citation: string | null): string | null {
  if (!citation) return null;
  const m = citation.match(/\b(1[89]\d{2}|20\d{2})\b/);
  return m ? m[1] : null;
}

function JudgmentsPanel({ caseId }: { caseId: number }) {
  const { t } = useI18n();
  const [judgments, setJudgments] = useState<Judgment[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.post(`/api/cases/${caseId}/judgments`);
      setJudgments(r.data.judgments ?? []);
      setStatus(r.data.status);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("legal.judgments.error"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border border-outline-variant rounded bg-surface-container-lowest">
      <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant">
        <div>
          <h3 className="font-headline-md text-primary">{t("legal.judgments.title")}</h3>
          <p className="font-body-md text-on-surface-variant">
            {t("legal.judgments.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded font-body-md border border-outline-variant text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-60"
        >
          {loading ? (
            <>
              <span className="material-symbols-outlined animate-spin text-lg">
                progress_activity
              </span>
              {t("legal.judgments.searching")}
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-lg">gavel</span>
              {judgments ? t("legal.judgments.refresh") : t("legal.judgments.suggest")}
            </>
          )}
        </button>
      </div>

      <div className="p-6">
        {error && <ErrorLine message={error} />}
        {judgments == null && !loading && !error && (
          <p className="font-body-md text-on-surface-variant">
            {t("legal.judgments.intro")}
          </p>
        )}
        {judgments != null && judgments.length === 0 && (
          <p className="font-body-md text-on-surface-variant">
            {status === "no_grounded_match"
              ? t("legal.judgments.noMatch")
              : t("legal.judgments.none")}
          </p>
        )}
        {judgments && judgments.length > 0 && (
          <ul className="space-y-5">
            {judgments.map((j) => {
              const yr = yearOf(j.citation);
              return (
                <li key={j.id} className="border-b border-outline-variant last:border-0 pb-5 last:pb-0">
                  <h4 className="font-serif text-body-lg text-primary">{j.title}</h4>
                  <p className="font-mono-data text-on-surface-variant mt-1">
                    {j.citation}
                    {(j.court || yr) && (
                      <span className="text-on-surface-variant">
                        {"  ·  "}
                        {[j.court, yr].filter(Boolean).join("  ·  ")}
                      </span>
                    )}
                  </p>
                  {j.relevance_reason && (
                    <p className="font-body-md text-on-surface mt-2 leading-relaxed">
                      <span className="font-label-caps text-[10px] text-on-surface-variant mr-2">
                        {t("legal.judgments.relevance")}
                      </span>
                      {j.relevance_reason}
                    </p>
                  )}
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

/* ---------------- Weak-charge alerts ---------------- */

function WeakChargePanel({ caseId }: { caseId: number }) {
  const { t } = useI18n();
  const [alerts, setAlerts] = useState<WeakAlert[] | null>(null);
  const [status, setStatus] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      const r = await api.get(`/api/cases/${caseId}/weak-charges`);
      setAlerts(r.data.alerts ?? []);
      setStatus(r.data.status);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("legal.weak.error"));
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="border border-outline-variant rounded bg-surface-container-lowest">
      <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant">
        <div>
          <h3 className="font-headline-md text-primary">{t("legal.weak.title")}</h3>
          <p className="font-body-md text-on-surface-variant">
            {t("legal.weak.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={run}
          disabled={loading}
          className="flex items-center gap-2 px-4 py-2 rounded font-body-md border border-outline-variant text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-60"
        >
          {loading ? (
            <>
              <span className="material-symbols-outlined animate-spin text-lg">
                progress_activity
              </span>
              {t("legal.weak.checking")}
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-lg">gpp_maybe</span>
              {alerts ? t("legal.weak.recheck") : t("legal.weak.check")}
            </>
          )}
        </button>
      </div>

      <div className="p-6">
        {error && <ErrorLine message={error} />}
        {alerts == null && !loading && !error && (
          <p className="font-body-md text-on-surface-variant">
            {t("legal.weak.intro")}
          </p>
        )}
        {alerts != null && alerts.length === 0 && !error && (
          <div className="flex items-center gap-2 font-body-md text-on-surface">
            <span className="material-symbols-outlined text-primary">verified</span>
            {status === "no_issues"
              ? t("legal.weak.allSupported")
              : t("legal.weak.none")}
          </div>
        )}
        {alerts && alerts.length > 0 && (
          <ul className="space-y-4">
            {alerts.map((a, i) => (
              <WeakAlertCard key={i} alert={a} />
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function WeakAlertCard({ alert }: { alert: WeakAlert }) {
  const { t } = useI18n();
  const high = (alert.severity ?? "").toLowerCase() === "high";
  return (
    <li
      className={
        "rounded border p-5 " +
        (high
          ? "border-error/40 bg-error-container/40"
          : "border-outline-variant bg-surface-container")
      }
    >
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="font-mono-data text-primary">
          {alert.citation ?? alert.section_code}
        </span>
        {/* Severity carried by icon + word + colour, never colour alone. */}
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
          {high ? t("legal.weak.highRisk") : t("legal.weak.lowRisk")}
        </span>
      </div>

      {alert.missing_ingredients.length > 0 && (
        <div className="mb-3">
          <p className="font-label-caps text-[10px] text-on-surface-variant mb-1">
            {t("legal.weak.notEstablished")}
          </p>
          <ul className="space-y-1">
            {alert.missing_ingredients.map((ing, j) => (
              <li key={j} className="flex items-start gap-2 font-body-md text-on-surface">
                <span className="material-symbols-outlined text-error text-base mt-0.5">
                  remove_circle
                </span>
                <span className="italic">&ldquo;{ing}&rdquo;</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {alert.suggestion && (
        <p className="font-body-md text-on-surface-variant">
          <span className="font-label-caps text-[10px] text-on-surface-variant mr-2">
            {t("legal.weak.suggestion")}
          </span>
          {alert.suggestion}
        </p>
      )}
    </li>
  );
}

/* ---------------- shared bits ---------------- */

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-center gap-2 font-body-md text-error mb-3">
      <span className="material-symbols-outlined text-base">error</span>
      {message}
    </p>
  );
}

function SectionsSkeleton() {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_460px] gap-8 animate-pulse">
      <div className="h-96 bg-surface-container-high rounded" />
      <div className="space-y-4">
        {Array.from({ length: 2 }).map((_, i) => (
          <div key={i} className="h-40 bg-surface-container-high rounded" />
        ))}
      </div>
    </div>
  );
}

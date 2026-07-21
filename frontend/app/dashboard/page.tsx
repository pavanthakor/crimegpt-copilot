"use client";
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n, type TKey } from "@/lib/i18n";
import { CASE_STATUSES, formatUpdated, isBlankDesc, statusMeta } from "@/lib/cases";

// A landing view over the whole caseload. Everything here is real: status counts come
// straight from the case list, and the activity feed is the actual case-diary entries
// merged across cases (no invented "productivity" metrics).

type CaseRow = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
  updated_at: string | null;
};
type DiaryEntry = {
  id: number;
  entry_datetime: string | null;
  activity_type: string;
  description: string | null;
  auto_generated: boolean | null;
};
type CaseDetail = { diary_entries: DiaryEntry[] };

// Activity feed pulls each case's diary; cap the fan-out so a large caseload doesn't
// fire hundreds of requests. The most recently updated cases carry the newest activity.
const ACTIVITY_CASE_CAP = 20;
const ACTIVITY_LIMIT = 12;

const ACTIVITY_ICON: Record<string, string> = {
  COMPLAINT: "report",
  WITNESS_EXAM: "record_voice_over",
  EVIDENCE_SEIZURE: "inventory_2",
  ARREST: "lock",
  REMAND: "gavel",
  DOC_GENERATED: "description",
  OTHER: "edit_note",
};

type FeedItem = DiaryEntry & { caseId: number; caseNumber: string };

export default function DashboardPage() {
  const { user, ready } = useAuth();
  const { t } = useI18n();
  const router = useRouter();

  const [cases, setCases] = useState<CaseRow[]>([]);
  const [feed, setFeed] = useState<FeedItem[]>([]);
  const [capped, setCapped] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .get<CaseRow[]>("/api/cases")
      .then(async (r) => {
        const rows = r.data;
        setCases(rows);

        // Newest-touched cases first, then pull their diaries in parallel.
        const recent = [...rows]
          .sort((a, b) => (a.updated_at ?? "") < (b.updated_at ?? "") ? 1 : -1)
          .slice(0, ACTIVITY_CASE_CAP);
        setCapped(rows.length > ACTIVITY_CASE_CAP);

        const details = await Promise.all(
          recent.map((c) =>
            api
              .get<CaseDetail>(`/api/cases/${c.id}`)
              .then((d) => ({ c, entries: d.data.diary_entries ?? [] }))
              .catch(() => ({ c, entries: [] as DiaryEntry[] }))
          )
        );

        const items: FeedItem[] = [];
        for (const { c, entries } of details) {
          for (const e of entries) {
            items.push({ ...e, caseId: c.id, caseNumber: c.case_number });
          }
        }
        items.sort((a, b) =>
          (a.entry_datetime ?? "") < (b.entry_datetime ?? "") ? 1 : -1
        );
        setFeed(items.slice(0, ACTIVITY_LIMIT));
      })
      .catch((e) => setError(e?.response?.data?.detail ?? t("common.serverUnreachable")))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    load();
  }, [ready, user, router, load]);

  if (!ready || !user) return null;

  const counts = CASE_STATUSES.map((s) => ({
    status: s,
    dot: statusMeta(s).dot,
    count: cases.filter((c) => c.status === s).length,
  }));

  return (
    <div className="space-y-8">
      {/* Greeting */}
      <div>
        <h1 className="font-headline-lg text-primary">{t("dash.title")}</h1>
        <p className="font-body-md text-on-surface-variant mt-1">
          {user.full_name
            ? t("dash.welcome", { name: user.full_name })
            : t("dash.welcomeNoName")}
        </p>
      </div>

      {error && <ErrorLine message={error} onRetry={load} />}

      {/* Status counts */}
      <section>
        <div className="flex items-baseline justify-between mb-3">
          <h2 className="font-headline-md text-primary">{t("dash.byStatus")}</h2>
          <Link href="/cases" className="font-body-md text-primary hover:underline">
            {loading ? "…" : t("dash.total", { n: cases.length })}
          </Link>
        </div>
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-px bg-outline-variant border border-outline-variant">
          {counts.map((c) => (
            <Link
              key={c.status}
              href={`/cases?status=${c.status}`}
              className="bg-surface-container-lowest p-5 hover:bg-surface-container-low transition-colors"
            >
              <div className="flex items-center gap-2 mb-2">
                <span className={`inline-block w-2 h-2 rounded-full ${c.dot}`} />
                <span className="font-label-caps text-[10px] text-on-surface-variant">
                  {t(`status.${c.status}` as TKey)}
                </span>
              </div>
              <span className="font-display-case text-3xl text-on-surface">
                {loading ? "—" : String(c.count).padStart(2, "0")}
              </span>
            </Link>
          ))}
        </div>
      </section>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_320px] gap-8 items-start">
        {/* Recent activity */}
        <section>
          <h2 className="font-headline-md text-primary mb-3">{t("dash.recent")}</h2>
          <div className="border border-outline-variant rounded bg-surface-container-lowest">
            {loading ? (
              <ActivitySkeleton />
            ) : feed.length === 0 ? (
              <div className="py-14 flex flex-col items-center gap-2 text-center">
                <span className="material-symbols-outlined text-4xl text-outline">
                  event_note
                </span>
                <p className="font-headline-md text-primary">{t("dash.recent.empty.title")}</p>
                <p className="font-body-md text-on-surface-variant">
                  {t("dash.recent.empty.hint")}
                </p>
              </div>
            ) : (
              <ul className="divide-y divide-outline-variant">
                {feed.map((e) => (
                  <li key={`${e.caseId}-${e.id}`} className="flex gap-4 p-4">
                    <span className="shrink-0 w-9 h-9 rounded-full bg-surface-container flex items-center justify-center">
                      <span className="material-symbols-outlined text-lg text-on-surface-variant">
                        {ACTIVITY_ICON[e.activity_type] ?? "circle"}
                      </span>
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-0.5">
                        <Link
                          href={`/cases/${e.caseId}`}
                          className="font-mono-data text-primary hover:underline"
                        >
                          {e.caseNumber}
                        </Link>
                        <span className="font-label-caps text-[9px] text-on-surface-variant border border-outline-variant rounded px-1.5 py-0.5">
                          {t(`activity.${e.activity_type}` as TKey)}
                        </span>
                        {e.auto_generated && (
                          <span className="font-label-caps text-[9px] text-on-secondary-container bg-secondary-container rounded px-1.5 py-0.5">
                            {t("diary.auto")}
                          </span>
                        )}
                      </div>
                      <p className="font-body-md text-on-surface">
                        {isBlankDesc(e.description) ? t("common.noDescription") : e.description}
                      </p>
                    </div>
                    <span className="shrink-0 font-mono-sm text-on-surface-variant text-right whitespace-nowrap">
                      {formatUpdated(e.entry_datetime)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {capped && (
            <p className="font-body-md text-on-surface-variant mt-2">
              {t("dash.recent.capped", { n: ACTIVITY_CASE_CAP })}
            </p>
          )}
        </section>

        {/* Quick links */}
        <section>
          <h2 className="font-headline-md text-primary mb-3">{t("dash.quickLinks")}</h2>
          <div className="space-y-2">
            <QuickLink href="/cases/new" icon="add_circle" label={t("dash.link.newCase")} primary />
            <QuickLink href="/cases" icon="folder_shared" label={t("dash.link.allCases")} />
            <QuickLink href="/analysis" icon="neurology" label={t("dash.link.analysis")} />
            <QuickLink href="/audit" icon="verified_user" label={t("dash.link.audit")} />
          </div>
        </section>
      </div>
    </div>
  );
}

function QuickLink({
  href,
  icon,
  label,
  primary,
}: {
  href: string;
  icon: string;
  label: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={
        "flex items-center gap-3 px-4 py-3 rounded font-body-md font-semibold transition-colors " +
        (primary
          ? "bg-primary text-surface-bright hover:bg-inverse-surface"
          : "border border-outline-variant text-on-surface hover:bg-surface-container-low")
      }
    >
      <span className="material-symbols-outlined text-xl">{icon}</span>
      {label}
    </Link>
  );
}

function ActivitySkeleton() {
  return (
    <ul className="divide-y divide-outline-variant animate-pulse">
      {Array.from({ length: 5 }).map((_, i) => (
        <li key={i} className="flex gap-4 p-4">
          <span className="shrink-0 w-9 h-9 rounded-full bg-surface-container-high" />
          <span className="flex-1 h-8 bg-surface-container-high rounded" />
        </li>
      ))}
    </ul>
  );
}

function ErrorLine({ message, onRetry }: { message: string; onRetry: () => void }) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-3 border border-error/40 bg-error-container/40 rounded p-4">
      <span className="material-symbols-outlined text-error">error</span>
      <p className="font-body-md text-on-surface flex-1">{message}</p>
      <button
        type="button"
        onClick={onRetry}
        className="flex items-center gap-1 border border-outline-variant px-3 py-1.5 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
      >
        <span className="material-symbols-outlined text-lg">refresh</span>
        {t("common.retry")}
      </button>
    </div>
  );
}

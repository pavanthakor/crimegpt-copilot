"use client";
import { useEffect, useMemo, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { CASE_STATUSES, formatUpdated, statusMeta } from "@/lib/cases";

type CaseRow = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
  police_station: string | null;
  updated_at: string | null;
  created_by_name: string | null;
};

export default function CasesPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  // Honour a ?status= deep-link (e.g. from a dashboard status tile) as the initial filter.
  const initialStatus = searchParams.get("status");
  const [statusFilter, setStatusFilter] = useState<string>(
    initialStatus && (CASE_STATUSES as string[]).includes(initialStatus) ? initialStatus : "ALL"
  );

  const isSho = user?.role === "SHO";

  function reload() {
    setLoading(true);
    setError(null);
    api
      .get<CaseRow[]>("/api/cases")
      .then((r) => setRows(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? "The server could not be reached."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ready, user, router]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return rows.filter((c) => {
      if (statusFilter !== "ALL" && c.status !== statusFilter) return false;
      if (!needle) return true;
      return (
        c.case_number.toLowerCase().includes(needle) ||
        (c.title ?? "").toLowerCase().includes(needle) ||
        (c.police_station ?? "").toLowerCase().includes(needle)
      );
    });
  }, [rows, q, statusFilter]);

  if (!ready || !user) return null;

  const cols = isSho ? 6 : 5;

  return (
    <div>
      {/* Header: count + New case */}
      <div className="flex items-end justify-between mb-6">
        <div>
          <h1 className="font-headline-lg text-primary">Cases</h1>
          <p className="font-body-md text-on-surface-variant mt-1">
            {loading
              ? "Loading…"
              : `${rows.length} ${rows.length === 1 ? "case" : "cases"}${
                  isSho ? " across all officers" : " assigned to you"
                }`}
          </p>
        </div>
        <button
          type="button"
          onClick={() => router.push("/cases/new")}
          className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2.5 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
        >
          <span className="material-symbols-outlined text-xl">add</span>
          New case
        </button>
      </div>

      {/* Filter row: search + status */}
      <div className="flex items-center gap-3 mb-4">
        <div className="relative flex-grow max-w-md">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-xl">
            search
          </span>
          <input
            type="text"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search case number, title, or station…"
            className="w-full bg-surface-container-low border border-outline-variant rounded pl-11 pr-4 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors"
          />
        </div>
        <label htmlFor="status-filter" className="font-label-caps text-on-surface-variant">
          Status
        </label>
        <select
          id="status-filter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
        >
          <option value="ALL">All</option>
          {CASE_STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusMeta(s).label}
            </option>
          ))}
        </select>
      </div>

      {/* Ruled table */}
      <div className="border border-outline-variant rounded overflow-hidden bg-surface-container-lowest">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
              <th className="px-4 py-3 font-label-caps w-[160px]">Case #</th>
              <th className="px-4 py-3 font-label-caps">Title</th>
              <th className="px-4 py-3 font-label-caps w-[150px]">Status</th>
              {isSho && <th className="px-4 py-3 font-label-caps w-[180px]">Officer</th>}
              <th className="px-4 py-3 font-label-caps w-[180px]">Police Station</th>
              <th className="px-4 py-3 font-label-caps w-[170px] text-right">Last Updated</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant">
            {loading ? (
              <SkeletonRows cols={cols} />
            ) : error ? (
              // Error state — distinct from "no cases yet" (which implies a successful
              // but empty load). Offer a retry.
              <tr>
                <td colSpan={cols} className="px-4 py-16 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="material-symbols-outlined text-4xl text-error">error</span>
                    <p className="font-headline-md text-primary">Could not load cases</p>
                    <p className="font-body-md text-on-surface-variant">{error}</p>
                    <button
                      type="button"
                      onClick={reload}
                      className="mt-2 flex items-center gap-2 border border-outline-variant px-4 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
                    >
                      <span className="material-symbols-outlined text-lg">refresh</span>
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            ) : filtered.length === 0 ? (
              <tr>
                <td colSpan={cols} className="px-4 py-16 text-center">
                  {rows.length === 0 ? (
                    <div className="flex flex-col items-center gap-2">
                      <span className="material-symbols-outlined text-4xl text-outline">
                        folder_open
                      </span>
                      <p className="font-headline-md text-primary">No cases yet</p>
                      <p className="font-body-md text-on-surface-variant">
                        Create the first case to begin.
                      </p>
                      <button
                        type="button"
                        onClick={() => router.push("/cases/new")}
                        className="mt-2 flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
                      >
                        <span className="material-symbols-outlined text-lg">add</span>
                        New case
                      </button>
                    </div>
                  ) : (
                    <p className="font-body-md text-on-surface-variant">
                      No cases match your filters.
                    </p>
                  )}
                </td>
              </tr>
            ) : (
              filtered.map((c) => {
                const meta = statusMeta(c.status);
                return (
                  <tr
                    key={c.id}
                    onClick={() => router.push(`/cases/${c.id}`)}
                    className="group cursor-pointer hover:bg-surface-container-low transition-colors"
                  >
                    <td className="px-4 py-4 font-mono-data text-primary align-top">
                      {c.case_number}
                    </td>
                    <td className="px-4 py-4 align-top">
                      <span className="font-body-md text-primary group-hover:underline">
                        {c.title ?? "Untitled case"}
                      </span>
                    </td>
                    <td className="px-4 py-4 align-top">
                      <span className="inline-flex items-center gap-2">
                        <span className={`inline-block w-2 h-2 rounded-full ${meta.dot}`} />
                        <span className="font-body-md text-on-surface">{meta.label}</span>
                      </span>
                    </td>
                    {isSho && (
                      <td className="px-4 py-4 font-body-md text-on-surface align-top">
                        {c.created_by_name ?? "—"}
                      </td>
                    )}
                    <td className="px-4 py-4 font-body-md text-on-surface-variant align-top">
                      {c.police_station ?? "—"}
                    </td>
                    <td className="px-4 py-4 font-mono-sm text-on-surface-variant text-right align-top">
                      {formatUpdated(c.updated_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SkeletonRows({ cols }: { cols: number }) {
  return (
    <>
      {Array.from({ length: 4 }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: cols }).map((_, c) => (
            <td key={c} className="px-4 py-4">
              <span className="block h-4 rounded bg-surface-container-high animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

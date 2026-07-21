"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { CaseSelect, useCasePicker } from "@/components/CasePicker";
import { formatUpdated } from "@/lib/cases";

// The audit trail is a named PS requirement (CLAUDE.md §4 Tier 1 "Search & Audit",
// §7 audit): every create/update/delete on a case is written to audit_log, and this
// page is where an SHO or reviewer reads it back — newest first, filterable, paginated.

type Change = { old?: unknown; new?: unknown } | unknown;
type AuditEntry = {
  id: number;
  action: "CREATE" | "UPDATE" | "DELETE";
  entity_type: string | null;
  entity_id: number | null;
  field_changes: Record<string, Change> | null;
  performed_by_name: string | null;
  performed_by_role: string | null;
  performed_at: string | null;
};
type AuditPage = {
  entries: AuditEntry[];
  total: number;
  limit: number;
  offset: number;
};

const PAGE_SIZE = 25;

// The entity_type values the backend actually writes (audit.py / pool.py / etc.).
const ENTITY_TYPES = [
  "case",
  "person",
  "seized_item",
  "statement",
  "evidence",
  "legal_section",
  "document",
  "case_diary_entry",
  "cctns_export",
] as const;
const ENTITY_LABEL: Record<string, string> = {
  case: "Case",
  person: "Person",
  seized_item: "Seized item",
  statement: "Statement",
  evidence: "Evidence",
  legal_section: "Legal section",
  document: "Document",
  case_diary_entry: "Diary entry",
  cctns_export: "CCTNS export",
};

const ACTION_META: Record<string, { label: string; cls: string; icon: string }> = {
  CREATE: {
    label: "Created",
    cls: "text-on-secondary-container bg-secondary-container",
    icon: "add_circle",
  },
  UPDATE: {
    label: "Updated",
    cls: "text-primary bg-surface-container-high",
    icon: "edit",
  },
  DELETE: { label: "Deleted", cls: "text-on-error-container bg-error-container", icon: "delete" },
};

const ROLE_LABEL: Record<string, string> = {
  IO: "Investigating Officer",
  SHO: "Station House Officer",
  LEGAL_ADVISOR: "Legal Advisor",
};

export default function AuditPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const { cases, loading: casesLoading, error: casesError, selected, setSelected } =
    useCasePicker();

  const [entityType, setEntityType] = useState<string>("ALL");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<AuditPage | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset to the first page whenever the case or the filter changes.
  useEffect(() => {
    setOffset(0);
  }, [selected, entityType]);

  const load = useCallback(() => {
    if (selected == null) return;
    setLoading(true);
    setError(null);
    api
      .get<AuditPage>(`/api/cases/${selected}/audit`, {
        params: {
          limit: PAGE_SIZE,
          offset,
          ...(entityType !== "ALL" ? { entity_type: entityType } : {}),
        },
      })
      .then((r) => setPage(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? "Could not load the audit trail."))
      .finally(() => setLoading(false));
  }, [selected, offset, entityType]);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    load();
  }, [ready, user, router, load]);

  if (!ready || !user) return null;

  const total = page?.total ?? 0;
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + PAGE_SIZE, total);

  return (
    <div>
      <div className="mb-6">
        <h1 className="font-headline-lg text-primary">Audit trail</h1>
        <p className="font-body-md text-on-surface-variant mt-1">
          Every create, update and delete on a case — who did it, when, and exactly
          what changed.
        </p>
      </div>

      {/* Controls: case + entity-type filter */}
      <div className="flex flex-wrap items-center gap-4 mb-4">
        {casesLoading ? (
          <span className="font-body-md text-on-surface-variant">Loading cases…</span>
        ) : cases.length === 0 ? (
          <span className="font-body-md text-on-surface-variant">No cases to audit yet.</span>
        ) : (
          <CaseSelect cases={cases} value={selected} onChange={setSelected} />
        )}
        <div className="flex items-center gap-3">
          <label htmlFor="entity-filter" className="font-label-caps text-on-surface-variant">
            Entity
          </label>
          <select
            id="entity-filter"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="ALL">All entities</option>
            {ENTITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {ENTITY_LABEL[t]}
              </option>
            ))}
          </select>
        </div>
      </div>

      {casesError && <ErrorLine message={casesError} />}

      {/* Dense ruled table */}
      <div className="border border-outline-variant rounded overflow-hidden bg-surface-container-lowest">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
              <th className="px-4 py-3 font-label-caps w-[170px]">Time</th>
              <th className="px-4 py-3 font-label-caps w-[120px]">Action</th>
              <th className="px-4 py-3 font-label-caps w-[150px]">Entity</th>
              <th className="px-4 py-3 font-label-caps">What changed</th>
              <th className="px-4 py-3 font-label-caps w-[220px]">Performed by</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-outline-variant">
            {loading ? (
              <SkeletonRows />
            ) : error ? (
              <tr>
                <td colSpan={5} className="px-4 py-16 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="material-symbols-outlined text-4xl text-error">error</span>
                    <p className="font-headline-md text-primary">Could not load the audit trail</p>
                    <p className="font-body-md text-on-surface-variant">{error}</p>
                    <button
                      type="button"
                      onClick={load}
                      className="mt-2 flex items-center gap-2 border border-outline-variant px-4 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
                    >
                      <span className="material-symbols-outlined text-lg">refresh</span>
                      Retry
                    </button>
                  </div>
                </td>
              </tr>
            ) : !page || page.entries.length === 0 ? (
              <tr>
                <td colSpan={5} className="px-4 py-16 text-center">
                  <div className="flex flex-col items-center gap-2">
                    <span className="material-symbols-outlined text-4xl text-outline">
                      verified_user
                    </span>
                    <p className="font-headline-md text-primary">No audit entries</p>
                    <p className="font-body-md text-on-surface-variant">
                      {entityType === "ALL"
                        ? "Actions on this case will be recorded here."
                        : `No ${ENTITY_LABEL[entityType]?.toLowerCase()} changes recorded.`}
                    </p>
                  </div>
                </td>
              </tr>
            ) : (
              page.entries.map((e) => {
                const action = ACTION_META[e.action] ?? {
                  label: e.action,
                  cls: "text-on-surface-variant border border-outline-variant",
                  icon: "history",
                };
                return (
                  <tr key={e.id} className="align-top">
                    <td className="px-4 py-4 font-mono-sm text-on-surface-variant whitespace-nowrap">
                      {formatUpdated(e.performed_at)}
                    </td>
                    <td className="px-4 py-4">
                      <span
                        className={`inline-flex items-center gap-1 font-label-caps text-[10px] rounded px-2 py-0.5 ${action.cls}`}
                      >
                        <span className="material-symbols-outlined text-sm">{action.icon}</span>
                        {action.label}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span className="font-body-md text-on-surface">
                        {ENTITY_LABEL[e.entity_type ?? ""] ?? e.entity_type ?? "—"}
                      </span>
                      {e.entity_id != null && (
                        <span className="font-mono-sm text-on-surface-variant ml-1">
                          #{e.entity_id}
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-4">
                      <ChangeCell action={e.action} changes={e.field_changes} />
                    </td>
                    <td className="px-4 py-4">
                      <p className="font-body-md text-on-surface">
                        {e.performed_by_name ?? "—"}
                      </p>
                      {e.performed_by_role && (
                        <p className="font-label-caps text-[9px] text-on-surface-variant mt-0.5">
                          {ROLE_LABEL[e.performed_by_role] ?? e.performed_by_role}
                        </p>
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {page && total > 0 && (
        <div className="flex items-center justify-between mt-4">
          <p className="font-body-md text-on-surface-variant">
            Showing <span className="font-mono-data text-on-surface">{from}</span>–
            <span className="font-mono-data text-on-surface">{to}</span> of{" "}
            <span className="font-mono-data text-on-surface">{total}</span>
          </p>
          <div className="flex items-center gap-2">
            <PageButton
              icon="chevron_left"
              label="Previous"
              disabled={offset === 0 || loading}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            />
            <PageButton
              icon="chevron_right"
              label="Next"
              trailing
              disabled={to >= total || loading}
              onClick={() => setOffset((o) => o + PAGE_SIZE)}
            />
          </div>
        </div>
      )}
    </div>
  );
}

// Renders a field_changes dict. Two shapes coexist in audit_log:
//   • per-field diffs — { field: { old, new } }  (updates)
//   • flat value maps — { field: value }         (creates / metadata)
// Diffs strike through the old value; flat values are shown as set.
function ChangeCell({
  action,
  changes,
}: {
  action: string;
  changes: Record<string, Change> | null;
}) {
  const keys = changes ? Object.keys(changes) : [];
  if (keys.length === 0) {
    return (
      <span className="font-body-md text-on-surface-variant italic">
        {action === "DELETE" ? "record removed" : "—"}
      </span>
    );
  }
  return (
    <ul className="space-y-1">
      {keys.map((k) => {
        const v = changes![k] as { old?: unknown; new?: unknown };
        const isDiff = v && typeof v === "object" && ("old" in v || "new" in v);
        return (
          <li key={k} className="font-body-md leading-snug">
            <span className="font-mono-sm text-on-surface-variant">{k}</span>{" "}
            {isDiff ? (
              <>
                <span className="text-on-surface-variant line-through">{fmt(v.old)}</span>
                <span className="material-symbols-outlined text-sm align-middle mx-1 text-outline">
                  arrow_forward
                </span>
                <span className="text-on-surface font-medium">{fmt(v.new)}</span>
              </>
            ) : (
              <span className="text-on-surface">{fmt(changes![k])}</span>
            )}
          </li>
        );
      })}
    </ul>
  );
}

function fmt(v: unknown): string {
  if (v === null || v === undefined || v === "") return "(empty)";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}

function PageButton({
  icon,
  label,
  onClick,
  disabled,
  trailing,
}: {
  icon: string;
  label: string;
  onClick: () => void;
  disabled: boolean;
  trailing?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="flex items-center gap-1 border border-outline-variant px-3 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
    >
      {!trailing && <span className="material-symbols-outlined text-lg">{icon}</span>}
      {label}
      {trailing && <span className="material-symbols-outlined text-lg">{icon}</span>}
    </button>
  );
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-center gap-2 font-body-md text-error mb-3">
      <span className="material-symbols-outlined text-base">error</span>
      {message}
    </p>
  );
}

function SkeletonRows() {
  return (
    <>
      {Array.from({ length: 6 }).map((_, r) => (
        <tr key={r}>
          {Array.from({ length: 5 }).map((_, c) => (
            <td key={c} className="px-4 py-4">
              <span className="block h-4 rounded bg-surface-container-high animate-pulse" />
            </td>
          ))}
        </tr>
      ))}
    </>
  );
}

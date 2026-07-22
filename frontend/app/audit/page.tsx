"use client";
import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { CaseSelect, useCasePicker } from "@/components/CasePicker";
import { useI18n, type TKey } from "@/lib/i18n";
import { formatUpdated } from "@/lib/cases";
import { PayloadSummary } from "@/components/PayloadSummary";

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

export default function AuditPage() {
  const { user, ready } = useAuth();
  const { t } = useI18n();
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
      .catch((e) => setError(e?.response?.data?.detail ?? t("audit.loadError.title")))
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
        <h1 className="font-headline-lg text-primary">{t("audit.title")}</h1>
        <p className="font-body-md text-on-surface-variant mt-1">
          {t("audit.subtitle")}
        </p>
      </div>

      {/* Controls: case + entity-type filter */}
      <div className="flex flex-wrap items-center gap-4 mb-4">
        {casesLoading ? (
          <span className="font-body-md text-on-surface-variant">{t("audit.loadingCases")}</span>
        ) : cases.length === 0 ? (
          <span className="font-body-md text-on-surface-variant">{t("audit.noCases")}</span>
        ) : (
          <CaseSelect cases={cases} value={selected} onChange={setSelected} />
        )}
        <div className="flex items-center gap-3">
          <label htmlFor="entity-filter" className="font-label-caps text-on-surface-variant">
            {t("audit.entity")}
          </label>
          <select
            id="entity-filter"
            value={entityType}
            onChange={(e) => setEntityType(e.target.value)}
            className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="ALL">{t("audit.entity.all")}</option>
            {ENTITY_TYPES.map((type) => (
              <option key={type} value={type}>
                {t(`audit.entity.${type}` as TKey)}
              </option>
            ))}
          </select>
        </div>
      </div>

      {casesError && <ErrorLine message={casesError} />}

      {/* Dense ruled table */}
      <div className="border border-outline-variant rounded overflow-x-auto bg-surface-container-lowest">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
              <th className="px-4 py-3 font-label-caps w-[170px]">{t("audit.col.time")}</th>
              <th className="px-4 py-3 font-label-caps w-[120px]">{t("audit.col.action")}</th>
              <th className="px-4 py-3 font-label-caps w-[150px]">{t("audit.col.entity")}</th>
              <th className="px-4 py-3 font-label-caps">{t("audit.col.changed")}</th>
              <th className="px-4 py-3 font-label-caps w-[220px]">{t("audit.col.performedBy")}</th>
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
                    <p className="font-headline-md text-primary">{t("audit.loadError.title")}</p>
                    <p className="font-body-md text-on-surface-variant">{error}</p>
                    <button
                      type="button"
                      onClick={load}
                      className="mt-2 flex items-center gap-2 border border-outline-variant px-4 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
                    >
                      <span className="material-symbols-outlined text-lg">refresh</span>
                      {t("common.retry")}
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
                    <p className="font-headline-md text-primary">{t("audit.empty.title")}</p>
                    <p className="font-body-md text-on-surface-variant">
                      {entityType === "ALL"
                        ? t("audit.empty.all")
                        : t("audit.empty.filtered", {
                            entity: t(`audit.entity.${entityType}` as TKey),
                          })}
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
                        {t(`audit.action.${e.action}` as TKey)}
                      </span>
                    </td>
                    <td className="px-4 py-4">
                      <span className="font-body-md text-on-surface">
                        {e.entity_type ? t(`audit.entity.${e.entity_type}` as TKey) : "—"}
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
                          {e.performed_by_role ? t(`role.${e.performed_by_role}` as TKey) : null}
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
            {t("audit.showing", { from, to, total })}
          </p>
          <div className="flex items-center gap-2">
            <PageButton
              icon="chevron_left"
              label={t("audit.previous")}
              disabled={offset === 0 || loading}
              onClick={() => setOffset((o) => Math.max(0, o - PAGE_SIZE))}
            />
            <PageButton
              icon="chevron_right"
              label={t("audit.next")}
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
  const { t } = useI18n();
  const show = (v: unknown) => {
    const s = fmt(v);
    return s === "(empty)" ? t("audit.empty.value") : s;
  };
  const keys = changes ? Object.keys(changes) : [];
  if (keys.length === 0) {
    return (
      <span className="font-body-md text-on-surface-variant italic">
        {action === "DELETE" ? t("audit.recordRemoved") : "—"}
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
                <span className="text-on-surface-variant line-through">{show(v.old)}</span>
                <span className="material-symbols-outlined text-sm align-middle mx-1 text-outline">
                  arrow_forward
                </span>
                <span className="text-on-surface font-medium">{show(v.new)}</span>
              </>
            ) : (
              <ValueView v={changes![k]} />
            )}
          </li>
        );
      })}
    </ul>
  );
}

function isPayload(v: unknown): v is Record<string, unknown> {
  return (
    !!v && typeof v === "object" && !Array.isArray(v) &&
    ("IIF-1" in (v as object) || "IIF-4" in (v as object))
  );
}

// Renders one audit value. The CCTNS export writes the whole iif_payload here; rather
// than a JSON wall, it renders as the labelled PayloadSummary. Any other large object is
// collapsed behind a disclosure instead of being stringified whole. Scalars render plainly.
function ValueView({ v }: { v: unknown }) {
  const { t } = useI18n();
  if (v && typeof v === "object") {
    if (isPayload(v)) return <PayloadSummary payload={v} />;
    const json = JSON.stringify(v, null, 2);
    if (json.length > 80) {
      const n = Array.isArray(v) ? v.length : Object.keys(v as object).length;
      return (
        <details className="inline-block align-top">
          <summary className="cursor-pointer font-mono-sm text-on-surface-variant hover:text-primary">
            {t("audit.objectCollapsed", { n })}
          </summary>
          <pre className="mt-1 max-h-48 overflow-auto rounded border border-outline-variant bg-surface-container-low p-2 text-xs whitespace-pre-wrap break-words">
            {json}
          </pre>
        </details>
      );
    }
  }
  const s = fmt(v);
  return <span className="text-on-surface">{s === "(empty)" ? t("audit.empty.value") : s}</span>;
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

"use client";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { isBlankDesc } from "@/lib/cases";
import { useI18n, type TKey } from "@/lib/i18n";

type Person = { id: number; full_name: string | null };
export type DiaryEntry = {
  id: number;
  entry_datetime: string | null;
  activity_type: string;
  description: string | null;
  related_person_id: number | null;
  related_evidence_id: number | null;
  auto_generated: boolean | null;
};
type Evidence = { id: number; description: string | null };

const ACTIVITY_TYPES = [
  "COMPLAINT",
  "WITNESS_EXAM",
  "EVIDENCE_SEIZURE",
  "ARREST",
  "REMAND",
  "DOC_GENERATED",
  "OTHER",
] as const;

const ACTIVITY_ICON: Record<string, string> = {
  COMPLAINT: "report",
  WITNESS_EXAM: "record_voice_over",
  EVIDENCE_SEIZURE: "inventory_2",
  ARREST: "lock",
  REMAND: "gavel",
  DOC_GENERATED: "description",
  OTHER: "edit_note",
};

function dateKey(iso: string | null): string {
  if (!iso) return "unknown";
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? "unknown" : d.toISOString().slice(0, 10);
}
function dateHeading(key: string, t: (k: TKey) => string): string {
  if (key === "unknown") return t("diary.undated");
  const d = new Date(key + "T00:00:00");
  return d.toLocaleDateString("en-GB", { day: "numeric", month: "long", year: "numeric" });
}
function timeOf(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? "—"
    : d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export default function DiaryTab({
  caseId,
  entries,
  persons,
  onDiaryChanged,
}: {
  caseId: number;
  entries: DiaryEntry[];
  persons: Person[];
  onDiaryChanged: () => void;
}) {
  const [filter, setFilter] = useState<string>("ALL");
  const [adding, setAdding] = useState(false);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const { t } = useI18n();

  // Evidence descriptions for related_evidence resolution.
  useEffect(() => {
    api
      .get<Evidence[]>(`/api/cases/${caseId}/evidence`)
      .then((r) => setEvidence(r.data))
      .catch(() => setEvidence([]));
  }, [caseId]);

  const personName = useMemo(() => {
    const m = new Map<number, string>();
    persons.forEach((p) => m.set(p.id, p.full_name ?? `Person ${p.id}`));
    return m;
  }, [persons]);
  const evidenceDesc = useMemo(() => {
    const m = new Map<number, string>();
    evidence.forEach((e) => m.set(e.id, e.description ?? `Evidence #${e.id}`));
    return m;
  }, [evidence]);

  const filtered = useMemo(
    () => entries.filter((e) => filter === "ALL" || e.activity_type === filter),
    [entries, filter]
  );

  // Group by date, newest date first, newest entry first within a date.
  const groups = useMemo(() => {
    const byDate = new Map<string, DiaryEntry[]>();
    for (const e of filtered) {
      const k = dateKey(e.entry_datetime);
      (byDate.get(k) ?? byDate.set(k, []).get(k)!).push(e);
    }
    const keys = [...byDate.keys()].sort((a, b) => (a < b ? 1 : a > b ? -1 : 0));
    return keys.map((k) => ({
      key: k,
      entries: byDate.get(k)!.slice().sort((a, b) => {
        const ta = a.entry_datetime ?? "";
        const tb = b.entry_datetime ?? "";
        if (ta !== tb) return ta < tb ? 1 : -1;
        return b.id - a.id;
      }),
    }));
  }, [filtered]);

  return (
    <div className="space-y-6">
      {/* Header: filter + add */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <label htmlFor="diary-filter" className="font-label-caps text-on-surface-variant">
            {t("diary.activity")}
          </label>
          <select
            id="diary-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="ALL">{t("diary.allActivity")}</option>
            {ACTIVITY_TYPES.map((code) => (
              <option key={code} value={code}>
                {t(`activity.${code}` as TKey)}
              </option>
            ))}
          </select>
          <span className="font-body-md text-on-surface-variant">
            {filtered.length === 1
              ? t("diary.entryCount.one", { n: filtered.length })
              : t("diary.entryCount.many", { n: filtered.length })}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setAdding((a) => !a)}
          className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          {t("diary.add")}
        </button>
      </div>

      {adding && (
        <ManualEntryForm
          caseId={caseId}
          persons={persons}
          onDone={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onDiaryChanged();
          }}
        />
      )}

      {filtered.length === 0 ? (
        <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-14 flex flex-col items-center gap-2 text-center">
          <span className="material-symbols-outlined text-4xl text-outline">event_note</span>
          <p className="font-headline-md text-primary">{t("diary.empty.title")}</p>
          <p className="font-body-md text-on-surface-variant">
            {filter === "ALL" ? t("diary.empty.hint") : t("diary.empty.filtered")}
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {groups.map((g) => (
            <div key={g.key}>
              {/* Serif date heading */}
              <h3 className="font-headline-md text-primary mb-4 flex items-center gap-3">
                {dateHeading(g.key, t)}
                <span className="flex-1 h-px bg-outline-variant" />
              </h3>
              <ul className="space-y-3">
                {g.entries.map((e) => (
                  <li
                    key={e.id}
                    className="flex gap-4 border border-outline-variant rounded bg-surface-container-lowest p-4"
                  >
                    {/* Time rail */}
                    <div className="shrink-0 w-16 text-right">
                      <p className="font-mono-data text-primary">{timeOf(e.entry_datetime)}</p>
                    </div>
                    <div className="w-px bg-outline-variant" />
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2 mb-1">
                        <span className="inline-flex items-center gap-1 font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
                          <span className="material-symbols-outlined text-sm">
                            {ACTIVITY_ICON[e.activity_type] ?? "circle"}
                          </span>
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
                      {(e.related_person_id != null || e.related_evidence_id != null) && (
                        <div className="flex flex-wrap gap-3 mt-2">
                          {e.related_person_id != null && (
                            <span className="inline-flex items-center gap-1 font-body-md text-on-surface-variant">
                              <span className="material-symbols-outlined text-sm">person</span>
                              {personName.get(e.related_person_id) ?? `Person #${e.related_person_id}`}
                            </span>
                          )}
                          {e.related_evidence_id != null && (
                            <span className="inline-flex items-center gap-1 font-body-md text-on-surface-variant">
                              <span className="material-symbols-outlined text-sm">inventory_2</span>
                              {evidenceDesc.get(e.related_evidence_id) ?? `Evidence #${e.related_evidence_id}`}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ManualEntryForm({
  caseId,
  persons,
  onDone,
  onSaved,
}: {
  caseId: number;
  persons: Person[];
  onDone: () => void;
  onSaved: () => void;
}) {
  const [activity, setActivity] = useState("OTHER");
  const [description, setDescription] = useState("");
  const [relatedPerson, setRelatedPerson] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { t } = useI18n();

  async function save() {
    if (!description.trim()) {
      setErr(t("diary.descRequired"));
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api.post(`/api/cases/${caseId}/diary`, {
        activity_type: activity,
        description,
        related_person_id: relatedPerson ? Number(relatedPerson) : null,
      });
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? t("diary.saveError"));
      setSaving(false);
    }
  }

  return (
    <div className="border border-outline-variant rounded bg-surface-container-low p-5 space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">{t("diary.form.title")}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="font-label-caps text-[10px] text-on-surface-variant">{t("diary.form.activityType")}</span>
          <select
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {ACTIVITY_TYPES.map((code) => (
              <option key={code} value={code}>
                {t(`activity.${code}` as TKey)}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="font-label-caps text-[10px] text-on-surface-variant">{t("diary.form.relatedPerson")}</span>
          <select
            value={relatedPerson}
            onChange={(e) => setRelatedPerson(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="">{t("common.none")}</option>
            {persons.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name ?? `Person ${p.id}`}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block space-y-1">
        <span className="font-label-caps text-[10px] text-on-surface-variant">{t("diary.form.description")}</span>
        <textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder={t("diary.form.placeholder")}
          className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary resize-y"
        />
      </label>
      {err && (
        <p role="alert" className="flex items-center gap-1 font-body-md text-error">
          <span className="material-symbols-outlined text-base">error</span>
          {err}
        </p>
      )}
      <div className="flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
        >
          {saving ? t("common.saving") : t("diary.add")}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
        >
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

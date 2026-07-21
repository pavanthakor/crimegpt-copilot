"use client";
import { useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { descOr } from "@/lib/cases";

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

const ACTIVITY_LABEL: Record<string, string> = {
  COMPLAINT: "Complaint",
  WITNESS_EXAM: "Witness exam",
  EVIDENCE_SEIZURE: "Evidence seizure",
  ARREST: "Arrest",
  REMAND: "Remand",
  DOC_GENERATED: "Document generated",
  OTHER: "Note",
};
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
function dateHeading(key: string): string {
  if (key === "unknown") return "Undated";
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
            Activity
          </label>
          <select
            id="diary-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            className="bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="ALL">All activity</option>
            {ACTIVITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {ACTIVITY_LABEL[t]}
              </option>
            ))}
          </select>
          <span className="font-body-md text-on-surface-variant">
            {filtered.length} {filtered.length === 1 ? "entry" : "entries"}
          </span>
        </div>
        <button
          type="button"
          onClick={() => setAdding((a) => !a)}
          className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          Add entry
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
          <p className="font-headline-md text-primary">No diary entries</p>
          <p className="font-body-md text-on-surface-variant">
            {filter === "ALL"
              ? "Actions on this case appear here automatically; add your own note above."
              : "No entries match this filter."}
          </p>
        </div>
      ) : (
        <div className="space-y-8">
          {groups.map((g) => (
            <div key={g.key}>
              {/* Serif date heading */}
              <h3 className="font-headline-md text-primary mb-4 flex items-center gap-3">
                {dateHeading(g.key)}
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
                          {ACTIVITY_LABEL[e.activity_type] ?? e.activity_type}
                        </span>
                        {e.auto_generated && (
                          <span className="font-label-caps text-[9px] text-on-secondary-container bg-secondary-container rounded px-1.5 py-0.5">
                            Auto
                          </span>
                        )}
                      </div>
                      <p className="font-body-md text-on-surface">{descOr(e.description)}</p>
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

  async function save() {
    if (!description.trim()) {
      setErr("A description is required.");
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
      setErr(e?.response?.data?.detail ?? "Could not save the entry.");
      setSaving(false);
    }
  }

  return (
    <div className="border border-outline-variant rounded bg-surface-container-low p-5 space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">Add a diary note</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <label className="block space-y-1">
          <span className="font-label-caps text-[10px] text-on-surface-variant">Activity type</span>
          <select
            value={activity}
            onChange={(e) => setActivity(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {ACTIVITY_TYPES.map((t) => (
              <option key={t} value={t}>
                {ACTIVITY_LABEL[t]}
              </option>
            ))}
          </select>
        </label>
        <label className="block space-y-1">
          <span className="font-label-caps text-[10px] text-on-surface-variant">Related person (optional)</span>
          <select
            value={relatedPerson}
            onChange={(e) => setRelatedPerson(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="">None</option>
            {persons.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name ?? `Person ${p.id}`}
              </option>
            ))}
          </select>
        </label>
      </div>
      <label className="block space-y-1">
        <span className="font-label-caps text-[10px] text-on-surface-variant">Description</span>
        <textarea
          rows={3}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="What happened…"
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
          {saving ? "Saving…" : "Add entry"}
        </button>
        <button
          type="button"
          onClick={onDone}
          className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}

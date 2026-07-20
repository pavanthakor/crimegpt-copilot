"use client";
import { useMemo, useState } from "react";

import { api } from "@/lib/api";
import {
  COMPLAINT_LANGS,
  PERSON_ROLES,
  PERSON_ROLE_LABEL,
  STATEMENT_TYPES,
} from "@/lib/cases";

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
};

type PersonForm = {
  role: string;
  full_name: string;
  alias: string;
  father_name: string;
  age: string;
  gender: string;
  phone: string;
  occupation: string;
  address: string;
};
const EMPTY_PERSON: PersonForm = {
  role: "WITNESS",
  full_name: "",
  alias: "",
  father_name: "",
  age: "",
  gender: "",
  phone: "",
  occupation: "",
  address: "",
};

export default function CaseDetailsTab({
  caseId,
  narrative,
  language,
  persons,
  statements,
  onPoolChanged,
}: {
  caseId: number;
  narrative: string | null;
  language: string | null;
  persons: Person[];
  statements: Statement[];
  onPoolChanged: () => void;
}) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,1fr)_360px] gap-8 items-start">
      {/* Left column: narrative as a document + statements below */}
      <div className="space-y-8 min-w-0">
        <NarrativeCard narrative={narrative} language={language} />
        <StatementsPanel
          caseId={caseId}
          persons={persons}
          statements={statements}
          onChanged={onPoolChanged}
        />
      </div>

      {/* Right column: persons grouped by role */}
      <PersonsPanel caseId={caseId} persons={persons} onChanged={onPoolChanged} />
    </div>
  );
}

function NarrativeCard({
  narrative,
  language,
}: {
  narrative: string | null;
  language: string | null;
}) {
  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded p-8">
      <div className="flex items-center justify-between border-b border-outline-variant pb-4 mb-6">
        <h2 className="font-headline-md text-primary">Complaint narrative</h2>
        {language && (
          <span className="font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
            {language}
          </span>
        )}
      </div>
      {narrative ? (
        // Set as a document: serif, comfortable measure, generous leading.
        <div className="font-serif text-body-lg leading-relaxed text-on-surface max-w-[68ch] whitespace-pre-wrap">
          {narrative}
        </div>
      ) : (
        <p className="font-body-md text-on-surface-variant italic">
          No complaint narrative recorded for this case.
        </p>
      )}
    </section>
  );
}

/* ---------------- Persons ---------------- */

function PersonsPanel({
  caseId,
  persons,
  onChanged,
}: {
  caseId: number;
  persons: Person[];
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<Person | "new" | null>(null);

  const grouped = useMemo(() => {
    return PERSON_ROLES.map((role) => ({
      role,
      people: persons.filter((p) => p.role === role),
    })).filter((g) => g.people.length > 0);
  }, [persons]);

  return (
    <aside className="bg-surface border border-outline-variant rounded">
      <div className="flex items-center justify-between px-5 py-4 border-b border-outline-variant">
        <h2 className="font-headline-md text-primary">People</h2>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="flex items-center gap-1 font-body-md text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          Add
        </button>
      </div>

      {editing && (
        <PersonForm
          caseId={caseId}
          person={editing === "new" ? null : editing}
          onDone={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}

      {grouped.length === 0 && !editing ? (
        <p className="px-5 py-8 font-body-md text-on-surface-variant text-center">
          No people added yet.
        </p>
      ) : (
        <div className="divide-y divide-outline-variant">
          {grouped.map((g) => (
            <div key={g.role} className="px-5 py-4">
              <p className="font-label-caps text-[10px] text-on-surface-variant mb-3">
                {g.people.length > 1
                  ? PERSON_ROLE_LABEL[g.role].plural
                  : PERSON_ROLE_LABEL[g.role].singular}
              </p>
              <ul className="space-y-3">
                {g.people.map((p) => (
                  <li key={p.id} className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-body-md text-on-surface">
                        {p.full_name ?? "Unnamed"}
                        {p.alias ? (
                          <span className="text-on-surface-variant"> · “{p.alias}”</span>
                        ) : null}
                      </p>
                      <p className="font-mono-sm text-on-surface-variant">
                        {[
                          p.age != null ? `${p.age}y` : null,
                          p.gender,
                          p.occupation,
                        ]
                          .filter(Boolean)
                          .join(" · ") || "—"}
                      </p>
                      {p.phone && (
                        <p className="font-mono-sm text-on-surface-variant">{p.phone}</p>
                      )}
                    </div>
                    <button
                      type="button"
                      onClick={() => setEditing(p)}
                      className="text-on-surface-variant hover:text-primary transition-colors shrink-0"
                      aria-label={`Edit ${p.full_name ?? "person"}`}
                    >
                      <span className="material-symbols-outlined text-lg">edit</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      )}
    </aside>
  );
}

function PersonForm({
  caseId,
  person,
  onDone,
  onSaved,
}: {
  caseId: number;
  person: Person | null;
  onDone: () => void;
  onSaved: () => void;
}) {
  const [f, setF] = useState<PersonForm>(
    person
      ? {
          role: person.role,
          full_name: person.full_name ?? "",
          alias: person.alias ?? "",
          father_name: person.father_name ?? "",
          age: person.age != null ? String(person.age) : "",
          gender: person.gender ?? "",
          phone: person.phone ?? "",
          occupation: person.occupation ?? "",
          address: person.address ?? "",
        }
      : EMPTY_PERSON
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const set = (k: keyof PersonForm, v: string) => setF((p) => ({ ...p, [k]: v }));

  async function save() {
    if (!f.full_name.trim()) {
      setErr("A name is required.");
      return;
    }
    setSaving(true);
    setErr(null);
    const body = { ...f, age: f.age === "" ? null : Number(f.age) };
    try {
      if (person) await api.patch(`/api/cases/${caseId}/persons/${person.id}`, body);
      else await api.post(`/api/cases/${caseId}/persons`, body);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Could not save.");
      setSaving(false);
    }
  }

  return (
    <div className="px-5 py-4 bg-surface-container-low border-b border-outline-variant space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">
        {person ? "Edit person" : "Add person"}
      </p>
      <FieldRow label="Role">
        <select
          value={f.role}
          onChange={(e) => set("role", e.target.value)}
          className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
        >
          {PERSON_ROLES.map((r) => (
            <option key={r} value={r}>
              {PERSON_ROLE_LABEL[r].singular}
            </option>
          ))}
        </select>
      </FieldRow>
      <FieldRow label="Full name">
        <TextInput value={f.full_name} onChange={(v) => set("full_name", v)} />
      </FieldRow>
      <div className="grid grid-cols-2 gap-3">
        <FieldRow label="Alias">
          <TextInput value={f.alias} onChange={(v) => set("alias", v)} />
        </FieldRow>
        <FieldRow label="Father's name">
          <TextInput value={f.father_name} onChange={(v) => set("father_name", v)} />
        </FieldRow>
        <FieldRow label="Age">
          <TextInput value={f.age} onChange={(v) => set("age", v)} />
        </FieldRow>
        <FieldRow label="Gender">
          <TextInput value={f.gender} onChange={(v) => set("gender", v)} />
        </FieldRow>
        <FieldRow label="Phone">
          <TextInput value={f.phone} onChange={(v) => set("phone", v)} />
        </FieldRow>
        <FieldRow label="Occupation">
          <TextInput value={f.occupation} onChange={(v) => set("occupation", v)} />
        </FieldRow>
      </div>
      <FieldRow label="Address">
        <TextInput value={f.address} onChange={(v) => set("address", v)} />
      </FieldRow>

      {err && (
        <p role="alert" className="font-body-md text-error flex items-center gap-1">
          <span className="material-symbols-outlined text-base">error</span>
          {err}
        </p>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
        >
          {saving ? "Saving…" : person ? "Save" : "Add"}
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

/* ---------------- Statements ---------------- */

function StatementsPanel({
  caseId,
  persons,
  statements,
  onChanged,
}: {
  caseId: number;
  persons: Person[];
  statements: Statement[];
  onChanged: () => void;
}) {
  const [adding, setAdding] = useState(false);
  const nameById = useMemo(() => {
    const m = new Map<number, string>();
    persons.forEach((p) => m.set(p.id, p.full_name ?? `Person ${p.id}`));
    return m;
  }, [persons]);

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded">
      <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant">
        <h2 className="font-headline-md text-primary">Statements</h2>
        <button
          type="button"
          onClick={() => setAdding((a) => !a)}
          className="flex items-center gap-1 font-body-md text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          Add statement
        </button>
      </div>

      {adding && (
        <StatementForm
          caseId={caseId}
          persons={persons}
          onDone={() => setAdding(false)}
          onSaved={() => {
            setAdding(false);
            onChanged();
          }}
        />
      )}

      {statements.length === 0 && !adding ? (
        <p className="px-6 py-8 font-body-md text-on-surface-variant text-center">
          No statements recorded yet.
        </p>
      ) : (
        <ul className="divide-y divide-outline-variant">
          {statements.map((s) => (
            <li key={s.id} className="px-6 py-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
                  {s.statement_type}
                </span>
                <span className="font-body-md text-on-surface">
                  {s.person_id != null ? nameById.get(s.person_id) ?? "—" : "—"}
                </span>
                {s.language && (
                  <span className="font-mono-sm text-on-surface-variant">{s.language}</span>
                )}
              </div>
              <p className="font-body-md text-on-surface-variant whitespace-pre-wrap">
                {s.statement_text}
              </p>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function StatementForm({
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
  const [personId, setPersonId] = useState("");
  const [type, setType] = useState("WITNESS");
  const [lang, setLang] = useState("EN");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!personId) {
      setErr("Select the person giving the statement.");
      return;
    }
    if (!text.trim()) {
      setErr("Statement text is required.");
      return;
    }
    setSaving(true);
    setErr(null);
    try {
      await api.post(`/api/cases/${caseId}/statements`, {
        person_id: Number(personId),
        statement_type: type,
        language: lang,
        statement_text: text,
      });
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Could not save.");
      setSaving(false);
    }
  }

  return (
    <div className="px-6 py-4 bg-surface-container-low border-b border-outline-variant space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <FieldRow label="Person">
          <select
            value={personId}
            onChange={(e) => setPersonId(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="">Select…</option>
            {persons.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name ?? `Person ${p.id}`} ({p.role})
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label="Type">
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {STATEMENT_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label="Language">
          <select
            value={lang}
            onChange={(e) => setLang(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {COMPLAINT_LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </FieldRow>
      </div>
      <FieldRow label="Statement">
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="What the person stated…"
          className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary resize-y"
        />
      </FieldRow>

      {err && (
        <p role="alert" className="font-body-md text-error flex items-center gap-1">
          <span className="material-symbols-outlined text-base">error</span>
          {err}
        </p>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          onClick={save}
          disabled={saving}
          className="flex items-center gap-1 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
        >
          {saving ? "Saving…" : "Add statement"}
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

/* ---------------- small shared inputs ---------------- */

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="font-label-caps text-[10px] text-on-surface-variant">{label}</span>
      {children}
    </label>
  );
}

function TextInput({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <input
      type="text"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
    />
  );
}

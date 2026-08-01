"use client";
import { useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n, type TKey } from "@/lib/i18n";
import { PERSON_ROLES } from "@/lib/cases";

/**
 * Conversational intake — the officer describes an incident in plain language and the
 * details are read into a case record they check field by field before anything is saved.
 *
 * THE DRAFT LIVES HERE, IN THE BROWSER. `/api/intake/extract` is a pure read: it opens no
 * transaction and writes no row. Only "Register case" sends the reviewed draft to
 * `/api/intake/commit`, which writes it in ONE transaction. Abandon this page and the case
 * simply never existed — there are no draft records to clean up.
 *
 * Because the officer and the extractor both write to the same record, edits are protected:
 * a field or row the officer has touched is never overwritten by a later extraction, and a
 * row they delete is not resurrected by it (see `mergeExtraction`).
 */

type Msg = { role: "officer" | "assistant"; content: string };

type CaseDraft = {
  case_number: string;
  case_type: string;
  title: string;
  fir_number: string;
  fir_date: string;
  police_station: string;
  district: string;
  incident_datetime: string;
  incident_location: string;
  complaint_narrative: string;
};

type PersonRow = {
  _key: string;
  _touched: boolean;
  role: string;
  full_name: string;
  alias: string;
  father_name: string;
  age: string;
  gender: string;
  address: string;
  phone: string;
  occupation: string;
};

type ItemRow = {
  _key: string;
  _touched: boolean;
  description: string;
  quantity: string;
  estimated_value: string;
  seized_from_name: string;
  seizure_datetime: string;
  seizure_location: string;
};

// The string-valued fields a later extraction may fill in on an existing row.
const PERSON_FILL_FIELDS = [
  "role",
  "full_name",
  "alias",
  "father_name",
  "age",
  "gender",
  "address",
  "phone",
  "occupation",
] as const;

const ITEM_FILL_FIELDS = [
  "description",
  "quantity",
  "estimated_value",
  "seized_from_name",
  "seizure_location",
] as const;

const CASE_FIELDS: (keyof CaseDraft)[] = [
  "title",
  "fir_number",
  "fir_date",
  "police_station",
  "district",
  "incident_datetime",
  "incident_location",
  "complaint_narrative",
];

const EMPTY_CASE: CaseDraft = {
  case_number: "",
  case_type: "CONVENTIONAL",
  title: "",
  fir_number: "",
  fir_date: "",
  police_station: "",
  district: "",
  incident_datetime: "",
  incident_location: "",
  complaint_narrative: "",
};

let keySeq = 0;
const nextKey = () => `r${++keySeq}`;

const blankPerson = (): PersonRow => ({
  _key: nextKey(),
  _touched: true, // hand-added rows are the officer's, never extractor-owned
  role: "ACCUSED",
  full_name: "",
  alias: "",
  father_name: "",
  age: "",
  gender: "",
  address: "",
  phone: "",
  occupation: "",
});

const blankItem = (): ItemRow => ({
  _key: nextKey(),
  _touched: true,
  description: "",
  quantity: "",
  estimated_value: "",
  seized_from_name: "",
  seizure_datetime: "",
  seizure_location: "",
});

// --- value helpers -------------------------------------------------------
const str = (v: unknown): string => (v === null || v === undefined ? "" : String(v));
const norm = (v: string): string => v.trim().toLowerCase();
// <input type="datetime-local"> wants "YYYY-MM-DDTHH:mm"; the API returns full ISO.
const toLocal = (v: unknown): string => str(v).slice(0, 16);
const orNull = (v: string): string | null => (v.trim() ? v.trim() : null);
const intOrNull = (v: string): number | null => {
  const n = parseInt(v.trim(), 10);
  return Number.isFinite(n) ? n : null;
};
const floatOrNull = (v: string): number | null => {
  const n = parseFloat(v.trim());
  return Number.isFinite(n) ? n : null;
};

export default function IntakePage() {
  const { user, ready } = useAuth();
  const { t, apiLang } = useI18n();
  const router = useRouter();

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [caseDraft, setCaseDraft] = useState<CaseDraft>(EMPTY_CASE);
  const [persons, setPersons] = useState<PersonRow[]>([]);
  const [items, setItems] = useState<ItemRow[]>([]);

  // Fields/rows the officer has edited — the extractor must not overwrite these.
  const touchedCase = useRef<Set<string>>(new Set());
  const dismissedPersons = useRef<Set<string>>(new Set());
  const dismissedItems = useRef<Set<string>>(new Set());

  const [extracting, setExtracting] = useState(false);
  const [committing, setCommitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [numberError, setNumberError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // Same convention as the manual form: suggest a unique number, officer can overwrite.
    setCaseDraft((prev) =>
      prev.case_number
        ? prev
        : { ...prev, case_number: `I-CR-${Math.floor(1000 + Math.random() * 9000)}-2026` }
    );
  }, [ready, user, router]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, extracting]);

  const hasDraft =
    persons.length > 0 ||
    items.length > 0 ||
    CASE_FIELDS.some((f) => caseDraft[f].trim() !== "");

  /**
   * Fold a fresh extraction into the record without trampling the officer.
   *  - a case field they edited keeps their value;
   *  - a person/item row they edited is left entirely alone;
   *  - a row they deleted stays deleted;
   *  - anything genuinely new is appended.
   * Rows are matched on name/description because the draft has no ids yet.
   */
  function mergeExtraction(draft: {
    case: Record<string, unknown>;
    persons: Record<string, unknown>[];
    seized_items: Record<string, unknown>[];
  }) {
    setCaseDraft((prev) => {
      const next = { ...prev };
      for (const field of CASE_FIELDS) {
        if (touchedCase.current.has(field)) continue;
        const raw = draft.case?.[field];
        if (raw === null || raw === undefined || raw === "") continue;
        next[field] =
          field === "incident_datetime" ? toLocal(raw) : field === "fir_date" ? str(raw).slice(0, 10) : str(raw);
      }
      return next;
    });

    setPersons((prev) => {
      const next = [...prev];
      for (const extracted of draft.persons ?? []) {
        const name = norm(str(extracted.full_name) || str(extracted.alias));
        if (!name || dismissedPersons.current.has(name)) continue;
        const idx = next.findIndex((p) => norm(p.full_name || p.alias) === name);
        if (idx === -1) {
          next.push({
            ...blankPerson(),
            _touched: false,
            role: str(extracted.role) || "ACCUSED",
            full_name: str(extracted.full_name),
            alias: str(extracted.alias),
            father_name: str(extracted.father_name),
            age: str(extracted.age),
            gender: str(extracted.gender),
            address: str(extracted.address),
            phone: str(extracted.phone),
            occupation: str(extracted.occupation),
          });
        } else if (!next[idx]._touched) {
          // Fill blanks a later turn supplied; never blank out what we already have.
          const row = { ...next[idx] };
          for (const field of PERSON_FILL_FIELDS) {
            const v = extracted[field];
            if (v === null || v === undefined || v === "") continue;
            row[field] = str(v);
          }
          next[idx] = row;
        }
      }
      return next;
    });

    setItems((prev) => {
      const next = [...prev];
      for (const extracted of draft.seized_items ?? []) {
        const desc = norm(str(extracted.description));
        if (!desc || dismissedItems.current.has(desc)) continue;
        const idx = next.findIndex((i) => norm(i.description) === desc);
        if (idx === -1) {
          next.push({
            ...blankItem(),
            _touched: false,
            description: str(extracted.description),
            quantity: str(extracted.quantity),
            estimated_value: str(extracted.estimated_value),
            seized_from_name: str(extracted.seized_from_name),
            seizure_datetime: toLocal(extracted.seizure_datetime),
            seizure_location: str(extracted.seizure_location),
          });
        } else if (!next[idx]._touched) {
          const row = { ...next[idx] };
          for (const field of ITEM_FILL_FIELDS) {
            const v = extracted[field];
            if (v === null || v === undefined || v === "") continue;
            row[field] = str(v);
          }
          if (extracted.seizure_datetime) row.seizure_datetime = toLocal(extracted.seizure_datetime);
          next[idx] = row;
        }
      }
      return next;
    });
  }

  async function onSend() {
    const text = input.trim();
    if (!text || extracting) return;

    const history: Msg[] = [...messages, { role: "officer", content: text }];
    setMessages(history);
    setInput("");
    setExtracting(true);
    setError(null);

    try {
      const res = await api.post("/api/intake/extract", { messages: history, lang: apiLang });
      mergeExtraction(res.data.draft);
      if (res.data.reply) {
        setMessages([...history, { role: "assistant", content: res.data.reply }]);
      }
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("intake.chat.error"));
    } finally {
      setExtracting(false);
    }
  }

  async function onConfirm() {
    if (committing) return;
    if (!caseDraft.case_number.trim()) {
      setNumberError(t("intake.numberRequired"));
      return;
    }
    setCommitting(true);
    setError(null);

    const payload = {
      case: {
        case_number: caseDraft.case_number.trim(),
        case_type: caseDraft.case_type,
        complaint_language: apiLang.toUpperCase(),
        title: orNull(caseDraft.title),
        fir_number: orNull(caseDraft.fir_number),
        fir_date: orNull(caseDraft.fir_date),
        police_station: orNull(caseDraft.police_station),
        district: orNull(caseDraft.district),
        incident_datetime: orNull(caseDraft.incident_datetime),
        incident_location: orNull(caseDraft.incident_location),
        complaint_narrative: orNull(caseDraft.complaint_narrative),
      },
      persons: persons.map((p) => ({
        role: p.role,
        full_name: orNull(p.full_name),
        alias: orNull(p.alias),
        father_name: orNull(p.father_name),
        age: intOrNull(p.age),
        gender: orNull(p.gender),
        address: orNull(p.address),
        phone: orNull(p.phone),
        occupation: orNull(p.occupation),
      })),
      seized_items: items.map((i) => ({
        description: orNull(i.description),
        quantity: intOrNull(i.quantity),
        estimated_value: floatOrNull(i.estimated_value),
        seized_from_name: orNull(i.seized_from_name),
        seizure_datetime: orNull(i.seizure_datetime),
        seizure_location: orNull(i.seizure_location),
      })),
    };

    try {
      const res = await api.post("/api/intake/commit", payload);
      router.push(`/cases/${res.data.case.id}`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("intake.commitError"));
      setCommitting(false);
    }
  }

  function setCaseField(field: keyof CaseDraft, value: string) {
    touchedCase.current.add(field);
    setCaseDraft((prev) => ({ ...prev, [field]: value }));
    if (field === "case_number" && value.trim()) setNumberError(null);
  }

  function setPersonField(key: string, field: keyof PersonRow, value: string) {
    // A seized item points at its person BY NAME until commit resolves it to an id.
    // Renaming the person must carry that reference along, or the item silently
    // detaches and lands in the pool with no "seized from".
    if (field === "full_name") {
      const previousName = persons.find((p) => p._key === key)?.full_name ?? "";
      if (previousName) {
        setItems((prev) =>
          prev.map((i) =>
            norm(i.seized_from_name) === norm(previousName) ? { ...i, seized_from_name: value } : i
          )
        );
      }
    }
    setPersons((prev) =>
      prev.map((p) => (p._key === key ? { ...p, [field]: value, _touched: true } : p))
    );
  }

  /** Seized-from choices: the people on this draft, plus any extracted name that no
   *  longer matches one (so an extraction is never silently discarded). */
  function seizedFromOptions(current: string): [string, string][] {
    const names = persons.map((p) => p.full_name || p.alias).filter((n) => n.trim() !== "");
    const options: [string, string][] = [["", t("common.none")]];
    for (const name of names) options.push([name, name]);
    if (current && !names.some((n) => norm(n) === norm(current))) options.push([current, current]);
    return options;
  }

  function setItemField(key: string, field: keyof ItemRow, value: string) {
    setItems((prev) =>
      prev.map((i) => (i._key === key ? { ...i, [field]: value, _touched: true } : i))
    );
  }

  function removePerson(row: PersonRow) {
    const name = norm(row.full_name || row.alias);
    if (name) dismissedPersons.current.add(name);
    setPersons((prev) => prev.filter((p) => p._key !== row._key));
  }

  function removeItem(row: ItemRow) {
    const desc = norm(row.description);
    if (desc) dismissedItems.current.add(desc);
    setItems((prev) => prev.filter((i) => i._key !== row._key));
  }

  function startOver() {
    setMessages([]);
    setInput("");
    setCaseDraft({ ...EMPTY_CASE, case_number: caseDraft.case_number });
    setPersons([]);
    setItems([]);
    touchedCase.current = new Set();
    dismissedPersons.current = new Set();
    dismissedItems.current = new Set();
    setError(null);
  }

  if (!ready || !user) return null;

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <button
          type="button"
          onClick={() => router.push("/cases")}
          className="text-on-surface-variant hover:text-primary transition-colors"
          aria-label={t("workspace.back")}
        >
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <h1 className="font-headline-lg text-primary">{t("intake.title")}</h1>
      </div>
      <p className="font-body-md text-on-surface-variant mb-6 ml-9 max-w-3xl">
        {t("intake.subtitle")}
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)] gap-6 items-start">
        {/* ---------------- Chat ---------------- */}
        <section className="border border-outline-variant rounded bg-surface-container-lowest flex flex-col lg:sticky lg:top-20">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-outline-variant">
            <span className="material-symbols-outlined text-on-surface-variant text-xl">forum</span>
            <h2 className="font-headline-md text-primary">{t("intake.chat.title")}</h2>
          </div>

          <div ref={scrollRef} className="px-5 py-4 space-y-4 overflow-y-auto custom-scrollbar h-[46vh] min-h-[280px]">
            <Bubble who={t("intake.chat.clerk")} tone="assistant">
              {t("intake.chat.intro")}
            </Bubble>
            {messages.map((m, idx) => (
              <Bubble
                key={idx}
                who={m.role === "officer" ? t("intake.chat.you") : t("intake.chat.clerk")}
                tone={m.role === "officer" ? "officer" : "assistant"}
              >
                {m.content}
              </Bubble>
            ))}
            {extracting && (
              <p className="font-body-md text-on-surface-variant flex items-center gap-2">
                <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
                {t("intake.chat.extracting")}
              </p>
            )}
          </div>

          <div className="border-t border-outline-variant p-4 space-y-3">
            <textarea
              rows={3}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) onSend();
              }}
              placeholder={t("intake.chat.placeholder")}
              className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors resize-y"
            />
            <div className="flex items-center gap-3">
              <button
                type="button"
                onClick={onSend}
                disabled={extracting || !input.trim()}
                className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-50"
              >
                <span className="material-symbols-outlined text-xl">send</span>
                {t("intake.chat.send")}
              </button>
              {(messages.length > 0 || hasDraft) && (
                <button
                  type="button"
                  onClick={startOver}
                  className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
                >
                  {t("intake.startOver")}
                </button>
              )}
            </div>
          </div>
        </section>

        {/* ---------------- Draft ---------------- */}
        <section className="border border-outline-variant rounded bg-surface-container-lowest">
          <div className="flex items-center gap-2 px-5 py-3 border-b border-outline-variant">
            <span className="material-symbols-outlined text-on-surface-variant text-xl">assignment</span>
            <h2 className="font-headline-md text-primary">{t("intake.draft.title")}</h2>
            <span className="ml-auto font-label-caps text-[9px] text-secondary border border-secondary rounded px-1.5 py-0.5">
              {t("intake.draft.unsaved")}
            </span>
          </div>

          {!hasDraft ? (
            <div className="p-10 text-center">
              <span className="material-symbols-outlined text-4xl text-outline">description</span>
              <p className="font-body-md text-on-surface mt-2">{t("intake.draft.empty.title")}</p>
              <p className="font-body-md text-on-surface-variant">{t("intake.draft.empty.hint")}</p>
            </div>
          ) : (
            <div className="p-5 space-y-6">
              <p className="font-body-md text-on-surface-variant flex items-start gap-2 bg-surface-container-low rounded px-3 py-2">
                <span className="material-symbols-outlined text-base mt-0.5">lock_open</span>
                {t("intake.draft.unsavedHint")}
              </p>

              {/* Incident */}
              <Group title={t("intake.section.case")}>
                <Grid>
                  <Field label={t("newCase.field.caseNumber")} required error={numberError}>
                    <Input
                      mono
                      value={caseDraft.case_number}
                      onChange={(v) => setCaseField("case_number", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.caseType")}>
                    <Select
                      value={caseDraft.case_type}
                      onChange={(v) => setCaseField("case_type", v)}
                      options={[
                        ["CONVENTIONAL", t("newCase.caseType.CONVENTIONAL")],
                        ["CYBER_FINANCIAL", t("newCase.caseType.CYBER_FINANCIAL")],
                      ]}
                    />
                  </Field>
                  <Field label={t("newCase.field.title")} full>
                    <Input value={caseDraft.title} onChange={(v) => setCaseField("title", v)} />
                  </Field>
                  <Field label={t("newCase.field.firNumber")}>
                    <Input
                      value={caseDraft.fir_number}
                      onChange={(v) => setCaseField("fir_number", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.firDate")}>
                    <Input
                      type="date"
                      value={caseDraft.fir_date}
                      onChange={(v) => setCaseField("fir_date", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.policeStation")}>
                    <Input
                      value={caseDraft.police_station}
                      onChange={(v) => setCaseField("police_station", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.district")}>
                    <Input
                      value={caseDraft.district}
                      onChange={(v) => setCaseField("district", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.incidentDatetime")}>
                    <Input
                      type="datetime-local"
                      value={caseDraft.incident_datetime}
                      onChange={(v) => setCaseField("incident_datetime", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.incidentLocation")}>
                    <Input
                      value={caseDraft.incident_location}
                      onChange={(v) => setCaseField("incident_location", v)}
                    />
                  </Field>
                  <Field label={t("newCase.field.narrative")} full>
                    <textarea
                      rows={5}
                      value={caseDraft.complaint_narrative}
                      onChange={(e) => setCaseField("complaint_narrative", e.target.value)}
                      className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors resize-y"
                    />
                  </Field>
                </Grid>
              </Group>

              {/* People */}
              <Group
                title={t("intake.section.persons")}
                action={
                  <AddButton onClick={() => setPersons((p) => [...p, blankPerson()])}>
                    {t("intake.addPerson")}
                  </AddButton>
                }
              >
                {persons.length === 0 ? (
                  <p className="font-body-md text-on-surface-variant">{t("details.people.empty")}</p>
                ) : (
                  <div className="space-y-4">
                    {persons.map((p) => (
                      <RowCard
                        key={p._key}
                        edited={p._touched}
                        editedLabel={t("intake.edited")}
                        onRemove={() => removePerson(p)}
                        removeLabel={t("intake.remove")}
                      >
                        <Grid>
                          <Field label={t("details.field.role")}>
                            <Select
                              value={p.role}
                              onChange={(v) => setPersonField(p._key, "role", v)}
                              options={PERSON_ROLES.map((r) => [r, t(`person.${r}.one` as TKey)])}
                            />
                          </Field>
                          <Field label={t("details.field.fullName")}>
                            <Input
                              value={p.full_name}
                              onChange={(v) => setPersonField(p._key, "full_name", v)}
                            />
                          </Field>
                          <Field label={t("details.field.alias")}>
                            <Input
                              value={p.alias}
                              onChange={(v) => setPersonField(p._key, "alias", v)}
                            />
                          </Field>
                          <Field label={t("details.field.fatherName")}>
                            <Input
                              value={p.father_name}
                              onChange={(v) => setPersonField(p._key, "father_name", v)}
                            />
                          </Field>
                          <Field label={t("details.field.age")}>
                            <Input
                              type="number"
                              value={p.age}
                              onChange={(v) => setPersonField(p._key, "age", v)}
                            />
                          </Field>
                          <Field label={t("details.field.gender")}>
                            <Input
                              value={p.gender}
                              onChange={(v) => setPersonField(p._key, "gender", v)}
                            />
                          </Field>
                          <Field label={t("details.field.phone")}>
                            <Input
                              value={p.phone}
                              onChange={(v) => setPersonField(p._key, "phone", v)}
                            />
                          </Field>
                          <Field label={t("details.field.occupation")}>
                            <Input
                              value={p.occupation}
                              onChange={(v) => setPersonField(p._key, "occupation", v)}
                            />
                          </Field>
                          <Field label={t("details.field.address")} full>
                            <Input
                              value={p.address}
                              onChange={(v) => setPersonField(p._key, "address", v)}
                            />
                          </Field>
                        </Grid>
                      </RowCard>
                    ))}
                  </div>
                )}
              </Group>

              {/* Seized items */}
              <Group
                title={t("intake.section.items")}
                action={
                  <AddButton onClick={() => setItems((i) => [...i, blankItem()])}>
                    {t("intake.addItem")}
                  </AddButton>
                }
              >
                {items.length === 0 ? (
                  <p className="font-body-md text-on-surface-variant">
                    {t("evidence.seized.empty.hint")}
                  </p>
                ) : (
                  <div className="space-y-4">
                    {items.map((i) => (
                      <RowCard
                        key={i._key}
                        edited={i._touched}
                        editedLabel={t("intake.edited")}
                        onRemove={() => removeItem(i)}
                        removeLabel={t("intake.remove")}
                      >
                        <Grid>
                          <Field label={t("evidence.col.description")} full>
                            <Input
                              value={i.description}
                              onChange={(v) => setItemField(i._key, "description", v)}
                            />
                          </Field>
                          <Field label={t("evidence.field.quantity")}>
                            <Input
                              type="number"
                              value={i.quantity}
                              onChange={(v) => setItemField(i._key, "quantity", v)}
                            />
                          </Field>
                          <Field label={t("evidence.field.estValue")}>
                            <Input
                              type="number"
                              value={i.estimated_value}
                              onChange={(v) => setItemField(i._key, "estimated_value", v)}
                            />
                          </Field>
                          <Field label={t("evidence.col.seizedFrom")}>
                            <Select
                              value={i.seized_from_name}
                              onChange={(v) => setItemField(i._key, "seized_from_name", v)}
                              options={seizedFromOptions(i.seized_from_name)}
                            />
                          </Field>
                          <Field label={t("evidence.field.seizureDatetime")}>
                            <Input
                              type="datetime-local"
                              value={i.seizure_datetime}
                              onChange={(v) => setItemField(i._key, "seizure_datetime", v)}
                            />
                          </Field>
                          <Field label={t("evidence.field.seizurePlace")} full>
                            <Input
                              value={i.seizure_location}
                              onChange={(v) => setItemField(i._key, "seizure_location", v)}
                            />
                          </Field>
                        </Grid>
                      </RowCard>
                    ))}
                  </div>
                )}
              </Group>

              {/* Confirmation gate */}
              <div className="border-t border-outline-variant pt-5 space-y-3">
                <p className="font-body-md text-on-surface-variant">{t("intake.confirmHint")}</p>
                <p className="font-body-md text-on-surface-variant flex items-start gap-2">
                  <span className="material-symbols-outlined text-base mt-0.5">gavel</span>
                  {t("intake.legalNote")}
                </p>
                <button
                  type="button"
                  onClick={onConfirm}
                  disabled={committing}
                  className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
                >
                  {committing ? (
                    <>
                      <span className="material-symbols-outlined animate-spin text-xl">
                        progress_activity
                      </span>
                      {t("intake.confirming")}
                    </>
                  ) : (
                    <>
                      <span className="material-symbols-outlined text-xl">check</span>
                      {t("intake.confirm")}
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </section>
      </div>

      {error && (
        <p role="alert" className="font-body-md text-error flex items-center gap-2 mt-6">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}
    </div>
  );
}

/* --- presentational helpers (mirroring app/cases/new) --- */

function Bubble({
  who,
  tone,
  children,
}: {
  who: string;
  tone: "officer" | "assistant";
  children: ReactNode;
}) {
  return (
    <div className={tone === "officer" ? "flex flex-col items-end" : "flex flex-col items-start"}>
      <span className="font-label-caps text-[9px] text-on-surface-variant mb-1">{who}</span>
      <div
        className={
          tone === "officer"
            ? "max-w-[85%] bg-surface-container-high text-on-surface rounded px-4 py-2.5 font-body-md whitespace-pre-wrap"
            : "max-w-[85%] bg-surface-container-low text-on-surface-variant border border-outline-variant rounded px-4 py-2.5 font-body-md whitespace-pre-wrap"
        }
      >
        {children}
      </div>
    </div>
  );
}

function Group({
  title,
  action,
  children,
}: {
  title: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div>
      <div className="flex items-center gap-3 mb-3">
        <h3 className="font-label-caps text-on-surface-variant">{title}</h3>
        <div className="flex-1 border-t border-outline-variant" />
        {action}
      </div>
      {children}
    </div>
  );
}

function RowCard({
  edited,
  editedLabel,
  onRemove,
  removeLabel,
  children,
}: {
  edited: boolean;
  editedLabel: string;
  onRemove: () => void;
  removeLabel: string;
  children: ReactNode;
}) {
  return (
    <div className="border border-outline-variant rounded bg-surface-container-low p-4">
      <div className="flex items-center gap-2 mb-3">
        {edited && (
          <span className="font-label-caps text-[9px] text-primary border border-primary rounded px-1.5 py-0.5">
            {editedLabel}
          </span>
        )}
        <button
          type="button"
          onClick={onRemove}
          className="ml-auto flex items-center gap-1 font-body-md text-on-surface-variant hover:text-error transition-colors"
        >
          <span className="material-symbols-outlined text-base">delete</span>
          {removeLabel}
        </button>
      </div>
      {children}
    </div>
  );
}

function AddButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="flex items-center gap-1 font-body-md text-primary hover:text-inverse-surface transition-colors"
    >
      <span className="material-symbols-outlined text-base">add</span>
      {children}
    </button>
  );
}

function Grid({ children }: { children: ReactNode }) {
  return <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-4">{children}</div>;
}

function Field({
  label,
  required,
  error,
  full,
  children,
}: {
  label: string;
  required?: boolean;
  error?: string | null;
  full?: boolean;
  children: ReactNode;
}) {
  const { t } = useI18n();
  return (
    <div className={`space-y-1.5 ${full ? "sm:col-span-2" : ""}`}>
      <div className="flex items-center gap-2">
        <label className="font-label-caps text-on-surface-variant">{label}</label>
        {required && (
          <span className="font-label-caps text-[9px] text-error border border-error rounded px-1 py-px">
            {t("common.required")}
          </span>
        )}
      </div>
      {children}
      {error && (
        <p className="font-body-md text-error flex items-center gap-1 text-[13px]">
          <span className="material-symbols-outlined text-sm">error</span>
          {error}
        </p>
      )}
    </div>
  );
}

function Input({
  value,
  onChange,
  type = "text",
  mono,
}: {
  value: string;
  onChange: (v: string) => void;
  type?: string;
  mono?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className={`w-full bg-surface-container-low border border-outline-variant rounded px-4 py-2.5 ${
        mono ? "font-mono-data" : "font-body-md"
      } text-on-surface focus:outline-none focus:border-primary transition-colors`}
    />
  );
}

function Select({
  value,
  onChange,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  options: [string, string][] | readonly (readonly [string, string])[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-2.5 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors"
    >
      {options.map(([v, label]) => (
        <option key={v} value={v}>
          {label}
        </option>
      ))}
    </select>
  );
}

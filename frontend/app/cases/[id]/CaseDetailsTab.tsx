"use client";
import { useEffect, useMemo, useRef, useState } from "react";

import { api } from "@/lib/api";
import { COMPLAINT_LANGS, PERSON_ROLES, STATEMENT_TYPES } from "@/lib/cases";
import { useI18n, type TKey } from "@/lib/i18n";

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
  dob_or_year?: string | null;
  nationality?: string | null;
  address_verified?: string | null;
  passport_no?: string | null;
  passport_issue_date?: string | null;
  passport_issue_place?: string | null;
  religion?: string | null;
  sc_st_obc?: string | null;
  provisional_criminal_no?: string | null;
  regular_criminal_no?: string | null;
  arrest_date?: string | null;
  bail_release_date?: string | null;
  forwarded_to_court_date?: string | null;
  arrest_acts_sections?: string | null;
  surety_details?: string | null;
  previous_convictions?: string | null;
  status_of_accused?: string | null;
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
  dob_or_year: string;
  nationality: string;
  address_verified: string;
  passport_no: string;
  passport_issue_date: string;
  passport_issue_place: string;
  religion: string;
  sc_st_obc: string;
  provisional_criminal_no: string;
  regular_criminal_no: string;
  arrest_date: string;
  bail_release_date: string;
  forwarded_to_court_date: string;
  arrest_acts_sections: string;
  surety_details: string;
  previous_convictions: string;
  status_of_accused: string;
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
  dob_or_year: "",
  nationality: "",
  address_verified: "",
  passport_no: "",
  passport_issue_date: "",
  passport_issue_place: "",
  religion: "",
  sc_st_obc: "",
  provisional_criminal_no: "",
  regular_criminal_no: "",
  arrest_date: "",
  bail_release_date: "",
  forwarded_to_court_date: "",
  arrest_acts_sections: "",
  surety_details: "",
  previous_convictions: "",
  status_of_accused: "",
};

const ACCUSED_STATUSES = [
  "FORWARDED",
  "BAILED_BY_POLICE",
  "BAILED_BY_COURT",
  "JUDICIAL_CUSTODY",
  "ABSCONDING",
  "PROCLAIMED_OFFENDER",
] as const;

function isoDate(v: string | null | undefined): string {
  if (!v) return "";
  return v.slice(0, 10);
}

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
      {/* Left column: narrative as a document + voice dictation + statements below */}
      <div className="space-y-8 min-w-0">
        <NarrativeCard narrative={narrative} language={language} />
        <VoiceDictation caseId={caseId} onApplied={onPoolChanged} />
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
  const { t } = useI18n();
  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded p-8">
      <div className="flex items-center justify-between border-b border-outline-variant pb-4 mb-6">
        <h2 className="font-headline-md text-primary">{t("details.narrative.title")}</h2>
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
          {t("details.narrative.empty")}
        </p>
      )}
    </section>
  );
}

/* ---------------- Voice dictation (CLAUDE.md §4 Gujarati voice-to-document) ---------------- */

type TranscribeResult = {
  transcript: string; // spoken-script text (e.g. Gujarati)
  language: string; // detected source (gu | hi | en)
  task: string;
  translation: string | null; // English narrative (null when source was English)
  duration: number | null;
  confidence: number | null;
  model: string | null;
  audio_id: string;
};

type VoiceState = "idle" | "recording" | "processing" | "done" | "error";

// Expected CPU transcription time (backend note: ~11s). Used only to pace the progress
// bar so the officer sees motion, not a bare spinner — the real completion is the POST.
const EXPECTED_MS = 11000;

function VoiceDictation({
  caseId,
  onApplied,
}: {
  caseId: number;
  onApplied: () => void;
}) {
  const { t, apiLang } = useI18n();
  const [state, setState] = useState<VoiceState>("idle");
  const [spokenLang, setSpokenLang] = useState<string>(apiLang);
  const [seconds, setSeconds] = useState(0);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState<TranscribeResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applying, setApplying] = useState(false);
  const [applied, setApplied] = useState(false);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const tickRef = useRef<number | undefined>(undefined);

  // Keep the spoken-language default in step with the interface language until the
  // officer overrides it.
  useEffect(() => {
    setSpokenLang(apiLang);
  }, [apiLang]);

  // Recording timer.
  useEffect(() => {
    if (state !== "recording") return;
    const id = window.setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => window.clearInterval(id);
  }, [state]);

  // Determinate-ish progress while the model runs — climbs toward 95% over ~11s and is
  // finished by the actual response. Not a bare spinner (CLAUDE.md §4 requirement).
  useEffect(() => {
    if (state !== "processing") return;
    setProgress(6);
    const start = Date.now();
    tickRef.current = window.setInterval(() => {
      const frac = Math.min((Date.now() - start) / EXPECTED_MS, 1);
      setProgress(6 + Math.round(frac * 89)); // 6 → 95
    }, 200);
    return () => window.clearInterval(tickRef.current);
  }, [state]);

  function cleanupStream() {
    streamRef.current?.getTracks().forEach((tr) => tr.stop());
    streamRef.current = null;
  }

  async function startRecording() {
    setError(null);
    setResult(null);
    setApplied(false);
    if (typeof navigator === "undefined" || !navigator.mediaDevices || typeof MediaRecorder === "undefined") {
      setError(t("voice.error.unsupported"));
      setState("error");
      return;
    }
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;
      const recorder = new MediaRecorder(stream);
      chunksRef.current = [];
      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onstop = () => {
        cleanupStream();
        void submit();
      };
      recorder.start();
      recorderRef.current = recorder;
      setSeconds(0);
      setState("recording");
    } catch {
      cleanupStream();
      setError(t("voice.error.mic"));
      setState("error");
    }
  }

  function stopRecording() {
    recorderRef.current?.stop();
  }

  async function submit() {
    setState("processing");
    const type = chunksRef.current[0]?.type || "audio/webm";
    const blob = new Blob(chunksRef.current, { type });
    if (!blob.size) {
      setError(t("voice.error.empty"));
      setState("error");
      return;
    }
    const ext = type.includes("ogg") ? "ogg" : type.includes("webm") ? "webm" : "wav";
    const fd = new FormData();
    fd.append("file", blob, `dictation.${ext}`);
    fd.append("language", spokenLang);
    fd.append("task", "transcribe");
    try {
      const r = await api.post<TranscribeResult>(`/api/cases/${caseId}/transcribe`, fd);
      const data = r.data;
      // Never accept a silent empty transcript — surface it as a clear failure.
      if (!data.transcript || !data.transcript.trim()) {
        setError(t("voice.error.failed"));
        setState("error");
        return;
      }
      setProgress(100);
      setResult(data);
      setState("done");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("voice.error.failed"));
      setState("error");
    }
  }

  function reset() {
    setResult(null);
    setError(null);
    setApplied(false);
    setSeconds(0);
    setProgress(0);
    setState("idle");
  }

  // The English text an officer applies to the record. When the source was already
  // English there is no separate translation, so the transcript itself is the English.
  const englishText = result ? result.translation ?? result.transcript : "";

  async function apply() {
    if (!englishText.trim()) return;
    setApplying(true);
    setError(null);
    try {
      await api.patch(`/api/cases/${caseId}`, { complaint_narrative: englishText });
      setApplied(true);
      onApplied();
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? t("voice.applyError"));
    } finally {
      setApplying(false);
    }
  }

  return (
    <section className="bg-surface border border-outline-variant rounded p-6">
      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-outline-variant pb-4 mb-5">
        <div className="min-w-0">
          <h2 className="font-headline-md text-primary flex items-center gap-2">
            <span className="material-symbols-outlined text-primary">mic</span>
            {t("voice.title")}
          </h2>
          <p className="font-body-md text-on-surface-variant mt-1 max-w-prose">
            {t("voice.subtitle")}
          </p>
        </div>

        {/* Spoken-language selector — defaults to the interface language. */}
        <label className="flex flex-col items-end gap-1">
          <span className="font-label-caps text-[10px] text-on-surface-variant">
            {t("voice.language")}
          </span>
          <select
            value={spokenLang}
            disabled={state === "recording" || state === "processing"}
            onChange={(e) => setSpokenLang(e.target.value)}
            className="bg-surface-container-lowest border border-outline-variant rounded px-3 py-1.5 font-body-md text-on-surface focus:outline-none focus:border-primary disabled:opacity-60"
          >
            {COMPLAINT_LANGS.map((code) => (
              <option key={code} value={code.toLowerCase()}>
                {code}
              </option>
            ))}
          </select>
        </label>
      </div>

      {/* Controls / state */}
      {state === "idle" || state === "error" ? (
        <div className="flex flex-col gap-3">
          <button
            type="button"
            onClick={startRecording}
            className="self-start flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
          >
            <span className="material-symbols-outlined">mic</span>
            {t("voice.record")}
          </button>
          {state === "error" && error && <ErrorLine message={error} />}
        </div>
      ) : state === "recording" ? (
        <div className="flex items-center gap-4">
          <button
            type="button"
            onClick={stopRecording}
            className="flex items-center gap-2 bg-error text-on-error px-5 py-2.5 rounded font-body-md font-semibold hover:opacity-90 transition-opacity"
          >
            <span className="material-symbols-outlined animate-pulse">stop_circle</span>
            {t("voice.stop")}
          </button>
          <span className="flex items-center gap-2 font-body-md text-on-surface">
            <span className="inline-block w-2.5 h-2.5 rounded-full bg-error animate-pulse" />
            {t("voice.recording", { sec: seconds })}
          </span>
        </div>
      ) : state === "processing" ? (
        <div className="max-w-xl">
          <div className="flex items-center justify-between mb-2">
            <span className="font-body-md text-on-surface flex items-center gap-2">
              <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
              {t("voice.processing")}
            </span>
            <span className="font-mono-sm text-on-surface-variant">{progress}%</span>
          </div>
          <div className="h-2 w-full bg-surface-container-high rounded-full overflow-hidden">
            <div
              className="h-full bg-primary transition-[width] duration-200 ease-linear"
              style={{ width: `${progress}%` }}
            />
          </div>
          <p className="font-body-md text-on-surface-variant mt-2">{t("voice.processingHint")}</p>
        </div>
      ) : null}

      {/* Result: transcript + translation side by side (review before applying) */}
      {state === "done" && result && (
        <div className="mt-2 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="border border-outline-variant rounded bg-surface-container-lowest p-4">
              <p className="font-label-caps text-[10px] text-on-surface-variant mb-2 flex items-center justify-between">
                <span>{t("voice.transcript")}</span>
                <span className="font-mono-sm normal-case tracking-normal text-on-surface-variant uppercase">
                  {result.language}
                </span>
              </p>
              <p className="font-serif text-body-lg leading-relaxed text-on-surface whitespace-pre-wrap">
                {result.transcript}
              </p>
            </div>
            <div className="border border-outline-variant rounded bg-surface-container-lowest p-4">
              <p className="font-label-caps text-[10px] text-on-surface-variant mb-2">
                {t("voice.translation")}
              </p>
              {result.translation ? (
                <p className="font-serif text-body-lg leading-relaxed text-on-surface whitespace-pre-wrap">
                  {result.translation}
                </p>
              ) : (
                <p className="font-body-md text-on-surface-variant italic">
                  {t("voice.noTranslation")}
                </p>
              )}
            </div>
          </div>

          <p className="font-body-md text-on-surface-variant flex items-start gap-2">
            <span className="material-symbols-outlined text-base text-on-surface-variant mt-0.5">info</span>
            {t("voice.reviewNote")}
          </p>

          {error && <ErrorLine message={error} />}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={apply}
              disabled={applying || applied || !englishText.trim()}
              className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
            >
              <span className="material-symbols-outlined text-lg">
                {applied ? "check_circle" : "playlist_add_check"}
              </span>
              {applied ? t("voice.applied") : t("voice.apply")}
            </button>
            <button
              type="button"
              onClick={reset}
              className="flex items-center gap-2 border border-outline-variant px-4 py-2 rounded font-body-md text-on-surface hover:bg-surface-container-low transition-colors"
            >
              <span className="material-symbols-outlined text-lg">restart_alt</span>
              {t("voice.rerecord")}
            </button>
            {result.duration != null && (
              <span className="font-mono-sm text-on-surface-variant">
                {t("voice.duration", { sec: Math.round(result.duration) })}
              </span>
            )}
          </div>
        </div>
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
  const { t } = useI18n();
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
        <h2 className="font-headline-md text-primary">{t("details.people.title")}</h2>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="flex items-center gap-1 font-body-md text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          {t("common.add")}
        </button>
      </div>

      {editing && (
        <PersonFormRow
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
          {t("details.people.empty")}
        </p>
      ) : (
        <div className="divide-y divide-outline-variant">
          {grouped.map((g) => (
            <div key={g.role} className="px-5 py-4">
              <p className="font-label-caps text-[10px] text-on-surface-variant mb-3">
                {t(`person.${g.role}.${g.people.length > 1 ? "many" : "one"}` as TKey)}
              </p>
              <ul className="space-y-3">
                {g.people.map((p) => (
                  <li key={p.id} className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="font-body-md text-on-surface">
                        {p.full_name ?? t("details.person.unnamed")}
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
                      aria-label={t("common.edit")}
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

function PersonFormRow({
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
  const { t } = useI18n();
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
          dob_or_year: person.dob_or_year ?? "",
          nationality: person.nationality ?? "",
          address_verified: person.address_verified ?? "",
          passport_no: person.passport_no ?? "",
          passport_issue_date: isoDate(person.passport_issue_date),
          passport_issue_place: person.passport_issue_place ?? "",
          religion: person.religion ?? "",
          sc_st_obc: person.sc_st_obc ?? "",
          provisional_criminal_no: person.provisional_criminal_no ?? "",
          regular_criminal_no: person.regular_criminal_no ?? "",
          arrest_date: isoDate(person.arrest_date),
          bail_release_date: isoDate(person.bail_release_date),
          forwarded_to_court_date: isoDate(person.forwarded_to_court_date),
          arrest_acts_sections: person.arrest_acts_sections ?? "",
          surety_details: person.surety_details ?? "",
          previous_convictions: person.previous_convictions ?? "",
          status_of_accused: person.status_of_accused ?? "",
        }
      : EMPTY_PERSON
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [csOpen, setCsOpen] = useState(
    Boolean(
      person?.role === "ACCUSED" &&
        (person.dob_or_year ||
          person.arrest_date ||
          person.status_of_accused ||
          person.nationality)
    )
  );

  const set = (k: keyof PersonForm, v: string) => setF((p) => ({ ...p, [k]: v }));

  async function save() {
    if (!f.full_name.trim()) {
      setErr(t("details.person.nameRequired"));
      return;
    }
    setSaving(true);
    setErr(null);
    const emptyToNull = (s: string) => (s.trim() === "" ? null : s.trim());
    const body: Record<string, unknown> = {
      role: f.role,
      full_name: emptyToNull(f.full_name),
      alias: emptyToNull(f.alias),
      father_name: emptyToNull(f.father_name),
      age: f.age === "" ? null : Number(f.age),
      gender: emptyToNull(f.gender),
      phone: emptyToNull(f.phone),
      occupation: emptyToNull(f.occupation),
      address: emptyToNull(f.address),
    };
    if (f.role === "ACCUSED") {
      Object.assign(body, {
        dob_or_year: emptyToNull(f.dob_or_year),
        nationality: emptyToNull(f.nationality),
        address_verified: emptyToNull(f.address_verified),
        passport_no: emptyToNull(f.passport_no),
        passport_issue_date: emptyToNull(f.passport_issue_date),
        passport_issue_place: emptyToNull(f.passport_issue_place),
        religion: emptyToNull(f.religion),
        sc_st_obc: emptyToNull(f.sc_st_obc),
        provisional_criminal_no: emptyToNull(f.provisional_criminal_no),
        regular_criminal_no: emptyToNull(f.regular_criminal_no),
        arrest_date: emptyToNull(f.arrest_date),
        bail_release_date: emptyToNull(f.bail_release_date),
        forwarded_to_court_date: emptyToNull(f.forwarded_to_court_date),
        arrest_acts_sections: emptyToNull(f.arrest_acts_sections),
        surety_details: emptyToNull(f.surety_details),
        previous_convictions: emptyToNull(f.previous_convictions),
        status_of_accused: emptyToNull(f.status_of_accused),
      });
    }
    try {
      if (person) await api.patch(`/api/cases/${caseId}/persons/${person.id}`, body);
      else await api.post(`/api/cases/${caseId}/persons`, body);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? t("details.saveError"));
      setSaving(false);
    }
  }

  return (
    <div className="px-5 py-4 bg-surface-container-low border-b border-outline-variant space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">
        {person ? t("details.person.edit") : t("details.person.add")}
      </p>
      <FieldRow label={t("details.field.role")}>
        <select
          value={f.role}
          onChange={(e) => {
            set("role", e.target.value);
            if (e.target.value === "ACCUSED") setCsOpen(true);
          }}
          className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
        >
          {PERSON_ROLES.map((r) => (
            <option key={r} value={r}>
              {t(`person.${r}.one` as TKey)}
            </option>
          ))}
        </select>
      </FieldRow>
      <FieldRow label={t("details.field.fullName")}>
        <TextInput value={f.full_name} onChange={(v) => set("full_name", v)} />
      </FieldRow>
      <div className="grid grid-cols-2 gap-3">
        <FieldRow label={t("details.field.alias")}>
          <TextInput value={f.alias} onChange={(v) => set("alias", v)} />
        </FieldRow>
        <FieldRow label={t("details.field.fatherName")}>
          <TextInput value={f.father_name} onChange={(v) => set("father_name", v)} />
        </FieldRow>
        <FieldRow label={t("details.field.age")}>
          <TextInput value={f.age} onChange={(v) => set("age", v)} />
        </FieldRow>
        <FieldRow label={t("details.field.gender")}>
          <TextInput value={f.gender} onChange={(v) => set("gender", v)} />
        </FieldRow>
        <FieldRow label={t("details.field.phone")}>
          <TextInput value={f.phone} onChange={(v) => set("phone", v)} />
        </FieldRow>
        <FieldRow label={t("details.field.occupation")}>
          <TextInput value={f.occupation} onChange={(v) => set("occupation", v)} />
        </FieldRow>
      </div>
      <FieldRow label={t("details.field.address")}>
        <TextInput value={f.address} onChange={(v) => set("address", v)} />
      </FieldRow>

      {f.role === "ACCUSED" && (
        <div className="border border-outline-variant rounded overflow-hidden">
          <button
            type="button"
            onClick={() => setCsOpen((o) => !o)}
            className="w-full flex items-center justify-between px-3 py-2 bg-surface-container-lowest font-body-md text-on-surface hover:bg-surface-container transition-colors"
            aria-expanded={csOpen}
          >
            <span>{t("details.chargesheet.group")}</span>
            <span className="material-symbols-outlined text-base text-on-surface-variant">
              {csOpen ? "expand_less" : "expand_more"}
            </span>
          </button>
          {csOpen && (
            <div className="px-3 py-3 space-y-3 border-t border-outline-variant">
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label={t("details.field.dobOrYear")}>
                  <TextInput value={f.dob_or_year} onChange={(v) => set("dob_or_year", v)} />
                </FieldRow>
                <FieldRow label={t("details.field.nationality")}>
                  <TextInput value={f.nationality} onChange={(v) => set("nationality", v)} />
                </FieldRow>
                <FieldRow label={t("details.field.addressVerified")}>
                  <TextInput
                    value={f.address_verified}
                    onChange={(v) => set("address_verified", v)}
                  />
                </FieldRow>
                <FieldRow label={t("details.field.religion")}>
                  <TextInput value={f.religion} onChange={(v) => set("religion", v)} />
                </FieldRow>
                <FieldRow label={t("details.field.scStObc")}>
                  <TextInput value={f.sc_st_obc} onChange={(v) => set("sc_st_obc", v)} />
                </FieldRow>
                <FieldRow label={t("details.field.statusOfAccused")}>
                  <select
                    value={f.status_of_accused}
                    onChange={(e) => set("status_of_accused", e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
                  >
                    <option value="">{t("common.select")}</option>
                    {ACCUSED_STATUSES.map((s) => (
                      <option key={s} value={s}>
                        {t(`details.status.${s}` as TKey)}
                      </option>
                    ))}
                  </select>
                </FieldRow>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label={t("details.field.passportNo")}>
                  <TextInput value={f.passport_no} onChange={(v) => set("passport_no", v)} />
                </FieldRow>
                <FieldRow label={t("details.field.passportIssueDate")}>
                  <input
                    type="date"
                    value={f.passport_issue_date}
                    onChange={(e) => set("passport_issue_date", e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
                  />
                </FieldRow>
                <FieldRow label={t("details.field.passportIssuePlace")}>
                  <TextInput
                    value={f.passport_issue_place}
                    onChange={(v) => set("passport_issue_place", v)}
                  />
                </FieldRow>
                <FieldRow label={t("details.field.provCriminalNo")}>
                  <TextInput
                    value={f.provisional_criminal_no}
                    onChange={(v) => set("provisional_criminal_no", v)}
                  />
                </FieldRow>
                <FieldRow label={t("details.field.regCriminalNo")}>
                  <TextInput
                    value={f.regular_criminal_no}
                    onChange={(v) => set("regular_criminal_no", v)}
                  />
                </FieldRow>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <FieldRow label={t("details.field.arrestDate")}>
                  <input
                    type="date"
                    value={f.arrest_date}
                    onChange={(e) => set("arrest_date", e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
                  />
                </FieldRow>
                <FieldRow label={t("details.field.bailReleaseDate")}>
                  <input
                    type="date"
                    value={f.bail_release_date}
                    onChange={(e) => set("bail_release_date", e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
                  />
                </FieldRow>
                <FieldRow label={t("details.field.forwardedToCourtDate")}>
                  <input
                    type="date"
                    value={f.forwarded_to_court_date}
                    onChange={(e) => set("forwarded_to_court_date", e.target.value)}
                    className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
                  />
                </FieldRow>
              </div>
              <FieldRow label={t("details.field.arrestActsSections")}>
                <TextInput
                  value={f.arrest_acts_sections}
                  onChange={(v) => set("arrest_acts_sections", v)}
                />
              </FieldRow>
              <FieldRow label={t("details.field.suretyDetails")}>
                <TextInput
                  value={f.surety_details}
                  onChange={(v) => set("surety_details", v)}
                />
              </FieldRow>
              <FieldRow label={t("details.field.previousConvictions")}>
                <TextInput
                  value={f.previous_convictions}
                  onChange={(v) => set("previous_convictions", v)}
                />
              </FieldRow>
            </div>
          )}
        </div>
      )}

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
          {saving ? t("common.saving") : person ? t("common.save") : t("common.add")}
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
  const { t } = useI18n();
  const [adding, setAdding] = useState(false);
  const nameById = useMemo(() => {
    const m = new Map<number, string>();
    persons.forEach((p) => m.set(p.id, p.full_name ?? `Person ${p.id}`));
    return m;
  }, [persons]);

  return (
    <section className="bg-surface-container-lowest border border-outline-variant rounded">
      <div className="flex items-center justify-between px-6 py-4 border-b border-outline-variant">
        <h2 className="font-headline-md text-primary">{t("details.statements.title")}</h2>
        <button
          type="button"
          onClick={() => setAdding((a) => !a)}
          className="flex items-center gap-1 font-body-md text-primary hover:underline"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          {t("details.statements.add")}
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
          {t("details.statements.empty")}
        </p>
      ) : (
        <ul className="divide-y divide-outline-variant">
          {statements.map((s) => (
            <li key={s.id} className="px-6 py-4">
              <div className="flex items-center gap-2 mb-1">
                <span className="font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
                  {t(`statementType.${s.statement_type}` as TKey)}
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
  const { t } = useI18n();
  const [personId, setPersonId] = useState("");
  const [type, setType] = useState("WITNESS");
  const [lang, setLang] = useState("EN");
  const [text, setText] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (!personId) {
      setErr(t("details.statement.selectPerson"));
      return;
    }
    if (!text.trim()) {
      setErr(t("details.statement.textRequired"));
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
      setErr(e?.response?.data?.detail ?? t("details.saveError"));
      setSaving(false);
    }
  }

  return (
    <div className="px-6 py-4 bg-surface-container-low border-b border-outline-variant space-y-3">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <FieldRow label={t("details.statement.person")}>
          <select
            value={personId}
            onChange={(e) => setPersonId(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="">{t("common.select")}</option>
            {persons.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name ?? `Person ${p.id}`} ({p.role})
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label={t("details.statement.type")}>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {STATEMENT_TYPES.map((tp) => (
              <option key={tp} value={tp}>
                {t(`statementType.${tp}` as TKey)}
              </option>
            ))}
          </select>
        </FieldRow>
        <FieldRow label={t("details.statement.language")}>
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
      <FieldRow label={t("details.statement.text")}>
        <textarea
          rows={4}
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={t("details.statement.placeholder")}
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
          {saving ? t("common.saving") : t("details.statements.add")}
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

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-center gap-2 font-body-md text-error">
      <span className="material-symbols-outlined text-base">error</span>
      {message}
    </p>
  );
}

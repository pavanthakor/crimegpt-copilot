"use client";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/lib/i18n";

type Form = {
  case_number: string;
  title: string;
  case_type: string;
  fir_number: string;
  fir_date: string;
  police_station: string;
  district: string;
  incident_datetime: string;
  incident_location: string;
  complaint_narrative: string;
  complaint_language: string;
};

const EMPTY: Form = {
  case_number: "",
  title: "",
  case_type: "CONVENTIONAL",
  fir_number: "",
  fir_date: "",
  police_station: "",
  district: "",
  incident_datetime: "",
  incident_location: "",
  complaint_narrative: "",
  complaint_language: "EN",
};

// Sent even when blank (they carry a chosen default); everything else only if filled.
const ALWAYS = ["case_number", "case_type", "complaint_language"] as const;
const OPTIONAL: (keyof Form)[] = [
  "title",
  "fir_number",
  "fir_date",
  "police_station",
  "district",
  "incident_datetime",
  "incident_location",
  "complaint_narrative",
];

export default function NewCasePage() {
  const { user, ready } = useAuth();
  const { t } = useI18n();
  const router = useRouter();
  const [f, setF] = useState<Form>(EMPTY);
  const [error, setError] = useState<string | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // case_number must be unique — offer a suggestion the officer can overwrite.
    setF((prev) =>
      prev.case_number
        ? prev
        : { ...prev, case_number: `I-CR-${Math.floor(1000 + Math.random() * 9000)}-2026` }
    );
  }, [ready, user, router]);

  function set(key: keyof Form, value: string) {
    setF((prev) => ({ ...prev, [key]: value }));
    if (key === "case_number" && value.trim()) setFieldError(null);
  }

  async function onCreate() {
    if (saving) return;
    if (!f.case_number.trim()) {
      setFieldError(t("newCase.numberRequired"));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, string> = {};
      for (const k of ALWAYS) payload[k] = f[k];
      for (const k of OPTIONAL) if (f[k]) payload[k] = f[k];
      const res = await api.post("/api/cases", payload);
      router.push(`/cases/${res.data.id}`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : t("newCase.createError"));
      setSaving(false);
    }
  }

  if (!ready || !user) return null;

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="flex items-center gap-2 mb-1">
        <button
          type="button"
          onClick={() => router.push("/cases")}
          className="text-on-surface-variant hover:text-primary transition-colors"
          aria-label={t("workspace.back")}
        >
          <span className="material-symbols-outlined">arrow_back</span>
        </button>
        <h1 className="font-headline-lg text-primary">{t("newCase.title")}</h1>
      </div>
      <p className="font-body-md text-on-surface-variant mb-6 ml-9">
        {t("newCase.subtitle")}
      </p>

      <div className="space-y-6">
        {/* Basic Information */}
        <Section title={t("newCase.section.identity")} icon="badge">
          <Grid>
            <Field label={t("newCase.field.caseNumber")} required error={fieldError}>
              <TextInput
                value={f.case_number}
                onChange={(v) => set("case_number", v)}
                mono
                placeholder="I-CR-0000-2026"
              />
            </Field>
            <Field label={t("newCase.field.caseType")}>
              <Select
                value={f.case_type}
                onChange={(v) => set("case_type", v)}
                options={[
                  ["CONVENTIONAL", t("newCase.caseType.CONVENTIONAL")],
                  ["CYBER_FINANCIAL", t("newCase.caseType.CYBER_FINANCIAL")],
                ]}
              />
            </Field>
            <Field label={t("newCase.field.title")} full>
              <TextInput
                value={f.title}
                onChange={(v) => set("title", v)}
                placeholder="Short description of the case"
              />
            </Field>
            <Field label={t("newCase.field.firNumber")}>
              <TextInput value={f.fir_number} onChange={(v) => set("fir_number", v)} />
            </Field>
            <Field label={t("newCase.field.firDate")}>
              <TextInput type="date" value={f.fir_date} onChange={(v) => set("fir_date", v)} />
            </Field>
            <Field label={t("newCase.field.policeStation")}>
              <TextInput
                value={f.police_station}
                onChange={(v) => set("police_station", v)}
              />
            </Field>
            <Field label={t("newCase.field.district")}>
              <TextInput value={f.district} onChange={(v) => set("district", v)} />
            </Field>
          </Grid>
        </Section>

        {/* Incident Details */}
        <Section title={t("newCase.section.incident")} icon="location_on">
          <Grid>
            <Field label={t("newCase.field.incidentDatetime")}>
              <TextInput
                type="datetime-local"
                value={f.incident_datetime}
                onChange={(v) => set("incident_datetime", v)}
              />
            </Field>
            <Field label={t("newCase.field.incidentLocation")}>
              <TextInput
                value={f.incident_location}
                onChange={(v) => set("incident_location", v)}
                placeholder="Where the offence took place"
              />
            </Field>
          </Grid>
        </Section>

        {/* Complaint Narrative */}
        <Section title={t("newCase.section.complaint")} icon="description">
          <Grid>
            <Field label={t("newCase.field.language")}>
              <Select
                value={f.complaint_language}
                onChange={(v) => set("complaint_language", v)}
                options={[
                  ["EN", "English"],
                  ["HI", "हिंदी"],
                  ["GU", "ગુજરાતી"],
                ]}
              />
            </Field>
            <Field label={t("newCase.field.narrative")} full>
              <textarea
                rows={6}
                value={f.complaint_narrative}
                onChange={(e) => set("complaint_narrative", e.target.value)}
                placeholder="Describe the complaint in the officer's own words…"
                className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors resize-y"
              />
            </Field>
          </Grid>
        </Section>
      </div>

      {error && (
        <p role="alert" className="font-body-md text-error flex items-center gap-2 mt-6">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      {/* Actions */}
      <div className="flex items-center gap-3 mt-6">
        <button
          type="button"
          onClick={onCreate}
          disabled={saving}
          className="flex items-center gap-2 bg-primary text-surface-bright px-5 py-2.5 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
        >
          {saving ? (
            <>
              <span className="material-symbols-outlined animate-spin text-xl">
                progress_activity
              </span>
              {t("newCase.creating")}
            </>
          ) : (
            <>
              <span className="material-symbols-outlined text-xl">check</span>
              {t("newCase.create")}
            </>
          )}
        </button>
        <button
          type="button"
          onClick={() => router.push("/cases")}
          className="px-5 py-2.5 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
        >
          {t("common.cancel")}
        </button>
      </div>
    </div>
  );
}

/* --- small presentational helpers (labels always above inputs) --- */

function Section({ title, icon, children }: { title: string; icon: string; children: ReactNode }) {
  return (
    <section className="border border-outline-variant rounded bg-surface-container-lowest">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-outline-variant">
        <span className="material-symbols-outlined text-on-surface-variant text-xl">{icon}</span>
        <h2 className="font-headline-md text-primary">{title}</h2>
      </div>
      <div className="p-5">{children}</div>
    </section>
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

function TextInput({
  value,
  onChange,
  type = "text",
  placeholder,
  mono,
}: {
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
  mono?: boolean;
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
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
  options: [string, string][];
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

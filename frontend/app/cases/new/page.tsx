"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

type Form = {
  case_number: string;
  title: string;
  fir_number: string;
  fir_date: string;
  police_station: string;
  district: string;
  incident_datetime: string;
  incident_location: string;
  complaint_narrative: string;
  complaint_language: string;
};

const OPTIONAL_KEYS: (keyof Form)[] = [
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
  const router = useRouter();
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const [f, setF] = useState<Form>({
    case_number: "",
    title: "",
    fir_number: "",
    fir_date: "",
    police_station: "",
    district: "",
    incident_datetime: "",
    incident_location: "",
    complaint_narrative: "",
    complaint_language: "EN",
  });

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    // case_number is required by the API but wasn't in the field list — suggest one.
    setF((prev) =>
      prev.case_number
        ? prev
        : { ...prev, case_number: `I-CR-${Math.floor(1000 + Math.random() * 9000)}-2026` }
    );
  }, [ready, user, router]);

  function set(key: keyof Form, value: string) {
    setF((prev) => ({ ...prev, [key]: value }));
  }

  async function onCreate() {
    setSaving(true);
    setError(null);
    try {
      const payload: Record<string, string> = {
        case_number: f.case_number,
        complaint_language: f.complaint_language,
      };
      for (const k of OPTIONAL_KEYS) {
        if (f[k]) payload[k] = f[k];
      }
      const res = await api.post("/api/cases", payload);
      router.push(`/cases/${res.data.id}`);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      setError(typeof detail === "string" ? detail : "Create failed");
    } finally {
      setSaving(false);
    }
  }

  if (!ready || !user) return <p>Loading…</p>;

  return (
    <div style={{ maxWidth: 560 }}>
      <h1>New case</h1>

      <label>Case number *</label>
      <input value={f.case_number} onChange={(e) => set("case_number", e.target.value)} />
      <label>Title</label>
      <input value={f.title} onChange={(e) => set("title", e.target.value)} />
      <label>FIR number</label>
      <input value={f.fir_number} onChange={(e) => set("fir_number", e.target.value)} />
      <label>FIR date</label>
      <input type="date" value={f.fir_date} onChange={(e) => set("fir_date", e.target.value)} />
      <label>Police station</label>
      <input value={f.police_station} onChange={(e) => set("police_station", e.target.value)} />
      <label>District</label>
      <input value={f.district} onChange={(e) => set("district", e.target.value)} />
      <label>Incident datetime</label>
      <input
        type="datetime-local"
        value={f.incident_datetime}
        onChange={(e) => set("incident_datetime", e.target.value)}
      />
      <label>Incident location</label>
      <input
        value={f.incident_location}
        onChange={(e) => set("incident_location", e.target.value)}
      />
      <label>Complaint narrative</label>
      <textarea
        rows={4}
        value={f.complaint_narrative}
        onChange={(e) => set("complaint_narrative", e.target.value)}
      />
      <label>Complaint language</label>
      <select
        value={f.complaint_language}
        onChange={(e) => set("complaint_language", e.target.value)}
      >
        <option value="EN">EN</option>
        <option value="HI">HI</option>
        <option value="GU">GU</option>
      </select>

      <div style={{ marginTop: 12 }}>
        <button onClick={onCreate} disabled={saving}>
          {saving ? "Saving…" : "Create case"}
        </button>
        <button onClick={() => router.push("/cases")} style={{ marginLeft: 8 }}>
          Cancel
        </button>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}
    </div>
  );
}

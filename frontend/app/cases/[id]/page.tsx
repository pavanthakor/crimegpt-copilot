"use client";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

const TABS = [
  "Persons",
  "Seized Items",
  "Statements",
  "Evidence",
  "Sections",
  "Documents",
  "Diary",
] as const;
type Tab = (typeof TABS)[number];

export default function CaseDetailPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const params = useParams<{ id: string }>();
  const [data, setData] = useState<any | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>("Persons");

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    api
      .get(`/api/cases/${params.id}`)
      .then((r) => setData(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load case"));
  }, [ready, user, params.id, router]);

  if (!ready || !user) return <p>Loading…</p>;
  if (error) return <p style={{ color: "red" }}>{error}</p>;
  if (!data) return <p>Loading…</p>;

  return (
    <div>
      <button onClick={() => router.push("/cases")}>← Back to cases</button>
      <h1>
        {data.case_number} — {data.title}
      </h1>

      <table style={{ maxWidth: 720, marginBottom: 16 }}>
        <tbody>
          <tr><th>Status</th><td>{data.status}</td></tr>
          <tr><th>Type</th><td>{data.case_type}</td></tr>
          <tr><th>FIR</th><td>{data.fir_number} ({data.fir_date ?? "-"})</td></tr>
          <tr><th>Police station</th><td>{data.police_station}</td></tr>
          <tr><th>District</th><td>{data.district}</td></tr>
          <tr><th>Incident</th><td>{data.incident_location} ({data.incident_datetime ?? "-"})</td></tr>
          <tr><th>Language</th><td>{data.complaint_language}</td></tr>
          <tr><th>Narrative</th><td style={{ whiteSpace: "pre-wrap" }}>{data.complaint_narrative}</td></tr>
        </tbody>
      </table>

      <div style={{ display: "flex", gap: 4, borderBottom: "2px solid #ccc" }}>
        {TABS.map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            style={{
              fontWeight: tab === t ? 700 : 400,
              background: tab === t ? "#eee" : "white",
              border: "1px solid #ccc",
              borderBottom: "none",
            }}
          >
            {t}
          </button>
        ))}
      </div>

      <div style={{ padding: 12, border: "1px solid #ccc", borderTop: "none" }}>
        {tab === "Persons" && <PersonsTab rows={data.persons} />}
        {tab === "Seized Items" && <SeizedTab rows={data.seized_items} />}
        {tab === "Statements" && <StatementsTab rows={data.statements} />}
        {tab === "Documents" && <DocumentsTab rows={data.documents} />}
        {tab === "Diary" && <DiaryTab rows={data.diary_entries} />}
        {tab === "Evidence" && <Placeholder name="Evidence" />}
        {tab === "Sections" && <Placeholder name="Legal sections" />}
      </div>
    </div>
  );
}

function Placeholder({ name }: { name: string }) {
  return <p style={{ color: "#888" }}>{name}: not implemented yet (later slice).</p>;
}

function PersonsTab({ rows }: { rows: any[] }) {
  if (!rows?.length) return <p>No persons.</p>;
  return (
    <table>
      <thead>
        <tr><th>Role</th><th>Name</th><th>Alias</th><th>Age</th><th>Gender</th><th>Phone</th><th>Occupation</th></tr>
      </thead>
      <tbody>
        {rows.map((p) => (
          <tr key={p.id}>
            <td>{p.role}</td><td>{p.full_name}</td><td>{p.alias}</td><td>{p.age}</td>
            <td>{p.gender}</td><td>{p.phone}</td><td>{p.occupation}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function SeizedTab({ rows }: { rows: any[] }) {
  if (!rows?.length) return <p>No seized items.</p>;
  return (
    <table>
      <thead>
        <tr><th>Description</th><th>Qty</th><th>Est. value</th><th>Seized from (person id)</th><th>Location</th></tr>
      </thead>
      <tbody>
        {rows.map((s) => (
          <tr key={s.id}>
            <td>{s.description}</td><td>{s.quantity}</td><td>{s.estimated_value}</td>
            <td>{s.seized_from}</td><td>{s.seizure_location}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StatementsTab({ rows }: { rows: any[] }) {
  if (!rows?.length) return <p>No statements.</p>;
  return (
    <ul>
      {rows.map((s) => (
        <li key={s.id}>
          <b>{s.statement_type}</b> (person {s.person_id}, {s.language}): {s.statement_text}
        </li>
      ))}
    </ul>
  );
}

function DocumentsTab({ rows }: { rows: any[] }) {
  if (!rows?.length) return <p>No documents.</p>;
  return (
    <ul>
      {rows.map((d) => (
        <li key={d.id}>
          {d.doc_type} v{d.version} — {d.status}
        </li>
      ))}
    </ul>
  );
}

function DiaryTab({ rows }: { rows: any[] }) {
  if (!rows?.length) return <p>No diary entries.</p>;
  return (
    <ul>
      {rows.map((e) => (
        <li key={e.id}>
          <b>{e.activity_type}</b> {e.auto_generated ? "(auto)" : ""} — {e.description}{" "}
          <i>[{e.entry_datetime}]</i>
        </li>
      ))}
    </ul>
  );
}

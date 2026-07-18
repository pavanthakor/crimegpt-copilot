"use client";
import { useEffect, useState, type CSSProperties } from "react";
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
        {tab === "Sections" && (
          <SectionsTab caseId={data.id} narrative={data.complaint_narrative ?? ""} />
        )}
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

// ---------------- Sections (Legal Intelligence) ----------------
const STATUS_STYLE: Record<string, CSSProperties> = {
  SUGGESTED: { background: "#fffbe6", border: "1px solid #ffe58f" },
  ACCEPTED: { background: "#f6ffed", border: "2px solid #52c41a" },
  REJECTED: { background: "#fafafa", border: "1px solid #d9d9d9", opacity: 0.65 },
};

function Highlighted({ text, phrase }: { text: string; phrase?: string | null }) {
  if (!text) return null;
  const base: CSSProperties = {
    whiteSpace: "pre-wrap",
    display: "block",
    maxHeight: 160,
    overflow: "auto",
    background: "#fff",
    border: "1px solid #eee",
    padding: 8,
    fontSize: 13,
  };
  if (!phrase) return <span style={base}>{text}</span>;
  const idx = text.toLowerCase().indexOf(phrase.toLowerCase());
  if (idx === -1) {
    // Phrase was validated against the analyzed narrative but isn't in the complaint
    // text shown here (e.g. it came from a statement). Never render blank — show it.
    return (
      <div>
        <span style={base}>{text}</span>
        <p style={{ color: "#a00", margin: "4px 0 0" }}>
          Triggering phrase: “{phrase}” (not located in the complaint text above)
        </p>
      </div>
    );
  }
  return (
    <span style={base}>
      {text.slice(0, idx)}
      <mark style={{ background: "#ffe58f", fontWeight: 700 }}>
        {text.slice(idx, idx + phrase.length)}
      </mark>
      {text.slice(idx + phrase.length)}
    </span>
  );
}

function SectionsTab({ caseId, narrative }: { caseId: number; narrative: string }) {
  const [sections, setSections] = useState<any[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [rejected, setRejected] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .get(`/api/cases/${caseId}/sections`)
      .then((r) => setSections(r.data))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load sections"));
  }, [caseId]);

  async function analyze() {
    setLoading(true);
    setErr(null);
    try {
      const r = await api.post(`/api/cases/${caseId}/analyze`);
      setStatus(r.data.status);
      setRejected(r.data.rejected ?? []);
      // Refetch the authoritative list (new suggestions + any prior decisions).
      const list = await api.get(`/api/cases/${caseId}/sections`);
      setSections(list.data);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Analysis failed");
    } finally {
      setLoading(false);
    }
  }

  async function decide(sid: number, decision: "ACCEPTED" | "REJECTED") {
    try {
      const r = await api.patch(`/api/cases/${caseId}/sections/${sid}`, {
        status: decision,
      });
      setSections((prev) => prev.map((s) => (s.id === sid ? r.data : s)));
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Update failed");
    }
  }

  return (
    <div>
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 12 }}>
        <button onClick={analyze} disabled={loading}>
          {loading ? "Analyzing… (~5s)" : "Analyze with AI"}
        </button>
        {loading && <span style={{ color: "#888" }}>Running grounded section mapping…</span>}
      </div>

      {err && <p style={{ color: "red" }}>{err}</p>}

      {status === "no_grounded_match" && (
        <div
          style={{
            background: "#fff7e6",
            border: "1px solid #ffd591",
            padding: 12,
            marginBottom: 12,
          }}
        >
          No confidently grounded section found — please review manually.
        </div>
      )}

      {!sections.length && !loading && status !== "no_grounded_match" && (
        <p style={{ color: "#888" }}>
          No sections yet. Click <b>Analyze with AI</b> to suggest legal sections from the
          case narrative.
        </p>
      )}

      {sections.map((s) => (
        <div
          key={s.id}
          style={{
            ...STATUS_STYLE[s.status],
            padding: 12,
            marginBottom: 12,
            borderRadius: 4,
          }}
        >
          <div style={{ display: "flex", justifyContent: "space-between" }}>
            <b
              style={{
                textDecoration: s.status === "REJECTED" ? "line-through" : "none",
              }}
            >
              {s.act} Section {s.section_code} — {s.section_title}
            </b>
            <span
              style={{
                fontSize: 12,
                fontWeight: 700,
                padding: "2px 8px",
                borderRadius: 10,
                background:
                  s.status === "ACCEPTED"
                    ? "#52c41a"
                    : s.status === "REJECTED"
                    ? "#bbb"
                    : "#faad14",
                color: "white",
              }}
            >
              {s.status}
            </span>
          </div>

          <p style={{ margin: "6px 0", fontSize: 13 }}>
            Confidence:{" "}
            <b>{s.confidence != null ? `${Math.round(s.confidence * 100)}%` : "—"}</b>
            {s.reason ? <> · {s.reason}</> : null}
          </p>

          <Highlighted text={narrative} phrase={s.triggering_phrase} />

          {s.status === "SUGGESTED" && (
            <div style={{ marginTop: 8, display: "flex", gap: 8 }}>
              <button onClick={() => decide(s.id, "ACCEPTED")}>Accept</button>
              <button onClick={() => decide(s.id, "REJECTED")}>Reject</button>
            </div>
          )}
        </div>
      ))}

      {rejected.length > 0 && (
        <div style={{ marginTop: 16 }}>
          <h4 style={{ margin: "0 0 6px" }}>Rejected by grounding check ({rejected.length})</h4>
          <ul style={{ fontSize: 12, color: "#a00" }}>
            {rejected.map((r, i) => (
              <li key={i}>
                {r.act} {r.section_code}: {r.rejection_reason}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

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
  const [lang, setLang] = useState("en"); // drives analyze + document generation

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
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <button onClick={() => router.push("/cases")}>← Back to cases</button>
        <div style={{ display: "flex", gap: 4, alignItems: "center" }}>
          <span style={{ fontSize: 12, color: "#666" }}>Output language:</span>
          {[
            { k: "en", label: "EN" },
            { k: "hi", label: "हिं" },
            { k: "gu", label: "ગુ" },
          ].map((o) => (
            <button
              key={o.k}
              onClick={() => setLang(o.k)}
              style={{
                fontWeight: lang === o.k ? 700 : 400,
                background: lang === o.k ? "#1677ff" : "white",
                color: lang === o.k ? "white" : "black",
                border: "1px solid #1677ff",
                padding: "2px 10px",
              }}
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>
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
        {tab === "Persons" && <PersonsTab caseId={data.id} />}
        {tab === "Seized Items" && <SeizedTab caseId={data.id} />}
        {tab === "Statements" && <StatementsTab caseId={data.id} />}
        {tab === "Documents" && <DocumentsTab caseId={data.id} lang={lang} />}
        {tab === "Diary" && <DiaryTab rows={data.diary_entries} />}
        {tab === "Evidence" && <EvidenceTab caseId={data.id} />}
        {tab === "Sections" && (
          <SectionsTab caseId={data.id} narrative={data.complaint_narrative ?? ""} lang={lang} />
        )}
      </div>
    </div>
  );
}

function Placeholder({ name }: { name: string }) {
  return <p style={{ color: "#888" }}>{name}: not implemented yet (later slice).</p>;
}

function useErr() {
  const [err, setErr] = useState<string | null>(null);
  const node = err ? (
    <div style={{ background: "#fff1f0", border: "1px solid #ffa39e", color: "#a8071a", padding: 8, margin: "8px 0" }}>
      {err}
    </div>
  ) : null;
  return { err, setErr, node };
}

const inp: CSSProperties = { padding: 4, margin: "2px 4px 2px 0", minWidth: 90 };
const PERSON_ROLES = ["VICTIM", "ACCUSED", "WITNESS", "COMPLAINANT"];
const STMT_TYPES = ["WITNESS", "ACCUSED", "VICTIM"];
const LANGS = ["GU", "HI", "EN"];
const EV_TYPES = ["IMAGE", "DOCUMENT", "PHYSICAL"];

const EMPTY_PERSON = {
  role: "WITNESS", full_name: "", alias: "", father_name: "",
  age: "", gender: "", phone: "", address: "", occupation: "",
};

function PersonsTab({ caseId }: { caseId: number }) {
  const [rows, setRows] = useState<any[]>([]);
  const [f, setF] = useState<any>({ ...EMPTY_PERSON });
  const [editId, setEditId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const { setErr, node } = useErr();

  const load = () => api.get(`/api/cases/${caseId}/persons`).then((r) => setRows(r.data));
  useEffect(() => { load(); }, [caseId]);

  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const reset = () => { setF({ ...EMPTY_PERSON }); setEditId(null); };

  async function save() {
    setBusy(true); setErr(null);
    const body: any = { ...f, age: f.age === "" ? null : Number(f.age) };
    try {
      if (editId) await api.patch(`/api/cases/${caseId}/persons/${editId}`, body);
      else await api.post(`/api/cases/${caseId}/persons`, body);
      reset(); await load();
    } catch (e: any) { setErr(e?.response?.data?.detail ?? "Save failed"); }
    finally { setBusy(false); }
  }
  async function del(id: number) {
    setErr(null);
    try { await api.delete(`/api/cases/${caseId}/persons/${id}`); await load(); }
    catch (e: any) { setErr(e?.response?.data?.detail ?? "Delete failed"); }
  }
  function edit(p: any) {
    setEditId(p.id);
    setF({ role: p.role, full_name: p.full_name ?? "", alias: p.alias ?? "", father_name: p.father_name ?? "",
      age: p.age ?? "", gender: p.gender ?? "", phone: p.phone ?? "", address: p.address ?? "", occupation: p.occupation ?? "" });
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <b>{editId ? "Edit person" : "Add person"}</b><br />
        <select style={inp} value={f.role} onChange={(e) => set("role", e.target.value)}>
          {PERSON_ROLES.map((r) => <option key={r}>{r}</option>)}
        </select>
        <input style={inp} placeholder="Full name" value={f.full_name} onChange={(e) => set("full_name", e.target.value)} />
        <input style={inp} placeholder="Alias" value={f.alias} onChange={(e) => set("alias", e.target.value)} />
        <input style={inp} placeholder="Father's name" value={f.father_name} onChange={(e) => set("father_name", e.target.value)} />
        <input style={{ ...inp, minWidth: 50 }} placeholder="Age" value={f.age} onChange={(e) => set("age", e.target.value)} />
        <input style={{ ...inp, minWidth: 50 }} placeholder="Gender" value={f.gender} onChange={(e) => set("gender", e.target.value)} />
        <input style={inp} placeholder="Phone" value={f.phone} onChange={(e) => set("phone", e.target.value)} />
        <input style={inp} placeholder="Occupation" value={f.occupation} onChange={(e) => set("occupation", e.target.value)} />
        <input style={{ ...inp, minWidth: 160 }} placeholder="Address" value={f.address} onChange={(e) => set("address", e.target.value)} />
        <button onClick={save} disabled={busy}>{editId ? "Update" : "Add person"}</button>
        {editId && <button onClick={reset}>Cancel</button>}
      </div>
      {node}
      {!rows.length ? <p>No persons.</p> : (
        <table>
          <thead><tr><th>Role</th><th>Name</th><th>Alias</th><th>Age</th><th>Gender</th><th>Phone</th><th>Occupation</th><th></th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td>{p.role}</td><td>{p.full_name}</td><td>{p.alias}</td><td>{p.age}</td>
                <td>{p.gender}</td><td>{p.phone}</td><td>{p.occupation}</td>
                <td><button onClick={() => edit(p)}>Edit</button> <button onClick={() => del(p.id)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const EMPTY_ITEM = { description: "", quantity: "", estimated_value: "", seizure_location: "", seizure_datetime: "" };

function SeizedTab({ caseId }: { caseId: number }) {
  const [rows, setRows] = useState<any[]>([]);
  const [f, setF] = useState<any>({ ...EMPTY_ITEM });
  const [editId, setEditId] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const { setErr, node } = useErr();

  const load = () => api.get(`/api/cases/${caseId}/seized-items`).then((r) => setRows(r.data));
  useEffect(() => { load(); }, [caseId]);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));
  const reset = () => { setF({ ...EMPTY_ITEM }); setEditId(null); };

  async function save() {
    setBusy(true); setErr(null);
    const body: any = {
      description: f.description,
      quantity: f.quantity === "" ? null : Number(f.quantity),
      estimated_value: f.estimated_value === "" ? null : Number(f.estimated_value),
      seizure_location: f.seizure_location || null,
      seizure_datetime: f.seizure_datetime ? new Date(f.seizure_datetime).toISOString() : null,
    };
    try {
      if (editId) await api.patch(`/api/cases/${caseId}/seized-items/${editId}`, body);
      else await api.post(`/api/cases/${caseId}/seized-items`, body);
      reset(); await load();
    } catch (e: any) { setErr(e?.response?.data?.detail ?? "Save failed"); }
    finally { setBusy(false); }
  }
  async function del(id: number) {
    setErr(null);
    try { await api.delete(`/api/cases/${caseId}/seized-items/${id}`); await load(); }
    catch (e: any) { setErr(e?.response?.data?.detail ?? "Delete failed"); }
  }
  function edit(s: any) {
    setEditId(s.id);
    setF({ description: s.description ?? "", quantity: s.quantity ?? "", estimated_value: s.estimated_value ?? "",
      seizure_location: s.seizure_location ?? "", seizure_datetime: "" });
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <b>{editId ? "Edit seized item" : "Add seized item"}</b><br />
        <input style={{ ...inp, minWidth: 220 }} placeholder="Description" value={f.description} onChange={(e) => set("description", e.target.value)} />
        <input style={{ ...inp, minWidth: 50 }} placeholder="Qty" value={f.quantity} onChange={(e) => set("quantity", e.target.value)} />
        <input style={inp} placeholder="Est. value (Rs.)" value={f.estimated_value} onChange={(e) => set("estimated_value", e.target.value)} />
        <input style={inp} placeholder="Seizure location" value={f.seizure_location} onChange={(e) => set("seizure_location", e.target.value)} />
        <input style={inp} type="datetime-local" value={f.seizure_datetime} onChange={(e) => set("seizure_datetime", e.target.value)} />
        <button onClick={save} disabled={busy}>{editId ? "Update" : "Add item"}</button>
        {editId && <button onClick={reset}>Cancel</button>}
      </div>
      {node}
      {!rows.length ? <p>No seized items.</p> : (
        <table>
          <thead><tr><th>Description</th><th>Qty</th><th>Est. value</th><th>From (pid)</th><th>Location</th><th></th></tr></thead>
          <tbody>
            {rows.map((s) => (
              <tr key={s.id}>
                <td>{s.description}</td><td>{s.quantity}</td><td>{s.estimated_value}</td>
                <td>{s.seized_from}</td><td>{s.seizure_location}</td>
                <td><button onClick={() => edit(s)}>Edit</button> <button onClick={() => del(s.id)}>Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

function StatementsTab({ caseId }: { caseId: number }) {
  const [rows, setRows] = useState<any[]>([]);
  const [persons, setPersons] = useState<any[]>([]);
  const [f, setF] = useState<any>({ person_id: "", statement_type: "WITNESS", language: "EN", statement_text: "" });
  const [busy, setBusy] = useState(false);
  const { setErr, node } = useErr();

  const load = () => api.get(`/api/cases/${caseId}/statements`).then((r) => setRows(r.data));
  useEffect(() => {
    load();
    api.get(`/api/cases/${caseId}/persons`).then((r) => setPersons(r.data));
  }, [caseId]);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));

  async function add() {
    if (!f.person_id) { setErr("Select a person"); return; }
    setBusy(true); setErr(null);
    try {
      await api.post(`/api/cases/${caseId}/statements`, { ...f, person_id: Number(f.person_id) });
      setF({ person_id: "", statement_type: "WITNESS", language: "EN", statement_text: "" });
      await load();
    } catch (e: any) { setErr(e?.response?.data?.detail ?? "Save failed"); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <b>Add statement</b><br />
        <select style={inp} value={f.person_id} onChange={(e) => set("person_id", e.target.value)}>
          <option value="">— person —</option>
          {persons.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.role})</option>)}
        </select>
        <select style={inp} value={f.statement_type} onChange={(e) => set("statement_type", e.target.value)}>
          {STMT_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <select style={inp} value={f.language} onChange={(e) => set("language", e.target.value)}>
          {LANGS.map((l) => <option key={l}>{l}</option>)}
        </select>
        <br />
        <textarea style={{ ...inp, width: 480, height: 60 }} placeholder="Statement text"
          value={f.statement_text} onChange={(e) => set("statement_text", e.target.value)} />
        <br />
        <button onClick={add} disabled={busy}>Add statement</button>
      </div>
      {node}
      {!rows.length ? <p>No statements.</p> : (
        <ul>
          {rows.map((s) => (
            <li key={s.id}><b>{s.statement_type}</b> (person {s.person_id}, {s.language}): {s.statement_text}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

function EvidenceTab({ caseId }: { caseId: number }) {
  const [rows, setRows] = useState<any[]>([]);
  const [persons, setPersons] = useState<any[]>([]);
  const [file, setFile] = useState<File | null>(null);
  const [f, setF] = useState<any>({ type: "IMAGE", description: "", tags: "", linked_person_id: "" });
  const [busy, setBusy] = useState(false);
  const { setErr, node } = useErr();

  const load = () => api.get(`/api/cases/${caseId}/evidence`).then((r) => setRows(r.data));
  useEffect(() => {
    load();
    api.get(`/api/cases/${caseId}/persons`).then((r) => setPersons(r.data));
  }, [caseId]);
  const set = (k: string, v: any) => setF((p: any) => ({ ...p, [k]: v }));

  async function upload() {
    if (!file) { setErr("Choose a file first"); return; }
    setBusy(true); setErr(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("type", f.type);
    if (f.description) fd.append("description", f.description);
    if (f.tags) fd.append("tags", f.tags);
    if (f.linked_person_id) fd.append("linked_person_id", f.linked_person_id);
    try {
      await api.post(`/api/cases/${caseId}/evidence`, fd);
      setFile(null);
      setF({ type: "IMAGE", description: "", tags: "", linked_person_id: "" });
      await load();
    } catch (e: any) { setErr(e?.response?.data?.detail ?? "Upload failed"); }
    finally { setBusy(false); }
  }

  return (
    <div>
      <div style={{ marginBottom: 8 }}>
        <b>Upload evidence</b><br />
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <select style={inp} value={f.type} onChange={(e) => set("type", e.target.value)}>
          {EV_TYPES.map((t) => <option key={t}>{t}</option>)}
        </select>
        <input style={{ ...inp, minWidth: 180 }} placeholder="Description" value={f.description} onChange={(e) => set("description", e.target.value)} />
        <input style={inp} placeholder="Tags (comma-separated)" value={f.tags} onChange={(e) => set("tags", e.target.value)} />
        <select style={inp} value={f.linked_person_id} onChange={(e) => set("linked_person_id", e.target.value)}>
          <option value="">— link person —</option>
          {persons.map((p) => <option key={p.id} value={p.id}>{p.full_name} ({p.role})</option>)}
        </select>
        <button onClick={upload} disabled={busy}>{busy ? "Uploading…" : "Upload"}</button>
      </div>
      {node}
      {!rows.length ? <p>No evidence uploaded.</p> : (
        <table>
          <thead><tr><th>Type</th><th>Description</th><th>Tags</th><th>SHA-256</th><th>Collected by</th><th>Collected at</th></tr></thead>
          <tbody>
            {rows.map((ev) => (
              <tr key={ev.id}>
                <td>{ev.type}</td>
                <td>{ev.description}</td>
                <td>{Array.isArray(ev.tags) ? ev.tags.join(", ") : ""}</td>
                <td style={{ fontFamily: "monospace", fontSize: 11, wordBreak: "break-all", maxWidth: 260 }}>{ev.file_hash}</td>
                <td>{ev.collected_by}</td>
                <td>{ev.collected_at ? new Date(ev.collected_at).toLocaleString() : "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const DOC_TYPES: { key: string; label: string }[] = [
  { key: "SEIZURE_RECEIPT", label: "Seizure Receipt" },
  { key: "PANCHNAMA", label: "Panchnama" },
  { key: "REMAND", label: "Remand Request" },
  { key: "MEDICAL_LETTER", label: "Medical Letter" },
];

function DocumentsTab({ caseId, lang }: { caseId: number; lang: string }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [busy, setBusy] = useState<string | null>(null); // doc_type currently generating
  const [err, setErr] = useState<string | null>(null);

  function loadDocs() {
    api
      .get(`/api/cases/${caseId}/documents`)
      .then((r) => setDocs(r.data))
      .catch((e) => setErr(e?.response?.data?.detail ?? "Failed to load documents"));
  }

  useEffect(loadDocs, [caseId]);

  async function generate(docType: string) {
    setBusy(docType);
    setErr(null);
    try {
      await api.post(`/api/cases/${caseId}/documents/${docType}?lang=${lang}`);
      loadDocs(); // refresh after success
    } catch (e: any) {
      // 400 carries the exact missing-fields message from the backend.
      setErr(e?.response?.data?.detail ?? "Document generation failed");
    } finally {
      setBusy(null);
    }
  }

  async function download(doc: any) {
    setErr(null);
    try {
      const res = await api.get(`/api/documents/${doc.id}/download`, {
        responseType: "blob",
      });
      // Filename from Content-Disposition, else construct one.
      const cd: string = res.headers["content-disposition"] ?? "";
      const m = cd.match(/filename="?([^"]+)"?/);
      const filename = m ? m[1] : `${doc.doc_type}_${caseId}.docx`;
      const url = URL.createObjectURL(new Blob([res.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? "Download failed");
    }
  }

  return (
    <div>
      <div style={{ display: "flex", gap: 8, flexWrap: "wrap", marginBottom: 12 }}>
        {DOC_TYPES.map((dt) => (
          <button key={dt.key} onClick={() => generate(dt.key)} disabled={busy !== null}>
            {busy === dt.key ? `Generating ${dt.label}…` : `Generate ${dt.label}`}
          </button>
        ))}
      </div>

      {err && (
        <div
          style={{
            background: "#fff1f0",
            border: "1px solid #ffa39e",
            color: "#a8071a",
            padding: 10,
            marginBottom: 12,
            whiteSpace: "pre-wrap",
          }}
        >
          {err}
        </div>
      )}

      {!docs.length ? (
        <p style={{ color: "#888" }}>
          No documents yet. Use the buttons above to generate a draft.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Document</th>
              <th>Version</th>
              <th>Status</th>
              <th>Generated</th>
              <th>By (user id)</th>
              <th></th>
            </tr>
          </thead>
          <tbody>
            {docs.map((d) => (
              <tr key={d.id}>
                <td>{DOC_LABELS[d.doc_type] ?? d.doc_type}</td>
                <td>v{d.version}</td>
                <td>
                  <span
                    style={{
                      fontSize: 12,
                      fontWeight: 700,
                      padding: "1px 8px",
                      borderRadius: 10,
                      background: d.status === "FINALIZED" ? "#52c41a" : "#faad14",
                      color: "white",
                    }}
                  >
                    {d.status}
                  </span>
                </td>
                <td>{d.generated_at ? new Date(d.generated_at).toLocaleString() : "—"}</td>
                <td>{d.generated_by ?? "—"}</td>
                <td>
                  <button onClick={() => download(d)}>Download</button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}

const DOC_LABELS: Record<string, string> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.key, d.label])
);

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

function SectionsTab({ caseId, narrative, lang }: { caseId: number; narrative: string; lang: string }) {
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
      const r = await api.post(`/api/cases/${caseId}/analyze?lang=${lang}`);
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

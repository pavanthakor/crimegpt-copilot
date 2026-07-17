"use client";
import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

type CaseRow = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
  police_station: string | null;
};

export default function CasesPage() {
  const { user, ready } = useAuth();
  const router = useRouter();
  const [rows, setRows] = useState<CaseRow[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!ready) return;
    if (!user) {
      router.replace("/login");
      return;
    }
    api
      .get<CaseRow[]>("/api/cases")
      .then((r) => setRows(r.data))
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load cases"))
      .finally(() => setLoading(false));
  }, [ready, user, router]);

  if (!ready || !user) return <p>Loading…</p>;

  return (
    <div>
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Cases</h1>
        <button onClick={() => router.push("/cases/new")}>+ New case</button>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th>Case #</th>
              <th>Title</th>
              <th>Status</th>
              <th>Police station</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((c) => (
              <tr
                key={c.id}
                style={{ cursor: "pointer" }}
                onClick={() => router.push(`/cases/${c.id}`)}
              >
                <td>{c.case_number}</td>
                <td>{c.title}</td>
                <td>{c.status}</td>
                <td>{c.police_station}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={4}>No cases yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}

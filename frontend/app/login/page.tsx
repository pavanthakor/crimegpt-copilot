"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";

export default function LoginPage() {
  const [username, setUsername] = useState("io");
  const [password, setPassword] = useState("io123");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();

  async function onLogin() {
    setLoading(true);
    setError(null);
    try {
      const res = await api.post("/api/auth/login", { username, password });
      login({
        token: res.data.token,
        role: res.data.role,
        full_name: res.data.full_name,
      });
      router.push("/cases");
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={{ maxWidth: 360, margin: "40px auto" }}>
      <h1>CrimeGPT Login</h1>
      <label>Username</label>
      <input value={username} onChange={(e) => setUsername(e.target.value)} />
      <label>Password</label>
      <input
        type="password"
        value={password}
        onChange={(e) => setPassword(e.target.value)}
      />
      <div style={{ marginTop: 12 }}>
        <button onClick={onLogin} disabled={loading}>
          {loading ? "…" : "Log in"}
        </button>
      </div>
      {error && <p style={{ color: "red" }}>{error}</p>}
      <p style={{ fontSize: 12, color: "#666" }}>
        Demo: io/io123 · sho/sho123 · legal/legal123
      </p>
    </div>
  );
}

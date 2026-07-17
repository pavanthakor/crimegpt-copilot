"use client";
import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "./AuthProvider";

export default function Nav() {
  const { user, logout } = useAuth();
  const router = useRouter();

  if (!user) return null;

  return (
    <nav
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        padding: "8px 16px",
        background: "#1f2937",
        color: "white",
      }}
    >
      <Link href="/cases" style={{ color: "white", fontWeight: 700, textDecoration: "none" }}>
        CrimeGPT
      </Link>
      <div style={{ display: "flex", gap: 12, alignItems: "center" }}>
        <span style={{ fontSize: 14 }}>
          {user.full_name} · {user.role}
        </span>
        <button
          onClick={() => {
            logout();
            router.replace("/login");
          }}
        >
          Logout
        </button>
      </div>
    </nav>
  );
}

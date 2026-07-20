"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "./AuthProvider";

type Lang = "EN" | "HI" | "GU";

// Label carries the native script so the selector itself exercises the Indic fonts.
const LANGS: { code: Lang; label: string }[] = [
  { code: "EN", label: "EN" },
  { code: "HI", label: "हिं" },
  { code: "GU", label: "ગુ" },
];

const ROLE_LABEL: Record<string, string> = {
  IO: "Investigating Officer",
  SHO: "Station House Officer",
  LEGAL_ADVISOR: "Legal Advisor",
};

export default function TopBar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  // State only for now — switching behaviour comes in a later slice.
  const [lang, setLang] = useState<Lang>("EN");

  const roleTitle = user ? ROLE_LABEL[user.role] ?? user.role : "";

  return (
    <header className="fixed top-0 right-0 left-0 ml-[280px] h-16 bg-surface-bright border-b border-outline-variant flex items-center justify-between px-edge-margin z-40">
      {/* Search */}
      <div className="flex items-center gap-8 w-full max-w-2xl">
        <div className="relative flex-grow">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-on-surface-variant text-xl">
            search
          </span>
          <input
            type="text"
            placeholder="Search cases, evidence, or persons…"
            className="w-full bg-surface-container-low border-none rounded focus:ring-1 focus:ring-primary pl-12 pr-4 py-2 font-body-md text-on-surface placeholder:text-outline"
          />
        </div>
      </div>

      <div className="flex items-center gap-5">
        {/* Language selector: EN | हिं | ગુ */}
        <div
          className="flex items-center rounded border border-outline-variant overflow-hidden"
          role="group"
          aria-label="Language"
        >
          {LANGS.map((l) => {
            const on = lang === l.code;
            return (
              <button
                key={l.code}
                type="button"
                onClick={() => setLang(l.code)}
                aria-pressed={on}
                className={
                  (on
                    ? "bg-primary text-on-primary "
                    : "bg-transparent text-on-surface-variant hover:bg-surface-container ") +
                  "px-3 py-1.5 font-body-md leading-none transition-colors"
                }
              >
                {l.label}
              </button>
            );
          })}
        </div>

        {/* Officer name + role badge */}
        {user && (
          <div className="flex items-center gap-3 pl-2 border-l border-outline-variant">
            <div className="flex flex-col items-end">
              <p className="font-body-md text-on-surface leading-none">{user.full_name}</p>
              <span className="mt-1 font-label-caps text-[10px] text-secondary bg-secondary-container px-1.5 py-0.5 rounded">
                {roleTitle}
              </span>
            </div>
            <div className="h-9 w-9 bg-surface-container-highest border border-outline-variant flex items-center justify-center rounded">
              <span className="material-symbols-outlined text-primary">account_circle</span>
            </div>
          </div>
        )}

        {/* Sign out */}
        <button
          type="button"
          onClick={() => {
            logout();
            router.replace("/login");
          }}
          className="flex items-center gap-1 text-on-surface-variant hover:text-error transition-colors"
          title="Sign out"
        >
          <span className="material-symbols-outlined">logout</span>
          <span className="font-body-md">Sign out</span>
        </button>
      </div>
    </header>
  );
}

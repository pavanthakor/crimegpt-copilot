"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";
import { motion, useReducedMotion } from "framer-motion";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/lib/i18n";

// Each centred-column element fades up 14px, staggered ~80ms.
const STAGGER = { hidden: {}, show: { transition: { staggerChildren: 0.08 } } };
const FADE_UP = {
  hidden: { opacity: 0, y: 14 },
  show: { opacity: 1, y: 0, transition: { duration: 0.5, ease: "easeOut" } },
};

// Decorative gradients use the accent (#8a7c3f = 138,124,63) and outline
// (#76777d = 118,119,125) tokens as rgba — no new palette colours are introduced.
const GLOW =
  "radial-gradient(circle at 50% 20%, rgba(138,124,63,0.14), transparent 58%)";
const GRID =
  "linear-gradient(to right, rgba(118,119,125,0.03) 1px, transparent 1px)," +
  "linear-gradient(to bottom, rgba(118,119,125,0.03) 1px, transparent 1px)";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();
  const { t } = useI18n();
  const reduce = useReducedMotion();

  async function onSignIn() {
    if (loading) return;
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
      // 401 → wrong credentials; anything else → a generic reachability message.
      const status = e?.response?.status;
      setError(status === 401 ? t("login.error") : t("common.serverUnreachable"));
      setLoading(false);
    }
  }

  function onKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") onSignIn();
  }

  return (
    <main className="relative min-h-screen overflow-hidden bg-on-surface flex items-center justify-center px-4">
      {/* ---- background, back to front ---- */}
      {/* 3. 40px grid at ~3% */}
      <div
        className="absolute inset-0"
        style={{ backgroundImage: GRID, backgroundSize: "40px 40px" }}
        aria-hidden
      />
      {/* 1. radial glow behind the emblem */}
      <div className="absolute inset-0" style={{ background: GLOW }} aria-hidden />
      {/* 2. drifting node clusters near each edge */}
      <NodeCluster side="left" reduce={!!reduce} />
      <NodeCluster side="right" reduce={!!reduce} />

      {/* ---- centred column ---- */}
      <motion.div
        variants={STAGGER}
        initial={reduce ? "show" : "hidden"}
        animate="show"
        className="relative z-10 w-[330px] max-w-full flex flex-col items-center text-center"
      >
        {/* Emblem */}
        <motion.div variants={FADE_UP}>
          <Emblem reduce={!!reduce} />
        </motion.div>

        {/* Wordmark */}
        <motion.h1
          variants={FADE_UP}
          className="mt-5 font-serif text-[31px] font-bold leading-none text-surface"
        >
          CrimeGPT
        </motion.h1>

        {/* Accent divider */}
        <motion.div variants={FADE_UP} className="mt-4 w-[34px] h-[1.5px] bg-accent" />

        {/* Force name */}
        <motion.p
          variants={FADE_UP}
          className="mt-4 font-mono text-[10.5px] tracking-[0.2em] uppercase text-outline"
        >
          {t("org.force")}
        </motion.p>

        {/* Username */}
        <motion.div variants={FADE_UP} className="mt-8 w-full">
          <Field
            id="username"
            icon="person"
            type="text"
            autoComplete="username"
            label={t("login.username")}
            value={username}
            onChange={setUsername}
            onKeyDown={onKeyDown}
          />
        </motion.div>

        {/* Password */}
        <motion.div variants={FADE_UP} className="mt-3 w-full">
          <Field
            id="password"
            icon="lock"
            type="password"
            autoComplete="current-password"
            label={t("login.password")}
            value={password}
            onChange={setPassword}
            onKeyDown={onKeyDown}
          />
        </motion.div>

        {/* Error — appears on demand (not part of the load stagger). */}
        {error && (
          <p
            role="alert"
            className="mt-3 w-full flex items-center justify-center gap-2 font-body-md text-error"
          >
            <span className="material-symbols-outlined text-base">error</span>
            {error}
          </p>
        )}

        {/* Sign in */}
        <motion.button
          variants={FADE_UP}
          type="button"
          onClick={onSignIn}
          disabled={loading}
          className="mt-4 w-full h-[46px] bg-accent text-on-surface rounded font-body-md font-semibold hover:bg-accent-strong disabled:opacity-60 flex items-center justify-center gap-2 transition-colors"
        >
          {loading ? (
            <>
              <span className="material-symbols-outlined animate-spin text-xl">
                progress_activity
              </span>
              {t("login.signingIn")}
            </>
          ) : (
            t("login.signIn")
          )}
        </motion.button>

        {/* Footer */}
        <motion.p
          variants={FADE_UP}
          className="mt-8 font-mono text-[10px] tracking-[0.15em] uppercase text-outline"
        >
          {t("org.branch")} · On-Premise
        </motion.p>
      </motion.div>
    </main>
  );
}

/* ---------------- Emblem: breathing ring + rotating dashed ring + shield-lock ---------------- */

function Emblem({ reduce }: { reduce: boolean }) {
  const centered = { transformBox: "fill-box", transformOrigin: "center" } as const;
  return (
    <div className="relative w-[74px] h-[74px]">
      <svg viewBox="0 0 74 74" className="absolute inset-0 w-full h-full" aria-hidden>
        {/* outer ring (r34) — breathes */}
        <motion.circle
          cx="37"
          cy="37"
          r="34"
          fill="none"
          className="stroke-accent"
          strokeWidth="1"
          style={centered}
          initial={false}
          animate={reduce ? { opacity: 0.3 } : { scale: [1, 1.13], opacity: [0.45, 0.12] }}
          transition={
            reduce
              ? undefined
              : { duration: 3.6, repeat: Infinity, repeatType: "reverse", ease: "easeInOut" }
          }
        />
        {/* dashed ring (r27) — rotates */}
        <motion.circle
          cx="37"
          cy="37"
          r="27"
          fill="none"
          className="stroke-accent"
          strokeWidth="1"
          strokeDasharray="13 9"
          opacity="0.7"
          style={centered}
          animate={reduce ? undefined : { rotate: 360 }}
          transition={reduce ? undefined : { duration: 26, repeat: Infinity, ease: "linear" }}
        />
        {/* solid inverse-surface disc (r20) */}
        <circle cx="37" cy="37" r="20" className="fill-inverse-surface" />
      </svg>
      {/* shield-lock, in accent, on top */}
      <svg
        viewBox="0 0 24 24"
        className="absolute inset-0 m-auto w-[28px] h-[28px] text-accent"
        aria-hidden
      >
        <path
          fill="currentColor"
          opacity="0.18"
          d="M12 2 19 4.6 V11 C19 15.3 16 19 12 20.3 C8 19 5 15.3 5 11 V4.6 Z"
        />
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
          strokeLinejoin="round"
          d="M12 2 19 4.6 V11 C19 15.3 16 19 12 20.3 C8 19 5 15.3 5 11 V4.6 Z"
        />
        <rect x="9.2" y="11" width="5.6" height="4.8" rx="1" fill="currentColor" />
        <path
          fill="none"
          stroke="currentColor"
          strokeWidth="1.3"
          d="M10.2 11 V9.6 a1.8 1.8 0 0 1 3.6 0 V11"
        />
      </svg>
    </div>
  );
}

/* ---------------- Drifting node cluster ---------------- */

function NodeCluster({ side, reduce }: { side: "left" | "right"; reduce: boolean }) {
  // Opposite keyframes give the two clusters independent (out-of-phase) drift over the
  // same 18s loop — equivalent to the -9s offset of a symmetric cycle.
  const drift =
    side === "left" ? { x: [0, 12, 0], y: [0, -16, 0] } : { x: [0, -12, 0], y: [0, 16, 0] };
  const colour = side === "left" ? "stroke-accent fill-accent" : "stroke-outline fill-outline";
  return (
    <svg
      viewBox="0 0 150 220"
      aria-hidden
      className={
        "absolute top-1/2 -translate-y-1/2 w-[150px] h-[220px] pointer-events-none opacity-25 " +
        (side === "left" ? "left-2 sm:left-12" : "right-2 sm:right-12")
      }
    >
      <motion.g
        className={colour}
        strokeWidth="1"
        animate={reduce ? undefined : drift}
        transition={reduce ? undefined : { duration: 18, repeat: Infinity, ease: "easeInOut" }}
      >
        {/* edges */}
        <line x1="30" y1="40" x2="95" y2="70" />
        <line x1="95" y1="70" x2="55" y2="120" />
        <line x1="55" y1="120" x2="110" y2="160" />
        <line x1="30" y1="40" x2="55" y2="120" />
        <line x1="95" y1="70" x2="120" y2="30" />
        <line x1="55" y1="120" x2="20" y2="175" />
        {/* nodes */}
        <circle cx="30" cy="40" r="3.5" />
        <circle cx="95" cy="70" r="2.5" />
        <circle cx="120" cy="30" r="2" />
        <circle cx="55" cy="120" r="3" />
        <circle cx="110" cy="160" r="2.5" />
        <circle cx="20" cy="175" r="2" />
      </motion.g>
    </svg>
  );
}

/* ---------------- Input field with a leading icon + visually-hidden label ---------------- */

function Field({
  id,
  icon,
  type,
  autoComplete,
  label,
  value,
  onChange,
  onKeyDown,
}: {
  id: string;
  icon: string;
  type: string;
  autoComplete: string;
  label: string;
  value: string;
  onChange: (v: string) => void;
  onKeyDown: (e: React.KeyboardEvent) => void;
}) {
  return (
    <div className="relative w-full">
      <span className="material-symbols-outlined absolute left-[15px] top-1/2 -translate-y-1/2 text-on-surface-variant text-xl pointer-events-none">
        {icon}
      </span>
      <label htmlFor={id} className="sr-only">
        {label}
      </label>
      <input
        id={id}
        type={type}
        autoComplete={autoComplete}
        placeholder={label}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={onKeyDown}
        className="w-full h-11 bg-surface border border-outline-variant rounded pl-[44px] pr-4 font-body-md text-on-surface placeholder:text-on-surface-variant focus:outline-none focus:border-accent transition-colors"
      />
    </div>
  );
}

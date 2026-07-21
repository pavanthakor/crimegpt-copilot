"use client";
import { useState } from "react";
import { useRouter } from "next/navigation";

import { api } from "@/lib/api";
import { useAuth } from "@/components/AuthProvider";
import { useI18n } from "@/lib/i18n";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  const { login } = useAuth();
  const { t } = useI18n();

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
    <main className="min-h-screen flex bg-surface-container">
      {/* Left: branding panel */}
      <div className="hidden lg:flex lg:w-1/2 bg-primary text-surface-bright flex-col justify-between p-12">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-surface-bright/10 border border-surface-bright/20 flex items-center justify-center">
            <span className="material-symbols-outlined filled text-surface-bright">security</span>
          </div>
          <span className="font-label-caps text-[10px] tracking-[0.3em] text-surface-bright/70">
            {t("org.force")}
          </span>
        </div>

        <div>
          <h1 className="font-display-case text-surface-bright mb-4">CrimeGPT</h1>
          <p className="font-headline-md font-normal text-surface-bright/80 max-w-sm">
            {t("login.tagline")}
          </p>
        </div>

        <p className="font-mono-sm text-surface-bright/50">{t("org.branch")}</p>
      </div>

      {/* Right: sign-in form */}
      <div className="w-full lg:w-1/2 flex items-center justify-center p-8">
        <div className="w-full max-w-sm">
          <div className="mb-8">
            <h2 className="font-headline-lg text-primary mb-1">{t("login.signIn")}</h2>
            <p className="font-body-md text-on-surface-variant">
              {t("login.subtitle")}
            </p>
          </div>

          <div className="space-y-5">
            <div className="space-y-2">
              <label htmlFor="username" className="font-label-caps text-on-surface-variant block">
                {t("login.username")}
              </label>
              <input
                id="username"
                type="text"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={onKeyDown}
                className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors"
              />
            </div>

            <div className="space-y-2">
              <label htmlFor="password" className="font-label-caps text-on-surface-variant block">
                {t("login.password")}
              </label>
              <input
                id="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={onKeyDown}
                className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors"
              />
            </div>

            {error && (
              <p role="alert" className="font-body-md text-error flex items-center gap-2">
                <span className="material-symbols-outlined text-base">error</span>
                {error}
              </p>
            )}

            <button
              type="button"
              onClick={onSignIn}
              disabled={loading}
              className="w-full bg-primary text-surface-bright py-3 rounded font-body-lg font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
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
            </button>
          </div>
        </div>
      </div>
    </main>
  );
}

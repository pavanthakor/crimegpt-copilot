"use client";
import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";

import { api } from "@/lib/api";
import { useI18n, type TKey } from "@/lib/i18n";

// A minimal case row — enough to label the picker options. /audit and /analysis
// both operate on a single chosen case, so they share this loader + dropdown.
export type CaseLite = {
  id: number;
  case_number: string;
  title: string | null;
  status: string;
};

// Fetch the role-visible case list once. Returns the selected id (kept in the
// URL as ?case= so a reload / a shared link keeps position) plus a setter.
export function useCasePicker() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [cases, setCases] = useState<CaseLite[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const urlCase = searchParams.get("case");
  const [selected, setSelectedState] = useState<number | null>(
    urlCase ? Number(urlCase) : null
  );

  useEffect(() => {
    api
      .get<CaseLite[]>("/api/cases")
      .then((r) => {
        setCases(r.data);
        // Default to the case named in the URL if it exists, else the first case.
        setSelectedState((prev) => {
          if (prev != null && r.data.some((c) => c.id === prev)) return prev;
          return r.data[0]?.id ?? null;
        });
      })
      .catch((e) => setError(e?.response?.data?.detail ?? "Could not load cases."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function setSelected(id: number) {
    setSelectedState(id);
    const p = new URLSearchParams(searchParams.toString());
    p.set("case", String(id));
    router.replace(`?${p.toString()}`, { scroll: false });
  }

  return { cases, loading, error, selected, setSelected };
}

export function CaseSelect({
  cases,
  value,
  onChange,
  disabled,
}: {
  cases: CaseLite[];
  value: number | null;
  onChange: (id: number) => void;
  disabled?: boolean;
}) {
  const { t } = useI18n();
  return (
    <div className="flex items-center gap-3">
      <label htmlFor="case-select" className="font-label-caps text-on-surface-variant">
        {t("audit.case")}
      </label>
      <select
        id="case-select"
        value={value ?? ""}
        disabled={disabled}
        onChange={(e) => onChange(Number(e.target.value))}
        className="min-w-[320px] bg-surface-container-low border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary disabled:opacity-60"
      >
        {cases.map((c) => (
          <option key={c.id} value={c.id}>
            {c.case_number} — {c.title ?? t("common.untitled")} · {t(`status.${c.status}` as TKey)}
          </option>
        ))}
      </select>
    </div>
  );
}

// Shared helpers for the cases UI: status presentation and date formatting.

export type CaseStatus =
  | "COMPLAINT"
  | "INVESTIGATION"
  | "ARREST"
  | "REMAND"
  | "CHARGESHEET";

// Status is shown as a coloured DOT plus the WORD — never colour alone (the word is
// authoritative, so colour-blind users and greyscale prints both read correctly).
// Dot colours use design tokens (bg-* classes), no hardcoded hex.
export const STATUS_META: Record<string, { label: string; dot: string }> = {
  COMPLAINT: { label: "Complaint", dot: "bg-outline" },
  INVESTIGATION: { label: "Investigation", dot: "bg-primary" },
  ARREST: { label: "Arrest", dot: "bg-error" },
  REMAND: { label: "Remand", dot: "bg-secondary" },
  CHARGESHEET: { label: "Chargesheet", dot: "bg-on-secondary-container" },
};

export function statusMeta(status: string): { label: string; dot: string } {
  return STATUS_META[status] ?? { label: status, dot: "bg-outline" };
}

export const CASE_STATUSES: CaseStatus[] = [
  "COMPLAINT",
  "INVESTIGATION",
  "ARREST",
  "REMAND",
  "CHARGESHEET",
];

// "24 Jan 2026 · 10:45" — matches the reference's Last Modified column.
export function formatUpdated(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const date = d.toLocaleDateString("en-GB", {
    day: "2-digit",
    month: "short",
    year: "numeric",
  });
  const time = d.toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
  return `${date} · ${time}`;
}

// A description string, or a clear placeholder when it is missing, blank, or just a
// bare dash placeholder ("—" / "-" / "–"). `??` alone leaks empty strings and stored
// em-dash placeholders through as a meaningless cell; officers read "(no description)"
// as "nothing recorded", not as a rendering glitch.
export function descOr(desc: string | null | undefined): string {
  const trimmed = (desc ?? "").replace(/[\s—–-]+/g, "");
  return trimmed ? (desc as string) : "(no description)";
}

// A section's `reason` adds nothing when it merely restates the heading title (the
// AI often returns the short statutory title as the "reason", so a full title in the
// heading + short title as the reason reads as a duplicated title). Compare case- and
// punctuation-insensitively (Latin, Devanagari, Gujarati): redundant if the title
// starts with, ends with, contains, or equals the reason.
export function reasonRestatesTitle(
  reason: string | null | undefined,
  title: string | null | undefined
): boolean {
  if (!reason || !title) return false;
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9ऀ-ॿ઀-૿]+/g, " ").trim();
  const r = norm(reason);
  const t = norm(title);
  if (!r || !t) return false;
  return t === r || t.startsWith(r) || t.endsWith(r) || t.includes(` ${r} `);
}

// Person roles, in the display order the Case-details panel groups them.
export const PERSON_ROLES = ["COMPLAINANT", "ACCUSED", "WITNESS", "VICTIM"] as const;
export type PersonRole = (typeof PERSON_ROLES)[number];

export const PERSON_ROLE_LABEL: Record<string, { singular: string; plural: string }> = {
  COMPLAINANT: { singular: "Complainant", plural: "Complainants" },
  ACCUSED: { singular: "Accused", plural: "Accused" },
  WITNESS: { singular: "Witness", plural: "Witnesses" },
  VICTIM: { singular: "Victim", plural: "Victims" },
};

export const STATEMENT_TYPES = ["WITNESS", "ACCUSED", "VICTIM"] as const;
export const COMPLAINT_LANGS = ["EN", "HI", "GU"] as const;

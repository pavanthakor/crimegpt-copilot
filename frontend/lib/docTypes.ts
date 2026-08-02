/**
 * Shared document-type helpers.
 *
 * The Documents tab and the case assistant both need the same three things: the list of
 * generatable documents, a way to read the missing-field list out of a failed generation,
 * and a translation key per field. They were private to DocumentsTab; the assistant needs
 * them too, and a second copy would be a second thing to keep in step.
 */
import type { TKey } from "@/lib/i18n";

/** The generatable documents, matching templates/_registry.py. Display names come from
 *  i18n (`docs.type.<KEY>`) — `icon` is the only presentation detail that lives here. */
export const DOC_TYPES: { key: string; note?: string; icon: string; glossary?: string }[] = [
  { key: "SEIZURE_RECEIPT", note: "Form IF4", icon: "receipt_long", glossary: "IF4" },
  { key: "PANCHNAMA", icon: "history_edu" },
  { key: "REMAND", icon: "gavel" },
  { key: "CUSTODY_LETTER", icon: "account_balance" },
  { key: "CHARGESHEET", note: "BNSS §193 Form I", icon: "description" },
  { key: "MEDICAL_LETTER", icon: "medical_services" },
  { key: "LERS_PRESERVATION_REQUEST", icon: "lock_clock", glossary: "LERS" },
  { key: "LERS_RECORDS_REQUEST", icon: "folder_data" },
];

export const DOC_ICON: Record<string, string> = Object.fromEntries(
  DOC_TYPES.map((d) => [d.key, d.icon])
);

/**
 * Recover the missing-field list from a generation failure.
 *
 * The backend raises `ValueError("Cannot generate X: missing required field(s): a, b")`,
 * which becomes a 400 body — so the only way to learn what a document needs is to attempt
 * it and read the prose back apart. That is a brittle contract and it is deliberately in
 * ONE place now, rather than duplicated per caller, so replacing it later (with a
 * readiness endpoint that returns the codes directly) is a single edit.
 */
export function parseMissing(detail: string | undefined): string[] | null {
  if (!detail) return null;
  const m = detail.match(/missing required field\(s\):\s*(.+)$/i);
  if (!m) return null;
  return m[1]
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** i18n key for a raw pool field code. */
export function fieldLabelKey(raw: string): TKey {
  return `docs.field.${raw.trim()}` as TKey;
}

/**
 * Officer-facing name for a raw pool field code, in the current language.
 *
 * `t()` returns the key itself when a string is missing rather than rendering blank, so
 * an unrecognised field code would otherwise surface as "docs.field.foo". Detect that and
 * fall back to the de-underscored code — ugly but readable, and it means a new required
 * field added to the registry degrades to "brief facts" rather than to a lookup key.
 */
export function fieldLabel(raw: string, t: (k: TKey) => string): string {
  const key = fieldLabelKey(raw);
  const label = t(key);
  return label === key ? raw.trim().replace(/_/g, " ") : label;
}

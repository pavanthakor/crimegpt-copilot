"use client";
import { useI18n } from "@/lib/i18n";

// Renders a labelled key/value list, skipping empty values. An officer reads
// "District: Ahmedabad", never raw JSON.
function PayloadRows({ items }: { items: Array<[string, unknown]> }) {
  const shown = items.filter(([, v]) => v != null && String(v).trim() !== "");
  if (shown.length === 0) return null;
  return (
    <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1.5">
      {shown.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="font-label-caps text-[10px] text-on-surface-variant self-center">
            {label}
          </dt>
          <dd className="font-body-md text-on-surface break-words">{String(value)}</dd>
        </div>
      ))}
    </dl>
  );
}

// Human-readable view of the CCTNS IIF payload (IIF-1 case header + IIF-4 seizure
// block), replacing the raw JSON dump. Reuses existing field tokens where they exist.
// Shared by the CCTNS export panel and the audit trail.
export function PayloadSummary({ payload }: { payload: Record<string, unknown> }) {
  const { t } = useI18n();
  const h = (payload["IIF-1"] ?? {}) as Record<string, any>;
  const s = (payload["IIF-4"] ?? {}) as Record<string, any>;
  const occurrence = (h.occurrence ?? {}) as Record<string, any>;

  const acts: any[] = Array.isArray(h.acts_sections) ? h.acts_sections : [];
  const actsText = acts.length ? acts.map((a) => `${a.act} ${a.section}`).join(", ") : null;
  const accused: any[] = Array.isArray(h.accused) ? h.accused : [];
  const accusedText = accused.map((a) => a?.name).filter(Boolean).join(", ") || null;
  const props: any[] = Array.isArray(s.properties) ? s.properties : [];
  const propsText = props.map((p) => p?.description).filter(Boolean).join(", ") || null;
  const witnesses: any[] = Array.isArray(s.witnesses) ? s.witnesses : [];
  const witnessText = witnesses.map((w) => w?.name).filter(Boolean).join(", ") || null;

  const headerRows: Array<[string, unknown]> = [
    [t("newCase.field.district"), h.district],
    [t("newCase.field.policeStation"), h.police_station],
    [t("newCase.field.caseNumber"), h.crime_no],
    [t("newCase.field.firNumber"), h.fir_no],
    [t("newCase.field.firDate"), h.fir_date],
    [t("newCase.field.incidentLocation"), occurrence.location],
    [t("cctns.summary.acts"), actsText],
    [t("person.COMPLAINANT.one"), h.complainant?.name],
    [t("person.ACCUSED.one"), accusedText],
  ];
  const seizureRows: Array<[string, unknown]> = [
    [t("evidence.field.seizureDatetime"), s.seizure_datetime],
    [t("evidence.field.seizurePlace"), s.seizure_location],
    [t("evidence.seized.title"), propsText],
    [t("workspace.stat.witnesses"), witnessText],
  ];

  return (
    <div className="mt-3 rounded border border-outline-variant bg-surface-container-low p-4 space-y-4">
      <div>
        <h3 className="font-label-caps text-[10px] text-primary mb-2">
          {t("cctns.summary.header")}
        </h3>
        <PayloadRows items={headerRows} />
      </div>
      <div>
        <h3 className="font-label-caps text-[10px] text-primary mb-2">
          {t("cctns.summary.seizure")}
        </h3>
        <PayloadRows items={seizureRows} />
      </div>
    </div>
  );
}

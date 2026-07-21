"use client";
import { useCallback, useEffect, useMemo, useState } from "react";

import { api } from "@/lib/api";
import { formatUpdated, isBlankDesc } from "@/lib/cases";
import { useI18n } from "@/lib/i18n";

type Person = { id: number; role: string; full_name: string | null };
type SeizedItem = {
  id: number;
  description: string | null;
  quantity: number | null;
  estimated_value: number | null;
  seized_from: number | null;
  seizure_datetime: string | null;
  seizure_location: string | null;
};
type Evidence = {
  id: number;
  type: string;
  file_hash: string | null;
  description: string | null;
  tags: string[] | null;
  linked_person_id: number | null;
  collected_by_name: string | null;
  collected_at: string | null;
};

const EVIDENCE_TYPES = ["IMAGE", "DOCUMENT", "PHYSICAL"] as const;

export default function EvidenceTab({
  caseId,
  onPoolChanged,
}: {
  caseId: number;
  onPoolChanged: () => void;
}) {
  const [items, setItems] = useState<SeizedItem[]>([]);
  const [evidence, setEvidence] = useState<Evidence[]>([]);
  const [persons, setPersons] = useState<Person[]>([]);
  const [loaded, setLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const { t } = useI18n();

  const load = useCallback(() => {
    Promise.all([
      api.get<SeizedItem[]>(`/api/cases/${caseId}/seized-items`),
      api.get<Evidence[]>(`/api/cases/${caseId}/evidence`),
      api.get<Person[]>(`/api/cases/${caseId}/persons`),
    ])
      .then(([s, e, p]) => {
        setItems(s.data);
        setEvidence(e.data);
        setPersons(p.data);
      })
      .catch((err) => setError(err?.response?.data?.detail ?? t("evidence.loadError")))
      .finally(() => setLoaded(true));
  }, [caseId, t]);

  useEffect(load, [load]);

  const personName = useMemo(() => {
    const m = new Map<number, string>();
    persons.forEach((p) => m.set(p.id, p.full_name ?? `Person ${p.id}`));
    return m;
  }, [persons]);

  function afterChange() {
    load();
    onPoolChanged();
  }

  if (!loaded) return <EvidenceSkeleton />;

  return (
    <div className="space-y-10">
      {error && (
        <p role="alert" className="flex items-center gap-2 font-body-md text-error">
          <span className="material-symbols-outlined text-base">error</span>
          {error}
        </p>
      )}

      <SeizedItemsBlock
        caseId={caseId}
        items={items}
        personName={personName}
        onChanged={afterChange}
      />

      <EvidenceFilesBlock
        caseId={caseId}
        evidence={evidence}
        persons={persons}
        personName={personName}
        onChanged={afterChange}
      />
    </div>
  );
}

/* ---------------- Seized items ---------------- */

type ItemForm = {
  description: string;
  quantity: string;
  estimated_value: string;
  seized_from: string;
  seizure_datetime: string;
  seizure_location: string;
};
const EMPTY_ITEM: ItemForm = {
  description: "",
  quantity: "",
  estimated_value: "",
  seized_from: "",
  seizure_datetime: "",
  seizure_location: "",
};

function SeizedItemsBlock({
  caseId,
  items,
  personName,
  onChanged,
}: {
  caseId: number;
  items: SeizedItem[];
  personName: Map<number, string>;
  onChanged: () => void;
}) {
  const [editing, setEditing] = useState<SeizedItem | "new" | null>(null);
  const { t } = useI18n();

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-headline-md text-primary">{t("evidence.seized.title")}</h2>
          <p className="font-body-md text-on-surface-variant">
            {t("evidence.seized.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setEditing("new")}
          className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
        >
          <span className="material-symbols-outlined text-lg">add</span>
          {t("evidence.seized.add")}
        </button>
      </div>

      {editing && (
        <SeizedItemForm
          caseId={caseId}
          item={editing === "new" ? null : editing}
          onDone={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            onChanged();
          }}
        />
      )}

      {items.length === 0 && !editing ? (
        <EmptyBlock icon="inventory_2" title={t("evidence.seized.empty.title")} hint={t("evidence.seized.empty.hint")} />
      ) : (
        <div className="border border-outline-variant rounded overflow-x-auto bg-surface-container-lowest">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-outline text-on-surface-variant bg-surface-container-low">
                <th className="px-4 py-3 font-label-caps">{t("evidence.col.description")}</th>
                <th className="px-4 py-3 font-label-caps w-[70px]">{t("evidence.col.qty")}</th>
                <th className="px-4 py-3 font-label-caps w-[130px]">{t("evidence.col.value")}</th>
                <th className="px-4 py-3 font-label-caps w-[150px]">{t("evidence.col.seizedFrom")}</th>
                <th className="px-4 py-3 font-label-caps w-[200px]">{t("evidence.col.seizureDate")}</th>
                <th className="px-4 py-3 font-label-caps w-[90px] text-right">{t("evidence.col.actions")}</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-outline-variant">
              {items.map((it) => (
                <tr key={it.id} className="align-top">
                  <td className="px-4 py-4 font-body-md text-on-surface">{it.description ?? "—"}</td>
                  <td className="px-4 py-4 font-mono-data text-on-surface-variant">{it.quantity ?? "—"}</td>
                  <td className="px-4 py-4 font-mono-data text-on-surface-variant">
                    {it.estimated_value != null ? `₹ ${it.estimated_value.toLocaleString("en-IN")}` : "—"}
                  </td>
                  <td className="px-4 py-4 font-body-md text-on-surface-variant">
                    {it.seized_from != null ? personName.get(it.seized_from) ?? `#${it.seized_from}` : "—"}
                  </td>
                  <td className="px-4 py-4">
                    <p className="font-mono-sm text-on-surface-variant">{formatUpdated(it.seizure_datetime)}</p>
                    <p className="font-body-md text-on-surface-variant">{it.seizure_location ?? "—"}</p>
                  </td>
                  <td className="px-4 py-4">
                    <div className="flex items-center justify-end gap-1">
                      <IconButton icon="edit" label={t("common.edit")} onClick={() => setEditing(it)} />
                      <DeleteButton
                        onDelete={async () => {
                          await api.delete(`/api/cases/${caseId}/seized-items/${it.id}`);
                          onChanged();
                        }}
                      />
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function SeizedItemForm({
  caseId,
  item,
  onDone,
  onSaved,
}: {
  caseId: number;
  item: SeizedItem | null;
  onDone: () => void;
  onSaved: () => void;
}) {
  const [f, setF] = useState<ItemForm>(
    item
      ? {
          description: item.description ?? "",
          quantity: item.quantity != null ? String(item.quantity) : "",
          estimated_value: item.estimated_value != null ? String(item.estimated_value) : "",
          seized_from: item.seized_from != null ? String(item.seized_from) : "",
          seizure_datetime: "",
          seizure_location: item.seizure_location ?? "",
        }
      : EMPTY_ITEM
  );
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { t } = useI18n();
  const set = (k: keyof ItemForm, v: string) => setF((p) => ({ ...p, [k]: v }));

  async function save() {
    if (!f.description.trim()) {
      setErr(t("evidence.descRequired"));
      return;
    }
    setSaving(true);
    setErr(null);
    const body = {
      description: f.description,
      quantity: f.quantity === "" ? null : Number(f.quantity),
      estimated_value: f.estimated_value === "" ? null : Number(f.estimated_value),
      seizure_location: f.seizure_location || null,
      seizure_datetime: f.seizure_datetime ? new Date(f.seizure_datetime).toISOString() : null,
    };
    try {
      if (item) await api.patch(`/api/cases/${caseId}/seized-items/${item.id}`, body);
      else await api.post(`/api/cases/${caseId}/seized-items`, body);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? t("details.saveError"));
      setSaving(false);
    }
  }

  return (
    <div className="border border-outline-variant rounded bg-surface-container-low p-5 mb-4 space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">
        {item ? t("evidence.seized.editTitle") : t("evidence.seized.addTitle")}
      </p>
      <Field label={t("evidence.col.description")}>
        <Text value={f.description} onChange={(v) => set("description", v)} />
      </Field>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Field label={t("evidence.field.quantity")}>
          <Text value={f.quantity} onChange={(v) => set("quantity", v)} />
        </Field>
        <Field label={t("evidence.field.estValue")}>
          <Text value={f.estimated_value} onChange={(v) => set("estimated_value", v)} />
        </Field>
        <Field label={t("evidence.field.seizureDatetime")}>
          <Text type="datetime-local" value={f.seizure_datetime} onChange={(v) => set("seizure_datetime", v)} />
        </Field>
        <Field label={t("evidence.field.seizurePlace")}>
          <Text value={f.seizure_location} onChange={(v) => set("seizure_location", v)} />
        </Field>
      </div>
      {err && <ErrorLine message={err} />}
      <FormActions saving={saving} onSave={save} onCancel={onDone} saveLabel={item ? t("common.save") : t("common.add")} savingLabel={t("common.saving")} />
    </div>
  );
}

/* ---------------- Evidence files ---------------- */

function EvidenceFilesBlock({
  caseId,
  evidence,
  persons,
  personName,
  onChanged,
}: {
  caseId: number;
  evidence: Evidence[];
  persons: Person[];
  personName: Map<number, string>;
  onChanged: () => void;
}) {
  const [uploading, setUploading] = useState(false);
  const { t } = useI18n();

  return (
    <section>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="font-headline-md text-primary">{t("evidence.files.title")}</h2>
          <p className="font-body-md text-on-surface-variant">
            {t("evidence.files.subtitle")}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setUploading((u) => !u)}
          className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
        >
          <span className="material-symbols-outlined text-lg">upload_file</span>
          {t("evidence.files.upload")}
        </button>
      </div>

      {uploading && (
        <UploadForm
          caseId={caseId}
          persons={persons}
          onDone={() => setUploading(false)}
          onSaved={() => {
            setUploading(false);
            onChanged();
          }}
        />
      )}

      {evidence.length === 0 && !uploading ? (
        <EmptyBlock icon="folder_open" title={t("evidence.files.empty.title")} hint={t("evidence.files.empty.hint")} />
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {evidence.map((ev) => (
            <EvidenceCard key={ev.id} caseId={caseId} ev={ev} personName={personName} />
          ))}
        </div>
      )}
    </section>
  );
}

function EvidenceCard({
  caseId,
  ev,
  personName,
}: {
  caseId: number;
  ev: Evidence;
  personName: Map<number, string>;
}) {
  const [thumb, setThumb] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const { t } = useI18n();

  // Fetch the image as an authenticated blob (an <img src> can't send the JWT).
  useEffect(() => {
    let url: string | null = null;
    if (ev.type === "IMAGE") {
      api
        .get(`/api/cases/${caseId}/evidence/${ev.id}/file`, { responseType: "blob" })
        .then((r) => {
          url = URL.createObjectURL(r.data as Blob);
          setThumb(url);
        })
        .catch(() => setThumb(null));
    }
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [caseId, ev.id, ev.type]);

  const hash = ev.file_hash ?? "";
  const shortHash = hash ? `${hash.slice(0, 10)}…${hash.slice(-6)}` : "—";

  async function copyHash() {
    try {
      await navigator.clipboard.writeText(hash);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      /* clipboard blocked — ignore */
    }
  }

  return (
    <div className="border border-outline-variant rounded overflow-hidden bg-surface-container-lowest flex flex-col">
      {/* Thumbnail / type placeholder */}
      <div className="aspect-video bg-surface-container border-b border-outline-variant flex items-center justify-center overflow-hidden">
        {thumb ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={thumb} alt={ev.description ?? "Evidence"} className="w-full h-full object-cover" />
        ) : (
          <span className="material-symbols-outlined text-4xl text-outline">
            {ev.type === "IMAGE" ? "image" : ev.type === "DOCUMENT" ? "description" : "inventory_2"}
          </span>
        )}
      </div>

      <div className="p-4 flex flex-col gap-3 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-label-caps text-[10px] text-on-surface-variant border border-outline-variant rounded px-2 py-0.5">
            {ev.type}
          </span>
        </div>

        <p className="font-body-md text-on-surface">
          {isBlankDesc(ev.description) ? t("common.noDescription") : ev.description}
        </p>

        {ev.tags && ev.tags.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {ev.tags.map((tag, i) => (
              <span key={i} className="font-mono-sm text-on-secondary-container bg-secondary-container rounded px-2 py-0.5">
                #{tag}
              </span>
            ))}
          </div>
        )}

        {/* SHA-256 — surfaced prominently, the chain-of-custody anchor */}
        <div className="mt-auto pt-3 border-t border-outline-variant">
          <p className="font-label-caps text-[10px] text-on-surface-variant mb-1">{t("evidence.sha")}</p>
          <div className="flex items-center gap-2">
            <code className="font-mono-data text-primary" title={hash}>
              {shortHash}
            </code>
            <button
              type="button"
              onClick={copyHash}
              className="text-on-surface-variant hover:text-primary transition-colors"
              title={t("evidence.copyHash")}
              aria-label={t("evidence.copyHash")}
            >
              <span className="material-symbols-outlined text-base">
                {copied ? "check" : "content_copy"}
              </span>
            </button>
            {copied && <span className="font-body-md text-on-surface-variant">{t("evidence.copied")}</span>}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-2 pt-2 border-t border-outline-variant">
          <div>
            <p className="font-label-caps text-[9px] text-on-surface-variant">{t("evidence.collected")}</p>
            <p className="font-mono-sm text-on-surface-variant">{formatUpdated(ev.collected_at)}</p>
          </div>
          <div>
            <p className="font-label-caps text-[9px] text-on-surface-variant">{t("evidence.by")}</p>
            <p className="font-body-md text-on-surface">{ev.collected_by_name ?? "—"}</p>
          </div>
          {ev.linked_person_id != null && (
            <div className="col-span-2">
              <p className="font-label-caps text-[9px] text-on-surface-variant">{t("evidence.linkedPerson")}</p>
              <p className="font-body-md text-on-surface">
                {personName.get(ev.linked_person_id) ?? `#${ev.linked_person_id}`}
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function UploadForm({
  caseId,
  persons,
  onDone,
  onSaved,
}: {
  caseId: number;
  persons: Person[];
  onDone: () => void;
  onSaved: () => void;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [type, setType] = useState("IMAGE");
  const [description, setDescription] = useState("");
  const [tags, setTags] = useState("");
  const [linked, setLinked] = useState("");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const { t } = useI18n();

  async function upload() {
    if (!file) {
      setErr(t("evidence.upload.chooseFile"));
      return;
    }
    setSaving(true);
    setErr(null);
    const fd = new FormData();
    fd.append("file", file);
    fd.append("type", type);
    if (description) fd.append("description", description);
    if (tags) fd.append("tags", JSON.stringify(tags.split(",").map((s) => s.trim()).filter(Boolean)));
    if (linked) fd.append("linked_person_id", linked);
    try {
      await api.post(`/api/cases/${caseId}/evidence`, fd);
      onSaved();
    } catch (e: any) {
      setErr(e?.response?.data?.detail ?? t("evidence.upload.failed"));
      setSaving(false);
    }
  }

  return (
    <div className="border border-outline-variant rounded bg-surface-container-low p-5 mb-4 space-y-3">
      <p className="font-label-caps text-[10px] text-on-surface-variant">{t("evidence.files.upload")}</p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        <Field label={t("evidence.field.file")}>
          <input
            type="file"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            className="w-full font-body-md text-on-surface file:mr-3 file:border-0 file:bg-primary file:text-surface-bright file:px-3 file:py-1.5 file:rounded file:font-body-md"
          />
        </Field>
        <Field label={t("evidence.field.type")}>
          <select
            value={type}
            onChange={(e) => setType(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            {EVIDENCE_TYPES.map((code) => (
              <option key={code} value={code}>
                {code}
              </option>
            ))}
          </select>
        </Field>
        <Field label={t("evidence.col.description")}>
          <Text value={description} onChange={setDescription} />
        </Field>
        <Field label={t("evidence.field.tags")}>
          <Text value={tags} onChange={setTags} placeholder="scene, weapon" />
        </Field>
        <Field label={t("evidence.field.linkedPerson")}>
          <select
            value={linked}
            onChange={(e) => setLinked(e.target.value)}
            className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
          >
            <option value="">{t("common.none")}</option>
            {persons.map((p) => (
              <option key={p.id} value={p.id}>
                {p.full_name ?? `Person ${p.id}`} ({p.role})
              </option>
            ))}
          </select>
        </Field>
      </div>
      {err && <ErrorLine message={err} />}
      <FormActions saving={saving} onSave={upload} onCancel={onDone} saveLabel={t("evidence.upload.action")} savingLabel={t("evidence.upload.uploading")} />
    </div>
  );
}

/* ---------------- shared bits ---------------- */

function EmptyBlock({ icon, title, hint }: { icon: string; title: string; hint: string }) {
  return (
    <div className="border border-dashed border-outline-variant rounded bg-surface-container-lowest py-16 flex flex-col items-center gap-3 text-center">
      <span className="material-symbols-outlined text-4xl text-outline">{icon}</span>
      <p className="font-headline-md text-primary">{title}</p>
      <p className="font-body-md text-on-surface-variant">{hint}</p>
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block space-y-1">
      <span className="font-label-caps text-[10px] text-on-surface-variant">{label}</span>
      {children}
    </label>
  );
}

function Text({
  value,
  onChange,
  type = "text",
  placeholder,
}: {
  value: string;
  onChange: (v: string) => void;
  type?: string;
  placeholder?: string;
}) {
  return (
    <input
      type={type}
      value={value}
      placeholder={placeholder}
      onChange={(e) => onChange(e.target.value)}
      className="w-full bg-surface-container-lowest border border-outline-variant rounded px-3 py-2 font-body-md text-on-surface focus:outline-none focus:border-primary"
    />
  );
}

function FormActions({
  saving,
  onSave,
  onCancel,
  saveLabel,
  savingLabel = "Saving…",
}: {
  saving: boolean;
  onSave: () => void;
  onCancel: () => void;
  saveLabel: string;
  savingLabel?: string;
}) {
  const { t } = useI18n();
  return (
    <div className="flex gap-2 pt-1">
      <button
        type="button"
        onClick={onSave}
        disabled={saving}
        className="bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-60"
      >
        {saving ? savingLabel : saveLabel}
      </button>
      <button
        type="button"
        onClick={onCancel}
        className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
      >
        {t("common.cancel")}
      </button>
    </div>
  );
}

function IconButton({ icon, label, onClick }: { icon: string; label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-label={label}
      title={label}
      className="text-on-surface-variant hover:text-primary transition-colors p-1"
    >
      <span className="material-symbols-outlined text-lg">{icon}</span>
    </button>
  );
}

function DeleteButton({ onDelete }: { onDelete: () => Promise<void> }) {
  const [confirm, setConfirm] = useState(false);
  const { t } = useI18n();
  if (confirm) {
    return (
      <span className="inline-flex items-center gap-1">
        <button
          type="button"
          onClick={onDelete}
          className="font-label-caps text-[10px] text-error hover:underline"
        >
          {t("common.delete")}
        </button>
        <button
          type="button"
          onClick={() => setConfirm(false)}
          className="font-label-caps text-[10px] text-on-surface-variant hover:underline"
        >
          {t("common.cancel")}
        </button>
      </span>
    );
  }
  return <IconButton icon="delete" label={t("common.delete")} onClick={() => setConfirm(true)} />;
}

function ErrorLine({ message }: { message: string }) {
  return (
    <p role="alert" className="flex items-center gap-1 font-body-md text-error">
      <span className="material-symbols-outlined text-base">error</span>
      {message}
    </p>
  );
}

function EvidenceSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="h-40 bg-surface-container-high rounded" />
      <div className="grid grid-cols-3 gap-4">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-64 bg-surface-container-high rounded" />
        ))}
      </div>
    </div>
  );
}

"use client";
/**
 * Case assistant — Capability 3: document generation by request.
 *
 * The officer asks for a document in their own words; the assistant works out WHICH
 * document, confirms, and then calls the very same endpoint the Documents tab calls.
 *
 * THE CHAT DOES NOT GENERATE ANYTHING. It has no template, no context builder and no
 * write of its own — `POST /api/cases/{id}/documents/{doc_type}` does all of it, exactly
 * as it does for the Documents tab. So there is one generation path, and the two surfaces
 * cannot drift apart.
 *
 * THE MODEL WRITES NO SENTENCE THE OFFICER READS. Routing returns a label out of a closed
 * set; every line below is composed from the i18n table. That is what keeps legal prose
 * out of the chat structurally rather than by instruction.
 *
 * NOTHING IS WRITTEN WITHOUT A CONFIRMATION. Generation creates a document row, a version
 * snapshot, a diary entry and an audit row, so a routed intent only ever produces a card
 * with a button on it. Misrouting therefore costs a click, never a document.
 */
import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/api";
import { useI18n, type TKey } from "@/lib/i18n";
import { DOC_TYPES, DOC_ICON, fieldLabel, parseMissing } from "@/lib/docTypes";

type Msg =
  | { kind: "officer"; text: string }
  | { kind: "assistant"; text: string }
  | { kind: "choices"; text: string; options: string[] }
  | { kind: "missing"; docType: string; fields: string[] }
  | { kind: "done"; docType: string; docId: number; version: number };

type Pending = { docType: string; existing: { version: number } | null };

export default function AssistantTab({
  caseId,
  role,
  onDocsChanged,
}: {
  caseId: number;
  role: string;
  onDocsChanged: () => void;
}) {
  const { t, apiLang } = useI18n();
  const canGenerate = role === "IO" || role === "SHO";

  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Pending | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, busy]);

  const docLabel = (key: string) => t(`docs.type.${key}` as TKey);
  const say = (m: Msg) => setMessages((prev) => [...prev, m]);

  /** Look up whether this document already exists, so the gate can say "version N+1"
   *  rather than implying a first draft. Read-only; a failure just omits the detail. */
  async function existingVersion(docType: string): Promise<{ version: number } | null> {
    try {
      const res = await api.get(`/api/cases/${caseId}/documents`);
      const hit = (res.data ?? []).find((d: any) => d.doc_type === docType);
      return hit ? { version: hit.version ?? 1 } : null;
    } catch {
      return null;
    }
  }

  async function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    say({ kind: "officer", text });
    setInput("");
    setPending(null);
    setBusy(true);
    try {
      const res = await api.post(`/api/cases/${caseId}/chat/route`, {
        message: text,
        lang: apiLang,
      });
      const { intent, doc_type, candidates } = res.data;

      if (intent === "GENERATE" && doc_type) {
        await proposeGeneration(doc_type);
      } else if (intent === "AMBIGUOUS") {
        // Two documents fit the words equally well. Ask; never pick one.
        say({ kind: "choices", text: t("chat.ask.which"), options: candidates ?? [] });
      } else {
        say({ kind: "choices", text: t("chat.unknown"), options: DOC_TYPES.map((d) => d.key) });
      }
    } catch {
      say({ kind: "assistant", text: t("chat.error") });
    } finally {
      setBusy(false);
    }
  }

  /** Put a confirmation card up. This is the only route to generation. */
  async function proposeGeneration(docType: string) {
    if (!canGenerate) {
      say({ kind: "assistant", text: t("chat.denied") });
      return;
    }
    setPending({ docType, existing: await existingVersion(docType) });
  }

  /** Confirmed: call the EXISTING generator. No new generation logic lives here. */
  async function runGeneration(docType: string) {
    setPending(null);
    setBusy(true);
    try {
      const res = await api.post(
        `/api/cases/${caseId}/documents/${docType}?lang=${apiLang}`
      );
      say({
        kind: "done",
        docType,
        docId: res.data.id,
        version: res.data.version ?? 1,
      });
      onDocsChanged();
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      const missing = parseMissing(typeof detail === "string" ? detail : undefined);
      if (missing) {
        // The existing missing-field checklist, surfaced as-is. Capability 2 turns this
        // into a conversation; for now it reports exactly what the generator reported.
        say({ kind: "missing", docType, fields: missing });
      } else if (e?.response?.status === 403) {
        say({ kind: "assistant", text: t("chat.denied") });
      } else {
        say({ kind: "assistant", text: typeof detail === "string" ? detail : t("chat.error") });
      }
    } finally {
      setBusy(false);
    }
  }

  async function download(docId: number) {
    const res = await api.get(`/api/documents/${docId}/download`, { responseType: "blob" });
    const url = URL.createObjectURL(new Blob([res.data]));
    const a = document.createElement("a");
    a.href = url;
    a.download = `document-${docId}.docx`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="border border-outline-variant rounded bg-surface-container-lowest flex flex-col">
      <div className="flex items-center gap-2 px-5 py-3 border-b border-outline-variant">
        <span className="material-symbols-outlined text-on-surface-variant text-xl">forum</span>
        <h2 className="font-headline-md text-primary">{t("chat.title")}</h2>
        <span className="ml-auto font-body-sm text-on-surface-variant">{t("chat.scope")}</span>
      </div>

      <div
        ref={scrollRef}
        className="px-5 py-4 space-y-4 overflow-y-auto custom-scrollbar h-[52vh] min-h-[320px]"
      >
        <Bubble who={t("chat.assistant")} tone="assistant">
          {t("chat.intro")}
        </Bubble>

        {messages.map((m, i) => {
          if (m.kind === "officer")
            return <Bubble key={i} who={t("chat.you")} tone="officer">{m.text}</Bubble>;

          if (m.kind === "assistant")
            return <Bubble key={i} who={t("chat.assistant")} tone="assistant">{m.text}</Bubble>;

          if (m.kind === "choices")
            return (
              <Bubble key={i} who={t("chat.assistant")} tone="assistant">
                <p>{m.text}</p>
                <div className="flex flex-wrap gap-2 mt-3">
                  {m.options.map((key) => (
                    <button
                      key={key}
                      type="button"
                      onClick={() => proposeGeneration(key)}
                      className="flex items-center gap-1.5 border border-outline-variant rounded px-3 py-1.5 font-body-sm text-on-surface hover:border-primary hover:text-primary transition-colors"
                    >
                      <span className="material-symbols-outlined text-base">
                        {DOC_ICON[key] ?? "description"}
                      </span>
                      {docLabel(key)}
                    </button>
                  ))}
                </div>
                {m.options.length > 2 && (
                  <p className="font-body-sm text-on-surface-variant mt-2">
                    {t("chat.unknown.hint")}
                  </p>
                )}
              </Bubble>
            );

          if (m.kind === "missing")
            return (
              <Bubble key={i} who={t("chat.assistant")} tone="assistant">
                <p>{t("chat.missing", { doc: docLabel(m.docType) })}</p>
                <ul className="mt-2 space-y-1">
                  {m.fields.map((f) => (
                    <li key={f} className="font-body-sm text-on-surface flex items-center gap-2">
                      <span className="material-symbols-outlined text-base text-secondary">
                        error
                      </span>
                      {fieldLabel(f, t)}
                    </li>
                  ))}
                </ul>
                <p className="font-body-sm text-on-surface-variant mt-2">
                  {t("chat.missing.hint")}
                </p>
              </Bubble>
            );

          return (
            <Bubble key={i} who={t("chat.assistant")} tone="assistant">
              <p>{t("chat.done", { doc: docLabel(m.docType), v: m.version })}</p>
              <p className="font-body-sm text-on-surface-variant mt-1">{t("chat.done.hint")}</p>
              <div className="flex gap-2 mt-3">
                <button
                  type="button"
                  onClick={() => download(m.docId)}
                  className="flex items-center gap-1.5 border border-outline-variant rounded px-3 py-1.5 font-body-sm hover:border-primary hover:text-primary transition-colors"
                >
                  <span className="material-symbols-outlined text-base">download</span>
                  {t("chat.download")}
                </button>
              </div>
            </Bubble>
          );
        })}

        {/* ---- the confirmation gate: nothing is written until this is clicked ---- */}
        {pending && (
          <div className="border border-primary rounded p-4 bg-surface-container-low">
            <p className="font-body-md text-on-surface font-semibold">
              {t("chat.confirm.title", { doc: docLabel(pending.docType) })}
            </p>
            <p className="font-body-sm text-on-surface-variant mt-1">
              {pending.existing
                ? t("chat.confirm.regen", {
                    doc: docLabel(pending.docType),
                    v: pending.existing.version,
                    next: pending.existing.version + 1,
                  })
                : t("chat.confirm.new")}
            </p>
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={() => runGeneration(pending.docType)}
                className="bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
              >
                {t("chat.confirm.go")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setPending(null);
                  say({ kind: "assistant", text: t("chat.cancelled") });
                }}
                className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
              >
                {t("chat.confirm.cancel")}
              </button>
            </div>
          </div>
        )}

        {busy && (
          <p className="font-body-md text-on-surface-variant flex items-center gap-2">
            <span className="material-symbols-outlined animate-spin text-lg">progress_activity</span>
            {t("chat.thinking")}
          </p>
        )}
      </div>

      <div className="border-t border-outline-variant p-4 space-y-3">
        <textarea
          rows={2}
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              onSend();
            }
          }}
          placeholder={t("chat.placeholder")}
          className="w-full bg-surface-container-low border border-outline-variant rounded px-4 py-3 font-body-md text-on-surface focus:outline-none focus:border-primary transition-colors resize-y"
        />
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={onSend}
            disabled={busy || !input.trim()}
            className="flex items-center gap-2 bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-xl">send</span>
            {t("chat.send")}
          </button>
          {messages.length > 0 && (
            <button
              type="button"
              onClick={() => {
                setMessages([]);
                setPending(null);
              }}
              className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
            >
              {t("chat.clear")}
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function Bubble({
  who,
  tone,
  children,
}: {
  who: string;
  tone: "officer" | "assistant";
  children: React.ReactNode;
}) {
  return (
    <div className={tone === "officer" ? "text-right" : ""}>
      <p className="font-label-caps text-[9px] text-on-surface-variant mb-1">{who}</p>
      <div
        className={`inline-block max-w-[90%] text-left rounded px-4 py-2.5 font-body-md whitespace-pre-wrap ${
          tone === "officer"
            ? "bg-primary text-surface-bright"
            : "bg-surface-container-low text-on-surface border border-outline-variant"
        }`}
      >
        {children}
      </div>
    </div>
  );
}

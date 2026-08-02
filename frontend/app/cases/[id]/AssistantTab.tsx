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
  | { kind: "missing"; docType: string; fields: string[]; blocked: string[] }
  | { kind: "query"; queryKind: string; lines: string[] }
  | { kind: "decline" }
  | { kind: "done"; docType: string; docId: number; version: number };

/**
 * The questions the assistant answers, and where each answer comes from.
 *
 * Every entry is an EXISTING read endpoint, and `lines` only formats values that came out
 * of it. There is no branch here that composes a sentence of its own, and nothing that
 * calls weak-charges, judgment retrieval or the consistency check — those run live legal
 * reasoning, and a record lookup must not quietly turn into an analysis the officer did
 * not ask to run. They stay on the Legal tab.
 */
const QUERY_KINDS = [
  "EVIDENCE", "WITNESSES", "ACCUSED", "PEOPLE", "ITEMS",
  "SECTIONS", "DIARY", "DOCUMENTS", "STATEMENTS", "STATUS",
] as const;

type Pending = { docType: string; existing: { version: number } | null };

/** The document we are collecting fields for, and which fields are still outstanding.
 *  While this is set, the officer's next message is read as an ANSWER rather than routed
 *  as a new request — we know what we asked, so there is nothing to classify. */
type Awaiting = { docType: string; fields: string[] };

/** Officer-confirmed-but-not-yet-written values. This is the gate: values sit here until
 *  the officer approves them, and only then are they sent to the pool endpoints. */
type FillPlan = { target: "case" | "person" | "item"; field?: string; role?: string };
type ProposedFill = {
  docType: string;
  values: Record<string, string>;
  unanswered: string[];
  plan: Record<string, FillPlan>;
};

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
  const [awaiting, setAwaiting] = useState<Awaiting | null>(null);
  const [fill, setFill] = useState<ProposedFill | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, pending, busy]);

  const docLabel = (key: string) => t(`docs.type.${key}` as TKey);
  const say = (m: Msg) => setMessages((prev) => [...prev, m]);

  /** Join field names the way the officer's language joins a list. */
  const joinList = (labels: string[]) =>
    labels.length <= 1
      ? labels[0] ?? ""
      : labels.slice(0, -1).join(t("intake.ask.listSep")) +
        t("intake.ask.listLast") +
        labels[labels.length - 1];

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
    setFill(null);
    setBusy(true);
    try {
      // If we just asked for specific fields, this message is the ANSWER. No routing is
      // needed — we know what the question was, so there is nothing to classify.
      if (awaiting) {
        await readAnswer(text, awaiting);
        return;
      }

      const res = await api.post(`/api/cases/${caseId}/chat/route`, {
        message: text,
        lang: apiLang,
      });
      const { intent, doc_type, candidates } = res.data;

      if (intent === "GENERATE" && doc_type) {
        await proposeGeneration(doc_type);
      } else if (intent === "QUERY" && res.data.query_kind) {
        await answerQuery(res.data.query_kind);
      } else if (intent === "AMBIGUOUS") {
        // Two documents fit the words equally well. Ask; never pick one.
        say({ kind: "choices", text: t("chat.ask.which"), options: candidates ?? [] });
      } else {
        // Not a document request and not a question we can look up — including anything
        // asking for an assessment. Say what can be answered; never venture an opinion.
        say({ kind: "decline" });
      }
    } catch {
      say({ kind: "assistant", text: t("chat.error") });
    } finally {
      setBusy(false);
    }
  }

  /** Read the officer's reply onto the outstanding fields. Proposes only — no write. */
  async function readAnswer(text: string, ctx: Awaiting) {
    const res = await api.post(`/api/cases/${caseId}/chat/answer`, {
      answer: text,
      fields: ctx.fields,
      lang: apiLang,
    });
    const values: Record<string, string> = res.data.values ?? {};
    const unanswered: string[] = res.data.unanswered ?? [];

    if (!Object.keys(values).length) {
      // Nothing usable in the reply. Say so and leave the fields empty — the document
      // goes on blocking rather than being completed with something plausible.
      say({ kind: "assistant", text: t("chat.fill.none") });
      return;
    }
    setFill({ docType: ctx.docType, values, unanswered, plan: res.data.plan ?? {} });
  }

  /**
   * Answer a question by READING an existing endpoint and formatting what it returns.
   *
   * Nothing in here writes a sentence about the case. Each branch fetches, picks fields
   * out of the response, and hands back a list of values; the surrounding sentence is an
   * i18n template. That is the whole guarantee — a component with no ability to compose
   * prose cannot interpret evidence, weigh a case, or state law, however it is prompted.
   */
  async function answerQuery(queryKind: string) {
    const get = async (path: string) => (await api.get(`/api/cases/${caseId}${path}`)).data ?? [];
    const person = (p: any) =>
      [p.full_name || p.alias, p.age ? `${p.age}` : null, p.address].filter(Boolean).join(", ");

    let lines: string[] = [];
    switch (queryKind) {
      case "EVIDENCE": {
        const rows = await get("/evidence");
        lines = rows.map((e: any) =>
          [e.description, e.type].filter(Boolean).join(" — ")
        );
        break;
      }
      case "WITNESSES":
      case "ACCUSED": {
        const role = queryKind === "WITNESSES" ? "WITNESS" : "ACCUSED";
        const rows = await get("/persons");
        lines = rows.filter((p: any) => p.role === role).map(person);
        break;
      }
      case "PEOPLE": {
        const rows = await get("/persons");
        lines = rows.map((p: any) => `${person(p)} — ${t(`person.${p.role}.one` as TKey)}`);
        break;
      }
      case "ITEMS": {
        const rows = await get("/seized-items");
        lines = rows.map((s: any) =>
          [s.description, s.quantity ? `× ${s.quantity}` : null, s.seizure_location]
            .filter(Boolean)
            .join(" — ")
        );
        break;
      }
      case "SECTIONS": {
        // ACCEPTED only, verbatim from the pool. Suggested-but-unreviewed sections are
        // not "the charges", and the assistant does not decide which apply.
        const rows = await get("/sections");
        lines = rows
          .filter((s: any) => s.status === "ACCEPTED")
          .map((s: any) => `${s.act} ${s.section_code} — ${s.section_title ?? ""}`.trim());
        break;
      }
      case "DIARY": {
        const detail = (await api.get(`/api/cases/${caseId}`)).data;
        lines = (detail.diary_entries ?? []).map((d: any) =>
          [d.entry_datetime?.slice(0, 10), d.description].filter(Boolean).join(" — ")
        );
        break;
      }
      case "DOCUMENTS": {
        const rows = await get("/documents");
        lines = rows.map(
          (d: any) => `${docLabel(d.doc_type)} — v${d.version ?? 1}, ${d.status}`
        );
        break;
      }
      case "STATEMENTS": {
        const [rows, persons] = await Promise.all([get("/statements"), get("/persons")]);
        const nameById: Record<number, string> = Object.fromEntries(
          persons.map((p: any) => [p.id, p.full_name || p.alias || ""])
        );
        lines = rows.map((s: any) =>
          [nameById[s.person_id], s.statement_type, s.recorded_at?.slice(0, 10)]
            .filter(Boolean)
            .join(" — ")
        );
        break;
      }
      case "STATUS": {
        const c = (await api.get(`/api/cases/${caseId}`)).data;
        lines = [
          `${t("docs.field.case_number")}: ${c.case_number}`,
          `${t("docs.field.fir_number")}: ${c.fir_number ?? "—"}`,
          `${t("docs.field.police_station")}: ${c.police_station ?? "—"}`,
          `${t("docs.field.district")}: ${c.district ?? "—"}`,
          `${t("chat.q.STATUS.state")}: ${c.status}`,
        ];
        break;
      }
      default:
        say({ kind: "decline" });
        return;
    }
    say({ kind: "query", queryKind, lines: lines.filter(Boolean) });
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
        await askForMissing(docType, missing);
      } else if (e?.response?.status === 403) {
        say({ kind: "assistant", text: t("chat.denied") });
      } else {
        say({ kind: "assistant", text: typeof detail === "string" ? detail : t("chat.error") });
      }
    } finally {
      setBusy(false);
    }
  }

  /**
   * Turn the generator's checklist into a question.
   *
   * The checklist is taken exactly as the generator reported it — nothing here decides
   * what a document requires. The split only says which of those fields an officer can
   * answer in a chat: accepted legal sections cannot be, because accepting a section is
   * the officer's reviewed decision in the legal flow, and a chat that could add one
   * would be authoring law.
   */
  async function askForMissing(docType: string, missing: string[]) {
    let fillable = missing;
    let blocked: string[] = [];
    try {
      const res = await api.post(`/api/cases/${caseId}/chat/missing`, { missing });
      fillable = [...(res.data.fillable ?? []), ...(res.data.unknown ?? [])];
      blocked = res.data.blocked ?? [];
    } catch {
      /* fall back to showing the whole checklist unsplit */
    }
    say({ kind: "missing", docType, fields: fillable, blocked });
    setAwaiting(fillable.length ? { docType, fields: fillable } : null);
  }

  /**
   * Apply confirmed values through the EXISTING pool endpoints, then retry the document.
   *
   * Every write below is a call the case workspace already makes: PATCH the case, POST a
   * person, POST/PATCH a seized item. Each writes its own audit row and diary entry as it
   * always has, so a field filled from the chat is indistinguishable in the record from
   * one typed into a form — which is the point.
   */
  async function applyFill(proposed: ProposedFill) {
    const { docType, values, plan: fillPlan } = proposed;
    setFill(null);
    setBusy(true);
    try {
      const casePatch: Record<string, string> = {};
      const itemFields: Record<string, string> = {};

      for (const [field, value] of Object.entries(values)) {
        const plan = fillPlan[field];
        if (!plan) continue;
        if (plan.target === "case") casePatch[plan.field!] = value;
        else if (plan.target === "item") itemFields[plan.field!] = value;
        else if (plan.target === "person") {
          await api.post(`/api/cases/${caseId}/persons`, {
            role: plan.role,
            full_name: value,
          });
        }
      }

      if (Object.keys(casePatch).length) {
        await api.patch(`/api/cases/${caseId}`, casePatch);
      }

      if (Object.keys(itemFields).length) {
        // Seizure date and place are read off the FIRST seized item, so they attach to it
        // — or create it, when the case has no items yet (which is why the list was empty).
        const items = (await api.get(`/api/cases/${caseId}/seized-items`)).data ?? [];
        if (items.length) {
          await api.patch(`/api/cases/${caseId}/seized-items/${items[0].id}`, itemFields);
        } else {
          await api.post(`/api/cases/${caseId}/seized-items`, itemFields);
        }
      }

      onDocsChanged();
      say({
        kind: "assistant",
        text: t("chat.fill.saved", { n: Object.keys(values).length }),
      });
      setAwaiting(null);
      // The officer asked for a document; now that the gaps are filled, try again.
      await runGeneration(docType);
    } catch (e: any) {
      const detail = e?.response?.data?.detail;
      say({ kind: "assistant", text: typeof detail === "string" ? detail : t("chat.error") });
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
                {/* The question names the fields the officer can answer right here. */}
                {m.fields.length > 0 && (
                  <>
                    <p>
                      {t("chat.ask.fields", {
                        doc: docLabel(m.docType),
                        fields: joinList(m.fields.map((f) => fieldLabel(f, t))),
                      })}
                    </p>
                    <p className="font-body-sm text-on-surface-variant mt-1">
                      {t("chat.ask.fields.hint")}
                    </p>
                  </>
                )}
                {/* Fields no chat answer can fill — say which surface owns them. */}
                {m.blocked.length > 0 && (
                  <p className={`font-body-sm text-on-surface-variant ${m.fields.length ? "mt-3" : ""}`}>
                    {t("chat.missing.blocked", {
                      fields: joinList(m.blocked.map((f) => fieldLabel(f, t))),
                    })}
                  </p>
                )}
              </Bubble>
            );

          if (m.kind === "query")
            return (
              <Bubble key={i} who={t("chat.assistant")} tone="assistant">
                {m.lines.length === 0 ? (
                  <p>{t(`chat.q.${m.queryKind}.empty` as TKey)}</p>
                ) : (
                  <>
                    <p>
                      {t(`chat.q.${m.queryKind}.title` as TKey, { n: m.lines.length })}
                    </p>
                    <ul className="mt-2 space-y-1">
                      {m.lines.map((line, j) => (
                        <li key={j} className="font-body-sm text-on-surface flex gap-2">
                          <span className="text-on-surface-variant">{j + 1}.</span>
                          {line}
                        </li>
                      ))}
                    </ul>
                  </>
                )}
              </Bubble>
            );

          if (m.kind === "decline")
            return (
              <Bubble key={i} who={t("chat.assistant")} tone="assistant">
                <p>{t("chat.q.decline")}</p>
                <ul className="mt-2 space-y-1">
                  {QUERY_KINDS.map((k) => (
                    <li key={k} className="font-body-sm text-on-surface-variant">
                      · {t(`chat.q.${k}.label` as TKey)}
                    </li>
                  ))}
                </ul>
                <p className="font-body-sm text-on-surface-variant mt-2">
                  {t("chat.q.decline.docs")}
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

        {/* ---- write gate: these values reach the case file only on confirm ---- */}
        {fill && (
          <div className="border border-primary rounded p-4 bg-surface-container-low">
            <p className="font-body-md text-on-surface font-semibold">
              {t("chat.fill.title")}
            </p>
            <ul className="mt-2 space-y-1">
              {Object.entries(fill.values).map(([field, value]) => (
                <li key={field} className="font-body-sm flex gap-2">
                  <span className="text-on-surface-variant min-w-[9rem]">
                    {fieldLabel(field, t)}
                  </span>
                  <span className="text-on-surface font-semibold">{value}</span>
                </li>
              ))}
            </ul>
            {fill.unanswered.length > 0 && (
              <p className="font-body-sm text-on-surface-variant mt-2">
                {t("chat.fill.stillEmpty", {
                  fields: joinList(fill.unanswered.map((f) => fieldLabel(f, t))),
                })}
              </p>
            )}
            <div className="flex gap-2 mt-3">
              <button
                type="button"
                onClick={() => applyFill(fill)}
                className="bg-primary text-surface-bright px-4 py-2 rounded font-body-md font-semibold hover:bg-inverse-surface transition-colors"
              >
                {t("chat.fill.save")}
              </button>
              <button
                type="button"
                onClick={() => {
                  setFill(null);
                  say({ kind: "assistant", text: t("chat.cancelled") });
                }}
                className="px-4 py-2 rounded font-body-md text-on-surface-variant border border-outline-variant hover:bg-surface-container-low transition-colors"
              >
                {t("chat.confirm.cancel")}
              </button>
            </div>
          </div>
        )}

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

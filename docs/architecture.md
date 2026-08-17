# CrimeGPT — Architecture

This document describes how CrimeGPT is built: its layers, the request flow for legal
section analysis, the data model, the security model, and why everything runs on‑premise.

For the API/service map and the locked technology decisions, see [`CLAUDE.md`](../CLAUDE.md).

---

## 1. The five layers

CrimeGPT is a layered application. A request flows down through the layers and a response
flows back up. Each layer has one job and talks only to the layer below it.

```
┌─ L1. PRESENTATION ───────────────────────────────────────────────────────┐
│  Next.js + React + TypeScript + Tailwind (browser). Sends JSON + a JWT.   │
│  Desktop workspace, conversational intake, and the /m mobile field page.  │
└──────────────────────────────────────────────────────────────────────────┘
             │
┌─ L2. API & AUTH ─────────────────────────────────────────────────────────┐
│  FastAPI routers under /api: auth, cases, pool, legal, documents, intake, │
│  chat, audit, integrations, system. 48 endpoints. JWT validation, role    │
│  gates and step-up PIN enforcement run before every handler.              │
└──────────────────────────────────────────────────────────────────────────┘
             │
┌─ L3. SERVICES ───────────────────────────────────────────────────────────┐
│  Business logic: document generation (docxtpl, no LLM), cross-document    │
│  consistency, CCTNS/IIF export, and the audit + case-diary writes that    │
│  every mutation triggers.                                                 │
└──────────────────────────────────────────────────────────────────────────┘
             │
┌─ L4. AI & LEGAL CORE ────────────────────────────────────────────────────┐
│  call_llm() is the single choke point to the LLM (Ollama/Qwen 2.5 7B, API │
│  fallback). RAG retrieval with query expansion, the grounding validator,  │
│  prompt templates, transcription and translation live here.               │
└──────────────────────────────────────────────────────────────────────────┘
             │
┌─ L5. DATA ───────────────────────────────────────────────────────────────┐
│  PostgreSQL (the 12-table Unified Case Data Pool) · ChromaDB (1,059 legal │
│  sections, embedded) · local filesystem (generated .docx, uploaded        │
│  evidence, Whisper models). All on-premise: Docker for Postgres, Ollama   │
│  on the station's RTX GPU host over the LAN, local disk. Nothing leaves   │
│  the police network.                                                      │
└──────────────────────────────────────────────────────────────────────────┘
```

**Key rule:** every LLM call goes through `call_llm()` (layer 4). Feature code never calls
Ollama or an external API directly. This gives one place to route to Ollama vs. the API
fallback, enforce JSON output, retry on bad JSON, and (in `DEMO_MODE`) serve cached outputs.

---

## 2. Request flow: legal section analysis

This is the signature flow — turning a free‑text complaint into **grounded, explainable**
BNS sections. Raw LLMs hallucinate section numbers (e.g. mapping snatching to a section that
does not exist), so the design never trusts the model's output directly.

```
Officer clicks "Analyse" on a case
        │
        ▼
POST /api/cases/{id}/analyze         (legal router — JWT checked)
        │  narrative = complaint + recorded statements
        ▼
(1) RAG RETRIEVAL        retrieve_offences_union(narrative, k=12)
        │  (1a) embed the RAW narrative with all-MiniLM-L6-v2 (CPU),
        │       cosine search ChromaDB (act="BNS") -> up to 12 real sections
        │  (1b) expand_query(): the LLM restates the complaint in formal
        │       statutory terms, and that restatement is retrieved too
        │  union, de-duplicated by (act, section_code) -> 17-24 candidates
        │
        │  Why 1b exists: a complaint says "the scooter was missing" while the
        │  statute says "dishonestly moves that property". Raw retrieval on the
        │  officer's own words misses the right section often. Measured over 3
        │  runs, the correct section is in the candidate set 89.5% of the time
        │  WITH the restatement and 57.9% WITHOUT it. Expansion only ever ADDS
        │  candidates; raw hits are inserted first and never displaced. It is
        │  best-effort: a failure degrades to raw-narrative retrieval, logged
        │  at WARNING, and never breaks the analysis.
        ▼
(2) LLM SELECTION        call_llm(prompt, schema)  ->  Ollama / Qwen 2.5
        │  "choose ONLY from these candidates; quote the triggering
        │   phrase verbatim from the narrative"  -> JSON selections
        │  The prompt is quote-first: copy the complainant's words, THEN
        │  label them with a section.
        ▼
(3) GROUNDING VALIDATOR  validate_selections(...)   (pure, unit-testable)
        │  DROP any (act, section_code) not in the retrieved candidates
        │  DROP any triggering_phrase not found literally in the narrative
        │  ONE repair attempt is allowed for a bad phrase on an otherwise
        │    valid section; section choice is never re-opened
        │  a relevance floor (retrieval score >= 0.25) drops grounded but
        │    weakly-related survivors
        │  survivors enriched with real title + citation; rejects kept + reasoned
        ▼
(4) PERSISTENCE          write SUGGESTED legal_sections rows
        │  + audit_log row + case_diary entry (one transaction)
        ▼
Response: { sections: [...grounded...], rejected: [...+why...],
            status: "ok" | "no_grounded_match" }
        │
        ▼
Officer ACCEPTS / REJECTS each section  ->  PATCH /cases/{id}/sections/{sid}
        (only ACCEPTED sections flow into documents)
```

Two properties fall out of this design:

- **Explainability** — every suggestion carries the exact phrase from the complaint that
  triggered it, plus its citation to real statutory text.
- **No hallucinated law** — a section the model invents, or a phrase it paraphrases instead
  of quoting, is dropped before it ever reaches the database. If nothing survives, the status
  is `no_grounded_match` (an honest "review manually") rather than a fabricated section.

The same retrieval pattern is scoped per act (BNS for offences, BNSS for procedure, BSA for
evidence) so charge mapping is never polluted by procedural sections.

---

## 3. The data model — Unified Case Data Pool (12 tables)

The product principle is *"enter once, reuse everywhere."* Every document reads from this
pool; no field is typed twice. PostgreSQL, via SQLAlchemy models and Alembic migrations.

| # | Table | Purpose |
|---|-------|---------|
| 1 | `users` | Officers + role, rank and badge/buckle number (for signatures). |
| 2 | `cases` | Case header: number, FIR, station, status, incident, complaint narrative + language. |
| 3 | `persons` | Victims, accused, witnesses, complainant — shared by all documents. |
| 4 | `seized_items` | Seized articles: description, quantity, value, from whom, hash. |
| 5 | `evidence` | Uploaded files with SHA‑256 hash, tags, chain of custody. |
| 6 | `statements` | Witness / accused / victim statements. |
| 7 | `legal_sections` | AI‑suggested, officer‑confirmed sections + triggering phrase. Also stores the model's self-reported `confidence`, which is **retained for regression measurement and is not displayed to the officer** (see technical.md §10). |
| 8 | `judgments` | Relevant case‑law citations + short paraphrases. |
| 9 | `documents` | Generated documents: type, version, status, and the exact merged data. |
| 10 | `document_versions` | Version history / snapshots — never overwrite silently. |
| 11 | `case_diary_entries` | Chronological diary, mostly auto‑generated from actions. |
| 12 | `audit_log` | Append‑only trail: entity, action, field changes, who, when. |

**Invariants the services enforce**
- Writing to `persons` / `seized_items` / `evidence` / `statements` / `legal_sections`
  updates the pool once; documents pull from it at generation time.
- Every mutating endpoint writes an `audit_log` row and, where relevant, a
  `case_diary_entry`.
- Regenerating a document is **version‑aware**: the current state is archived into
  `document_versions` and the same row is bumped to a new draft version — it is never
  duplicated or silently overwritten. `finalize` snapshots the draft, then flips it to
  FINALIZED.

---

## 4. Security model

**Authentication — local JWT.** `POST /auth/login` verifies the username/password (bcrypt
hash) and returns a signed JWT carrying the user id, role and expiry. Every route except
login validates the token via a FastAPI dependency; an invalid or missing token is 401.
Accounts are created by an admin/seed script — there is no self‑signup.

**Authorization — three roles (RBAC).** Gated at the endpoint (and hidden in the UI):

| Role | Can do |
|------|--------|
| **IO** | Create/edit cases and pool data, upload evidence, run AI, generate documents. Sees only cases they created. |
| **SHO** | Everything an IO can see — across all officers (supervision) — plus **finalize/approve** documents. |
| **Legal Advisor** | Read a case, focus on section mapping and judgments; cannot alter evidence. |

Case visibility is enforced centrally: an IO requesting a case they do not own gets a 404
(the case's existence is hidden), while an SHO sees every case.

**Step-up PIN, enforced server-side.** Two writes are high-stakes enough to need a fresh
proof of identity beyond the session token: registering a case and finalizing a document.
The browser asks for the PIN, and the server independently checks that this session actually
stepped up. The record is keyed by a hash of the bearer token, so the claim being made is
"the holder of this session proved themselves", and a new sign-in has to prove it again.

Register is exempt on the mobile path, where the PIN was itself the sign-in and asking again
seconds later would be ceremony rather than security. **Finalize has no exemption at all**,
because an SHO can sign in on a phone with four digits and exempting it would let four digits
approve a document. A refusal is a uniform 401, is audited with the attempted action, and
happens before the endpoint body runs, so nothing is written. The PIN is never logged.

**Idle auto-logout.** An unattended terminal left signed in is a way into the case file:
anyone walking past could register a case under the signed-in officer's name, and the audit
trail would name that officer. The session therefore ends after a period with no activity,
with a warning first. The timeout, the warning window and a seconds-based override are all
environment variables, so a station can tune it without a code change. A request in flight
holds the session open, because the officer is waiting rather than absent, but only up to a
grace period, so one hung connection cannot disable the safeguard.

**Auditability.** The `audit_log` is written on every create/update/delete, recording the
entity, the action, the field‑level changes (old → new), the performing officer and the
timestamp. The audit endpoint returns it newest‑first with the officer's name and rank, and
supports filtering. Combined with the auto case diary and document version history, this
gives a complete, reviewable trail of who did what and when — the accountability the problem
statement demands.

**AI outputs are always drafts.** Generated documents and legal suggestions are drafts that
the officer reviews and accepts/finalizes. The system never treats an AI output as final.

---

## 5. Design decision: everything on‑premise

CrimeGPT is deliberately built to run **inside the police network**, not in a public cloud.

**Why**
- **Data sensitivity & legal chain of custody.** FIRs, accused/victim identities, statements
  and evidence are highly sensitive and legally consequential. They must not leave the
  station's control or be processed by a third‑party cloud LLM.
- **Sovereignty & compliance.** On‑prem keeps case data within jurisdiction and under the
  department's own governance.
- **Availability.** Stations cannot depend on internet uptime for core documentation work.

**How the design supports it**
- The **LLM is local** — Ollama running Qwen 2.5 7B on the station's own RTX GPU, served over
  the LAN. `call_llm()` centralises this so an optional API fallback exists but is never
  required.
- **Embeddings run on CPU** (`all-MiniLM-L6-v2`), keeping the GPU free for the LLM, and the
  **vector store (ChromaDB) is a local file** — the legal corpus never leaves the machine.
- **PostgreSQL, generated documents and uploaded evidence** all live on local infrastructure
  (Docker + local disk).
- The only external touch‑point, **CCTNS export**, targets a **mock receiver** in this
  prototype; production simply points it at the department's own CCTNS endpoint. The
  swap is a URL change, not a rewrite.

### Golden Hour seams

Three hooks are built in so the cyber/financial vertical can plug in later as configuration,
not a rewrite: a `case_type` discriminator on `cases`, the document **template registry**
(a new document is a template + one registry entry, no code change), and a pluggable
workflow/SOP module. These are seats for future work, not features built now.

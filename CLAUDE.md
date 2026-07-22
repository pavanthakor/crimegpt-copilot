# CLAUDE.md — CrimeGPT Technical Foundation

> This file is the single source of truth for the CrimeGPT build. Claude Code reads it automatically as persistent context. Humans: read the top 3 sections before writing any code. Keep this file updated as decisions change.

---

## 0. AGENT RULES (read every time)

1. **Work in vertical slices, one task at a time.** Implement one endpoint/feature end-to-end, then stop and show the result. Do not build "the whole backend" in one go.
2. **Plan before coding** for any non-trivial task: list the files you will change and the approach, wait for confirmation, then code.
3. **Verify your own work.** After implementing, run the code / hit the endpoint and show the actual output. Do not assume it works.
4. **Never touch auth or database migrations without explicit review.** These are high-risk.
5. **Commit after every working slice** with a clear message. A bad change must be one `git reset` away.
6. **Follow the schema and API map in this file exactly.** If something here is wrong or missing, flag it — do not silently invent a different structure.
7. **All AI calls go through `call_llm()`** (Section 6). Never call Ollama or an API directly from feature code.
8. **All AI outputs are drafts.** Every generated document and legal suggestion is reviewed by the officer before it is finalized. Reflect this in the UI (draft → review → finalize).
9. Prefer **simple and working** over clever and half-done. This is a 4-day hackathon build.

---

## 1. PROJECT SUMMARY

**What:** CrimeGPT — an on-premise web application that automates crime-related documentation and legal intelligence for Indian police. One structured case entry becomes the single source of truth that generates all required documents, suggests legal sections and judgments, and maintains a case diary — from FIR to arrest.

**Problem statement:** Kanad S.H.I.E.L.D. Hackathon 2026, Category 2, PS-69EEFDFB90B99 — *"CrimeGPT: AI-Powered Automation for Crime Documentation and Legal Intelligence."* (Ahmedabad City Police, Cyber Crime Branch.)

**Team:** Skill Issue — Thakor Pavansinh, Sumit Kumar, Shiv Gamit, Gopesh Jha · Karnavati University.

**Form factor:** A single **web application** (browser-based), served locally for the demo, designed to run **on-premise** in production. Not a mobile or desktop app.

**Core promise (the one line):** *"One case entry powers every document, and the AI doesn't just fill forms — it explains the law, catches weak charges, and keeps every document consistent, in the officer's own language."*

---

## 2. LOCKED DECISIONS (do not change without team agreement)

| Area | Decision |
|---|---|
| Frontend | Next.js + React + TypeScript + Tailwind CSS |
| Backend | FastAPI + Python 3.11+ + SQLAlchemy + Pydantic |
| Database | PostgreSQL 15+ (local, via Docker) |
| Auth | Local **JWT, 3 roles** (IO, SHO, LEGAL_ADVISOR). Admin-created accounts. No Google/Gmail login. |
| LLM | **Ollama running Qwen 2.5 7B (Q4)** on the RTX 4060 machine, served over LAN. API fallback via `call_llm()`. |
| Embeddings | `nomic-embed-text` via Ollama, or `sentence-transformers` on CPU. Keep GPU free for the LLM. |
| Vector DB | ChromaDB (local, file-based) for legal RAG |
| Doc generation | `docxtpl` + `python-docx` (Word templates) → optional PDF export |
| OCR (if needed) | PaddleOCR or Tesseract (only for scanned-doc ingestion; optional) |
| Object storage | Local filesystem (`/backend/storage/`) for the prototype |

**Hardware note:** Only one machine has the RTX 4060 (8GB). That machine runs `ollama serve` bound to the LAN; teammates point `OLLAMA_HOST` at its IP, OR develop against the API fallback. Do not assume every dev machine can run the model.

---

## 3. DELIVERABLES TARGET (this is what we are graded on)

Build toward these exact outputs — everything in the plan serves them:

1. **Working prototype** generating **at least 4** of the required documents.
2. **Demo** that shows: case creation from FIR → arrest · real-time generation of ≥2 documents · legal section + judgment suggestions.
3. **Documentation:** README + user guide + clean code.
4. **Dataset:** anonymized legal texts (BNS/BNSS/BSA), FIR samples, judgment samples.

**Required documents (target 4, stretch to 7):**
1. Accused Panchnama ✅ (priority)
2. Remand Request Letter (Police Custody) ✅ (priority)
3. Seizure Receipt ✅ (priority)
4. Medical Treatment Letter ✅ (priority)
5. Court Custody Letter (stretch)
6. Accused Face Identification Form (stretch — pairs with face-capture bonus)
7. Purvani Chargesheet (stretch — confirm exact Gujarat format from samples)

---

## 4. FEATURE SCOPE (tiered)

> **Status (reconciled against the code, ~30 slices in):** Tiers 1–3 are ALL built and wired end-to-end (FastAPI backend + Next.js frontend). The list below is the original tiered plan annotated with what actually shipped.

**Tier 1 — Core (✅ all built):** Unified Case Data Pool · Document Generation Engine (**6** docs, §8) · Case Diary Automation (auto entries on key actions) · Legal Section Intelligence (grounded BNS/BNSS/BSA sections + landmark judgments, RAG over a 1,059-chunk Chroma corpus) · Multilingual UI (EN/HI/GU, persisted to localStorage, also drives the AI `lang` param) · Search & Audit (case/person/seized-item search returning `SearchHit`, paginated audit trail, document version history).

**Tier 2 — Signature differentiators (✅ built, one exception):** Explainable section mapping (triggering-phrase highlight + marked-up narrative + confidence) ✅ · Cross-document consistency checker (pure-DB staleness/divergence, `GET /consistency`) ✅ · Auto-writing case diary ✅ · Weak-charge / missing-ingredient alerts ✅ · Gujarati voice-to-document (record → Whisper transcript → **Qwen** English narrative → officer reviews & applies) ✅ · **BNSS/BSA compliance checker — NOT built** (the weak-charge check is the nearest thing shipped).

**Tier 3 — Committed bonuses (✅ all built):** RBAC (3 roles: IO / SHO / LEGAL_ADVISOR) ✅ · Evidence upload + tagging + SHA-256 auto-hash + authenticated file serving ✅ · LERS request templates (preservation + records — compliant `.docx` templates, not a live API) ✅ · CCTNS mock IIF export (POSTs to a mock receiver, returns a mock FIR id) ✅.

**Tier 4 — Genuinely NOT built (deck / roadmap only):** Golden Hour cyber vertical (only the three §10 seams exist — no live workflow logic or timers) · Face-capture / Face ID form (`DocType.FACE_ID` exists but has no template) · Custody Letter & Purvani Chargesheet docs (`CUSTODY_LETTER` / `CHARGESHEET` enum values exist, no templates) · BNSS/BSA compliance checker · `.docx → PDF` export (download is `.docx` only) · money-trail visualisation · offline-first PWA · live CCTNS / ICJS / eCourts / BharatPol integration.

---

## 5. DATABASE SCHEMA (the Unified Case Data Pool)

The whole product is "enter once, reuse everywhere." Every document reads from these tables — no field is ever typed twice. Use SQLAlchemy models + Alembic migrations.

```
users
  id (PK) · username (unique) · password_hash · full_name
  role (enum: IO | SHO | LEGAL_ADVISOR) · rank · badge_no · created_at
      # rank + badge_no were ADDED post-plan; they print on the IF4 / seizure-receipt signature block

cases
  id (PK) · case_number (unique) · case_type (enum: CONVENTIONAL | CYBER_FINANCIAL)   # Golden Hour seam
  title · fir_number · fir_date · police_station · district
  status (enum: COMPLAINT | INVESTIGATION | ARREST | REMAND | CHARGESHEET)
  incident_datetime · incident_location
  complaint_narrative (text) · complaint_language (enum: GU | HI | EN)
  created_by (FK users) · created_at · updated_at

persons                        # victims, accused, witnesses, complainant — shared everywhere
  id (PK) · case_id (FK) · role (enum: VICTIM | ACCUSED | WITNESS | COMPLAINANT)
  full_name · alias · father_name · age · gender
  address · phone · occupation · extra (JSONB) · created_at

seized_items
  id (PK) · case_id (FK) · description · quantity · estimated_value
  seized_from (FK persons, nullable) · seizure_datetime · seizure_location
  item_hash (nullable) · created_at

evidence
  id (PK) · case_id (FK) · type (enum: IMAGE | DOCUMENT | PHYSICAL)
  file_path · file_hash (sha256) · description · tags (JSONB)
  linked_person_id (FK persons, nullable) · collected_by (FK users)
  collected_at · chain_of_custody (JSONB)

statements
  id (PK) · case_id (FK) · person_id (FK) · statement_type (enum: WITNESS | ACCUSED | VICTIM)
  statement_text (text) · language · recorded_by (FK users) · recorded_at

legal_sections                 # AI-suggested, officer-confirmed
  id (PK) · case_id (FK) · act (enum: BNS | BNSS | BSA | IT_ACT | OTHER)
  section_code · section_title · reason · triggering_phrase        # explainability
  confidence (float) · ingredient_evidence_map (JSONB)             # ingredient -> evidence
  status (enum: SUGGESTED | ACCEPTED | REJECTED) · added_by · created_at

judgments
  id (PK) · case_id (FK) · title · citation · court · summary
  relevance_reason · source_url · added_by · created_at

documents
  id (PK) · case_id (FK) · doc_type (enum: PANCHNAMA | REMAND | SEIZURE_RECEIPT |
       MEDICAL_LETTER | CUSTODY_LETTER | FACE_ID | CHARGESHEET | LERS_REQUEST |
       LERS_PRESERVATION_REQUEST | LERS_RECORDS_REQUEST)
       # LERS_PRESERVATION_REQUEST + LERS_RECORDS_REQUEST were ADDED post-plan. Of the 10
       # enum values, only 6 have templates and are generatable (§8); the rest are enum-only stretch types.
  version (int) · file_path · generated_data (JSONB)               # the exact data merged in
  language · status (enum: DRAFT | FINALIZED)
  generated_by (FK users) · generated_at

document_versions              # version history / traceability requirement
  id (PK) · document_id (FK) · version (int) · snapshot (JSONB)
  edited_by (FK users) · edited_at

case_diary_entries
  id (PK) · case_id (FK) · entry_datetime · activity_type
       (enum: COMPLAINT | WITNESS_EXAM | EVIDENCE_SEIZURE | ARREST | REMAND | DOC_GENERATED | OTHER)
  description · related_person_id (nullable) · related_evidence_id (nullable)
  auto_generated (bool) · created_by (FK users) · created_at

audit_log                      # audit trail requirement — write on every create/update/delete
  id (PK) · case_id (FK, nullable) · entity_type · entity_id
  action (enum: CREATE | UPDATE | DELETE) · field_changes (JSONB)
  performed_by (FK users) · performed_at
```

**Rules:**
- Writing to `persons`, `seized_items`, `evidence`, `statements`, `legal_sections` = update the pool once; documents pull from it at generation time.
- Every mutating endpoint writes an `audit_log` row and (where relevant) a `case_diary_entry`.
- Document edits create a new `document_versions` snapshot — never overwrite silently.

---

## 6. THE `call_llm()` ABSTRACTION (every AI call goes through this)

Single choke point for all LLM use. Routes to Ollama by default, API fallback on failure, parses/validates JSON, retries once on bad JSON.

```python
# backend/app/ai/llm.py  (design contract)
def call_llm(
    prompt: str,
    system: str = "",
    json_schema: dict | None = None,   # if set, response MUST be valid JSON matching it
    temperature: float = 0.2,
    provider: str = "ollama",          # "ollama" | "api"  (fallback)
) -> dict | str:
    """
    1. Build request for the active provider.
       - ollama: POST {OLLAMA_HOST}/api/generate  model="qwen2.5:7b"
       - api:    fallback provider (only if OLLAMA down or FORCE_API set)
    2. If json_schema: append 'Return ONLY valid JSON matching this schema, no prose.'
    3. Parse JSON; on failure, retry once with a 'fix the JSON' reprompt.
    4. On provider error: if provider=='ollama', retry with provider='api'.
    5. Return parsed dict (json mode) or raw string.
    """
```

- Config via env: `OLLAMA_HOST` (e.g. `http://192.168.1.20:11434`), `LLM_MODEL=qwen2.5:7b`, `FALLBACK_API_KEY`, `FORCE_API=false`.
- **Demo safety:** a `DEMO_MODE` flag + a `demo_cache/` of pre-generated outputs so a live GPU stall never breaks the demo.

### Structured JSON prompts (build these as templates)

**A. Section mapping** (input: narrative + language)
```json
{ "sections": [ { "act": "BNS", "section_code": "318",
    "section_title": "...", "reason": "...", "triggering_phrase": "exact quote from narrative",
    "confidence": 0.0 } ],
  "cross_references": [ { "framework": "IPC", "provision": "420", "note": "..." } ] }
```

**B. Judgment suggestion** (input: narrative + accepted sections)
```json
{ "judgments": [ { "title": "...", "citation": "...", "court": "...",
    "summary": "<=2 sentences, paraphrased", "relevance_reason": "..." } ] }
```

**C. Weak-charge alert** (input: narrative + accepted sections)
```json
{ "alerts": [ { "section_code": "...", "missing_ingredients": ["..."],
    "explanation": "...", "suggestion": "..." } ] }
```

**D. Case-diary entry** (input: an action event) → returns `{ "activity_type": "...", "description": "one clear line" }`

**E. Consistency check** (input: field values gathered from all documents of a case)
```json
{ "inconsistencies": [ { "field": "accused_name", "values": {"panchnama":"...","remand":"..."},
    "severity": "high|low", "note": "..." } ] }
```

**F. Translation** — use IndicTrans2 or Ollama for GU/HI/EN; keep legal section names canonical (don't translate section codes).

> Keep judgment summaries short and paraphrased. Do not reproduce large blocks of copyrighted legal text; store citations + short paraphrases only.

---

## 7. API / SERVICE MAP

Transcribed verbatim from the routers (`backend/app/api/*.py`). All prefixed `/api`. All
except `/auth/login` and `/integrations/cctns/mock` require a valid JWT.

```
auth  (app/api/auth.py)
  POST  /auth/login                     -> { token, role, full_name }
  GET   /auth/me                        current user
  POST  /auth/register                  create officer account (SHO/admin only)

cases  (app/api/cases.py)
  POST  /cases                          create case from FIR (IO/SHO)
  GET   /cases                          list (IO sees own; SHO sees all)
  GET   /cases/search?q=                search case_number/title/narrative + person names/aliases
                                        + seized-item text -> [SearchHit{case, matched_field, matched_value}]
                                        with a context snippet — NOT [CaseOut]      # Search requirement
  GET   /cases/{id}                     full case (pool + statements + documents + diary_entries)
  PATCH /cases/{id}                     update status / fields (status change auto-writes a diary entry)

pool  (app/api/pool.py — the shared data; every mutation writes audit + a diary entry)
  POST/GET/PATCH/DELETE  /cases/{id}/persons[/{pid}]
  POST/GET/PATCH/DELETE  /cases/{id}/seized-items[/{sid}]
  POST/GET               /cases/{id}/statements            # POST + GET only (no PATCH/DELETE)
  POST                   /cases/{id}/evidence              multipart upload -> SHA-256 hash + tag
  GET                    /cases/{id}/evidence              list
  GET                    /cases/{id}/evidence/{eid}/file   serve the stored file (auth'd; JWT can't ride an <img src>)
  POST                   /cases/{id}/diary                 manual diary entry (auto entries written by the system;
                                                           the diary is READ via GET /cases/{id} — no standalone GET)
  POST                   /cases/{id}/transcribe            multipart audio -> {transcript, language, translation,
                                                           duration, confidence, model, audio_id}; dual-model:
                                                           gu-Whisper transcript + Qwen English narrative (§8/§15)

legal  (app/api/legal.py — AI, grounded)
  POST  /cases/{id}/analyze             run grounded section mapping, persist SUGGESTED rows (prompt A)
  GET   /cases/{id}/sections            list persisted sections for the case
  PATCH /cases/{id}/sections/{sid}      accept / reject a suggested section
  POST  /cases/{id}/judgments           suggest + persist landmark judgments (prompt B)
  GET   /cases/{id}/judgments           list persisted judgments
  GET   /cases/{id}/weak-charges        weak-charge alerts (prompt C) — GET, read-only, nothing persisted

documents  (app/api/documents.py)
  POST  /cases/{id}/documents/{doc_type}  generate a document (docxtpl); regen is version-aware (§8).
                                          LERS docs use doc_type=LERS_PRESERVATION_REQUEST | LERS_RECORDS_REQUEST
  GET   /cases/{id}/documents             list generated documents (current state)
  GET   /documents/{doc_id}/versions      version history: per-version metadata + diff vs previous
  GET   /documents/{doc_id}/download       .docx  (no PDF export)
  POST  /documents/{doc_id}/finalize      DRAFT -> FINALIZED (+ version snapshot); SHO only
  GET   /cases/{id}/consistency           cross-document consistency check — read-only, pure-DB, no LLM, no side effects

audit  (app/api/audit.py)
  GET   /cases/{id}/audit                 audit trail (paginated, newest first, optional entity_type filter,
                                          resolves performer name + role)

integrations  (app/api/integrations.py)
  POST  /cases/{id}/export/cctns          map case -> IIF (IIF-1 header + IIF-4 seizure block), POST to the mock
                                          receiver -> mock FIR id; persists audit_log + diary; returns
                                          {cctns_fir_id, mock_response, iif_payload}
  POST  /integrations/cctns/mock          mock CCTNS ingest receiver (UNauthenticated) -> mock FIR id
```

---

## 8. DOCUMENT GENERATION ENGINE

- Each doc type = one **Word template** in `/templates/` with `{{ jinja }}` placeholders (docxtpl).
- A **template registry** maps `doc_type -> template file + required fields`. Adding a document = drop a template + register it. **No code change.** (This is a Golden Hour seam — a freeze letter is just another template.)
- Generation flow: gather fields from the pool → build a context dict → render template → save file + `documents` row + `generated_data` JSONB + diary entry (`DOC_GENERATED`) + audit row.
- **Regeneration is version-aware** (§5/§8 "never overwrite silently"): if a document of that `doc_type` already exists on the case, its current state is archived to `document_versions` (full snapshot: status/language/timestamps + `generated_data`) and the **same** `documents` row is bumped to the next `version` as a fresh `DRAFT` — it does **not** insert a duplicate row. `finalize` likewise snapshots the draft, then flips status to `FINALIZED` and bumps the version. `GET /documents/{id}/versions` reconstructs the timeline from these snapshots plus the live row and diffs each version's `generated_data` against the previous.
- Free-text/narrative portions (e.g. panchnama description) are drafted via `call_llm()` then merged; officer edits before finalize.
- Support GU/HI/EN output — template picks language variant or translates the merged narrative.

**Field-mapping example (Seizure Receipt):** case_number, police_station, IO name (user), seized_items[] (description/qty/value/seized_from), accused person, seizure datetime/location, witnesses (persons role=WITNESS). All already in the pool.

**Registered document types** (`templates/_registry.py` — the `doc_type` used in `POST /cases/{id}/documents/{doc_type}`):
- `PANCHNAMA` — Accused Panchnama
- `REMAND` — Remand Request Letter (police custody)
- `SEIZURE_RECEIPT` — Property Seizure Receipt (CCTNS Form IF4 layout)
- `MEDICAL_LETTER` — Medical Treatment / Examination Letter
- `LERS_PRESERVATION_REQUEST` — LERS data-preservation request to a platform (Meta/WhatsApp/Instagram) — a compliant request template, **not** a live API integration
- `LERS_RECORDS_REQUEST` — LERS records-disclosure request to a platform — a compliant request template, **not** a live API integration

> Caveat to "no code change": because `doc_type` is a typed, native-enum column, adding a **new** document type needs a template + a registry entry **plus** one `DocType` enum value and a one-line `ALTER TYPE ... ADD VALUE` migration. The generation engine (`services/documents.py`), the endpoint, and the routers stay untouched.

---

## 9. AUTH & RBAC (JWT, 3 roles)

- Login returns a JWT (`sub`, `role`, exp). Middleware validates on every request.
- Role gates (keep simple — gate at the endpoint + hide UI):
  - **IO:** create/edit cases, pool data, generate documents, run AI, evidence upload.
  - **SHO:** everything IO can see (supervision) + case list across officers + finalize/approve.
  - **LEGAL_ADVISOR:** read case, focus on legal section mapping + judgments + weak-charge review; cannot alter evidence.
- Passwords hashed with bcrypt (`passlib`). Accounts created by an admin/seed script (no self-signup in demo).

---

## 10. GOLDEN HOUR SEAMS (build the seats, not the feature)

Three hooks so the cyber vertical plugs in later as config, not a rewrite:
1. `case_type` on `cases` (CONVENTIONAL | CYBER_FINANCIAL) — branch behavior off this.
2. **Template registry** — cyber docs (freeze letter) become just more templates.
3. **Pluggable workflow/SOP module** — a case loads its step list from a config; cyber loads Golden Hour steps + timers. Same interface, different config file.

Do not build Golden Hour logic now. Just make sure these three exist so it slots in at the end (or stays a roadmap line).

---

## 11. REPO / FOLDER STRUCTURE

Reconciled against the actual tree (only the load-bearing files shown).

```
crimegpt-copilot/
  CLAUDE.md  README.md  docker-compose.yml       <- postgres
  scripts/preflight.py                           <- cold-start check: postgres, alembic head, seed,
                                                    Chroma=1059 chunks, Ollama+qwen2.5:7b (§12/§15)
  fonts/                                          <- NotoSansGujarati-Regular.ttf (+ OFL) for .docx GU rendering
  docs/  user-guide.md  architecture.md
  data/                                           <- dataset deliverable (§13)
    bns_bnss_bsa/     BNS/BNSS/BSA .txt + *_sections.json (the RAG corpus source)
    judgments/        judgments.jsonl             <- curated citations + paraphrases
    audio/            A.mpeg B.mpeg + *_16k_mono.wav   <- real Gujarati demo recordings
    fir_samples/      (empty — pending from team)
    backfill_section_titles.py                    <- one-off data script
  templates/                                      <- 6 docx templates, one per generatable doc_type
    seizure_receipt.docx  panchnama.docx  remand_request.docx  medical_letter.docx
    lers_preservation_request.docx  lers_records_request.docx
    _registry.py   <- doc_type -> template + required_fields (import-free)   _build_templates.py
  backend/
    app/
      main.py                                     <- app + routers (auth, cases, legal, documents, pool, audit, integrations)
      core/        config.py (pydantic-settings), security (JWT/bcrypt), db session
      models/      SQLAlchemy models (= schema §5) + enums.py
      schemas/     Pydantic (case.py, …)
      api/         auth, cases, pool, legal, documents, audit, integrations   (diary + transcribe live in pool.py)
      ai/          llm.py (call_llm), prompts.py, rag.py (RAG loader + corpus ingest), legal.py,
                   judgments.py, weak_charge.py, translate.py (Qwen), transcribe.py (faster-whisper, CPU-only)
      services/    documents.py (generation + version-aware archive), consistency.py, cctns.py
      storage/     audio/  chroma/ (ChromaDB)  documents/  evidence/  whisper/ (downloaded models)
      demo_cache.py  demo_cache_build.py  demo_cache_reviewed.py   <- DEMO_MODE cache tooling
      seed.py                                     <- demo users + 2 demo cases
    demo_cache/    analysis/  documents/  transcripts/  reviewed_gu.json   <- pre-generated DEMO_MODE outputs
    alembic/       migrations       requirements.txt   .env / .env.example
  frontend/
    app/           login, dashboard, cases, cases/new, cases/[id] (tabs: details/evidence/sections/documents/diary),
                   analysis, audit                (Evidence & Documents are tabs, not standalone routes)
    components/     AppShell  AuthProvider  Sidebar  TopBar  CasePicker
    lib/            api.ts  cases.ts  i18n.ts (EN/HI/GU string table)
    public/fonts/   material-symbols-outlined.woff2 (self-hosted)
    tailwind.config.ts  package.json  (Next.js + React + TS + Tailwind + framer-motion)
```

---

## 12. ENVIRONMENT SETUP

**System (each dev machine):** Node.js 20+, Python 3.11+ (this repo has run on 3.13), Git. **Docker Desktop is REQUIRED** — Postgres runs inside it and there is no local fallback; the backend will not start without it. **GPU machine only:** Ollama.

```bash
# GPU machine — one time
ollama pull qwen2.5:7b
ollama pull nomic-embed-text            # embeddings for the legal RAG
#   serve on LAN:  set OLLAMA_HOST=0.0.0.0  then  ollama serve   (note the LAN IP)

# Database — Docker MUST be running first
docker compose up -d                    # starts postgres on :5432

# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate       # Windows
pip install -r requirements.txt
#   incl. fastapi uvicorn sqlalchemy alembic psycopg2-binary pydantic pydantic-settings
#         python-jose[cryptography] passlib[bcrypt] python-multipart docxtpl python-docx
#         chromadb sentence-transformers faster-whisper pillow requests
alembic upgrade head
python -m app.seed                      # demo users + 2 demo cases
python -m app.ai.rag                    # FRESH CLONE: build the Chroma RAG collection (~1,059 chunks)
python -m app.ai.judgments              # FRESH CLONE: build the judgments collection (41)
python -m uvicorn app.main:app --reload # NOTE: `python -m uvicorn`, NOT bare `uvicorn`
# → http://localhost:8000  (Swagger at /docs)

# Frontend
cd frontend && npm install && npm run dev   # http://localhost:3000

# One-shot preflight before a demo (verifies everything above, PASS/FAIL per dependency):
python scripts/preflight.py --fix

# .env (backend)
OLLAMA_HOST=http://<GPU-LAN-IP>:11434
LLM_MODEL=qwen2.5:7b
JWT_SECRET=<random>
DATABASE_URL=postgresql://crimegpt:crimegpt@localhost:5432/crimegpt
DEMO_MODE=false
WHISPER_MODEL=small                     # general faster-whisper model (also the English-translate fallback)
WHISPER_MODEL_GU=gujarati-medium-ct2    # Gujarati CT2 checkpoint under backend/app/storage/whisper/
```

**Gotchas we actually hit (do these or the stack breaks):**
- **`python -m uvicorn …`, never bare `uvicorn`** — the bare launcher fails to resolve the `app` package in this layout.
- **`USE_TF=0`** in the environment — `transformers` (pulled in by `sentence-transformers`) tries to import TensorFlow and errors/spams the console on load; `USE_TF=0` disables that path.
- **Docker up first** — no Postgres, no app.
- **Whisper stays on the CPU (int8).** Qwen owns the 8 GB GPU; a Whisper model sharing it risks an OOM kill mid-demo. `transcribe.py` pins `device="cpu"` and asserts it. Models are configured via `WHISPER_MODEL` (general) + `WHISPER_MODEL_GU` (Gujarati CT2 dir under `storage/whisper/`), not code.
- **Noto Sans Gujarati installed system-wide** is required for `.docx` generation to render Gujarati — Word/LibreOffice substitute tofu boxes otherwise. The TTF is checked in under `fonts/`.
- **Fresh clone:** run `python -m app.ai.rag` once, or `/analyze` returns nothing (the RAG collection is empty). `scripts/preflight.py` fails until the collection holds ~1,059 chunks.

**Team fallback:** non-GPU devs set `FORCE_API=true` with a `FALLBACK_API_KEY`, or point `OLLAMA_HOST` at the GPU machine's IP.

---

## 13. DATASET PLAN (deliverable #4)

- **Legal texts:** BNS, BNSS, BSA bare acts (public) — chunk + embed into ChromaDB for RAG.
- **Judgments:** ~20–30 relevant judgments from Indian Kanoon (public), stored as citation + short paraphrase.
- **FIR / document samples:** anonymized real formats (Panchnama, Remand, Seizure, Medical) — **pending from team**; these drive template accuracy.
- Keep everything in `/data/` with a short `data/README.md` describing sources + anonymization. Do not commit copyrighted full-text beyond public bare acts / public judgments.

---

## 14. FOUR-DAY BUILD PLAN (4 members)

**Roles:** A = Backend/Data lead · B = AI/Legal · C = Documents/Diary · D = Frontend.
(Suggested: Pavansinh=A, Sumit=B, Shiv=C, Gopesh=D — adjust to strengths.)

**Day 1 — Foundations (everything demoable ugly, not pretty)**
- A: repo scaffold, docker Postgres, SQLAlchemy models (§5), Alembic migration, `/auth` + JWT + seed users.
- B: Ollama + Qwen up and served on LAN; `call_llm()` working with JSON mode; embeddings + ChromaDB loaded with BNS/BNSS/BSA.
- C: template registry + first document (Seizure Receipt) rendering from hardcoded data via docxtpl.
- D: Next.js shell, login screen, case-creation form, case list. Wire to `/auth` + `/cases`.
- **End of day:** login works, a case can be created, one document renders.

**Day 2 — Core features**
- A: full pool endpoints (persons, seized_items, statements, evidence upload+hash), audit_log writing, case search.
- B: `/analyze` section mapping with explainability (triggering_phrase + confidence); `/judgments`.
- C: 4 documents generating from the real pool; case-diary auto-entries on key actions.
- D: case detail page (tabs: facts, persons, evidence, sections, documents, diary); document view + download.
- **End of day:** one case → 4 documents + AI sections + judgments, all from shared data.

**Day 3 — Differentiators + bonuses**
- A: RBAC role views (IO/SHO/Legal), search & audit UI endpoints, version history.
- B: consistency checker, weak-charge alerts (stretch), Gujarati output path.
- C: LERS templates, CCTNS mock export, face-capture on Face ID form (if time).
- D: Gujarati UI, evidence upload UI + tagging, consistency + explainability display.
- **End of day:** all committed bonuses working; Gujarati visible; differentiators demoable.

**Day 4 — Polish + demo + docs**
- All: integration pass, bug fixes, seed a clean demo case, **rehearse the demo twice**, pre-cache demo outputs (`DEMO_MODE`).
- D: the "fabulous frontend" pass — design, spacing, Gujarati polish.
- A/B/C: README + user guide + dataset README; record fallback demo video.
- **Lock scope at noon Day 4.** No new features after that.

---

## 15. DEMO SCRIPT (rehearse this exact flow)

Run `python scripts/preflight.py --fix` first — every line must say PASS. Set `DEMO_MODE=true`
so the heavy LLM/Whisper steps are served instantly from `demo_cache/` (see the **[cached]** /
**[live]** tags below) and a GPU stall can't break the demo.

**What DEMO_MODE caches vs runs live:**
- **[cached]** section analysis (`demo_cache/analysis/`), document generation (`demo_cache/documents/`,
  6 types × EN/HI/GU), and voice transcription (`demo_cache/transcripts/`, keyed by upload filename —
  the in-browser record button uploads `dictation.webm/.ogg/.wav`, which are pre-cached).
- **[live]** judgments and weak-charge alerts (always call Qwen), and the consistency check (pure-DB, no LLM — instant either way). Human-reviewed Gujarati strings in the cache are pinned in `demo_cache/reviewed_gu.json`.

1. Login as **IO**; toggle the UI to **ગુ** to show the whole interface in Gujarati (persists on reload).
2. **Create case from FIR** (or open the seeded case). On **Case details**, use **voice dictation**: record the complaint → **[cached]** Gujarati transcript + English translation appear side by side → officer clicks **Apply** to set the narrative (never auto-overwritten).
3. Add **persons** (accused, witnesses) + **evidence** (upload an image → auto SHA-256 + tag).
4. **Legal sections** tab → **Analyse** → **[cached]** grounded BNS/BNSS/BSA sections with the **highlighted triggering phrase** in the marked-up narrative + confidence. Accept a few. Suggest **judgments** **[live]**; run **weak-charge alerts** **[live]**.
5. **Documents** tab → generate **[cached]** Panchnama, Remand, Seizure Receipt, Medical Letter, and the two LERS templates — all pre-filled from the pool; download one `.docx`. Show **version history** (regen bumps the same row, §8).
6. **Case diary** tab — auto-built from the actions just taken.
7. **AI Analysis** page → **Consistency check** **[live, pure-DB]** → show it catches a deliberate stale value (e.g. rename the accused after a doc was generated).
8. Switch to **SHO** (supervision + finalize a document) and **Legal Advisor** (section focus).
9. **Global search** (top bar) — type a person/case → `SearchHit` with the matched field highlighted. Open **Audit** — the full trail with field-level old→new diffs.
10. **CCTNS mock export** → returns a mock FIR id ("deployment-ready").
11. Close on the one-liner + roadmap (Golden Hour / cyber vertical).

---

## 16. RISK / FALLBACKS

- **GPU stall in demo:** `DEMO_MODE=true` serves cached outputs; or `FORCE_API=true`. Rehearse both.
- **Model gives bad JSON:** `call_llm()` retries once, then falls back to a safe default + flags for manual entry.
- **Time crunch:** protect Tier 1 + the 4 documents + Gujarati + docs. Bonuses are droppable. Golden Hour stays roadmap.
- **Don't over-scope the frontend early** — ugly-but-working first, polish Day 4.

---

## 17. KNOWN LIMITATIONS (be honest in the deck & the Q&A)

These are real and worth stating plainly — the judges will find them anyway.

- **Weak-charge ingredient granularity is coarse.** On the 7B Qwen model the ingredient→evidence breakdown is high-level; it flags *that* a charge is under-supported, not a fine-grained per-ingredient proof map. Treat it as a prompt for the officer, not a legal conclusion.
- **Live Gujarati transcription is audio-dependent — DEMO_MODE is the demo path.** With clean, front-loaded audio the Gujarati transcript is complete and correct-script; on harder clips it can truncate the tail, and end-to-end latency is ~10–40 s on CPU. The demo runs the voice step from the reviewed `demo_cache/` (sub-second, deterministic). Live still works as an on-prem talking point.
- **The English narrative is Qwen-translated, and still needs review.** The narrative comes from LLM-translating the Gujarati transcript (Whisper's own translate task is a repetitive fallback). Qwen is coherent but can mistranslate spelled-out numbers/nouns — which is exactly why the UI shows both versions and requires the officer to **Apply** manually.
- **Judgment citations require human verification.** Judgments are grounded in a small curated corpus and paraphrased; a citation shown is a *suggestion to check on Indian Kanoon*, not a verified authority. Do not present them as confirmed law.
- **The CCTNS integration is a mock.** `/export/cctns` builds a real IIF payload and POSTs it to a local mock receiver that returns a fabricated FIR id. There is no live CCTNS/ICJS/BharatPol connection.
- **Golden Hour is seams only.** `case_type`, the template registry, and a pluggable-SOP intent exist (§10); no cyber-vertical workflow, timers, or money-trail logic is built.
- **Documents export as `.docx` only** (no PDF), and Gujarati rendering depends on Noto Sans Gujarati being installed on the machine that opens the file (§12).
- **Person/evidence deletes are guarded in the application layer, not the schema (roadmap).** The FKs that point at `persons` and `evidence` — `case_diary_entries.related_person_id` / `related_evidence_id`, `seized_items.seized_from`, `evidence.linked_person_id` — have no `ON DELETE` rule. `delete_person` / `delete_evidence` compensate by nulling those references (so the diary/item records survive) and returning a clean 409 when a person still has statements. The proper fix is a migration adding `ON DELETE SET NULL` (and `RESTRICT` for statements) so the DB is self-consistent regardless of code path; deferred to avoid a schema change close to the demo.

---

*End of CLAUDE.md. Keep this file current — it is the contract the whole team and Claude Code build against.*

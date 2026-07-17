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

**Tier 1 — Core (must work):** Unified Case Data Pool · Document Generation Engine (4 docs) · Case Diary Automation · Legal Section Intelligence (sections + judgments + IPC/CrPC/Evidence cross-refs) · Multilingual (Gujarati/Hindi/English) · Search & Audit (keyword/case-number search, version history, audit trail).

**Tier 2 — Signature differentiators:** Explainable section mapping (highlight triggering phrase + ingredient→evidence map) · Cross-document consistency checker · Auto-writing case diary · Weak-charge/missing-ingredient alerts (stretch) · BNSS/BSA compliance checker (stretch) · Gujarati voice-to-document (stretch).

**Tier 3 — Committed bonuses:** RBAC (3 roles) · Evidence image upload + tagging + auto-hash · LERS request templates (Meta/WhatsApp/Instagram — as compliant templates, not live API) · CCTNS/BharatPol mock API export.

**Tier 4 — Deck/roadmap only (do NOT build now):** Golden Hour cyber vertical · money-trail visualisation · offline-first PWA · live CCTNS/ICJS/eCourts integration.

---

## 5. DATABASE SCHEMA (the Unified Case Data Pool)

The whole product is "enter once, reuse everywhere." Every document reads from these tables — no field is ever typed twice. Use SQLAlchemy models + Alembic migrations.

```
users
  id (PK) · username (unique) · password_hash · full_name
  role (enum: IO | SHO | LEGAL_ADVISOR) · created_at

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
       MEDICAL_LETTER | CUSTODY_LETTER | FACE_ID | CHARGESHEET | LERS_REQUEST)
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

Group endpoints by module. All under `/api`. All (except `/auth/login`) require a valid JWT.

```
auth
  POST /auth/login                 -> { token, role, full_name }
  POST /auth/register              (admin only) create officer account
  GET  /auth/me

cases
  POST /cases                      create case from FIR (narrative + basics)
  GET  /cases                      list (filtered by role)
  GET  /cases/{id}                 full case (pool + docs + diary)
  PATCH /cases/{id}                update status / fields
  GET  /cases/search?q=            keyword / case-number search        # Search req.

pool  (the shared data)
  POST/GET/PATCH/DELETE /cases/{id}/persons
  POST/GET/PATCH/DELETE /cases/{id}/seized-items
  POST/GET/PATCH/DELETE /cases/{id}/statements
  POST /cases/{id}/evidence        (multipart upload -> hash + tag)    # Evidence bonus
  GET  /cases/{id}/evidence

legal  (AI)
  POST /cases/{id}/analyze         run section mapping (call_llm A)     # returns explainable sections
  POST /cases/{id}/judgments       suggest judgments (call_llm B)
  POST /cases/{id}/weak-charges    weak-charge alerts (call_llm C)     # stretch
  PATCH /cases/{id}/sections/{sid} accept/reject a suggested section

documents
  POST /cases/{id}/documents/{doc_type}   generate a document (docxtpl)
  GET  /cases/{id}/documents              list + versions
  GET  /documents/{id}/download           .docx (and/or .pdf)
  POST /documents/{id}/finalize           draft -> finalized (+ new version)
  POST /cases/{id}/consistency            cross-document consistency check  # differentiator

diary
  GET  /cases/{id}/diary                  chronological entries
  POST /cases/{id}/diary                  manual entry (auto entries created by system)

integrations
  POST /cases/{id}/export/cctns           map to IIF format -> mock endpoint -> mock FIR id  # bonus
  POST /cases/{id}/documents/lers         generate LERS request template                     # bonus

audit
  GET  /cases/{id}/audit                   audit trail for a case
```

---

## 8. DOCUMENT GENERATION ENGINE

- Each doc type = one **Word template** in `/templates/` with `{{ jinja }}` placeholders (docxtpl).
- A **template registry** maps `doc_type -> template file + required fields`. Adding a document = drop a template + register it. **No code change.** (This is a Golden Hour seam — a freeze letter is just another template.)
- Generation flow: gather fields from the pool → build a context dict → render template → save file + `documents` row + `generated_data` JSONB + diary entry (`DOC_GENERATED`) + audit row.
- Free-text/narrative portions (e.g. panchnama description) are drafted via `call_llm()` then merged; officer edits before finalize.
- Support GU/HI/EN output — template picks language variant or translates the merged narrative.

**Field-mapping example (Seizure Receipt):** case_number, police_station, IO name (user), seized_items[] (description/qty/value/seized_from), accused person, seizure datetime/location, witnesses (persons role=WITNESS). All already in the pool.

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

```
crimegpt-copilot/
  CLAUDE.md                      <- this file
  README.md
  docker-compose.yml             <- postgres (+ optional services)
  docs/
    user-guide.md
    architecture.md
  data/                          <- dataset deliverable
    bns_bnss_bsa/                <- bare act texts (anonymized/public)
    fir_samples/
    judgments/
  templates/                     <- docx templates (one per doc_type)
    panchnama.docx
    remand_request.docx
    seizure_receipt.docx
    medical_letter.docx
    _registry.py                 <- doc_type -> template + fields
  backend/
    app/
      main.py
      core/       (config, security/JWT, db session)
      models/     (SQLAlchemy models = the schema in §5)
      schemas/    (Pydantic)
      api/        (routers: auth, cases, pool, legal, documents, diary, integrations, audit)
      ai/         (llm.py = call_llm, prompts.py, rag.py, embeddings)
      services/   (doc generation, consistency, diary, audit, cctns_mock)
      storage/    (uploaded evidence, generated docs)
      seed.py     (demo users + a demo case)
    alembic/      (migrations)
    requirements.txt
    .env.example
  frontend/
    app/          (Next.js routes: login, cases, case/[id], documents, diary, admin)
    components/
    lib/api.ts
    package.json
```

---

## 12. ENVIRONMENT SETUP

**System (each dev machine):** Node.js 20+, Python 3.11+, Git. **Docker Desktop** for Postgres. **GPU machine only:** Ollama.

```bash
# GPU machine — one time
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
# serve on LAN so teammates can reach it:
#   set OLLAMA_HOST=0.0.0.0  then  ollama serve   (note the machine's LAN IP)

# Database
docker compose up -d            # starts postgres

# Backend
cd backend
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements.txt
#   requirements: fastapi uvicorn sqlalchemy alembic psycopg2-binary pydantic
#                 python-jose[cryptography] passlib[bcrypt] python-multipart
#                 docxtpl python-docx chromadb sentence-transformers pillow requests
alembic upgrade head
python -m app.seed              # create demo users + demo case
uvicorn app.main:app --reload   # http://localhost:8000  (Swagger at /docs)

# Frontend
cd frontend
npm install
npm run dev                     # http://localhost:3000

# .env (backend)
OLLAMA_HOST=http://<GPU-LAN-IP>:11434
LLM_MODEL=qwen2.5:7b
JWT_SECRET=<random>
DATABASE_URL=postgresql://crimegpt:crimegpt@localhost:5432/crimegpt
DEMO_MODE=false
```

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

1. Login as **IO** (Gujarati UI).
2. **Create case from FIR** — paste/dictate a complaint (show Gujarati input).
3. Add **persons** (accused, witnesses) + **evidence** (upload an image → auto-hash + tag).
4. Click **Analyze** → AI suggests **BNS/BNSS/BSA sections** with the **highlighted triggering phrase** + ingredient→evidence map; suggests **judgments**. Accept a few.
5. **Generate documents** in real time: Panchnama, Remand Request, Seizure Receipt, Medical Letter — all pre-filled from the pool. Download one.
6. Show the **case diary** auto-built from the actions just taken.
7. Run **consistency check** → show it catches a deliberate mismatch.
8. Switch to **SHO** view (supervision) and **Legal Advisor** view (section focus).
9. Show **search** (by case number) + **audit trail** + **version history**.
10. **CCTNS mock export** → returns mock FIR id ("deployment-ready").
11. Close on the one-liner + roadmap (Golden Hour / cyber vertical).

---

## 16. RISK / FALLBACKS

- **GPU stall in demo:** `DEMO_MODE=true` serves cached outputs; or `FORCE_API=true`. Rehearse both.
- **Model gives bad JSON:** `call_llm()` retries once, then falls back to a safe default + flags for manual entry.
- **Time crunch:** protect Tier 1 + the 4 documents + Gujarati + docs. Bonuses are droppable. Golden Hour stays roadmap.
- **Don't over-scope the frontend early** — ugly-but-working first, polish Day 4.

---

*End of CLAUDE.md. Keep this file current — it is the contract the whole team and Claude Code build against.*

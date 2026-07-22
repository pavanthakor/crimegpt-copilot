# CrimeGPT

**AI-powered automation for crime documentation and legal intelligence, built for Indian police.** CrimeGPT turns a single structured case entry into the source of truth for every required document, suggests grounded legal sections and case law, and maintains a digital case diary from FIR to arrest — on-premise, in the officer's own language.

It is a browser-based web application designed to run entirely on local hardware, so sensitive case data never leaves the station.

---

## Problem statement

Built for the **Kanad S.H.I.E.L.D. Hackathon 2026**, Category 2 — **PS-69EEFDFB90B99**:
*"CrimeGPT: AI-Powered Automation for Crime Documentation and Legal Intelligence."*
Proposed by the **Ahmedabad City Police, Cyber Crime Branch**.

Police documentation today is repetitive and error-prone: the same facts — names, sections, seized property — are re-typed across a dozen forms, legal sections are applied from memory, and consistency between documents is manual. CrimeGPT enters each fact **once** and reuses it everywhere, while the AI explains the law, flags weak charges, and keeps every document consistent.

---

## Key features

| Area | What it does |
|---|---|
| **Unified Case Data Pool** | Enter persons, seized items, evidence and statements once; every document reads from the same pool — no field is ever typed twice. |
| **Document generation (6 types)** | Panchnama · Remand Request · Seizure Receipt (CCTNS Form IF4 layout) · Medical Letter · LERS Preservation Request · LERS Records Request — all pre-filled from the pool, rendered as `.docx`, with version-aware regeneration and draft→finalize review. |
| **Grounded legal intelligence** | RAG over a 1,059-section BNS/BNSS/BSA corpus. Section mapping cites the **exact triggering phrase** from the narrative with a confidence score and old-law (IPC/CrPC) cross-reference; landmark-judgment suggestions and weak-charge / missing-ingredient alerts are grounded in a curated corpus, never free-generated. |
| **Case diary automation** | Key actions (case creation, statements, evidence, document generation, status changes, exports) auto-write timestamped diary entries, flagged system-vs-officer. |
| **Multilingual (EN / HI / GU)** | Full UI localisation persisted across reloads; drives the AI language parameter; documents render in all three languages. |
| **Search & audit** | Global search across cases, persons and seized items; a paginated audit trail with field-level old→new diffs, performer name and role; per-document version history. |
| **Evidence chain of custody** | Every upload is SHA-256 hashed on collection, tagged, and served over an authenticated endpoint (no public URLs). |
| **CCTNS export (mock)** | Maps a case to a CCTNS IIF payload (IIF-1 header + IIF-4 seizure block) and posts it to a local mock receiver that returns a mock FIR id — a deployment-ready export path, clearly labelled as a demonstration gateway. |

---

## Architecture

Six layers, top to bottom — the UI never talks to a model directly; every AI call goes through the `call_llm()` choke point in the AI layer.

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. PRESENTATION      Next.js · React · TypeScript · Tailwind       │
│    login · dashboard · case workspace (5 tabs) · analysis · audit  │
│    English / हिन्दी / ગુજરાતી, persisted per browser                │
└────────────────────────────────┬─────────────────────────────────┘
                                  │  HTTP + JWT (Bearer)
┌────────────────────────────────┴─────────────────────────────────┐
│ 2. API + AUTH        FastAPI routers · JWT · RBAC (IO/SHO/LEGAL)   │
│    /auth /cases /pool /legal /documents /audit /integrations       │
└────────────────────────────────┬─────────────────────────────────┘
                                  │
┌────────────────────────────────┴─────────────────────────────────┐
│ 3. SERVICES          document generation (docxtpl) · consistency   │
│    checker (pure-DB) · CCTNS IIF mapping                            │
└────────────────────────────────┬─────────────────────────────────┘
                                  │
┌────────────────────────────────┴─────────────────────────────────┐
│ 4. AI / INTELLIGENCE   call_llm() · RAG retrieval · section        │
│    mapping · judgments · weak-charge · transcribe · translate      │
└───────────────┬──────────────────────────────────┬───────────────┘
                │                                  │
┌───────────────┴────────────────┐   ┌─────────────┴────────────────┐
│ 5. DATA — Unified Case Pool     │   │ 6. LOCAL INFRA                │
│    SQLAlchemy → PostgreSQL 15   │   │    Ollama (Qwen 2.5 7B) · LAN │
│    12 tables · audit · diary    │   │    ChromaDB · Whisper (CPU)   │
│                                 │   │    filesystem storage         │
└─────────────────────────────────┘   └──────────────────────────────┘
```

Everything runs **inside the police network** — no case data leaves the station.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 14 · React 18 · TypeScript · Tailwind CSS | Fast to build, first-class TS, utility styling; framer-motion for the fan-out animations. |
| Backend | FastAPI · Python 3.11+ · Pydantic | Async, typed request/response models, auto OpenAPI docs at `/docs`. |
| ORM / migrations | SQLAlchemy · Alembic | Explicit schema and reversible migrations for a 12-table relational pool. |
| Database | PostgreSQL 15 (Docker) | JSONB for flexible snapshots (audit diffs, generated data) on a solid relational core. |
| Auth | JWT + bcrypt (python-jose, passlib) | Local, on-prem auth with three roles; no external identity provider. |
| LLM | Ollama running **Qwen 2.5 7B (Q4)** | Runs on a single RTX 4060 (8 GB) over the LAN; on-prem, no data egress. `call_llm()` falls back to an API provider if Ollama is down. |
| Embeddings | `sentence-transformers` (all-MiniLM-L6-v2, CPU) | Keeps the 8 GB GPU free for the LLM. |
| Vector DB | ChromaDB (local, file-based) | Zero-ops local RAG store for the legal corpus and judgments. |
| Doc generation | `docxtpl` + `python-docx` | Word templates with `{{ jinja }}` placeholders; drop a template + register it to add a document type. |
| Voice | `faster-whisper` (CPU, int8) | Gujarati voice-to-document; pinned to CPU so it can't OOM the GPU mid-demo. |
| Fonts | Noto Sans Gujarati | Correct Gujarati rendering in generated `.docx`. |

---

## Full setup from a clean clone

> Tested on Windows 11 (also runs on macOS/Linux — swap the venv activate path). Every command below maps to a file or module that exists in the repo.

### 0. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | to clone |
| **Docker Desktop** | any recent | **required** — Postgres runs inside it; there is no local DB fallback |
| Python | 3.11+ (runs on 3.13) | backend |
| Node.js | 20+ | frontend |
| Ollama | latest | **GPU machine only** — the box with the RTX 4060 |

### 1. Clone

```bash
git clone https://github.com/pavanthakor/crimegpt-copilot.git
cd crimegpt-copilot
```

### 2. Start Postgres (Docker must be running first)

```bash
docker compose up -d          # starts postgres:15 on localhost:5432
```

### 3. Backend virtual environment + dependencies

```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate       # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
```

Set `USE_TF=0` in your shell (see [Troubleshooting](#troubleshooting)):

```bash
export USE_TF=0                 # PowerShell:  $env:USE_TF = "0"
```

### 4. Environment file

```bash
cp .env.example .env            # Windows:  copy .env.example .env
```

Every variable (`backend/.env`):

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `postgresql://crimegpt:crimegpt@localhost:5432/crimegpt` | Postgres DSN — matches `docker-compose.yml`. **Required.** |
| `JWT_SECRET` | `change-me` | Signing secret for JWTs — **set a random value.** Required. |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama endpoint; point at the GPU box's LAN IP from other machines. |
| `LLM_MODEL` | `qwen2.5:7b` | Ollama model tag used by `call_llm()`. |
| `DEMO_MODE` | `false` | Serve pre-generated AI outputs from `demo_cache/` (see [DEMO_MODE](#demo_mode)). |
| `FORCE_API` | `false` | Skip Ollama and always use the API fallback provider. |
| `FALLBACK_API_KEY` | *(empty)* | API key for the fallback provider when `FORCE_API=true` or Ollama is down. |
| `WHISPER_MODEL` | `small` | General faster-whisper model (English narrative + non-Gujarati transcription). |
| `WHISPER_MODEL_GU` | `gujarati-medium-ct2` | Optional Gujarati CT2 model under `backend/app/storage/whisper/`; empty → falls back to `WHISPER_MODEL`. |

### 5. Database schema + demo data

```bash
alembic upgrade head            # apply migrations (12 tables)
python -m app.seed              # demo users + 2 demo cases
```

### 6. Build the RAG corpus (required before AI analysis works)

```bash
python -m app.ai.rag            # ingest BNS/BNSS/BSA -> ChromaDB (~1,059 sections)
python -m app.ai.judgments      # ingest landmark judgments -> ChromaDB (41)
```

> On a fresh clone this step is **mandatory** — without it `/analyze` returns nothing. Add `--reset` to wipe and re-ingest.

### 7. LLM (GPU machine only)

```bash
ollama pull qwen2.5:7b
ollama pull nomic-embed-text
# serve on the LAN:  set OLLAMA_HOST=0.0.0.0  then  ollama serve   (note the LAN IP)
```

Non-GPU teammates: set `FORCE_API=true` with a `FALLBACK_API_KEY`, or point `OLLAMA_HOST` at the GPU box.

### 8. Whisper model (voice-to-document)

- `WHISPER_MODEL=small` **auto-downloads** on first transcription into `backend/app/storage/whisper/` (HuggingFace cache).
- `WHISPER_MODEL_GU` is optional: drop a CTranslate2 Gujarati checkpoint directory under `backend/app/storage/whisper/` (e.g. `gujarati-medium-ct2`) for the higher-quality Gujarati display transcript. If absent, Gujarati falls back to `WHISPER_MODEL`.

### 9. Gujarati font (for `.docx` rendering)

Install `fonts/NotoSansGujarati-Regular.ttf` **system-wide** (SIL OFL, see `fonts/OFL.txt`):

```bash
# Windows (PowerShell, per-user — no admin):
Copy-Item fonts\NotoSansGujarati-Regular.ttf "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\"
# Linux:
mkdir -p ~/.local/share/fonts && cp fonts/NotoSansGujarati-Regular.ttf ~/.local/share/fonts/ && fc-cache -f
# macOS:
cp fonts/NotoSansGujarati-Regular.ttf ~/Library/Fonts/
```

Without it, Word/LibreOffice render Gujarati as empty boxes.

### 10. Frontend

```bash
cd ../frontend
npm install
npm run dev                     # http://localhost:3000
```

### 11. Preflight (recommended before a demo)

```bash
python scripts/preflight.py --fix    # PASS/FAIL per dependency: Postgres, Alembic head,
                                     # Chroma=1059, judgments=41, Ollama, fonts, single worker
```

---

## How to run

Three terminals:

```bash
# Terminal 1 — database (repo root)
docker compose up -d

# Terminal 2 — backend (from backend/, venv active, USE_TF=0)
python -m uvicorn app.main:app --reload      # -> http://localhost:8000  (Swagger at /docs)

# Terminal 3 — frontend (from frontend/)
npm run dev                                   # -> http://localhost:3000
```

> **Run exactly ONE uvicorn worker.** Use `python -m uvicorn app.main:app --reload` (single process) or `--workers 1` — **never** bare `uvicorn` (it fails to resolve the `app` package in this layout). The runtime DEMO_MODE toggle and the loaded Whisper/embedding models live in process memory, so multiple workers would not share state. If you see stale behaviour, check for an orphaned worker still bound to port 8000 (see Troubleshooting).

---

## Demo credentials

Created by `python -m app.seed`. Password format is `<username>123`.

| Username | Password | Role | Can do |
|---|---|---|---|
| `io` | `io123` | Investigating Officer | Create/edit cases, pool data, run AI, generate documents, upload evidence. Sees **only their own** cases. |
| `sho` | `sho123` | Station House Officer | Everything an IO can, across **all** officers' cases, **plus finalize documents** and the runtime DEMO_MODE toggle. |
| `legal` | `legal123` | Legal Advisor | Read cases; focus on legal sections, judgments and weak-charge review. **Cannot alter evidence** or export to CCTNS. |
| `io2` | `io2123` | Investigating Officer | Second IO, owns the vehicle-theft demo case (used to demonstrate case-visibility isolation). |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend won't start / `app` (or `chromadb`) not found | Use `python -m uvicorn app.main:app`, **never** bare `uvicorn` — the bare launcher can't reliably resolve the `app` package / the venv's interpreter in this layout. |
| TensorFlow / Keras import errors or console spam on startup | Set `USE_TF=0` in the environment. `transformers` (via `sentence-transformers`) otherwise tries to import TensorFlow. `app/ai/rag.py` sets it automatically at import; export it yourself for standalone scripts. |
| Stale DEMO_MODE / port 8000 "address in use" | An **orphaned uvicorn worker** is still bound to 8000. Kill it (`netstat -ano | findstr :8000` → `taskkill /PID <pid> /F` on Windows) and start one worker. |
| Backend errors about the database | **Docker must be running** and `docker compose up -d` must have started Postgres — there is no local DB fallback. |
| Generated `.docx` shows boxes instead of Gujarati | Install **Noto Sans Gujarati** system-wide on the machine that *opens* the file (`fonts/NotoSansGujarati-Regular.ttf`). |
| `/analyze` returns nothing on a fresh clone | Run `python -m app.ai.rag` once to build the Chroma corpus (~1,059 sections). `python scripts/preflight.py` fails until the collection is populated. |
| **Windows: frontend `EACCES` / `listen -4092` on port 3000** | Hyper-V/WSL reserved a port range that includes 3000. Free it by restarting WinNAT **as Administrator**: `net stop winnat` then `net start winnat`. (Or run `npm run dev -- -p 3005` on another port.) |

---

## DEMO_MODE

**What it is.** A safety switch that serves pre-generated AI outputs from `backend/demo_cache/` instead of calling the models live — so a GPU stall or slow first-token can never break a live demo, and the reviewed Gujarati strings stay deterministic.

**What it caches vs. runs live.** Cached: section analysis, document generation (6 types × EN/HI/GU) and voice transcription (keyed by upload filename). Live regardless: judgment suggestions, weak-charge alerts, and the consistency check (pure-DB). On a cache miss, the API discloses it (`cache_miss: true`) rather than silently going live.

**How to toggle.**
- Startup default: `DEMO_MODE` in `backend/.env`.
- At runtime (no restart): `PATCH /api/system/demo-mode` — **SHO only**, audit-logged — or the toggle in the top bar (visible to SHO only). The value lives in `app.core.runtime` and takes effect on the next request.

**Why it exists.** Live 7B inference on a single 8 GB GPU is fast but not instant; a demo cannot depend on it. DEMO_MODE makes the heavy steps sub-second and deterministic while the on-prem live path remains a genuine talking point.

---

## Project structure

```
crimegpt-copilot/
  CLAUDE.md               single source of truth for the build (architecture + decisions)
  README.md               this file
  docker-compose.yml      Postgres 15 service
  docs/                   architecture.md · user-guide.md
  data/                   dataset deliverable
    bns_bnss_bsa/         BNS/BNSS/BSA bare acts + parsed sections (RAG source)
    judgments/            curated judgments.jsonl + verification worksheet
    mappings/             new-law → IPC/CrPC cross-reference table
    fir_samples/          anonymised synthetic FIR/complaint samples
    audio/                real Gujarati demo recordings (raw + 16k mono)
  fonts/                  NotoSansGujarati-Regular.ttf (+ OFL licence)
  scripts/                preflight.py — cold-start dependency check
  templates/              6 .docx document templates + registry + label tables
  backend/
    alembic/              schema migrations
    app/
      api/                FastAPI routers (auth, cases, pool, legal, documents, audit, integrations, system)
      ai/                 call_llm, RAG, legal, judgments, weak_charge, transcribe, translate
      core/               config, DB session, security, runtime flags
      models/             SQLAlchemy models (the 12-table pool)
      schemas/            Pydantic request/response models
      services/           document generation, consistency checker, CCTNS mapping
      storage/            (gitignored) uploads, ChromaDB, Whisper models
      demo_cache/         pre-generated DEMO_MODE outputs
    requirements.txt
  frontend/
    app/                  routes: login, dashboard, cases, cases/new, cases/[id] (5 tabs), analysis, audit
    components/           AppShell, AuthProvider, Sidebar, TopBar, CasePicker
    lib/                  api client, case helpers, i18n string table (EN/HI/GU)
    public/fonts/         self-hosted icon font
```

---

## Documentation & data

- **[CLAUDE.md](CLAUDE.md)** — the technical foundation: locked decisions, database schema, API map, feature scope, demo script.
- **[docs/architecture.md](docs/architecture.md)** — system architecture in depth.
- **[docs/user-guide.md](docs/user-guide.md)** — officer-facing walkthrough.
- **[data/README.md](data/README.md)** — dataset overview and provenance.
- **[data/bns_bnss_bsa/README.md](data/bns_bnss_bsa/README.md)** — legal-corpus sources and parsing.
- **[data/fir_samples/README.md](data/fir_samples/README.md)** — synthetic-FIR anonymisation notice.
- **[data/judgments/VERIFICATION.md](data/judgments/VERIFICATION.md)** — judgment-corpus verification worksheet.

---

## Known limitations

Stated plainly — these are real and worth naming.

- **The legal corpus is BNS/BNSS/BSA only.** RAG covers the three 2023 codes (1,059 sections); IPC/CrPC cross-references are shown from a curated table, not corpus-grounded. There is no IT Act or special-law corpus.
- **CCTNS integration is a mock.** `/export/cctns` builds a real IIF payload and posts it to a **local mock receiver** that returns a fabricated FIR id. There is no live CCTNS/ICJS/BharatPol connection.
- **4 of the 7 named documents are implemented.** Accused Panchanama, Remand Request, Seizure Receipt and Medical Treatment Letter ship (plus 2 LERS request templates = 6 generatable types). Court Custody Letter, Purvani Chargesheet and the Accused Face Identification Form are enum placeholders without templates.
- **No PDF export.** Documents export as `.docx` only; Gujarati rendering depends on Noto Sans Gujarati being installed on the machine that opens the file.
- **Judgment citations require human verification.** Suggestions are grounded in a small curated corpus and paraphrased — a prompt to check on Indian Kanoon, not confirmed law.

---

*CrimeGPT — Team Skill Issue · Karnavati University · Kanad S.H.I.E.L.D. Hackathon 2026.*

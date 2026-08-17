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
| **Document generation (8 types)** | Seizure Receipt (CCTNS Form IF4 layout) · Panchnama · Remand Request · Court Custody Letter · Medical Letter · LERS Preservation Request · LERS Records Request · Final Form / Report (BNSS §193). All pre-filled from the pool, rendered as `.docx` in EN/HI/GU, with version-aware regeneration and draft to finalize review. No LLM runs in the document path, so generation is deterministic and takes under 0.12 s per document. |
| **Grounded legal intelligence** | RAG over a 1,059-section BNS/BNSS/BSA corpus. Section mapping cites the **exact triggering phrase** from the narrative plus an old-law (IPC/CrPC) cross-reference. A grounding validator drops any section outside the retrieved candidate set and any phrase not found verbatim in the narrative: **0 violations across 3 full evaluation runs**. Judgment suggestions and weak-charge alerts are grounded in a curated corpus, never free-generated. |
| **Conversational intake and chat** | Describe an incident in plain language and the system extracts the case, persons and seized items into a reviewable draft. Chat covers four capabilities: intake from narrative, document generation by request, missing-field prompting, and case queries. It returns labels from a closed set, never prose, so it cannot state law or offer an opinion. **Nothing is written until the officer confirms.** |
| **Mobile field capture (`/m`)** | Register a case from a phone on the station LAN. PIN sign-in, capture only (no document generation or chat reachable from it), writing into the same shared pool, visible on the desktop immediately. |
| **Security** | JWT with three roles (IO/SHO/Legal Advisor), server-side **step-up PIN** on case register and document finalize, idle auto-logout, SHA-256 evidence hashing, and an append-only audit trail with field-level old-to-new diffs. |
| **Case diary automation** | Key actions (case creation, statements, evidence, document generation, status changes, exports) auto-write timestamped diary entries, flagged system-vs-officer. |
| **Multilingual (EN / HI / GU)** | Full UI localisation persisted across reloads; drives the AI language parameter; documents render in all three languages. |
| **Search & audit** | Global search across cases, persons and seized items; a paginated audit trail with field-level old→new diffs, performer name and role; per-document version history. |
| **Evidence chain of custody** | Every upload is SHA-256 hashed on collection, tagged, and served over an authenticated endpoint (no public URLs). |
| **CCTNS export (mock)** | Maps a case to a CCTNS IIF payload (IIF-1 header + IIF-4 seizure block) and posts it to a local mock receiver that returns a mock FIR id — a deployment-ready export path, clearly labelled as a demonstration gateway. |

---

## Architecture

Five layers, top to bottom. The UI never talks to a model directly. Every AI call goes through the `call_llm()` choke point in L4.

```
┌──────────────────────────────────────────────────────────────────┐
│ L1. PRESENTATION     Next.js · React · TypeScript · Tailwind      │
│     login · dashboard · case workspace · conversational intake    │
│     mobile field page (/m) · analysis · audit                     │
│     English / हिन्दी / ગુજરાતી, persisted per browser              │
└────────────────────────────────┬─────────────────────────────────┘
                                 │  HTTP + JWT (Bearer)
┌────────────────────────────────┴─────────────────────────────────┐
│ L2. API + AUTH       FastAPI · JWT · RBAC (IO/SHO/LEGAL)          │
│     step-up PIN enforcement · idle auto-logout · 48 endpoints     │
│     /auth /cases /pool /legal /documents /intake /chat            │
│     /audit /integrations /system                                  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────┴─────────────────────────────────┐
│ L3. SERVICES         document generation (docxtpl, no LLM) ·      │
│     consistency checker (pure-DB) · CCTNS IIF mapping ·           │
│     audit + case-diary writes on every mutation                   │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────┴─────────────────────────────────┐
│ L4. AI + LEGAL CORE  call_llm() · RAG retrieval + query expansion │
│     grounding validator · section mapping · judgments ·           │
│     weak-charge · transcribe · translate                          │
│     Ollama (Qwen 2.5 7B Q4) on the station GPU, over the LAN      │
└────────────────────────────────┬─────────────────────────────────┘
                                 │
┌────────────────────────────────┴─────────────────────────────────┐
│ L5. DATA             PostgreSQL 15 (12-table Unified Case Pool)   │
│     ChromaDB (1,059 legal sections, embedded) ·                   │
│     local filesystem (generated .docx, evidence, Whisper models)   │
└──────────────────────────────────────────────────────────────────┘
```

Everything runs **inside the police network**. No case data leaves the station.

---

## Tech stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | Next.js 14 · React 18 · TypeScript · Tailwind CSS | Fast to build, first-class TS, utility styling; framer-motion for the fan-out animations. |
| Backend | FastAPI · **Python 3.13** · Pydantic | Async, typed request/response models, auto OpenAPI docs at `/docs`. 3.13 is a hard requirement: it is the interpreter that owns `docxtpl`, and a bare `uvicorn` on PATH often resolves to 3.11 without it, which breaks document generation. `setup.ps1` enforces this and recreates a 3.11 virtual environment. |
| ORM / migrations | SQLAlchemy · Alembic | Explicit schema and reversible migrations for a 12-table relational pool. |
| Database | PostgreSQL 15 (Docker) | JSONB for flexible snapshots (audit diffs, generated data) on a solid relational core. |
| Auth | JWT + bcrypt (python-jose, passlib) | Local, on-prem auth with three roles; no external identity provider. |
| LLM | Ollama running **Qwen 2.5 7B (Q4)** | Runs on a single RTX 4060 (8 GB) over the LAN; on-prem, no data egress. `call_llm()` falls back to an API provider if Ollama is down. |
| Embeddings | `sentence-transformers` (all-MiniLM-L6-v2, CPU) | Keeps the 8 GB GPU free for the LLM. |
| Vector DB | ChromaDB (local, file-based) | Zero-ops local RAG store for the legal corpus and judgments. |
| Doc generation | `docxtpl` + `python-docx` | Word templates with `{{ jinja }}` placeholders; drop a template + register it to add a document type. |
| Voice | `faster-whisper` (CPU, int8) | Gujarati voice-to-document; pinned to CPU so it can't OOM the GPU mid-demo. |
| Fonts | Noto Sans Gujarati (bundled) | Named by the generated `.docx`. Not required on Windows: Word substitutes Shruti, which ships with the OS. See the Gujarati note below. |

---

## Full setup from a clean clone

> **Preferred (demo laptop / fresh machine):** run the one-command setup, then prove it. See [SETUP.md](SETUP.md).
>
> ```powershell
> .\setup.ps1          # Windows. Run as Administrator to get the firewall rules.
> .\start.ps1          # start both servers
> .\verify.ps1         # prove the install (read-only)
> ```
> ```bash
> ./setup.sh && ./start.sh   # Linux/macOS
> ```
>
> `setup.ps1` forces **Python 3.13 + `python -m uvicorn`** (never bare `uvicorn`), pins the UI to port **3000**, seeds demo users and PINs, **builds the ChromaDB legal corpus**, **writes the LAN config for the mobile page** (`frontend/.env.local` and `CORS_EXTRA_ORIGINS`, without overwriting anything you already set), sets `OLLAMA_KEEP_ALIVE`, and adds inbound firewall rules for ports 3000 and 8000 when elevated. It is idempotent: existing configuration always wins over a clean install.
>
> `verify.ps1` then prints PASS or FAIL for the whole running stack, with a fix line for each failure. It is read-only unless you pass `-FullCheck`.
>
> The manual steps below remain valid and are what the script automates. Tested on Windows 11. **The clean-install path has not yet been executed start to finish on a fresh machine**, so treat it as written and reviewed rather than proven.

### 0. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Git | any recent | to clone |
| **Docker Desktop** | any recent | **required** — Postgres runs inside it; there is no local DB fallback |
| **Python** | **3.13 (required)** | Backend. This is the interpreter that owns `docxtpl`. A bare `uvicorn` can resolve to 3.11 without it and document generation fails. |
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

### 9. Gujarati font (optional on Windows)

The generated `.docx` names Noto Sans Gujarati but does not embed it. **On Windows this is not a problem and no action is needed.** Word substitutes Shruti, which ships with the operating system, and Gujarati renders correctly. This was verified by rendering a generated document to PDF: Word embedded a Shruti subset and the glyphs were well formed, while an Arial control produced the empty boxes that a genuine failure looks like. Nirmala UI, also a Windows font, covers Gujarati equally.

On Linux or macOS, where there is no guaranteed fallback, install the bundled font (SIL OFL, see `fonts/OFL.txt`):

```bash
# Linux:
mkdir -p ~/.local/share/fonts && cp fonts/NotoSansGujarati-Regular.ttf ~/.local/share/fonts/ && fc-cache -f
# macOS:
cp fonts/NotoSansGujarati-Regular.ttf ~/Library/Fonts/
# Windows (only if you want the exact designed typeface rather than the Shruti substitute):
Copy-Item fonts\NotoSansGujarati-Regular.ttf "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\"
```

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

Created by `python -m app.seed`. Password format is `<username>123`. Step-up PINs (see [SETUP.md](SETUP.md)):

| Username | Password | PIN | Role | Can do |
|---|---|---|---|---|
| `io` | `io123` | `1234` | Investigating Officer | Create/edit cases, pool data, run AI, generate documents, upload evidence. Sees **only their own** cases. |
| `sho` | `sho123` | `4321` | Station House Officer | Everything an IO can, across **all** officers' cases, **plus finalize documents** and the runtime DEMO_MODE toggle. |
| `legal` | `legal123` | `8765` | Legal Advisor | Read cases; focus on legal sections, judgments and weak-charge review. **Cannot alter evidence** or export to CCTNS. |
| `io2` | `io2123` | `5678` | Investigating Officer | Second IO, owns the vehicle-theft demo case (used to demonstrate case-visibility isolation). |

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Backend won't start / `app` (or `chromadb`) not found | Use `python -m uvicorn app.main:app`, **never** bare `uvicorn` — the bare launcher can't reliably resolve the `app` package / the venv's interpreter in this layout. |
| TensorFlow / Keras import errors or console spam on startup | Set `USE_TF=0` in the environment. `transformers` (via `sentence-transformers`) otherwise tries to import TensorFlow. `app/ai/rag.py` sets it automatically at import; export it yourself for standalone scripts. |
| Stale DEMO_MODE / port 8000 "address in use" | An **orphaned uvicorn worker** is still bound to 8000. Kill it (`netstat -ano | findstr :8000` → `taskkill /PID <pid> /F` on Windows) and start one worker. |
| Backend errors about the database | **Docker must be running** and `docker compose up -d` must have started Postgres — there is no local DB fallback. |
| Generated `.docx` shows boxes instead of Gujarati | Not expected on Windows, where Word substitutes Shruti. If it happens (Linux, macOS, or a machine with no Indic fonts), install `fonts/NotoSansGujarati-Regular.ttf` on the machine that *opens* the file. |
| `/analyze` returns nothing on a fresh clone | Run `python -m app.ai.rag` once to build the Chroma corpus (~1,059 sections). `python scripts/preflight.py` fails until the collection is populated. |
| **Windows: frontend `EACCES` / `listen -4092` on port 3000** | Hyper-V/WSL reserved a port range that includes 3000. Free it by restarting WinNAT **as Administrator**: `net stop winnat` then `net start winnat`. (Or run `npm run dev -- -p 3005` on another port.) |

---

## DEMO_MODE

**What it is.** A safety switch that serves pre-generated AI outputs from `backend/demo_cache/` instead of calling the models live — so a GPU stall or slow first-token can never break a live demo, and the reviewed Gujarati strings stay deterministic.

**What it caches vs. runs live.** Cached: section analysis, document generation (8 types × EN/HI/GU) and voice transcription (keyed by upload filename). Live regardless: judgment suggestions, weak-charge alerts, and the consistency check (pure-DB). On a cache miss, the API discloses it (`cache_miss: true`) rather than silently going live. The cache covers the seeded demo case only, so a case you register during a demo runs live.

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
  docs/                   technical.md · architecture.md · user-guide.md · health-check reports
  data/                   dataset deliverable
    bns_bnss_bsa/         BNS/BNSS/BSA bare acts + parsed sections (RAG source)
    judgments/            curated judgments.jsonl + verification worksheet
    mappings/             new-law → IPC/CrPC cross-reference table
    fir_samples/          anonymised synthetic FIR/complaint samples
    audio/                real Gujarati demo recordings (raw + 16k mono)
  fonts/                  NotoSansGujarati-Regular.ttf (+ OFL licence)
  scripts/                preflight.py — cold-start dependency check
                          section_eval.py — accuracy harness · verify_seed_counts.py
  setup.ps1 / setup.sh    one-command install
  start.ps1 / start.sh    start both servers
  verify.ps1              prove the running stack (PASS/FAIL)
  templates/              8 .docx document templates + registry + label tables
  backend/
    alembic/              schema migrations
    app/
      api/                FastAPI routers (auth, cases, pool, legal, documents, intake,
                          chat, audit, integrations, system) — 48 endpoints
      ai/                 call_llm, RAG, legal, judgments, weak_charge, transcribe, translate
      core/               config, DB session, security, runtime flags
      models/             SQLAlchemy models (the 12-table pool)
      schemas/            Pydantic request/response models
      services/           document generation, consistency checker, CCTNS mapping
      storage/            (gitignored) uploads, ChromaDB, Whisper models
      demo_cache/         pre-generated DEMO_MODE outputs
    requirements.txt
  frontend/
    app/                  routes: login, dashboard, cases, cases/new, cases/intake
                          (conversational), cases/[id] (5 tabs), m (mobile field page),
                          analysis, audit
    components/           AppShell, AuthProvider, Sidebar, TopBar, CasePicker
    lib/                  api client, case helpers, i18n string table (EN/HI/GU)
    public/fonts/         self-hosted icon font
```

---

## Documentation & data

- **[docs/technical.md](docs/technical.md)** — technical reference: the five layers, API surface, document engine, section-mapping flow, security model, **measured performance and accuracy**, and known limitations stated openly.
- **[docs/architecture.md](docs/architecture.md)** — system architecture and the section-analysis request flow in depth.
- **[docs/user-guide.md](docs/user-guide.md)** — officer-facing walkthrough.
- **[SETUP.md](SETUP.md)** — installation, LAN and mobile setup, and verification.
- **[CLAUDE.md](CLAUDE.md)** — the build's technical foundation: locked decisions, database schema, API map, feature scope, demo script.
- **Audit reports** — two read-only audits measuring commit `95665e8`, each carrying a status header that maps fixed findings to the commits that closed them: [round 1](docs/health-check-2026-08-17.md) (endpoint count, feature inventory over two independent runs, accuracy, timings, repository consistency) and [round 2](docs/health-check-round2-2026-08-17.md) (metric reconciliation, determinism, the slow-tail investigation, Gujarati rendering).
- **[data/README.md](data/README.md)** — dataset overview and provenance.
- **[data/bns_bnss_bsa/README.md](data/bns_bnss_bsa/README.md)** — legal-corpus sources and parsing.
- **[data/fir_samples/README.md](data/fir_samples/README.md)** — synthetic-FIR anonymisation notice.
- **[data/judgments/VERIFICATION.md](data/judgments/VERIFICATION.md)** — judgment-corpus verification worksheet.

---

## Measured performance and accuracy

Hardware: RTX 4060 (8 GB). 5-run medians, demo cache off, measured over `127.0.0.1`.

| Operation | Median |
|---|---|
| Intake extraction, 613-char bilingual Gujarati and English narrative | 14.1 s |
| Intake extraction, 384-char English narrative | 9.7 s |
| Section analysis, live | 7.8 s |
| Document generation, each of the eight | 89 ms |

Language dominates, not length: the Gujarati script costs far more tokens per character. Document generation is fast because no LLM runs in that path.

**Accuracy.** On our 21-case held-out test set, CrimeGPT puts the correct BNS section in front of the officer **58% of the time**, and the correct section is in the candidate list it chooses from **90% of the time**. Scope: 19 in-scope cases plus 2 out-of-scope, three runs, live `qwen2.5:7b`, demo cache off, BNS offence mapping only. Ground truth is in the repository at `data/eval/section_eval.json`.

**Guardrails**, re-verified independently of the application's own validator: **0 grounding violations** and **0 verbatim-quote violations** across three full runs. When nothing clears grounding the system returns `no_grounded_match` rather than inventing a section. We do not publish a refusal percentage, because the out-of-scope portion of the set is two cases and cannot support one.

Full method, per-case results and what was not tested: [docs/technical.md](docs/technical.md) and the audit reports.

---

## Known limitations

Stated plainly. These are real and worth naming. The full list, with measurements, is in [docs/technical.md](docs/technical.md).

- **Section selection is not deterministic.** No seed is set. The same complaint run ten times produced three distinct section sets. The officer accepts or rejects every section; the system proposes and does not decide.
- **Intake extraction has a slow tail.** About one call in twenty hits a JSON-repair retry. Median is 13.5 s, but the worst observed run took 137 s and then failed with a 422.
- **The system does not judge whether an input describes an offence.** It maps to grounded sections or returns `no_grounded_match`. That gate was built and reverted twice; a 7B model cannot make that call reliably on speech-act offences, and it errs toward charging rather than toward turning a complainant away.
- **The fresh-machine setup path has never been run start to finish.** It is written and reviewed, not proven.

- **The legal corpus is BNS/BNSS/BSA only.** RAG covers the three 2023 codes (1,059 sections); IPC/CrPC cross-references are shown from a curated table, not corpus-grounded. There is no IT Act or special-law corpus.
- **CCTNS integration is a mock.** `/export/cctns` builds a real IIF payload and posts it to a **local mock receiver** that returns a fabricated FIR id. There is no live CCTNS/ICJS/BharatPol connection.
- **One named document is not implemented.** All 8 generatable types ship (Seizure Receipt, Panchnama, Remand Request, Court Custody Letter, Medical Letter, LERS Preservation Request, LERS Records Request, Final Form / Report under BNSS §193). The Accused Face Identification Form remains an enum value with no template.
- **No PDF export.** Documents export as `.docx` only. On Windows this renders Gujarati correctly without extra fonts, because Word substitutes Shruti; on Linux or macOS with no Indic font installed it may not.
- **The evaluation set is small.** 21 cases, single annotator. At that size one case changing its mind moves the headline accuracy by about five points.
- **Judgment citations require human verification.** Suggestions are grounded in a small curated corpus and paraphrased — a prompt to check on Indian Kanoon, not confirmed law.

---

*CrimeGPT — Team Skill Issue · Karnavati University · Kanad S.H.I.E.L.D. Hackathon 2026.*

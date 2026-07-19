# CrimeGPT

**One case entry powers every document — and the AI doesn't just fill forms, it explains
the law, catches weak charges, and keeps every document consistent, in the officer's own
language.**

CrimeGPT is an on‑premise web application that automates crime documentation and legal
intelligence for Indian police. An officer enters a case once; that single, structured
record becomes the source of truth that generates every required document (FIR to arrest to
remand), suggests the applicable BNS/BNSS/BSA sections with the exact phrase that triggered
each one, keeps an automatic case diary, and exports to CCTNS — all running locally, with no
case data leaving the station.

---

## Problem statement

**Kanad S.H.I.E.L.D. Hackathon 2026 — Category 2, PS‑69EEFDFB90B99:**
*"CrimeGPT: AI‑Powered Automation for Crime Documentation and Legal Intelligence."*
Proposed by the **Ahmedabad City Police, Cyber Crime Branch.**

Police documentation today is repetitive and error‑prone: the same facts (names, dates,
seized items, sections) are typed by hand into many separate forms, and legal‑section
mapping depends on individual recall. CrimeGPT removes the re‑typing, grounds every legal
suggestion in the actual bare‑act text, and keeps the whole file internally consistent.

---

## Key features

**Core**
- **Unified Case Data Pool** — enter persons, evidence, seized items and statements once;
  every document reads from the pool. No field is ever typed twice.
- **Document generation (4 documents)** — Accused Panchnama, Police‑Custody Remand Request,
  Property Seizure Receipt (CCTNS **Form IF4** layout), and Medical Examination Letter, all
  merged from the pool into Word (`.docx`).
- **Legal Section Intelligence** — suggests BNS sections grounded in a real bare‑act corpus
  (1,059 sections), each with the **triggering phrase** quoted verbatim from the complaint,
  a confidence score, and a citation. Officer accepts or rejects each suggestion.
- **Automatic case diary** — key actions (registration, analysis, evidence, document
  generation, export) are logged to a chronological diary without extra typing.
- **Multilingual** — Gujarati / Hindi / English input and document output (legal codes stay
  canonical; only free‑text narrative is translated).
- **Search & audit** — search by case number, title, narrative, **person name** or
  **seized‑item description**; full audit trail and document version history.

**Differentiators**
- **Explainable section mapping** — highlights the phrase in the narrative that triggered
  each section.
- **Hallucination guard** — the AI can only choose from sections actually retrieved from the
  corpus; any invented section number or unsupported phrase is dropped and shown as rejected.
- **Cross‑document consistency checker** — flags stale documents and fields that disagree
  across documents (e.g. an accused renamed after a document was generated).

**Bonuses**
- **RBAC** — three roles (IO, SHO, Legal Advisor).
- **Evidence upload** — image/file upload with automatic SHA‑256 hashing + tagging.
- **CCTNS mock export** — maps a case to a CCTNS IIF payload (IIF‑1 header + IIF‑4 seizure
  block), posts it to a mock receiver, and returns a mock CCTNS FIR id.

See **[docs/user-guide.md](docs/user-guide.md)** for the officer walkthrough and
**[docs/architecture.md](docs/architecture.md)** for the technical design.

---

## Architecture (at a glance)

```
                         BROWSER (officer)
                    Next.js + React + Tailwind
                               │  HTTPS/JSON + JWT
                               ▼
        ┌───────────────────────────────────────────────┐
        │  API & AUTH   FastAPI routers · JWT · 3 roles  │
        │  auth · cases · pool · legal · documents ·     │
        │  audit · integrations                          │
        └───────────────────────────────────────────────┘
                               │
        ┌───────────────────────────────────────────────┐
        │  SERVICES   doc generation (docxtpl) ·         │
        │  consistency · CCTNS export · diary · audit    │
        └───────────────────────────────────────────────┘
                               │
        ┌───────────────────────────────────────────────┐
        │  AI & LEGAL   call_llm() ─▶ Ollama / Qwen2.5   │
        │  RAG over ChromaDB ─▶ grounding validator      │
        │  prompts · translation                         │
        └───────────────────────────────────────────────┘
                               │
        ┌───────────────────────────────────────────────┐
        │  DATA   PostgreSQL (unified pool, 12 tables) · │
        │  ChromaDB (1,059 legal sections) · file store  │
        └───────────────────────────────────────────────┘
                               │
        ┌───────────────────────────────────────────────┐
        │  INFRASTRUCTURE (ON‑PREM)   Docker · Ollama on │
        │  the station's RTX GPU · LAN · local disk      │
        └───────────────────────────────────────────────┘
```

Everything runs **inside the police network**. No case data is sent to any external cloud.

---

## Tech stack

| Layer      | Choice |
|------------|--------|
| Frontend   | Next.js · React · TypeScript · Tailwind CSS |
| Backend    | FastAPI · Python 3.11+ · SQLAlchemy · Pydantic |
| Database   | PostgreSQL 15 (Docker) |
| LLM        | Ollama running **Qwen 2.5 7B** (API fallback via `call_llm()`) |
| Embeddings | `sentence-transformers` `all-MiniLM-L6-v2` on CPU |
| Vector DB  | ChromaDB (local, file‑based) |
| Documents  | `docxtpl` + `python-docx` (Word templates) |
| Auth       | Local JWT, bcrypt, 3 roles |

---

## Setup from a clean clone

### Prerequisites
- **Python 3.11+**, **Git**, and **Docker Desktop** on every dev machine.
- **Node.js 20+** if you also run the frontend.
- **Ollama** on the machine with the GPU (only that machine needs it — teammates point
  `OLLAMA_HOST` at its LAN IP, or use the API fallback).

### 1. Clone
```bash
git clone <repo-url> crimegpt-copilot
cd crimegpt-copilot
```

### 2. LLM models (GPU machine, one time)
```bash
ollama pull qwen2.5:7b          # the analysis / drafting model  (required for AI features)
# Serve on the LAN so teammates can reach it:
#   Windows:  set OLLAMA_HOST=0.0.0.0 && ollama serve
#   Linux:    OLLAMA_HOST=0.0.0.0 ollama serve
# Note the machine's LAN IP for the .env below.
```
> The RAG **embeddings** use `all-MiniLM-L6-v2` (sentence-transformers, CPU) — downloaded
> automatically on the first `python -m app.ai.rag` run (needs internet that one time). It
> does **not** use Ollama, so the GPU stays free for Qwen.

### 3. Database (Postgres via Docker)
```bash
docker compose up -d            # starts PostgreSQL 15 on localhost:5432
```

### 4. Backend environment
```bash
cd backend
python -m venv .venv
. .venv/Scripts/activate        # Windows;  Linux/macOS:  source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env            # then edit: set OLLAMA_HOST (GPU LAN IP) and a real JWT_SECRET
```

### 5. Migrations, seed, and the legal RAG index
```bash
alembic upgrade head            # create the 12 tables
python -m app.seed              # demo users + one demo case
python -m app.ai.rag            # build the ChromaDB legal index (1,059 sections; idempotent)
```

### 6. Install the Gujarati font (for correct Gujarati documents)
See **[Fonts](#fonts--install-noto-sans-gujarati-on-the-demo-machine-required-for-gujarati-docs)**
below — install `fonts/NotoSansGujarati-Regular.ttf`.

### 7. Run the backend
```bash
python -m uvicorn app.main:app --reload    # http://localhost:8000  (Swagger UI at /docs)
```

### 8. Run the frontend (optional, separate terminal)
```bash
cd frontend
npm install
npm run dev                     # http://localhost:3000
```

### Demo credentials
Created by `python -m app.seed`:

| Role          | Username | Password   |
|---------------|----------|------------|
| IO            | `io`     | `io123`    |
| SHO           | `sho`    | `sho123`   |
| Legal Advisor | `legal`  | `legal123` |

The seed also creates one demo case (`I-CR-0142-2026`) with persons, seized items and a
statement so the app is demoable immediately.

---

## Setup notes

### Run the server with `python -m uvicorn` (not bare `uvicorn`)

Start the backend as `python -m uvicorn app.main:app`. The bare `uvicorn` launcher on
some machines binds to a different Python interpreter than the one where the AI deps
(`chromadb`, `sentence-transformers`) are installed, so importing the legal router fails
with `ModuleNotFoundError: No module named 'chromadb'`. Running via `python -m` guarantees
the same interpreter (and therefore the same installed packages) is used.

### `USE_TF=0` (required for the AI/embeddings layer)

The RAG layer uses `sentence-transformers`, which pulls in `transformers`. On machines
that have **Keras 3** installed, `transformers` fails to import with a TensorFlow/Keras
error. Set `USE_TF=0` to force the PyTorch backend and skip the TF import path:

```bash
# bash / Windows Git Bash
export USE_TF=0
# PowerShell
$env:USE_TF = "0"
```

`backend/app/ai/rag.py` sets this automatically at import time, so `python -m app.ai.rag`
works out of the box. Export it yourself only if you import `sentence-transformers` /
`transformers` directly in your own scripts.

### Fonts — install Noto Sans Gujarati on the demo machine (required for Gujarati docs)

The generated `.docx` documents pin **Noto Sans Gujarati** for all Gujarati/Devanagari
text (see `templates/_build_templates.py`). If that font is **not installed** on the
machine that opens the document, Word/LibreOffice substitutes the next face in the
documented fallback chain (`Nirmala UI` → `Shruti` → `Arial Unicode MS`); on a machine
that has none of these the Gujarati shows as box glyphs (□□□) even though the underlying
text is correct Unicode. Install the bundled font so every machine renders it identically.

The font (SIL Open Font License, see `fonts/OFL.txt`) is committed at
`fonts/NotoSansGujarati-Regular.ttf` so it can be installed anywhere:

```bash
# Windows (PowerShell, per-user — no admin needed)
Copy-Item fonts\NotoSansGujarati-Regular.ttf "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\"
# or double-click the .ttf and press "Install"

# Linux
mkdir -p ~/.local/share/fonts && cp fonts/NotoSansGujarati-Regular.ttf ~/.local/share/fonts/ && fc-cache -f

# macOS
cp fonts/NotoSansGujarati-Regular.ttf ~/Library/Fonts/
```

Regenerate the templates after any font/layout change with
`python templates/_build_templates.py`.

### Demo safety (`DEMO_MODE`)

Set `DEMO_MODE=true` in `backend/.env` to serve pre‑generated outputs from
`backend/demo_cache/` for the seeded case, so a live GPU stall never breaks a demo. A cache
miss falls through to the live pipeline.

---

## Documentation

| Doc | For | Contents |
|-----|-----|----------|
| **[docs/user-guide.md](docs/user-guide.md)** | Officers | Step‑by‑step, plain‑language walkthrough |
| **[docs/architecture.md](docs/architecture.md)** | Engineers | Layers, request flow, data model, security, on‑prem rationale |
| **[data/bns_bnss_bsa/README.md](data/bns_bnss_bsa/README.md)** | — | Legal corpus: sources, counts, schema, processing |
| **[CLAUDE.md](CLAUDE.md)** | — | Full technical foundation & decisions |

---

## Deliverables & dataset

- **Prototype** generating 4 required documents from one case entry.
- **Dataset** (`data/`): anonymised BNS/BNSS/BSA bare‑act corpus (1,059 sections), FIR and
  judgment samples. See `data/bns_bnss_bsa/README.md`.

**Team "Skill Issue"** — Thakor Pavansinh, Sumit Kumar, Shiv Gamit, Gopesh Jha ·
Karnavati University.

*Legal texts are public bare acts; case data in the repo is anonymised/demo. Do not commit
real case information.*

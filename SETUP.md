# CrimeGPT — setup (one command → ready)

This document is the **working** machine recipe: what actually brings a fresh clone (or the demo laptop) to a runnable state without tribal knowledge.

Application code is unchanged by these scripts — they only install deps, start Postgres, migrate, pull models, and seed.

---

## Prerequisites (install yourself once)

| Tool | Why | Notes |
|------|-----|--------|
| **Docker Desktop** | Postgres | Must be **running** before setup. No local-DB fallback. |
| **Python 3.13+** | Backend + `docxtpl` | **Required.** Python 3.11 on PATH is not enough — bare `uvicorn` often targets 3.11 **without** `docxtpl` and document generation dies with `ModuleNotFoundError: docxtpl`. |
| **Node.js 20+** | Frontend | Includes `npm`. |
| **Ollama** | Local Qwen | Install from [ollama.com](https://ollama.com); the app must be running so `ollama list` works. |
| **Git** | Clone | Any recent. |

Optional but recommended for Gujarati `.docx`: install `fonts/NotoSansGujarati-Regular.ttf` system-wide (see README).

---

## One-command setup

From the **repo root** (after `git clone` / checkout):

**Windows (primary — demo laptop):**

```powershell
.\setup.ps1
```

If execution policy blocks scripts:

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
# or:
powershell -ExecutionPolicy Bypass -File .\setup.ps1
```

**Linux / macOS:**

```bash
chmod +x setup.sh start.sh
./setup.sh
```

### What the script does

1. **Prerequisite check** — Docker (engine up), Ollama, Python **3.13+**, Node/npm. Fails with a clear install hint if anything is missing.
2. **Python deps** — creates/reuses `backend/.venv` on that 3.13+ interpreter, `pip install -r requirements.txt`, then **verifies** `import docxtpl` and `import fastapi`.
3. **Node deps** — `npm install` in `frontend/`.
4. **Postgres** — `docker compose up -d`, waits on `pg_isready`.
5. **Migrations** — `python -m alembic upgrade head`, confirms `(head)`.
6. **Ollama models** — ensures `qwen2.5:7b` and `nomic-embed-text` (pulls if missing).
7. **Seed** — `python -m app.seed` (**idempotent**, never `--reset` — will not wipe your DB). Verifies ≥4 users and ≥2 cases.
8. **READY summary** — prints start commands, URLs, demo logins/PINs. **Does not** start servers (avoids orphaned processes on a demo machine).

Also copies `backend/.env.example` → `backend/.env` if `.env` is missing.

Re-running setup on a machine that already works is safe: deps install is incremental, seed upserts users/PINs/stations, Postgres data volume is kept.

---

## Start the servers

Use **two terminals**, or the helper scripts.

### Option A — `start.ps1` / `start.sh`

```powershell
# Windows: opens backend + frontend in separate PowerShell windows
.\start.ps1

# LAN / phone (bind 0.0.0.0) — after you finished SETUP.md § Mobile
.\start.ps1 -Lan
```

```bash
# Linux/mac: backend in background, frontend in foreground
./start.sh
./start.sh --lan
./start.sh --backend-only   # one terminal
./start.sh --frontend-only
```

### Option B — exact commands (what you must remember)

**Terminal 1 — backend.** Always `python -m uvicorn` with the **venv** interpreter — never bare `uvicorn`:

```powershell
cd backend
$env:USE_TF = "0"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

```bash
cd backend
export USE_TF=0
./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — frontend.** Pin **port 3000** (an orphaned Next child can hold 3000 and the new process silent-falls to **3001**, which then 404s mysteriously):

```powershell
cd frontend
npm run dev -- -p 3000
```

```bash
cd frontend
npm run dev -- -p 3000
```

### URLs

| What | URL |
|------|-----|
| App | http://localhost:3000 |
| API / Swagger | http://127.0.0.1:8000/docs |
| Health | http://127.0.0.1:8000/health |

---

## Demo logins and PINs

Created by `python -m app.seed`. Password pattern: `<username>123`. Step-up PIN is asked once per session before high-stakes actions (register case, finalize document).

| Username | Password | PIN  | Role / station |
|----------|----------|------|----------------|
| `io`     | `io123`  | `1234` | IO · Satellite PS · main demo case `I-CR-0142-2026` |
| `io2`    | `io2123` | `5678` | IO · Ellisbridge PS · second case (RBAC isolation) |
| `sho`    | `sho123` | `4321` | SHO · all cases + finalize + DEMO_MODE toggle |
| `legal`  | `legal123` | `8765` | Legal advisor · read / review |

Wrong PIN blocks the action and writes nothing. Correct PIN then allows the write.

---

## Mobile / LAN field page (manual — gitignored env)

The phone load of `/m` (or the desktop UI over LAN) **cannot** rely on `localhost` — on the phone that means the phone itself. `.env.local` is **gitignored**, so a fresh clone never gets LAN config until you add it.

### 1. Find this PC’s LAN IP

```powershell
ipconfig
# look for IPv4 under your Wi‑Fi / Ethernet adapter, e.g. 192.168.29.188
```

```bash
ip addr   # or: hostname -I
```

### 2. Create `frontend/.env.local` (manual)

```env
# LAN access — phone loads the UI from this PC's IP, so API must not be localhost.
NEXT_PUBLIC_API_URL=http://YOUR_LAN_IP:8000
```

Example: `NEXT_PUBLIC_API_URL=http://192.168.29.188:8000`

Restart `npm run dev` after creating or changing this file.  
**Desktop-only:** delete or rename `.env.local` and the app falls back to `http://localhost:8000`.

### 3. CORS origin on the backend

When the mobile-field CORS wiring is present (`CORS_EXTRA_ORIGINS` in settings / `main.py`), add to **`backend/.env`** (also gitignored if you keep secrets there — same idea: local only):

```env
CORS_EXTRA_ORIGINS=http://YOUR_LAN_IP:3000
```

Without that extra origin, the browser on the phone will block API calls (origin is the LAN IP, not `localhost`). Restart uvicorn after changing `.env`.

> On branches where `CORS_EXTRA_ORIGINS` is not yet wired into `main.py`, LAN `/m` will need that merge (or an equivalent CORS allow-list) before phone calls succeed. Localhost desktop login does not need it.

### 4. Bind `0.0.0.0` (not only 127.0.0.1)

```powershell
.\start.ps1 -Lan
# or manually:
#   python -m uvicorn ... --host 0.0.0.0 --port 8000
#   npm run dev -- -H 0.0.0.0 -p 3000
```

### 5. Windows Firewall (Administrator PowerShell — you run this)

```powershell
New-NetFirewallRule -DisplayName "CrimeGPT frontend 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
New-NetFirewallRule -DisplayName "CrimeGPT backend 8000"  -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

Keep this **LAN-only**. Do not expose port 8000 beyond the station network. HTTP carries PINs/JWTs in clear text on the LAN.

Phone URL example: `http://YOUR_LAN_IP:3000/m`

---

## Tribal knowledge baked into the scripts

| Trap | What the scripts force instead |
|------|--------------------------------|
| Bare `uvicorn` → Python 3.11 without `docxtpl` | `backend\.venv\Scripts\python.exe -m uvicorn` (3.13+) + import check |
| Next.js silent fall-through to **:3001** | `npm run dev -- -p 3000` |
| Docker installed but engine off | `docker info` before compose |
| Seed wipe on every setup | `python -m app.seed` only — **never** `--reset` |
| Missing `backend/.env` | Copy from `.env.example` once |
| TensorFlow noise from transformers | `USE_TF=0` in start helpers |
| Postgres “up” but not accepting connections yet | wait on `pg_isready` |

---

## After setup — optional (legal RAG)

Document generation and chat work without this. **Section analysis** (`/analyze`) needs the Chroma corpus once:

```powershell
cd backend
$env:USE_TF = "0"
.\.venv\Scripts\python.exe -m app.ai.rag
.\.venv\Scripts\python.exe -m app.ai.judgments
```

Pre-demo check: `python scripts/preflight.py` (from repo conventions in README).

---

## Related

- Broader product / architecture notes: [README.md](README.md), [CLAUDE.md](CLAUDE.md)
- Scripts: `setup.ps1` · `setup.sh` · `start.ps1` · `start.sh`

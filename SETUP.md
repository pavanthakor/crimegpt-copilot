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
7b. **Gujarati rendering** — checks for **any** Gujarati-capable font. On Windows, Nirmala UI and Shruti ship with the OS and Word substitutes one automatically, so this is normally a PASS even without Noto Sans Gujarati installed.
8. **LAN config for `/m`** — detects the LAN IPv4, writes `frontend/.env.local` (`NEXT_PUBLIC_API_URL`) and adds `CORS_EXTRA_ORIGINS` to `backend/.env`. **Additive only** — an existing file is read and reported, never overwritten.
9. **Legal RAG corpus** — `python -m app.ai.rag` + `python -m app.ai.judgments`. Idempotent (no-op when already populated); a cold build embeds 1,059 sections on CPU in **~2 minutes**, once. Without this `/analyze` returns nothing.
10. **Runtime tuning** — sets `OLLAMA_KEEP_ALIVE=24h` and creates inbound firewall rules for 3000/8000 (see caveats below).
11. **Dependency verification** — runs `scripts/preflight.py --no-start` (read-only, no `--fix`): Postgres, Alembic head, seed, **Chroma = 1,059**, judgments = 41, Ollama + `qwen2.5:7b`.
12. **READY summary** — prints start commands, URLs, demo logins/PINs, the **resolved `DEMO_MODE` value and what it changes**, and any required manual steps. **Does not** start servers (avoids orphaned processes on a demo machine).

Also copies `backend/.env.example` → `backend/.env` if `.env` is missing.

Re-running setup on a machine that already works is safe: deps install is incremental, seed upserts users/PINs/stations, Postgres data volume is kept, the RAG ingest is a no-op, and **existing `.env` / `.env.local` values always win**.

### Two caveats on step 10

**`OLLAMA_KEEP_ALIVE=24h` is set at USER scope, and you must restart Ollama.** It applies to every Ollama use on your account, not just CrimeGPT. The Ollama **server reads it at startup**, so setting it does nothing until you **quit Ollama from the system tray and reopen it** — `setup.ps1` says so in a banner at the moment it sets the variable, and repeats it as a required manual step. Without it the model is evicted after 5 idle minutes and the next call pays a **~6.9 s reload**, which is exactly what a pause mid-demo costs you. `verify.ps1` will keep reporting FAIL until Ollama is restarted, because it checks the live deadline rather than the variable.

> There is a **project-scoped** alternative that needs no restart and no machine-wide variable: send `"keep_alive": "24h"` in the Ollama request body from `_ollama_generate` in `backend/app/ai/llm.py`. Verified to work (sets `expires_at` 24 h out immediately, affecting only CrimeGPT's own calls). Not implemented — it is a code change to the LLM path, deliberately out of scope for the setup scripts.

**Firewall rules need elevation.** The script creates **port** rules for 3000 and 8000. If you are not running as Administrator it creates nothing and prints the exact commands to paste into an admin shell instead. Port rules are deliberate: Windows' own "Allow access" prompt creates invisible *program* rules for `node.exe`/`python.exe`, and if `python.exe` is denied while `node.exe` is allowed you get the signature symptom — **`/m` loads on the phone but sign-in hangs**, because port 8000 is blocked.

---

## Prove it works — `verify.ps1`

`setup.ps1` installs; `verify.ps1` proves. It is standalone and re-runnable any time the servers are up — run it before every demo.

```powershell
.\start.ps1          # or .\start.ps1 -Lan for phone access
.\verify.ps1
```

**It is read-only by default.** A plain `.\verify.ps1` changes nothing in the database.

| Flag | Effect |
|---|---|
| *(none)* | **Read-only.** Skips the two checks that write. Safe to run before every demo. |
| `-FullCheck` | Opt in to the writing checks: generates a document, and probes the step-up gate (a refusal writes one `auth.step_up` audit row). |
| `-CaseId <n>` | Case used by `-FullCheck`'s document generation. Default **2**, deliberately not the case-1 demo case. |

> **Version-history baseline.** `-FullCheck` bumps a real document version, and version history is demo material. As of 18 Aug 2026 the document it targets — case **2** (`I-CR-0199-2026`), `SEIZURE_RECEIPT`, document id **60** — is at **v6, DRAFT, with 5 archived versions**. That is where it started; each `-FullCheck` run adds one. Use a plain `.\verify.ps1` if you want that number to stay put.

It prints PASS/FAIL with a fix line for every failure, covering: `preflight.py` dependencies · backend on **127.0.0.1** · frontend on 3000 · all 3 roles log in · `/m` and the API reachable on the LAN IP · the **live** model-eviction deadline · the resolved `DEMO_MODE` — plus, with `-FullCheck`, one document generated end to end and **commit without step-up returns 401** (the server-side gate from `495a34a`).

Three behaviours worth knowing:

- **The keep-alive check reads Ollama, not the environment variable.** `OLLAMA_KEEP_ALIVE` is read by the Ollama *server* at startup, so setting it changes nothing until Ollama restarts. A variable that is set but not in effect is **worse than one that is unset**, because it reads as PASS while the model still evicts. So `verify.ps1` queries `/api/ps` for the resident model's `expires_at` and reports the real deadline: ≥ 1 hour is a PASS, minutes is a FAIL that tells you to restart Ollama.

- **Everything is hit on `127.0.0.1`, never `localhost`.** On Windows `localhost` resolves to IPv6 `::1` first and uvicorn binds IPv4, so each *new* connection stalls **~2 s** before falling back. Measured and reproducible. Any timing taken through `localhost` measures the resolver, not the app.
- **It names the firewall specifically.** If a port answers on `127.0.0.1` but not on the LAN IP, the failure text says so in those words rather than making you guess.

A seed-count mismatch from `preflight.py` is downgraded to a **WARN** when `verify_seed_counts.py` still passes: preflight asserts the *pristine* seed baseline, so any machine that has registered real cases "fails" it, which is normal rather than broken.

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

## Mobile / LAN field page

> **Steps 1–3 below are now done for you by `setup.ps1` / `setup.sh`** (step 8): it detects the LAN IP, writes `frontend/.env.local`, and adds `CORS_EXTRA_ORIGINS` to `backend/.env` — without overwriting anything you already set. They are kept here as the reference for doing it by hand, or when detection picks the wrong adapter.
>
> **Step 5 (firewall) still needs you** unless you ran setup elevated, and **one step no script can do**: a handset holding a PIN token minted **before commit `495a34a`** has no `pin_login` claim and is refused at Register. **Sign out on the phone and sign back in with the PIN once — one tap, per device.**

The phone load of `/m` (or the desktop UI over LAN) **cannot** rely on `localhost` — on the phone that means the phone itself. `.env.local` is **gitignored**, so a fresh clone never gets LAN config until it is created.

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

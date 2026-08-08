#!/usr/bin/env bash
# One-command setup: fresh CrimeGPT clone -> runnable demo stack (Linux/macOS).
# Does NOT start the API/UI servers — use ./start.sh afterward.
#
# Critical: backend always uses Python 3.13+ via `python -m uvicorn`
# (never bare `uvicorn`, which can pick another interpreter without docxtpl).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_DIR="$BACKEND/.venv"
VENV_PY="$VENV_DIR/bin/python"

step() { printf '\n==> %s\n' "$1"; }
ok()   { printf '  OK  %s\n' "$1"; }
warn() { printf '  WARN  %s\n' "$1"; }
fail() { printf '\nSETUP FAILED: %s\nSee SETUP.md for prerequisites and fixes.\n' "$1" >&2; exit 1; }

# ---------------------------------------------------------------------------
# 1. Prerequisites
# ---------------------------------------------------------------------------
step "Checking prerequisites"

command -v docker >/dev/null 2>&1 || fail "Docker is not installed or not on PATH."
if ! docker info >/dev/null 2>&1; then
  fail "Docker is installed but the engine is not running. Start Docker and re-run."
fi
ok "Docker is running"

command -v ollama >/dev/null 2>&1 || fail "Ollama is not installed or not on PATH (https://ollama.com)."
if ! ollama list >/dev/null 2>&1; then
  fail "Ollama is installed but not responding. Start the Ollama service and re-run."
fi
ok "Ollama responds (ollama list)"

command -v node >/dev/null 2>&1 || fail "Node.js is not installed (need Node 20+)."
command -v npm  >/dev/null 2>&1 || fail "npm is not on PATH."
ok "Node.js $(node -v) / npm $(npm -v)"

# Python 3.13+
PY=""
for cand in python3.13 python3.14 python3; do
  if command -v "$cand" >/dev/null 2>&1; then
    ver="$("$cand" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
    maj="${ver%%.*}"
    min="${ver#*.}"
    if [[ "$maj" == "3" && "$min" -ge 13 ]]; then
      PY="$(command -v "$cand")"
      ok "Python $ver at $PY"
      break
    fi
  fi
done
if [[ -z "$PY" ]]; then
  fail "Python 3.13+ was not found (required for the docxtpl / document-generation path). Install python3.13 and re-run."
fi

# ---------------------------------------------------------------------------
# 2. Python deps
# ---------------------------------------------------------------------------
step "Python dependencies (venv on Python 3.13+)"
[[ -d "$BACKEND" ]] || fail "backend/ not found under $ROOT"

NEED_VENV=1
if [[ -x "$VENV_PY" ]]; then
  vver="$("$VENV_PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  vmaj="${vver%%.*}"; vmin="${vver#*.}"
  if [[ "$vmaj" == "3" && "$vmin" -ge 13 ]]; then
    NEED_VENV=0
    ok "Reusing backend/.venv ($vver)"
  else
    warn "backend/.venv is Python $vver (need 3.13+); recreating"
    rm -rf "$VENV_DIR"
  fi
fi
if [[ "$NEED_VENV" -eq 1 ]]; then
  echo "  Creating backend/.venv with $PY ..."
  "$PY" -m venv "$VENV_DIR"
  [[ -x "$VENV_PY" ]] || fail "Could not create backend/.venv"
  ok "Created backend/.venv"
fi

echo "  pip install -r requirements.txt ..."
"$VENV_PY" -m pip install --upgrade pip
# --break-system-packages is a no-op / harmless inside a venv; kept for system installs.
"$VENV_PY" -m pip install -r "$BACKEND/requirements.txt" --break-system-packages \
  || fail "pip install failed"

echo "  Verifying imports (docxtpl, fastapi) ..."
"$VENV_PY" -c "import docxtpl, fastapi; print('docxtpl ok'); print('fastapi', fastapi.__version__)" \
  || fail "docxtpl/fastapi import failed under the venv Python — document generation would break."
ok "docxtpl + fastapi importable under backend/.venv"

if [[ ! -f "$BACKEND/.env" ]]; then
  [[ -f "$BACKEND/.env.example" ]] || fail "backend/.env.example missing"
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  ok "Created backend/.env from .env.example (edit JWT_SECRET before production)"
else
  ok "backend/.env already present"
fi

export USE_TF=0

# ---------------------------------------------------------------------------
# 3. Node deps
# ---------------------------------------------------------------------------
step "Node dependencies (frontend/)"
( cd "$FRONTEND" && npm install ) || fail "npm install failed in frontend/"
ok "npm install complete"

# ---------------------------------------------------------------------------
# 4. Docker / Postgres
# ---------------------------------------------------------------------------
step "Postgres (docker compose up -d)"
( cd "$ROOT" && docker compose up -d ) || fail "docker compose up -d failed"

echo "  Waiting for Postgres to accept connections ..."
ready=0
for _ in $(seq 1 60); do
  if docker compose -f "$ROOT/docker-compose.yml" exec -T db pg_isready -U crimegpt -d crimegpt >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 2
done
[[ "$ready" -eq 1 ]] || fail "Postgres did not become ready within ~2 minutes. Check: docker compose ps"
ok "Postgres is ready (pg_isready)"

# ---------------------------------------------------------------------------
# 5. Migrations
# ---------------------------------------------------------------------------
step "Alembic migrations"
(
  cd "$BACKEND"
  "$VENV_PY" -m alembic upgrade head || fail "alembic upgrade head failed"
  current="$("$VENV_PY" -m alembic current 2>&1 || true)"
  printf '%s\n' "$current"
  echo "$current" | grep -q '(head)' || fail "Alembic is not at head after upgrade."
)
ok "alembic at head"

# ---------------------------------------------------------------------------
# 6. Ollama models
# ---------------------------------------------------------------------------
step "Ollama models (qwen2.5:7b, nomic-embed-text)"
list="$(ollama list 2>&1 || true)"
for model in qwen2.5:7b nomic-embed-text; do
  short="${model%%:*}"
  if printf '%s\n' "$list" | grep -E -q "^${model}\b|^${short}\b"; then
    ok "$model already present"
  else
    echo "  Pulling $model (may take several minutes) ..."
    ollama pull "$model" || fail "ollama pull $model failed"
    ok "Pulled $model"
  fi
done

# ---------------------------------------------------------------------------
# 7. Seed (idempotent — never --reset)
# ---------------------------------------------------------------------------
step "Demo seed (users + cases) - idempotent, no wipe"
(
  cd "$BACKEND"
  "$VENV_PY" -m app.seed || fail "python -m app.seed failed"
  if ! verify_out="$("$VENV_PY" "$ROOT/scripts/verify_seed_counts.py")"; then
    fail "Expected at least 4 seeded users and 2 cases. Got: $verify_out"
  fi
  printf '%s\n' "$verify_out"
)
ok "Seed verified (users >= 4, cases >= 2)"

FONT="$ROOT/fonts/NotoSansGujarati-Regular.ttf"
if [[ -f "$FONT" ]]; then
  if [[ ! -f "$HOME/.local/share/fonts/NotoSansGujarati-Regular.ttf" \
     && ! -f "$HOME/Library/Fonts/NotoSansGujarati-Regular.ttf" ]]; then
    warn "Noto Sans Gujarati is in fonts/ but may not be installed system-wide — see SETUP.md"
  fi
fi

# ---------------------------------------------------------------------------
# 8. READY
# ---------------------------------------------------------------------------
cat <<EOF

========================================
  CrimeGPT SETUP READY
========================================

Servers are NOT started (avoids orphaned processes). Use two terminals:

  Terminal 1 — backend (CRITICAL: python -m uvicorn, NOT bare uvicorn)
    cd "$BACKEND"
    export USE_TF=0
    ./.venv/bin/python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

  Terminal 2 — frontend (pin -p 3000 so Next does not silently fall to 3001)
    cd "$FRONTEND"
    npm run dev -- -p 3000

  Or from the repo root:  ./start.sh

URLs
  Frontend  http://localhost:3000
  API docs  http://127.0.0.1:8000/docs
  Health    http://127.0.0.1:8000/health

Demo logins (password = <username>123) + step-up PINs
  io      / io123      PIN 1234   (Satellite PS — main demo case)
  io2     / io2123     PIN 5678   (Ellisbridge PS — second case)
  sho     / sho123     PIN 4321   (all cases + finalize)
  legal   / legal123   PIN 8765   (read / legal review)

Mobile / LAN field page: see SETUP.md (gitignored .env.local is a MANUAL step).
Full notes: SETUP.md

EOF

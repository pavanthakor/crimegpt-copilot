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

# ---------------------------------------------------------------------------
# 7b. Gujarati rendering
#
# The old check warned whenever Noto Sans Gujarati was absent. On Windows that cries
# wolf: the .docx names Noto but embeds no font, and Word substitutes Shruti (ships with
# Windows) and renders correctly - verified by PDF render. Linux/macOS have no such
# guaranteed fallback, so check for ANY Gujarati-capable font before warning.
# ---------------------------------------------------------------------------
step "Gujarati rendering (.docx)"
if command -v fc-list >/dev/null 2>&1 && fc-list :lang=gu 2>/dev/null | grep -q .; then
  ok "A Gujarati-capable font is installed ($(fc-list :lang=gu 2>/dev/null | wc -l) face(s))"
elif [[ -f "$HOME/.local/share/fonts/NotoSansGujarati-Regular.ttf" \
     || -f "$HOME/Library/Fonts/NotoSansGujarati-Regular.ttf" ]]; then
  ok "Noto Sans Gujarati installed for this user"
else
  warn "No Gujarati-capable font detected. Install fonts/NotoSansGujarati-Regular.ttf or Gujarati .docx may show boxes."
fi

# ---------------------------------------------------------------------------
# 8. LAN config for the mobile field page (/m) - ADDITIVE ONLY.
# An existing .env.local is never rewritten. Without NEXT_PUBLIC_API_URL the phone
# calls "localhost", which is the phone itself.
# ---------------------------------------------------------------------------
step "LAN config for the mobile field page"
LAN_IP=""
if command -v ip >/dev/null 2>&1; then
  LAN_IP="$(ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}')"
fi
if [[ -z "$LAN_IP" ]] && command -v ipconfig >/dev/null 2>&1; then
  LAN_IP="$(ipconfig getifaddr en0 2>/dev/null || true)"
fi
if [[ -z "$LAN_IP" ]] && command -v hostname >/dev/null 2>&1; then
  LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
fi

ENV_LOCAL="$FRONTEND/.env.local"
if [[ -z "$LAN_IP" ]]; then
  warn "Could not detect a LAN IPv4. /m needs $ENV_LOCAL set by hand (SETUP.md)."
else
  ok "LAN IPv4 detected: $LAN_IP"
  if [[ -f "$ENV_LOCAL" ]]; then
    cur="$(grep -E '^[[:space:]]*NEXT_PUBLIC_API_URL[[:space:]]*=' "$ENV_LOCAL" | head -n1 || true)"
    if [[ -n "$cur" ]]; then
      ok "frontend/.env.local already sets ${cur} (kept as-is)"
      printf '%s' "$cur" | grep -q "$LAN_IP" || \
        warn "  ...but it does not match the detected LAN IP $LAN_IP - update by hand if the phone cannot reach the API."
    else
      printf 'NEXT_PUBLIC_API_URL=http://%s:8000\n' "$LAN_IP" >> "$ENV_LOCAL"
      ok "Appended NEXT_PUBLIC_API_URL to the existing frontend/.env.local"
    fi
  else
    {
      echo "# LAN access for the mobile field page (/m). Written by setup.sh."
      echo "# The phone loads the UI from this machine, so the API must not be 'localhost'."
      printf 'NEXT_PUBLIC_API_URL=http://%s:8000\n' "$LAN_IP"
    } > "$ENV_LOCAL"
    ok "Created frontend/.env.local -> http://$LAN_IP:8000"
  fi

  if grep -Eq '^[[:space:]]*CORS_EXTRA_ORIGINS[[:space:]]*=' "$BACKEND/.env"; then
    cur_cors="$(grep -E '^[[:space:]]*CORS_EXTRA_ORIGINS[[:space:]]*=' "$BACKEND/.env" | head -n1)"
    ok "backend/.env already sets ${cur_cors} (kept as-is)"
    printf '%s' "$cur_cors" | grep -q "$LAN_IP" || \
      warn "  ...but it does not include $LAN_IP - the phone browser will be blocked by CORS."
  else
    {
      echo ""
      echo "# Browser origin of the phone loading /m (added by setup.sh)."
      printf 'CORS_EXTRA_ORIGINS=http://%s:3000\n' "$LAN_IP"
    } >> "$BACKEND/.env"
    ok "Added CORS_EXTRA_ORIGINS=http://$LAN_IP:3000 to backend/.env"
  fi
fi

# ---------------------------------------------------------------------------
# 9. Legal RAG corpus (Chroma) - /analyze returns nothing without it.
# Both ingests are idempotent (no-op when already full). Cold build ~2 min.
# ---------------------------------------------------------------------------
step "Legal RAG corpus (Chroma) - idempotent, ~2 min on a cold machine"
(
  cd "$BACKEND"
  "$VENV_PY" -m app.ai.rag || fail "Chroma ingest failed (python -m app.ai.rag). /analyze would return nothing."
  "$VENV_PY" -m app.ai.judgments || fail "Judgments ingest failed. /judgments would 503."
)
ok "Chroma corpus + judgments collection ready"

# ---------------------------------------------------------------------------
# 10. Runtime tuning
#
# DRIFT FROM setup.ps1, stated plainly: the Windows script also SETS
# OLLAMA_KEEP_ALIVE at user scope and CREATES inbound firewall rules for 3000/8000.
# Neither is portable here - keep-alive belongs in the Ollama service unit / launchd
# plist, and the firewall is distro-specific (ufw / firewalld). Printed, not applied.
# ---------------------------------------------------------------------------
step "Runtime tuning (manual on this platform - see comment re: drift from setup.ps1)"
if [[ -n "${OLLAMA_KEEP_ALIVE:-}" ]]; then
  ok "OLLAMA_KEEP_ALIVE is set to '${OLLAMA_KEEP_ALIVE}'"
else
  warn "OLLAMA_KEEP_ALIVE unset - Ollama evicts the model after 5 idle minutes (~7s reload after a pause)."
  echo "       systemd:  Environment=\"OLLAMA_KEEP_ALIVE=24h\" in the ollama unit, then daemon-reload + restart"
  echo "       shell:    export OLLAMA_KEEP_ALIVE=24h  before 'ollama serve'"
fi
[[ -n "$LAN_IP" ]] && echo "       Firewall: allow inbound TCP 3000 and 8000 on the LAN if a phone cannot reach /m."

# ---------------------------------------------------------------------------
# 11. Dependency verification (no servers needed) - reuse scripts/preflight.py
# ---------------------------------------------------------------------------
step "Dependency verification (scripts/preflight.py, read-only)"
if "$VENV_PY" "$ROOT/scripts/preflight.py" --no-start; then
  ok "preflight: all dependency checks PASS"
else
  warn "preflight reported at least one FAIL (above). Setup finished, but fix those before the demo."
fi

DEMO_MODE_VAL="$(grep -E '^[[:space:]]*DEMO_MODE[[:space:]]*=' "$BACKEND/.env" | head -n1 | cut -d= -f2- | tr -d '[:space:]' || true)"
[[ -n "$DEMO_MODE_VAL" ]] || DEMO_MODE_VAL="(unset - defaults to false)"
PHONE_URL="see SETUP.md"
[[ -n "$LAN_IP" ]] && PHONE_URL="http://$LAN_IP:3000/m"

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

DEMO_MODE = $DEMO_MODE_VAL   (backend/.env)
  true  -> cached analysis + documents for seeded case 1 are served instantly;
           judgments and weak-charge alerts still call Qwen live.
  false -> everything runs live against Qwen. Honest default for a fresh install:
           the demo cache only covers seeded case 1, so a new machine has nothing
           to serve. Set DEMO_MODE=true in backend/.env for a cached demo of case 1.

Mobile field page (phone on the same Wi-Fi)
  Start with LAN binding:  ./start.sh --lan
  Phone URL:               $PHONE_URL

REQUIRED MANUAL STEP - phones already signed in
  A handset holding a PIN token minted before commit 495a34a has no pin_login claim
  and is refused at Register. Sign out on the phone and sign back in with the PIN
  once. One tap, per device.

NEXT: start the servers, then prove the install
  1.  ./start.sh            (or ./start.sh --lan for phone access)
  2.  pwsh ./verify.ps1     (PowerShell 7; the verifier is Windows-first - on Linux
                             use scripts/preflight.py plus a manual login check)

Full notes: SETUP.md

EOF

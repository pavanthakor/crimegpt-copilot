#!/usr/bin/env bash
# Start CrimeGPT backend and/or frontend after ./setup.sh.
# Uses backend/.venv/bin/python -m uvicorn (never bare uvicorn).
# Pins Next.js to port 3000.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"
VENV_PY="$BACKEND/.venv/bin/python"

BACKEND_ONLY=0
FRONTEND_ONLY=0
LAN=0
for arg in "$@"; do
  case "$arg" in
    --backend-only) BACKEND_ONLY=1 ;;
    --frontend-only) FRONTEND_ONLY=1 ;;
    --lan) LAN=1 ;;
    -h|--help)
      cat <<EOF
Usage: ./start.sh [--backend-only|--frontend-only] [--lan]
  --lan   bind 0.0.0.0 (phone / mobile field page; see SETUP.md)
EOF
      exit 0
      ;;
  esac
done

[[ -x "$VENV_PY" ]] || { echo "backend/.venv missing. Run ./setup.sh first." >&2; exit 1; }

HOST_BIND="127.0.0.1"
FRONT_HOST="127.0.0.1"
if [[ "$LAN" -eq 1 ]]; then
  HOST_BIND="0.0.0.0"
  FRONT_HOST="0.0.0.0"
  echo "LAN mode: bind 0.0.0.0 — also create frontend/.env.local and set CORS (SETUP.md)."
fi

echo "Remember: never use bare 'uvicorn' — it may pick an interpreter without docxtpl."

start_backend() {
  export USE_TF=0
  cd "$BACKEND"
  echo "CrimeGPT backend — python -m uvicorn on ${HOST_BIND}:8000"
  exec "$VENV_PY" -m uvicorn app.main:app --reload --host "$HOST_BIND" --port 8000
}

start_frontend() {
  cd "$FRONTEND"
  echo "CrimeGPT frontend — Next.js on ${FRONT_HOST}:3000 (pinned; not 3001)"
  exec npm run dev -- -H "$FRONT_HOST" -p 3000
}

if [[ "$BACKEND_ONLY" -eq 1 ]]; then
  start_backend
elif [[ "$FRONTEND_ONLY" -eq 1 ]]; then
  start_frontend
else
  # Two processes: backend in background, frontend in foreground (Ctrl+C stops frontend;
  # kill the backend job on exit).
  (
    export USE_TF=0
    cd "$BACKEND"
    "$VENV_PY" -m uvicorn app.main:app --reload --host "$HOST_BIND" --port 8000
  ) &
  BACK_PID=$!
  trap 'kill $BACK_PID 2>/dev/null || true' EXIT
  sleep 2
  start_frontend
fi

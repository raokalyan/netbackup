#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
mkdir -p "$ROOT/logs"

log() {
  printf '[%s] %s\n' "$(date '+%Y-%m-%d %H:%M:%S %Z')" "$*"
}

log "run_web.sh starting (root=$ROOT)"

if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  source .env
  set +a
  log "loaded .env"
else
  log "warning: .env not found at $ROOT/.env"
fi

PYTHON=""
if [ -d .venv ]; then
  # shellcheck disable=SC1091
  source .venv/bin/activate
  PYTHON="$(command -v python || true)"
  log "activated .venv (python=${PYTHON:-missing})"
fi

if [ -z "$PYTHON" ]; then
  PYTHON="$(command -v python3 || command -v python || true)"
fi

if [ -z "$PYTHON" ]; then
  log "error: python3/python not found in PATH=$PATH"
  exit 127
fi

WEB_HOST="${NETBACKUP_WEB_HOST:-0.0.0.0}"
WEB_PORT="${NETBACKUP_WEB_PORT:-8000}"

export PYTHONPATH="$ROOT/src"
log "starting web UI on ${WEB_HOST}:${WEB_PORT}"
exec "$PYTHON" -m uvicorn netbackup.web:app --host "$WEB_HOST" --port "$WEB_PORT"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${FIN_OPS_BACKEND_HOST:-127.0.0.1}"
PORT="${FIN_OPS_BACKEND_PORT:-8001}"
STORAGE_MODE="${FIN_OPS_STORAGE_MODE:-mongo_only}"

kill_port() {
  local port="$1"
  local pids
  pids="$(lsof -ti "tcp:${port}" || true)"
  if [[ -z "${pids}" ]]; then
    return
  fi

  kill ${pids} 2>/dev/null || true
  sleep 1

  pids="$(lsof -ti "tcp:${port}" || true)"
  if [[ -n "${pids}" ]]; then
    kill -9 ${pids} 2>/dev/null || true
  fi
}

kill_port "${PORT}"

cd "${ROOT_DIR}"
exec env PYTHONPATH="${ROOT_DIR}/backend/src" \
  FIN_OPS_STORAGE_MODE="${STORAGE_MODE}" \
  python3 -m fin_ops_platform.app.main --host "${HOST}" --port "${PORT}"

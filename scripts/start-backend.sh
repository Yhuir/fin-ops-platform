#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${FIN_OPS_BACKEND_HOST:-127.0.0.1}"
PORT="${FIN_OPS_BACKEND_PORT:-8001}"
STORAGE_MODE="${FIN_OPS_STORAGE_MODE:-mongo_only}"
DEV_ALLOW_LOCAL_SESSION="${FIN_OPS_DEV_ALLOW_LOCAL_SESSION:-}"
APP_MONGO_TIMEOUT_MS="${FIN_OPS_APP_MONGO_TIMEOUT_MS:-20000}"
OA_MONGO_TIMEOUT_MS="${FIN_OPS_OA_MONGO_TIMEOUT_MS:-20000}"

if [[ -z "${DEV_ALLOW_LOCAL_SESSION}" ]]; then
  if [[ -z "${FIN_OPS_OA_BASE_URL:-}" ]]; then
    DEV_ALLOW_LOCAL_SESSION="1"
  else
    DEV_ALLOW_LOCAL_SESSION="0"
  fi
fi

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
  FIN_OPS_DEV_ALLOW_LOCAL_SESSION="${DEV_ALLOW_LOCAL_SESSION}" \
  FIN_OPS_APP_MONGO_TIMEOUT_MS="${APP_MONGO_TIMEOUT_MS}" \
  FIN_OPS_OA_MONGO_TIMEOUT_MS="${OA_MONGO_TIMEOUT_MS}" \
  python3 -m fin_ops_platform.app.main --host "${HOST}" --port "${PORT}"

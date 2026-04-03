#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOST="${FIN_OPS_WEB_HOST:-127.0.0.1}"
PORT="${FIN_OPS_WEB_PORT:-4173}"

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

cd "${ROOT_DIR}/web"
exec npm run dev:raw -- --host "${HOST}" --port "${PORT}"

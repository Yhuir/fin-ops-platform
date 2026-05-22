#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND_ENV_FILE="${FIN_OPS_BACKEND_ENV_FILE:-${ROOT_DIR}/.runtime/fin_ops_platform/local-postgres.env}"

if [[ -f "${BACKEND_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${BACKEND_ENV_FILE}"
  set +a
fi

HOST="${FIN_OPS_BACKEND_HOST:-127.0.0.1}"
PORT="${FIN_OPS_BACKEND_PORT:-8001}"
PYTHON_BIN="${FIN_OPS_PYTHON_BIN:-python3}"
DATA_DIR="${FIN_OPS_DATA_DIR:-${ROOT_DIR}/.runtime/fin_ops_platform}"
DEV_ALLOW_LOCAL_SESSION="${FIN_OPS_DEV_ALLOW_LOCAL_SESSION:-}"
APP_MONGO_TIMEOUT_MS="${FIN_OPS_APP_MONGO_TIMEOUT_MS:-20000}"
OA_MONGO_TIMEOUT_MS="${FIN_OPS_OA_MONGO_TIMEOUT_MS:-20000}"
OA_BASE_URL="${FIN_OPS_OA_BASE_URL:-https://www.yn-sourcing.com/oa-api}"
ETC_OA_BASE_URL="${FIN_OPS_ETC_OA_BASE_URL:-${OA_BASE_URL}}"
ETC_OA_FILE_UPLOAD_PATH="${FIN_OPS_ETC_OA_FILE_UPLOAD_PATH:-/file/upload}"
ETC_OA_FORM_DRAFT_PATH="${FIN_OPS_ETC_OA_FORM_DRAFT_PATH:-}"
if [[ -z "${ETC_OA_FORM_DRAFT_PATH}" ]]; then
  ETC_OA_FORM_DRAFT_PATH='/forms/form/{form_id}/records/record'
fi
ETC_OA_DRAFT_URL_TEMPLATE="${FIN_OPS_ETC_OA_DRAFT_URL_TEMPLATE:-}"
if [[ -z "${ETC_OA_DRAFT_URL_TEMPLATE}" ]]; then
  ETC_OA_DRAFT_URL_TEMPLATE='https://www.yn-sourcing.com/oa/#/normal/forms/form/{form_id}?formId={form_id}&id={draft_id}'
fi
ETC_OA_REQUEST_TIMEOUT_MS="${FIN_OPS_ETC_OA_REQUEST_TIMEOUT_MS:-${FIN_OPS_OA_REQUEST_TIMEOUT_MS:-20000}}"
APP_STORAGE_BACKEND="${FIN_OPS_APP_STORAGE_BACKEND:-}"
APP_READ_BACKEND="${FIN_OPS_APP_READ_BACKEND:-}"
POSTGRES_CUTOVER_PHASE="${FIN_OPS_POSTGRES_CUTOVER_PHASE:-}"
STORAGE_MODE="${FIN_OPS_STORAGE_MODE:-mongo_only}"

if [[ -n "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}}" ]]; then
  APP_STORAGE_BACKEND="${APP_STORAGE_BACKEND:-postgres}"
  APP_READ_BACKEND="${APP_READ_BACKEND:-postgres}"
  POSTGRES_CUTOVER_PHASE="${POSTGRES_CUTOVER_PHASE:-postgres_primary}"
  STORAGE_MODE="${FIN_OPS_STORAGE_MODE:-postgres}"
fi

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

is_port_open() {
  local port="$1"
  lsof -ti "tcp:${port}" >/dev/null 2>&1
}

wait_for_port() {
  local port="$1"
  local label="$2"
  local attempts="${3:-20}"
  local i
  for ((i = 1; i <= attempts; i++)); do
    if is_port_open "${port}"; then
      return
    fi
    sleep 0.25
  done
  echo "ERROR: ${label} tunnel is not listening on localhost:${port}." >&2
  exit 1
}

ensure_ssh_tunnel() {
  local tunnel_host="${FIN_OPS_SSH_TUNNEL_HOST:-}"
  if [[ -z "${tunnel_host}" ]]; then
    return
  fi

  local tunnel_user="${FIN_OPS_SSH_TUNNEL_USER:-root}"
  local pg_local_port="${FIN_OPS_SSH_TUNNEL_PG_PORT:-15432}"
  local s3_local_port="${FIN_OPS_SSH_TUNNEL_S3_PORT:-19000}"
  local redis_local_port="${FIN_OPS_SSH_TUNNEL_REDIS_PORT:-}"
  local pg_remote="${FIN_OPS_SSH_TUNNEL_REMOTE_PG:-127.0.0.1:5432}"
  local s3_remote="${FIN_OPS_SSH_TUNNEL_REMOTE_S3:-127.0.0.1:9000}"
  local redis_remote="${FIN_OPS_SSH_TUNNEL_REMOTE_REDIS:-127.0.0.1:6379}"
  local tunnel_target="${tunnel_user}@${tunnel_host}"
  local identity_file="${FIN_OPS_SSH_IDENTITY_FILE:-}"
  local pg_open="0"
  local s3_open="0"
  local redis_open="1"
  local ssh_args=(
    -f
    -N
    -o ExitOnForwardFailure=yes
    -o ServerAliveInterval=30
    -o ServerAliveCountMax=3
  )
  if [[ -n "${identity_file}" ]]; then
    ssh_args+=(-i "${identity_file}" -o BatchMode=yes)
  fi

  if is_port_open "${pg_local_port}"; then
    pg_open="1"
  fi
  if is_port_open "${s3_local_port}"; then
    s3_open="1"
  fi
  if [[ -n "${redis_local_port}" ]]; then
    redis_open="0"
    if is_port_open "${redis_local_port}"; then
      redis_open="1"
    fi
  fi
  if [[ "${pg_open}" == "1" && "${s3_open}" == "1" && "${redis_open}" == "1" ]]; then
    return
  fi
  if [[ "${pg_open}" == "0" ]]; then
    ssh_args+=(-L "${pg_local_port}:${pg_remote}")
  fi
  if [[ "${s3_open}" == "0" ]]; then
    ssh_args+=(-L "${s3_local_port}:${s3_remote}")
  fi
  if [[ "${redis_open}" == "0" && -n "${redis_local_port}" ]]; then
    ssh_args+=(-L "${redis_local_port}:${redis_remote}")
  fi
  ssh_args+=("${tunnel_target}")

  echo "Starting missing SSH tunnel forwards for PostgreSQL localhost:${pg_local_port}, object storage localhost:${s3_local_port}, and Redis localhost:${redis_local_port:-disabled} via ${tunnel_target}..."
  ssh "${ssh_args[@]}"
  wait_for_port "${pg_local_port}" "PostgreSQL"
  wait_for_port "${s3_local_port}" "object storage"
  if [[ -n "${redis_local_port}" ]]; then
    wait_for_port "${redis_local_port}" "Redis"
  fi
}

ensure_ssh_tunnel

if [[ -n "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}}" && "${FIN_OPS_SKIP_LOCAL_RUNTIME_CHECK:-0}" != "1" ]]; then
  FIN_OPS_BACKEND_ENV_FILE="${BACKEND_ENV_FILE}" "${ROOT_DIR}/scripts/check-local-runtime.sh" --dependencies-only
fi

kill_port "${PORT}"

cd "${ROOT_DIR}"
ENV_ARGS=(
  PYTHONPATH="${ROOT_DIR}/backend/src"
  FIN_OPS_STORAGE_MODE="${STORAGE_MODE}"
  FIN_OPS_DATA_DIR="${DATA_DIR}"
  FIN_OPS_DEV_ALLOW_LOCAL_SESSION="${DEV_ALLOW_LOCAL_SESSION}"
  FIN_OPS_APP_MONGO_TIMEOUT_MS="${APP_MONGO_TIMEOUT_MS}"
  FIN_OPS_OA_MONGO_TIMEOUT_MS="${OA_MONGO_TIMEOUT_MS}"
  FIN_OPS_OA_BASE_URL="${OA_BASE_URL}"
  FIN_OPS_ETC_OA_BASE_URL="${ETC_OA_BASE_URL}"
  FIN_OPS_ETC_OA_FILE_UPLOAD_PATH="${ETC_OA_FILE_UPLOAD_PATH}"
  FIN_OPS_ETC_OA_FORM_DRAFT_PATH="${ETC_OA_FORM_DRAFT_PATH}"
  FIN_OPS_ETC_OA_DRAFT_URL_TEMPLATE="${ETC_OA_DRAFT_URL_TEMPLATE}"
  FIN_OPS_ETC_OA_REQUEST_TIMEOUT_MS="${ETC_OA_REQUEST_TIMEOUT_MS}"
)

if [[ -n "${APP_STORAGE_BACKEND}" ]]; then
  ENV_ARGS+=(FIN_OPS_APP_STORAGE_BACKEND="${APP_STORAGE_BACKEND}")
fi
if [[ -n "${APP_READ_BACKEND}" ]]; then
  ENV_ARGS+=(FIN_OPS_APP_READ_BACKEND="${APP_READ_BACKEND}")
fi
if [[ -n "${POSTGRES_CUTOVER_PHASE}" ]]; then
  ENV_ARGS+=(FIN_OPS_POSTGRES_CUTOVER_PHASE="${POSTGRES_CUTOVER_PHASE}")
fi
if [[ -n "${FIN_OPS_POSTGRES_DATABASE_URL:-}" ]]; then
  ENV_ARGS+=(FIN_OPS_POSTGRES_DATABASE_URL="${FIN_OPS_POSTGRES_DATABASE_URL}")
fi
if [[ -n "${DATABASE_URL:-}" ]]; then
  ENV_ARGS+=(DATABASE_URL="${DATABASE_URL}")
fi
if [[ -n "${OBJECT_STORAGE_BACKEND:-}" ]]; then
  ENV_ARGS+=(OBJECT_STORAGE_BACKEND="${OBJECT_STORAGE_BACKEND}")
fi
if [[ -n "${S3_ENDPOINT_URL:-}" ]]; then
  ENV_ARGS+=(S3_ENDPOINT_URL="${S3_ENDPOINT_URL}")
fi
if [[ -n "${S3_BUCKET:-}" ]]; then
  ENV_ARGS+=(S3_BUCKET="${S3_BUCKET}")
fi
if [[ -n "${S3_REGION:-}" ]]; then
  ENV_ARGS+=(S3_REGION="${S3_REGION}")
fi
if [[ -n "${S3_ACCESS_KEY_ID:-}" ]]; then
  ENV_ARGS+=(S3_ACCESS_KEY_ID="${S3_ACCESS_KEY_ID}")
fi
if [[ -n "${S3_SECRET_ACCESS_KEY:-}" ]]; then
  ENV_ARGS+=(S3_SECRET_ACCESS_KEY="${S3_SECRET_ACCESS_KEY}")
fi
if [[ -n "${FIN_OPS_REDIS_URL:-}" ]]; then
  ENV_ARGS+=(FIN_OPS_REDIS_URL="${FIN_OPS_REDIS_URL}")
fi
if [[ -n "${REDIS_URL:-}" ]]; then
  ENV_ARGS+=(REDIS_URL="${REDIS_URL}")
fi
if [[ -n "${FIN_OPS_REDIS_KEY_PREFIX:-}" ]]; then
  ENV_ARGS+=(FIN_OPS_REDIS_KEY_PREFIX="${FIN_OPS_REDIS_KEY_PREFIX}")
fi
if [[ -n "${FIN_OPS_REDIS_WAKEUP_CHANNEL:-}" ]]; then
  ENV_ARGS+=(FIN_OPS_REDIS_WAKEUP_CHANNEL="${FIN_OPS_REDIS_WAKEUP_CHANNEL}")
fi
if [[ -n "${FIN_OPS_REDIS_DEFAULT_TTL_SECONDS:-}" ]]; then
  ENV_ARGS+=(FIN_OPS_REDIS_DEFAULT_TTL_SECONDS="${FIN_OPS_REDIS_DEFAULT_TTL_SECONDS}")
fi

exec env "${ENV_ARGS[@]}" "${PYTHON_BIN}" -m fin_ops_platform.app.main --host "${HOST}" --port "${PORT}"

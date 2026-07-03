#!/usr/bin/env bash
set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LOCK_FILE="${FINOPS_OA_SYNC_ENQUEUE_LOCK_FILE:-/run/finops-enqueue-oa-sync.lock}"
LOG_DIR="${FINOPS_OA_SYNC_ENQUEUE_LOG_DIR:-/var/log/fin-ops}"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"
COMMON_ENV="${FINOPS_COMMON_ENV:-/etc/fin-ops/fin-ops.common.env}"
SECRETS_ENV="${FINOPS_SECRETS_ENV:-/etc/fin-ops/fin-ops.secrets.env}"
SCOPE="${FINOPS_OA_SYNC_SCOPE:-all}"
REASON="${FINOPS_OA_SYNC_REASON:-scheduled_oa_sync}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/oa-sync-enqueue-$(date +%Y%m%d).log"
exec >>"$LOG_FILE" 2>&1

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Is) another OA sync enqueue run is active; exiting"
  exit 0
fi

echo "== finops OA sync enqueue $(date -Is) =="

active_src="$(systemctl show fin-ops.service -p WorkingDirectory --value || true)"
if [[ -z "$active_src" || ! -d "$active_src/backend/src/fin_ops_platform" ]]; then
  echo "active release source not found: ${active_src:-<empty>}"
  exit 2
fi
if [[ ! -x "$API_PYTHON" ]]; then
  echo "api python not executable: $API_PYTHON"
  exit 2
fi
if [[ ! -f "$COMMON_ENV" || ! -f "$SECRETS_ENV" ]]; then
  echo "runtime env missing: $COMMON_ENV / $SECRETS_ENV"
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$COMMON_ENV"
# shellcheck disable=SC1090
source "$SECRETS_ENV"
set +a

if [[ -z "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}}" ]]; then
  echo "missing FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL in runtime env"
  exit 2
fi

export PYTHONPATH="$active_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"

echo "active_src=$active_src scope=$SCOPE reason=$REASON"
(cd "$active_src" && "$API_PYTHON" -m fin_ops_platform.tools.runtime_queue_ops enqueue-oa-sync \
  --scope "$SCOPE" \
  --reason "$REASON" \
  --triggered-by system)

echo "== done $(date -Is) =="

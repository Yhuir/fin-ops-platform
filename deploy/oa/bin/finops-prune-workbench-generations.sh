#!/usr/bin/env bash
set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LOCK_FILE="${FINOPS_WORKBENCH_PRUNE_LOCK_FILE:-/run/finops-prune-workbench-generations.lock}"
LOG_DIR="${FINOPS_WORKBENCH_PRUNE_LOG_DIR:-/var/log/fin-ops}"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"
COMMON_ENV="${FINOPS_COMMON_ENV:-/etc/fin-ops/fin-ops.common.env}"
SECRETS_ENV="${FINOPS_SECRETS_ENV:-/etc/fin-ops/fin-ops.secrets.env}"
HEALTH_URL="${FINOPS_HEALTH_URL:-http://127.0.0.1:18001/health/ready}"

KEEP_RECENT="${FINOPS_WORKBENCH_PRUNE_KEEP_RECENT:-1}"
KEEP_DAYS="${FINOPS_WORKBENCH_PRUNE_KEEP_DAYS:-0}"
LIMIT="${FINOPS_WORKBENCH_PRUNE_LIMIT:-500}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/workbench-generation-prune-$(date +%Y%m%d).log"
exec >>"$LOG_FILE" 2>&1

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Is) another prune run is active; exiting"
  exit 0
fi

echo "== finops workbench generation prune $(date -Is) =="

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

prune_script="$active_src/backend/src/fin_ops_platform/tools/prune_workbench_generations.py"
if [[ ! -f "$prune_script" ]]; then
  echo "prune script not found: $prune_script"
  exit 2
fi

echo "active_src=$active_src"
echo "policy keep_recent=$KEEP_RECENT keep_days=$KEEP_DAYS limit=$LIMIT"
echo "disk_before=$(df -h / | awk 'NR==2 {print $0}')"
if [[ -d /var/lib/pgsql/data/pg_wal ]]; then
  echo "pg_wal_before=$(du -sh /var/lib/pgsql/data/pg_wal 2>/dev/null || true)"
fi

echo "generation_status_before"
sudo -u postgres psql -d fin_ops -Atc "select status || ':' || count(*) from read_model.workbench_generations group by status order by status;" || true

set -a
# shellcheck disable=SC1090
source "$COMMON_ENV"
# shellcheck disable=SC1090
source "$SECRETS_ENV"
set +a
export PYTHONPATH="$active_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"

(cd "$active_src" && "$API_PYTHON" "$prune_script" \
  --execute \
  --keep-recent-generations-per-scope "$KEEP_RECENT" \
  --keep-days "$KEEP_DAYS" \
  --limit "$LIMIT")

echo "generation_status_after"
sudo -u postgres psql -d fin_ops -Atc "select status || ':' || count(*) from read_model.workbench_generations group by status order by status;" || true

echo "workbench_generation_total=$(sudo -u postgres psql -d fin_ops -Atc 'select count(*) from read_model.workbench_generations;' || true)"
echo "disk_after=$(df -h / | awk 'NR==2 {print $0}')"
if [[ -d /var/lib/pgsql/data/pg_wal ]]; then
  echo "pg_wal_after=$(du -sh /var/lib/pgsql/data/pg_wal 2>/dev/null || true)"
fi

echo "health_check"
curl -fsS --max-time 20 "$HEALTH_URL" >/dev/null && echo "health=ready" || echo "health=failed url=$HEALTH_URL"
echo "== done $(date -Is) =="

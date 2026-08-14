#!/usr/bin/env bash
set -Eeuo pipefail

PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

LOCK_FILE="${FINOPS_RUNTIME_QUEUE_PRUNE_LOCK_FILE:-/run/finops-prune-runtime-queue-history.lock}"
LOG_DIR="${FINOPS_RUNTIME_QUEUE_PRUNE_LOG_DIR:-/var/log/fin-ops}"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"
COMMON_ENV="${FINOPS_COMMON_ENV:-/etc/fin-ops/fin-ops.common.env}"
MIGRATOR_ENV="${FINOPS_MIGRATOR_ENV:-/etc/fin-ops/fin-ops.postgres-migrator.env}"
HEALTH_URL="${FINOPS_HEALTH_URL:-http://127.0.0.1:18001/health/ready}"

KEEP_DAYS="${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_DAYS:-30}"
KEEP_RECENT_PER_TYPE="${FINOPS_RUNTIME_QUEUE_PRUNE_KEEP_RECENT_PER_TYPE:-512}"
LIMIT="${FINOPS_RUNTIME_QUEUE_PRUNE_LIMIT:-20000}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/runtime-queue-history-prune-$(date +%Y%m%d).log"
exec >>"$LOG_FILE" 2>&1

exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "$(date -Is) another runtime queue history prune run is active; exiting"
  exit 0
fi

echo "== finops runtime queue history prune $(date -Is) =="

active_src="$(systemctl show fin-ops.service -p WorkingDirectory --value || true)"
if [[ -z "$active_src" || ! -d "$active_src/backend/src/fin_ops_platform" ]]; then
  echo "active release source not found: ${active_src:-<empty>}"
  exit 2
fi
if [[ ! -x "$API_PYTHON" ]]; then
  echo "api python not executable: $API_PYTHON"
  exit 2
fi
if [[ ! -f "$COMMON_ENV" || ! -f "$MIGRATOR_ENV" ]]; then
  echo "runtime queue retention env missing: $COMMON_ENV / $MIGRATOR_ENV"
  exit 2
fi

set -a
# shellcheck disable=SC1090
source "$COMMON_ENV"
# shellcheck disable=SC1090
source "$MIGRATOR_ENV"
set +a
if [[ -z "${FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL:-}" ]]; then
  echo "missing FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL in $MIGRATOR_ENV"
  exit 2
fi
export FIN_OPS_POSTGRES_DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL"
export DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL"
export PYTHONPATH="$active_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"

echo "active_src=$active_src"
echo "policy keep_days=$KEEP_DAYS keep_recent_per_type=$KEEP_RECENT_PER_TYPE limit=$LIMIT"
echo "disk_before=$(df -h / | awk 'NR==2 {print $0}')"
if [[ -d /var/lib/pgsql/data/pg_wal ]]; then
  echo "pg_wal_before=$(du -sh /var/lib/pgsql/data/pg_wal 2>/dev/null || true)"
fi

echo "outbox_status_before"
sudo -u postgres psql -d fin_ops -Atc "select status || ':' || count(*) from job.outbox_events group by status order by status;" || true

(cd "$active_src" && "$API_PYTHON" -m fin_ops_platform.tools.runtime_queue_ops prune-history \
  --execute \
  --keep-days "$KEEP_DAYS" \
  --keep-recent-per-type "$KEEP_RECENT_PER_TYPE" \
  --limit "$LIMIT")

echo "outbox_status_after"
sudo -u postgres psql -d fin_ops -Atc "select status || ':' || count(*) from job.outbox_events group by status order by status;" || true
echo "job_schema_size=$(sudo -u postgres psql -d fin_ops -Atc \"select pg_size_pretty(sum(pg_total_relation_size(c.oid))) from pg_class c join pg_namespace n on n.oid = c.relnamespace where n.nspname = 'job' and c.relkind in ('r','i','t');\" || true)"

echo "disk_after=$(df -h / | awk 'NR==2 {print $0}')"
if [[ -d /var/lib/pgsql/data/pg_wal ]]; then
  echo "pg_wal_after=$(du -sh /var/lib/pgsql/data/pg_wal 2>/dev/null || true)"
fi

echo "health_check"
curl -fsS --max-time 20 "$HEALTH_URL" >/dev/null && echo "health=ready" || echo "health=failed url=$HEALTH_URL"
echo "== done $(date -Is) =="

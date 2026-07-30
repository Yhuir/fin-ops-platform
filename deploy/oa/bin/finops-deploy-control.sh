#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_ROOT="${FINOPS_RELEASE_ROOT:-/opt/fin-ops/releases}"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"
WORKER_PYTHON="${FINOPS_WORKER_PYTHON:-/opt/fin-ops/rabbitmq-runtime/20260522-224452/venv/bin/python}"
ENV_DIR="${FINOPS_ENV_DIR:-/etc/fin-ops}"
API_DROPIN_DIR="${FINOPS_API_DROPIN_DIR:-/etc/systemd/system/fin-ops.service.d}"
WORKER_DROPIN_DIR="${FINOPS_WORKER_DROPIN_DIR:-/etc/systemd/system/fin-ops-worker@.service.d}"
DISPATCHER_DROPIN_DIR="${FINOPS_DISPATCHER_DROPIN_DIR:-/etc/systemd/system/fin-ops-rabbitmq-dispatcher.service.d}"
API_DROPIN="$API_DROPIN_DIR/99-deploy-release.conf"
WORKER_DROPIN="$WORKER_DROPIN_DIR/99-deploy-release.conf"
DISPATCHER_DROPIN="$DISPATCHER_DROPIN_DIR/99-deploy-release.conf"
FRONTEND_DIR="${FINOPS_FRONTEND_DIR:-/www/wwwroot/fin-ops/dist}"
LEGACY_CURRENT_DIR="${FINOPS_LEGACY_CURRENT_DIR:-/opt/fin-ops/current}"
LEGACY_CURRENT_ARCHIVE_DIR="${FINOPS_LEGACY_CURRENT_ARCHIVE_DIR:-/opt/fin-ops/legacy-current-archives}"
COMMON_ENV="$ENV_DIR/fin-ops.common.env"
SECRETS_ENV="$ENV_DIR/fin-ops.secrets.env"
MIGRATOR_ENV="$ENV_DIR/fin-ops.postgres-migrator.env"
DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"
ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"
WRITE_E2E_BACKUP_ROOT="${FINOPS_WRITE_E2E_BACKUP_ROOT:-/opt/fin-ops/backups/write-operation-e2e}"
STANDARD_WRITE_E2E_SCENARIO="${FINOPS_STANDARD_WRITE_E2E_SCENARIO:-/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json}"
PRUNE_WORKBENCH_GENERATIONS_HELPER="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_HELPER:-/usr/local/sbin/finops-prune-workbench-generations}"
PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT:-/etc/systemd/system/finops-prune-workbench-generations.service}"
PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT:-/etc/systemd/system/finops-prune-workbench-generations.timer}"
PRUNE_RUNTIME_QUEUE_HISTORY_HELPER="${FINOPS_PRUNE_RUNTIME_QUEUE_HISTORY_HELPER:-/usr/local/sbin/finops-prune-runtime-queue-history}"
PRUNE_RUNTIME_QUEUE_HISTORY_SERVICE_UNIT="${FINOPS_PRUNE_RUNTIME_QUEUE_HISTORY_SERVICE_UNIT:-/etc/systemd/system/finops-prune-runtime-queue-history.service}"
PRUNE_RUNTIME_QUEUE_HISTORY_TIMER_UNIT="${FINOPS_PRUNE_RUNTIME_QUEUE_HISTORY_TIMER_UNIT:-/etc/systemd/system/finops-prune-runtime-queue-history.timer}"
OA_SYNC_ENQUEUE_HELPER="${FINOPS_OA_SYNC_ENQUEUE_HELPER:-/usr/local/sbin/finops-enqueue-oa-sync}"
OA_SYNC_ENQUEUE_SERVICE_UNIT="${FINOPS_OA_SYNC_ENQUEUE_SERVICE_UNIT:-/etc/systemd/system/finops-enqueue-oa-sync.service}"
OA_SYNC_ENQUEUE_TIMER_UNIT="${FINOPS_OA_SYNC_ENQUEUE_TIMER_UNIT:-/etc/systemd/system/finops-enqueue-oa-sync.timer}"

usage() {
  cat <<'USAGE'
usage: finops-deploy-control <command> [args]

commands:
  check-release <release-name>         validate a release under /opt/fin-ops/releases
  self-update <release-name>           install deploy-control helper from a validated release
  activate <release-name>              point API/workers/dispatcher at release and restart active services
  workbench-rehydrate <release-name> [args]
                                      rebuild Workbench SQL read models using runtime env
  workbench-audit-identity <release-name> [args]
                                      run Workbench object identity audit using runtime env
  workbench-requirement-repair <release-name> --dry-run
  workbench-requirement-repair <release-name> --execute --expected-fingerprint <sha256>
  workbench-requirement-repair <release-name> --rollback-dry-run --expected-fingerprint <sha256>
  workbench-requirement-repair <release-name> --rollback --expected-fingerprint <sha256>
                                      repair historical frozen OA/invoice requirements through relation commands
  workbench-etc-summary-repair <release-name> --case-id ID --external-etc-batch-id ID --dry-run
  workbench-etc-summary-repair <release-name> --case-id ID --external-etc-batch-id ID --execute --expected-fingerprint <sha256>
  workbench-etc-summary-repair <release-name> --case-id ID --external-etc-batch-id ID --rollback-dry-run --expected-fingerprint <sha256>
  workbench-etc-summary-repair <release-name> --case-id ID --external-etc-batch-id ID --rollback --expected-fingerprint <sha256>
                                      repair one proven ETC summary relation through relation commands
  batch-accounting-metadata-cleanup <release-name> --dry-run
  batch-accounting-metadata-cleanup <release-name> --execute --expected-fingerprint <sha256>
  batch-accounting-metadata-cleanup <release-name> --rollback-dry-run --expected-fingerprint <sha256>
  batch-accounting-metadata-cleanup <release-name> --rollback --expected-fingerprint <sha256>
                                      remove retired batch membership metadata through relation commands
  batch-accounting-audit <release-name>
                                      run the fixed read-only Batch Accounting business audit
  domain-contract-audit <release-name>
                                      count canonical PostgreSQL contract violations without samples or writes
  batch-accounting-read-smoke <release-name> --bank-year YYYY [--iterations N]
                                      time and validate both canonical read buckets without HTTP auth
  workbench-matching-retry <release-name> --scope-month YYYY-MM --dry-run
  workbench-matching-retry <release-name> --scope-month YYYY-MM --execute --expected-fingerprint <sha256>
                                      requeue one failed matching scope through its durable repository boundary
  etc-deleted-batch-restore <release-name> --business-batch-id ID --expected-invoice-count N --expected-total-amount AMOUNT --expected-oa-row-id ID --dry-run
  etc-deleted-batch-restore <release-name> --business-batch-id ID --expected-invoice-count N --expected-total-amount AMOUNT --expected-oa-row-id ID --execute --expected-fingerprint <sha256> --operator ACTOR --reason TEXT
                                      restore one exact deleted submitted ETC tombstone
  etc-batch-invoice-link-backfill <release-name> --business-batch-id ID --limit N --dry-run
  etc-batch-invoice-link-backfill <release-name> --business-batch-id ID --limit N --apply --expected-auto-backfill-count N --operator ACTOR --reason TEXT
                                      backfill strict canonical invoice links for one ETC business batch
  etc-submitted-batch-member-repair <release-name> [tool args]
                                      repair proven canonical invoices into one submitted ETC batch
  read-model-scope-contract <release-name> [args]
                                      check or repair read model scope contracts using runtime env
  read-model-slo-smoke <release-name> [args]
                                      run read model SLO smoke dry-run using runtime env; --apply is refused
  write-operation-restore-point <release-name> <run-id>
                                      create and verify a fixed full PostgreSQL backup before write smoke
  write-operation-restore-point-delete <run-id> <expected-sha256>
                                      delete one exact verified write-smoke backup
  write-operation-e2e-smoke <release-name> <scenario-path> [--dry-run|--apply-stdin] [preview-samples]
  api-request-error <request-id>
  api-request-trace <request-id>
  api-request-timing <request-id>
                                      run the fixed production relation runner; admin token is read from stdin
  read-model-refresh <release-name> [args]
                                      validate or enqueue read-model refresh scopes through the durable gateway
  settings-normalize <release-name> [--dry-run|--execute]
                                      normalize App settings through the canonical service/repository boundary
  import-audit-repair <release-name> [--dry-run|--execute --expected-fingerprint <sha256>]
                                      repair strict import facts through the canonical PostgreSQL boundary
  bank-transaction-category-repair <release-name> [--dry-run|--apply --operator <actor> --expected-candidate-count <count>]
                                      repair proven historical manual category clears through the canonical writer
  runtime-queue-resolve-covered <release-name> [args]
                                      resolve only dead letters covered by fresh/done scope proof
  restart                              restart API, active workers, and active dispatcher
  status                               print service state and active release paths
  cleanup-dropins                      remove historical release drop-ins, preserving 99-deploy-release.conf
  cleanup-releases [--keep N] [--dry-run]
                                      delete old release directories, preserving newest N and active references
USAGE
}

die() {
  echo "finops-deploy-control: $*" >&2
  exit 1
}

release_src() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "release name is required"
  [[ "$release" =~ ^[A-Za-z0-9._-]+$ ]] || die "invalid release name: $release"
  local src="$RELEASE_ROOT/$release/src"
  [[ -d "$src" ]] || die "release src directory not found: $src"
  [[ -d "$src/backend/src/fin_ops_platform" ]] || die "backend package not found in release: $src"
  [[ -f "$src/backend/requirements.txt" ]] || die "backend requirements not found in release: $src"
  [[ -f "$src/web/dist/index.html" ]] || die "frontend dist not found in release: $src"
  printf '%s\n' "$src"
}

active_worker_services() {
  systemctl list-units --type=service --state=active --no-legend 'fin-ops-worker@*.service' \
    | awk '{print $1}' \
    | grep -E '^fin-ops-worker@[-A-Za-z0-9_.]+\.service$' \
    | sort -u || true
}

all_worker_services() {
  systemctl list-units --type=service --all --no-legend 'fin-ops-worker@*.service' \
    | awk '{print $1}' \
    | grep -E '^fin-ops-worker@[-A-Za-z0-9_.]+\.service$' \
    | sort -u || true
}

registered_worker_instances() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -m fin_ops_platform.tools.runtime_worker_manifest --instances
}

stop_runtime_worker_services_for_activation() {
  local service
  while IFS= read -r service; do
    [[ -n "$service" ]] || continue
    printf 'stopping previous-release runtime worker: %s\n' "$service"
    systemctl stop "$service"
  done < <(active_worker_services)
}

retire_unregistered_worker_services() {
  local src="$1"
  local registered_workers service instance
  registered_workers=" $(registered_worker_instances "$src") "

  while IFS= read -r service; do
    [[ -n "$service" ]] || continue
    instance="${service#fin-ops-worker@}"
    instance="${instance%.service}"
    if [[ "$registered_workers" == *" $instance "* ]]; then
      continue
    fi
    if ! systemctl is-enabled --quiet "$service" \
      && ! systemctl is-active --quiet "$service" \
      && ! systemctl is-failed --quiet "$service"; then
      continue
    fi
    printf 'retiring unregistered runtime worker: %s\n' "$service"
    systemctl disable "$service" >/dev/null 2>&1 || true
    systemctl stop "$service"
    systemctl reset-failed "$service" >/dev/null 2>&1 || true
  done < <(all_worker_services)
}

assert_runtime_env_contract() {
  [[ -f "$COMMON_ENV" ]] || die "missing common runtime env: $COMMON_ENV"
  [[ -f "$SECRETS_ENV" ]] || die "missing secret runtime env: $SECRETS_ENV"
  if ! grep -hE '^(FIN_OPS_POSTGRES_DATABASE_URL|DATABASE_URL)=' "$COMMON_ENV" "$SECRETS_ENV" >/dev/null; then
    die "missing PostgreSQL DSN in $COMMON_ENV or $SECRETS_ENV"
  fi
  local required_key
  for required_key in \
    FIN_OPS_OA_BASE_URL \
    FIN_OPS_OA_USER_INFO_PATH \
    FIN_OPS_ALLOWED_USERNAMES \
    FIN_OPS_ADMIN_USERNAMES; do
    if ! grep -hE "^${required_key}=" "$COMMON_ENV" "$SECRETS_ENV" >/dev/null; then
      die "missing OA session runtime env: $required_key in $COMMON_ENV or $SECRETS_ENV"
    fi
  done
}

sync_python_envs() {
  local src="$1"
  [[ -x "$API_PYTHON" ]] || die "API python not executable: $API_PYTHON"
  [[ -x "$WORKER_PYTHON" ]] || die "worker python not executable: $WORKER_PYTHON"
  "$API_PYTHON" -m pip install -r "$src/backend/requirements.txt" >/dev/null
  if [[ "$WORKER_PYTHON" != "$API_PYTHON" ]]; then
    "$WORKER_PYTHON" -m pip install -r "$src/backend/requirements.txt" >/dev/null
  fi
}

run_schema_migrations() {
  local src="$1"
  [[ -f "$MIGRATOR_ENV" ]] || die "missing PostgreSQL migrator env: $MIGRATOR_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$MIGRATOR_ENV"
  set +a
  PYTHONPATH="$src/backend/src" "$API_PYTHON" -m fin_ops_platform.postgres.migrate apply
}

run_with_runtime_env() {
  local src="$1"
  shift
  [[ -f "$COMMON_ENV" ]] || die "missing common runtime env: $COMMON_ENV"
  [[ -f "$SECRETS_ENV" ]] || die "missing secret runtime env: $SECRETS_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$COMMON_ENV"
  # shellcheck disable=SC1090
  source "$SECRETS_ENV"
  set +a
  export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
  export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
  (cd "$src" && "$API_PYTHON" "$@")
}

assert_retired_page_runtime_quiesced() {
  local src="$1"
  local evidence
  if ! evidence="$(run_with_runtime_env "$src" -c '
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST

active_event_types = sorted(
    entry.refresh_event_type
    for entry in READ_MODEL_MANIFEST.values()
)
active_scope_types = sorted(
    entry.scope_type
    for entry in READ_MODEL_MANIFEST.values()
)
connection = PostgresConnection(PostgresSettings.from_env())
processing_events = connection.fetch_all(
    """
    select event_type, count(*)::bigint as count
    from job.outbox_events
    where status = %s
      and event_type like %s
      and not (event_type = any(%s))
    group by event_type
    order by event_type
    """,
    ("processing", "%.read_model.refresh", active_event_types),
)
processing_scopes = connection.fetch_all(
    """
    select scope_type, count(*)::bigint as count
    from job.read_model_dirty_scopes
    where status = %s
      and not (scope_type = any(%s))
    group by scope_type
    order by scope_type
    """,
    ("processing", active_scope_types),
)
payload = {
    "retired_processing_event_types": processing_events,
    "retired_processing_scope_types": processing_scopes,
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
raise SystemExit(0 if not processing_events and not processing_scopes else 3)
')"; then
    printf 'retired page runtime is not quiesced: %s\n' "$evidence" >&2
    die "refusing activation while retired page outbox or dirty-scope work is processing"
  fi
  printf 'retired page runtime preflight passed: %s\n' "$evidence"
}

archive_legacy_current() {
  [[ -e "$LEGACY_CURRENT_DIR" || -L "$LEGACY_CURRENT_DIR" ]] || return 0
  mkdir -p "$LEGACY_CURRENT_ARCHIVE_DIR"
  local timestamp target suffix
  timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
  target="$LEGACY_CURRENT_ARCHIVE_DIR/current-$timestamp"
  suffix=0
  while [[ -e "$target" || -L "$target" ]]; do
    suffix=$((suffix + 1))
    target="$LEGACY_CURRENT_ARCHIVE_DIR/current-$timestamp-$suffix"
  done
  mv "$LEGACY_CURRENT_DIR" "$target"
  printf 'archived legacy current runtime: %s -> %s\n' "$LEGACY_CURRENT_DIR" "$target"
}

write_api_dropin() {
  local src="$1"
  mkdir -p "$API_DROPIN_DIR"
  cat > "$API_DROPIN" <<DROPIN
[Service]
EnvironmentFile=
EnvironmentFile=$COMMON_ENV
EnvironmentFile=$SECRETS_ENV
EnvironmentFile=-$ENV_DIR/fin-ops.rabbitmq-monitoring.env
Environment=PYTHONPATH=$src/backend/src
Environment=FIN_OPS_DATA_DIR=/opt/fin-ops/data
WorkingDirectory=$src
ExecStart=
ExecStart=$API_PYTHON -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001
DROPIN
}

write_worker_dropin() {
  local src="$1"
  mkdir -p "$WORKER_DROPIN_DIR"
  cat > "$WORKER_DROPIN" <<DROPIN
[Service]
WorkingDirectory=$src
Environment=PYTHONPATH=$src/backend/src
ExecStart=
ExecStart=$WORKER_PYTHON -m fin_ops_platform.app.worker --worker-id \${FIN_OPS_WORKER_ID} --registration \${FIN_OPS_WORKER_INSTANCE} --worker-instance \${FIN_OPS_WORKER_INSTANCE} \$FIN_OPS_WORKER_ARGS --lock-timeout-seconds \${FIN_OPS_WORKER_LOCK_TIMEOUT_SECONDS} --task-timeout-seconds \${FIN_OPS_WORKER_TASK_TIMEOUT_SECONDS} --statement-timeout-seconds \${FIN_OPS_WORKER_STATEMENT_TIMEOUT_SECONDS} --max-attempts \${FIN_OPS_WORKER_MAX_ATTEMPTS} --max-events-per-iteration \${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION} --dependency-not-fresh-delay-seconds \${FIN_OPS_WORKER_DEPENDENCY_NOT_FRESH_DELAY_SECONDS}
DROPIN
}

write_dispatcher_dropin() {
  local src="$1"
  [[ -d "$DISPATCHER_DROPIN_DIR" || -f /etc/systemd/system/fin-ops-rabbitmq-dispatcher.service ]] || return 0
  mkdir -p "$DISPATCHER_DROPIN_DIR"
  cat > "$DISPATCHER_DROPIN" <<DROPIN
[Service]
WorkingDirectory=$src
EnvironmentFile=
EnvironmentFile=$COMMON_ENV
EnvironmentFile=$SECRETS_ENV
EnvironmentFile=-$ENV_DIR/fin-ops.rabbitmq-dispatcher.env
Environment=RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS=0.05
Environment=PYTHONPATH=$src/backend/src
ExecStart=
ExecStart=$WORKER_PYTHON -m fin_ops_platform.app.rabbitmq_dispatcher --publisher-id rabbitmq-dispatcher-shadow-1 --batch-size 100 --lock-timeout-seconds 300 --retry-delay-seconds 60 --poll-interval-seconds \${RABBITMQ_DISPATCHER_POLL_INTERVAL_SECONDS}
DROPIN
}

ensure_runtime_workers() {
  local src="$1"
  [[ -x "$ENSURE_RUNTIME_WORKERS_HELPER" ]] || die "runtime worker ensure helper is not executable: $ENSURE_RUNTIME_WORKERS_HELPER"
  "$ENSURE_RUNTIME_WORKERS_HELPER" "$src"
}

install_deploy_control_helper() {
  local src="$1"
  local helper_src="$src/deploy/oa/bin/finops-deploy-control.sh"
  [[ -f "$helper_src" ]] || die "missing deploy-control helper in release: $helper_src"
  if [[ -f "$DEPLOY_CONTROL_HELPER" ]] && cmp -s "$helper_src" "$DEPLOY_CONTROL_HELPER"; then
    return 0
  fi
  install -m 0755 -o root -g root "$helper_src" "$DEPLOY_CONTROL_HELPER"
}

install_runtime_worker_helper() {
  local src="$1"
  local helper_src="$src/deploy/oa/bin/finops-ensure-runtime-workers.sh"
  [[ -f "$helper_src" ]] || die "missing runtime worker helper in release: $helper_src"
  if [[ -f "$ENSURE_RUNTIME_WORKERS_HELPER" ]] && cmp -s "$helper_src" "$ENSURE_RUNTIME_WORKERS_HELPER"; then
    return 0
  fi
  install -m 0755 -o root -g root "$helper_src" "$ENSURE_RUNTIME_WORKERS_HELPER"
}

install_workbench_generation_retention() {
  local src="$1"
  local helper_src service_src timer_src timer_unit
  helper_src="$src/deploy/oa/bin/finops-prune-workbench-generations.sh"
  service_src="$src/deploy/oa/systemd/finops-prune-workbench-generations.service.example"
  timer_src="$src/deploy/oa/systemd/finops-prune-workbench-generations.timer.example"
  timer_unit="$(basename "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT")"

  [[ -f "$helper_src" ]] || die "missing Workbench generation prune helper in release: $helper_src"
  [[ -f "$service_src" ]] || die "missing Workbench generation prune service unit in release: $service_src"
  [[ -f "$timer_src" ]] || die "missing Workbench generation prune timer unit in release: $timer_src"

  install -m 0755 -o root -g root "$helper_src" "$PRUNE_WORKBENCH_GENERATIONS_HELPER"
  install -m 0644 -o root -g root "$service_src" "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT"
  install -m 0644 -o root -g root "$timer_src" "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT"
  systemctl daemon-reload
  systemctl enable --now "$timer_unit"
}

install_runtime_queue_history_retention() {
  local src="$1"
  local helper_src service_src timer_src timer_unit
  helper_src="$src/deploy/oa/bin/finops-prune-runtime-queue-history.sh"
  service_src="$src/deploy/oa/systemd/finops-prune-runtime-queue-history.service.example"
  timer_src="$src/deploy/oa/systemd/finops-prune-runtime-queue-history.timer.example"
  timer_unit="$(basename "$PRUNE_RUNTIME_QUEUE_HISTORY_TIMER_UNIT")"

  [[ -f "$helper_src" ]] || die "missing runtime queue history prune helper in release: $helper_src"
  [[ -f "$service_src" ]] || die "missing runtime queue history prune service unit in release: $service_src"
  [[ -f "$timer_src" ]] || die "missing runtime queue history prune timer unit in release: $timer_src"

  install -m 0755 -o root -g root "$helper_src" "$PRUNE_RUNTIME_QUEUE_HISTORY_HELPER"
  install -m 0644 -o root -g root "$service_src" "$PRUNE_RUNTIME_QUEUE_HISTORY_SERVICE_UNIT"
  install -m 0644 -o root -g root "$timer_src" "$PRUNE_RUNTIME_QUEUE_HISTORY_TIMER_UNIT"
  systemctl daemon-reload
  systemctl enable --now "$timer_unit"
}

install_oa_sync_enqueue_timer() {
  local src="$1"
  local helper_src service_src timer_src timer_unit
  helper_src="$src/deploy/oa/bin/finops-enqueue-oa-sync.sh"
  service_src="$src/deploy/oa/systemd/finops-enqueue-oa-sync.service.example"
  timer_src="$src/deploy/oa/systemd/finops-enqueue-oa-sync.timer.example"
  timer_unit="$(basename "$OA_SYNC_ENQUEUE_TIMER_UNIT")"

  [[ -f "$helper_src" ]] || die "missing OA sync enqueue helper in release: $helper_src"
  [[ -f "$service_src" ]] || die "missing OA sync enqueue service unit in release: $service_src"
  [[ -f "$timer_src" ]] || die "missing OA sync enqueue timer unit in release: $timer_src"

  install -m 0755 -o root -g root "$helper_src" "$OA_SYNC_ENQUEUE_HELPER"
  install -m 0644 -o root -g root "$service_src" "$OA_SYNC_ENQUEUE_SERVICE_UNIT"
  install -m 0644 -o root -g root "$timer_src" "$OA_SYNC_ENQUEUE_TIMER_UNIT"
  systemctl daemon-reload
  systemctl enable --now "$timer_unit"
}

publish_frontend() {
  local src="$1"
  local dist="$src/web/dist"
  local parent tmp backup
  [[ -f "$dist/index.html" ]] || die "release frontend dist missing: $dist"
  parent="$(dirname "$FRONTEND_DIR")"
  tmp="$parent/.dist.deploy.$$"
  backup="$parent/.dist.previous"
  mkdir -p "$parent"
  rm -rf -- "$tmp"
  cp -a "$dist" "$tmp"
  chmod -R a+rX "$tmp"
  rm -rf -- "$backup"
  if [[ -d "$FRONTEND_DIR" ]]; then
    mv "$FRONTEND_DIR" "$backup"
  fi
  mv "$tmp" "$FRONTEND_DIR"
  rm -rf -- "$backup"
}

restart_services() {
  systemctl daemon-reload
  systemctl restart fin-ops.service
  local svc
  while IFS= read -r svc; do
    [[ -n "$svc" ]] || continue
    systemctl restart "$svc"
  done < <(active_worker_services)
  if systemctl is-active --quiet fin-ops-rabbitmq-dispatcher.service; then
    systemctl restart fin-ops-rabbitmq-dispatcher.service
  fi
}

wait_required_workers_ready() {
  local timeout deadline health status_json readiness_status
  timeout="${FINOPS_WORKER_READY_TIMEOUT_SECONDS:-90}"
  [[ "$timeout" =~ ^[0-9]+$ ]] || die "invalid FINOPS_WORKER_READY_TIMEOUT_SECONDS: $timeout"
  deadline=$((SECONDS + timeout))
  health=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    health="$(curl -fsS --max-time 5 http://127.0.0.1:18001/health 2>&1 || true)"
    readiness_status=0
    status_json="$(printf '%s' "$health" | python3 -c '
import json
import sys

try:
    data = json.load(sys.stdin)
except Exception:
    sys.exit(1)
runtime = data.get("runtime_infrastructure")
if not isinstance(runtime, dict):
    sys.exit(1)
workers = runtime.get("worker_metrics")
if not isinstance(workers, list):
    workers = []
missing = int(runtime.get("missing_required_worker_count") or 0)
stale = int(runtime.get("stale_required_worker_count") or 0)
mismatched = int(runtime.get("mismatched_required_worker_count") or 0)
bad_codes = {"worker_kind_mismatch", "worker_event_type_mismatch"}
bad_workers = [
    str(row.get("worker_instance") or row.get("worker_kind") or "")
    for row in workers
    if isinstance(row, dict) and row.get("warning_code") in bad_codes
]
payload = {
    "missing_required_worker_count": missing,
    "stale_required_worker_count": stale,
    "mismatched_required_worker_count": mismatched,
    "bad_workers": bad_workers,
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
sys.exit(0 if missing == 0 and stale == 0 and mismatched == 0 and not bad_workers else 2)
' 2>/dev/null)" || readiness_status="$?"
    case "$readiness_status" in
      0)
        return 0
        ;;
      2)
        health="$status_json"
        ;;
      *)
        ;;
    esac
    sleep 2
  done
  echo "required runtime workers did not become ready after release activation" >&2
  printf '%s\n' "$health" >&2
  exit 68
}

status() {
  systemctl is-active fin-ops.service || true
  systemctl is-active fin-ops-rabbitmq-dispatcher.service || true
  active_worker_services | while read -r svc; do
    [[ -n "$svc" ]] || continue
    printf '%s ' "$svc"
    systemctl is-active "$svc" || true
  done
  systemctl show fin-ops.service -p EnvironmentFiles -p WorkingDirectory -p ExecStart --no-pager
  systemctl show fin-ops-rabbitmq-dispatcher.service -p EnvironmentFiles -p WorkingDirectory -p ExecStart --no-pager || true
  systemctl show fin-ops-worker@workbench.service -p EnvironmentFiles -p WorkingDirectory -p Environment --no-pager || true
}

active_release_names() {
  {
    systemctl show fin-ops.service -p WorkingDirectory -p ExecStart -p Environment --no-pager || true
    systemctl show fin-ops-rabbitmq-dispatcher.service -p WorkingDirectory -p ExecStart -p Environment --no-pager || true
    active_worker_services | while read -r svc; do
      [[ -n "$svc" ]] || continue
      systemctl show "$svc" -p WorkingDirectory -p ExecStart -p Environment --no-pager || true
    done
  } | grep -oE '/opt/fin-ops/releases/[^/[:space:]]+' | sed 's#^/opt/fin-ops/releases/##' | sort -u
}

cleanup_dropins() {
  local dir
  for dir in "$API_DROPIN_DIR" "$WORKER_DROPIN_DIR" "$DISPATCHER_DROPIN_DIR"; do
    [[ -d "$dir" ]] || continue
    [[ -f "$dir/99-deploy-release.conf" ]] || die "missing active deploy drop-in: $dir/99-deploy-release.conf"
    find "$dir" -maxdepth 1 -type f -name '*.conf' ! -name '99-deploy-release.conf' -print -delete
  done
  systemctl daemon-reload
}

cleanup_releases() {
  local keep=8 dry_run=0
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --keep)
        keep="${2:-}"
        [[ "$keep" =~ ^[0-9]+$ ]] || die "invalid --keep value: $keep"
        shift 2
        ;;
      --dry-run)
        dry_run=1
        shift
        ;;
      *)
        die "unknown cleanup-releases argument: $1"
        ;;
    esac
  done
  [[ "$keep" -ge 1 ]] || die "--keep must be >= 1"
  mapfile -t protected < <(active_release_names)
  find "$RELEASE_ROOT" -maxdepth 1 -mindepth 1 -type d -printf '%T@ %f\n' \
    | sort -nr \
    | awk -v keep="$keep" 'NR > keep {print $2}' \
    | while IFS= read -r name; do
        [[ -n "$name" ]] || continue
        local skip=0 protected_name path
        for protected_name in "${protected[@]}"; do
          [[ "$name" == "$protected_name" ]] && skip=1 && break
        done
        [[ "$skip" -eq 0 ]] || continue
        [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]] || die "refusing invalid release directory name: $name"
        path="$RELEASE_ROOT/$name"
        [[ -d "$path" ]] || continue
        if [[ "$dry_run" -eq 1 ]]; then
          printf 'would_delete %s\n' "$name"
        else
          rm -rf --one-file-system -- "$path"
          printf 'deleted %s\n' "$name"
        fi
      done
}

workbench_rehydrate() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "workbench-rehydrate requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" "$src/scripts/rehydrate-workbench-read-models.py" "$@"
}

workbench_audit_identity() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "workbench-audit-identity requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.audit_object_identity "$@"
}

workbench_requirement_repair() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "workbench-requirement-repair requires release name"
  shift
  local mode="${1:-}"
  case "$mode" in
    --dry-run)
      [[ "$#" -eq 1 ]] || die "workbench-requirement-repair only permits the four fixed modes"
      ;;
    --execute|--rollback-dry-run|--rollback)
      [[ "$#" -eq 3 && "${2:-}" == "--expected-fingerprint" && -n "${3:-}" ]] || \
        die "workbench-requirement-repair only permits the four fixed modes"
      ;;
    *)
      die "workbench-requirement-repair only permits the four fixed modes"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.workbench_relation_requirement_repair_ops "$@"
}

workbench_etc_summary_repair() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "workbench-etc-summary-repair requires release name"
  shift
  [[ "${1:-}" == "--case-id" && "${2:-}" =~ ^[A-Za-z0-9._-]+$ ]] || \
    die "workbench-etc-summary-repair requires a safe --case-id"
  [[ "${3:-}" == "--external-etc-batch-id" && "${4:-}" =~ ^[A-Za-z0-9._-]+$ ]] || \
    die "workbench-etc-summary-repair requires a safe --external-etc-batch-id"
  local mode="${5:-}"
  case "$mode" in
    --dry-run)
      [[ "$#" -eq 5 ]] || die "workbench-etc-summary-repair only permits the four fixed modes"
      ;;
    --execute|--rollback-dry-run|--rollback)
      [[ "$#" -eq 7 && "${6:-}" == "--expected-fingerprint" && "${7:-}" =~ ^[0-9a-f]{64}$ ]] || \
        die "workbench-etc-summary-repair only permits the four fixed modes"
      ;;
    *)
      die "workbench-etc-summary-repair only permits the four fixed modes"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.workbench_etc_summary_relation_repair_ops "$@"
}

batch_accounting_metadata_cleanup() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "batch-accounting-metadata-cleanup requires release name"
  shift
  local mode="${1:-}"
  case "$mode" in
    --dry-run)
      [[ "$#" -eq 1 ]] || die "batch-accounting-metadata-cleanup only permits the four fixed modes"
      ;;
    --execute|--rollback-dry-run|--rollback)
      [[ "$#" -eq 3 && "${2:-}" == "--expected-fingerprint" && "${3:-}" =~ ^[0-9a-f]{64}$ ]] || \
        die "batch-accounting-metadata-cleanup only permits the four fixed modes"
      ;;
    *)
      die "batch-accounting-metadata-cleanup only permits the four fixed modes"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.batch_accounting_metadata_cleanup_ops "$@"
}

batch_accounting_audit() {
  local release="${1:-}"
  [[ -n "$release" && "$#" -eq 1 ]] || die "batch-accounting-audit accepts only release name"
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.audit_page_business_read_model \
    batch_accounting --json --fail-on-issues --tenant-id default --limit 50
}

domain_contract_audit() {
  local release="${1:-}"
  [[ -n "$release" && "$#" -eq 1 ]] || die "domain-contract-audit accepts only release name"
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.domain_contract_audit
}

batch_accounting_read_smoke() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "batch-accounting-read-smoke requires release name"
  shift
  [[ "${1:-}" == "--bank-year" && "${2:-}" =~ ^[0-9]{4}$ ]] || \
    die "batch-accounting-read-smoke requires --bank-year YYYY"
  case "$#" in
    2)
      ;;
    4)
      [[ "${3:-}" == "--iterations" && "${4:-}" =~ ^([1-9]|[1-4][0-9]|50)$ ]] || \
        die "batch-accounting-read-smoke iterations must be 1..50"
      ;;
    *)
      die "batch-accounting-read-smoke accepts only --bank-year YYYY [--iterations N]"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.batch_accounting_read_smoke \
    "$@" --warmup 1 --target-ms 1000 --json
}

workbench_matching_retry() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "workbench-matching-retry requires release name"
  shift
  [[ "${1:-}" == "--scope-month" && "${2:-}" =~ ^[0-9]{4}-(0[1-9]|1[0-2])$ ]] || \
    die "workbench-matching-retry requires --scope-month YYYY-MM"
  case "${3:-}" in
    --dry-run)
      [[ "$#" -eq 3 ]] || die "workbench-matching-retry only permits dry-run or fingerprint-guarded execute"
      ;;
    --execute)
      [[ "$#" -eq 5 && "${4:-}" == "--expected-fingerprint" && "${5:-}" =~ ^[0-9a-f]{64}$ ]] || \
        die "workbench-matching-retry only permits dry-run or fingerprint-guarded execute"
      ;;
    *)
      die "workbench-matching-retry only permits dry-run or fingerprint-guarded execute"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.workbench_matching_scope_retry_ops "$@"
}

etc_deleted_batch_restore() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "etc-deleted-batch-restore requires release name"
  shift
  [[ "$#" -ge 9 ]] || die "etc-deleted-batch-restore requires exact batch, count, total, OA row and mode"
  [[ "${1:-}" == "--business-batch-id" && "${2:-}" =~ ^[A-Za-z0-9._:-]+$ ]] || die "invalid ETC business batch id"
  [[ "${3:-}" == "--expected-invoice-count" && "${4:-}" =~ ^[1-9][0-9]*$ ]] || die "invalid expected invoice count"
  [[ "${5:-}" == "--expected-total-amount" && "${6:-}" =~ ^[0-9]+([.][0-9]{1,2})?$ ]] || die "invalid expected total amount"
  [[ "${7:-}" == "--expected-oa-row-id" && "${8:-}" =~ ^[A-Za-z0-9._:-]+$ ]] || die "invalid expected OA row id"
  case "${9:-}" in
    --dry-run)
      [[ "$#" -eq 9 ]] || die "ETC restore dry-run accepts no additional arguments"
      ;;
    --execute)
      [[ "$#" -eq 15 && "${10:-}" == "--expected-fingerprint" && "${11:-}" =~ ^[0-9a-f]{64}$ ]] || \
        die "ETC restore execute requires the dry-run fingerprint"
      [[ "${12:-}" == "--operator" && -n "${13:-}" && "${14:-}" == "--reason" && -n "${15:-}" ]] || \
        die "ETC restore execute requires operator and reason"
      ;;
    *)
      die "ETC restore only permits dry-run or fingerprint-guarded execute"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.restore_deleted_etc_business_batch "$@"
}

etc_batch_invoice_link_backfill() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "etc-batch-invoice-link-backfill requires release name"
  shift
  [[ "${1:-}" == "--business-batch-id" && "${2:-}" =~ ^[A-Za-z0-9._:-]+$ ]] || die "invalid ETC business batch id"
  [[ "${3:-}" == "--limit" && "${4:-}" =~ ^[1-9][0-9]*$ ]] || die "invalid ETC backfill limit"
  case "${5:-}" in
    --dry-run)
      [[ "$#" -eq 5 ]] || die "ETC backfill dry-run accepts no additional arguments"
      set -- "${@:1:4}"
      ;;
    --apply)
      [[ "$#" -eq 11 && "${6:-}" == "--expected-auto-backfill-count" && "${7:-}" =~ ^[0-9]+$ ]] || \
        die "ETC backfill apply requires an expected strict candidate count"
      [[ "${8:-}" == "--operator" && -n "${9:-}" && "${10:-}" == "--reason" && -n "${11:-}" ]] || \
        die "ETC backfill apply requires operator and reason"
      ;;
    *)
      die "ETC backfill only permits dry-run or guarded apply"
      ;;
  esac
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.backfill_etc_batch_invoice_links "$@"
}

etc_submitted_batch_member_repair() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "etc-submitted-batch-member-repair requires release name"
  shift
  [[ "${1:-}" == "--business-batch-id" && "${2:-}" =~ ^[A-Za-z0-9._:-]+$ ]] || \
    die "invalid ETC business batch id"
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.repair_submitted_etc_batch_members "$@"
}

read_model_scope_contract() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "read-model-scope-contract requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" "$src/scripts/check-read-model-scope-contracts.py" "$@"
}

read_model_slo_smoke() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "read-model-slo-smoke requires release name"
  shift
  local arg src
  for arg in "$@"; do
    case "$arg" in
      --apply|--apply=*)
        die "read-model-slo-smoke only permits dry-run through deploy-control; run --apply only from an explicitly approved root session"
        ;;
    esac
  done
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.read_model_slo_smoke "$@"
}

write_operation_restore_point() {
  local release="${1:-}" run_id="${2:-}"
  [[ -n "$release" ]] || die "write-operation-restore-point requires release name"
  [[ "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] \
    || die "write-operation-restore-point run-id must be 1..80 safe filename characters"
  [[ $# -le 2 ]] || die "write-operation-restore-point accepts only release name and run-id"

  local src output_dir dump_path temp_path manifest_path checksum size created_at
  src="$(release_src "$release")"
  assert_runtime_env_contract
  [[ -f "$MIGRATOR_ENV" ]] || die "missing PostgreSQL migrator env: $MIGRATOR_ENV"
  command -v pg_dump >/dev/null || die "pg_dump is required for write-operation restore points"
  command -v pg_restore >/dev/null || die "pg_restore is required to verify write-operation restore points"
  install -d -m 0700 "$WRITE_E2E_BACKUP_ROOT"
  output_dir="$WRITE_E2E_BACKUP_ROOT/$run_id"
  if [[ -d "$output_dir" ]] && [[ -z "$(find "$output_dir" -mindepth 1 -maxdepth 1 -print -quit)" ]]; then
    rmdir -- "$output_dir"
  fi
  [[ ! -e "$output_dir" ]] || die "write-operation restore point already exists: $output_dir"
  install -d -m 0700 "$output_dir"
  dump_path="$output_dir/fin_ops.dump"
  temp_path="$output_dir/.fin_ops.dump.tmp"
  manifest_path="$output_dir/manifest.json"

  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    [[ -n "${FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL:-${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}}}" ]] \
      || die "PostgreSQL DSN is empty after loading runtime env"
    umask 077
    trap 'rm -f -- "$temp_path"; rmdir -- "$output_dir" 2>/dev/null || true' EXIT
    "$API_PYTHON" - "$temp_path" <<'PY'
import os
import subprocess
import sys

from psycopg.conninfo import conninfo_to_dict

database_url = (
    os.environ.get("FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL")
    or os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL")
    or os.environ.get("DATABASE_URL")
    or ""
).strip()
if database_url.startswith("postgresql+psycopg://"):
    database_url = "postgresql://" + database_url.removeprefix("postgresql+psycopg://")
parameters = conninfo_to_dict(database_url)
environment = {key: value for key, value in os.environ.items() if not key.startswith("PG")}
parameter_environment = {
    "host": "PGHOST",
    "hostaddr": "PGHOSTADDR",
    "port": "PGPORT",
    "dbname": "PGDATABASE",
    "user": "PGUSER",
    "password": "PGPASSWORD",
    "passfile": "PGPASSFILE",
    "connect_timeout": "PGCONNECT_TIMEOUT",
    "client_encoding": "PGCLIENTENCODING",
    "options": "PGOPTIONS",
    "sslmode": "PGSSLMODE",
    "sslcert": "PGSSLCERT",
    "sslkey": "PGSSLKEY",
    "sslpassword": "PGSSLPASSWORD",
    "sslrootcert": "PGSSLROOTCERT",
    "target_session_attrs": "PGTARGETSESSIONATTRS",
}
for parameter, environment_name in parameter_environment.items():
    value = parameters.get(parameter)
    if value is not None and str(value):
        environment[environment_name] = str(value)
environment["PGAPPNAME"] = "finops-write-operation-restore-point"
subprocess.run(
    ["pg_dump", "--format=custom", "--no-owner", "--no-acl", f"--file={sys.argv[1]}"],
    check=True,
    env=environment,
)
PY
    pg_restore --list "$temp_path" >/dev/null
    mv "$temp_path" "$dump_path"
    trap - EXIT
    checksum="$(sha256sum "$dump_path" | awk '{print $1}')"
    size="$(stat -c '%s' "$dump_path")"
    created_at="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    printf '{\n  "status": "created",\n  "run_id": "%s",\n  "release": "%s",\n  "created_at": "%s",\n  "dump_path": "%s",\n  "size_bytes": %s,\n  "sha256": "%s",\n  "format": "postgresql_custom"\n}\n' \
      "$run_id" "$release" "$created_at" "$dump_path" "$size" "$checksum" >"$manifest_path"
    cat "$manifest_path"
  )
}

write_operation_restore_point_delete() {
  local run_id="${1:-}" expected_checksum="${2:-}"
  [[ "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] \
    || die "write-operation-restore-point-delete run-id must be 1..80 safe filename characters"
  [[ "$expected_checksum" =~ ^[0-9a-f]{64}$ ]] \
    || die "write-operation-restore-point-delete requires a lowercase SHA-256 checksum"
  [[ $# -le 2 ]] || die "write-operation-restore-point-delete accepts only run-id and expected checksum"

  local output_dir dump_path manifest_path actual_checksum manifest_values manifest_run_id manifest_checksum
  output_dir="$WRITE_E2E_BACKUP_ROOT/$run_id"
  dump_path="$output_dir/fin_ops.dump"
  manifest_path="$output_dir/manifest.json"
  [[ -d "$output_dir" && ! -L "$output_dir" ]] || die "write-operation restore point directory is unavailable"
  [[ -f "$dump_path" && ! -L "$dump_path" ]] || die "write-operation restore point dump is unavailable"
  [[ -f "$manifest_path" && ! -L "$manifest_path" ]] || die "write-operation restore point manifest is unavailable"
  [[ "$(find "$output_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" == $'fin_ops.dump\nmanifest.json' ]] \
    || die "write-operation restore point directory contains unexpected files"
  actual_checksum="$(sha256sum "$dump_path" | awk '{print $1}')"
  [[ "$actual_checksum" == "$expected_checksum" ]] || die "write-operation restore point checksum mismatch"
  manifest_values="$($API_PYTHON - "$manifest_path" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
print(str(manifest.get("run_id") or ""), str(manifest.get("sha256") or ""))
PY
)"
  read -r manifest_run_id manifest_checksum <<<"$manifest_values"
  [[ "$manifest_run_id" == "$run_id" && "$manifest_checksum" == "$expected_checksum" ]] \
    || die "write-operation restore point manifest identity mismatch"
  rm -f -- "$dump_path" "$manifest_path"
  rmdir -- "$output_dir"
  printf '{"status":"deleted","run_id":"%s","sha256":"%s"}\n' "$run_id" "$expected_checksum"
}

write_operation_e2e_smoke() {
  local release="${1:-}" scenario="${2:-}" mode="${3:---dry-run}" preview_samples="${4:-1}"
  [[ -n "$release" ]] || die "write-operation-e2e-smoke requires release name"
  [[ -f "$scenario" && ! -L "$scenario" ]] || die "scenario must be a regular non-symlink file"
  if [[ "$scenario" =~ ^/tmp/finops-write-e2e-[A-Za-z0-9._-]+\.json$ ]]; then
    [[ "$(stat -c '%U' "$scenario")" == "finops-deploy" ]] \
      || die "temporary scenario must be owned by finops-deploy"
  elif [[ "$scenario" == "$STANDARD_WRITE_E2E_SCENARIO" ]]; then
    [[ "$(stat -c '%U:%a' "$scenario")" == "root:600" ]] \
      || die "standard scenario must be root-owned with mode 0600"
  else
    die "scenario path must be the fixed standard scenario or match /tmp/finops-write-e2e-*.json"
  fi
  [[ "$(stat -c '%s' "$scenario")" -le 1048576 ]] || die "scenario exceeds 1 MiB"
  find "$scenario" -maxdepth 0 -perm /022 -print -quit | grep -q . \
    && die "scenario must not be group/world writable"
  [[ "$mode" == "--dry-run" || "$mode" == "--apply-stdin" ]] || die "unsupported write-operation mode: $mode"
  [[ "$preview_samples" =~ ^[0-9]+$ && "$preview_samples" -ge 1 && "$preview_samples" -le 20 ]] \
    || die "preview samples must be an integer between 1 and 20"
  [[ $# -le 4 ]] || die "write-operation-e2e-smoke accepts at most four arguments"

  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
    export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    local apply_args=()
    local report_path runner_status
    report_path="$(mktemp /tmp/finops-write-e2e-report.XXXXXX.json)"
    trap 'rm -f -- "$report_path"' EXIT
    if [[ "$mode" == "--apply-stdin" ]]; then
      local admin_token approval_ticket
      IFS= read -r admin_token
      [[ -n "$admin_token" ]] || die "admin token stdin is empty"
      IFS= read -r approval_ticket
      [[ -n "$approval_ticket" ]] || die "write approval ticket stdin is empty"
      export FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$admin_token"
      export FIN_OPS_WRITE_E2E_APPROVAL_TICKET="$approval_ticket"
      apply_args=(--apply)
    fi
    cd "$src"
    if "$API_PYTHON" -m fin_ops_platform.tools.write_operation_e2e_smoke \
      --scenario "$scenario" \
      --base-url https://www.yn-sourcing.com \
      --api-prefix /fin-ops-api \
      --write-target-ms 5000 \
      --refresh-target-ms 30000 \
      --http-target-ms 1000 \
      --timeout-seconds 120 \
      --relation-preview-samples "$preview_samples" \
      --output "$report_path" \
      "${apply_args[@]}" >/dev/null; then
      runner_status=0
    else
      runner_status=$?
    fi
    [[ -s "$report_path" ]] || die "write-operation E2E runner did not produce a JSON report"
    cat -- "$report_path"
    exit "$runner_status"
  )
}

api_request_error() {
  local request_id="${1:-}"
  [[ "$request_id" =~ ^[0-9a-f]{12}$ ]] || die "request id must be 12 lowercase hexadecimal characters"
  [[ $# -le 1 ]] || die "api-request-error accepts only request id"
  local match
  match="$(journalctl -u fin-ops.service --since '2 hours ago' --no-pager -o cat \
    | grep -F "request_id=$request_id" | tail -n 1 || true)"
  [[ -n "$match" ]] || die "request error not found in the bounded journal window"
  printf '%s\n' "$match"
}

api_request_trace() {
  local request_id="${1:-}"
  [[ "$request_id" =~ ^[0-9a-f]{12}$ ]] || die "request id must be 12 lowercase hexadecimal characters"
  [[ $# -le 1 ]] || die "api-request-trace accepts only request id"
  local journal line_number trace
  journal="$(journalctl -u fin-ops.service --since '2 hours ago' --no-pager -o cat)"
  line_number="$(printf '%s\n' "$journal" | grep -n -F "request_id=$request_id" | tail -n 1 | cut -d: -f1 || true)"
  [[ "$line_number" =~ ^[0-9]+$ ]] || die "request trace not found in the bounded journal window"
  trace="$(
    printf '%s\n' "$journal" \
      | tail -n "+$line_number" \
      | awk '
          NR <= 64 {
            print
            if (NR > 1 && $0 ~ /^[A-Za-z_][A-Za-z0-9_.]*(Error|Exception)(:|$)/) {
              exit
            }
          }
        '
  )"
  [[ -n "$trace" ]] || die "request trace not found in the bounded journal window"
  printf '%s\n' "$trace"
}

api_request_timing() {
  local request_id="${1:-}"
  [[ "$request_id" =~ ^[0-9a-f]{12}$ ]] || die "request id must be 12 lowercase hexadecimal characters"
  [[ $# -le 1 ]] || die "api-request-timing accepts only request id"
  local matches
  matches="$(journalctl -u fin-ops.service --since '2 hours ago' --no-pager -o cat \
    | grep -F '"kind": "workbench_action_timing"' \
    | grep -F "\"request_id\": \"$request_id\"" \
    | tail -n 32 || true)"
  [[ -n "$matches" ]] || die "request timing not found in the bounded journal window"
  printf '%s\n' "$matches"
}

read_model_refresh() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "read-model-refresh requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.runtime_queue_ops \
    enqueue-read-model-refresh "$@"
}

settings_normalize() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "settings-normalize requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.settings_normalization_ops "$@"
}

import_audit_repair() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "import-audit-repair requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.import_audit_repair_ops "$@"
}

bank_transaction_category_repair() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "bank-transaction-category-repair requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.repair_unknown_bank_transaction_categories "$@"
}

runtime_queue_resolve_covered() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "runtime-queue-resolve-covered requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.runtime_queue_ops \
    resolve-covered-dead-letters "$@"
}

cmd="${1:-}"
case "$cmd" in
  check-release)
    src="$(release_src "${2:-}")"
    assert_runtime_env_contract
    echo "$src"
    ;;
  self-update)
    src="$(release_src "${2:-}")"
    install_deploy_control_helper "$src"
    install_runtime_worker_helper "$src"
    ;;
  activate)
    src="$(release_src "${2:-}")"
    install_deploy_control_helper "$src"
    install_runtime_worker_helper "$src"
    assert_runtime_env_contract
    sync_python_envs "$src"
    retire_unregistered_worker_services "$src"
    assert_retired_page_runtime_quiesced "$src"
    stop_runtime_worker_services_for_activation
    run_schema_migrations "$src"
    archive_legacy_current
    write_api_dropin "$src"
    write_worker_dropin "$src"
    write_dispatcher_dropin "$src"
    ensure_runtime_workers "$src"
    install_workbench_generation_retention "$src"
    install_runtime_queue_history_retention "$src"
    install_oa_sync_enqueue_timer "$src"
    publish_frontend "$src"
    restart_services
    wait_required_workers_ready
    status
    ;;
  workbench-rehydrate)
    shift
    workbench_rehydrate "$@"
    ;;
  workbench-audit-identity)
    shift
    workbench_audit_identity "$@"
    ;;
  workbench-requirement-repair)
    shift
    workbench_requirement_repair "$@"
    ;;
  workbench-etc-summary-repair)
    shift
    workbench_etc_summary_repair "$@"
    ;;
  batch-accounting-metadata-cleanup)
    shift
    batch_accounting_metadata_cleanup "$@"
    ;;
  batch-accounting-audit)
    shift
    batch_accounting_audit "$@"
    ;;
  domain-contract-audit)
    shift
    domain_contract_audit "$@"
    ;;
  batch-accounting-read-smoke)
    shift
    batch_accounting_read_smoke "$@"
    ;;
  workbench-matching-retry)
    shift
    workbench_matching_retry "$@"
    ;;
  etc-deleted-batch-restore)
    shift
    etc_deleted_batch_restore "$@"
    ;;
  etc-batch-invoice-link-backfill)
    shift
    etc_batch_invoice_link_backfill "$@"
    ;;
  etc-submitted-batch-member-repair)
    shift
    etc_submitted_batch_member_repair "$@"
    ;;
  read-model-scope-contract)
    shift
    read_model_scope_contract "$@"
    ;;
  read-model-slo-smoke)
    shift
    read_model_slo_smoke "$@"
    ;;
  write-operation-restore-point)
    shift
    write_operation_restore_point "$@"
    ;;
  write-operation-restore-point-delete)
    shift
    write_operation_restore_point_delete "$@"
    ;;
  write-operation-e2e-smoke)
    shift
    write_operation_e2e_smoke "$@"
    ;;
  api-request-error)
    shift
    api_request_error "$@"
    ;;
  api-request-trace)
    shift
    api_request_trace "$@"
    ;;
  api-request-timing)
    shift
    api_request_timing "$@"
    ;;
  read-model-refresh)
    shift
    read_model_refresh "$@"
    ;;
  settings-normalize)
    shift
    settings_normalize "$@"
    ;;
  import-audit-repair)
    shift
    import_audit_repair "$@"
    ;;
  bank-transaction-category-repair)
    shift
    bank_transaction_category_repair "$@"
    ;;
  runtime-queue-resolve-covered)
    shift
    runtime_queue_resolve_covered "$@"
    ;;
  restart)
    assert_runtime_env_contract
    restart_services
    status
    ;;
  status)
    status
    ;;
  cleanup-dropins)
    cleanup_dropins
    status
    ;;
  cleanup-releases)
    shift
    cleanup_releases "$@"
    ;;
  -h|--help|help|"")
    usage
    ;;
  *)
    usage >&2
    die "unknown command: $cmd"
    ;;
esac

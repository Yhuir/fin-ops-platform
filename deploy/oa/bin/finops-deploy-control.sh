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
  read-model-scope-contract <release-name> [args]
                                      check or repair read model scope contracts using runtime env
  read-model-slo-smoke <release-name> [args]
                                      run read model SLO smoke dry-run using runtime env; --apply is refused
  write-operation-e2e-smoke <release-name> <scenario-path> [--dry-run|--apply-stdin]
                                      run the fixed production relation runner; admin token is read from stdin
  read-model-refresh <release-name> [args]
                                      validate or enqueue read-model refresh scopes through the durable gateway
  settings-normalize <release-name> [--dry-run|--execute]
                                      normalize App settings through the canonical service/repository boundary
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

write_operation_e2e_smoke() {
  local release="${1:-}" scenario="${2:-}" mode="${3:---dry-run}"
  [[ -n "$release" ]] || die "write-operation-e2e-smoke requires release name"
  [[ "$scenario" =~ ^/tmp/finops-write-e2e-[A-Za-z0-9._-]+\.json$ ]] \
    || die "scenario path must match /tmp/finops-write-e2e-*.json"
  [[ -f "$scenario" && ! -L "$scenario" ]] || die "scenario must be a regular non-symlink file"
  [[ "$(stat -c '%U' "$scenario")" == "finops-deploy" ]] || die "scenario must be owned by finops-deploy"
  [[ "$(stat -c '%s' "$scenario")" -le 1048576 ]] || die "scenario exceeds 1 MiB"
  find "$scenario" -maxdepth 0 -perm /022 -print -quit | grep -q . \
    && die "scenario must not be group/world writable"
  [[ "$mode" == "--dry-run" || "$mode" == "--apply-stdin" ]] || die "unsupported write-operation mode: $mode"
  [[ $# -le 3 ]] || die "write-operation-e2e-smoke accepts no additional arguments"

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
    if [[ "$mode" == "--apply-stdin" ]]; then
      local admin_token
      IFS= read -r admin_token
      [[ -n "$admin_token" ]] || die "admin token stdin is empty"
      export FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$admin_token"
      apply_args=(--apply)
    fi
    cd "$src"
    "$API_PYTHON" -m fin_ops_platform.tools.write_operation_e2e_smoke \
      --scenario "$scenario" \
      --base-url https://www.yn-sourcing.com \
      --api-prefix /fin-ops-api \
      --write-target-ms 1000 \
      --http-target-ms 1000 \
      "${apply_args[@]}"
  )
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
  read-model-scope-contract)
    shift
    read_model_scope_contract "$@"
    ;;
  read-model-slo-smoke)
    shift
    read_model_slo_smoke "$@"
    ;;
  write-operation-e2e-smoke)
    shift
    write_operation_e2e_smoke "$@"
    ;;
  read-model-refresh)
    shift
    read_model_refresh "$@"
    ;;
  settings-normalize)
    shift
    settings_normalize "$@"
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

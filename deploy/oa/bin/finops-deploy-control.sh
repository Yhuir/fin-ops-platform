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

usage() {
  cat <<'USAGE'
usage: finops-deploy-control <command> [args]

commands:
  check-release <release-name>         validate a release under /opt/fin-ops/releases
  activate <release-name>              point API/workers/dispatcher at release and restart active services
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
Environment=FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION=1
ExecStart=
ExecStart=$WORKER_PYTHON -m fin_ops_platform.app.worker --worker-id \${FIN_OPS_WORKER_ID} --worker-kind \${FIN_OPS_WORKER_KIND} \$FIN_OPS_WORKER_ARGS --lock-timeout-seconds \${FIN_OPS_WORKER_LOCK_TIMEOUT_SECONDS} --task-timeout-seconds \${FIN_OPS_WORKER_TASK_TIMEOUT_SECONDS} --statement-timeout-seconds \${FIN_OPS_WORKER_STATEMENT_TIMEOUT_SECONDS} --max-attempts \${FIN_OPS_WORKER_MAX_ATTEMPTS} --max-events-per-iteration \${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}
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
Environment=PYTHONPATH=$src/backend/src
ExecStart=
ExecStart=$WORKER_PYTHON -m fin_ops_platform.app.rabbitmq_dispatcher --publisher-id rabbitmq-dispatcher-shadow-1 --batch-size 100 --lock-timeout-seconds 300 --retry-delay-seconds 60 --poll-interval-seconds 5
DROPIN
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

cmd="${1:-}"
case "$cmd" in
  check-release)
    src="$(release_src "${2:-}")"
    assert_runtime_env_contract
    echo "$src"
    ;;
  activate)
    src="$(release_src "${2:-}")"
    assert_runtime_env_contract
    sync_python_envs "$src"
    run_schema_migrations "$src"
    archive_legacy_current
    write_api_dropin "$src"
    write_worker_dropin "$src"
    write_dispatcher_dropin "$src"
    publish_frontend "$src"
    restart_services
    status
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

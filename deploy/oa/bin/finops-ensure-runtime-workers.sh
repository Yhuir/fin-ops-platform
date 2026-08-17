#!/usr/bin/env bash
set -euo pipefail

release_src="${1:-${RELEASE_SRC:-/opt/fin-ops/current}}"
systemd_dir="${FINOPS_SYSTEMD_DIR:-/etc/systemd/system}"
env_dir="${FINOPS_ENV_DIR:-/etc/fin-ops}"
worker_template="$release_src/deploy/oa/systemd/fin-ops-worker@.service.example"
worker_unit="$systemd_dir/fin-ops-worker@.service"
worker_python="${FINOPS_WORKER_PYTHON:-/opt/fin-ops/venv/bin/python}"
runtime_pythonpath="$release_src/backend/src"
required_workers="${FINOPS_REQUIRED_WORKERS:-}"
optional_workers="${FINOPS_OPTIONAL_WORKERS:-}"

fail() {
  printf 'finops-ensure-runtime-workers: %s\n' "$*" >&2
  exit 1
}

install_if_changed() {
  local source_file="$1"
  local target_file="$2"
  local mode="$3"
  local owner_group="$4"

  if [ ! -f "$source_file" ]; then
    fail "required source file is missing: $source_file"
  fi
  if [ -f "$target_file" ] && cmp -s "$source_file" "$target_file"; then
    return
  fi
  install -m "$mode" -o "${owner_group%%:*}" -g "${owner_group##*:}" "$source_file" "$target_file"
}

install_if_missing() {
  local source_file="$1"
  local target_file="$2"
  local mode="$3"
  local owner_group="$4"

  if [ ! -f "$source_file" ]; then
    fail "required source file is missing: $source_file"
  fi
  if [ -e "$target_file" ]; then
    return
  fi
  install -m "$mode" -o "${owner_group%%:*}" -g "${owner_group##*:}" "$source_file" "$target_file"
}

runtime_worker_manifest() {
  PYTHONPATH="$runtime_pythonpath${PYTHONPATH:+:$PYTHONPATH}" \
    "$worker_python" -m fin_ops_platform.tools.runtime_worker_manifest "$@"
}

worker_env_example() {
  runtime_worker_manifest --env-example "$1"
}

ensure_worker_env() {
  local worker="$1"
  local example_file target_file
  target_file="$env_dir/fin-ops.worker.${worker}.env"
  example_file="$(worker_env_example "$worker")"
  install_if_missing \
    "$release_src/deploy/oa/env/$example_file" \
    "$target_file" \
    0640 \
    root:fin-ops
}

migrate_legacy_worker_poll_interval() {
  local worker="$1"
  local example_file source_file target_file source_poll
  example_file="$(worker_env_example "$worker")"
  source_file="$release_src/deploy/oa/env/$example_file"
  target_file="$env_dir/fin-ops.worker.${worker}.env"
  [ -f "$target_file" ] || return 0
  source_poll="$(grep -oE -- "--poll-interval-seconds [0-9.]+" "$source_file" | awk '{print $2}' | tail -1 || true)"
  [ -n "$source_poll" ] || return 0
  if grep -Eq -- "--poll-interval-seconds (2|0\\.25|0\\.1|0\\.05)([^0-9.]|$)" "$target_file"; then
    sed -i -E "s/--poll-interval-seconds (2|0\\.25|0\\.1|0\\.05)([^0-9.]|$)/--poll-interval-seconds ${source_poll}\\2/g" "$target_file"
  fi
  if [ "$worker" = "workbench-matching" ] && grep -Eq -- "--poll-interval-seconds 5([^0-9.]|$)" "$target_file"; then
    sed -i -E "s/--poll-interval-seconds 5([^0-9.]|$)/--poll-interval-seconds ${source_poll}\\1/g" "$target_file"
  fi
}

migrate_retired_worker_runtime_env() {
  local worker="$1"
  local target_file temporary_file
  target_file="$env_dir/fin-ops.worker.${worker}.env"
  [ -f "$target_file" ] || return 0
  [ ! -L "$target_file" ] || fail "worker env must not be a symlink: $target_file"

  temporary_file="$(mktemp "$env_dir/.fin-ops.worker.${worker}.env.XXXXXX")"
  if ! awk '
    BEGIN { queue_backend_written = 0 }
    /^FIN_OPS_(RABBITMQ|REDIS)_[A-Z0-9_]*=/ { next }
    /^FIN_OPS_QUEUE_BACKEND=/ {
      if (!queue_backend_written) {
        print "FIN_OPS_QUEUE_BACKEND=postgres"
        queue_backend_written = 1
      }
      next
    }
    { print }
    END {
      if (!queue_backend_written) {
        print "FIN_OPS_QUEUE_BACKEND=postgres"
      }
    }
  ' "$target_file" > "$temporary_file"; then
    rm -f -- "$temporary_file"
    fail "failed to migrate retired worker runtime env: $target_file"
  fi

  chown --reference="$target_file" "$temporary_file"
  chmod --reference="$target_file" "$temporary_file"
  if cmp -s "$target_file" "$temporary_file"; then
    rm -f -- "$temporary_file"
    return 0
  fi
  mv -f -- "$temporary_file" "$target_file"
}

check_worker_registration() {
  local worker="$1"
  local check_args
  local -a runtime_args=()
  check_args="$(runtime_worker_manifest --worker-check-command "$worker")"
  (
    set -a
    # shellcheck disable=SC1091
    . "$env_dir/fin-ops.common.env"
    # shellcheck disable=SC1091
    . "$env_dir/fin-ops.secrets.env"
    if [ -f "$env_dir/fin-ops.worker.${worker}.env" ]; then
      # shellcheck disable=SC1090
      . "$env_dir/fin-ops.worker.${worker}.env"
    fi
    set +a
    export PYTHONPATH="$runtime_pythonpath${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    export FIN_OPS_WORKER_ID="${FIN_OPS_WORKER_ID:-$(hostname)-${worker}}"
    "$worker_python" -m fin_ops_platform.app.worker $check_args >/dev/null
    read -r -a runtime_args <<< "${FIN_OPS_WORKER_ARGS:-}"
    "$worker_python" -m fin_ops_platform.app.worker \
      --registration "$worker" \
      --worker-instance "$worker" \
      "${runtime_args[@]}" \
      --check >/dev/null
  )
}

if [ "$(id -u)" -ne 0 ]; then
  fail "must run as root"
fi
if [ ! -d "$release_src" ]; then
  fail "release source directory does not exist: $release_src"
fi
if [ ! -d "$runtime_pythonpath" ]; then
  fail "backend source directory does not exist: $runtime_pythonpath"
fi
if ! id -u fin-ops >/dev/null 2>&1; then
  fail "system user fin-ops does not exist"
fi
if ! getent group fin-ops >/dev/null 2>&1; then
  fail "system group fin-ops does not exist"
fi

install -d -m 0755 "$systemd_dir"
install -d -m 0750 -o root -g fin-ops "$env_dir"
install_if_changed "$worker_template" "$worker_unit" 0644 root:root

if [ -z "$required_workers" ]; then
  required_workers="$(runtime_worker_manifest --required-instances)"
fi

for worker in $required_workers $optional_workers; do
  ensure_worker_env "$worker"
  migrate_legacy_worker_poll_interval "$worker"
  migrate_retired_worker_runtime_env "$worker"
done

if [ ! -f "$env_dir/fin-ops.common.env" ]; then
  fail "missing $env_dir/fin-ops.common.env"
fi
if [ ! -f "$env_dir/fin-ops.secrets.env" ]; then
  fail "missing $env_dir/fin-ops.secrets.env"
fi
if ! grep -hE '^(FIN_OPS_POSTGRES_DATABASE_URL|DATABASE_URL)=' \
  "$env_dir/fin-ops.common.env" "$env_dir/fin-ops.secrets.env" >/dev/null; then
  fail "missing PostgreSQL DSN in fin-ops common/secrets env"
fi

systemctl daemon-reload

for worker in $required_workers $optional_workers; do
  worker_env_example "$worker" >/dev/null
  check_worker_registration "$worker"
  service_name="fin-ops-worker@${worker}.service"
  systemctl reset-failed "$service_name" >/dev/null 2>&1 || true
  systemctl enable "$service_name"
  systemctl restart "$service_name"
  systemctl is-active --quiet "$service_name"
done

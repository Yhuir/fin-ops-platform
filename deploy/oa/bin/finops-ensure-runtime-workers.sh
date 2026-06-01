#!/usr/bin/env bash
set -euo pipefail

release_src="${1:-${RELEASE_SRC:-/opt/fin-ops/current}}"
systemd_dir="${FINOPS_SYSTEMD_DIR:-/etc/systemd/system}"
env_dir="${FINOPS_ENV_DIR:-/etc/fin-ops}"
worker_template="$release_src/deploy/oa/systemd/fin-ops-worker@.service.example"
worker_unit="$systemd_dir/fin-ops-worker@.service"
required_workers="${FINOPS_REQUIRED_WORKERS:-oa-sync workbench workbench-matching bank-detail turnover-ledger search-pending invoice-usage-collection cost-tax import no-oa-bank-batch etc-business-oa-detection}"
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

worker_env_example() {
  case "$1" in
    oa-sync) printf '%s\n' "fin-ops.worker.oa-sync.env.example" ;;
    workbench) printf '%s\n' "fin-ops.worker.workbench.env.example" ;;
    workbench-matching) printf '%s\n' "fin-ops.worker.workbench-matching.env.example" ;;
    bank-account-balance) printf '%s\n' "fin-ops.worker.bank-account-balance.env.example" ;;
    bank-detail) printf '%s\n' "fin-ops.worker.bank-detail.env.example" ;;
    no-oa-bank-batch) printf '%s\n' "fin-ops.worker.no-oa-bank-batch.env.example" ;;
    turnover-ledger) printf '%s\n' "fin-ops.worker.turnover-ledger.env.example" ;;
    search-pending) printf '%s\n' "fin-ops.worker.search-pending.env.example" ;;
    invoice-usage-collection) printf '%s\n' "fin-ops.worker.invoice-usage-collection.env.example" ;;
    cost-tax) printf '%s\n' "fin-ops.worker.cost-tax.env.example" ;;
    import) printf '%s\n' "fin-ops.worker.import.env.example" ;;
    etc-business-oa-detection) printf '%s\n' "fin-ops.worker.etc-business-oa-detection.env.example" ;;
    file-migration) printf '%s\n' "fin-ops.worker.file-migration.env.example" ;;
    *) fail "unsupported worker instance: $1" ;;
  esac
}

ensure_worker_env() {
  local worker="$1"
  local example_file
  example_file="$(worker_env_example "$worker")"
  install_if_missing \
    "$release_src/deploy/oa/env/$example_file" \
    "$env_dir/fin-ops.worker.${worker}.env" \
    0640 \
    root:fin-ops
}

if [ "$(id -u)" -ne 0 ]; then
  fail "must run as root"
fi
if [ ! -d "$release_src" ]; then
  fail "release source directory does not exist: $release_src"
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

for worker in $required_workers $optional_workers; do
  ensure_worker_env "$worker"
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
  service_name="fin-ops-worker@${worker}.service"
  systemctl reset-failed "$service_name" >/dev/null 2>&1 || true
  systemctl enable "$service_name"
  systemctl restart "$service_name"
  systemctl is-active --quiet "$service_name"
done

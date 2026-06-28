#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage: scripts/verify.sh [backend|frontend|e2e|docs|runtime-check|infra-smoke|all]

backend   Run clean backend check and full backend unittest discovery.
frontend  Run frontend Vitest and production build.
e2e       Run deterministic Playwright browser smoke tests.
docs      Run lightweight documentation structure checks.
runtime-check
          Run app check against the current configured runtime state.
infra-smoke
          Run runtime smoke tooling checks. If real staging
          PostgreSQL/RabbitMQ env vars are present, also run real infra preflight.
          Always print the production external gate input preflight without secrets.
          Set FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS to run read-only
          write-operation SLO audits against recent real outbox events.
all       Run backend, frontend, deterministic browser e2e, and docs checks. This is the default.
USAGE
}

run_clean_app_check() {
  cd "$ROOT_DIR"
  local verify_data_dir
  verify_data_dir="$(mktemp -d)"
  trap 'rm -rf "$verify_data_dir"' RETURN
  FIN_OPS_DATA_DIR="$verify_data_dir" PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
  trap - RETURN
  rm -rf "$verify_data_dir"
}

run_runtime_check() {
  cd "$ROOT_DIR"
  PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
}

run_backend() {
  cd "$ROOT_DIR"
  run_clean_app_check
  PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
}

run_frontend() {
  cd "$ROOT_DIR/web"
  npm test -- --run
  npm run build
}

run_e2e() {
  cd "$ROOT_DIR/web"
  npm run e2e:smoke
}

run_docs() {
  cd "$ROOT_DIR"
  find docs -maxdepth 3 -type f -name '*.md' | sort >/tmp/fin_ops_docs_files.txt
  stale_refs="$(rg -n "docs/product/|OA 集成当前 app 技术方案" README.md docs backend web deploy -g '*.md' -g '!docs/dev/testing.md' || true)"
  if [[ -n "$stale_refs" ]]; then
    printf '%s\n' "$stale_refs"
    echo "Stale documentation reference found." >&2
    exit 1
  fi

  for required in \
    docs/dev/testing.md \
    docs/dev/nightly-ci.md \
    docs/dev/spec-first-e2e-audit.md \
    docs/dev/spec-first-e2e-inventory.md \
    docs/dev/testing-closure-state.md \
    docs/dev/testing-closure-dependency-map.md \
    docs/modules/README.md \
    .planning/README.md
  do
    if [[ ! -f "$required" ]]; then
      echo "Missing required documentation file: $required" >&2
      exit 1
    fi
  done

  if ! rg -q "不作为当前需求、架构、API 或验收事实源" .planning/README.md; then
    echo ".planning/README.md must state that GSD records are not current facts." >&2
    exit 1
  fi

  if ! rg -q "不作为当前 app 后端、API、read model、worker 或生产运行事实源" docs/refactor-ui/README.md; then
    echo "docs/refactor-ui/README.md must scope prompt/state files to UI migration only." >&2
    exit 1
  fi

  if ! rg -q "\.planning/.*不作为当前需求、架构、API 或验收事实源" docs/index.md; then
    echo "docs/index.md must document the .planning fact-source boundary." >&2
    exit 1
  fi

  while IFS= read -r module_readme; do
    module_dir="$(dirname "$module_readme")"
    for required in e2e-spec.md e2e-coverage.md; do
      if [[ ! -f "$module_dir/$required" ]]; then
        echo "Missing Spec-first E2E documentation file: $module_dir/$required" >&2
        exit 1
      fi
    done
  done < <(find docs/modules -mindepth 2 -maxdepth 2 -name README.md | sort)
}

run_infra_smoke() {
  cd "$ROOT_DIR"
  PYTHONPATH=backend/src python3 -m unittest \
    tests.test_runtime_sync_closure_gate \
    tests.test_write_operation_slo_audit \
    tests.test_production_external_gate_preflight \
    tests.test_rabbitmq_staging_preflight \
    tests.test_runtime_infrastructure_postgres_integration \
    tests.test_rabbitmq_integration \
    -v

  PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json

  if [[ -n "${FIN_OPS_TEST_DATABASE_URL:-}" && -n "${FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS:-}" ]]; then
    local write_operation_audit_args=(--json)
    local write_operation_seen=0
    local write_operation
    IFS=',' read -ra write_operations <<< "$FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS"
    for write_operation in "${write_operations[@]}"; do
      write_operation="${write_operation#"${write_operation%%[![:space:]]*}"}"
      write_operation="${write_operation%"${write_operation##*[![:space:]]}"}"
      if [[ -n "$write_operation" ]]; then
        write_operation_audit_args+=(--operation "$write_operation")
        write_operation_seen=1
      fi
    done
    if [[ "$write_operation_seen" != "1" ]]; then
      echo "FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS did not contain a valid operation profile." >&2
      exit 2
    fi
    write_operation_audit_args+=(--lookback-hours "${FIN_OPS_WRITE_OPERATION_AUDIT_LOOKBACK_HOURS:-24}")
    write_operation_audit_args+=(--target-ms "${FIN_OPS_WRITE_OPERATION_AUDIT_TARGET_MS:-5000}")
    if [[ -n "${FIN_OPS_WRITE_OPERATION_AUDIT_P99_TARGET_MS:-}" ]]; then
      write_operation_audit_args+=(--p99-target-ms "$FIN_OPS_WRITE_OPERATION_AUDIT_P99_TARGET_MS")
    fi
    if [[ -n "${FIN_OPS_WRITE_OPERATION_AUDIT_SINCE:-}" ]]; then
      write_operation_audit_args+=(--since "$FIN_OPS_WRITE_OPERATION_AUDIT_SINCE")
    fi
    echo "Running write_operation_slo_audit for: $FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS" >&2
    FIN_OPS_POSTGRES_DATABASE_URL="${FIN_OPS_POSTGRES_DATABASE_URL:-$FIN_OPS_TEST_DATABASE_URL}" \
      PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.write_operation_slo_audit \
      "${write_operation_audit_args[@]}"
  elif [[ -n "${FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS:-}" ]]; then
    echo "Skipping write_operation_slo_audit real operation check; FIN_OPS_TEST_DATABASE_URL is not set." >&2
  else
    echo "Skipping write_operation_slo_audit real operation check; set FIN_OPS_WRITE_OPERATION_AUDIT_OPERATIONS to audit recent real writes." >&2
  fi

  if [[ -n "${FIN_OPS_TEST_DATABASE_URL:-}" && -n "${RABBITMQ_TEST_URL:-}" ]]; then
    PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.run_rabbitmq_staging_preflight \
      --json
  else
    echo "Skipping RabbitMQ staging preflight; FIN_OPS_TEST_DATABASE_URL and/or RABBITMQ_TEST_URL are not set." >&2
  fi
}

target="${1:-all}"
case "$target" in
  backend)
    run_backend
    ;;
  frontend)
    run_frontend
    ;;
  e2e)
    run_e2e
    ;;
  docs)
    run_docs
    ;;
  runtime-check)
    run_runtime_check
    ;;
  infra-smoke)
    run_infra_smoke
    ;;
  all)
    run_backend
    run_frontend
    run_e2e
    run_docs
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac

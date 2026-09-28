#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage: scripts/verify.sh [lint|dependency-audit|backend|frontend|e2e|docs|runtime-check|infra-smoke|settings-acl-postgres|all]

lint      Run Ruff lint checks for backend Python code, tests, and scripts.
dependency-audit
          Fail when pinned backend dependencies contain known vulnerabilities.
backend   Run clean backend check and full backend unittest discovery.
frontend  Run frontend Vitest and production build.
e2e       Run deterministic Playwright browser smoke tests.
docs      Run lightweight documentation structure checks.
runtime-check
          Run app check against the current configured runtime state.
infra-smoke
          Run runtime and canonical API smoke tooling checks. If real staging
          When PostgreSQL test env vars are present, also run real infrastructure preflight.
          Always print the production external gate input preflight without secrets.
settings-acl-postgres
          Run settings ACL persistence and canonical migration tests against a visibly disposable PostgreSQL database.
all       Run backend, frontend, deterministic browser e2e, and docs checks. This is the default.
USAGE
}

run_clean_app_check() {
  cd "$ROOT_DIR"
  local verify_data_dir
  verify_data_dir="$(mktemp -d)"
  trap 'rm -rf "$verify_data_dir"' RETURN
  if [[ -z "${FIN_OPS_POSTGRES_DATABASE_URL:-${DATABASE_URL:-}}" ]]; then
    FIN_OPS_DATA_DIR="$verify_data_dir" PYTHONPATH=backend/src python3 - <<'PY'
from __future__ import annotations

from pathlib import Path
import os

from fin_ops_platform.app.server import build_application

try:
    build_application(data_dir=Path(os.environ["FIN_OPS_DATA_DIR"]))
except ValueError as exc:
    message = str(exc)
    if "requires FIN_OPS_APP_STORAGE_BACKEND=postgres" not in message:
        raise
else:
    raise AssertionError("Application unexpectedly started without PostgreSQL storage backend.")
PY
  else
    FIN_OPS_APP_STORAGE_BACKEND="${FIN_OPS_APP_STORAGE_BACKEND:-postgres}" \
      FIN_OPS_DATA_DIR="$verify_data_dir" \
      PYTHONPATH=backend/src \
      python3 -m fin_ops_platform.app.main --check
  fi
  trap - RETURN
  rm -rf "$verify_data_dir"
}

run_runtime_check() {
  cd "$ROOT_DIR"
  PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
}

run_settings_acl_postgres() {
  cd "$ROOT_DIR"
  if [[ -z "${FIN_OPS_TEST_DATABASE_URL:-}" ]]; then
    echo "FIN_OPS_TEST_DATABASE_URL is required for settings-acl-postgres." >&2
    exit 2
  fi
  FIN_OPS_REQUIRE_SETTINGS_ACL_POSTGRES=1 \
    PYTHONPATH=backend/src:tests \
    python3 -m unittest \
      tests.test_postgres_state_store_integration.PostgresStateStoreIntegrationTests.test_settings_acl_commit_lost_ack_reconciles_under_fresh_lock \
      tests.test_settings_access_control_postgres_integration.SettingsAccessControlPostgresIntegrationTests.test_0133_repairs_0132_order_and_enforces_exact_acl_shape \
      -v
}

run_backend() {
  cd "$ROOT_DIR"
  run_clean_app_check
  PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
}

run_lint() {
  cd "$ROOT_DIR"
  python3 -m ruff check backend/src tests scripts
}

run_dependency_audit() {
  cd "$ROOT_DIR"
  python3 -m pip_audit -r backend/requirements.txt --progress-spinner off
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
  python3 -m unittest tests.test_documentation -v
}

run_infra_smoke() {
  cd "$ROOT_DIR"
  PYTHONPATH=backend/src python3 -m unittest \
    tests.test_runtime_sync_closure_gate \
    tests.test_production_external_gate_preflight \
    tests.test_runtime_infrastructure_postgres_integration \
    -v

  PYTHONPATH=backend/src python3 -m fin_ops_platform.tools.production_external_gate_preflight --json
}

target="${1:-all}"
case "$target" in
  lint)
    run_lint
    ;;
  dependency-audit)
    run_dependency_audit
    ;;
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
  settings-acl-postgres)
    run_settings_acl_postgres
    ;;
  all)
    run_dependency_audit
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

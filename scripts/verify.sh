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

find_stale_doc_refs() {
  local pattern="$1"
  if command -v rg >/dev/null 2>&1; then
    rg -n "$pattern" README.md docs backend web deploy -g '*.md' -g '!docs/dev/testing.md'
    return
  fi
  git grep -n -E "$pattern" -- \
    README.md \
    ':(glob)docs/**/*.md' \
    ':(glob)backend/**/*.md' \
    ':(glob)web/**/*.md' \
    ':(glob)deploy/**/*.md' \
    ':(exclude)docs/dev/testing.md'
}

doc_file_matches() {
  local pattern="$1"
  local path="$2"
  if command -v rg >/dev/null 2>&1; then
    rg -q "$pattern" "$path"
    return
  fi
  grep -Eq "$pattern" "$path"
}

run_docs() {
  cd "$ROOT_DIR"
  stale_refs="$(find_stale_doc_refs "docs/product/|OA 集成当前 app 技术方案" || true)"
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

  if ! doc_file_matches "不作为当前需求、架构、API 或验收事实源" .planning/README.md; then
    echo ".planning/README.md must state that GSD records are not current facts." >&2
    exit 1
  fi

  if ! doc_file_matches "不作为当前 app 后端、API、read model、worker 或生产运行事实源" docs/refactor-ui/README.md; then
    echo "docs/refactor-ui/README.md must scope prompt/state files to UI migration only." >&2
    exit 1
  fi

  if ! doc_file_matches "\.planning/.*不作为当前需求、架构、API 或验收事实源" docs/index.md; then
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

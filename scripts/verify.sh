#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

usage() {
  cat <<'USAGE'
Usage: scripts/verify.sh [backend|frontend|docs|all]

backend   Run backend check and full backend unittest discovery.
frontend  Run frontend Vitest and production build.
docs      Run lightweight documentation structure checks.
all       Run backend, frontend, and docs checks. This is the default.
USAGE
}

run_backend() {
  cd "$ROOT_DIR"
  PYTHONPATH=backend/src python3 -m fin_ops_platform.app.main --check
  PYTHONPATH=backend/src python3 -m unittest discover -s tests -v
}

run_frontend() {
  cd "$ROOT_DIR/web"
  npm test -- --run
  npm run build
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
    docs/dev/testing-closure-state.md \
    docs/dev/testing-closure-dependency-map.md \
    docs/modules/README.md
  do
    if [[ ! -f "$required" ]]; then
      echo "Missing required documentation file: $required" >&2
      exit 1
    fi
  done
}

target="${1:-all}"
case "$target" in
  backend)
    run_backend
    ;;
  frontend)
    run_frontend
    ;;
  docs)
    run_docs
    ;;
  all)
    run_backend
    run_frontend
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

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
RABBITMQ_TOPOLOGY_ENV="${FINOPS_RABBITMQ_TOPOLOGY_ENV:-$ENV_DIR/fin-ops.rabbitmq-topology.env}"
RABBITMQ_MONITORING_ENV="${FINOPS_RABBITMQ_MONITORING_ENV:-$ENV_DIR/fin-ops.rabbitmq-monitoring.env}"
RABBITMQ_WORKER_ENV="${FINOPS_RABBITMQ_WORKER_ENV:-$ENV_DIR/fin-ops.rabbitmq-worker.env}"
RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT="${FINOPS_RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT:-/opt/fin-ops/backups/rabbitmq-worker-cutover}"
DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"
ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"
WRITE_E2E_BACKUP_ROOT="${FINOPS_WRITE_E2E_BACKUP_ROOT:-/opt/fin-ops/backups/write-operation-e2e}"
STANDARD_WRITE_E2E_SCENARIO="${FINOPS_STANDARD_WRITE_E2E_SCENARIO:-/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json}"
RELEASE_GATE_EVIDENCE_ROOT="${FINOPS_RELEASE_GATE_EVIDENCE_ROOT:-/opt/fin-ops/runtime-smoke/release-gates}"
SETTINGS_ACL_EVIDENCE_ROOT="${FINOPS_SETTINGS_ACL_EVIDENCE_ROOT:-/opt/fin-ops/evidence}"
SETTINGS_ACL_CONTRACT="settings-access-control-v1"
LEGACY_ADMIN_ENV="FIN_OPS_""ADMIN_USERNAMES"
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
  contract-version [--require VERSION] print or require the deploy-control safety contract
  candidate-status <release-name> --json
                                      validate candidate source and ACL safety fingerprints
  release-gate-profile <release-name> --json
                                      classify the exact candidate as frontend, runtime, or ACL
  settings-access-control-preflight <release-name> --http-tokens-stdin --dry-run --json
                                      write a secret-safe read-only DB/OA/session preflight artifact
  settings-access-control-post-deploy <release-name> --http-tokens-stdin --json
                                      verify the approved production ACL flow and restore the probe account
  repair-active-api-runtime            restore the API drop-in for exactly the active release
  rabbitmq-required-worker-cutover <release-name>
                                      switch exactly the required RabbitMQ-eligible workers, drain queues, rollback on failure
  release-gate-activate <release-name>
                                      auto-select frontend/runtime/ACL gate and activate exact release
  workbench-rehydrate <release-name> [args]
                                      rebuild Workbench SQL read models using runtime env
  oa-attachment-invoice-promotion <release-name> [args]
                                      dry-run/apply OA attachment invoice promotion using runtime env
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
  write-operation-e2e-scenario-install <release-name> <temporary-scenario-path>
                                      validate and atomically install the fixed root-owned write-smoke scenario
  write-operation-e2e-smoke <release-name> <scenario-path> [--dry-run|--apply-stdin] [preview-samples]
  api-request-error <request-id>
  api-request-trace <request-id>
  api-request-timing <request-id>
                                      run the fixed production relation runner; admin token is read from stdin
  read-model-refresh <release-name> [args]
                                      validate or enqueue read-model refresh scopes through the durable gateway
  settings-normalize <release-name> [--dry-run|--execute]
                                      normalize App settings through the canonical service/repository boundary
  import-audit-repair <release-name> [--dry-run|--execute --expected-fingerprint <sha256>] [--retire-etc-session-id <id> ...]
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

contract_version() {
  if [[ "$#" -eq 0 ]]; then
    printf '%s\n' "$SETTINGS_ACL_CONTRACT"
    return 0
  fi
  [[ "$#" -eq 2 && "$1" == "--require" ]] || die "contract-version accepts only --require VERSION"
  [[ "$2" == "$SETTINGS_ACL_CONTRACT" ]] \
    || die "required deploy-control contract $2 is unavailable"
  printf '%s\n' "$SETTINGS_ACL_CONTRACT"
}

candidate_status() {
  local release="${1:-}"
  [[ "$#" -eq 2 && "$2" == "--json" ]] || die "candidate-status requires release name and --json"
  local src active_releases
  src="$(release_src "$release")"
  active_releases="$(active_release_names)"
  ACTIVE_RELEASES="$active_releases" "$API_PYTHON" - "$src" "$release" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

src = Path(sys.argv[1])
release = sys.argv[2]

def sha256(path):
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()

EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

STRUCTURAL_DIRS = {Path("deploy"), Path("web")}

def source_tree_sha256(root):
    entries = []

    def visit(directory, relative_directory=Path()):
        for path in sorted(directory.iterdir(), key=lambda item: item.name):
            relative_path = relative_directory / path.name
            if (
                relative_path == Path("RELEASE.json")
                or any(part in EXCLUDED_PARTS for part in relative_path.parts)
                or relative_path.name.endswith((".pyc", ".pyo", ".DS_Store"))
            ):
                continue
            if relative_path not in STRUCTURAL_DIRS:
                entries.append((relative_path, path))
            if path.is_dir() and not path.is_symlink():
                visit(path, relative_path)

    visit(root)
    digest = hashlib.sha256()
    for relative_path, path in sorted(entries, key=lambda item: item[0].as_posix()):
        metadata = path.lstat()
        if path.is_symlink():
            kind = "symlink"
            payload = os.readlink(path).encode("utf-8")
        elif path.is_dir():
            kind = "directory"
            payload = b""
        elif path.is_file():
            kind = "file"
            payload = path.read_bytes()
        else:
            raise RuntimeError(f"unsupported release source entry: {path}")
        mode = stat.S_IMODE(metadata.st_mode)
        if kind == "directory":
            mode &= 0o777
        header = (
            f"{relative_path.as_posix()}\0{kind}\0{mode:04o}\0{len(payload)}\0"
        ).encode("utf-8")
        digest.update(header)
        digest.update(payload)
        digest.update(b"\0")
    return digest.hexdigest()

def facts(name):
    root = src.parents[1] / name / "src"
    metadata_path = root / "RELEASE.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.is_file() else {}
    contract = metadata.get("settings_access_control", {})
    migration = root / "backend/src/fin_ops_platform/postgres/migrations/0133_settings_access_control_canonical_order.sql"
    helper = root / "deploy/oa/bin/finops-deploy-control.sh"
    actual_migration = sha256(migration) if migration.is_file() else ""
    actual_helper = sha256(helper) if helper.is_file() else ""
    actual_source = source_tree_sha256(root) if root.is_dir() else ""
    safe = (
        metadata.get("release_name") == name
        and re.fullmatch(r"[0-9a-f]{40}", str(metadata.get("git_commit") or "")) is not None
        and metadata.get("git_status_porcelain") == ""
        and contract.get("capability") == "settings-access-control-v1"
        and contract.get("migration") == "0133_settings_access_control_canonical_order.sql"
        and contract.get("migration_sha256") == actual_migration
        and contract.get("deploy_control_sha256") == actual_helper
        and contract.get("source_sha256") == actual_source
    )
    fingerprint_source = {
        "release": name,
        "git_commit": metadata.get("git_commit"),
        "capability": contract.get("capability"),
        "migration_sha256": actual_migration,
        "deploy_control_sha256": actual_helper,
        "source_sha256": actual_source,
    }
    return {
        **fingerprint_source,
        "safe": safe,
        "fingerprint_sha256": hashlib.sha256(
            json.dumps(fingerprint_source, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest(),
    }

candidate = facts(release)
active = [facts(name) for name in os.environ.get("ACTIVE_RELEASES", "").splitlines() if name]
payload = {
    "contract": "settings-access-control-v1",
    "candidate": candidate,
    "active_releases": active,
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
raise SystemExit(0 if candidate["safe"] else 1)
PY
}

release_gate_profile() {
  local release="${1:-}"
  [[ "$#" -eq 2 && "$2" == "--json" ]] \
    || die "release-gate-profile requires release name and --json"
  local candidate_src previous_release active_count previous_src
  candidate_src="$(release_src "$release")"
  previous_release="$(active_release_names)"
  active_count="$(printf '%s\n' "$previous_release" | sed '/^$/d' | wc -l | tr -d ' ')"
  [[ "$active_count" == "1" ]] \
    || die "release profile requires exactly one active release, found $active_count"
  [[ "$previous_release" != "$release" ]] || die "candidate release is already active"
  previous_src="$(release_src "$previous_release")"
  "$API_PYTHON" - "$candidate_src" "$previous_src" "$release" "$previous_release" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

candidate = Path(sys.argv[1])
active = Path(sys.argv[2])
candidate_name = sys.argv[3]
active_name = sys.argv[4]

ACL_PATHS = (
    "backend/src/fin_ops_platform/app/auth.py",
    "backend/src/fin_ops_platform/app/route_access_policy.py",
    "backend/src/fin_ops_platform/app/routes_settings.py",
    "backend/src/fin_ops_platform/services/access_control_service.py",
    "backend/src/fin_ops_platform/services/oa_role_sync_service.py",
    "backend/src/fin_ops_platform/tools/settings_access_control_preflight.py",
    "backend/src/fin_ops_platform/postgres/migrations/0132_settings_access_control_guard.sql",
    "backend/src/fin_ops_platform/postgres/migrations/0133_settings_access_control_canonical_order.sql",
)
EXCLUDED_PARTS = {
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".runtime",
    ".venv",
    "__pycache__",
    "node_modules",
    "venv",
}

def entry_map(root, selected_paths=None, *, exclude_frontend=False):
    entries = {}

    def add(path, relative):
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            return
        if relative == Path("RELEASE.json"):
            return
        if exclude_frontend and relative.parts[:2] == ("web", "dist"):
            return
        if path.is_symlink():
            payload = os.readlink(path).encode("utf-8")
            kind = "symlink"
        elif path.is_file():
            payload = path.read_bytes()
            kind = "file"
        elif path.is_dir():
            for child in sorted(path.iterdir(), key=lambda item: item.name):
                add(child, relative / child.name)
            return
        else:
            payload = b""
            kind = "missing"
        mode = stat.S_IMODE(path.lstat().st_mode) if path.exists() or path.is_symlink() else 0
        entries[relative.as_posix()] = hashlib.sha256(
            f"{kind}\0{mode:04o}\0".encode("ascii") + payload
        ).hexdigest()

    if selected_paths is None:
        for child in sorted(root.iterdir(), key=lambda item: item.name):
            add(child, Path(child.name))
    else:
        for name in selected_paths:
            path = root / name
            if path.exists() or path.is_symlink():
                add(path, Path(name))
            else:
                entries[name] = "missing"
    return entries

def digest(entries):
    encoded = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()

candidate_acl = digest(entry_map(candidate, ACL_PATHS))
active_acl = digest(entry_map(active, ACL_PATHS))
candidate_runtime = digest(entry_map(candidate, exclude_frontend=True))
active_runtime = digest(entry_map(active, exclude_frontend=True))
candidate_frontend = digest(entry_map(candidate, ("web/dist",)))
active_frontend = digest(entry_map(active, ("web/dist",)))

acl_changed = candidate_acl != active_acl
runtime_changed = candidate_runtime != active_runtime
frontend_changed = candidate_frontend != active_frontend
profile = "acl" if acl_changed else "runtime" if runtime_changed or not frontend_changed else "frontend"
payload = {
    "contract": "release-gate-profile-v1",
    "candidate_release": candidate_name,
    "active_release": active_name,
    "profile": profile,
    "acl_changed": acl_changed,
    "runtime_changed": runtime_changed,
    "frontend_changed": frontend_changed,
    "digests": {
        "candidate_acl": candidate_acl,
        "active_acl": active_acl,
        "candidate_runtime": candidate_runtime,
        "active_runtime": active_runtime,
        "candidate_frontend": candidate_frontend,
        "active_frontend": active_frontend,
    },
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY
}

settings_acl_http_session_fact() {
  local token="$1"
  local credential_source="$2"
  local output="$3"
  local scratch="$4"
  local url="${5:-http://127.0.0.1:18001/api/session/me}"
  local header_file="$scratch/${credential_source}.header"
  local raw_file="$scratch/${credential_source}.raw.json"
  local status=0
  if [[ -n "$token" ]]; then
    printf 'Authorization: Bearer %s\n' "$token" >"$header_file"
    chmod 0600 "$header_file"
    status="$(
      curl --silent --show-error \
        --connect-timeout 5 --max-time 15 \
        --header "@$header_file" \
        --output "$raw_file" \
        --write-out '%{http_code}' \
        "$url" \
        || printf '0'
    )"
  fi
  HTTP_STATUS="$status" CREDENTIAL_SOURCE="$credential_source" \
    "$API_PYTHON" - "$raw_file" "$output" <<'PY'
import json
import os
from pathlib import Path
import sys

source = Path(sys.argv[1])
try:
    payload = json.loads(source.read_text(encoding="utf-8")) if source.is_file() else {}
except (OSError, ValueError):
    payload = {}
if not isinstance(payload, dict):
    payload = {}
try:
    status = int(os.environ.get("HTTP_STATUS") or 0)
except ValueError:
    status = 0
payload["_preflight_http_status"] = status
payload["_preflight_credential_source"] = os.environ["CREDENTIAL_SOURCE"]
Path(sys.argv[2]).write_text(json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8")
PY
}

settings_access_control_preflight() (
  local release="${1:-}"
  [[ "$#" -eq 4 && "$2" == "--http-tokens-stdin" && "$3" == "--dry-run" && "$4" == "--json" ]] \
    || die "settings-access-control-preflight requires release, --http-tokens-stdin, --dry-run, and --json"
  local src evidence_dir artifact scratch admin_token bearer_token
  local admin_session bearer_session deployment_facts
  src="$(release_src "$release")"
  assert_runtime_env_prerequisites
  evidence_dir="$SETTINGS_ACL_EVIDENCE_ROOT/$release"
  artifact="$evidence_dir/settings-access-control-preflight.json"
  install -d -m 0700 "$evidence_dir"
  scratch="$(mktemp -d /run/finops-settings-acl-preflight.XXXXXX)"
  chmod 0700 "$scratch"
  trap 'rm -rf -- "$scratch"' EXIT
  IFS= read -r admin_token || true
  IFS= read -r bearer_token || true
  admin_session="$scratch/admin-session.json"
  bearer_session="$scratch/bearer-session.json"
  deployment_facts="$scratch/deployment.json"
  settings_acl_http_session_fact "$admin_token" admin_stdin "$admin_session" "$scratch"
  settings_acl_http_session_fact "$bearer_token" dedicated_bearer_stdin "$bearer_session" "$scratch"
  unset admin_token bearer_token
  candidate_status "$release" --json >"$deployment_facts"
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$API_PYTHON" -m fin_ops_platform.tools.settings_access_control_preflight \
        --release "$release" \
        --admin-session-json "$admin_session" \
        --bearer-session-json "$bearer_session" \
        --deployment-facts-json "$deployment_facts" \
        --output "$artifact"
  )
  sha256sum "$artifact" >"$artifact.sha256"
  cat "$artifact"
)

settings_access_control_post_deploy() (
  local release="${1:-}"
  [[ "$#" -eq 3 && "$2" == "--http-tokens-stdin" && "$3" == "--json" ]] \
    || die "settings-access-control-post-deploy requires release, --http-tokens-stdin, and --json"
  local src evidence_dir preflight artifact status_file admin_token bearer_token candidate
  src="$(release_src "$release")"
  assert_runtime_env_contract
  evidence_dir="$SETTINGS_ACL_EVIDENCE_ROOT/$release"
  preflight="$evidence_dir/settings-access-control-preflight.json"
  artifact="$evidence_dir/settings-access-control-post-deploy.json"
  [[ -f "$preflight" && -f "$preflight.sha256" ]] || die "approved preflight artifact is missing"
  sha256sum --check "$preflight.sha256" >/dev/null
  status_file="$(mktemp /run/finops-settings-acl-postdeploy.XXXXXX)"
  trap 'rm -f -- "$status_file"' EXIT
  candidate_status "$release" --json >"$status_file"
  candidate="$release" "$API_PYTHON" - "$status_file" <<'PY'
import json
import os
from pathlib import Path
import sys

status = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
active = status.get("active_releases", [])
if status.get("candidate", {}).get("safe") is not True:
    raise SystemExit("active candidate is not ACL-safe")
if len(active) != 1 or active[0].get("release") != os.environ["candidate"] or active[0].get("safe") is not True:
    raise SystemExit("exact ACL-safe candidate is not the sole active release")
PY
  IFS= read -r admin_token || true
  IFS= read -r bearer_token || true
  local runner_status=0
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    printf '%s\n%s\n' "$admin_token" "$bearer_token" \
      | PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
        "$API_PYTHON" -m fin_ops_platform.tools.settings_access_control_preflight \
          --post-deploy \
          --release "$release" \
          --preflight-artifact "$preflight" \
          --oa-base-url "$FIN_OPS_OA_BASE_URL" \
          --output "$artifact"
  ) || runner_status=$?
  unset admin_token bearer_token
  [[ -f "$artifact" ]] || die "settings access-control post-deploy artifact was not created"
  sha256sum "$artifact" >"$artifact.sha256"
  cat "$artifact"
  exit "$runner_status"
)

assert_settings_access_control_preflight() (
  local release="$1"
  local evidence_dir="$SETTINGS_ACL_EVIDENCE_ROOT/$release"
  local artifact="$evidence_dir/settings-access-control-preflight.json"
  local current
  [[ -f "$artifact" && -f "$artifact.sha256" ]] || die "approved settings access-control preflight is missing"
  sha256sum --check "$artifact.sha256" >/dev/null
  current="$(mktemp /run/finops-settings-acl-candidate.XXXXXX)"
  trap 'rm -f -- "$current"' EXIT
  candidate_status "$release" --json >"$current"
  "$API_PYTHON" - "$artifact" "$current" <<'PY'
import json
from pathlib import Path
import sys

approved = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
current = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
if approved.get("eligible") is not True:
    raise SystemExit("settings access-control preflight is not steady-state eligible")
if approved.get("release") != current.get("candidate", {}).get("release"):
    raise SystemExit("settings access-control preflight release drifted")
if approved.get("deployment") != current:
    raise SystemExit("settings access-control candidate or active release fingerprint drifted")
PY
)

assert_settings_access_control_database_guard() (
  local src="$1"
  local release
  release="$(basename "$(dirname "$src")")"
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$API_PYTHON" -m fin_ops_platform.tools.settings_access_control_preflight \
        --release "$release" \
        --database-guard-only \
        --json
  )
)

release_is_acl_safe() {
  local release="$1"
  candidate_status "$release" --json >/dev/null 2>&1
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

required_worker_instances() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -m fin_ops_platform.tools.runtime_worker_manifest --required-instances
}

rabbitmq_required_worker_instances() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -m fin_ops_platform.tools.runtime_worker_manifest --rabbitmq-required-instances
}

rabbitmq_dispatch_event_types() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -m fin_ops_platform.tools.runtime_worker_manifest --rabbitmq-dispatch-event-types
}

known_worker_services() {
  {
    all_worker_services
    systemctl list-unit-files --no-legend 'fin-ops-worker@*.service' \
      | awk '{print $1}' \
      | grep -E '^fin-ops-worker@[-A-Za-z0-9_.]+\.service$' || true
  } | sort -u
}

worker_inventory_report() {
  local src="$1"
  local output="$2"
  local registered required active unknown missing service instance
  registered="$(registered_worker_instances "$src")"
  required="$(required_worker_instances "$src")"
  active="$(
    active_worker_services \
      | sed -E 's/^fin-ops-worker@//; s/\.service$//' \
      | tr '\n' ' '
  )"
  unknown=""
  while IFS= read -r service; do
    [[ -n "$service" ]] || continue
    instance="${service#fin-ops-worker@}"
    instance="${instance%.service}"
    if [[ " $registered " == *" $instance "* ]]; then
      continue
    fi
    unknown+=" $instance"
  done < <(known_worker_services)
  missing=""
  for instance in $required; do
    if [[ " $active " != *" $instance "* ]]; then
      missing+=" $instance"
    fi
  done
  REGISTERED_WORKERS="$registered" \
  REQUIRED_WORKERS="$required" \
  ACTIVE_WORKERS="$active" \
  UNKNOWN_WORKERS="$unknown" \
  MISSING_WORKERS="$missing" \
    "$API_PYTHON" - "$output" <<'PY'
import json
import os
import sys
from pathlib import Path

def words(name):
    return sorted(set(os.environ.get(name, "").split()))

unknown = words("UNKNOWN_WORKERS")
missing = words("MISSING_WORKERS")
payload = {
    "status": "PASS" if not unknown and not missing else "FAIL",
    "registered_workers": words("REGISTERED_WORKERS"),
    "required_workers": words("REQUIRED_WORKERS"),
    "active_workers": words("ACTIVE_WORKERS"),
    "unknown_workers": unknown,
    "missing_required_workers": missing,
    "unknown_worker_count": len(unknown),
    "required_worker_not_ready": len(missing),
}
Path(sys.argv[1]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
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

assert_runtime_env_prerequisites() {
  [[ -f "$COMMON_ENV" ]] || die "missing common runtime env: $COMMON_ENV"
  [[ -f "$SECRETS_ENV" ]] || die "missing secret runtime env: $SECRETS_ENV"
  assert_root_owned_runtime_env "$COMMON_ENV"
  assert_root_owned_runtime_env "$SECRETS_ENV"
  if ! grep -hE '^(FIN_OPS_POSTGRES_DATABASE_URL|DATABASE_URL)=' "$COMMON_ENV" "$SECRETS_ENV" >/dev/null; then
    die "missing PostgreSQL DSN in $COMMON_ENV or $SECRETS_ENV"
  fi
  local required_key
  for required_key in \
    FIN_OPS_OA_BASE_URL \
    FIN_OPS_OA_USER_INFO_PATH \
    FIN_OPS_OA_REQUIRED_PERMISSION \
    FIN_OPS_OA_ROLE_SYNC_ENABLED \
    FIN_OPS_OA_ROLE_SYNC_HOST \
    FIN_OPS_OA_ROLE_SYNC_DATABASE \
    FIN_OPS_OA_ROLE_SYNC_USERNAME \
    FIN_OPS_OA_ROLE_SYNC_PASSWORD; do
    if ! grep -hE "^${required_key}=" "$COMMON_ENV" "$SECRETS_ENV" >/dev/null; then
      die "missing OA session runtime env: $required_key in $COMMON_ENV or $SECRETS_ENV"
    fi
  done
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
    [[ "$FIN_OPS_OA_REQUIRED_PERMISSION" == "finops:app:view" ]] \
      || die "FIN_OPS_OA_REQUIRED_PERMISSION must equal finops:app:view"
    case "$FIN_OPS_OA_ROLE_SYNC_ENABLED" in
      1|true|TRUE|yes|YES|on|ON) ;;
      *) die "FIN_OPS_OA_ROLE_SYNC_ENABLED must be enabled for production release" ;;
    esac
    [[ -n "$FIN_OPS_OA_ROLE_SYNC_HOST" \
      && -n "$FIN_OPS_OA_ROLE_SYNC_DATABASE" \
      && -n "$FIN_OPS_OA_ROLE_SYNC_USERNAME" \
      && -n "$FIN_OPS_OA_ROLE_SYNC_PASSWORD" ]] \
      || die "OA role sync connection configuration is incomplete"
    [[ "${FIN_OPS_OA_ROLE_SYNC_PORT:-3306}" =~ ^[0-9]+$ ]] \
      || die "FIN_OPS_OA_ROLE_SYNC_PORT must be numeric"
    [[ "${FIN_OPS_OA_ROLE_SYNC_READONLY_ROLE_KEY:-finops_read_export}" == "finops_read_export" \
      && "${FIN_OPS_OA_ROLE_SYNC_FULL_ACCESS_ROLE_KEY:-finops_full_access}" == "finops_full_access" \
      && "${FIN_OPS_OA_ROLE_SYNC_ADMIN_ROLE_KEY:-finops_admin}" == "finops_admin" ]] \
      || die "OA role sync must use the three fixed fin-ops role keys"
  )
}

assert_runtime_env_contract() {
  assert_runtime_env_prerequisites
  local retired_key
  for retired_key in \
    FIN_OPS_ALLOWED_USERNAMES \
    FIN_OPS_ALLOWED_ROLES \
    FIN_OPS_READONLY_EXPORT_USERNAMES \
    "$LEGACY_ADMIN_ENV"; do
    if grep -hE "^${retired_key}=" "$COMMON_ENV" "$SECRETS_ENV" >/dev/null; then
      die "retired APP admission env must be absent: $retired_key"
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
  local api_exec_start
  if [[ -f "$src/backend/src/fin_ops_platform/app/wsgi.py" \
    && -f "$src/backend/src/fin_ops_platform/app/gunicorn_conf.py" ]]; then
    api_exec_start="$API_PYTHON -m gunicorn --config python:fin_ops_platform.app.gunicorn_conf fin_ops_platform.app.wsgi:application"
  else
    api_exec_start="$API_PYTHON -m fin_ops_platform.app.main --host 127.0.0.1 --port 18001"
  fi
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
RuntimeDirectory=fin-ops
RuntimeDirectoryMode=0750
ExecStart=
ExecStart=$api_exec_start
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
  local worker_services="${1:-}"
  if [[ -z "$worker_services" ]]; then
    worker_services="$(active_worker_services)"
  fi
  systemctl daemon-reload
  systemctl restart fin-ops.service
  local svc
  while IFS= read -r svc; do
    [[ -n "$svc" ]] || continue
    systemctl restart "$svc"
  done <<<"$worker_services"
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

assert_root_owned_runtime_env() {
  local path="$1"
  [[ -f "$path" && ! -L "$path" ]] || die "runtime env must be a regular non-symlink file: $path"
  [[ "$(stat -c '%u' "$path")" == "0" ]] || die "runtime env must be root-owned: $path"
  [[ -z "$(find "$path" -maxdepth 0 -perm /022 -print -quit)" ]] \
    || die "runtime env must not be group/world writable: $path"
}

write_rabbitmq_transport_env() {
  local path="$1"
  local temporary="${path}.rabbitmq-cutover.$$"
  if ! awk '!/^FIN_OPS_QUEUE_BACKEND=/' "$path" >"$temporary" \
    || ! printf '%s\n' 'FIN_OPS_QUEUE_BACKEND=rabbitmq' >>"$temporary" \
    || ! chown --reference="$path" "$temporary" \
    || ! chmod --reference="$path" "$temporary" \
    || ! mv -f "$temporary" "$path"; then
    rm -f -- "$temporary"
    return 1
  fi
}

restore_rabbitmq_worker_envs() {
  local backup_dir="$1"
  local instances="$2"
  local instance path
  for instance in $instances; do
    path="$ENV_DIR/fin-ops.worker.$instance.env"
    cp -a -- "$backup_dir/$(basename "$path")" "$path"
  done
  for instance in $instances; do
    systemctl restart "fin-ops-worker@$instance.service"
  done
}

wait_rabbitmq_required_queues_drained() {
  local src="$1"
  local event_types="$2"
  local timeout="${FINOPS_RABBITMQ_CUTOVER_TIMEOUT_SECONDS:-600}"
  local deadline status_json readiness_status=1
  [[ "$timeout" =~ ^[0-9]+$ ]] || die "invalid FINOPS_RABBITMQ_CUTOVER_TIMEOUT_SECONDS: $timeout"
  deadline=$((SECONDS + timeout))
  status_json=""
  while [ "$SECONDS" -lt "$deadline" ]; do
    readiness_status=0
    status_json="$(
      set -a
      # shellcheck disable=SC1090
      source "$COMMON_ENV"
      # shellcheck disable=SC1090
      source "$SECRETS_ENV"
      [[ -r "$RABBITMQ_MONITORING_ENV" ]] || exit 1
      # shellcheck disable=SC1090
      source "$RABBITMQ_MONITORING_ENV"
      set +a
      EXPECTED_EVENT_TYPES="$event_types" \
      PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$API_PYTHON" - <<'PY'
import json
import os
import sys

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository

connection = PostgresConnection(PostgresSettings.from_env())
runtime = RuntimeMonitoringRepository(connection).ready_health_summary()
queues = runtime.get("rabbitmq_queues")
if not isinstance(queues, dict):
    sys.exit(1)
expected = tuple(os.environ.get("EXPECTED_EVENT_TYPES", "").split())
missing = [event_type for event_type in expected if not isinstance(queues.get(event_type), dict)]
without_consumers = [
    event_type
    for event_type in expected
    if isinstance(queues.get(event_type), dict)
    and int(queues[event_type].get("consumers") or 0) <= 0
]
payload = {
    "missing_queue_metrics": missing,
    "queues_without_consumers": without_consumers,
    "rabbitmq_queue_depth": int(runtime.get("rabbitmq_queue_depth") or 0),
    "rabbitmq_unacked_messages": int(runtime.get("rabbitmq_unacked_messages") or 0),
    "rabbitmq_dlq_count": int(runtime.get("rabbitmq_dlq_count") or 0),
}
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
ready = (
    not missing
    and not without_consumers
    and payload["rabbitmq_queue_depth"] == 0
    and payload["rabbitmq_unacked_messages"] == 0
    and payload["rabbitmq_dlq_count"] == 0
    and not runtime.get("rabbitmq_metric_error")
)
sys.exit(0 if ready else 2)
PY
    )" || readiness_status="$?"
    case "$readiness_status" in
      0)
        printf 'RabbitMQ required queues drained: %s\n' "$status_json"
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
  printf 'RabbitMQ required queues did not drain within %s seconds: %s\n' "$timeout" "$status_json" >&2
  return 1
}

rabbitmq_required_worker_cutover() {
  local release="${1:-}"
  [[ -n "$release" && "$#" -eq 1 ]] || die "rabbitmq-required-worker-cutover accepts only release name"
  local src instances event_types backup_dir instance path
  src="$(release_src "$release")"
  assert_root_owned_runtime_env "$RABBITMQ_WORKER_ENV"
  grep -Eq '^RABBITMQ_URL=.+$' "$RABBITMQ_WORKER_ENV" \
    || die "missing RABBITMQ_URL in $RABBITMQ_WORKER_ENV"
  ! grep -Eq '^FIN_OPS_QUEUE_BACKEND=' "$RABBITMQ_WORKER_ENV" \
    || die "shared RabbitMQ env must not define FIN_OPS_QUEUE_BACKEND: $RABBITMQ_WORKER_ENV"
  instances="$(rabbitmq_required_worker_instances "$src")"
  event_types="$(rabbitmq_dispatch_event_types "$src")"
  [[ -n "$instances" ]] || die "registry returned no required RabbitMQ worker instances"
  [[ -n "$event_types" ]] || die "registry returned no RabbitMQ dispatcher event types"
  for instance in $instances; do
    path="$ENV_DIR/fin-ops.worker.$instance.env"
    assert_root_owned_runtime_env "$path"
  done
  backup_dir="$RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT/$(date -u +%Y%m%dT%H%M%SZ)-$$"
  install -d -m 0700 "$RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT" "$backup_dir"
  for instance in $instances; do
    path="$ENV_DIR/fin-ops.worker.$instance.env"
    cp -a -- "$path" "$backup_dir/$(basename "$path")"
  done
  if ! (
    set -Eeuo pipefail
    for instance in $instances; do
      write_rabbitmq_transport_env "$ENV_DIR/fin-ops.worker.$instance.env" || exit 1
    done
    for instance in $instances; do
      systemctl restart "fin-ops-worker@$instance.service" || exit 1
    done
    wait_required_workers_ready || exit 1
    wait_rabbitmq_required_queues_drained "$src" "$event_types" || exit 1
  ); then
    restore_rabbitmq_worker_envs "$backup_dir" "$instances"
    wait_required_workers_ready
    die "RabbitMQ worker cutover failed; original worker env files were restored from $backup_dir"
  fi
  printf 'RabbitMQ worker cutover passed; rollback backup retained at %s\n' "$backup_dir"
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

oa_attachment_invoice_promotion() {
  local release="${1:-}"
  [[ -n "$release" ]] || die "oa-attachment-invoice-promotion requires release name"
  shift
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  run_with_runtime_env "$src" -m fin_ops_platform.tools.oa_attachment_invoice_promotion "$@"
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

write_operation_e2e_scenario_install() {
  local release="${1:-}" scenario="${2:-}"
  [[ -n "$release" ]] || die "write-operation-e2e-scenario-install requires release name"
  [[ "$scenario" =~ ^/tmp/finops-write-e2e-[A-Za-z0-9._-]+\.json$ ]] \
    || die "temporary scenario path must match /tmp/finops-write-e2e-*.json"
  [[ -f "$scenario" && ! -L "$scenario" ]] || die "temporary scenario must be a regular non-symlink file"
  [[ "$(stat -c '%U' "$scenario")" == "finops-deploy" ]] \
    || die "temporary scenario must be owned by finops-deploy"
  [[ "$(stat -c '%s' "$scenario")" -le 1048576 ]] || die "temporary scenario exceeds 1 MiB"
  find "$scenario" -maxdepth 0 -perm /022 -print -quit | grep -q . \
    && die "temporary scenario must not be group/world writable"
  [[ $# -eq 2 ]] || die "write-operation-e2e-scenario-install accepts only release name and scenario path"

  local src target_dir staged backup validation
  src="$(release_src "$release")"
  validation="$(
    PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$API_PYTHON" - "$scenario" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

from fin_ops_platform.tools.runtime_sync_closure_gate import _load_write_scenarios

path = Path(sys.argv[1])
scenarios, error = _load_write_scenarios(path, http_target_ms=1000.0)
if error is not None or not scenarios:
    raise SystemExit(
        "write-operation scenario validation failed: "
        + json.dumps(error or {"error": "empty_scenarios"}, ensure_ascii=False, sort_keys=True)
    )
print(
    json.dumps(
        {
            "status": "valid",
            "scenario_count": len(scenarios),
            "scenario_names": [str(scenario.name) for scenario in scenarios],
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
)
PY
  )"

  target_dir="$(dirname "$STANDARD_WRITE_E2E_SCENARIO")"
  [[ ! -L "$target_dir" ]] || die "write-operation scenario directory must not be a symlink"
  install -d -m 0700 -o root -g root "$target_dir"
  staged="$(mktemp "$target_dir/.write-operation-e2e-scenarios.XXXXXX")"
  backup="$STANDARD_WRITE_E2E_SCENARIO.previous"
  [[ ! -L "$backup" ]] || die "write-operation scenario backup must not be a symlink"
  if ! install -m 0600 -o root -g root "$scenario" "$staged"; then
    rm -f -- "$staged"
    die "failed to stage validated write-operation scenario"
  fi
  if [[ -f "$STANDARD_WRITE_E2E_SCENARIO" && ! -L "$STANDARD_WRITE_E2E_SCENARIO" ]]; then
    install -m 0600 -o root -g root "$STANDARD_WRITE_E2E_SCENARIO" "$backup"
  elif [[ -L "$STANDARD_WRITE_E2E_SCENARIO" ]]; then
    rm -f -- "$staged"
    die "write-operation scenario target must not be a symlink"
  fi
  mv -f -- "$staged" "$STANDARD_WRITE_E2E_SCENARIO"
  printf '%s\n' "$validation"
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

activate_release() {
  local release="$1"
  local release_profile="${2:-runtime}"
  local src active_workers
  [[ "$release_profile" == "frontend" || "$release_profile" == "runtime" || "$release_profile" == "acl" ]] \
    || die "unsupported activation profile: $release_profile"
  src="$(release_src "$release")"
  assert_runtime_env_contract
  active_workers="$(active_worker_services)"
  systemctl stop fin-ops.service
  stop_runtime_worker_services_for_activation
  if [[ "$release_profile" == "frontend" ]]; then
    write_api_dropin "$src"
    write_worker_dropin "$src"
    write_dispatcher_dropin "$src"
    publish_frontend "$src"
    restart_services "$active_workers"
    wait_required_workers_ready
    status
    return 0
  fi
  run_schema_migrations "$src"
  assert_settings_access_control_database_guard "$src"
  sync_python_envs "$src"
  install_runtime_worker_helper "$src"
  retire_unregistered_worker_services "$src"
  assert_retired_page_runtime_quiesced "$src"
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
}

repair_active_api_runtime() {
  [[ "$#" -eq 0 ]] || die "repair-active-api-runtime accepts no arguments"
  local release active_count src
  release="$(active_release_names)"
  active_count="$(printf '%s\n' "$release" | sed '/^$/d' | wc -l | tr -d ' ')"
  [[ "$active_count" == "1" ]] \
    || die "API runtime repair requires exactly one active release, found $active_count"
  src="$(release_src "$release")"
  assert_runtime_env_contract
  write_api_dropin "$src"
  systemctl daemon-reload
  systemctl reset-failed fin-ops.service || true
  systemctl restart fin-ops.service
  wait_required_workers_ready
  status
}

release_gate_frontend_checkpoint() (
  local release="$1"
  local label="$2"
  local admin_token="$3"
  local evidence_dir="$4"
  local src checkpoint_dir scratch inventory_report candidate_report
  local health_body health_metrics public_body public_metrics asset_url asset_body asset_metrics
  local session_report active_releases dist_match=false
  src="$(release_src "$release")"
  checkpoint_dir="$evidence_dir/$label"
  install -d -m 0700 "$checkpoint_dir"
  scratch="$(mktemp -d /run/finops-frontend-gate.XXXXXX)"
  chmod 0700 "$scratch"
  trap 'rm -rf -- "$scratch"' EXIT
  inventory_report="$checkpoint_dir/worker-inventory.json"
  candidate_report="$checkpoint_dir/candidate-status.json"
  session_report="$scratch/session.json"
  health_body="$scratch/health.json"
  public_body="$scratch/index.html"
  asset_body="$scratch/asset"
  worker_inventory_report "$src" "$inventory_report"
  candidate_status "$release" --json >"$candidate_report"
  active_releases="$(active_release_names)"
  if diff -qr -- "$src/web/dist" "$FRONTEND_DIR" >/dev/null; then
    dist_match=true
  fi
  if ! health_metrics="$(curl --silent --show-error --connect-timeout 5 --max-time 15 \
    --output "$health_body" --write-out '%{http_code} %{time_total}' \
    http://127.0.0.1:18001/health/ready)"; then
    health_metrics="0 0"
  fi
  settings_acl_http_session_fact \
    "$admin_token" release_gate_005 "$session_report" "$scratch" \
    https://www.yn-sourcing.com/fin-ops/api/session/me
  if ! public_metrics="$(curl --silent --show-error --location --connect-timeout 5 --max-time 15 \
    --output "$public_body" --write-out '%{http_code} %{time_total}' \
    https://www.yn-sourcing.com/fin-ops/)"; then
    public_metrics="0 0"
  fi
  asset_url="$(grep -oE '/fin-ops/assets/[^"[:space:]]+' "$public_body" | head -n 1 || true)"
  asset_metrics="0 0"
  if [[ -n "$asset_url" ]]; then
    if ! asset_metrics="$(curl --silent --show-error --location --connect-timeout 5 --max-time 15 \
      --output "$asset_body" --write-out '%{http_code} %{time_total}' \
      "https://www.yn-sourcing.com${asset_url}")"; then
      asset_metrics="0 0"
    fi
  fi
  RELEASE_NAME="$release" \
  CHECKPOINT_LABEL="$label" \
  ACTIVE_RELEASES="$active_releases" \
  DIST_MATCH="$dist_match" \
  HEALTH_METRICS="$health_metrics" \
  PUBLIC_METRICS="$public_metrics" \
  ASSET_METRICS="$asset_metrics" \
  ASSET_URL="$asset_url" \
  INVENTORY_REPORT="$inventory_report" \
  CANDIDATE_REPORT="$candidate_report" \
  SESSION_REPORT="$session_report" \
  HEALTH_BODY="$health_body" \
    "$API_PYTHON" - "$checkpoint_dir/checkpoint.json" <<'PY'
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

def load(path):
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}

def metric(name):
    parts = os.environ.get(name, "0 0").split()
    try:
        status = int(parts[0])
        elapsed_ms = round(float(parts[1]) * 1000, 3)
    except (IndexError, ValueError):
        status, elapsed_ms = 0, 0.0
    return {"http_status": status, "elapsed_ms": elapsed_ms}

inventory = load(os.environ["INVENTORY_REPORT"])
candidate = load(os.environ["CANDIDATE_REPORT"])
session = load(os.environ["SESSION_REPORT"])
health = load(os.environ["HEALTH_BODY"])
health_request = metric("HEALTH_METRICS")
public_request = metric("PUBLIC_METRICS")
asset_request = metric("ASSET_METRICS")
user = session.get("user", {}) if isinstance(session.get("user"), dict) else {}
active_releases = [item for item in os.environ.get("ACTIVE_RELEASES", "").splitlines() if item]
checks = {
    "active_release_exact": active_releases == [os.environ["RELEASE_NAME"]],
    "candidate_safe": candidate.get("candidate", {}).get("safe") is True,
    "worker_inventory": inventory.get("status") == "PASS",
    "health_ready": health_request["http_status"] == 200 and health.get("status") == "ready",
    "admin_session": (
        int(session.get("_preflight_http_status") or 0) == 200
        and user.get("username") == "YNSYLP005"
        and session.get("allowed") is True
        and session.get("access_tier") == "admin"
        and session.get("can_admin_access") is True
    ),
    "public_index": public_request["http_status"] == 200,
    "public_asset": bool(os.environ.get("ASSET_URL")) and asset_request["http_status"] == 200,
    "published_dist_exact": os.environ.get("DIST_MATCH") == "true",
}
passed = all(checks.values())
payload = {
    "release_gate_status": "PASS" if passed else "FAIL",
    "release_name": os.environ["RELEASE_NAME"],
    "checkpoint": os.environ["CHECKPOINT_LABEL"],
    "profile": "frontend",
    "checked_at": datetime.now(UTC).isoformat(),
    "frontend_verified": passed,
    "checks": checks,
    "timings_ms": {
        "health_ready": health_request["elapsed_ms"],
        "admin_session": None,
        "public_index": public_request["elapsed_ms"],
        "public_asset": asset_request["elapsed_ms"],
    },
    "public_asset_path": os.environ.get("ASSET_URL") or None,
    "unknown_worker_count": int(inventory.get("unknown_worker_count") or 0),
    "required_worker_not_ready": int(inventory.get("required_worker_not_ready") or 0),
    "reports": {
        "worker_inventory": os.environ["INVENTORY_REPORT"],
        "candidate_status": os.environ["CANDIDATE_REPORT"],
    },
}
Path(sys.argv[1]).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
raise SystemExit(0 if passed else 1)
PY
)

release_gate_checkpoint() {
  local release="$1"
  local label="$2"
  local admin_token="$3"
  local evidence_dir="$4"
  local profile="${5:-full}"
  local verification_release="${6:-$release}"
  local src verification_src checkpoint_dir rabbit_report domain_report closure_report inventory_report runtime_report
  local required_worker_instance
  local -a closure_args
  [[ "$profile" == "preflight" || "$profile" == "full" || "$profile" == "stability" ]] \
    || die "unsupported release gate profile: $profile"
  src="$(release_src "$release")"
  verification_src="$(release_src "$verification_release")"
  checkpoint_dir="$evidence_dir/$label"
  rabbit_report="$checkpoint_dir/rabbitmq-topology.json"
  domain_report="$checkpoint_dir/domain-contract-audit.json"
  closure_report="$checkpoint_dir/runtime-sync-closure.json"
  inventory_report="$checkpoint_dir/worker-inventory.json"
  runtime_report="$checkpoint_dir/runtime-health.json"
  install -d -m 0700 "$checkpoint_dir"
  worker_inventory_report "$src" "$inventory_report"
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    [[ -r "$RABBITMQ_TOPOLOGY_ENV" ]] \
      || die "RabbitMQ topology env is missing or unreadable: $RABBITMQ_TOPOLOGY_ENV"
    # shellcheck disable=SC1090
    source "$RABBITMQ_TOPOLOGY_ENV"
    set +a
    export PYTHONPATH="$verification_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    cd "$verification_src"
    "$API_PYTHON" -m fin_ops_platform.app.rabbitmq_topology --apply >"$rabbit_report"
  ) || true
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    set +a
    export PYTHONPATH="$verification_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    cd "$verification_src"
    "$API_PYTHON" -m fin_ops_platform.tools.domain_contract_audit >"$domain_report"
  ) || true
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    [[ -r "$RABBITMQ_MONITORING_ENV" ]] \
      || die "RabbitMQ monitoring env is missing or unreadable: $RABBITMQ_MONITORING_ENV"
    # shellcheck disable=SC1090
    source "$RABBITMQ_MONITORING_ENV"
    set +a
    export PYTHONPATH="$verification_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    export FIN_OPS_HTTP_SLO_ADMIN_TOKEN="$admin_token"
    export FIN_OPS_E2E_ADMIN_TOKEN="$admin_token"
    cd "$verification_src"
    closure_args=(
      --base-url http://127.0.0.1:18001
      --page-base-url https://www.yn-sourcing.com
      --api-prefix ""
      --profile "$profile"
      --apply-read-model-smoke
      --read-model-target-ms 5000
      --write-target-ms 5000
      --http-target-ms 1000
      --health-ready-target-ms 1000
      --timeout-seconds 120
      --output "$closure_report"
    )
    if [[ "$profile" == "preflight" ]]; then
      for required_worker_instance in $(required_worker_instances "$src"); do
        closure_args+=(--required-worker-instance "$required_worker_instance")
      done
    fi
    "$API_PYTHON" -m fin_ops_platform.tools.runtime_sync_closure_gate "${closure_args[@]}" >/dev/null
  ) || true
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    [[ -r "$RABBITMQ_MONITORING_ENV" ]] \
      || die "RabbitMQ monitoring env is missing or unreadable: $RABBITMQ_MONITORING_ENV"
    # shellcheck disable=SC1090
    source "$RABBITMQ_MONITORING_ENV"
    set +a
    export PYTHONPATH="$verification_src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    "$API_PYTHON" - "$runtime_report" <<'PY'
import json
from pathlib import Path
import sys

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository

connection = PostgresConnection(PostgresSettings.from_env())
summary = RuntimeMonitoringRepository(connection).ready_health_summary()
Path(sys.argv[1]).write_text(
    json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True, default=str) + "\n",
    encoding="utf-8",
)
PY
  ) || true
  RELEASE_NAME="$release" \
  CHECKPOINT_LABEL="$label" \
  CHECKPOINT_PROFILE="$profile" \
  RABBIT_REPORT="$rabbit_report" \
  DOMAIN_REPORT="$domain_report" \
  CLOSURE_REPORT="$closure_report" \
  INVENTORY_REPORT="$inventory_report" \
  RUNTIME_REPORT="$runtime_report" \
    "$API_PYTHON" - "$checkpoint_dir/checkpoint.json" <<'PY'
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

def load(name):
    path = Path(os.environ[name])
    if not path.is_file():
        return {"status": "missing", "path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {"status": "invalid", "path": str(path), "error": str(exc)}

inventory = load("INVENTORY_REPORT")
rabbit = load("RABBIT_REPORT")
domain = load("DOMAIN_REPORT")
closure = load("CLOSURE_REPORT")
runtime = load("RUNTIME_REPORT")
closure_checks = closure.get("checks", []) if isinstance(closure, dict) else []
runtime_checks = [
    check
    for check in closure_checks
    if isinstance(check, dict)
    and str(check.get("name") or "").startswith("runtime_health")
]
terminal_publish_reconciliation_count = sum(
    int((check.get("payload") or {}).get("reconciled_completed_publish_states") or 0)
    for check in runtime_checks
    if isinstance(check.get("payload"), dict)
)
terminal_publish_reconciliation_stable = all(
    (check.get("payload") or {}).get("terminal_publish_reconciliation_stable") is True
    for check in runtime_checks
    if isinstance(check.get("payload"), dict)
)
closure_failures = []
for check in closure_checks:
    if not isinstance(check, dict) or check.get("status") == "pass":
        continue
    check_payload = check.get("payload", {}) if isinstance(check.get("payload"), dict) else {}
    blockers = check_payload.get("blockers", {}) if isinstance(check_payload.get("blockers"), dict) else {}
    audit = (
        check_payload
        if check.get("name") == "page_canonical_audit"
        else check_payload.get("page_canonical_audit", {})
        if isinstance(check_payload.get("page_canonical_audit"), dict)
        else {}
    )
    diagnostic_keys = (
        "summary",
        "failed_count",
        "failed_scenario_count",
        "failed_probe_count",
        "auth_configured",
        "failed_results",
        "slowest_results",
        "failed_probes",
        "slowest_probes",
        "snapshot",
    )
    diagnostics = {
        key: check_payload.get(key)
        for key in diagnostic_keys
        if key in check_payload
    }
    closure_failures.append(
        {
            "name": check.get("name"),
            "status": check.get("status"),
            "detail": check.get("detail"),
            "error": check_payload.get("error"),
            "blocker_keys": sorted(str(key) for key in blockers),
            "page_canonical_audit": {
                "status": audit.get("status"),
                "audit_count": audit.get("audit_count"),
                "error": audit.get("error"),
            }
            if audit
            else None,
            "diagnostics": diagnostics or None,
        }
    )
page_audit_check = next(
    (
        check
        for check in closure.get("checks", [])
        if isinstance(check, dict) and check.get("name") == "page_canonical_audit"
    ),
    {},
) if isinstance(closure, dict) else {}
page_canonical_audit = (
    page_audit_check.get("payload", {})
    if isinstance(page_audit_check, dict)
    else {}
)
page_canonical_audit_ready = (
    isinstance(page_canonical_audit, dict)
    and page_canonical_audit.get("status") == "pass"
    and int(page_canonical_audit.get("audit_count") or 0) > 0
)
profile = os.environ["CHECKPOINT_PROFILE"]
page_canonical_audit_required = True
queue_backlog = runtime.get("queue_backlog", {}) if isinstance(runtime, dict) else {}
dirty_scopes = runtime.get("dirty_scopes", {}) if isinstance(runtime, dict) else {}
publish_status = runtime.get("rabbitmq_publish_status", {}) if isinstance(runtime, dict) else {}
pending = (
    sum(int(queue_backlog.get(status) or 0) for status in ("pending", "processing"))
    if isinstance(queue_backlog, dict)
    else -1
)
publishing = int(publish_status.get("publishing") or 0) if isinstance(publish_status, dict) else -1
failed = int(queue_backlog.get("failed") or 0) if isinstance(queue_backlog, dict) else -1
durable_dead_letters = int(queue_backlog.get("dead_lettered") or 0) if isinstance(queue_backlog, dict) else -1
rabbitmq_metrics_ready = (
    isinstance(runtime, dict)
    and runtime.get("rabbitmq_management_configured") is True
    and not runtime.get("rabbitmq_metric_error")
    and "rabbitmq_dlq_count" in runtime
)
rabbitmq_dead_letters = int(runtime.get("rabbitmq_dlq_count") or 0) if rabbitmq_metrics_ready else -1
dead_letters = (
    durable_dead_letters + rabbitmq_dead_letters
    if durable_dead_letters >= 0 and rabbitmq_dead_letters >= 0
    else -1
)
dirty = sum(int(value or 0) for value in dirty_scopes.values()) if isinstance(dirty_scopes, dict) else -1
passed = (
    inventory.get("status") == "PASS"
    and rabbit.get("status") == "applied"
    and domain.get("status") == "pass"
    and closure.get("status") == "pass"
    and (page_canonical_audit_ready or not page_canonical_audit_required)
    and rabbitmq_metrics_ready
    and pending == 0
    and publishing == 0
    and failed == 0
    and dead_letters == 0
    and dirty == 0
)
payload = {
    "release_gate_status": "PASS" if passed else "FAIL",
    "release_name": os.environ["RELEASE_NAME"],
    "checkpoint": os.environ["CHECKPOINT_LABEL"],
    "profile": profile,
    "checked_at": datetime.now(UTC).isoformat(),
    "component_statuses": {
        "worker_inventory": inventory.get("status"),
        "rabbitmq_topology": rabbit.get("status"),
        "domain_contract_audit": domain.get("status"),
        "runtime_sync_closure": closure.get("status"),
        "page_canonical_audit": page_canonical_audit.get("status"),
        "rabbitmq_metrics": "pass" if rabbitmq_metrics_ready else "fail",
    },
    "unknown_worker_count": int(inventory.get("unknown_worker_count") or 0),
    "required_worker_not_ready": int(inventory.get("required_worker_not_ready") or 0),
    "dirty_scope_count": dirty,
    "pending_outbox_count": pending,
    "publishing_outbox_count": publishing,
    "failed_outbox_count": failed,
    "durable_dead_letter_count": durable_dead_letters,
    "rabbitmq_dead_letter_count": rabbitmq_dead_letters,
    "dead_letter_count": dead_letters,
    "terminal_publish_reconciliation_count": terminal_publish_reconciliation_count,
    "terminal_publish_reconciliation_stable": terminal_publish_reconciliation_stable,
    "runtime_sync_closure_failed_checks": [
        failure.get("name") for failure in closure_failures
    ],
    "runtime_sync_closure_failures": closure_failures,
    "page_canonical_audit": page_canonical_audit,
    "reports": {
        "worker_inventory": os.environ["INVENTORY_REPORT"],
        "rabbitmq_topology": os.environ["RABBIT_REPORT"],
        "domain_contract_audit": os.environ["DOMAIN_REPORT"],
        "runtime_health": os.environ["RUNTIME_REPORT"],
        "runtime_sync_closure": os.environ["CLOSURE_REPORT"],
    },
}
output = Path(sys.argv[1])
output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
sys.exit(0 if passed else 1)
PY
}

write_release_gate_evidence() {
  local release="$1"
  local previous_release="$2"
  local evidence_dir="$3"
  local gate_status="$4"
  local rolled_back="$5"
  local release_profile="$6"
  local failure_checkpoint="${7:-}"
  RELEASE_NAME="$release" \
  PREVIOUS_RELEASE="$previous_release" \
  EVIDENCE_DIR="$evidence_dir" \
  GATE_STATUS="$gate_status" \
  ROLLED_BACK="$rolled_back" \
  RELEASE_PROFILE="$release_profile" \
  FAILURE_CHECKPOINT="$failure_checkpoint" \
    "$API_PYTHON" - "$RELEASE_ROOT/$release/src/RELEASE.json" "$evidence_dir/evidence.json" <<'PY'
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import sys

release_meta = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = Path(os.environ["EVIDENCE_DIR"])
checkpoints = {}
for label in ("pre", "t0", "t60", "t300", "rollback"):
    path = root / label / "checkpoint.json"
    if path.is_file():
        checkpoints[label] = json.loads(path.read_text(encoding="utf-8"))
latest = next((checkpoints[name] for name in ("t300", "t60", "t0", "pre") if name in checkpoints), {})
t0_page_audit = checkpoints.get("t0", {}).get("page_canonical_audit", {})
pre_dlq = int(checkpoints.get("pre", {}).get("dead_letter_count", 0))
final_dlq = int(latest.get("dead_letter_count", pre_dlq))
profile = os.environ["RELEASE_PROFILE"]
required_final_checkpoint = "t0" if profile == "frontend" else "t300"
passed = os.environ["GATE_STATUS"] == "PASS" and required_final_checkpoint in checkpoints
payload = {
    "release_gate_status": "PASS" if passed else "FAIL",
    "release_name": os.environ["RELEASE_NAME"],
    "git_commit": release_meta.get("git_commit"),
    "release_profile": profile,
    "previous_release": os.environ["PREVIOUS_RELEASE"],
    "generated_at": datetime.now(UTC).isoformat(),
    "rolled_back": os.environ["ROLLED_BACK"] == "true",
    "failure_checkpoint": os.environ.get("FAILURE_CHECKPOINT") or None,
    "unknown_worker_count": int(latest.get("unknown_worker_count", -1)),
    "required_worker_not_ready": int(latest.get("required_worker_not_ready", -1)),
    "dirty_scope_count": int(latest.get("dirty_scope_count", -1)),
    "pending_outbox_count": int(latest.get("pending_outbox_count", -1)),
    "publishing_outbox_count": int(latest.get("publishing_outbox_count", -1)),
    "dead_letter_delta": final_dlq - pre_dlq,
    "terminal_publish_reconciliation_count": sum(
        int(checkpoint.get("terminal_publish_reconciliation_count") or 0)
        for checkpoint in checkpoints.values()
    ),
    "terminal_publish_reconciliation_stable": all(
        checkpoint.get("terminal_publish_reconciliation_stable") is True
        for checkpoint in checkpoints.values()
    ),
    "page_canonical_audit_status": (
        t0_page_audit.get("status")
        if isinstance(t0_page_audit, dict)
        else None
    ),
    "frontend_verified": latest.get("frontend_verified") is True if profile == "frontend" else None,
    "queue_stable_after_300_seconds": passed if profile != "frontend" else None,
    "checkpoints": checkpoints,
}
output = Path(sys.argv[2])
temporary = output.with_suffix(".tmp")
temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
temporary.replace(output)
output.chmod(0o600)
PY
}

rollback_release_gate() {
  local candidate="$1"
  local previous_release="$2"
  local admin_token="$3"
  local evidence_dir="$4"
  local failure_checkpoint="$5"
  local release_profile="$6"
  local rolled_back=false
  cat "$evidence_dir/$failure_checkpoint/checkpoint.json" >&2 || true
  if [[ "$release_profile" == "acl" ]]; then
    systemctl stop fin-ops.service || true
    stop_runtime_worker_services_for_activation || true
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "ACL release gate failed at $failure_checkpoint; production remains in maintenance for forward repair"
  fi
  if ! release_is_acl_safe "$previous_release"; then
    systemctl stop fin-ops.service || true
    stop_runtime_worker_services_for_activation || true
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "release gate failed at $failure_checkpoint; previous release lacks $SETTINGS_ACL_CONTRACT, production remains in maintenance for forward repair"
  fi
  if (activate_release "$previous_release" "$release_profile"); then
    if [[ "$release_profile" == "frontend" ]]; then
      release_gate_frontend_checkpoint \
        "$previous_release" rollback "$admin_token" "$evidence_dir" && rolled_back=true
    elif release_gate_checkpoint \
      "$previous_release" rollback "$admin_token" "$evidence_dir" preflight "$candidate"; then
      rolled_back=true
    fi
  fi
  write_release_gate_evidence \
    "$candidate" "$previous_release" "$evidence_dir" FAIL "$rolled_back" "$release_profile" "$failure_checkpoint"
  [[ "$rolled_back" == true ]] \
    || die "release gate failed at $failure_checkpoint and automatic rollback validation also failed"
  die "release gate failed at $failure_checkpoint; previous release $previous_release was restored"
}

release_gate_activate() {
  local release="${1:-}"
  [[ -n "$release" && "$#" -eq 1 ]] || die "release-gate-activate accepts only release name"
  local admin_token previous_release active_count evidence_dir profile_report release_profile
  release_src "$release" >/dev/null
  assert_runtime_env_contract
  candidate_status "$release" --json >/dev/null
  IFS= read -r admin_token
  [[ -n "$admin_token" ]] || die "production admin token stdin is empty"
  previous_release="$(active_release_names)"
  active_count="$(printf '%s\n' "$previous_release" | sed '/^$/d' | wc -l | tr -d ' ')"
  [[ "$active_count" == "1" ]] \
    || die "release gate requires exactly one active release, found $active_count"
  [[ "$previous_release" != "$release" ]] || die "candidate release is already active"
  profile_report="$(mktemp /run/finops-release-profile.XXXXXX)"
  trap 'rm -f -- "$profile_report"' EXIT
  release_gate_profile "$release" --json >"$profile_report"
  release_profile="$("$API_PYTHON" - "$profile_report" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profile = payload.get("profile")
if profile not in {"frontend", "runtime", "acl"}:
    raise SystemExit("release profile is invalid")
print(profile)
PY
)"
  evidence_dir="$RELEASE_GATE_EVIDENCE_ROOT/$release"
  [[ ! -e "$evidence_dir" ]] || die "release gate evidence already exists: $evidence_dir"
  install -d -m 0700 "$evidence_dir"
  install -m 0600 "$profile_report" "$evidence_dir/profile.json"
  if [[ "$release_profile" == "frontend" ]]; then
    if ! release_gate_frontend_checkpoint \
      "$previous_release" pre "$admin_token" "$evidence_dir"; then
      cat "$evidence_dir/pre/checkpoint.json" >&2
      write_release_gate_evidence \
        "$release" "$previous_release" "$evidence_dir" FAIL false "$release_profile" pre
      die "current production runtime failed the frontend pre-activation release gate"
    fi
  elif ! release_gate_checkpoint \
    "$previous_release" pre "$admin_token" "$evidence_dir" preflight "$release"; then
    cat "$evidence_dir/pre/checkpoint.json" >&2
    write_release_gate_evidence \
      "$release" "$previous_release" "$evidence_dir" FAIL false "$release_profile" pre
    die "current production runtime failed the pre-activation release gate"
  fi
  if ! (activate_release "$release" "$release_profile"); then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" activation "$release_profile"
  fi
  if [[ "$release_profile" == "frontend" ]]; then
    if ! release_gate_frontend_checkpoint "$release" t0 "$admin_token" "$evidence_dir"; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t0 "$release_profile"
    fi
  else
    if ! release_gate_checkpoint "$release" t0 "$admin_token" "$evidence_dir" full; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t0 "$release_profile"
    fi
    sleep 60
    if ! release_gate_checkpoint "$release" t60 "$admin_token" "$evidence_dir" stability; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t60 "$release_profile"
    fi
    sleep 240
    if ! release_gate_checkpoint "$release" t300 "$admin_token" "$evidence_dir" stability; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t300 "$release_profile"
    fi
  fi
  if ! write_release_gate_evidence \
    "$release" "$previous_release" "$evidence_dir" PASS false "$release_profile"; then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" evidence "$release_profile"
  fi
  if ! "$API_PYTHON" - "$evidence_dir/evidence.json" <<'PY'
import json
from pathlib import Path
import sys

evidence = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
profile = evidence.get("release_profile")
required = {
    "release_gate_status": "PASS",
    "release_profile": profile,
    "unknown_worker_count": 0,
    "required_worker_not_ready": 0,
}
if profile == "frontend":
    required["frontend_verified"] = True
elif profile in {"runtime", "acl"}:
    required.update(
        {
            "dirty_scope_count": 0,
            "pending_outbox_count": 0,
            "publishing_outbox_count": 0,
            "dead_letter_delta": 0,
            "terminal_publish_reconciliation_stable": True,
            "page_canonical_audit_status": "pass",
            "queue_stable_after_300_seconds": True,
        }
    )
else:
    raise SystemExit(f"unsupported release evidence profile: {profile!r}")
violations = {
    key: {"expected": value, "actual": evidence.get(key)}
    for key, value in required.items()
    if evidence.get(key) != value
}
if violations:
    raise SystemExit(
        "release gate evidence contract failed: "
        + json.dumps(violations, ensure_ascii=False, sort_keys=True)
    )
print(json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True))
PY
  then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" evidence_contract "$release_profile"
  fi
  rm -f -- "$profile_report"
  trap - EXIT
}
cmd="${1:-}"
case "$cmd" in
  check-release)
    src="$(release_src "${2:-}")"
    assert_runtime_env_prerequisites
    echo "$src"
    ;;
  contract-version)
    shift
    contract_version "$@"
    ;;
  candidate-status)
    shift
    candidate_status "$@"
    ;;
  release-gate-profile)
    shift
    release_gate_profile "$@"
    ;;
  settings-access-control-preflight)
    shift
    settings_access_control_preflight "$@"
    ;;
  settings-access-control-post-deploy)
    shift
    settings_access_control_post_deploy "$@"
    ;;
  repair-active-api-runtime)
    shift
    repair_active_api_runtime "$@"
    ;;
  rabbitmq-required-worker-cutover)
    shift
    rabbitmq_required_worker_cutover "$@"
    ;;
  release-gate-activate)
    shift
    release_gate_activate "$@"
    ;;
  workbench-rehydrate)
    shift
    workbench_rehydrate "$@"
    ;;
  oa-attachment-invoice-promotion)
    shift
    oa_attachment_invoice_promotion "$@"
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
  write-operation-e2e-scenario-install)
    shift
    write_operation_e2e_scenario_install "$@"
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

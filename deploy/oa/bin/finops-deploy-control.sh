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
RABBITMQ_DISPATCHER_ENV="${FINOPS_RABBITMQ_DISPATCHER_ENV:-$ENV_DIR/fin-ops.rabbitmq-dispatcher.env}"
RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT="${FINOPS_RABBITMQ_WORKER_CUTOVER_BACKUP_ROOT:-/opt/fin-ops/backups/rabbitmq-worker-cutover}"
DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"
ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"
WRITE_E2E_BACKUP_ROOT="${FINOPS_WRITE_E2E_BACKUP_ROOT:-/opt/fin-ops/backups/write-operation-e2e}"
STANDARD_WRITE_E2E_SCENARIO="${FINOPS_STANDARD_WRITE_E2E_SCENARIO:-/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json}"
RELEASE_GATE_EVIDENCE_ROOT="${FINOPS_RELEASE_GATE_EVIDENCE_ROOT:-/opt/fin-ops/runtime-smoke/release-gates}"
SCHEMA_COMPATIBILITY_EVIDENCE_ROOT="${FINOPS_SCHEMA_COMPATIBILITY_EVIDENCE_ROOT:-/opt/fin-ops/runtime-smoke/schema-compatibility}"
SETTINGS_ACL_EVIDENCE_ROOT="${FINOPS_SETTINGS_ACL_EVIDENCE_ROOT:-/opt/fin-ops/evidence}"
SETTINGS_ACL_CONTRACT="settings-access-control-v1"
LEGACY_ADMIN_ENV="FIN_OPS_""ADMIN_USERNAMES"
PRUNE_WORKBENCH_GENERATIONS_HELPER="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_HELPER:-/usr/local/sbin/finops-prune-workbench-generations}"
PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT:-/etc/systemd/system/finops-prune-workbench-generations.service}"
PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT="${FINOPS_PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT:-/etc/systemd/system/finops-prune-workbench-generations.timer}"
WORKBENCH_PAGE_WORKER_ENV="${FINOPS_WORKBENCH_PAGE_WORKER_ENV:-$ENV_DIR/fin-ops.worker.workbench.env}"
WORKBENCH_PAGE_WORKER_UNIT="${FINOPS_WORKBENCH_PAGE_WORKER_UNIT:-/etc/systemd/system/fin-ops-worker@workbench.service}"
WORKBENCH_PAGE_WORKER_ROLLBACK_DIRNAME="workbench-page-worker-runtime"
WORKBENCH_PAGE_WORKER_ROLLBACK_ENV_BASENAME="fin-ops.worker.workbench.env"
WORKBENCH_PAGE_WORKER_ROLLBACK_METADATA_BASENAME="fin-ops.worker.workbench.env.json"
RETIRED_WORKBENCH_PAGE_OBSERVER_PID=""
RETIRED_WORKBENCH_PAGE_OBSERVER_STOP_PATH=""
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
  schema-compatibility-plan <release-name> --json
                                      compare exact candidate migrations with production schema and active release
  schema-compatibility-evidence-install <release-name> --stdin
                                      validate and atomically install previous-code/candidate-schema test evidence
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
  workbench-audit-identity <release-name> [args]
                                      run Workbench object identity audit using runtime env
  workbench-requirement-repair <release-name> --dry-run
  workbench-requirement-repair <release-name> --execute --expected-fingerprint <sha256>
  workbench-requirement-repair <release-name> --rollback-dry-run --expected-fingerprint <sha256>
  workbench-requirement-repair <release-name> --rollback --expected-fingerprint <sha256>
                                      backfill missing historical OA/invoice requirement proof through relation commands
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
  settings-data-reset-restore-point <release-name> <run-id> <action> <operator>
                                      create, verify and bind a fresh restore point to one exact settings reset impact
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
  import-audit-repair <release-name> [--dry-run|--execute --expected-fingerprint <sha256>] [--retire-etc-session-id <id> ...] [--normalize-reverted-batch-id <id> ...] [--discover-recover-import-job-id <id>] [--recover-import-job-id <id> --recover-event-id <id> --recover-background-job-id <id> --recover-session-id <id> --recover-file-id <id> ...] [--repair-bank-source <session>=<file,...> ... --expected-bank-target-count <n> --expected-bank-protected-count <n> --expected-bank-duplicate-delete-count <n> --expected-bank-replay-create-count <n> --expected-bank-replay-repaired-duplicate-count <n> --operator-id <id> [--cleanup-related-bank-duplicates --expected-bank-category-cleanup-count <n> --expected-bank-workbench-withdraw-count <n> --expected-bank-workbench-transaction-id <id>]]
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
  [[ -f "$src/backend/requirements-audit.txt" ]] || die "backend audit requirements not found in release: $src"
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

schema_compatibility_plan() {
  local release="${1:-}"
  [[ "$#" -eq 2 && "$2" == "--json" ]] \
    || die "schema-compatibility-plan requires release name and --json"
  local candidate_src previous_release active_count previous_src
  candidate_status "$release" --json >/dev/null
  candidate_src="$(release_src "$release")"
  previous_release="$(active_release_names)"
  active_count="$(printf '%s\n' "$previous_release" | sed '/^$/d' | wc -l | tr -d ' ')"
  [[ "$active_count" == "1" ]] \
    || die "schema compatibility requires exactly one active release, found $active_count"
  [[ "$previous_release" != "$release" ]] || die "candidate release is already active"
  previous_src="$(release_src "$previous_release")"
  [[ -f "$MIGRATOR_ENV" ]] || die "missing PostgreSQL migrator env: $MIGRATOR_ENV"
  set -a
  # shellcheck disable=SC1090
  source "$MIGRATOR_ENV"
  set +a
  CANDIDATE_RELEASE="$release" PREVIOUS_RELEASE="$previous_release" \
  PYTHONPATH="$candidate_src/backend/src" \
    "$API_PYTHON" - "$candidate_src" "$previous_src" <<'PY'
import hashlib
import json
import os
from pathlib import Path
import re

from fin_ops_platform.postgres.migrate import (
    database_url_from_env_or_arg,
    discover_migrations,
    fetch_applied_migrations,
    is_accepted_checksum_drift,
    load_accepted_checksum_drifts,
    run_psql,
)

candidate_src = Path(__import__("sys").argv[1])
previous_src = Path(__import__("sys").argv[2])
filename_pattern = re.compile(r"^(?P<version>\d{4})_[a-z0-9_]+\.sql$")


def metadata(root):
    return json.loads((root / "RELEASE.json").read_text(encoding="utf-8"))


def schema_contract(root):
    entries = []
    migrations_dir = root / "backend/src/fin_ops_platform/postgres/migrations"
    for path in sorted(migrations_dir.glob("*.sql")):
        match = filename_pattern.fullmatch(path.name)
        if match is None:
            raise SystemExit(f"invalid migration filename: {path.name}")
        entries.append(
            {
                "version": match.group("version"),
                "name": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    if not entries:
        raise SystemExit(f"no migrations found: {migrations_dir}")
    fingerprint = hashlib.sha256(
        json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return {
        "contract": "postgres-schema-migrations-v1",
        "migration_count": len(entries),
        "migration_head": entries[-1]["version"],
        "migration_fingerprint_sha256": fingerprint,
    }


candidate_meta = metadata(candidate_src)
previous_meta = metadata(previous_src)
candidate_contract = schema_contract(candidate_src)
if candidate_meta.get("schema_contract") != candidate_contract:
    raise SystemExit("candidate RELEASE.json schema contract does not match packaged migrations")
previous_contract = schema_contract(previous_src)

database_url = database_url_from_env_or_arg(None)
migrations = discover_migrations(candidate_src / "backend/src/fin_ops_platform/postgres/migrations")
applied = fetch_applied_migrations(database_url)
accepted = load_accepted_checksum_drifts(
    candidate_src / "backend/src/fin_ops_platform/postgres/accepted_checksum_drifts.json"
)
candidate_versions = {migration.version for migration in migrations}
unexpected_applied = sorted(set(applied) - candidate_versions)
if unexpected_applied:
    raise SystemExit(
        "production schema is ahead of candidate migrations: " + ", ".join(unexpected_applied)
    )

pending = []
for migration in migrations:
    current = applied.get(migration.version)
    if current is None:
        pending.append(
            {
                "version": migration.version,
                "name": migration.name,
                "sha256": migration.checksum_sha256,
            }
        )
        continue
    if current.checksum_sha256 == migration.checksum_sha256:
        continue
    if not is_accepted_checksum_drift(migration, current, accepted):
        raise SystemExit(
            f"production migration checksum mismatch: {migration.version} {migration.name}"
        )

server_version_num = int(run_psql(database_url, sql="show server_version_num;"))
applied_versions = sorted(applied)


def release_identity(name, release_meta, contract):
    access = release_meta.get("settings_access_control") or {}
    return {
        "release_name": name,
        "git_commit": release_meta.get("git_commit"),
        "source_sha256": access.get("source_sha256"),
        "schema_contract": contract,
    }


plan = {
    "contract": "schema-rollback-compatibility-plan-v1",
    "candidate": release_identity(
        os.environ["CANDIDATE_RELEASE"], candidate_meta, candidate_contract
    ),
    "previous": release_identity(
        os.environ["PREVIOUS_RELEASE"], previous_meta, previous_contract
    ),
    "database": {
        "postgres_major": server_version_num // 10000,
        "applied_migration_count": len(applied_versions),
        "applied_migration_head": applied_versions[-1] if applied_versions else None,
    },
    "pending_migrations": pending,
    "requires_compatibility_evidence": bool(pending),
}
plan["plan_fingerprint_sha256"] = hashlib.sha256(
    json.dumps(plan, sort_keys=True, separators=(",", ":")).encode()
).hexdigest()
print(json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True))
PY
}

validate_schema_compatibility_evidence() {
  local plan_path="$1"
  local evidence_path="$2"
  local require_fresh="${3:-false}"
  "$API_PYTHON" - "$plan_path" "$evidence_path" "$require_fresh" <<'PY'
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import sys

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
evidence = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
require_fresh = sys.argv[3] == "true"
required_operations = [
    "bank_transaction_existing_upsert",
    "correction_audit_same_transaction",
    "import_enrichment",
    "invoice_existing_upsert",
    "settings_data_reset",
]
candidate = plan.get("candidate") or {}
previous = plan.get("previous") or {}
database = plan.get("database") or {}
tested_schema_heads = [
    str(item.get("version") or "") for item in plan.get("pending_migrations") or []
]
expected = {
    "contract": "schema-rollback-compatibility-evidence-v1",
    "status": "pass",
    "plan_fingerprint_sha256": plan.get("plan_fingerprint_sha256"),
    "candidate_release": candidate.get("release_name"),
    "candidate_git_commit": candidate.get("git_commit"),
    "previous_release": previous.get("release_name"),
    "previous_git_commit": previous.get("git_commit"),
    "postgres_major": database.get("postgres_major"),
    "tested_schema_heads": tested_schema_heads,
    "tested_operations": required_operations,
    "candidate_schema_applied": True,
    "previous_release_write_probe": True,
}
violations = {
    key: {"expected": value, "actual": evidence.get(key)}
    for key, value in expected.items()
    if evidence.get(key) != value
}
database_name = str(evidence.get("test_database_name") or "")
if "test" not in database_name.lower() or database_name.lower() in {"fin_ops", "postgres"}:
    violations["test_database_name"] = {
        "expected": "a disposable database name containing 'test'",
        "actual": database_name,
    }
for key in ("test_run_id", "approved_by", "reason"):
    if not str(evidence.get(key) or "").strip():
        violations[key] = {"expected": "non-empty", "actual": evidence.get(key)}
try:
    generated_at = datetime.fromisoformat(str(evidence.get("generated_at") or ""))
    if generated_at.tzinfo is None:
        raise ValueError
    age_seconds = (datetime.now(UTC) - generated_at.astimezone(UTC)).total_seconds()
    if require_fresh and not 0 <= age_seconds <= 86400:
        raise ValueError
except ValueError:
    violations["generated_at"] = {
        "expected": "timezone-aware timestamp no older than 24 hours" if require_fresh else "timezone-aware timestamp",
        "actual": evidence.get("generated_at"),
    }
if not re.fullmatch(r"[0-9a-f]{64}", str(evidence.get("probe_sha256") or "")):
    violations["probe_sha256"] = {
        "expected": "sha256 of the exact compatibility probe",
        "actual": evidence.get("probe_sha256"),
    }
if violations:
    raise SystemExit(
        "schema compatibility evidence contract failed: "
        + json.dumps(violations, ensure_ascii=False, sort_keys=True)
    )
normalized = {key: evidence.get(key) for key in (*expected, "test_database_name", "test_run_id", "approved_by", "reason", "generated_at", "probe_sha256")}
print(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True))
PY
}

schema_compatibility_evidence_install() {
  local release="${1:-}"
  [[ "$#" -eq 2 && "$2" == "--stdin" ]] \
    || die "schema-compatibility-evidence-install requires release name and --stdin"
  local plan_path input_path normalized_path target_path requires_evidence
  plan_path="$(mktemp /run/finops-schema-plan.XXXXXX)"
  input_path="$(mktemp /run/finops-schema-evidence-input.XXXXXX)"
  normalized_path="$(mktemp /run/finops-schema-evidence-normalized.XXXXXX)"
  trap 'rm -f -- "$plan_path" "$input_path" "$normalized_path"' RETURN
  schema_compatibility_plan "$release" --json >"$plan_path"
  requires_evidence="$("$API_PYTHON" - "$plan_path" <<'PY'
import json
from pathlib import Path
import sys
print("true" if json.loads(Path(sys.argv[1]).read_text())["requires_compatibility_evidence"] else "false")
PY
)"
  [[ "$requires_evidence" == "true" ]] \
    || die "candidate has no pending migrations; schema compatibility evidence is unnecessary"
  dd bs=262145 count=1 of="$input_path" status=none
  [[ "$(stat -c %s "$input_path")" -le 262144 ]] || die "schema compatibility evidence exceeds 256 KiB"
  validate_schema_compatibility_evidence "$plan_path" "$input_path" true >"$normalized_path"
  install -d -m 0700 "$SCHEMA_COMPATIBILITY_EVIDENCE_ROOT"
  target_path="$SCHEMA_COMPATIBILITY_EVIDENCE_ROOT/$release.json"
  [[ ! -e "$target_path" ]] || die "schema compatibility evidence already exists: $target_path"
  install -o root -g root -m 0600 "$normalized_path" "$target_path"
  printf '%s\n' "$target_path"
}

schema_compatibility_evidence_valid() {
  local release="$1"
  local plan_path="$2"
  local evidence_path="$SCHEMA_COMPATIBILITY_EVIDENCE_ROOT/$release.json"
  local candidate_src
  [[ -f "$evidence_path" ]] || return 1
  validate_schema_compatibility_evidence "$plan_path" "$evidence_path" false >/dev/null || return 1
  candidate_src="$(release_src "$release")"
  [[ -f "$MIGRATOR_ENV" ]] || return 1
  set -a
  # shellcheck disable=SC1090
  source "$MIGRATOR_ENV"
  set +a
  PYTHONPATH="$candidate_src/backend/src" "$API_PYTHON" - "$plan_path" <<'PY'
import json
from pathlib import Path
import sys

from fin_ops_platform.postgres.migrate import (
    database_url_from_env_or_arg,
    fetch_applied_migrations,
)

plan = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
applied = fetch_applied_migrations(database_url_from_env_or_arg(None))
database = plan.get("database") or {}
initial_count = int(database.get("applied_migration_count") or 0)
initial_head = database.get("applied_migration_head")
pending = plan.get("pending_migrations") or []
allowed_states = {(initial_count, initial_head)}
for index, item in enumerate(pending, start=1):
    allowed_states.add((initial_count + index, item.get("version")))
actual_versions = sorted(applied)
actual_state = (
    len(actual_versions),
    actual_versions[-1] if actual_versions else None,
)
if actual_state not in allowed_states:
    raise SystemExit(
        f"production schema state {actual_state!r} is outside the tested migration prefix"
    )
for item in pending:
    current = applied.get(str(item.get("version") or ""))
    if current is not None and current.checksum_sha256 != item.get("sha256"):
        raise SystemExit(
            f"applied candidate migration checksum changed: {current.version}"
        )
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

registered_read_models() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -c \
      'from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST; print(" ".join(sorted(READ_MODEL_MANIFEST)))'
}

release_has_workbench_page_read_model() {
  local src="$1"
  PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
    "$WORKER_PYTHON" -c \
      'from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST; raise SystemExit(0 if "workbench" in READ_MODEL_MANIFEST else 1)'
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
  local registered required read_models active unknown missing service instance
  registered="$(registered_worker_instances "$src")"
  required="$(required_worker_instances "$src")"
  read_models="$(registered_read_models "$src")"
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
  REGISTERED_READ_MODELS="$read_models" \
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
    "registered_read_models": words("REGISTERED_READ_MODELS"),
    "registered_read_model_count": len(words("REGISTERED_READ_MODELS")),
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

enter_runtime_maintenance() {
  local generation_service generation_timer
  generation_service="$(basename "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT")"
  generation_timer="$(basename "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT")"

  systemctl stop fin-ops.service >/dev/null 2>&1 || true
  systemctl stop fin-ops-rabbitmq-dispatcher.service >/dev/null 2>&1 || true
  stop_runtime_worker_services_for_activation >/dev/null 2>&1 || true
  systemctl disable --now "$generation_timer" >/dev/null 2>&1 || true
  systemctl stop "$generation_service" >/dev/null 2>&1 || true
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
    systemctl stop "$service" >/dev/null 2>&1 || true
    systemctl reset-failed "$service" >/dev/null 2>&1 || true
  done < <(known_worker_services)
}

retire_workbench_page_runtime_assets() {
  local src="$1"
  release_has_workbench_page_read_model "$src" && return 0

  systemctl disable --now fin-ops-worker@workbench.service >/dev/null 2>&1 || true
  systemctl stop fin-ops-worker@workbench.service >/dev/null 2>&1 || true
  systemctl reset-failed fin-ops-worker@workbench.service >/dev/null 2>&1 || true
  rm -f -- "$WORKBENCH_PAGE_WORKER_ENV" "$WORKBENCH_PAGE_WORKER_UNIT"
  systemctl daemon-reload
}

assert_root_owned_private_file() {
  local path="$1"
  "$API_PYTHON" - "$path" <<'PY'
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
metadata = path.lstat()
if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
    raise SystemExit(f"private runtime evidence must be a regular non-symlink file: {path}")
if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o600:
    raise SystemExit(f"private runtime evidence must be root-owned with mode 0600: {path}")
PY
}

assert_root_owned_private_directory() {
  local path="$1"
  "$API_PYTHON" - "$path" <<'PY'
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
metadata = path.lstat()
if not stat.S_ISDIR(metadata.st_mode) or path.is_symlink():
    raise SystemExit(f"private runtime evidence must be a non-symlink directory: {path}")
if metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) != 0o700:
    raise SystemExit(f"private runtime evidence directory must be root-owned with mode 0700: {path}")
PY
}

capture_workbench_page_worker_env_for_cutover() {
  local candidate_release="$1"
  local previous_release="$2"
  local evidence_dir="$3"
  local candidate_src previous_src backup_dir backup_path metadata_path
  local backup_temp metadata_temp source_facts source_uid source_gid source_mode source_sha256
  candidate_src="$(release_src "$candidate_release")"
  previous_src="$(release_src "$previous_release")"
  release_has_workbench_page_read_model "$candidate_src" && return 0
  release_has_workbench_page_read_model "$previous_src" || return 0

  assert_root_owned_runtime_env "$WORKBENCH_PAGE_WORKER_ENV"
  backup_dir="$evidence_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_DIRNAME"
  backup_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_ENV_BASENAME"
  metadata_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_METADATA_BASENAME"
  [[ ! -e "$backup_path" && ! -L "$backup_path" ]] \
    || die "previous Workbench page worker env backup already exists"
  [[ ! -e "$metadata_path" && ! -L "$metadata_path" ]] \
    || die "previous Workbench page worker env metadata already exists"
  install -d -m 0700 "$backup_dir"
  if ! assert_root_owned_private_directory "$backup_dir"; then
    die "Workbench page worker rollback evidence directory is not private root-owned storage"
  fi

  source_facts="$("$API_PYTHON" - "$WORKBENCH_PAGE_WORKER_ENV" <<'PY'
import hashlib
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
metadata = path.lstat()
print(
    metadata.st_uid,
    metadata.st_gid,
    format(stat.S_IMODE(metadata.st_mode), "04o"),
    hashlib.sha256(path.read_bytes()).hexdigest(),
)
PY
)"
  read -r source_uid source_gid source_mode source_sha256 <<<"$source_facts"
  [[ "$source_uid" =~ ^[0-9]+$ && "$source_gid" =~ ^[0-9]+$ ]] \
    || die "invalid Workbench page worker env ownership evidence"
  [[ "$source_mode" =~ ^0[0-7]{3}$ && "$source_sha256" =~ ^[0-9a-f]{64}$ ]] \
    || die "invalid Workbench page worker env mode or hash evidence"

  backup_temp="$(mktemp "$backup_dir/.fin-ops.worker.workbench.env.XXXXXX")"
  metadata_temp="$(mktemp "$backup_dir/.fin-ops.worker.workbench.env.json.XXXXXX")"
  if ! install -m 0600 "$WORKBENCH_PAGE_WORKER_ENV" "$backup_temp" \
    || [[ "$(sha256sum "$backup_temp" | awk '{print $1}')" != "$source_sha256" ]] \
    || ! mv -f -- "$backup_temp" "$backup_path"; then
    rm -f -- "$backup_temp" "$metadata_temp"
    die "failed to capture exact Workbench page worker env for automatic rollback"
  fi
  if ! assert_root_owned_private_file "$backup_path"; then
    rm -f -- "$backup_path" "$metadata_temp"
    die "captured Workbench page worker rollback env is not private root-owned evidence"
  fi
  if ! "$API_PYTHON" - \
    "$metadata_temp" "$candidate_release" "$previous_release" \
    "$WORKBENCH_PAGE_WORKER_ENV" "$backup_path" \
    "$source_uid" "$source_gid" "$source_mode" "$source_sha256" <<'PY'
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

(
    output_path,
    candidate_release,
    previous_release,
    source_path,
    backup_path,
    source_uid,
    source_gid,
    source_mode,
    source_sha256,
) = sys.argv[1:]
payload = {
    "contract": "workbench-page-worker-env-rollback-v1",
    "status": "ready",
    "candidate_release": candidate_release,
    "previous_release": previous_release,
    "captured_at": datetime.now(UTC).isoformat(),
    "source_path": source_path,
    "backup_path": backup_path,
    "source_uid": int(source_uid),
    "source_gid": int(source_gid),
    "source_mode": source_mode,
    "sha256": source_sha256,
}
Path(output_path).write_text(
    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
)
PY
  then
    rm -f -- "$metadata_temp" "$backup_path"
    die "failed to write Workbench page worker rollback metadata"
  fi
  if ! chmod 0600 "$metadata_temp" \
    || ! mv -f -- "$metadata_temp" "$metadata_path" \
    || ! assert_root_owned_private_file "$metadata_path"; then
    rm -f -- "$metadata_temp" "$metadata_path" "$backup_path"
    die "failed to finalize private Workbench page worker rollback evidence"
  fi
}

workbench_page_worker_env_rollback_facts() {
  local candidate_release="$1"
  local previous_release="$2"
  local evidence_dir="$3"
  local backup_dir backup_path metadata_path
  backup_dir="$evidence_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_DIRNAME"
  backup_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_ENV_BASENAME"
  metadata_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_METADATA_BASENAME"
  if ! assert_root_owned_private_directory "$backup_dir" \
    || ! assert_root_owned_private_file "$backup_path" \
    || ! assert_root_owned_private_file "$metadata_path"; then
    die "Workbench page worker rollback evidence is not private root-owned storage"
  fi
  "$API_PYTHON" - \
    "$metadata_path" "$candidate_release" "$previous_release" \
    "$WORKBENCH_PAGE_WORKER_ENV" "$backup_path" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys

metadata_path = Path(sys.argv[1])
candidate_release = sys.argv[2]
previous_release = sys.argv[3]
expected_source_path = sys.argv[4]
expected_backup_path = sys.argv[5]
payload = json.loads(metadata_path.read_text(encoding="utf-8"))
if not isinstance(payload, dict):
    raise SystemExit("Workbench page worker rollback metadata must be an object")
expected = {
    "contract": "workbench-page-worker-env-rollback-v1",
    "status": "ready",
    "candidate_release": candidate_release,
    "previous_release": previous_release,
    "source_path": expected_source_path,
    "backup_path": expected_backup_path,
}
for key, value in expected.items():
    if payload.get(key) != value:
        raise SystemExit(f"Workbench page worker rollback metadata mismatch: {key}")
try:
    source_uid = int(payload["source_uid"])
    source_gid = int(payload["source_gid"])
except (KeyError, TypeError, ValueError) as exc:
    raise SystemExit("Workbench page worker rollback ownership metadata is invalid") from exc
source_mode = str(payload.get("source_mode") or "")
source_sha256 = str(payload.get("sha256") or "")
if source_uid < 0 or source_gid < 0 or re.fullmatch(r"0[0-7]{3}", source_mode) is None:
    raise SystemExit("Workbench page worker rollback owner or mode is invalid")
if int(source_mode, 8) & 0o022:
    raise SystemExit("Workbench page worker rollback mode is group/world writable")
if re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
    raise SystemExit("Workbench page worker rollback hash is invalid")
actual_sha256 = hashlib.sha256(Path(expected_backup_path).read_bytes()).hexdigest()
if actual_sha256 != source_sha256:
    raise SystemExit("Workbench page worker rollback backup hash mismatch")
print(source_uid, source_gid, source_mode, source_sha256)
PY
}

restore_previous_workbench_page_worker_env() {
  local previous_release="$1"
  local candidate_release="$2"
  local evidence_dir="$3"
  local previous_src backup_dir backup_path restore_temp rollback_facts
  local source_uid source_gid source_mode source_sha256
  previous_src="$(release_src "$previous_release")"
  release_has_workbench_page_read_model "$previous_src" \
    || die "refusing Workbench page worker env restore for a direct-only release"
  if ! rollback_facts="$(workbench_page_worker_env_rollback_facts \
    "$candidate_release" "$previous_release" "$evidence_dir")"; then
    die "Workbench page worker rollback evidence validation failed"
  fi
  read -r source_uid source_gid source_mode source_sha256 <<<"$rollback_facts"
  backup_dir="$evidence_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_DIRNAME"
  backup_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_ENV_BASENAME"
  [[ -d "$ENV_DIR" && ! -L "$ENV_DIR" ]] \
    || die "runtime env directory must be a non-symlink directory: $ENV_DIR"
  [[ ! -L "$WORKBENCH_PAGE_WORKER_ENV" ]] \
    || die "refusing to replace symlink Workbench page worker env"
  restore_temp="$(mktemp "$ENV_DIR/.fin-ops.worker.workbench.env.rollback.XXXXXX")"
  if ! install -m 0600 "$backup_path" "$restore_temp" \
    || ! chown "$source_uid:$source_gid" "$restore_temp" \
    || ! chmod "$source_mode" "$restore_temp" \
    || ! mv -f -- "$restore_temp" "$WORKBENCH_PAGE_WORKER_ENV"; then
    rm -f -- "$restore_temp"
    die "failed to atomically restore previous Workbench page worker env"
  fi
  if ! "$API_PYTHON" - \
    "$WORKBENCH_PAGE_WORKER_ENV" "$source_uid" "$source_gid" "$source_mode" "$source_sha256" <<'PY'
import hashlib
from pathlib import Path
import stat
import sys

path = Path(sys.argv[1])
expected_uid = int(sys.argv[2])
expected_gid = int(sys.argv[3])
expected_mode = int(sys.argv[4], 8)
expected_sha256 = sys.argv[5]
metadata = path.lstat()
actual = (
    metadata.st_uid,
    metadata.st_gid,
    stat.S_IMODE(metadata.st_mode),
    hashlib.sha256(path.read_bytes()).hexdigest(),
)
expected = (expected_uid, expected_gid, expected_mode, expected_sha256)
if path.is_symlink() or actual != expected:
    raise SystemExit("restored Workbench page worker env does not match rollback evidence")
PY
  then
    die "restored Workbench page worker env failed exact owner/mode/hash validation"
  fi
}

discard_workbench_page_worker_env_rollback_backup() {
  local candidate_release="$1"
  local previous_release="$2"
  local evidence_dir="$3"
  local candidate_src previous_src backup_dir backup_path
  candidate_src="$(release_src "$candidate_release")"
  previous_src="$(release_src "$previous_release")"
  release_has_workbench_page_read_model "$candidate_src" && return 0
  release_has_workbench_page_read_model "$previous_src" || return 0
  if ! workbench_page_worker_env_rollback_facts \
    "$candidate_release" "$previous_release" "$evidence_dir" >/dev/null; then
    die "refusing to delete invalid Workbench page worker rollback evidence"
  fi
  backup_dir="$evidence_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_DIRNAME"
  backup_path="$backup_dir/$WORKBENCH_PAGE_WORKER_ROLLBACK_ENV_BASENAME"
  rm -f -- "$backup_path"
  [[ ! -e "$backup_path" && ! -L "$backup_path" ]] \
    || die "failed to delete Workbench page worker rollback env after validated release closure"
}

sync_rabbitmq_dispatcher_event_types() {
  local src="$1"
  local event_types temporary
  [[ -e "$RABBITMQ_DISPATCHER_ENV" || -L "$RABBITMQ_DISPATCHER_ENV" ]] || return 0
  assert_root_owned_runtime_env "$RABBITMQ_DISPATCHER_ENV"
  event_types="$(rabbitmq_dispatch_event_types "$src" | tr ' ' ',')"
  event_types="${event_types//$'\n'/}"
  [[ -n "$event_types" ]] || die "target release has no RabbitMQ dispatcher event types"
  temporary="$(mktemp "$ENV_DIR/.fin-ops.rabbitmq-dispatcher.env.XXXXXX")"
  if ! awk -v value="$event_types" '
      BEGIN { replaced = 0 }
      /^RABBITMQ_DISPATCH_EVENT_TYPES=/ {
        if (!replaced) print "RABBITMQ_DISPATCH_EVENT_TYPES=" value
        replaced = 1
        next
      }
      { print }
      END {
        if (!replaced) print "RABBITMQ_DISPATCH_EVENT_TYPES=" value
      }
    ' "$RABBITMQ_DISPATCHER_ENV" >"$temporary" \
    || ! chown --reference="$RABBITMQ_DISPATCHER_ENV" "$temporary" \
    || ! chmod --reference="$RABBITMQ_DISPATCHER_ENV" "$temporary" \
    || ! mv -f "$temporary" "$RABBITMQ_DISPATCHER_ENV"; then
    rm -f -- "$temporary"
    die "failed to synchronize the live RabbitMQ dispatcher allowlist"
  fi
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

audit_python_dependencies() {
  local src="$1"
  local audit_env
  audit_env="$(mktemp -d /tmp/fin-ops-dependency-audit.XXXXXX)"
  trap 'rm -rf "$audit_env"' RETURN
  "$API_PYTHON" -m venv "$audit_env"
  "$audit_env/bin/python" -m pip install -q -r "$src/backend/requirements-audit.txt"
  "$audit_env/bin/python" -m pip_audit \
    -r "$src/backend/requirements.txt" \
    --progress-spinner off
  rm -rf "$audit_env"
  trap - RETURN
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

run_workbench_direct_compatibility_preflight() {
  local src="$1"
  local evidence_dir="$2"
  local first_path="$evidence_dir/workbench-legacy-typed-identity-repair.json"
  local second_path="$evidence_dir/workbench-legacy-typed-identity-repair-idempotency.json"
  local bootstrap_path="$evidence_dir/workbench-direct-application-bootstrap.json"
  local temporary

  release_has_workbench_page_read_model "$src" \
    && die "direct Workbench compatibility preflight requires a direct-only release"
  install -d -m 0700 "$evidence_dir"

  temporary="${first_path}.tmp"
  run_with_runtime_env "$src" \
    -m fin_ops_platform.tools.repair_workbench_legacy_typed_identities \
    >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$first_path"

  temporary="${second_path}.tmp"
  run_with_runtime_env "$src" \
    -m fin_ops_platform.tools.repair_workbench_legacy_typed_identities \
    >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$second_path"

  "$API_PYTHON" - "$first_path" "$second_path" <<'PY'
import json
from pathlib import Path
import sys

first = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
second = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
required_keys = {
    "override_repaired",
    "override_unresolved_missing_source",
    "exception_repaired",
}
for label, report in (("first", first), ("second", second)):
    if report.get("status") != "completed":
        raise SystemExit(f"{label} Workbench compatibility repair did not complete")
    if report.get("contract_schema") != "workbench_typed_identity":
        raise SystemExit(f"{label} Workbench compatibility repair contract is invalid")
    counts = report.get("counts")
    if not isinstance(counts, dict) or set(counts) != required_keys:
        raise SystemExit(f"{label} Workbench compatibility repair counts are invalid")
    if any(not isinstance(counts[key], int) or counts[key] < 0 for key in required_keys):
        raise SystemExit(f"{label} Workbench compatibility repair counts are invalid")

if second.get("changed") is not False:
    raise SystemExit("Workbench compatibility repair is not idempotent")
if second["counts"]["override_repaired"] != 0 or second["counts"]["exception_repaired"] != 0:
    raise SystemExit("Workbench compatibility repair changed typed rows on its second pass")
if (
    first["counts"]["override_unresolved_missing_source"]
    != second["counts"]["override_unresolved_missing_source"]
):
    raise SystemExit("Workbench compatibility repair unresolved count is unstable")
PY

  temporary="${bootstrap_path}.tmp"
  run_with_runtime_env "$src" \
    -m fin_ops_platform.tools.workbench_direct_application_bootstrap_probe \
    >"$temporary"
  chmod 0600 "$temporary"
  mv -f "$temporary" "$bootstrap_path"
  "$API_PYTHON" - "$bootstrap_path" <<'PY'
import json
from pathlib import Path
import sys

report = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
if report != {
    "read_only": True,
    "status": "passed",
    "tool": "workbench_direct_application_bootstrap_probe",
}:
    raise SystemExit("candidate Workbench application bootstrap proof is invalid")
PY
}

assert_retired_page_runtime_quiesced() {
  local src="$1"
  local evidence_path="${2:-}"
  local first second terminal_resolution final report sample_seconds temporary
  sample_seconds="${FINOPS_RETIRED_PAGE_RUNTIME_STABILITY_SECONDS:-2}"
  [[ "$sample_seconds" =~ ^[0-9]+$ ]] \
    && (( sample_seconds >= 2 && sample_seconds <= 60 )) \
    || die "FINOPS_RETIRED_PAGE_RUNTIME_STABILITY_SECONDS must be an integer from 2 through 60"
  if ! first="$(retired_page_runtime_snapshot "$src")"; then
    printf 'retired page runtime is not quiesced: %s\n' "$first" >&2
    die "refusing activation while retired page outbox or dirty-scope work is active"
  fi
  sleep "$sample_seconds"
  if ! second="$(retired_page_runtime_snapshot "$src")"; then
    printf 'retired page runtime is not quiesced: %s\n' "$second" >&2
    die "refusing activation while retired page outbox or dirty-scope work is active"
  fi
  if ! FIRST="$first" SECOND="$second" "$API_PYTHON" -c '
import json
import os

first = json.loads(os.environ["FIRST"])
second = json.loads(os.environ["SECOND"])
stable_fields = (
    "event_total_count",
    "event_latest_created_at",
    "scope_total_count",
    "scope_latest_created_at",
)
changed = {field: [first.get(field), second.get(field)] for field in stable_fields if first.get(field) != second.get(field)}
if changed:
    print(json.dumps({"status": "FAIL", "changed": changed}, ensure_ascii=False, sort_keys=True))
    raise SystemExit(4)
' >/dev/null; then
    printf 'retired Workbench page runtime changed during the stability sample: first=%s second=%s\n' \
      "$first" "$second" >&2
    die "retired Workbench page runtime changed during the stability sample; production remains in maintenance"
  fi
  terminal_resolution="$(terminalize_retired_page_runtime_history "$src")"
  if ! final="$(retired_page_runtime_snapshot "$src")"; then
    printf 'retired page runtime is active after terminal history resolution: %s\n' "$final" >&2
    die "retired Workbench page runtime became active during terminal history resolution"
  fi
  if ! report="$(FIRST="$first" SECOND="$second" FINAL="$final" RESOLUTION="$terminal_resolution" \
    "$API_PYTHON" -c '
import json
import os

first = json.loads(os.environ["FIRST"])
second = json.loads(os.environ["SECOND"])
final = json.loads(os.environ["FINAL"])
resolution = json.loads(os.environ["RESOLUTION"])
stable_fields = (
    "event_total_count",
    "event_latest_created_at",
    "scope_total_count",
    "scope_latest_created_at",
)
changed = {
    field: [second.get(field), final.get(field)]
    for field in stable_fields
    if second.get(field) != final.get(field)
}
remaining_terminal = {
    "failed_event_count": final.get("event_failed_count", 0),
    "dead_lettered_event_count": final.get("event_dead_lettered_count", 0),
    "failed_scope_count": final.get("scope_failed_count", 0),
}
if changed or any(remaining_terminal.values()):
    print(json.dumps({
        "status": "FAIL",
        "changed": changed,
        "remaining_terminal_history": remaining_terminal,
        "resolution": resolution,
    }, ensure_ascii=False, sort_keys=True))
    raise SystemExit(5)
print(json.dumps({
    "status": "PASS",
    "first": first,
    "second": second,
    "final": final,
    "terminal_history": {
        "failed_event_count": second.get("event_failed_count", 0),
        "dead_lettered_event_count": second.get("event_dead_lettered_count", 0),
        "failed_scope_count": second.get("scope_failed_count", 0),
        "disposition": "terminalized_in_place_for_retired_page_runtime",
        "resolution": resolution,
    },
}, ensure_ascii=False, sort_keys=True))
')"; then
    printf 'retired Workbench page runtime failed final terminal-history validation: %s\n' "$report" >&2
    die "retired Workbench page terminal history did not converge; production remains in maintenance"
  fi
  if [[ -n "$evidence_path" ]]; then
    install -d -m 0700 "$(dirname "$evidence_path")"
    temporary="${evidence_path}.tmp.$$"
    printf '%s\n' "$report" >"$temporary"
    chmod 0600 "$temporary"
    mv -f -- "$temporary" "$evidence_path"
  fi
  printf '%s\n' "$report"
}

terminalize_retired_page_runtime_history() {
  local src="$1"
  [[ -f "$MIGRATOR_ENV" ]] || die "missing PostgreSQL migrator env: $MIGRATOR_ENV"
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    [[ -n "${FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL:-}" ]] \
      || die "missing FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL in $MIGRATOR_ENV"
    export DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL"
    unset FIN_OPS_POSTGRES_DATABASE_URL
    export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    cd "$src"
    "$API_PYTHON" -c '
import json
import os

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

def bounded_positive_int(name, default, maximum):
    try:
        value = int(os.environ.get(name, default))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be an integer") from exc
    if value <= 0 or value > maximum:
        raise RuntimeError(f"{name} must be between 1 and {maximum}")
    return value

batch_size = bounded_positive_int("FINOPS_RETIRED_PAGE_RUNTIME_TERMINAL_BATCH_SIZE", 500, 5000)
max_rows = bounded_positive_int("FINOPS_RETIRED_PAGE_RUNTIME_TERMINAL_MAX_ROWS", 20000, 100000)
batch_size = min(batch_size, max_rows)
connection = PostgresConnection(PostgresSettings.from_env())

def assert_no_active(transaction):
    active = transaction.fetch_one(
        """
        select
            count(*) filter (where status in (%s, %s))::bigint as active_event_count,
            count(*) filter (where publish_status = %s)::bigint as publishing_event_count
        from job.outbox_events
        where event_type = %s
        """,
        ("pending", "processing", "publishing", "workbench.read_model.refresh"),
    ) or {}
    active_scope = transaction.fetch_one(
        """
        select count(*)::bigint as active_scope_count
        from job.read_model_dirty_scopes
        where scope_type = %s and status in (%s, %s)
        """,
        ("workbench", "pending", "processing"),
    ) or {}
    if any(int(value or 0) for value in (
        active.get("active_event_count"),
        active.get("publishing_event_count"),
        active_scope.get("active_scope_count"),
    )):
        raise RuntimeError("retired Workbench page runtime became active before terminal history resolution")

with connection.transaction() as transaction:
    assert_no_active(transaction)
    inventory = transaction.fetch_one(
        """
        select
            (
                select count(*)::bigint from (
                    select 1
                    from job.outbox_events
                    where event_type = %s and status in (%s, %s)
                    limit %s
                ) bounded_events
            ) as event_count,
            (
                select count(*)::bigint from (
                    select 1
                    from job.read_model_dirty_scopes
                    where scope_type = %s and status = %s
                    limit %s
                ) bounded_scopes
            ) as scope_count
        """,
        (
            "workbench.read_model.refresh", "failed", "dead_lettered", max_rows + 1,
            "workbench", "failed", max_rows + 1,
        ),
    ) or {}
event_inventory_count = int(inventory.get("event_count") or 0)
scope_inventory_count = int(inventory.get("scope_count") or 0)
if event_inventory_count > max_rows or scope_inventory_count > max_rows:
    raise RuntimeError(
        "retired Workbench terminal history exceeds the bounded resolution cap: "
        f"events={event_inventory_count}, scopes={scope_inventory_count}, max_rows={max_rows}"
    )

event_resolved_count = 0
while event_resolved_count < max_rows:
    current_batch_size = min(batch_size, max_rows - event_resolved_count)
    with connection.transaction() as transaction:
        assert_no_active(transaction)
        event_resolution = transaction.fetch_one(
        """
        with candidate as (
            select id
            from job.outbox_events
            where event_type = %s
              and status in (%s, %s)
            order by updated_at, id
            limit %s
            for update skip locked
        ),
        resolved as (
            update job.outbox_events as target
            set
                status = %s,
                processed_at = coalesce(processed_at, now()),
                locked_by = null,
                locked_at = null,
                publish_locked_by = null,
                publish_locked_at = null,
                updated_at = now(),
                raw_payload = jsonb_set(
                    coalesce(raw_payload, %s::jsonb),
                    %s::text[],
                    jsonb_build_object(
                        %s::text, %s::text,
                        %s::text, status,
                        %s::text, last_error,
                        %s::text, attempts,
                        %s::text, publish_status,
                        %s::text, publish_attempt_count,
                        %s::text, publish_last_error,
                        %s::text, %s::text,
                        %s::text, now()
                    ),
                    true
                )
            from candidate
            where target.id = candidate.id
            returning target.id
        )
        select count(*)::bigint as resolved_count from resolved
        """,
        (
            "workbench.read_model.refresh", "failed", "dead_lettered", current_batch_size,
            "done", "{}", ["retirement_resolution"],
            "reason", "workbench_page_read_model_runtime_retired",
            "original_status", "original_last_error", "original_attempts",
            "original_publish_status", "original_publish_attempts", "original_publish_last_error",
            "terminal_status", "done", "resolved_at",
        ),
        ) or {}
    resolved = int(event_resolution.get("resolved_count") or 0)
    event_resolved_count += resolved
    if resolved < current_batch_size:
        break

scope_resolved_count = 0
while scope_resolved_count < max_rows:
    current_batch_size = min(batch_size, max_rows - scope_resolved_count)
    with connection.transaction() as transaction:
        assert_no_active(transaction)
        scope_resolution = transaction.fetch_one(
        """
        with candidate as (
            select id
            from job.read_model_dirty_scopes
            where scope_type = %s
              and status = %s
            order by updated_at, id
            limit %s
            for update skip locked
        ),
        resolved as (
            update job.read_model_dirty_scopes as target
            set
                status = %s,
                locked_by = null,
                locked_at = null,
                updated_at = now(),
                raw_payload = jsonb_set(
                    coalesce(raw_payload, %s::jsonb),
                    %s::text[],
                    jsonb_build_object(
                        %s::text, %s::text,
                        %s::text, status,
                        %s::text, last_error,
                        %s::text, attempts,
                        %s::text, %s::text,
                        %s::text, now()
                    ),
                    true
                )
            from candidate
            where target.id = candidate.id
            returning target.id
        )
        select count(*)::bigint as resolved_count from resolved
        """,
        (
            "workbench", "failed", current_batch_size,
            "superseded", "{}", ["retirement_resolution"],
            "reason", "workbench_page_read_model_runtime_retired",
            "original_status", "original_last_error", "original_attempts",
            "terminal_status", "superseded", "resolved_at",
        ),
        ) or {}
    resolved = int(scope_resolution.get("resolved_count") or 0)
    scope_resolved_count += resolved
    if resolved < current_batch_size:
        break
print(json.dumps({
    "status": "PASS",
    "event_type": "workbench.read_model.refresh",
    "scope_type": "workbench",
    "terminalized_event_count": event_resolved_count,
    "terminalized_scope_count": scope_resolved_count,
    "terminal_inventory_event_count": event_inventory_count,
    "terminal_inventory_scope_count": scope_inventory_count,
    "batch_size": batch_size,
    "max_rows": max_rows,
    "audit_metadata": "retirement_resolution",
}, ensure_ascii=False, sort_keys=True, default=str))
'
  )
}

retired_page_runtime_snapshot() {
  local src="$1"
  run_with_runtime_env "$src" -c '
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
connection = PostgresConnection(PostgresSettings.from_env())
event = connection.fetch_one(
    """
    select
        count(*)::bigint as total_count,
        count(*) filter (where status = %s)::bigint as pending_count,
        count(*) filter (where status = %s)::bigint as processing_count,
        count(*) filter (where status = %s)::bigint as failed_count,
        count(*) filter (where status = %s)::bigint as dead_lettered_count,
        count(*) filter (where publish_status = %s)::bigint as publishing_count,
        max(created_at)::text as latest_created_at
    from job.outbox_events
    where event_type = %s
    """,
    (
        "pending", "processing", "failed", "dead_lettered", "publishing",
        "workbench.read_model.refresh",
    ),
) or {}
scope = connection.fetch_one(
    """
    select
        count(*)::bigint as total_count,
        count(*) filter (where status = %s)::bigint as pending_count,
        count(*) filter (where status = %s)::bigint as processing_count,
        count(*) filter (where status = %s)::bigint as failed_count,
        max(created_at)::text as latest_created_at
    from job.read_model_dirty_scopes
    where scope_type = %s
    """,
    ("pending", "processing", "failed", "workbench"),
) or {}
resolution = connection.fetch_one(
    """
    select
        count(*)::bigint as event_count,
        count(*) filter (
            where raw_payload->%s::text->>%s::text = %s
        )::bigint as failed_event_count,
        count(*) filter (
            where raw_payload->%s::text->>%s::text = %s
        )::bigint as dead_lettered_event_count
    from job.outbox_events
    where event_type = %s
      and raw_payload ? %s
    """,
    (
        "retirement_resolution", "original_status", "failed",
        "retirement_resolution", "original_status", "dead_lettered",
        "workbench.read_model.refresh", "retirement_resolution",
    ),
) or {}
scope_resolution = connection.fetch_one(
    """
    select count(*)::bigint as scope_count
    from job.read_model_dirty_scopes
    where scope_type = %s
      and raw_payload ? %s
    """,
    ("workbench", "retirement_resolution"),
) or {}
def integer(row, key):
    return int(row.get(key) or 0)
payload = dict(
    event_total_count=integer(event, "total_count"),
    event_pending_count=integer(event, "pending_count"),
    event_processing_count=integer(event, "processing_count"),
    event_publishing_count=integer(event, "publishing_count"),
    event_failed_count=integer(event, "failed_count"),
    event_dead_lettered_count=integer(event, "dead_lettered_count"),
    event_latest_created_at=event.get("latest_created_at"),
    scope_total_count=integer(scope, "total_count"),
    scope_pending_count=integer(scope, "pending_count"),
    scope_processing_count=integer(scope, "processing_count"),
    scope_failed_count=integer(scope, "failed_count"),
    scope_latest_created_at=scope.get("latest_created_at"),
    resolved_failed_event_count=integer(resolution, "failed_event_count"),
    resolved_dead_lettered_event_count=integer(resolution, "dead_lettered_event_count"),
    resolved_failed_scope_count=integer(scope_resolution, "scope_count"),
)
print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
active = sum(payload[key] for key in (
    "event_pending_count", "event_processing_count", "event_publishing_count",
    "scope_pending_count", "scope_processing_count",
))
raise SystemExit(0 if active == 0 else 3)
'
}

retired_workbench_page_runtime_window_required() {
  local candidate_src="$1"
  local previous_src="$2"
  ! release_has_workbench_page_read_model "$candidate_src" \
    && release_has_workbench_page_read_model "$previous_src"
}

start_retired_workbench_page_runtime_window() {
  local candidate_release="$1"
  local previous_release="$2"
  local evidence_dir="$3"
  local candidate_src previous_src report_path ready_path stop_path preflight_path attempt
  candidate_src="$(release_src "$candidate_release")"
  previous_src="$(release_src "$previous_release")"
  report_path="$evidence_dir/retired-workbench-page-runtime-window.json"
  ready_path="$evidence_dir/retired-workbench-page-runtime-window.ready"
  stop_path="$evidence_dir/retired-workbench-page-runtime-window.stop"
  preflight_path="$evidence_dir/retired-workbench-page-runtime.json"
  rm -f -- "$report_path" "$ready_path" "$stop_path"

  if ! retired_workbench_page_runtime_window_required "$candidate_src" "$previous_src"; then
    "$API_PYTHON" - "$report_path" <<'PY'
import json
from pathlib import Path
import sys

path = Path(sys.argv[1])
path.write_text(json.dumps({
    "contract": "retired-workbench-page-runtime-window-v1",
    "required": False,
    "status": "NOT_REQUIRED",
}, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
path.chmod(0o600)
PY
    return 0
  fi
  [[ -s "$preflight_path" ]] || return 1

  RETIRED_WORKBENCH_PAGE_OBSERVER_STOP_PATH="$stop_path"
  run_with_runtime_env "$candidate_src" - \
    "$report_path" "$ready_path" "$stop_path" "$preflight_path" "$candidate_src" <<'PY' &
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
import time

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_manifest import READ_MODEL_MANIFEST
from fin_ops_platform.services.runtime_worker_registry import RUNTIME_WORKER_REGISTRY

report_path = Path(sys.argv[1])
ready_path = Path(sys.argv[2])
stop_path = Path(sys.argv[3])
preflight_path = Path(sys.argv[4])
candidate_src = Path(sys.argv[5]).resolve()
stable_fields = (
    "event_total_count",
    "event_latest_created_at",
    "scope_total_count",
    "scope_latest_created_at",
)
table_counters = (
    "seq_scan", "seq_tup_read", "idx_scan", "idx_tup_fetch",
    "n_tup_ins", "n_tup_upd", "n_tup_del", "n_tup_hot_upd",
)

def now():
    return datetime.now(UTC).isoformat()

def integer(row, key):
    return int(row.get(key) or 0)

def snapshot(connection):
    event = connection.fetch_one(
        """
        select count(*)::bigint as total_count, max(created_at)::text as latest_created_at
        from job.outbox_events where event_type = %s
        """,
        ("workbench.read_model.refresh",),
    ) or {}
    scope = connection.fetch_one(
        """
        select count(*)::bigint as total_count, max(created_at)::text as latest_created_at
        from job.read_model_dirty_scopes where scope_type = %s
        """,
        ("workbench",),
    ) or {}
    extension = connection.fetch_one(
        "select exists(select 1 from pg_extension where extname = %s) as installed",
        ("pg_stat_statements",),
    ) or {}
    if extension.get("installed") is not True:
        raise RuntimeError("pg_stat_statements_unavailable")
    statement_reset = connection.fetch_one(
        "select stats_reset::text as stats_reset from pg_stat_statements_info"
    ) or {}
    visibility = connection.fetch_one(
        """
        select
          count(*) filter (where query = %s)::bigint as hidden_count,
          count(*) filter (where query <> %s)::bigint as visible_count
        from pg_stat_statements
        """,
        ("<insufficient privilege>", "<insufficient privilege>"),
    ) or {}
    if integer(visibility, "visible_count") == 0:
        raise RuntimeError("pg_stat_statements_visibility_unavailable")
    projection = connection.fetch_one(
        """
        select count(*)::bigint as statement_count,
               coalesce(sum(calls), 0)::bigint as calls,
               coalesce(sum(rows), 0)::bigint as rows
        from pg_stat_statements
        where lower(query) like any(%s::text[])
        """,
        ([
            "%read_model.workbench_rows%",
            "%read_model.workbench_groups%",
            "%read_model.workbench_generations%",
            "%read_model.workbench_group_rows%",
            "%read_model.workbench_generation_stats%",
            "%read_model.workbench_snapshots%",
            "%read_model.workbench_summary%",
        ],),
    ) or {}
    tables = connection.fetch_all(
        """
        select relname, seq_scan, seq_tup_read, idx_scan, idx_tup_fetch,
               n_tup_ins, n_tup_upd, n_tup_del, n_tup_hot_upd
        from pg_stat_user_tables
        where schemaname = %s and relname = any(%s::text[])
        order by relname
        """,
        (
            "read_model",
            [
                "workbench_rows",
                "workbench_groups",
                "workbench_generations",
                "workbench_group_rows",
                "workbench_generation_stats",
                "workbench_snapshots",
                "workbench_summary",
            ],
        ),
    )
    database = connection.fetch_one(
        "select stats_reset::text as stats_reset from pg_stat_database where datname = current_database()"
    ) or {}
    return {
        "captured_at": now(),
        "event_total_count": integer(event, "total_count"),
        "event_latest_created_at": event.get("latest_created_at"),
        "scope_total_count": integer(scope, "total_count"),
        "scope_latest_created_at": scope.get("latest_created_at"),
        "pg_stat_statements_reset": statement_reset.get("stats_reset"),
        "pg_stat_database_reset": database.get("stats_reset"),
        "projection_statements": {
            "statement_count": integer(projection, "statement_count"),
            "calls": integer(projection, "calls"),
            "rows": integer(projection, "rows"),
        },
        "projection_table_stats": {
            str(row["relname"]): {name: integer(row, name) for name in table_counters}
            for row in tables
        },
    }

def write_report(payload):
    temporary = report_path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.chmod(0o600)
    temporary.replace(report_path)

try:
    preflight = json.loads(preflight_path.read_text(encoding="utf-8"))
    if preflight.get("status") != "PASS":
        raise RuntimeError("preflight_retirement_evidence_invalid")
    preflight_final = preflight.get("final")
    if not isinstance(preflight_final, dict):
        raise RuntimeError("preflight_retirement_final_snapshot_missing")
    connection = PostgresConnection(PostgresSettings.from_env())
    before = snapshot(connection)
    startup_changed = {
        field: {"preflight": preflight_final.get(field), "window_start": before.get(field)}
        for field in stable_fields
        if preflight_final.get(field) != before.get(field)
    }
    release_metadata = json.loads((candidate_src / "RELEASE.json").read_text(encoding="utf-8"))
    retired_redis_owners = (
        "backend/src/fin_ops_platform/services/workbench_groups_page_cache.py",
        "backend/src/fin_ops_platform/services/workbench_query_freshness_service.py",
        "backend/src/fin_ops_platform/services/workbench_read_model_refresh.py",
    )
    active_read_sources = (
        "backend/src/fin_ops_platform/services/workbench_query_facade.py",
        "backend/src/fin_ops_platform/app/routes_workbench.py",
    )
    present_retired_owners = [path for path in retired_redis_owners if (candidate_src / path).exists()]
    active_call_markers = {}
    for relative_path in active_read_sources:
        source_path = candidate_src / relative_path
        if not source_path.is_file():
            active_call_markers[relative_path] = ["missing_source"]
            continue
        source = source_path.read_text(encoding="utf-8")
        markers = [
            marker
            for marker in ("redis_helper", "RuntimeRedisHelper", ".get_json(", ".set_json(", ".get_text(", ".set_text(")
            if marker in source
        ]
        if markers:
            active_call_markers[relative_path] = markers
    page_runtime_registrations = [
        registration.instance_name
        for registration in RUNTIME_WORKER_REGISTRY
        if registration.instance_name == "workbench"
        or registration.read_model_key == "workbench"
        or "workbench.read_model.refresh" in registration.event_types
    ]
    page_read_model_registered = "workbench" in READ_MODEL_MANIFEST
    redis_page_cache_proof = {
        "status": (
            "PASS"
            if not present_retired_owners
            and not active_call_markers
            and not page_runtime_registrations
            and not page_read_model_registered
            else "FAIL"
        ),
        "mode": "source_owner_absent",
        "guard_contract": "candidate_source_owner_and_registry_v1",
        "candidate_git_commit": release_metadata.get("git_commit"),
        "retired_source_paths_absent": not present_retired_owners,
        "active_call_markers_absent": not active_call_markers,
        "page_runtime_registration_absent": not page_runtime_registrations,
        "page_read_model_registration_absent": not page_read_model_registered,
        "present_retired_source_paths": present_retired_owners,
        "active_call_markers": active_call_markers,
        "page_runtime_registrations": page_runtime_registrations,
    }
    ready_path.write_text(now() + "\n", encoding="utf-8")
    ready_path.chmod(0o600)
    deadline = time.monotonic() + 600
    while not stop_path.exists():
        if time.monotonic() >= deadline:
            raise RuntimeError("observer_deadline_exceeded")
        time.sleep(0.25)
    after = snapshot(connection)
    changed = {
        field: {"before": before.get(field), "after": after.get(field)}
        for field in stable_fields
        if before.get(field) != after.get(field)
    }
    changed.update({f"startup_{field}": value for field, value in startup_changed.items()})
    if before["pg_stat_statements_reset"] != after["pg_stat_statements_reset"]:
        changed["pg_stat_statements_reset"] = {
            "before": before["pg_stat_statements_reset"],
            "after": after["pg_stat_statements_reset"],
        }
    if before["pg_stat_database_reset"] != after["pg_stat_database_reset"]:
        changed["pg_stat_database_reset"] = {
            "before": before["pg_stat_database_reset"],
            "after": after["pg_stat_database_reset"],
        }
    if before["projection_statements"] != after["projection_statements"]:
        changed["projection_statements"] = {
            "before": before["projection_statements"],
            "after": after["projection_statements"],
        }
    if before["projection_table_stats"] != after["projection_table_stats"]:
        changed["projection_table_stats"] = {
            "before": before["projection_table_stats"],
            "after": after["projection_table_stats"],
        }
    if redis_page_cache_proof["status"] != "PASS":
        changed["redis_page_cache_source_owner"] = redis_page_cache_proof
    passed = not changed
    write_report({
        "contract": "retired-workbench-page-runtime-window-v1",
        "required": True,
        "status": "PASS" if passed else "FAIL",
        "preflight_evidence_status": preflight.get("status"),
        "before": before,
        "after": after,
        "redis_page_cache_proof": redis_page_cache_proof,
        "changed": changed,
    })
    raise SystemExit(0 if passed else 6)
except BaseException as exc:
    if isinstance(exc, SystemExit):
        raise
    write_report({
        "contract": "retired-workbench-page-runtime-window-v1",
        "required": True,
        "status": "FAIL",
        "failure_type": type(exc).__name__,
    })
    raise SystemExit(7)
PY
  RETIRED_WORKBENCH_PAGE_OBSERVER_PID="$!"

  for attempt in $(seq 1 15); do
    [[ -s "$ready_path" ]] && return 0
    if [[ -s "$report_path" ]] \
      && ! kill -0 "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID" >/dev/null 2>&1; then
      wait "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID" || true
      RETIRED_WORKBENCH_PAGE_OBSERVER_PID=""
      return 1
    fi
    sleep 1
  done
  abandon_retired_workbench_page_runtime_window
  return 1
}

finish_retired_workbench_page_runtime_window() {
  local report_path="$1"
  local observer_failed=false
  if [[ -n "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID" ]]; then
    : >"$RETIRED_WORKBENCH_PAGE_OBSERVER_STOP_PATH"
    chmod 0600 "$RETIRED_WORKBENCH_PAGE_OBSERVER_STOP_PATH"
    if ! wait "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID"; then
      observer_failed=true
    fi
    RETIRED_WORKBENCH_PAGE_OBSERVER_PID=""
  fi
  [[ "$observer_failed" == false && -s "$report_path" ]] || return 1
  "$API_PYTHON" - "$report_path" <<'PY'
import json
from pathlib import Path
import sys

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
required = payload.get("required")
status = payload.get("status")
if not ((required is True and status == "PASS") or (required is False and status == "NOT_REQUIRED")):
    raise SystemExit("retired Workbench page runtime window evidence did not pass")
PY
}

abandon_retired_workbench_page_runtime_window() {
  if [[ -n "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID" ]]; then
    : >"$RETIRED_WORKBENCH_PAGE_OBSERVER_STOP_PATH" 2>/dev/null || true
    wait "$RETIRED_WORKBENCH_PAGE_OBSERVER_PID" >/dev/null 2>&1 || true
    RETIRED_WORKBENCH_PAGE_OBSERVER_PID=""
  fi
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
  local required_existing_worker_envs="${2:-}"
  local worker worker_env
  [[ -x "$ENSURE_RUNTIME_WORKERS_HELPER" ]] || die "runtime worker ensure helper is not executable: $ENSURE_RUNTIME_WORKERS_HELPER"
  for worker in $required_existing_worker_envs; do
    [[ "$worker" =~ ^[A-Za-z0-9][A-Za-z0-9._-]*$ ]] \
      || die "invalid required existing worker env name: $worker"
    worker_env="$ENV_DIR/fin-ops.worker.${worker}.env"
    [[ -f "$worker_env" && ! -L "$worker_env" ]] \
      || die "required restored worker env is missing or not a regular file: $worker_env"
    assert_root_owned_runtime_env "$worker_env"
  done
  FINOPS_REQUIRE_EXISTING_WORKER_ENVS="$required_existing_worker_envs" \
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

retire_workbench_generation_retention() {
  local service_unit timer_unit
  service_unit="$(basename "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT")"
  timer_unit="$(basename "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT")"

  systemctl disable --now "$timer_unit" >/dev/null 2>&1 || true
  systemctl stop "$service_unit" >/dev/null 2>&1 || true
  rm -f -- \
    "$PRUNE_WORKBENCH_GENERATIONS_HELPER" \
    "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT" \
    "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT"
  systemctl daemon-reload
  systemctl reset-failed "$service_unit" "$timer_unit" >/dev/null 2>&1 || true
}

restore_previous_workbench_generation_retention_for_rollback() {
  local src="$1"
  local helper_src service_src timer_src timer_unit
  helper_src="$src/deploy/oa/bin/finops-prune-workbench-generations.sh"
  service_src="$src/deploy/oa/systemd/finops-prune-workbench-generations.service.example"
  timer_src="$src/deploy/oa/systemd/finops-prune-workbench-generations.timer.example"
  timer_unit="$(basename "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT")"

  release_has_workbench_page_read_model "$src" \
    || die "refusing to restore Workbench generation retention from a direct-only release"
  [[ -f "$helper_src" ]] || die "previous release is missing its Workbench generation prune helper: $helper_src"
  [[ -f "$service_src" ]] || die "previous release is missing its Workbench generation prune service: $service_src"
  [[ -f "$timer_src" ]] || die "previous release is missing its Workbench generation prune timer: $timer_src"

  install -m 0755 -o root -g root "$helper_src" "$PRUNE_WORKBENCH_GENERATIONS_HELPER"
  install -m 0644 -o root -g root "$service_src" "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT"
  install -m 0644 -o root -g root "$timer_src" "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT"
  systemctl daemon-reload
  systemctl enable --now "$timer_unit"
}

assert_previous_workbench_rollback_evidence() {
  local release="$1"
  local evidence_path="$2"
  [[ -n "$evidence_path" && -f "$evidence_path" && ! -L "$evidence_path" ]] \
    || die "audited previous-page-runtime activation requires immutable rollback validation evidence"
  [[ "$(stat -c '%u' "$evidence_path")" == "0" ]] \
    || die "previous-page-runtime rollback validation evidence must be root-owned"
  "$API_PYTHON" - "$release" "$evidence_path" <<'PY'
import json
from pathlib import Path
import sys

release = sys.argv[1]
path = Path(sys.argv[2])
try:
    payload = json.loads(path.read_text(encoding="utf-8"))
except (OSError, ValueError) as exc:
    raise SystemExit(f"invalid previous-page-runtime rollback evidence: {exc}") from exc
if not isinstance(payload, dict):
    raise SystemExit("previous-page-runtime rollback evidence must be a JSON object")
if payload.get("status") != "PASS":
    raise SystemExit("previous-page-runtime rollback evidence did not pass")
if payload.get("previous_release") != release:
    raise SystemExit("previous-page-runtime rollback evidence does not bind the target release")
if payload.get("errors") not in ([], None):
    raise SystemExit("previous-page-runtime rollback evidence contains errors")
if not payload.get("rebuilt_generation_ids") or not payload.get("active_generation_id"):
    raise SystemExit("previous-page-runtime rollback evidence does not prove a new active generation")
PY
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
  local restart_dispatcher="${2:-auto}"
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
  if [[ "$restart_dispatcher" == "true" ]] \
    || { [[ "$restart_dispatcher" == "auto" ]] \
      && systemctl is-active --quiet fin-ops-rabbitmq-dispatcher.service; }; then
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
  active_worker_services | while read -r svc; do
    [[ -n "$svc" ]] || continue
    systemctl show "$svc" -p EnvironmentFiles -p WorkingDirectory -p Environment --no-pager || true
  done
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

workbench_page_runtime_audit() {
  local src="$1"
  run_with_runtime_env "$src" -c '
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository

connection = PostgresConnection(PostgresSettings.from_env())
status = PostgresReadModelRepository(connection).get_workbench_refresh_status(scope_key="all")
outbox = connection.fetch_one(
    """
    select
        count(*)::bigint as total_count,
        count(*) filter (where status = %s)::bigint as pending_count,
        count(*) filter (where status = %s)::bigint as processing_count,
        count(*) filter (where publish_status = %s)::bigint as publishing_count,
        count(*) filter (
            where status in (%s, %s)
              and not (raw_payload ? %s)
        )::bigint as unresolved_terminal_count,
        max(created_at)::text as latest_created_at
    from job.outbox_events
    where event_type = %s
    """,
    (
        "pending", "processing", "publishing", "failed", "dead_lettered",
        "retirement_resolution", "workbench.read_model.refresh",
    ),
) or {}
dirty = connection.fetch_one(
    """
    select
        count(*) filter (where status = %s)::bigint as pending_count,
        count(*) filter (where status = %s)::bigint as processing_count,
        count(*) filter (where status = %s)::bigint as failed_count
    from job.read_model_dirty_scopes
    where scope_type = %s
    """,
    ("pending", "processing", "failed", "workbench"),
) or {}
active_generations = connection.fetch_all(
    """
    select scope_key, generation_id, source_versions
    from read_model.workbench_generations
    where tenant_id = %s
      and status = %s
      and scope_key ~ %s
    order by scope_key
    """,
    ("default", "active", "^[0-9]{4}-[0-9]{2}$"),
)
retirement_history = connection.fetch_one(
    """
    select
        count(*)::bigint as event_count,
        count(*) filter (
            where raw_payload->%s::text->>%s::text = %s
        )::bigint as failed_count,
        count(*) filter (
            where raw_payload->%s::text->>%s::text = %s
        )::bigint as dead_lettered_count
    from job.outbox_events
    where event_type = %s
      and raw_payload ? %s
    """,
    (
        "retirement_resolution", "original_status", "failed",
        "retirement_resolution", "original_status", "dead_lettered",
        "workbench.read_model.refresh", "retirement_resolution",
    ),
) or {}
retirement_dirty_history = connection.fetch_one(
    """
    select count(*)::bigint as scope_count
    from job.read_model_dirty_scopes
    where scope_type = %s
      and raw_payload ? %s
    """,
    ("workbench", "retirement_resolution"),
) or {}
print(json.dumps({
    "status": status,
    "outbox": outbox,
    "dirty_scopes": dirty,
    "active_generations": active_generations,
    "retirement_history": {
        **retirement_history,
        **retirement_dirty_history,
    },
}, default=str, sort_keys=True))
'
}

seed_previous_workbench_rehydrate_scopes() {
  local src="$1"
  [[ -f "$MIGRATOR_ENV" ]] || die "missing PostgreSQL migrator env: $MIGRATOR_ENV"
  (
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    [[ -n "${FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL:-}" ]] \
      || die "missing FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL in $MIGRATOR_ENV"
    export DATABASE_URL="$FIN_OPS_POSTGRES_MIGRATOR_DATABASE_URL"
    unset FIN_OPS_POSTGRES_DATABASE_URL
    export PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}"
    export FIN_OPS_DATA_DIR="${FIN_OPS_DATA_DIR:-/opt/fin-ops/data}"
    cd "$src"
    "$API_PYTHON" -c '
import json

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder

connection = PostgresConnection(PostgresSettings.from_env())
builder = WorkbenchSqlProjectionBuilder(
    connection=connection,
    read_model_repository=PostgresReadModelRepository(connection),
)
month_scopes = sorted(set(builder.list_workbench_scope_shards("all")))
if not month_scopes:
    raise RuntimeError("previous release discovered no Workbench month shards to rehydrate")
scope_keys = [*month_scopes, "all"]
seeded = []
with connection.transaction() as transaction:
    processing = transaction.fetch_all(
        """
        select scope_key
        from job.read_model_dirty_scopes
        where tenant_id = %s
          and scope_type = %s
          and status = %s
          and scope_key = any(%s::text[])
        order by scope_key
        """,
        ("default", "workbench", "processing", scope_keys),
    )
    if processing:
        raise RuntimeError("cannot seed rollback rehydrate while a Workbench dirty scope is processing")
    for scope_key in scope_keys:
        marker = {
            "reason": "direct_only_release_rollback_rehydrate",
            "rollback_rehydrate_seed": {
                "scope_key": scope_key,
                "source": "finops-deploy-control",
            },
        }
        row = transaction.fetch_one(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, month, reason,
                source_version, status, next_run_at, payload, raw_payload
            )
            values (
                %s, %s, %s, %s::date, %s,
                coalesce((
                    select max(existing.source_version) + 1
                    from job.read_model_dirty_scopes existing
                    where existing.tenant_id = %s
                      and existing.scope_type = %s
                      and existing.scope_key = %s
                ), 0),
                %s, clock_timestamp(), %s, %s
            )
            on conflict (tenant_id, scope_type, scope_key)
            where status in ($$pending$$, $$processing$$)
            do update set
                reason = excluded.reason,
                source_version = job.read_model_dirty_scopes.source_version + 1,
                status = %s,
                next_run_at = clock_timestamp(),
                locked_by = null,
                locked_at = null,
                payload = job.read_model_dirty_scopes.payload || excluded.payload,
                raw_payload = job.read_model_dirty_scopes.raw_payload || excluded.raw_payload,
                updated_at = clock_timestamp()
            where job.read_model_dirty_scopes.status = %s
            returning scope_key, source_version, status
            """,
            (
                "default", "workbench", scope_key,
                f"{scope_key}-01" if scope_key != "all" else None,
                "direct_only_release_rollback_rehydrate",
                "default", "workbench", scope_key,
                "pending", jsonb(marker), jsonb(marker),
                "pending", "pending",
            ),
        )
        if row is None:
            raise RuntimeError(f"failed to seed rollback rehydrate scope {scope_key}")
        seeded.append(dict(row))
print(json.dumps({
    "status": "PASS",
    "scope_type": "workbench",
    "scope_keys": scope_keys,
    "seeded": seeded,
}, ensure_ascii=False, sort_keys=True, default=str))
'
  )
}

prepare_previous_workbench_page_runtime() {
  local previous_release="$1"
  local evidence_dir="$2"
  local src rehydrate_report seed_report before_report after_report validation_report stderr_report
  src="$(release_src "$previous_release")"
  rehydrate_report="$evidence_dir/rollback-workbench-rehydrate.json"
  seed_report="$evidence_dir/rollback-workbench-seed.json"
  before_report="$evidence_dir/rollback-workbench-before.json"
  after_report="$evidence_dir/rollback-workbench-after.json"
  validation_report="$evidence_dir/rollback-workbench-validation.json"
  stderr_report="$evidence_dir/rollback-workbench-rehydrate.stderr"

  [[ -f "$src/scripts/rehydrate-workbench-read-models.py" ]] \
    || die "previous release is missing its Workbench rehydrate script: $src/scripts/rehydrate-workbench-read-models.py"
  umask 077
  workbench_page_runtime_audit "$src" >"$before_report"
  if ! seed_previous_workbench_rehydrate_scopes "$src" >"$seed_report"; then
    printf 'previous-release Workbench rollback seed failed; see %s\n' "$seed_report" >&2
    return 1
  fi
  if ! run_with_runtime_env "$src" \
    "$src/scripts/rehydrate-workbench-read-models.py" --json \
    >"$rehydrate_report" 2>"$stderr_report"; then
    printf 'previous-release Workbench rehydrate failed; see %s\n' "$stderr_report" >&2
    return 1
  fi
  workbench_page_runtime_audit "$src" >"$after_report"

  if ! "$API_PYTHON" - \
    "$rehydrate_report" "$seed_report" "$before_report" "$after_report" "$validation_report" "$previous_release" <<'PY'
from datetime import datetime
import json
from pathlib import Path
import sys

rehydrate_path, seed_path, before_path, after_path, output_path = map(Path, sys.argv[1:6])
previous_release = sys.argv[6]
errors = []

def load(path):
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        errors.append(f"invalid evidence {path.name}: {exc}")
        return {}
    if not isinstance(payload, dict):
        errors.append(f"evidence {path.name} must be a JSON object")
        return {}
    return payload

def integer(value):
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return -1

def timestamp(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"invalid outbox watermark: {value}")
        return None

def validate_generation(status, label, *, require_clean_dirty):
    if not isinstance(status, dict):
        errors.append(f"{label} status is missing")
        return
    if status.get("read_model_status") != "fresh":
        errors.append(f"{label} read_model_status is not fresh")
    if not status.get("active_generation_id"):
        errors.append(f"{label} active_generation_id is missing")
    if status.get("building_generation_id") not in (None, ""):
        errors.append(f"{label} still has a building generation")
    if status.get("consistency_status") != "fresh":
        errors.append(f"{label} consistency_status is not fresh")
    if status.get("consistency_failures"):
        errors.append(f"{label} has consistency failures")
    if status.get("all_scope_parent_failures"):
        errors.append(f"{label} has all-scope parent failures")
    if status.get("read_model_stale_reasons"):
        errors.append(f"{label} has stale reasons")
    if require_clean_dirty and status.get("dirty_scopes"):
        errors.append(f"{label} still has active dirty scopes")
    backlog = status.get("outbox_backlog")
    if not isinstance(backlog, dict):
        errors.append(f"{label} page refresh backlog is missing")
    elif any(integer(backlog.get(key)) != 0 for key in ("pending", "processing", "failed", "dead_lettered")):
        errors.append(f"{label} has unresolved page refresh events")

rehydrate = load(rehydrate_path)
seed = load(seed_path)
before = load(before_path)
after = load(after_path)
if rehydrate.get("action") != "rehydrate_workbench_read_models":
    errors.append("rehydrate action is not exact")
if rehydrate.get("dry_run") is not False:
    errors.append("rehydrate did not execute")

scope_keys = [str(value) for value in rehydrate.get("scope_keys", [])]
seed_scope_keys = [str(value) for value in seed.get("scope_keys", [])]
if seed.get("status") != "PASS":
    errors.append("rollback rehydrate dirty-scope seed did not pass")
if sorted(seed_scope_keys) != sorted([*scope_keys, "all"]):
    errors.append("rollback rehydrate seed did not cover every month shard and all")
rebuilt = rehydrate.get("rebuilt") if isinstance(rehydrate.get("rebuilt"), list) else []
rebuilt_scope_keys = [str(item.get("scope_key")) for item in rebuilt if isinstance(item, dict)]
if sorted(scope_keys) != sorted(rebuilt_scope_keys):
    errors.append("rehydrate did not rebuild every discovered shard")
for item in rebuilt:
    if isinstance(item, dict):
        validate_generation(item.get("status"), f"scope {item.get('scope_key')}", require_clean_dirty=False)
all_payload = rehydrate.get("all")
validate_generation(
    all_payload.get("status") if isinstance(all_payload, dict) else None,
    "all-scope publish",
    require_clean_dirty=False,
)
validate_generation(rehydrate.get("status"), "rehydrate final", require_clean_dirty=True)
validate_generation(after.get("status"), "offline audit", require_clean_dirty=True)

def active_generations(payload):
    rows = payload.get("active_generations") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return {}
    return {
        str(row.get("scope_key")): str(row.get("generation_id"))
        for row in rows
        if isinstance(row, dict) and row.get("scope_key") and row.get("generation_id")
    }

before_active_generations = active_generations(before)
after_active_generations = active_generations(after)
rebuilt_active_generations = {
    str(item.get("scope_key")): str(item["status"].get("active_generation_id"))
    for item in rebuilt
    if isinstance(item, dict)
    and isinstance(item.get("status"), dict)
    and item["status"].get("active_generation_id")
}
if not scope_keys:
    errors.append("previous-release rehydrate discovered no Workbench month shards")
new_generation_ids = []
for scope_key in scope_keys:
    after_generation_id = after_active_generations.get(scope_key)
    if not after_generation_id:
        errors.append(f"scope {scope_key} has no active generation after rehydrate")
        continue
    if after_generation_id == before_active_generations.get(scope_key):
        errors.append(f"scope {scope_key} did not create a new Workbench generation")
    else:
        new_generation_ids.append(after_generation_id)
    if rebuilt_active_generations.get(scope_key) != after_generation_id:
        errors.append(f"scope {scope_key} new Workbench generation is not active after rehydrate")

before_retirement_history = before.get("retirement_history")
after_retirement_history = after.get("retirement_history")
if not isinstance(before_retirement_history, dict) or not isinstance(after_retirement_history, dict):
    errors.append("retired page terminal-history audit is missing")
elif before_retirement_history != after_retirement_history:
    errors.append("retired page terminal-history evidence changed during offline rehydrate")

before_outbox = before.get("outbox") if isinstance(before.get("outbox"), dict) else {}
after_outbox = after.get("outbox") if isinstance(after.get("outbox"), dict) else {}
if integer(before_outbox.get("processing_count")) != 0:
    errors.append("page refresh outbox was processing before offline rehydrate")
if any(integer(after_outbox.get(key)) != 0 for key in (
    "pending_count", "processing_count", "publishing_count", "unresolved_terminal_count",
)):
    errors.append("page refresh outbox is not quiesced after offline rehydrate")
if integer((after.get("dirty_scopes") or {}).get("processing_count")) != 0:
    errors.append("page dirty scope is processing after offline rehydrate")
if integer((after.get("dirty_scopes") or {}).get("pending_count")) != 0:
    errors.append("page dirty scope is pending after offline rehydrate")
if integer((after.get("dirty_scopes") or {}).get("failed_count")) != 0:
    errors.append("page dirty scope failed during offline rehydrate")
before_latest = timestamp(before_outbox.get("latest_created_at"))
after_latest = timestamp(after_outbox.get("latest_created_at"))
if before_latest is None and after_latest is not None:
    errors.append("a page refresh event was created during offline rehydrate")
elif before_latest is not None and after_latest is not None and after_latest > before_latest:
    errors.append("page refresh outbox watermark advanced during offline rehydrate")
if integer(after_outbox.get("total_count")) > integer(before_outbox.get("total_count")):
    errors.append("page refresh outbox count increased during offline rehydrate")

payload = {
    "status": "PASS" if not errors else "FAIL",
    "previous_release": previous_release,
    "previous_release_rehydrate": str(rehydrate_path),
    "rollback_seed": str(seed_path),
    "before_audit": str(before_path),
    "after_audit": str(after_path),
    "rebuilt_scope_count": len(rebuilt_scope_keys),
    "rebuilt_generation_ids": sorted(new_generation_ids),
    "active_generation_id": (after.get("status") or {}).get("active_generation_id"),
    "retirement_history": after_retirement_history,
    "outbox_watermark_before": before_outbox.get("latest_created_at"),
    "outbox_watermark_after": after_outbox.get("latest_created_at"),
    "errors": errors,
}
output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
raise SystemExit(0 if not errors else 1)
PY
  then
    cat "$validation_report" >&2 || true
    return 1
  fi
  chmod 0600 \
    "$rehydrate_report" "$seed_report" "$before_report" "$after_report" "$validation_report" "$stderr_report"
  cat "$validation_report"
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
    --execute)
      [[ "$#" -eq 3 && "${2:-}" == "--expected-fingerprint" && "${3:-}" =~ ^[a-f0-9]{64}$ ]] || \
        die "workbench-requirement-repair only permits the four fixed modes"
      ;;
    --rollback-dry-run|--rollback)
      [[ "$#" -eq 3 && "${2:-}" == "--expected-fingerprint" && "${3:-}" =~ ^[a-f0-9]{64}$ ]] || \
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

settings_data_reset_restore_point() {
  local release="${1:-}" run_id="${2:-}" action="${3:-}" operator="${4:-}"
  [[ -n "$release" ]] || die "settings-data-reset-restore-point requires release name"
  [[ "$run_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]] \
    || die "settings-data-reset-restore-point run-id must be 1..80 safe filename characters"
  case "$action" in
    reset_bank_transactions|reset_invoices|reset_oa_and_rebuild) ;;
    *) die "settings-data-reset-restore-point action is unsupported" ;;
  esac
  [[ -n "$operator" ]] || die "settings-data-reset-restore-point operator is required"
  [[ $# -le 4 ]] || die "settings-data-reset-restore-point accepts release, run-id, action and operator"

  local src manifest_path impact_fingerprint
  src="$(release_src "$release")"
  manifest_path="$WRITE_E2E_BACKUP_ROOT/$run_id/manifest.json"
  impact_fingerprint="$(
    set -a
    # shellcheck disable=SC1090
    source "$COMMON_ENV"
    # shellcheck disable=SC1090
    source "$SECRETS_ENV"
    # shellcheck disable=SC1090
    source "$MIGRATOR_ENV"
    set +a
    PYTHONPATH="$src/backend/src${PYTHONPATH:+:$PYTHONPATH}" \
      "$API_PYTHON" -m fin_ops_platform.tools.settings_data_reset_restore_point \
        preview --action "$action" --fingerprint-only
  )"
  [[ "$impact_fingerprint" =~ ^[0-9a-f]{64}$ ]] \
    || die "settings-data-reset-restore-point preview returned an invalid fingerprint"
  write_operation_restore_point "$release" "$run_id"
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
      "$API_PYTHON" -m fin_ops_platform.tools.settings_data_reset_restore_point register \
        --action "$action" \
        --manifest "$manifest_path" \
        --expected-impact-fingerprint "$impact_fingerprint" \
        --created-by "$operator"
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
  [[ "$request_id" =~ ^[0-9a-f]{32}$ ]] || die "request id must be 32 lowercase hexadecimal characters"
  [[ $# -le 1 ]] || die "api-request-error accepts only request id"
  local match
  match="$(journalctl -u fin-ops.service --since '2 hours ago' --no-pager -o cat \
    | grep -F "\"request_id\": \"$request_id\"" | tail -n 1 || true)"
  [[ -n "$match" ]] || die "request error not found in the bounded journal window"
  printf '%s\n' "$match"
}

api_request_trace() {
  local request_id="${1:-}"
  [[ "$request_id" =~ ^[0-9a-f]{32}$ ]] || die "request id must be 32 lowercase hexadecimal characters"
  [[ $# -le 1 ]] || die "api-request-trace accepts only request id"
  local journal line_number trace
  journal="$(journalctl -u fin-ops.service --since '2 hours ago' --no-pager -o cat)"
  line_number="$(printf '%s\n' "$journal" | grep -n -F "\"request_id\": \"$request_id\"" | tail -n 1 | cut -d: -f1 || true)"
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
  [[ "$request_id" =~ ^[0-9a-f]{32}$ ]] || die "request id must be 32 lowercase hexadecimal characters"
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
  local dispatcher_restart_override="${3:-auto}"
  local rollback_page_runtime_mode="${4:-direct-only}"
  local rollback_page_runtime_evidence="${5:-}"
  local rollback_candidate_release="${6:-}"
  local src runtime_worker_helper_src active_workers dispatcher_was_active=false
  local required_existing_worker_envs=""
  [[ "$release_profile" == "frontend" || "$release_profile" == "runtime" || "$release_profile" == "acl" ]] \
    || die "unsupported activation profile: $release_profile"
  src="$(release_src "$release")"
  runtime_worker_helper_src="$src"
  assert_runtime_env_contract
  active_workers="$(active_worker_services)"
  if [[ "$dispatcher_restart_override" == "true" ]]; then
    dispatcher_was_active=true
  elif [[ "$dispatcher_restart_override" == "false" ]]; then
    dispatcher_was_active=false
  elif [[ "$dispatcher_restart_override" == "auto" ]] \
    && systemctl is-active --quiet fin-ops-rabbitmq-dispatcher.service; then
    dispatcher_was_active=true
  elif [[ "$dispatcher_restart_override" != "auto" ]]; then
    die "invalid dispatcher restart override: $dispatcher_restart_override"
  fi
  case "$rollback_page_runtime_mode" in
    direct-only)
      release_has_workbench_page_read_model "$src" \
        && die "page read-model release activation requires the audited rollback-only path"
      ;;
    audited-previous-page-runtime)
      release_has_workbench_page_read_model "$src" \
        || die "audited previous-page-runtime mode requires a page read-model release"
      [[ -n "$rollback_candidate_release" ]] \
        || die "audited previous-page-runtime mode requires the exact direct candidate release"
      runtime_worker_helper_src="$(release_src "$rollback_candidate_release")"
      release_has_workbench_page_read_model "$runtime_worker_helper_src" \
        && die "audited previous-page-runtime rollback candidate must be direct-only"
      assert_previous_workbench_rollback_evidence \
        "$release" "$rollback_page_runtime_evidence"
      ;;
    *)
      die "invalid Workbench page runtime activation mode: $rollback_page_runtime_mode"
      ;;
  esac
  systemctl stop fin-ops.service
  if [[ "$release_profile" != "frontend" \
    || "$rollback_page_runtime_mode" == "audited-previous-page-runtime" ]]; then
    systemctl stop fin-ops-rabbitmq-dispatcher.service >/dev/null 2>&1 || true
  fi
  stop_runtime_worker_services_for_activation
  if [[ "$release_profile" == "frontend" \
    && "$rollback_page_runtime_mode" == "direct-only" ]]; then
    write_api_dropin "$src"
    write_worker_dropin "$src"
    write_dispatcher_dropin "$src"
    publish_frontend "$src"
    restart_services "$active_workers" "$dispatcher_was_active"
    wait_required_workers_ready
    status
    return 0
  fi
  run_schema_migrations "$src"
  assert_settings_access_control_database_guard "$src"
  sync_python_envs "$src"
  if [[ "$rollback_page_runtime_mode" == "direct-only" ]]; then
    run_workbench_direct_compatibility_preflight \
      "$src" "$RELEASE_GATE_EVIDENCE_ROOT/$release"
  fi
  install_runtime_worker_helper "$runtime_worker_helper_src"
  retire_unregistered_worker_services "$src"
  retire_workbench_page_runtime_assets "$src"
  if [[ "$rollback_page_runtime_mode" == "direct-only" ]]; then
    retire_workbench_generation_retention
  fi
  sync_rabbitmq_dispatcher_event_types "$src"
  if [[ "$rollback_page_runtime_mode" == "direct-only" ]]; then
    assert_retired_page_runtime_quiesced \
      "$src" "$RELEASE_GATE_EVIDENCE_ROOT/$release/retired-workbench-page-runtime.json"
  fi
  archive_legacy_current
  write_api_dropin "$src"
  write_worker_dropin "$src"
  write_dispatcher_dropin "$src"
  if [[ "$rollback_page_runtime_mode" == "audited-previous-page-runtime" ]]; then
    if ! restore_previous_workbench_page_worker_env \
      "$release" "$rollback_candidate_release" \
      "$(dirname "$rollback_page_runtime_evidence")"; then
      die "failed to restore exact Workbench page worker env before previous release ensure"
    fi
    required_existing_worker_envs="workbench"
  fi
  ensure_runtime_workers "$src" "$required_existing_worker_envs"
  if [[ "$rollback_page_runtime_mode" == "audited-previous-page-runtime" ]]; then
    restore_previous_workbench_generation_retention_for_rollback "$src"
  fi
  install_runtime_queue_history_retention "$src"
  install_oa_sync_enqueue_timer "$src"
  publish_frontend "$src"
  restart_services "" "$dispatcher_was_active"
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
    "registered_workers": inventory.get("registered_workers") or [],
    "registered_read_models": inventory.get("registered_read_models") or [],
    "registered_read_model_count": int(inventory.get("registered_read_model_count") or 0),
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
    "registered_workers": inventory.get("registered_workers") or [],
    "registered_read_models": inventory.get("registered_read_models") or [],
    "registered_read_model_count": int(inventory.get("registered_read_model_count") or 0),
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
retired_page_runtime_path = root / "retired-workbench-page-runtime.json"
retired_page_runtime = (
    json.loads(retired_page_runtime_path.read_text(encoding="utf-8"))
    if retired_page_runtime_path.is_file()
    else None
)
retired_page_runtime_window_path = root / "retired-workbench-page-runtime-window.json"
retired_page_runtime_window = (
    json.loads(retired_page_runtime_window_path.read_text(encoding="utf-8"))
    if retired_page_runtime_window_path.is_file()
    else None
)
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
runtime_window_valid = isinstance(retired_page_runtime_window, dict) and (
    (
        retired_page_runtime_window.get("required") is True
        and retired_page_runtime_window.get("status") == "PASS"
    )
    or (
        retired_page_runtime_window.get("required") is False
        and retired_page_runtime_window.get("status") == "NOT_REQUIRED"
    )
)
passed = (
    os.environ["GATE_STATUS"] == "PASS"
    and required_final_checkpoint in checkpoints
    and runtime_window_valid
)
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
    "registered_workers": latest.get("registered_workers") or [],
    "registered_read_models": latest.get("registered_read_models") or [],
    "registered_read_model_count": int(latest.get("registered_read_model_count", -1)),
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
    "retired_workbench_page_runtime": retired_page_runtime,
    "retired_workbench_page_runtime_window": retired_page_runtime_window,
    "retired_workbench_page_runtime_window_status": (
        retired_page_runtime_window.get("status")
        if isinstance(retired_page_runtime_window, dict)
        else None
    ),
    "retired_workbench_page_runtime_zero_delta": runtime_window_valid,
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
  local previous_src dispatcher_was_active=false dispatcher_state_path rollback_page_runtime_mode=direct-only
  local rollback_page_runtime_evidence=""
  local schema_plan_path="$evidence_dir/schema-compatibility-plan.json"
  local schema_evidence_required=false
  abandon_retired_workbench_page_runtime_window
  cat "$evidence_dir/$failure_checkpoint/checkpoint.json" >&2 || true
  dispatcher_state_path="$evidence_dir/dispatcher-was-active"
  if [[ -f "$dispatcher_state_path" ]] \
    && [[ "$(tr -d '[:space:]' <"$dispatcher_state_path")" == "true" ]]; then
    dispatcher_was_active=true
  elif [[ ! -f "$dispatcher_state_path" ]] \
    && systemctl is-active --quiet fin-ops-rabbitmq-dispatcher.service; then
    dispatcher_was_active=true
  fi
  enter_runtime_maintenance
  if [[ -f "$schema_plan_path" ]]; then
    schema_evidence_required="$("$API_PYTHON" - "$schema_plan_path" <<'PY'
import json
from pathlib import Path
import sys
print("true" if json.loads(Path(sys.argv[1]).read_text())["requires_compatibility_evidence"] else "false")
PY
)"
  fi
  if [[ "$schema_evidence_required" == "true" ]] \
    && ! schema_compatibility_evidence_valid "$candidate" "$schema_plan_path"; then
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "release gate failed at $failure_checkpoint; previous release is not proven compatible with the candidate schema, production remains in maintenance for forward repair"
  fi
  if [[ "$release_profile" == "acl" ]]; then
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "ACL release gate failed at $failure_checkpoint; production remains in maintenance for forward repair"
  fi
  if ! release_is_acl_safe "$previous_release"; then
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "release gate failed at $failure_checkpoint; previous release lacks $SETTINGS_ACL_CONTRACT, production remains in maintenance for forward repair"
  fi
  previous_src="$(release_src "$previous_release")"
  if release_has_workbench_page_read_model "$previous_src"; then
    rollback_page_runtime_mode=audited-previous-page-runtime
    rollback_page_runtime_evidence="$evidence_dir/rollback-workbench-validation.json"
    if ! prepare_previous_workbench_page_runtime "$previous_release" "$evidence_dir"; then
      write_release_gate_evidence \
        "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
      die "release gate failed at $failure_checkpoint; previous-release Workbench rehydrate or strict offline audit failed, production remains in maintenance"
    fi
  fi
  if (activate_release "$previous_release" \
    "$release_profile" "$dispatcher_was_active" "$rollback_page_runtime_mode" \
    "$rollback_page_runtime_evidence" "$candidate"); then
    if [[ "$release_profile" == "frontend" ]]; then
      release_gate_frontend_checkpoint \
        "$previous_release" rollback "$admin_token" "$evidence_dir" && rolled_back=true
    elif release_gate_checkpoint \
      "$previous_release" rollback "$admin_token" "$evidence_dir" preflight "$candidate"; then
      rolled_back=true
    fi
  fi
  if [[ "$rolled_back" == true ]] \
    && ! (discard_workbench_page_worker_env_rollback_backup \
      "$candidate" "$previous_release" "$evidence_dir"); then
    rolled_back=false
  fi
  if [[ "$rolled_back" != true ]]; then
    enter_runtime_maintenance
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
  local schema_plan_path schema_evidence_required
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
  schema_plan_path="$(mktemp /run/finops-schema-plan.XXXXXX)"
  trap 'abandon_retired_workbench_page_runtime_window; rm -f -- "$profile_report" "$schema_plan_path"' EXIT
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
  schema_compatibility_plan "$release" --json >"$schema_plan_path"
  schema_evidence_required="$("$API_PYTHON" - "$schema_plan_path" <<'PY'
import json
from pathlib import Path
import sys
print("true" if json.loads(Path(sys.argv[1]).read_text())["requires_compatibility_evidence"] else "false")
PY
)"
  if [[ "$schema_evidence_required" == "true" ]] \
    && ! schema_compatibility_evidence_valid "$release" "$schema_plan_path"; then
    die "candidate has pending migrations but no exact previous-release compatibility evidence; services were not stopped and schema was not changed"
  fi
  evidence_dir="$RELEASE_GATE_EVIDENCE_ROOT/$release"
  [[ ! -e "$evidence_dir" ]] || die "release gate evidence already exists: $evidence_dir"
  install -d -m 0700 "$evidence_dir"
  if systemctl is-active --quiet fin-ops-rabbitmq-dispatcher.service; then
    printf '%s\n' true >"$evidence_dir/dispatcher-was-active"
  else
    printf '%s\n' false >"$evidence_dir/dispatcher-was-active"
  fi
  chmod 0600 "$evidence_dir/dispatcher-was-active"
  install -m 0600 "$profile_report" "$evidence_dir/profile.json"
  install -m 0600 "$schema_plan_path" "$evidence_dir/schema-compatibility-plan.json"
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
  if ! (capture_workbench_page_worker_env_for_cutover \
    "$release" "$previous_release" "$evidence_dir"); then
    write_release_gate_evidence \
      "$release" "$previous_release" "$evidence_dir" FAIL false "$release_profile" page_worker_env_capture || true
    die "failed to capture the exact live Workbench page worker env before cutover; services were not stopped"
  fi
  if ! (activate_release "$release" "$release_profile"); then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" activation "$release_profile"
  fi
  if ! start_retired_workbench_page_runtime_window \
    "$release" "$previous_release" "$evidence_dir"; then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" retired_page_observer_start "$release_profile"
  fi
  if [[ "$release_profile" == "frontend" ]]; then
    if ! release_gate_frontend_checkpoint "$release" t0 "$admin_token" "$evidence_dir"; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t0 "$release_profile"
    fi
  else
    if ! release_gate_checkpoint "$release" t0 "$admin_token" "$evidence_dir" stability; then
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
  if ! finish_retired_workbench_page_runtime_window \
    "$evidence_dir/retired-workbench-page-runtime-window.json"; then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" retired_page_runtime_window "$release_profile"
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
    "registered_workers": [
        "import",
        "oa-sync",
        "settings-maintenance",
        "workbench-matching",
        "workbench-relation",
    ],
    "registered_read_models": ["workbench_relation"],
    "registered_read_model_count": 1,
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
            "retired_workbench_page_runtime_zero_delta": True,
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
  if ! (discard_workbench_page_worker_env_rollback_backup \
    "$release" "$previous_release" "$evidence_dir"); then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" backup_cleanup "$release_profile"
  fi
  rm -f -- "$profile_report" "$schema_plan_path"
  trap - EXIT
}
cmd="${1:-}"
case "$cmd" in
  check-release)
    src="$(release_src "${2:-}")"
    audit_python_dependencies "$src"
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
  schema-compatibility-plan)
    shift
    schema_compatibility_plan "$@"
    ;;
  schema-compatibility-evidence-install)
    shift
    schema_compatibility_evidence_install "$@"
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
  settings-data-reset-restore-point)
    shift
    settings_data_reset_restore_point "$@"
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

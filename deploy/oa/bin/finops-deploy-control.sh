#!/usr/bin/env bash
set -Eeuo pipefail

RELEASE_ROOT="${FINOPS_RELEASE_ROOT:-/opt/fin-ops/releases}"
API_PYTHON="${FINOPS_API_PYTHON:-/opt/fin-ops/venv/bin/python}"
WORKER_PYTHON="${FINOPS_WORKER_PYTHON:-/opt/fin-ops/venv/bin/python}"
ENV_DIR="${FINOPS_ENV_DIR:-/etc/fin-ops}"
API_DROPIN_DIR="${FINOPS_API_DROPIN_DIR:-/etc/systemd/system/fin-ops.service.d}"
WORKER_DROPIN_DIR="${FINOPS_WORKER_DROPIN_DIR:-/etc/systemd/system/fin-ops-worker@.service.d}"
API_DROPIN="$API_DROPIN_DIR/99-deploy-release.conf"
WORKER_DROPIN="$WORKER_DROPIN_DIR/99-deploy-release.conf"
FRONTEND_DIR="${FINOPS_FRONTEND_DIR:-/www/wwwroot/fin-ops/dist}"
LEGACY_CURRENT_DIR="${FINOPS_LEGACY_CURRENT_DIR:-/opt/fin-ops/current}"
LEGACY_CURRENT_ARCHIVE_DIR="${FINOPS_LEGACY_CURRENT_ARCHIVE_DIR:-/opt/fin-ops/legacy-current-archives}"
COMMON_ENV="$ENV_DIR/fin-ops.common.env"
SECRETS_ENV="$ENV_DIR/fin-ops.secrets.env"
MIGRATOR_ENV="$ENV_DIR/fin-ops.postgres-migrator.env"
DEPLOY_CONTROL_HELPER="${FINOPS_DEPLOY_CONTROL_HELPER:-/usr/local/sbin/finops-deploy-control}"
ENSURE_RUNTIME_WORKERS_HELPER="${FINOPS_ENSURE_RUNTIME_WORKERS_HELPER:-/usr/local/sbin/finops-ensure-runtime-workers}"
WRITE_E2E_BACKUP_ROOT="${FINOPS_WRITE_E2E_BACKUP_ROOT:-/opt/fin-ops/backups/write-operation-e2e}"
STANDARD_WRITE_E2E_SCENARIO="${FINOPS_STANDARD_WRITE_E2E_SCENARIO:-/opt/fin-ops/runtime-smoke/write-operation-e2e-scenarios.json}"
RELEASE_GATE_EVIDENCE_ROOT="${FINOPS_RELEASE_GATE_EVIDENCE_ROOT:-/opt/fin-ops/runtime-smoke/release-gates}"
SCHEMA_COMPATIBILITY_EVIDENCE_ROOT="${FINOPS_SCHEMA_COMPATIBILITY_EVIDENCE_ROOT:-/opt/fin-ops/runtime-smoke/schema-compatibility}"
SETTINGS_ACL_EVIDENCE_ROOT="${FINOPS_SETTINGS_ACL_EVIDENCE_ROOT:-/opt/fin-ops/evidence}"
readonly IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT="/opt/fin-ops/runtime-smoke/import-audit-repair-artifacts"
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
  settings-normalize <release-name> [--dry-run|--execute]
                                      normalize App settings through the canonical service/repository boundary
  import-audit-repair <release-name> [--dry-run|--execute --expected-fingerprint <sha256>|--delete-rollback-manifest-artifact <name> --expected-rollback-manifest-fingerprint <sha256>] [--repair-all-oa-attachment-invoice-links --rollback-manifest-path <fixed-root/path> --operator-id <id> --reason <text>] [--retire-etc-session-id <id> ...] [--normalize-reverted-batch-id <id> ...] [--discover-recover-import-job-id <id>] [--recover-import-job-id <id> --recover-event-id <id> --recover-background-job-id <id> --recover-session-id <id> --recover-file-id <id> ...] [--repair-bank-source <session>=<file,...> ... --expected-bank-target-count <n> --expected-bank-protected-count <n> --expected-bank-duplicate-delete-count <n> --expected-bank-replay-create-count <n> --expected-bank-replay-repaired-duplicate-count <n> --operator-id <id> [--cleanup-related-bank-duplicates --expected-bank-category-cleanup-count <n> --expected-bank-workbench-withdraw-count <n> --expected-bank-workbench-transaction-id <id>]]
  import-audit-repair-artifact-delete <artifact-name> <rollback-manifest-fingerprint>
                                      verify and delete one task-scoped rollback artifact
                                      repair strict import facts through the canonical PostgreSQL boundary
  bank-transaction-category-repair <release-name> [--dry-run|--apply --operator <actor> --expected-candidate-count <count>]
                                      repair proven historical manual category clears through the canonical writer
  restart                              restart API and active workers
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
forward_only_versions = {"0149"}
forward_only = bool(pending) and all(
    item["version"] in forward_only_versions for item in pending
)


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
    "forward_only": forward_only,
    "rollback_supported": not forward_only,
    "requires_compatibility_evidence": bool(pending) and not forward_only,
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

enter_runtime_maintenance() {
  systemctl stop fin-ops.service >/dev/null 2>&1 || true
  stop_runtime_worker_services_for_activation >/dev/null 2>&1 || true
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

retire_removed_runtime_assets() {
  local generation_service generation_timer legacy_service legacy_dir
  generation_service="$(basename "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT")"
  generation_timer="$(basename "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT")"
  systemctl disable --now "$generation_timer" >/dev/null 2>&1 || true
  systemctl stop "$generation_service" >/dev/null 2>&1 || true
  rm -f -- \
    "$PRUNE_WORKBENCH_GENERATIONS_HELPER" \
    "$PRUNE_WORKBENCH_GENERATIONS_SERVICE_UNIT" \
    "$PRUNE_WORKBENCH_GENERATIONS_TIMER_UNIT" \
    "$ENV_DIR/fin-ops.worker.workbench.env" \
    "$ENV_DIR/fin-ops.worker.workbench-relation.env" \
    "$ENV_DIR/fin-ops.rabbitmq-dispatcher.env" \
    "$ENV_DIR/fin-ops.rabbitmq-dispatcher.env.bak.20260526144711" \
    "$ENV_DIR/fin-ops.rabbitmq-dispatcher.env.bak-import-fact-20260528190525" \
    "$ENV_DIR/fin-ops.rabbitmq-dispatcher.env.bak-invoice-lifecycle" \
    "$ENV_DIR/fin-ops.rabbitmq-dispatcher.env.bak-invoice-lifecycle-3" \
    "$ENV_DIR/fin-ops.rabbitmq-monitoring.env" \
    "$ENV_DIR/fin-ops.rabbitmq-topology.env" \
    "$ENV_DIR/fin-ops.rabbitmq-worker.env" \
    "$ENV_DIR/fin-ops.worker.bank-detail-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.cost-tax-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.cost-tax-rabbitmq.env.bak-20260528204437" \
    "$ENV_DIR/fin-ops.worker.file-migration-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.import-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.search-pending-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.workbench-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker-import-rabbitmq.env" \
    "$ENV_DIR/fin-ops.worker.oa-sync-rabbitmq.env"
  for legacy_service in fin-ops-rabbitmq-dispatcher.service fin-ops-rabbitmq-topology.service; do
    systemctl disable --now "$legacy_service" >/dev/null 2>&1 || true
    systemctl reset-failed "$legacy_service" >/dev/null 2>&1 || true
    rm -f -- "/etc/systemd/system/$legacy_service"
    legacy_dir="/etc/systemd/system/$legacy_service.d"
    rm -f -- "$legacy_dir/99-deploy-release.conf"
    rmdir "$legacy_dir" >/dev/null 2>&1 || true
  done
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
ExecStart=$WORKER_PYTHON -m fin_ops_platform.app.worker --worker-id \${FIN_OPS_WORKER_ID} --registration \${FIN_OPS_WORKER_INSTANCE} --worker-instance \${FIN_OPS_WORKER_INSTANCE} \$FIN_OPS_WORKER_ARGS --lock-timeout-seconds \${FIN_OPS_WORKER_LOCK_TIMEOUT_SECONDS} --task-timeout-seconds \${FIN_OPS_WORKER_TASK_TIMEOUT_SECONDS} --statement-timeout-seconds \${FIN_OPS_WORKER_STATEMENT_TIMEOUT_SECONDS} --max-attempts \${FIN_OPS_WORKER_MAX_ATTEMPTS} --max-events-per-iteration \${FIN_OPS_WORKER_MAX_EVENTS_PER_ITERATION}
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
  systemctl enable "$timer_unit"
}

stop_oa_sync_enqueue_timer() {
  local timer_unit
  timer_unit="$(basename "$OA_SYNC_ENQUEUE_TIMER_UNIT")"
  systemctl stop "$timer_unit" >/dev/null 2>&1 || true
}

start_oa_sync_enqueue_timer() {
  local service_unit timer_unit
  service_unit="$(basename "$OA_SYNC_ENQUEUE_SERVICE_UNIT")"
  timer_unit="$(basename "$OA_SYNC_ENQUEUE_TIMER_UNIT")"
  systemctl reset-failed "$service_unit" "$timer_unit" >/dev/null 2>&1 || true
  systemctl start "$timer_unit"
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

status() {
  systemctl is-active fin-ops.service || true
  active_worker_services | while read -r svc; do
    [[ -n "$svc" ]] || continue
    printf '%s ' "$svc"
    systemctl is-active "$svc" || true
  done
  systemctl show fin-ops.service -p EnvironmentFiles -p WorkingDirectory -p ExecStart --no-pager
  active_worker_services | while read -r svc; do
    [[ -n "$svc" ]] || continue
    systemctl show "$svc" -p EnvironmentFiles -p WorkingDirectory -p Environment --no-pager || true
  done
}

active_release_names() {
  {
    systemctl show fin-ops.service -p WorkingDirectory -p ExecStart -p Environment --no-pager || true
    active_worker_services | while read -r svc; do
      [[ -n "$svc" ]] || continue
      systemctl show "$svc" -p WorkingDirectory -p ExecStart -p Environment --no-pager || true
    done
  } | grep -oE '/opt/fin-ops/releases/[^/[:space:]]+' | sed 's#^/opt/fin-ops/releases/##' | sort -u
}

cleanup_dropins() {
  local dir
  for dir in "$API_DROPIN_DIR" "$WORKER_DROPIN_DIR"; do
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
  run_with_runtime_env "$src" -m fin_ops_platform.tools.audit_page_canonical_data \
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
  [[ -z "${FINOPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT:-}" ]] \
    || die "import Audit repair artifact root override is not supported"
  local src
  src="$(release_src "$release")"
  assert_runtime_env_contract
  [[ ! -L "$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT" ]] \
    || die "import Audit repair artifact root must not be a symlink"
  install -d -m 0700 -o root -g root "$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT"
  (
    export FIN_OPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT="$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT"
    run_with_runtime_env "$src" -m fin_ops_platform.tools.import_audit_repair_ops "$@"
  )
}

import_audit_repair_artifact_delete() {
  local artifact_name="${1:-}" expected_fingerprint="${2:-}"
  [[ -z "${FINOPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT:-}" ]] \
    || die "import Audit repair artifact root override is not supported"
  [[ "$artifact_name" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.json$ ]] \
    || die "import Audit repair artifact name must be a safe .json filename"
  [[ "$expected_fingerprint" =~ ^[0-9a-f]{64}$ ]] \
    || die "import Audit repair artifact delete requires a lowercase SHA-256 fingerprint"
  [[ $# -le 2 ]] \
    || die "import-audit-repair-artifact-delete accepts only artifact name and fingerprint"

  local artifact_path actual_fingerprint
  artifact_path="$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT/$artifact_name"
  [[ -d "$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT" && ! -L "$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT" ]] \
    || die "import Audit repair artifact root is unavailable"
  [[ "$(stat -c '%U:%a' "$IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT")" == "root:700" ]] \
    || die "import Audit repair artifact root must be root-owned with mode 0700"
  [[ -f "$artifact_path" && ! -L "$artifact_path" ]] \
    || die "import Audit repair artifact is unavailable"
  [[ "$(stat -c '%U:%a:%h' "$artifact_path")" == "root:600:1" ]] \
    || die "import Audit repair artifact must be root-owned, mode 0600, with one hard link"
  actual_fingerprint="$($API_PYTHON - "$artifact_path" <<'PY'
import hashlib
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    manifest = json.load(handle)
if not isinstance(manifest, dict):
    raise SystemExit("rollback manifest must be a JSON object")
encoded = json.dumps(
    manifest,
    ensure_ascii=False,
    sort_keys=True,
    default=str,
).encode("utf-8")
print(hashlib.sha256(encoded).hexdigest())
PY
)"
  [[ "$actual_fingerprint" == "$expected_fingerprint" ]] \
    || die "import Audit repair artifact fingerprint mismatch"
  rm -f -- "$artifact_path"
  printf '{"status":"deleted","artifact_name":"%s","rollback_manifest_fingerprint":"%s"}\n' \
    "$artifact_name" "$expected_fingerprint"
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

activate_release() {
  local release="$1"
  local release_profile="${2:-runtime}"
  local src active_workers
  [[ "$release_profile" == "frontend" || "$release_profile" == "runtime" || "$release_profile" == "acl" ]] \
    || die "unsupported activation profile: $release_profile"
  src="$(release_src "$release")"
  assert_runtime_env_contract
  active_workers="$(active_worker_services)"
  stop_oa_sync_enqueue_timer
  systemctl stop fin-ops.service
  stop_runtime_worker_services_for_activation
  retire_removed_runtime_assets
  if [[ "$release_profile" == "frontend" ]]; then
    write_api_dropin "$src"
    write_worker_dropin "$src"
    publish_frontend "$src"
    restart_services "$active_workers"
    wait_required_workers_ready
    status
    return 0
  fi
  run_schema_migrations "$src" || die "schema migration failed; candidate was not activated"
  assert_settings_access_control_database_guard "$src"
  sync_python_envs "$src"
  run_workbench_direct_compatibility_preflight \
    "$src" "$RELEASE_GATE_EVIDENCE_ROOT/$release"
  install_runtime_worker_helper "$src"
  retire_unregistered_worker_services "$src"
  archive_legacy_current
  write_api_dropin "$src"
  write_worker_dropin "$src"
  ensure_runtime_workers "$src"
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
    "registered_workers": inventory.get("registered_workers") or [],
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
  local src verification_src checkpoint_dir domain_report closure_report inventory_report runtime_report
  local required_worker_instance
  local -a closure_args
  [[ "$profile" == "preflight" || "$profile" == "full" || "$profile" == "stability" ]] \
    || die "unsupported release gate profile: $profile"
  src="$(release_src "$release")"
  verification_src="$(release_src "$verification_release")"
  checkpoint_dir="$evidence_dir/$label"
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
      --write-target-ms 5000
      --http-target-ms 1000
      --health-ready-target-ms 1000
      --timeout-seconds 60
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
  # Authenticated probes can enqueue short-lived PostgreSQL work. Give only
  # pending/processing rows a bounded drain window; failed/dead-lettered work
  # remain immediate checkpoint failures.
  if [[ "$profile" == "stability" ]]; then
    local drain_attempt
    for drain_attempt in 1 2 3 4 5; do
      if RUNTIME_REPORT="$runtime_report" "$API_PYTHON" - <<'PY'
import json
import os

payload = json.load(open(os.environ["RUNTIME_REPORT"], encoding="utf-8"))
queue = payload.get("queue_backlog") or {}
failed_or_dead = sum(int(queue.get(key) or 0) for key in ("failed", "dead_lettered"))
active = sum(int(queue.get(key) or 0) for key in ("pending", "processing"))
raise SystemExit(0 if active == 0 or failed_or_dead > 0 else 1)
PY
      then
        break
      fi
      sleep 1
      (
        set -a
        # shellcheck disable=SC1090
        source "$COMMON_ENV"
        # shellcheck disable=SC1090
        source "$SECRETS_ENV"
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
    done
  fi
  RELEASE_NAME="$release" \
  CHECKPOINT_LABEL="$label" \
  CHECKPOINT_PROFILE="$profile" \
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
domain = load("DOMAIN_REPORT")
closure = load("CLOSURE_REPORT")
runtime = load("RUNTIME_REPORT")
closure_checks = closure.get("checks", []) if isinstance(closure, dict) else []
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
pending = (
    sum(int(queue_backlog.get(status) or 0) for status in ("pending", "processing"))
    if isinstance(queue_backlog, dict)
    else -1
)
failed = int(queue_backlog.get("failed") or 0) if isinstance(queue_backlog, dict) else -1
dead_letters = int(queue_backlog.get("dead_lettered") or 0) if isinstance(queue_backlog, dict) else -1
passed = (
    inventory.get("status") == "PASS"
    and domain.get("status") == "pass"
    and closure.get("status") == "pass"
    and (page_canonical_audit_ready or not page_canonical_audit_required)
    and pending == 0
    and failed == 0
    and dead_letters == 0
)
payload = {
    "release_gate_status": "PASS" if passed else "FAIL",
    "release_name": os.environ["RELEASE_NAME"],
    "checkpoint": os.environ["CHECKPOINT_LABEL"],
    "profile": profile,
    "checked_at": datetime.now(UTC).isoformat(),
    "component_statuses": {
        "worker_inventory": inventory.get("status"),
        "domain_contract_audit": domain.get("status"),
        "runtime_sync_closure": closure.get("status"),
        "page_canonical_audit": page_canonical_audit.get("status"),
        "postgres_queue": "pass" if pending == 0 and failed == 0 and dead_letters == 0 else "fail",
    },
    "unknown_worker_count": int(inventory.get("unknown_worker_count") or 0),
    "required_worker_not_ready": int(inventory.get("required_worker_not_ready") or 0),
    "registered_workers": inventory.get("registered_workers") or [],
    "pending_outbox_count": pending,
    "failed_outbox_count": failed,
    "dead_letter_count": dead_letters,
    "runtime_sync_closure_failed_checks": [
        failure.get("name") for failure in closure_failures
    ],
    "runtime_sync_closure_failures": closure_failures,
    "page_canonical_audit": page_canonical_audit,
    "reports": {
        "worker_inventory": os.environ["INVENTORY_REPORT"],
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
for label in ("pre", "t0", "t30", "rollback"):
    path = root / label / "checkpoint.json"
    if path.is_file():
        checkpoints[label] = json.loads(path.read_text(encoding="utf-8"))
latest = next((checkpoints[name] for name in ("t30", "t0", "pre") if name in checkpoints), {})
t0_page_audit = checkpoints.get("t0", {}).get("page_canonical_audit", {})
pre_dlq = int(checkpoints.get("pre", {}).get("dead_letter_count", 0))
final_dlq = int(latest.get("dead_letter_count", pre_dlq))
profile = os.environ["RELEASE_PROFILE"]
required_final_checkpoint = "t0" if profile == "frontend" else "t30"
passed = (
    os.environ["GATE_STATUS"] == "PASS"
    and required_final_checkpoint in checkpoints
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
    "pending_outbox_count": int(latest.get("pending_outbox_count", -1)),
    "dead_letter_delta": final_dlq - pre_dlq,
    "page_canonical_audit_status": (
        t0_page_audit.get("status")
        if isinstance(t0_page_audit, dict)
        else None
    ),
    "frontend_verified": latest.get("frontend_verified") is True if profile == "frontend" else None,
    "queue_stable_after_30_seconds": passed if profile != "frontend" else None,
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
  local schema_plan_path="$evidence_dir/schema-compatibility-plan.json"
  local schema_evidence_required=false
  local schema_rollback_supported=true
  cat "$evidence_dir/$failure_checkpoint/checkpoint.json" >&2 || true
  enter_runtime_maintenance
  if [[ -f "$schema_plan_path" ]]; then
    schema_evidence_required="$("$API_PYTHON" - "$schema_plan_path" <<'PY'
import json
from pathlib import Path
import sys
print("true" if json.loads(Path(sys.argv[1]).read_text())["requires_compatibility_evidence"] else "false")
PY
)"
    schema_rollback_supported="$("$API_PYTHON" - "$schema_plan_path" <<'PY'
import json
from pathlib import Path
import sys
print("true" if json.loads(Path(sys.argv[1]).read_text()).get("rollback_supported", True) else "false")
PY
)"
  fi
  if [[ "$schema_rollback_supported" != "true" ]]; then
    write_release_gate_evidence \
      "$candidate" "$previous_release" "$evidence_dir" FAIL false "$release_profile" "$failure_checkpoint" || true
    die "release gate failed at $failure_checkpoint after a forward-only schema migration; production remains in maintenance for forward repair"
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
  if (activate_release "$previous_release" "$release_profile"); then
    if [[ "$release_profile" == "frontend" ]]; then
      release_gate_frontend_checkpoint \
        "$previous_release" rollback "$admin_token" "$evidence_dir" && rolled_back=true
    elif release_gate_checkpoint \
      "$previous_release" rollback "$admin_token" "$evidence_dir" preflight "$candidate"; then
      rolled_back=true
    fi
  fi
  if [[ "$rolled_back" != true ]]; then
    enter_runtime_maintenance
  elif ! start_oa_sync_enqueue_timer; then
    rolled_back=false
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
  trap 'rm -f -- "$profile_report" "$schema_plan_path"' EXIT
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
    if ! release_gate_checkpoint "$release" t0 "$admin_token" "$evidence_dir" stability; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t0 "$release_profile"
    fi
    sleep 30
    if ! release_gate_checkpoint "$release" t30 "$admin_token" "$evidence_dir" stability; then
      rollback_release_gate \
        "$release" "$previous_release" "$admin_token" "$evidence_dir" t30 "$release_profile"
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
    "registered_workers": [
        "import",
        "oa-sync",
        "settings-maintenance",
        "workbench-matching",
    ],
}
if profile == "frontend":
    required["frontend_verified"] = True
elif profile in {"runtime", "acl"}:
    required.update(
        {
            "pending_outbox_count": 0,
            "dead_letter_delta": 0,
            "page_canonical_audit_status": "pass",
            "queue_stable_after_30_seconds": True,
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
  if ! start_oa_sync_enqueue_timer; then
    rollback_release_gate \
      "$release" "$previous_release" "$admin_token" "$evidence_dir" timer_start "$release_profile"
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
  settings-normalize)
    shift
    settings_normalize "$@"
    ;;
  import-audit-repair)
    shift
    import_audit_repair "$@"
    ;;
  import-audit-repair-artifact-delete)
    shift
    import_audit_repair_artifact_delete "$@"
    ;;
  bank-transaction-category-repair)
    shift
    bank_transaction_category_repair "$@"
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

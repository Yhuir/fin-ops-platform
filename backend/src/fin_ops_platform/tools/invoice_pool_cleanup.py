from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Sequence
import csv
import hashlib
import json
import os
from pathlib import Path
import sys
from typing import Any, TextIO

from fin_ops_platform.services.cutover_preflight import redact_secret_text
from fin_ops_platform.services.import_file_service import parse_invoice_rows, read_xlsx_rows
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


DEFAULT_AUDIT_ROOT = Path(".runtime/backups/invoice-pool-audit")
EXECUTE_GUARD_ENV = "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTE"
BACKUP_CONFIRMED_ENV = "FIN_OPS_INVOICE_POOL_BACKUP_CONFIRMED"
CONFIRM_TOKEN = "DELETE_APP_INVOICES_AND_REIMPORT"
EXECUTABLE_SQL_MARKER = "FIN_OPS_INVOICE_POOL_CLEANUP_EXECUTABLE_SQL"
OA_REVERSE_BATCH_STRATEGIES = ("block", "archive_legacy_polluted_history")
REQUIRED_BACKUP_FILES = (
    "invoice_related_tables.dump",
    "invoice_related_schema.sql",
    "audit_summary.json",
    "checksums.tsv",
)
REQUIRED_BACKUP_FILE_GROUPS = (
    ("data_dump", ("invoice_fact_tables.dump", "invoice_related_tables.dump")),
    ("schema", ("invoice_related_schema.sql",)),
    ("summary", ("backup_summary.json", "audit_summary.json")),
    ("checksum", ("checksums.tsv",)),
)
DRY_RUN_FILES = (
    "summary.json",
    "candidate_delete_full_reset_app_invoices.csv",
    "candidate_delete_targeted_not_in_excel.csv",
    "candidate_delete_targeted_duplicates.csv",
    "candidate_keep_excel_identities.csv",
    "candidate_retire_app_etc_invoices.csv",
    "soft_reference_inventory.csv",
    "draft_cleanup.sql",
)
BLOCKING_SOFT_REFERENCES = {
    ("app", "input_invoice_usage_oa_reverse_batches", "invoice_ids"),
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Preflight canonical invoice pool cleanup and reimport.")
    parser.add_argument(
        "--backup-dir",
        type=Path,
        default=None,
        help="Invoice pool backup/audit directory. Defaults to the latest directory under .runtime/backups/invoice-pool-audit.",
    )
    parser.add_argument(
        "--dry-run-dir",
        type=Path,
        default=None,
        help="Cleanup dry-run artifact directory. Defaults to backup-dir/cleanup_dry_run, or the latest audit cleanup_dry_run when the latest backup is scoped-only.",
    )
    parser.add_argument("--execute", action="store_true", help="Attempt the cleanup. Requires explicit guards and an unblocked plan.")
    parser.add_argument("--confirm-token", default="", help=f"Required with --execute: {CONFIRM_TOKEN}.")
    parser.add_argument(
        "--execution-sql-file",
        type=Path,
        default=None,
        help="Executable cleanup SQL artifact. Required with --execute after all guards pass.",
    )
    parser.add_argument(
        "--execution-sql-sha256",
        default="",
        help="Exact SHA-256 digest of --execution-sql-file. Required with --execute.",
    )
    parser.add_argument(
        "--oa-reverse-batch-strategy",
        choices=OA_REVERSE_BATCH_STRATEGIES,
        default="block",
        help="How to handle app.input_invoice_usage_oa_reverse_batches invoice_id soft references.",
    )
    parser.add_argument(
        "--verify-final",
        action="store_true",
        help="Run read-only final invoice pool invariant checks after cleanup/reimport.",
    )
    parser.add_argument(
        "--verify-input-files",
        action="store_true",
        help="Run read-only official Excel input checks before cleanup/reimport.",
    )
    parser.add_argument(
        "--input-invoice-xlsx",
        type=Path,
        default=None,
        help="Official input invoice Excel file used to build final expected identities.",
    )
    parser.add_argument(
        "--output-invoice-xlsx",
        type=Path,
        default=None,
        help="Official output invoice Excel file used to build final expected identities.",
    )
    parser.add_argument(
        "--expected-input-rows",
        type=int,
        default=371,
        help="Expected row count for --input-invoice-xlsx when --verify-input-files is used.",
    )
    parser.add_argument(
        "--expected-output-rows",
        type=int,
        default=20,
        help="Expected row count for --output-invoice-xlsx when --verify-input-files is used.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON only. Human output is JSON today; kept for CLI consistency.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    connection: Any | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    try:
        args = build_parser().parse_args(argv)
        if args.verify_input_files:
            result = verify_input_invoice_files(
                input_invoice_xlsx=args.input_invoice_xlsx,
                output_invoice_xlsx=args.output_invoice_xlsx,
                expected_input_rows=args.expected_input_rows,
                expected_output_rows=args.expected_output_rows,
            )
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
            return 0 if result.get("gate_recommendation") == "PASS_INPUT_FILES" else 1

        backup_dir = resolve_backup_dir(args.backup_dir)
        dry_run_dir = resolve_dry_run_dir(backup_dir, args.dry_run_dir)
        if connection is None and _database_configured():
            connection = build_connection_from_env()
        plan = build_cleanup_preflight_plan(
            backup_dir,
            dry_run_dir=dry_run_dir,
            connection=connection,
            oa_reverse_batch_strategy=args.oa_reverse_batch_strategy,
        )
        if args.verify_final:
            expected_source = build_expected_invoice_source(
                dry_run_dir=dry_run_dir,
                input_invoice_xlsx=args.input_invoice_xlsx,
                output_invoice_xlsx=args.output_invoice_xlsx,
            )
            result = verify_final_invoice_pool(plan, connection=connection, expected_source=expected_source)
        elif args.execute:
            result = execute_cleanup(
                plan,
                connection=connection,
                confirm_token=str(args.confirm_token or ""),
                execution_sql_file=args.execution_sql_file,
                execution_sql_sha256=str(args.execution_sql_sha256 or ""),
            )
        else:
            result = plan
    except Exception as exc:  # noqa: BLE001 - CLI boundary must redact operational errors.
        print(f"ERROR: {redact_secret_text(str(exc))}", file=stderr)
        return 1

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    recommendation = str(result.get("gate_recommendation") or "")
    if recommendation.startswith(("PASS", "DRY_RUN_PASS")):
        return 0
    if recommendation.startswith("BLOCKED"):
        return 1
    return 0 if result.get("status") in {"ok", "dry_run"} else 1


def resolve_backup_dir(raw_backup_dir: Path | None) -> Path:
    if raw_backup_dir is not None:
        return raw_backup_dir
    if not DEFAULT_AUDIT_ROOT.exists():
        raise FileNotFoundError(f"invoice pool audit root not found: {DEFAULT_AUDIT_ROOT}")
    candidates = sorted(path for path in DEFAULT_AUDIT_ROOT.iterdir() if path.is_dir())
    if not candidates:
        raise FileNotFoundError(f"no invoice pool audit backups found under {DEFAULT_AUDIT_ROOT}")
    return candidates[-1]


def resolve_dry_run_dir(backup_dir: Path, raw_dry_run_dir: Path | None) -> Path:
    if raw_dry_run_dir is not None:
        return raw_dry_run_dir
    colocated = backup_dir / "cleanup_dry_run"
    if colocated.exists():
        return colocated
    if DEFAULT_AUDIT_ROOT.exists():
        candidates = sorted(
            path / "cleanup_dry_run"
            for path in DEFAULT_AUDIT_ROOT.iterdir()
            if path.is_dir() and (path / "cleanup_dry_run").is_dir()
        )
        if candidates:
            return candidates[-1]
    return colocated


def build_cleanup_preflight_plan(
    backup_dir: Path,
    *,
    dry_run_dir: Path | None = None,
    connection: Any | None = None,
    oa_reverse_batch_strategy: str = "block",
) -> dict[str, Any]:
    backup_dir = backup_dir.resolve()
    dry_run_dir = (dry_run_dir or (backup_dir / "cleanup_dry_run")).resolve()
    backup_files = backup_artifact_checks(backup_dir)
    dry_run_files = file_checks(dry_run_dir, DRY_RUN_FILES)
    summary = _read_json(dry_run_dir / "summary.json")
    soft_references = _read_csv(dry_run_dir / "soft_reference_inventory.csv")
    blockers, resolved_actions = soft_reference_strategy_status(
        soft_references,
        oa_reverse_batch_strategy=oa_reverse_batch_strategy,
    )
    current_counts = live_counts(connection) if connection is not None else {}
    count_guard = count_guard_status(summary, current_counts)
    gate_recommendation = gate_recommendation_for(
        backup_files=backup_files,
        dry_run_files=dry_run_files,
        blockers=blockers,
        count_guard=count_guard,
    )
    return {
        "status": "dry_run",
        "mode": "dry_run",
        "backup_dir": str(backup_dir),
        "dry_run_dir": str(dry_run_dir),
        "backup_files": backup_files,
        "dry_run_files": dry_run_files,
        "summary": summary,
        "current_counts": current_counts,
        "count_guard": count_guard,
        "soft_reference_strategies": {
            "oa_reverse_batch_strategy": oa_reverse_batch_strategy,
        },
        "soft_reference_blockers": blockers,
        "resolved_soft_reference_actions": resolved_actions,
        "planned_actions": planned_actions(summary),
        "execute_requirements": {
            "environment": {
                EXECUTE_GUARD_ENV: "1",
                BACKUP_CONFIRMED_ENV: "1",
            },
            "confirm_token": CONFIRM_TOKEN,
            "unblocked_soft_reference_strategy_required": bool(blockers),
            "database_connection_required": True,
        },
        "gate_recommendation": gate_recommendation,
}


def execute_cleanup(
    plan: dict[str, Any],
    *,
    connection: Any | None,
    confirm_token: str,
    execution_sql_file: Path | None = None,
    execution_sql_sha256: str = "",
) -> dict[str, Any]:
    errors: list[str] = []
    if connection is None:
        errors.append("database_connection_required")
    if os.environ.get(EXECUTE_GUARD_ENV) != "1":
        errors.append(f"{EXECUTE_GUARD_ENV}=1_required")
    if os.environ.get(BACKUP_CONFIRMED_ENV) != "1":
        errors.append(f"{BACKUP_CONFIRMED_ENV}=1_required")
    if confirm_token != CONFIRM_TOKEN:
        errors.append("confirm_token_mismatch")
    if plan.get("gate_recommendation") != "PASS_READY_TO_EXECUTE":
        errors.append("preflight_not_ready_to_execute")
    if errors:
        return {
            **plan,
            "mode": "execute",
            "status": "blocked",
            "executed": False,
            "execute_errors": errors,
            "gate_recommendation": "BLOCKED_EXECUTE_GUARD",
        }
    sql_metadata, sql_text, sql_errors = validate_execution_sql_artifact(
        execution_sql_file,
        expected_sha256=execution_sql_sha256,
    )
    if sql_errors:
        return {
            **plan,
            "mode": "execute",
            "status": "blocked",
            "executed": False,
            "execute_errors": sql_errors,
            "execution_sql": sql_metadata,
            "gate_recommendation": "BLOCKED_EXECUTE_SQL_GUARD",
        }
    affected_rows = connection.execute(sql_text)
    return {
        **plan,
        "mode": "execute",
        "status": "ok",
        "executed": True,
        "execute_errors": [],
        "execution_sql": sql_metadata,
        "affected_rows": affected_rows,
        "gate_recommendation": "PASS_EXECUTED",
    }


def validate_execution_sql_artifact(
    path: Path | None,
    *,
    expected_sha256: str,
) -> tuple[dict[str, Any], str, list[str]]:
    metadata: dict[str, Any] = {
        "path": str(path) if path is not None else None,
        "expected_sha256": expected_sha256,
    }
    errors: list[str] = []
    expected_sha256 = str(expected_sha256 or "").strip().lower()
    if path is None:
        errors.append("execution_sql_file_required")
    if not expected_sha256:
        errors.append("execution_sql_sha256_required")
    elif len(expected_sha256) != 64 or any(char not in "0123456789abcdef" for char in expected_sha256):
        errors.append("execution_sql_sha256_invalid")
    if errors:
        return metadata, "", errors

    sql_path = path.resolve()
    metadata["path"] = str(sql_path)
    if not sql_path.exists() or not sql_path.is_file():
        return metadata, "", ["execution_sql_file_not_found"]
    sql_text = sql_path.read_text(encoding="utf-8")
    metadata["bytes"] = len(sql_text.encode("utf-8"))
    if not sql_text.strip():
        return metadata, "", ["execution_sql_file_empty"]
    actual_sha256 = hashlib.sha256(sql_text.encode("utf-8")).hexdigest()
    metadata["actual_sha256"] = actual_sha256
    if actual_sha256 != expected_sha256:
        return metadata, "", ["execution_sql_sha256_mismatch"]

    lowered = sql_text.lower()
    artifact_errors: list[str] = []
    if EXECUTABLE_SQL_MARKER.lower() not in lowered:
        artifact_errors.append("execution_sql_marker_required")
    if "review only" in lowered or "do not run as a production cleanup script" in lowered:
        artifact_errors.append("execution_sql_review_only_forbidden")
    if _contains_rollback_statement(sql_text):
        artifact_errors.append("execution_sql_rollback_forbidden")
    if artifact_errors:
        return metadata, "", artifact_errors
    metadata["marker"] = EXECUTABLE_SQL_MARKER
    return metadata, sql_text, []


def _contains_rollback_statement(sql_text: str) -> bool:
    return "rollback;" in " ".join(sql_text.lower().split())


def verify_final_invoice_pool(
    plan: dict[str, Any],
    *,
    connection: Any | None,
    expected_source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    expected_source = expected_source or build_expected_invoice_source(
        dry_run_dir=Path(str(plan.get("dry_run_dir") or "")),
        input_invoice_xlsx=None,
        output_invoice_xlsx=None,
    )
    expected_identity_keys = set(expected_source.get("identity_keys") or set())
    expected_app_invoices = _int(
        expected_source.get("total_rows"),
        _int((plan.get("summary") or {}).get("excel_unique_identity_keys"), 391),
    )
    expected_input_invoices = _int(expected_source.get("input_rows"), 371)
    expected_output_invoices = _int(expected_source.get("output_rows"), 20)
    if connection is None:
        invariants = {
            "status": "not_checked",
            "reason": "database_connection_required",
            "expected_app_invoices": expected_app_invoices,
            "expected_unique_identities": expected_app_invoices,
            "expected_input_invoices": expected_input_invoices,
            "expected_output_invoices": expected_output_invoices,
            "expected_etc_only_canonical_rows": 0,
            "expected_excel_identity_count": len(expected_identity_keys),
            "expected_identity_source": expected_source.get("source"),
        }
        passed = False
    else:
        invariants = final_invoice_pool_invariants(
            connection,
            expected_app_invoices=expected_app_invoices,
            expected_input_invoices=expected_input_invoices,
            expected_output_invoices=expected_output_invoices,
            expected_identity_keys=expected_identity_keys,
        )
        invariants["expected_identity_source"] = expected_source.get("source")
        invariants["expected_identity_files"] = expected_source.get("files", [])
        passed = invariants.get("status") == "pass"
    return {
        **plan,
        "mode": "verify_final",
        "status": "ok" if passed else "blocked",
        "final_invariants": invariants,
        "gate_recommendation": "PASS_FINAL_INVARIANTS" if passed else "BLOCKED_FINAL_INVARIANTS",
    }


def final_invoice_pool_invariants(
    connection: Any,
    *,
    expected_app_invoices: int,
    expected_input_invoices: int,
    expected_output_invoices: int,
    expected_identity_keys: set[str] | None = None,
) -> dict[str, Any]:
    query = """
        with invoice_rows as (
            select
                invoice_type,
                source_links,
                raw_payload,
                case
                    when nullif(trim(coalesce(digital_invoice_no, '')), '') is not null
                        then trim(digital_invoice_no)
                    when length(trim(coalesce(invoice_no, ''))) = 20
                        then trim(invoice_no)
                    when nullif(trim(coalesce(invoice_code, '')), '') is not null
                     and nullif(trim(coalesce(invoice_no, '')), '') is not null
                        then trim(invoice_code) || ':' || trim(invoice_no)
                    when nullif(trim(coalesce(source_unique_key, '')), '') is not null
                        then trim(source_unique_key)
                    else null
                end as identity_key,
                coalesce(
                    raw_payload->'normalized_payload'->>'invoice_source',
                    raw_payload->>'invoice_source',
                    ''
                ) as invoice_source,
                coalesce(
                    raw_payload->'normalized_payload'->>'invoice_kind',
                    raw_payload->>'invoice_kind',
                    ''
                ) as invoice_kind
            from app.invoices
        ),
        duplicate_identity_groups as (
            select identity_key
            from invoice_rows
            where identity_key is not null
            group by identity_key
            having count(*) > 1
        )
        select
            count(*)::bigint as app_invoices,
            count(distinct identity_key)::bigint as unique_identity_count,
            count(*) filter (where identity_key is null)::bigint as missing_identity_rows,
            count(*) filter (where invoice_type in ('input', 'input_invoice'))::bigint as input_invoices,
            count(*) filter (where invoice_type in ('output', 'output_invoice'))::bigint as output_invoices,
            (select count(*)::bigint from duplicate_identity_groups) as duplicate_identity_groups,
            count(*) filter (
                where invoice_source = 'ETC导入'
                  and invoice_kind = 'ETC发票'
                  and not exists (
                      select 1
                      from jsonb_array_elements(coalesce(invoice_rows.source_links, '[]'::jsonb)) as source_link
                      where coalesce(source_link->>'source_type', '') <> 'etc_invoice_import'
                  )
            )::bigint as etc_only_canonical_rows
        from invoice_rows
    """
    rows = list(connection.fetch_all(query) or [])
    row = rows[0] if rows else {}
    actual = {
        "app_invoices": _int(row.get("app_invoices"), 0),
        "unique_identity_count": _int(row.get("unique_identity_count"), 0),
        "missing_identity_rows": _int(row.get("missing_identity_rows"), 0),
        "input_invoices": _int(row.get("input_invoices"), 0),
        "output_invoices": _int(row.get("output_invoices"), 0),
        "duplicate_identity_groups": _int(row.get("duplicate_identity_groups"), 0),
        "etc_only_canonical_rows": _int(row.get("etc_only_canonical_rows"), 0),
    }
    expected = {
        "app_invoices": expected_app_invoices,
        "unique_identity_count": expected_app_invoices,
        "missing_identity_rows": 0,
        "input_invoices": expected_input_invoices,
        "output_invoices": expected_output_invoices,
        "duplicate_identity_groups": 0,
        "etc_only_canonical_rows": 0,
    }
    failures = [
        {
            "name": name,
            "expected": expected_value,
            "actual": actual[name],
        }
        for name, expected_value in expected.items()
        if actual[name] != expected_value
    ]
    identity_check = final_invoice_identity_set_check(connection, expected_identity_keys or set())
    for name in ("missing_excel_identity_count", "extra_identity_count"):
        if identity_check["actual"][name] != identity_check["expected"][name]:
            failures.append(
                {
                    "name": name,
                    "expected": identity_check["expected"][name],
                    "actual": identity_check["actual"][name],
                    "examples": identity_check["examples"][name],
                }
            )
    return {
        "status": "pass" if not failures else "blocked",
        "expected": expected,
        "actual": actual,
        "identity_set_check": identity_check,
        "failures": failures,
    }


def final_invoice_identity_set_check(connection: Any, expected_identity_keys: set[str]) -> dict[str, Any]:
    actual_identity_keys = live_invoice_identity_keys(connection)
    missing = sorted(expected_identity_keys - actual_identity_keys)
    extra = sorted(actual_identity_keys - expected_identity_keys)
    return {
        "expected": {
            "excel_identity_count": len(expected_identity_keys),
            "missing_excel_identity_count": 0,
            "extra_identity_count": 0,
        },
        "actual": {
            "excel_identity_count": len(expected_identity_keys),
            "actual_identity_count": len(actual_identity_keys),
            "missing_excel_identity_count": len(missing),
            "extra_identity_count": len(extra),
        },
        "examples": {
            "missing_excel_identity_count": missing[:20],
            "extra_identity_count": extra[:20],
        },
    }


def verify_input_invoice_files(
    *,
    input_invoice_xlsx: Path | None,
    output_invoice_xlsx: Path | None,
    expected_input_rows: int = 371,
    expected_output_rows: int = 20,
) -> dict[str, Any]:
    file_specs = [
        ("input", input_invoice_xlsx, expected_input_rows),
        ("output", output_invoice_xlsx, expected_output_rows),
    ]
    files: list[dict[str, Any]] = []
    all_identity_keys: list[str] = []
    errors: list[dict[str, Any]] = []
    for direction, path, expected_rows in file_specs:
        verification = verify_single_invoice_input_file(
            direction=direction,
            path=path,
            expected_rows=expected_rows,
        )
        files.append(verification)
        all_identity_keys.extend(list(verification.get("identity_keys") or []))
        errors.extend(list(verification.get("errors") or []))
    duplicate_identity_counts = {
        identity_key: count
        for identity_key, count in Counter(all_identity_keys).items()
        if identity_key and count > 1
    }
    if duplicate_identity_counts:
        errors.append(
            {
                "code": "duplicate_identity_keys_across_input_files",
                "duplicate_identity_groups": len(duplicate_identity_counts),
                "examples": sorted(duplicate_identity_counts)[:20],
            }
        )
    total_rows = sum(_int(item.get("parsed_rows"), 0) for item in files)
    unique_identity_count = len(set(all_identity_keys))
    expected_total_rows = expected_input_rows + expected_output_rows
    status = "ok" if not errors else "blocked"
    return {
        "status": status,
        "mode": "verify_input_files",
        "files": files,
        "summary": {
            "expected_input_rows": expected_input_rows,
            "expected_output_rows": expected_output_rows,
            "expected_total_rows": expected_total_rows,
            "parsed_total_rows": total_rows,
            "unique_identity_count": unique_identity_count,
            "duplicate_identity_groups": len(duplicate_identity_counts),
            "missing_identity_rows": sum(_int(item.get("missing_identity_rows"), 0) for item in files),
        },
        "errors": errors,
        "gate_recommendation": "PASS_INPUT_FILES" if not errors else "BLOCKED_INPUT_FILES",
    }


def verify_single_invoice_input_file(
    *,
    direction: str,
    path: Path | None,
    expected_rows: int,
) -> dict[str, Any]:
    if path is None:
        return {
            "direction": direction,
            "path": None,
            "expected_rows": expected_rows,
            "parsed_rows": 0,
            "identity_keys": [],
            "missing_identity_rows": 0,
            "duplicate_identity_groups": 0,
            "month_counts": {},
            "errors": [{"code": f"{direction}_invoice_xlsx_required"}],
        }
    resolved_path = path.resolve()
    if not resolved_path.exists() or not resolved_path.is_file():
        return {
            "direction": direction,
            "path": str(resolved_path),
            "expected_rows": expected_rows,
            "parsed_rows": 0,
            "identity_keys": [],
            "missing_identity_rows": 0,
            "duplicate_identity_groups": 0,
            "month_counts": {},
            "errors": [{"code": "invoice_xlsx_not_found", "path": str(resolved_path)}],
        }
    rows = parse_invoice_rows(read_xlsx_rows(resolved_path.read_bytes()))
    identity_keys = [_invoice_identity_key_from_mapping(row) for row in rows]
    missing_identity_indexes = [
        index + 1
        for index, identity_key in enumerate(identity_keys)
        if not identity_key
    ]
    duplicate_identity_counts = {
        identity_key: count
        for identity_key, count in Counter(identity_keys).items()
        if identity_key and count > 1
    }
    errors: list[dict[str, Any]] = []
    if len(rows) != expected_rows:
        errors.append(
            {
                "code": "row_count_mismatch",
                "expected": expected_rows,
                "actual": len(rows),
            }
        )
    if missing_identity_indexes:
        errors.append(
            {
                "code": "missing_strong_identity_rows",
                "count": len(missing_identity_indexes),
                "examples": missing_identity_indexes[:20],
            }
        )
    if duplicate_identity_counts:
        errors.append(
            {
                "code": "duplicate_identity_keys_in_file",
                "duplicate_identity_groups": len(duplicate_identity_counts),
                "examples": sorted(duplicate_identity_counts)[:20],
            }
        )
    month_counts = Counter(
        str(row.get("invoice_date") or "")[:7]
        for row in rows
        if str(row.get("invoice_date") or "").strip()
    )
    return {
        "direction": direction,
        "path": str(resolved_path),
        "expected_rows": expected_rows,
        "parsed_rows": len(rows),
        "identity_keys": [identity_key for identity_key in identity_keys if identity_key],
        "missing_identity_rows": len(missing_identity_indexes),
        "duplicate_identity_groups": len(duplicate_identity_counts),
        "month_counts": dict(sorted(month_counts.items())),
        "errors": errors,
    }


def build_expected_invoice_source(
    *,
    dry_run_dir: Path,
    input_invoice_xlsx: Path | None,
    output_invoice_xlsx: Path | None,
) -> dict[str, Any]:
    excel_files = [
        ("input", input_invoice_xlsx),
        ("output", output_invoice_xlsx),
    ]
    provided_excel_files = [(direction, path) for direction, path in excel_files if path is not None]
    if provided_excel_files:
        identity_keys: set[str] = set()
        input_rows = 0
        output_rows = 0
        files: list[str] = []
        for direction, path in provided_excel_files:
            rows = parse_invoice_rows(read_xlsx_rows(path.read_bytes()))
            row_identity_keys = _invoice_identity_keys_from_parsed_rows(rows)
            identity_keys.update(row_identity_keys)
            files.append(str(path))
            if direction == "input":
                input_rows += len(rows)
            else:
                output_rows += len(rows)
        return {
            "source": "excel_files",
            "files": files,
            "identity_keys": identity_keys,
            "input_rows": input_rows,
            "output_rows": output_rows,
            "total_rows": input_rows + output_rows,
        }
    identity_keys = _expected_excel_identity_keys(dry_run_dir)
    return {
        "source": "dry_run_candidate_keep_excel_identities",
        "files": [str(dry_run_dir / "candidate_keep_excel_identities.csv")],
        "identity_keys": identity_keys,
        "input_rows": 371,
        "output_rows": 20,
        "total_rows": len(identity_keys) or 391,
    }


def live_invoice_identity_keys(connection: Any) -> set[str]:
    rows = connection.fetch_all(
        """
        with invoice_rows as (
            select
                case
                    when nullif(trim(coalesce(digital_invoice_no, '')), '') is not null
                        then trim(digital_invoice_no)
                    when length(trim(coalesce(invoice_no, ''))) = 20
                        then trim(invoice_no)
                    when nullif(trim(coalesce(invoice_code, '')), '') is not null
                     and nullif(trim(coalesce(invoice_no, '')), '') is not null
                        then trim(invoice_code) || ':' || trim(invoice_no)
                    when nullif(trim(coalesce(source_unique_key, '')), '') is not null
                        then trim(source_unique_key)
                    else null
                end as identity_key
            from app.invoices
        )
        select distinct identity_key
        from invoice_rows
        where identity_key is not null
        """
    )
    return {
        str(row.get("identity_key") or "").strip()
        for row in rows
        if str(row.get("identity_key") or "").strip()
    }


def _invoice_identity_keys_from_parsed_rows(rows: Sequence[dict[str, Any]]) -> set[str]:
    identity_keys: set[str] = set()
    for row in rows:
        identity_key = _invoice_identity_key_from_mapping(row)
        if identity_key:
            identity_keys.add(identity_key)
    return identity_keys


def _invoice_identity_key_from_mapping(row: dict[str, Any]) -> str:
    digital_invoice_no = str(row.get("digital_invoice_no") or "").strip()
    if digital_invoice_no:
        return digital_invoice_no
    invoice_no = str(row.get("invoice_no") or "").strip()
    if len(invoice_no) == 20:
        return invoice_no
    invoice_code = str(row.get("invoice_code") or "").strip()
    if invoice_code and invoice_no:
        return f"{invoice_code}:{invoice_no}"
    return ""


def file_checks(root: Path, relative_files: Sequence[str]) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for relative_file in relative_files:
        path = root / relative_file
        exists = path.exists()
        checks.append(
            {
                "file": relative_file,
                "path": str(path),
                "exists": exists,
                "bytes": path.stat().st_size if exists and path.is_file() else 0,
            }
        )
    return checks


def _expected_excel_identity_keys(dry_run_dir: Path) -> set[str]:
    path = dry_run_dir / "candidate_keep_excel_identities.csv"
    rows = _read_csv(path)
    return {
        str(row.get("identity_key") or "").strip()
        for row in rows
        if str(row.get("identity_key") or "").strip()
    }


def backup_artifact_checks(root: Path) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    for group, alternatives in REQUIRED_BACKUP_FILE_GROUPS:
        alternative_checks = file_checks(root, alternatives)
        group_satisfied = any(_file_check_satisfied(check) for check in alternative_checks)
        for check in alternative_checks:
            checks.append(
                {
                    **check,
                    "group": group,
                    "required": True,
                    "accepted": group_satisfied and _file_check_satisfied(check),
                    "alternatives": list(alternatives),
                }
            )
    return checks


def soft_reference_blockers(rows: Sequence[dict[str, str]]) -> list[dict[str, Any]]:
    blockers, _resolved_actions = soft_reference_strategy_status(
        rows,
        oa_reverse_batch_strategy="block",
    )
    return blockers


def soft_reference_strategy_status(
    rows: Sequence[dict[str, str]],
    *,
    oa_reverse_batch_strategy: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blockers: list[dict[str, Any]] = []
    resolved_actions: list[dict[str, Any]] = []
    for row in rows:
        key = (
            str(row.get("table_schema") or "").strip(),
            str(row.get("table_name") or "").strip(),
            str(row.get("column_name") or "").strip(),
        )
        if key not in BLOCKING_SOFT_REFERENCES:
            continue
        count = _int(row.get("matching_rows"), 0)
        if count <= 0:
            continue
        blocker = {
            "table_schema": key[0],
            "table_name": key[1],
            "column_name": key[2],
            "matching_rows": count,
            "required_decision": _soft_reference_required_decision(key),
        }
        resolved = _resolved_soft_reference_action(
            key,
            count,
            oa_reverse_batch_strategy=oa_reverse_batch_strategy,
        )
        if resolved is None:
            blockers.append(blocker)
        else:
            resolved_actions.append(resolved)
    return blockers, resolved_actions


def count_guard_status(summary: dict[str, Any], current_counts: dict[str, int]) -> dict[str, Any]:
    expected_app_invoices = _int(summary.get("current_app_invoices_rows"), 0)
    expected_app_etc_invoices = _int(summary.get("app_etc_invoices_rows"), 0)
    actual_app_invoices = current_counts.get("app.invoices")
    actual_app_etc_invoices = current_counts.get("app.etc_invoices")
    if actual_app_invoices is None:
        return {
            "status": "not_checked",
            "expected_app_invoices": expected_app_invoices,
            "actual_app_invoices": None,
            "expected_app_etc_invoices": expected_app_etc_invoices,
            "actual_app_etc_invoices": None,
            "reason": "database_not_connected",
        }
    if actual_app_invoices != expected_app_invoices:
        return {
            "status": "blocked",
            "expected_app_invoices": expected_app_invoices,
            "actual_app_invoices": actual_app_invoices,
            "expected_app_etc_invoices": expected_app_etc_invoices,
            "actual_app_etc_invoices": actual_app_etc_invoices,
            "reason": "app_invoices_count_changed_since_dry_run",
        }
    if expected_app_etc_invoices and actual_app_etc_invoices != expected_app_etc_invoices:
        return {
            "status": "blocked",
            "expected_app_invoices": expected_app_invoices,
            "actual_app_invoices": actual_app_invoices,
            "expected_app_etc_invoices": expected_app_etc_invoices,
            "actual_app_etc_invoices": actual_app_etc_invoices,
            "reason": "app_etc_invoices_count_changed_since_dry_run",
        }
    return {
        "status": "pass",
        "expected_app_invoices": expected_app_invoices,
        "actual_app_invoices": actual_app_invoices,
        "expected_app_etc_invoices": expected_app_etc_invoices,
        "actual_app_etc_invoices": actual_app_etc_invoices,
    }


def gate_recommendation_for(
    *,
    backup_files: Sequence[dict[str, Any]],
    dry_run_files: Sequence[dict[str, Any]],
    blockers: Sequence[dict[str, Any]],
    count_guard: dict[str, Any],
) -> str:
    if _backup_artifacts_missing(backup_files):
        return "BLOCKED_BACKUP_ARTIFACT_MISSING"
    if any(not check.get("exists") or int(check.get("bytes") or 0) <= 0 for check in dry_run_files):
        return "BLOCKED_DRY_RUN_ARTIFACT_MISSING"
    if count_guard.get("status") == "blocked":
        return "BLOCKED_COUNT_GUARD"
    if blockers:
        return "BLOCKED_SOFT_REFERENCE_STRATEGY_REQUIRED"
    if count_guard.get("status") == "not_checked":
        return "DRY_RUN_PASS_DATABASE_NOT_CHECKED"
    return "PASS_READY_TO_EXECUTE"


def _backup_artifacts_missing(backup_files: Sequence[dict[str, Any]]) -> bool:
    groups = {str(group) for group, _alternatives in REQUIRED_BACKUP_FILE_GROUPS}
    satisfied = {
        str(check.get("group"))
        for check in backup_files
        if str(check.get("group")) in groups and bool(check.get("accepted"))
    }
    return satisfied != groups


def _file_check_satisfied(check: dict[str, Any]) -> bool:
    return bool(check.get("exists")) and int(check.get("bytes") or 0) > 0


def planned_actions(summary: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "action": "reset_canonical_invoice_pool",
            "table": "app.invoices",
            "expected_rows_to_remove": _int(summary.get("recommended_full_reset_delete_app_invoices_rows"), 0),
        },
        {
            "action": "reimport_formal_excel_invoices",
            "expected_unique_identities": _int(summary.get("excel_unique_identity_keys"), 0),
            "expected_input_rows": 371,
            "expected_output_rows": 20,
        },
        {
            "action": "remove_legacy_etc_created_canonical_pollution",
            "scope": "app.invoices",
            "expected_final_rows_after_reimport": _int(summary.get("excel_unique_identity_keys"), 0),
            "preserve_formal_excel_and_oa_canonical_invoices": True,
            "legacy_match_rule": "invoice_source='ETC导入' and invoice_kind='ETC发票' without non-ETC source links",
        },
        {
            "action": "verify_final_invariants",
            "expected_app_invoices": _int(summary.get("excel_unique_identity_keys"), 0),
            "expected_etc_only_canonical_rows": 0,
        },
    ]


def live_counts(connection: Any) -> dict[str, int]:
    query = """
        select 'app.invoices' as table_name, count(*)::bigint as row_count from app.invoices
        union all
        select 'app.etc_invoices', count(*)::bigint from app.etc_invoices
        union all
        select 'app.input_invoice_usage_oa_reverse_batches', count(*)::bigint from app.input_invoice_usage_oa_reverse_batches
    """
    rows = connection.fetch_all(query)
    return {str(row.get("table_name")): _int(row.get("row_count"), 0) for row in rows}


def build_connection_from_env() -> PostgresConnection:
    return PostgresConnection(PostgresSettings.from_env())


def _database_configured() -> bool:
    return bool((os.environ.get("FIN_OPS_POSTGRES_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip())


def _soft_reference_required_decision(key: tuple[str, str, str]) -> str:
    if key == ("app", "input_invoice_usage_oa_reverse_batches", "invoice_ids"):
        return "archive_or_rebuild_oa_reverse_batches_before_canonical_pool_reset"
    return "explicit_cleanup_strategy_required"


def _resolved_soft_reference_action(
    key: tuple[str, str, str],
    count: int,
    *,
    oa_reverse_batch_strategy: str,
) -> dict[str, Any] | None:
    if key == ("app", "input_invoice_usage_oa_reverse_batches", "invoice_ids"):
        if oa_reverse_batch_strategy != "archive_legacy_polluted_history":
            return None
        return {
            "strategy": oa_reverse_batch_strategy,
            "table_schema": key[0],
            "table_name": key[1],
            "column_name": key[2],
            "matching_rows": count,
            "action": "archive_legacy_polluted_oa_reverse_batches_before_canonical_pool_reset",
            "reason": "OA reverse batches store historical selected invoice ids and display rows; polluted legacy ids must be preserved in backup/audit history rather than carried into the rebuilt canonical invoice pool.",
        }
    return None


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def _read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from collections.abc import Sequence
from contextlib import contextmanager
from typing import Any, TextIO

from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.bank_import_dedup_repair_service import (
    BankImportDedupRelationEvidenceError,
    build_bank_import_dedup_repair_plan,
    public_bank_import_dedup_repair_report,
    verify_bank_import_repair_source_files,
    withdraw_bank_import_dedup_workbench_relations,
)
from fin_ops_platform.services.bank_import_audit_contract_repair_service import (
    build_bank_import_audit_contract_repair_plan,
    public_bank_import_audit_contract_repair_report,
)
from fin_ops_platform.services.import_audit_repair_service import (
    build_failed_import_job_recovery_plan,
    build_import_audit_repair_plan,
    execute_failed_import_job_recovery,
    public_failed_import_recovery_report,
    public_repair_report,
)
from fin_ops_platform.services.invoice_expense_item_link_repair_service import (
    build_invoice_expense_item_link_repair_plan,
    build_oa_attachment_invoice_link_audit_plan,
    public_invoice_expense_item_link_repair_report,
    public_oa_attachment_invoice_link_audit_report,
)
from fin_ops_platform.services.invoice_header_fact_repair_service import (
    INVOICE_HEADER_REPAIR_FACTS,
    build_invoice_header_fact_repair_plan,
    public_invoice_header_fact_repair_report,
)
from fin_ops_platform.services.object_storage import (
    ObjectStorageSettings,
    S3ObjectStorageRepository,
)
from fin_ops_platform.services.postgres_connection import (
    PostgresConnection,
    PostgresSettings,
    PostgresTransaction,
)
from fin_ops_platform.services.postgres_repositories.bank_import_dedup_repair import (
    apply_bank_import_dedup_repair,
    load_bank_import_dedup_repair_snapshot,
)
from fin_ops_platform.services.postgres_repositories.bank_import_audit_contract_repair import (
    apply_bank_import_audit_contract_repair,
    load_bank_import_audit_contract_repair_snapshot,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_import_audit_repair,
    discover_failed_import_job_recovery_snapshot,
    load_failed_import_job_recovery_snapshot,
    load_import_audit_repair_snapshot,
    load_invoice_expense_item_link_repair_snapshot,
    load_invoice_header_fact_repair_snapshot,
    load_oa_attachment_invoice_link_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import (
    PostgresOperationsAuditRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir


_PRODUCTION_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT = (
    "/opt/fin-ops/runtime-smoke/import-audit-repair-artifacts"
)


def _build_bank_repair_state_store(connection: PostgresConnection) -> PostgresStateStore:
    object_storage_settings = ObjectStorageSettings.from_env()
    state_store_kwargs: dict[str, object] = {
        "data_dir": default_data_dir(),
        "connection": connection,
    }
    if object_storage_settings.enabled:
        state_store_kwargs["object_storage_repository"] = S3ObjectStorageRepository(
            object_storage_settings
        )
    return PostgresStateStore(**state_store_kwargs)


class _ActiveTransactionConnection(PostgresTransaction):
    """Expose one active transaction through the connection-shaped repository boundary."""

    def __init__(self, transaction: Any) -> None:
        self._transaction = transaction

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transaction, name)

    def fetch_one(self, sql: str, params: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        return self._transaction.fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        return self._transaction.fetch_all(sql, params)

    def execute(self, sql: str, params: tuple[Any, ...] = ()) -> int:
        return self._transaction.execute(sql, params)

    def execute_many(self, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
        return self._transaction.execute_many(sql, params_seq)

    def execute_many_values(
        self,
        sql: str,
        params_seq: list[tuple[Any, ...]],
        *,
        chunk_size: int = 1000,
    ) -> int:
        return self._transaction.execute_many_values(
            sql,
            params_seq,
            chunk_size=chunk_size,
        )

    def copy_rows(self, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
        return self._transaction.copy_rows(sql, params_seq)

    @contextmanager
    def transaction(self):
        yield self._transaction


def _rollback_manifest_fingerprint(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _ensure_private_artifact_root(path: str, *, expected_uid: int) -> None:
    parent = os.path.dirname(path)
    parent_stat = os.lstat(parent)
    if (
        not stat.S_ISDIR(parent_stat.st_mode)
        or stat.S_ISLNK(parent_stat.st_mode)
        or parent_stat.st_uid != expected_uid
        or stat.S_IMODE(parent_stat.st_mode) & 0o022
    ):
        raise RuntimeError(
            "Rollback manifest artifact parent must be an owned non-writable directory."
        )
    try:
        os.mkdir(path, mode=0o700)
    except FileExistsError:
        pass


def _private_artifact_root() -> str:
    configured_root = str(
        os.environ.get("FIN_OPS_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT") or ""
    ).strip()
    if configured_root:
        return os.path.abspath(configured_root)
    if os.geteuid() != 0:
        raise RuntimeError(
            "Rollback manifest artifact root must be configured before reading or writing an artifact."
        )
    production_root = _PRODUCTION_IMPORT_AUDIT_REPAIR_ARTIFACT_ROOT
    _ensure_private_artifact_root(production_root, expected_uid=0)
    return production_root


def _validate_private_rollback_manifest_path(path: str) -> None:
    normalized_root = _private_artifact_root()
    normalized_path = os.path.abspath(path)
    artifact_name = os.path.basename(normalized_path)
    if (
        not os.path.isabs(path)
        or path != normalized_path
        or os.path.dirname(normalized_path) != normalized_root
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}\.json", artifact_name)
    ):
        raise RuntimeError(
            "Rollback manifest path must be one safe JSON file inside the configured artifact root."
        )
    root_stat = os.lstat(normalized_root)
    if (
        not stat.S_ISDIR(root_stat.st_mode)
        or stat.S_ISLNK(root_stat.st_mode)
        or stat.S_IMODE(root_stat.st_mode) != 0o700
        or root_stat.st_uid != os.geteuid()
    ):
        raise RuntimeError(
            "Rollback manifest artifact root must be an owned 0700 directory."
        )


def _write_private_rollback_manifest(path: str, plan: dict[str, Any]) -> None:
    _validate_private_rollback_manifest_path(path)
    manifest = dict(plan["rollback_manifest"])
    expected_fingerprint = str(plan["rollback_manifest_fingerprint"])
    if _rollback_manifest_fingerprint(manifest) != expected_fingerprint:
        raise RuntimeError("Rollback manifest changed before artifact creation.")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0)
    flags |= getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            file_descriptor = -1
            json.dump(
                manifest,
                handle,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
    except BaseException:
        if file_descriptor >= 0:
            os.close(file_descriptor)
        try:
            os.unlink(path)
        except FileNotFoundError:
            pass
        raise


def _verify_private_rollback_manifest(path: str, plan: dict[str, Any]) -> None:
    _validate_private_rollback_manifest_path(path)
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    file_descriptor = os.open(path, flags)
    with os.fdopen(file_descriptor, "r", encoding="utf-8") as handle:
        artifact_stat = os.fstat(handle.fileno())
        if not stat.S_ISREG(artifact_stat.st_mode):
            raise RuntimeError("Rollback manifest artifact must be a regular file.")
        if stat.S_IMODE(artifact_stat.st_mode) != 0o600:
            raise RuntimeError("Rollback manifest artifact must have mode 0600.")
        if artifact_stat.st_uid != os.geteuid() or artifact_stat.st_nlink != 1:
            raise RuntimeError(
                "Rollback manifest artifact must be owned by the current user with one hard link."
            )
        manifest = json.load(handle)
    if not isinstance(manifest, dict):
        raise RuntimeError("Rollback manifest artifact must contain one JSON object.")
    if _rollback_manifest_fingerprint(manifest) != plan["rollback_manifest_fingerprint"]:
        raise RuntimeError("Rollback manifest artifact does not match the current repair plan.")
    if manifest.get("source_fingerprint") != plan["source_fingerprint"]:
        raise RuntimeError("Rollback manifest artifact has the wrong source fingerprint.")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair strict import Audit facts from durable App evidence.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--batch-id")
    parser.add_argument("--file-id")
    parser.add_argument("--retire-etc-session-id", action="append", default=[])
    parser.add_argument("--normalize-reverted-batch-id", action="append", default=[])
    parser.add_argument("--recover-import-job-id")
    parser.add_argument("--recover-event-id")
    parser.add_argument("--recover-background-job-id")
    parser.add_argument("--recover-session-id")
    parser.add_argument("--recover-file-id", action="append", default=[])
    parser.add_argument("--discover-recover-import-job-id")
    parser.add_argument(
        "--repair-bank-source",
        action="append",
        default=[],
        help="Confirmed recovery source in session_id=file_id[,file_id] form.",
    )
    parser.add_argument("--expected-bank-target-count", type=int)
    parser.add_argument("--expected-bank-protected-count", type=int)
    parser.add_argument("--expected-bank-duplicate-delete-count", type=int)
    parser.add_argument("--expected-bank-replay-create-count", type=int)
    parser.add_argument("--expected-bank-replay-repaired-duplicate-count", type=int)
    parser.add_argument(
        "--expected-bank-replay-released-reference-count",
        type=int,
    )
    parser.add_argument("--cleanup-related-bank-duplicates", action="store_true")
    parser.add_argument("--expected-bank-category-cleanup-count", type=int)
    parser.add_argument("--expected-bank-workbench-withdraw-count", type=int)
    parser.add_argument("--expected-bank-workbench-transaction-id")
    parser.add_argument("--repair-bank-audit-contract", action="store_true")
    parser.add_argument("--repair-invoice-header-source-sha256")
    parser.add_argument("--expected-invoice-header-repair-count", type=int)
    parser.add_argument("--repair-invoice-expense-link-id", action="append", default=[])
    parser.add_argument("--repair-invoice-expense-link-case-id")
    parser.add_argument("--repair-invoice-expense-link-oa-row-id")
    parser.add_argument("--repair-invoice-expense-link-item-id")
    parser.add_argument("--expected-invoice-expense-link-total")
    parser.add_argument("--repair-all-oa-attachment-invoice-links", action="store_true")
    parser.add_argument("--rollback-manifest-path")
    parser.add_argument("--reason")
    parser.add_argument("--expected-bank-audit-file-object-link-count", type=int)
    parser.add_argument("--expected-bank-audit-payload-update-count", type=int)
    parser.add_argument("--expected-bank-audit-row-relink-count", type=int)
    parser.add_argument("--expected-bank-audit-row-unlink-count", type=int)
    parser.add_argument("--operator-id")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint from a dry run")
    if bool(args.batch_id) != bool(args.file_id):
        raise SystemExit("--batch-id and --file-id must be provided together")
    if args.retire_etc_session_id and args.batch_id:
        raise SystemExit("ETC session retirement cannot be combined with batch/file lifecycle repair")
    if args.normalize_reverted_batch_id and (args.batch_id or args.retire_etc_session_id):
        raise SystemExit("Reverted batch normalization cannot be combined with another repair mode")
    recovery_values = (
        args.recover_import_job_id,
        args.recover_event_id,
        args.recover_background_job_id,
        args.recover_session_id,
        args.recover_file_id,
    )
    recovery_requested = any(recovery_values)
    discovery_requested = bool(args.discover_recover_import_job_id)
    bank_repair_requested = bool(args.repair_bank_source)
    bank_audit_repair_requested = bool(args.repair_bank_audit_contract)
    invoice_header_repair_requested = bool(args.repair_invoice_header_source_sha256)
    invoice_expense_link_repair_requested = bool(args.repair_invoice_expense_link_id)
    oa_attachment_invoice_link_repair_requested = bool(
        args.repair_all_oa_attachment_invoice_links
    )
    rollback_repair_requested = (
        invoice_expense_link_repair_requested
        or oa_attachment_invoice_link_repair_requested
    )
    if rollback_repair_requested and not args.rollback_manifest_path:
        raise SystemExit(
            "Invoice expense-item link repair requires --rollback-manifest-path."
        )
    if args.rollback_manifest_path and not rollback_repair_requested:
        raise SystemExit(
            "--rollback-manifest-path requires an invoice expense-item link repair mode."
        )
    specialized_repair_count = sum(
        bool(value)
        for value in (
            recovery_requested,
            discovery_requested,
            bank_repair_requested,
            bank_audit_repair_requested,
            invoice_header_repair_requested,
            invoice_expense_link_repair_requested,
            oa_attachment_invoice_link_repair_requested,
        )
    )
    if specialized_repair_count > 1:
        raise SystemExit("Specialized import repair modes cannot be combined.")
    if discovery_requested and args.execute:
        raise SystemExit("Failed import recovery discovery is read-only and requires --dry-run")
    if recovery_requested and not all(recovery_values):
        raise SystemExit("Failed import recovery requires job, event, background job, session, and file ids")
    if (
        recovery_requested
        or discovery_requested
        or bank_repair_requested
        or bank_audit_repair_requested
        or invoice_header_repair_requested
        or invoice_expense_link_repair_requested
        or oa_attachment_invoice_link_repair_requested
    ) and (
        args.batch_id or args.retire_etc_session_id or args.normalize_reverted_batch_id
    ):
        raise SystemExit("Specialized import repair cannot be combined with another repair mode")
    if recovery_requested and discovery_requested:
        raise SystemExit("Failed import recovery discovery cannot be combined with an explicit target")
    if bank_repair_requested and (recovery_requested or discovery_requested):
        raise SystemExit("Bank dedup repair cannot be combined with failed import recovery")
    if bank_audit_repair_requested and (
        recovery_requested or discovery_requested or bank_repair_requested or invoice_header_repair_requested
    ):
        raise SystemExit(
            "Bank import Audit contract repair cannot be combined with another repair mode"
        )
    if invoice_header_repair_requested and (
        recovery_requested or discovery_requested or bank_repair_requested
    ):
        raise SystemExit("Invoice header fact repair cannot be combined with another repair mode")
    if invoice_header_repair_requested and (
        args.expected_invoice_header_repair_count is None or not args.operator_id
    ):
        raise SystemExit(
            "Invoice header fact repair requires exact target count and --operator-id"
        )
    if not invoice_header_repair_requested and args.expected_invoice_header_repair_count is not None:
        raise SystemExit(
            "Invoice header fact repair count requires --repair-invoice-header-source-sha256"
        )
    invoice_expense_link_values = (
        args.repair_invoice_expense_link_case_id,
        args.repair_invoice_expense_link_oa_row_id,
        args.repair_invoice_expense_link_item_id,
        args.expected_invoice_expense_link_total,
        args.operator_id,
        args.reason,
    )
    if invoice_expense_link_repair_requested and not all(invoice_expense_link_values):
        raise SystemExit(
            "Invoice expense-item link repair requires case, OA row, expense item, "
            "expected total, operator, and reason."
        )
    if oa_attachment_invoice_link_repair_requested and any(
        value is not None
        for value in (
            args.repair_invoice_expense_link_case_id,
            args.repair_invoice_expense_link_oa_row_id,
            args.repair_invoice_expense_link_item_id,
            args.expected_invoice_expense_link_total,
        )
    ):
        raise SystemExit(
            "Full OA attachment invoice repair derives targets from canonical evidence; "
            "targeted link values are not allowed."
        )
    if (
        oa_attachment_invoice_link_repair_requested
        and args.execute
        and (not args.operator_id or not args.reason)
    ):
        raise SystemExit(
            "Full OA attachment invoice repair execute requires operator and reason."
        )
    if not (
        invoice_expense_link_repair_requested
        or oa_attachment_invoice_link_repair_requested
    ) and any(
        value is not None
        for value in (
            args.repair_invoice_expense_link_case_id,
            args.repair_invoice_expense_link_oa_row_id,
            args.repair_invoice_expense_link_item_id,
            args.expected_invoice_expense_link_total,
            args.reason,
        )
    ):
        raise SystemExit(
            "Invoice expense-item link repair values require --repair-invoice-expense-link-id."
        )
    bank_audit_expectations = (
        args.expected_bank_audit_file_object_link_count,
        args.expected_bank_audit_payload_update_count,
        args.expected_bank_audit_row_relink_count,
        args.expected_bank_audit_row_unlink_count,
    )
    if bank_audit_repair_requested and (
        any(value is None for value in bank_audit_expectations) or not args.operator_id
    ):
        raise SystemExit(
            "Bank import Audit contract repair requires exact file-object-link, "
            "payload-update, row-relink, and row-unlink counts and --operator-id"
        )
    if not bank_audit_repair_requested and any(
        value is not None for value in bank_audit_expectations
    ):
        raise SystemExit(
            "Bank import Audit contract expectations require "
            "--repair-bank-audit-contract"
        )
    if bank_repair_requested and (
        args.expected_bank_target_count is None
        or args.expected_bank_protected_count is None
        or args.expected_bank_duplicate_delete_count is None
        or args.expected_bank_replay_create_count is None
        or args.expected_bank_replay_repaired_duplicate_count is None
        or args.expected_bank_replay_released_reference_count is None
        or not args.operator_id
    ):
        raise SystemExit(
            "Bank dedup repair requires exact target/protected/duplicate-delete/replay/"
            "repaired-duplicate/released-reference counts "
            "and --operator-id"
        )
    related_cleanup_values = (
        args.expected_bank_category_cleanup_count,
        args.expected_bank_workbench_withdraw_count,
        args.expected_bank_workbench_transaction_id,
    )
    if args.cleanup_related_bank_duplicates and (
        args.expected_bank_category_cleanup_count is None
        or args.expected_bank_workbench_withdraw_count is None
        or not args.expected_bank_workbench_transaction_id
    ):
        raise SystemExit(
            "Related bank duplicate cleanup requires exact category/workbench counts and "
            "the Workbench duplicate transaction id"
        )
    if not args.cleanup_related_bank_duplicates and any(
        value is not None for value in related_cleanup_values
    ):
        raise SystemExit(
            "Related bank duplicate cleanup expectations require "
            "--cleanup-related-bank-duplicates"
        )
    connection = PostgresConnection(PostgresSettings.from_env())
    if oa_attachment_invoice_link_repair_requested:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_oa_attachment_invoice_link_audit_plan(
                load_oa_attachment_invoice_link_audit_snapshot(transaction)
            )
        if args.dry_run:
            _write_private_rollback_manifest(args.rollback_manifest_path, plan)
            report = public_oa_attachment_invoice_link_audit_report(
                plan,
                mode="dry_run",
                written=False,
            )
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError(
                    "OA attachment invoice ownership changed after dry-run; rerun dry-run."
                )
            _verify_private_rollback_manifest(args.rollback_manifest_path, plan)
            with connection.transaction() as transaction:
                transaction.execute("set transaction isolation level serializable")
                transaction.fetch_one(
                    "select pg_advisory_xact_lock("
                    "hashtext('fin_ops_oa_attachment_invoice_link_repair'))"
                )
                locked_plan = build_oa_attachment_invoice_link_audit_plan(
                    load_oa_attachment_invoice_link_audit_snapshot(transaction)
                )
                if locked_plan["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError(
                        "OA attachment invoice ownership changed while acquiring the write lock."
                    )
                _verify_private_rollback_manifest(
                    args.rollback_manifest_path,
                    locked_plan,
                )
                completion = PostgresCoreRepository(
                    transaction
                ).repair_invoice_expense_item_links(
                    transaction,
                    list(locked_plan["updates"]),
                    operator_id=args.operator_id,
                    reason=args.reason,
                )
                AuditTrailService(
                    PostgresOperationsAuditRepository(transaction)
                ).record_action(
                    actor_id=args.operator_id,
                    action="oa_attachment_invoice_expense_item_link_repair",
                    entity_type="invoice_expense_item_link_audit",
                    entity_id=locked_plan["source_fingerprint"],
                    metadata={
                        "event_type": "operation.completed",
                        "page_key": "reconciliation_workbench",
                        "operation_location": "import_audit_repair_ops",
                        "reason": args.reason,
                        "outcome": "success",
                        "source_fingerprint": locked_plan["source_fingerprint"],
                        "audited_invoice_count": locked_plan["audited_invoice_count"],
                        "attachment_edge_count": locked_plan["attachment_edge_count"],
                        "classification_counts": locked_plan["classification_counts"],
                        **completion,
                    },
                )
            report = public_oa_attachment_invoice_link_audit_report(
                locked_plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            file=stdout,
        )
        return 0
    if invoice_expense_link_repair_requested:
        plan_kwargs = {
            "invoice_ids": args.repair_invoice_expense_link_id,
            "case_id": args.repair_invoice_expense_link_case_id,
            "oa_row_id": args.repair_invoice_expense_link_oa_row_id,
            "expense_item_id": args.repair_invoice_expense_link_item_id,
            "expected_total": args.expected_invoice_expense_link_total,
        }
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_invoice_expense_item_link_repair_plan(
                load_invoice_expense_item_link_repair_snapshot(
                    transaction,
                    invoice_ids=args.repair_invoice_expense_link_id,
                ),
                **plan_kwargs,
            )
        if args.dry_run:
            _write_private_rollback_manifest(args.rollback_manifest_path, plan)
            report = public_invoice_expense_item_link_repair_report(
                plan,
                mode="dry_run",
                written=False,
            )
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError(
                    "Invoice expense-item links changed after dry-run; rerun dry-run."
                )
            _verify_private_rollback_manifest(args.rollback_manifest_path, plan)
            with connection.transaction() as transaction:
                transaction.execute("set transaction isolation level serializable")
                transaction.fetch_one(
                    "select pg_advisory_xact_lock("
                    "hashtext('fin_ops_invoice_expense_item_link_repair'))"
                )
                locked_plan = build_invoice_expense_item_link_repair_plan(
                    load_invoice_expense_item_link_repair_snapshot(
                        transaction,
                        invoice_ids=args.repair_invoice_expense_link_id,
                    ),
                    **plan_kwargs,
                )
                if locked_plan["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError(
                        "Invoice expense-item links changed while acquiring the write lock."
                    )
                _verify_private_rollback_manifest(
                    args.rollback_manifest_path,
                    locked_plan,
                )
                completion = PostgresCoreRepository(
                    transaction
                ).repair_invoice_expense_item_links(
                    transaction,
                    list(locked_plan["updates"]),
                    operator_id=args.operator_id,
                    reason=args.reason,
                )
                AuditTrailService(
                    PostgresOperationsAuditRepository(transaction)
                ).record_action(
                    actor_id=args.operator_id,
                    action="invoice_expense_item_link_repair",
                    entity_type="workbench_relation",
                    entity_id=locked_plan["case_id"],
                    metadata={
                        "event_type": "operation.completed",
                        "page_key": "reconciliation_workbench",
                        "operation_location": "import_audit_repair_ops",
                        "reason": args.reason,
                        "outcome": "success",
                        **completion,
                    },
                )
            report = public_invoice_expense_item_link_repair_report(
                locked_plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            file=stdout,
        )
        return 0
    if invoice_header_repair_requested:
        invoice_numbers = [fact["digital_invoice_no"] for fact in INVOICE_HEADER_REPAIR_FACTS]
        plan_kwargs = {
            "source_sha256": args.repair_invoice_header_source_sha256,
            "expected_target_count": args.expected_invoice_header_repair_count,
        }
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_invoice_header_fact_repair_plan(
                load_invoice_header_fact_repair_snapshot(
                    transaction,
                    digital_invoice_numbers=invoice_numbers,
                ),
                **plan_kwargs,
            )
        if args.dry_run:
            report = public_invoice_header_fact_repair_report(
                plan,
                mode="dry_run",
                written=False,
            )
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Invoice header facts changed after dry-run; rerun dry-run.")
            with connection.transaction() as transaction:
                transaction.execute("set transaction isolation level serializable")
                transaction.fetch_one(
                    "select pg_advisory_xact_lock(hashtext('fin_ops_invoice_header_fact_repair'))"
                )
                locked_plan = build_invoice_header_fact_repair_plan(
                    load_invoice_header_fact_repair_snapshot(
                        transaction,
                        digital_invoice_numbers=invoice_numbers,
                    ),
                    **plan_kwargs,
                )
                if locked_plan["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError(
                        "Invoice header facts changed while acquiring the write lock."
                    )
                completion = PostgresCoreRepository(transaction).repair_invoice_header_facts(
                    transaction,
                    list(locked_plan["updates"]),
                    operator_id=args.operator_id,
                )
                AuditTrailService(
                    PostgresOperationsAuditRepository(transaction)
                ).record_action(
                    actor_id=args.operator_id,
                    action="invoice_header_fact_repair",
                    entity_type="invoice_header_fact_repair",
                    entity_id=locked_plan["source_fingerprint"],
                    metadata={
                        "event_type": "operation.completed",
                        "page_key": "invoice_import",
                        "operation_location": "import_audit_repair_ops",
                        "reason": "authorized_invoice_header_fact_repair",
                        "outcome": "success",
                        **completion,
                    },
                )
            report = public_invoice_header_fact_repair_report(
                locked_plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(
            json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str),
            file=stdout,
        )
        return 0
    if bank_audit_repair_requested:
        plan_kwargs = {
            "expected_file_object_link_count": (
                args.expected_bank_audit_file_object_link_count
            ),
            "expected_payload_update_count": (
                args.expected_bank_audit_payload_update_count
            ),
            "expected_row_relink_count": args.expected_bank_audit_row_relink_count,
            "expected_row_unlink_count": args.expected_bank_audit_row_unlink_count,
        }
        with connection.transaction() as transaction:
            transaction.execute(
                "set transaction isolation level repeatable read read only"
            )
            plan = build_bank_import_audit_contract_repair_plan(
                load_bank_import_audit_contract_repair_snapshot(transaction),
                **plan_kwargs,
            )
        if args.dry_run:
            report = public_bank_import_audit_contract_repair_report(
                plan,
                mode="dry_run",
                written=False,
            )
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError(
                    "Bank import Audit contract source changed after dry-run; "
                    "rerun dry-run."
                )
            with connection.transaction() as transaction:
                transaction.execute("set transaction isolation level serializable")
                transaction.fetch_one(
                    "select pg_advisory_xact_lock("
                    "hashtext('fin_ops_bank_import_audit_contract_repair'))"
                )
                locked_plan = build_bank_import_audit_contract_repair_plan(
                    load_bank_import_audit_contract_repair_snapshot(transaction),
                    **plan_kwargs,
                )
                if locked_plan["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError(
                        "Bank import Audit contract source changed while acquiring "
                        "the write lock."
                    )
                completion = apply_bank_import_audit_contract_repair(
                    transaction,
                    locked_plan,
                    operator_id=args.operator_id,
                )
                AuditTrailService(
                    PostgresOperationsAuditRepository(transaction)
                ).record_action(
                    actor_id=args.operator_id,
                    action="bank_import_audit_contract_repair",
                    entity_type="bank_import_audit_contract",
                    entity_id=locked_plan["source_fingerprint"],
                    metadata={
                        "event_type": "operation.completed",
                        "page_key": "bank_transaction_import",
                        "operation_location": "import_audit_repair_ops",
                        "reason": "authorized_audit_contract_repair",
                        "outcome": "success",
                        **completion,
                    },
                )
            report = public_bank_import_audit_contract_repair_report(
                locked_plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            ),
            file=stdout,
        )
        return 0
    if bank_repair_requested:
        source_sessions = _parse_bank_repair_sources(args.repair_bank_source)
        snapshot_kwargs = {
            "source_sessions": source_sessions,
            "expected_target_count": args.expected_bank_target_count,
            "expected_protected_count": args.expected_bank_protected_count,
            "expected_duplicate_delete_count": (
                args.expected_bank_duplicate_delete_count
            ),
            "expected_replay_create_count": args.expected_bank_replay_create_count,
            "expected_replay_repaired_duplicate_count": (
                args.expected_bank_replay_repaired_duplicate_count
            ),
            "expected_replay_released_reference_count": (
                args.expected_bank_replay_released_reference_count
            ),
            "cleanup_related_duplicates": args.cleanup_related_bank_duplicates,
            "expected_category_cleanup_count": (
                args.expected_bank_category_cleanup_count or 0
            ),
            "expected_workbench_withdraw_count": (
                args.expected_bank_workbench_withdraw_count or 0
            ),
            "expected_workbench_transaction_id": (
                args.expected_bank_workbench_transaction_id
            ),
        }
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            try:
                plan = build_bank_import_dedup_repair_plan(
                    load_bank_import_dedup_repair_snapshot(transaction, **snapshot_kwargs)
                )
            except BankImportDedupRelationEvidenceError as exc:
                print(
                    json.dumps(
                        {
                            "tool": "import_audit_repair_ops",
                            "operation": "bank_import_identity_v3_recovery",
                            "mode": "dry_run" if args.dry_run else "execute_preflight",
                            "written": False,
                            "eligible": False,
                            "error_code": "relationful_delete_candidates",
                            "message": str(exc),
                            "candidate_count": len(exc.candidates),
                            "candidates": exc.candidates,
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    ),
                    file=stdout,
                )
                return 2
        state_store = _build_bank_repair_state_store(connection)
        verify_bank_import_repair_source_files(plan, read_file=state_store.read_import_file)
        if args.dry_run:
            report = public_bank_import_dedup_repair_report(
                plan,
                mode="dry_run",
                written=False,
            )
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Bank dedup repair source changed after dry-run; rerun dry-run.")
            with connection.transaction() as transaction:
                transaction.execute("set transaction isolation level serializable")
                transaction.fetch_one(
                    "select pg_advisory_xact_lock(hashtext('fin_ops_bank_import_identity_v3_repair'))"
                )
                locked_plan = build_bank_import_dedup_repair_plan(
                    load_bank_import_dedup_repair_snapshot(transaction, **snapshot_kwargs)
                )
                if locked_plan["source_fingerprint"] != args.expected_fingerprint:
                    raise RuntimeError("Bank dedup repair source changed while acquiring the write lock.")
                withdraw_results = withdraw_bank_import_dedup_workbench_relations(
                    transaction,
                    locked_plan,
                    operator_id=args.operator_id,
                )
                apply_result = apply_bank_import_dedup_repair(
                    transaction,
                    locked_plan,
                    operator_id=args.operator_id,
                )
                AuditTrailService(
                    PostgresOperationsAuditRepository(transaction)
                ).record_action(
                    actor_id=args.operator_id,
                    action="bank_import_identity_v3_recovery",
                    entity_type="bank_import_dedup_repair",
                    entity_id=locked_plan["source_fingerprint"],
                    metadata={
                        "event_type": "operation.completed",
                        "page_key": "bank_transaction_import",
                        "operation_location": "import_audit_repair_ops",
                        "reason": "authorized_duplicate_cleanup",
                        "outcome": "success",
                        "summary": "Authorized bank duplicate cleanup completed.",
                        "target_count": locked_plan["target_count"],
                        "duplicate_delete_count": locked_plan["duplicate_delete_count"],
                        "category_ids": [
                            item["category_id"]
                            for item in locked_plan.get("category_cleanup_actions") or []
                        ],
                        "workbench_case_ids": [
                            item["case_id"]
                            for item in locked_plan.get("workbench_withdraw_actions") or []
                        ],
                    },
                )
                report = _complete_bank_repair_transaction(
                    transaction=transaction,
                    locked_plan=locked_plan,
                    apply_result=apply_result,
                    withdraw_results=withdraw_results,
                    operator_id=args.operator_id,
                    expected_replay_create_count=args.expected_bank_replay_create_count,
                    expected_replay_repaired_duplicate_count=(
                        args.expected_bank_replay_repaired_duplicate_count
                    ),
                )
        print(
            json.dumps(
                report,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
                default=str,
            ),
            file=stdout,
        )
        return 0
    if discovery_requested:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            snapshot = discover_failed_import_job_recovery_snapshot(
                transaction,
                import_job_id=args.discover_recover_import_job_id,
            )
            try:
                plan = build_failed_import_job_recovery_plan(snapshot)
            except ValueError as exc:
                print(
                    json.dumps(
                        {
                            "tool": "import_audit_repair_ops",
                            "mode": "discovery",
                            "written": False,
                            "eligible": False,
                            "error": str(exc),
                            "target": (snapshot.get("recovery_requested") or [None])[0],
                            "files": snapshot.get("files") or [],
                        },
                        ensure_ascii=False,
                        indent=2,
                        sort_keys=True,
                        default=str,
                    ),
                    file=stdout,
                )
                return 2
        report = public_failed_import_recovery_report(plan, mode="discovery", written=False)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if recovery_requested:
        snapshot_args = {
            "import_job_id": args.recover_import_job_id,
            "event_id": args.recover_event_id,
            "background_job_id": args.recover_background_job_id,
            "session_id": args.recover_session_id,
            "file_ids": args.recover_file_id,
        }
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_failed_import_job_recovery_plan(
                load_failed_import_job_recovery_snapshot(transaction, **snapshot_args)
            )
        if args.dry_run:
            report = public_failed_import_recovery_report(plan, mode="dry_run", written=False)
        else:
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Import recovery source changed after dry-run; rerun dry-run before execute.")
            completion = execute_failed_import_job_recovery(connection, plan)
            report = public_failed_import_recovery_report(
                plan,
                mode="execute",
                written=True,
                completion=completion,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 0
    if args.dry_run:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=args.batch_id,
                    lifecycle_file_id=args.file_id,
                    etc_deleted_task_session_ids=args.retire_etc_session_id,
                    reverted_batch_ids=args.normalize_reverted_batch_id,
                )
            )
        report = public_repair_report(plan, mode="dry_run", written=False)
    else:
        with connection.transaction() as transaction:
            transaction.execute("set transaction isolation level serializable")
            transaction.fetch_one("select pg_advisory_xact_lock(hashtext('fin_ops_import_audit_repair'))")
            plan = build_import_audit_repair_plan(
                load_import_audit_repair_snapshot(
                    transaction,
                    lifecycle_batch_id=args.batch_id,
                    lifecycle_file_id=args.file_id,
                    etc_deleted_task_session_ids=args.retire_etc_session_id,
                    reverted_batch_ids=args.normalize_reverted_batch_id,
                )
            )
            if plan["source_fingerprint"] != args.expected_fingerprint:
                raise RuntimeError("Import repair source changed after dry-run; rerun dry-run before execute.")
            apply_import_audit_repair(transaction, plan)
        report = public_repair_report(plan, mode="execute", written=True)
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _complete_bank_repair_transaction(
    *,
    transaction: Any,
    locked_plan: dict[str, Any],
    apply_result: dict[str, Any],
    withdraw_results: list[dict[str, Any]],
    operator_id: str,
    expected_replay_create_count: int,
    expected_replay_repaired_duplicate_count: int,
) -> dict[str, Any]:
    """Replay and verify the repair in the same write transaction."""

    from fin_ops_platform.services.runtime_worker_handlers import ImportRuntimeProcessorFactory

    transaction_connection = _ActiveTransactionConnection(transaction)
    runtime = ImportRuntimeProcessorFactory(
        data_dir=default_data_dir(),
        connection=transaction_connection,
    )
    replay_results = [
        runtime.replay_confirmed_file_import_session(
            source_session_id=entry["session_id"],
            selected_file_ids=entry["file_ids"],
            operator_id=operator_id,
            expected_repaired_duplicate_count=entry[
                "expected_repaired_duplicate_count"
            ],
            repaired_duplicate_decision_reason=entry[
                "repaired_duplicate_decision_reason"
            ],
            repaired_duplicate_evidence=entry["repaired_duplicate_evidence"],
            expected_canonical_owner_count=entry["expected_canonical_owner_count"],
            canonical_owner_evidence=entry["canonical_owner_evidence"],
            expected_canonical_reference_count=entry[
                "expected_canonical_reference_count"
            ],
            canonical_reference_evidence=entry["canonical_reference_evidence"],
        )
        for entry in locked_plan["replay_sources"]
    ]
    audit_summaries = [dict(item.get("audit_summary") or {}) for item in replay_results]
    created_count = sum(int(item.get("created_count") or 0) for item in audit_summaries)
    if created_count != expected_replay_create_count:
        raise RuntimeError(
            "Bank recovery replay created an unexpected number of transactions: "
            f"expected {expected_replay_create_count}, got {created_count}."
        )
    repaired_duplicate_count = sum(
        int(item.get("repaired_duplicate_count") or 0) for item in audit_summaries
    )
    if repaired_duplicate_count != expected_replay_repaired_duplicate_count:
        raise RuntimeError(
            "Bank recovery replay resolved an unexpected number of repaired duplicates: "
            f"expected {expected_replay_repaired_duplicate_count}, "
            f"got {repaired_duplicate_count}."
        )
    if any(
        int(item.get("error_count") or 0)
        or int(item.get("suspected_duplicate_count") or 0)
        for item in audit_summaries
    ):
        raise RuntimeError("Bank recovery replay ended with errors or suspected duplicates.")
    canonical_owner_count = sum(
        int(item.get("canonical_owner_count") or 0) for item in audit_summaries
    )
    if canonical_owner_count != locked_plan["replay_canonical_owner_count"]:
        raise RuntimeError("Bank recovery replay canonical owner evidence changed.")
    canonical_reference_count = sum(
        int(item.get("canonical_reference_count") or 0) for item in audit_summaries
    )
    if canonical_reference_count != locked_plan["replay_canonical_reference_count"]:
        raise RuntimeError("Bank recovery replay canonical reference evidence changed.")
    released_canonical_reference_count = sum(
        int(item.get("released_canonical_reference_count") or 0)
        for item in audit_summaries
    )
    if (
        released_canonical_reference_count
        != locked_plan["expected_replay_released_reference_count"]
    ):
        raise RuntimeError(
            "Bank recovery replay released an unexpected number of canonical references: "
            f"expected {locked_plan['expected_replay_released_reference_count']}, "
            f"got {released_canonical_reference_count}."
        )

    idempotence_replay_results = [
        runtime.replay_confirmed_file_import_session(
            source_session_id=entry["session_id"],
            selected_file_ids=entry["file_ids"],
            operator_id=operator_id,
            expected_repaired_duplicate_count=entry[
                "expected_repaired_duplicate_count"
            ],
            repaired_duplicate_decision_reason=entry[
                "repaired_duplicate_decision_reason"
            ],
            repaired_duplicate_evidence=entry["repaired_duplicate_evidence"],
            expected_canonical_owner_count=entry["expected_canonical_owner_count"],
            canonical_owner_evidence=entry["canonical_owner_evidence"],
            expected_canonical_reference_count=entry[
                "expected_canonical_reference_count"
            ],
            canonical_reference_evidence=entry["canonical_reference_evidence"],
        )
        for entry in locked_plan["replay_sources"]
    ]
    idempotence_summaries = [
        dict(item.get("audit_summary") or {}) for item in idempotence_replay_results
    ]
    if any(
        int(item.get("created_count") or 0)
        or int(item.get("updated_count") or 0)
        or int(item.get("error_count") or 0)
        or int(item.get("suspected_duplicate_count") or 0)
        for item in idempotence_summaries
    ):
        raise RuntimeError(
            "Repeated bank recovery replay was not idempotent or ended with audit issues."
        )
    repeated_repaired_duplicate_count = sum(
        int(item.get("repaired_duplicate_count") or 0)
        for item in idempotence_summaries
    )
    if repeated_repaired_duplicate_count != expected_replay_repaired_duplicate_count:
        raise RuntimeError("Repeated bank recovery replay changed repaired duplicate evidence.")
    repeated_canonical_owner_count = sum(
        int(item.get("canonical_owner_count") or 0) for item in idempotence_summaries
    )
    if repeated_canonical_owner_count != locked_plan["replay_canonical_owner_count"]:
        raise RuntimeError("Repeated bank recovery replay changed canonical owner evidence.")
    repeated_canonical_reference_count = sum(
        int(item.get("canonical_reference_count") or 0)
        for item in idempotence_summaries
    )
    if repeated_canonical_reference_count != locked_plan["replay_canonical_reference_count"]:
        raise RuntimeError("Repeated bank recovery replay changed canonical reference evidence.")
    repeated_released_reference_count = sum(
        int(item.get("released_canonical_reference_count") or 0)
        for item in idempotence_summaries
    )
    if (
        repeated_released_reference_count
        != locked_plan["expected_replay_released_reference_count"]
    ):
        raise RuntimeError(
            "Repeated bank recovery replay changed released canonical reference evidence."
        )

    return public_bank_import_dedup_repair_report(
        locked_plan,
        mode="execute",
        written=True,
        replay_results=replay_results,
        idempotence_replay_results=idempotence_replay_results,
        apply_result=apply_result,
        withdraw_results=withdraw_results,
    )


def _parse_bank_repair_sources(values: list[str]) -> list[dict[str, object]]:
    sources: list[dict[str, object]] = []
    for value in values:
        session_id, separator, raw_file_ids = str(value or "").partition("=")
        file_ids = sorted({item.strip() for item in raw_file_ids.split(",") if item.strip()})
        if not separator or not session_id.strip() or not file_ids:
            raise SystemExit("--repair-bank-source must use session_id=file_id[,file_id] form")
        sources.append({"session_id": session_id.strip(), "file_ids": file_ids})
    return sources


if __name__ == "__main__":
    raise SystemExit(main())

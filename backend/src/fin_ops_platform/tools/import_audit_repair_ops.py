from __future__ import annotations

import argparse
import json
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
from fin_ops_platform.services.import_audit_repair_service import (
    build_failed_import_job_recovery_plan,
    build_import_audit_repair_plan,
    execute_failed_import_job_recovery,
    public_failed_import_recovery_report,
    public_repair_report,
)
from fin_ops_platform.services.object_storage import (
    ObjectStorageSettings,
    S3ObjectStorageRepository,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.bank_import_dedup_repair import (
    apply_bank_import_dedup_repair,
    load_bank_import_dedup_repair_snapshot,
)
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    apply_import_audit_repair,
    discover_failed_import_job_recovery_snapshot,
    load_failed_import_job_recovery_snapshot,
    load_import_audit_repair_snapshot,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import (
    PostgresOperationsAuditRepository,
)
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.runtime_paths import default_data_dir


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


class _ActiveTransactionConnection:
    """Expose one active transaction through the connection-shaped repository boundary."""

    def __init__(self, transaction: Any) -> None:
        self._transaction = transaction

    def __getattr__(self, name: str) -> Any:
        return getattr(self._transaction, name)

    @contextmanager
    def transaction(self):
        yield self._transaction


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
    if discovery_requested and args.execute:
        raise SystemExit("Failed import recovery discovery is read-only and requires --dry-run")
    if recovery_requested and not all(recovery_values):
        raise SystemExit("Failed import recovery requires job, event, background job, session, and file ids")
    if (recovery_requested or discovery_requested or bank_repair_requested) and (
        args.batch_id or args.retire_etc_session_id or args.normalize_reverted_batch_id
    ):
        raise SystemExit("Failed import recovery cannot be combined with another repair mode")
    if recovery_requested and discovery_requested:
        raise SystemExit("Failed import recovery discovery cannot be combined with an explicit target")
    if bank_repair_requested and (recovery_requested or discovery_requested):
        raise SystemExit("Bank dedup repair cannot be combined with failed import recovery")
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
    """Replay, verify, and enqueue refreshes in the repair write transaction."""

    from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
    from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
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

    refresh_gateway = ReadModelRefreshGateway(
        queue_repository=RuntimeQueueRepository(transaction_connection)
    )
    refresh_scopes = {
        scope_type: refresh_gateway.enqueue_many(
            scope_type,
            locked_plan["affected_months"],
            reason="bank_import_identity_v3_recovery",
            metadata={
                "force_refresh": True,
                "source_fingerprint": locked_plan["source_fingerprint"],
            },
        )
        for scope_type in ("workbench", "workbench_relation")
    }
    return public_bank_import_dedup_repair_report(
        locked_plan,
        mode="execute",
        written=True,
        replay_results=replay_results,
        idempotence_replay_results=idempotence_replay_results,
        apply_result=apply_result,
        withdraw_results=withdraw_results,
        refresh_scopes=refresh_scopes,
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

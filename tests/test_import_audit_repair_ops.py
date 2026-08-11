from __future__ import annotations

from copy import deepcopy
from contextlib import contextmanager
import io
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from fin_ops_platform.services.import_audit_repair_service import (
    build_failed_import_job_recovery_plan,
    build_import_audit_repair_plan,
    execute_failed_import_job_recovery,
    public_repair_report,
)
from fin_ops_platform.services.bank_import_dedup_repair_service import (
    BankImportDedupRelationEvidenceError,
)
from fin_ops_platform.services.postgres_repositories.import_audit_repair import (
    _FAILED_IMPORT_FILE_SQL,
    apply_import_audit_repair,
    discover_failed_import_job_recovery_snapshot,
    load_failed_import_job_recovery_snapshot,
    load_import_audit_repair_snapshot,
)
from fin_ops_platform.tools import import_audit_repair_ops


def _bank_file(*, batch_id: str = "batch-bank-1", decision: str = "created") -> dict[str, object]:
    normalized = {
        "source_unique_key": "bank-key-1",
        "account_no": "62220001",
        "pay_receive_time": "2026-07-01T10:00:00+08:00",
        "txn_direction": "expense",
        "amount": "100.00",
        "counterparty_name_raw": "供应商甲",
    }
    row_result = {
        "source_unique_key": "bank-key-1",
        "data_fingerprint": "fingerprint-1",
        "decision": decision,
        "decision_reason": "registered decision",
        "identity_kind": "stable",
        "account_no": normalized["account_no"],
        "trade_time": normalized["pay_receive_time"],
        "direction": normalized["txn_direction"],
        "amount": normalized["amount"],
        "counterparty_name": normalized["counterparty_name_raw"],
    }
    return {
        "file_id": "file-bank-1",
        "batch_id": batch_id,
        "raw_payload": {
            "normalized_payload": {
                "row_results": [row_result],
                "normalized_rows": [normalized],
            }
        },
        "row_count": 1,
        "success_count": 1 if decision == "created" else 0,
        "error_count": 0,
        "duplicate_count": 1 if decision == "duplicate_skipped" else 0,
        "suspected_duplicate_count": 0,
        "updated_count": 0,
    }


def _invoice_component(
    *,
    row_id: str,
    row_no: int,
    item: str,
    amount: str,
    tax_amount: str,
    total_with_tax: str,
) -> dict[str, object]:
    normalized = {
        "digital_invoice_no": "26117000001052654674",
        "invoice_no": "1052654674",
        "invoice_date": "2026-07-01",
        "seller_tax_no": "915300000000000001",
        "buyer_tax_no": "915300007194052520",
        "taxable_item_name": item,
        "amount": amount,
        "signed_amount": amount,
        "tax_amount": tax_amount,
        "total_with_tax": total_with_tax,
        "tax_rate": "13%",
    }
    return {
        "batch_id": "batch-invoice-1",
        "row_id": row_id,
        "row_no": row_no,
        "invoice_id": "invoice-1",
        "invoice_source_batch_id": "batch-invoice-1",
        "invoice_month": "2026-07",
        "row_raw_payload": {"normalized_payload": {"normalized_row": normalized}},
        "amount": "39.58",
        "signed_amount": "39.58",
        "tax_amount": "5.15",
        "total_with_tax": "44.73",
        "tax_rate": "13%",
        "invoice_raw_payload": {"normalized_payload": {"amount": "39.58"}},
    }


def _snapshot() -> dict[str, list[dict[str, object]]]:
    return {
        "bank_files": [_bank_file()],
        "bank_transactions": [
            {
                "transaction_id": "transaction-1",
                "source_unique_key": "bank-key-1",
                "data_fingerprint": "fingerprint-1",
                "source_batch_id": "batch-bank-1",
            }
        ],
        "bank_rows": [],
        "invoice_rows": [
            _invoice_component(
                row_id="row-invoice-1",
                row_no=1,
                item="服务",
                amount="39.58",
                tax_amount="5.15",
                total_with_tax="44.73",
            ),
            _invoice_component(
                row_id="row-invoice-2",
                row_no=2,
                item="折扣",
                amount="-1.77",
                tax_amount="-0.23",
                total_with_tax="-2.00",
            ),
        ],
    }


def _lifecycle_snapshot(*, terminal: bool = False) -> dict[str, list[dict[str, object]]]:
    batch_status = "completed" if terminal else "pending"
    file_status = "confirmed" if terminal else "preview_ready"
    return {
        "bank_files": [],
        "bank_transactions": [],
        "bank_rows": [],
        "invoice_rows": [],
        "lifecycle_requested": [{"batch_id": "batch-import-1", "file_id": "file-import-1"}],
        "lifecycle_targets": [
            {
                "batch_id": "batch-import-1",
                "batch_type": "input_invoice",
                "batch_status": batch_status,
                "row_count": 3,
                "success_count": 2,
                "error_count": 0,
                "duplicate_count": 1,
                "suspected_duplicate_count": 0,
                "updated_count": 0,
                "batch_raw_payload": {"normalized_payload": {"status": batch_status}},
                "file_id": "file-import-1",
                "session_id": "session-import-1",
                "file_status": file_status,
                "file_raw_payload": {
                    "normalized_payload": {
                        "status": file_status,
                        "preview_batch_id": "batch-import-1",
                        "batch_id": "batch-import-1" if terminal else None,
                        "session_status": "confirmed" if terminal else "preview_ready",
                    }
                },
            }
        ],
        "lifecycle_jobs": [
            {
                "job_id": "job-import-1",
                "import_session_id": "session-import-1",
                "status": "succeeded",
                "stage": "succeeded",
                "payload": {
                    "session_id": "session-import-1",
                    "selected_file_ids": ["file-import-1"],
                },
                "result_payload": {"selected": 1, "confirmed": 1},
            }
        ],
        "lifecycle_row_evidence": [
            {
                "row_count": 3,
                "created_count": 2,
                "status_updated_count": 0,
                "error_count": 0,
                "duplicate_count": 1,
                "suspected_duplicate_count": 0,
            }
        ],
        "lifecycle_row_links": [
            {
                "row_id": f"row-import-{index}",
                "decision": "created" if index < 3 else "duplicate_skipped",
                "source_id": f"source-{index}",
                "linked_object_type": "invoice" if terminal else None,
                "linked_object_id": f"invoice-{index}" if terminal else None,
                "candidate_count": 1,
                "candidate_invoice_id": f"invoice-{index}",
                "candidate_is_batch_owner": index < 3,
            }
            for index in range(1, 4)
        ],
    }


def _etc_session_retirement_snapshot(*, retired: bool = False) -> dict[str, list[dict[str, object]]]:
    revision = (
        "etc-import-page-audit.v1.deleted-task-retired"
        if retired
        else "etc-import-page-audit.v1"
    )
    return {
        "bank_files": [],
        "bank_transactions": [],
        "bank_rows": [],
        "invoice_rows": [],
        "etc_session_retirement_requested": [
            {"session_id": "session-deleted-1"},
            {"session_id": "session-deleted-2"},
        ],
        "etc_session_retirement_targets": [
            {
                "session_id": "session-deleted-1",
                "audit_contract_revision": revision,
                "session_status": "preview_ready",
                "task_id": "task-deleted-1",
                "task_status": "deleted",
                "task_raw_payload": {"normalized_payload": {"status": "deleted"}},
                "active_job_count": 0,
                "active_outbox_count": 0,
            },
            {
                "session_id": "session-deleted-2",
                "audit_contract_revision": revision,
                "session_status": "succeeded",
                "task_id": "task-deleted-2",
                "task_status": "deleted",
                "task_raw_payload": {"normalized_payload": {"status": "deleted"}},
                "active_job_count": 0,
                "active_outbox_count": 0,
            },
        ],
    }


def _reverted_batch_snapshot(*, payload_status: str = "pending") -> dict[str, list[dict[str, object]]]:
    return {
        "bank_files": [],
        "bank_transactions": [],
        "bank_rows": [],
        "invoice_rows": [],
        "reverted_batch_normalization_requested": [
            {"batch_id": "batch-reverted-1"},
            {"batch_id": "batch-reverted-2"},
        ],
        "reverted_batch_normalization_targets": [
            {
                "batch_id": batch_id,
                "batch_type": "input_invoice",
                "batch_status": "reverted",
                "batch_raw_payload": {"normalized_payload": {"status": payload_status}},
                "file_count": 1,
                "strict_reverted_file_count": 1,
                "active_or_succeeded_job_count": 0,
                "linked_row_count": 0,
                "canonical_invoice_count": 0,
            }
            for batch_id in ("batch-reverted-1", "batch-reverted-2")
        ],
    }


def _failed_import_recovery_snapshot(
    *,
    completed: bool = False,
    event_status: str | None = None,
) -> dict[str, list[dict[str, object]]]:
    error = 'duplicate key value violates unique constraint "background_jobs_idempotency_uidx"'
    file_ids = ["file-bank-1", "file-bank-2"]
    return {
        "recovery_requested": [
            {
                "import_job_id": "import-job-1",
                "event_id": "event-1",
                "background_job_id": "background-job-1",
                "session_id": "session-bank-1",
                "file_ids": file_ids,
            }
        ],
        "import_jobs": [
            {
                "import_job_id": "import-job-1",
                "tenant_id": "default",
                "import_type": "file_import.confirm",
                "import_session_id": "session-bank-1",
                "source_file_id": None,
                "idempotency_key": "file_import.confirm:session-bank-1:file-bank-1,file-bank-2",
                "request_fingerprint": "fingerprint",
                "status": "succeeded" if completed else "failed",
                "stage": "succeeded" if completed else "processor_failed",
                "priority": "normal",
                "attempt_count": 1,
                "max_attempts": 5,
                "last_error": None if completed else error,
                "payload": {
                    "session_id": "session-bank-1",
                    "selected_file_ids": file_ids,
                    "background_job_id": "background-job-1",
                    "owner_user_id": "owner-1",
                },
                "result_payload": {"confirmed": 2, "selected": 2} if completed else {},
                "raw_payload": {},
                "created_by": "owner-1",
                "trace_id": "trace-1",
            }
        ],
        "events": [
            {
                "event_id": "event-1",
                "event_type": "import.process.requested",
                "aggregate_type": "import_job",
                "aggregate_id": "import-job-1",
                "payload": {"import_job_id": "import-job-1"},
                "status": event_status or ("done" if completed else "dead_lettered"),
                "last_error": error,
                "raw_payload": {
                    "operator_resolution": {"reason": "candidate_import_recovery_succeeded"}
                }
                if completed
                else {},
            }
        ],
        "background_jobs": [
            {
                "job_id": "background-job-1",
                "job_type": "file_import",
                "status": "succeeded" if completed else "queued",
                "owner_id": "owner-1",
                "raw_payload": {
                    "normalized_payload": {
                        "job_id": "background-job-1",
                        "source": {
                            "session_id": "session-bank-1",
                            "selected_file_ids": file_ids,
                        },
                    }
                },
            }
        ],
        "files": [
            {
                "file_id": file_id,
                "session_id": "session-bank-1",
                "file_status": "confirmed" if completed else "preview_ready",
                "file_payload_status": "confirmed" if completed else "preview_ready",
                "session_status": "confirmed" if completed else "preview_ready",
                "batch_type": "bank_transaction",
                "preview_batch_id": f"preview-{index}",
                "batch_id": f"preview-{index}" if completed else None,
                "batch_status": "completed" if completed else "pending",
                "row_count": 6 if index == 1 else 24,
                "success_count": 0 if index == 1 else 8,
                "error_count": 0,
                "duplicate_count": 6 if index == 1 else 16,
                "suspected_duplicate_count": 0,
                "updated_count": 0,
                "canonical_bank_transaction_count": 0 if index == 1 or not completed else 8,
                "canonical_audit_issue_count": 0,
            }
            for index, file_id in enumerate(file_ids, start=1)
        ],
    }


class FailedImportRecoveryTests(unittest.TestCase):
    def test_plan_authorizes_only_exact_untouched_failed_bank_import(self) -> None:
        plan = build_failed_import_job_recovery_plan(_failed_import_recovery_snapshot())

        self.assertEqual(plan["target"]["file_ids"], ["file-bank-1", "file-bank-2"])
        self.assertEqual(plan["import_job"]["status"], "failed")
        self.assertEqual(len(plan["source_fingerprint"]), 64)

        suspected_duplicate_snapshot = _failed_import_recovery_snapshot()
        suspected_duplicate_snapshot["files"][0].update(
            {
                "session_status": "preview_ready_with_errors",
                "duplicate_count": 0,
                "suspected_duplicate_count": 6,
            }
        )
        suspected_duplicate_plan = build_failed_import_job_recovery_plan(suspected_duplicate_snapshot)
        self.assertEqual(suspected_duplicate_plan["files"][0]["suspected_duplicate_count"], 6)

        stale_preview_snapshot = _failed_import_recovery_snapshot()
        stale_preview_snapshot["import_jobs"][0]["last_error"] = "preview_stale"
        stale_preview_snapshot["background_jobs"][0]["status"] = "failed"
        stale_preview_plan = build_failed_import_job_recovery_plan(stale_preview_snapshot)
        self.assertEqual(stale_preview_plan["import_job"]["last_error"], "preview_stale")

        partial_snapshot = _failed_import_recovery_snapshot()
        partial_snapshot["files"][0]["canonical_bank_transaction_count"] = 1
        with self.assertRaisesRegex(ValueError, "not an untouched bank preview"):
            build_failed_import_job_recovery_plan(partial_snapshot)

    def test_repository_loads_only_explicit_recovery_rows(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_all(self, sql: str, params: tuple[object, ...]) -> list[dict[str, object]]:
                self.calls.append((sql, params))
                return []

        connection = Connection()

        snapshot = load_failed_import_job_recovery_snapshot(
            connection,
            import_job_id="import-job-1",
            event_id="event-1",
            background_job_id="background-job-1",
            session_id="session-bank-1",
            file_ids=["file-bank-2", "file-bank-1"],
        )

        self.assertEqual(len(connection.calls), 4)
        self.assertEqual(snapshot["recovery_requested"][0]["file_ids"], ["file-bank-1", "file-bank-2"])
        self.assertTrue(all("where" in sql.lower() for sql, _ in connection.calls))

    def test_repository_discovers_exact_recovery_target_from_failed_import_job(self) -> None:
        source = _failed_import_recovery_snapshot()

        class Connection:
            def fetch_all(self, sql: str, _params: tuple[object, ...]) -> list[dict[str, object]]:
                if "from job.import_jobs" in sql:
                    return deepcopy(source["import_jobs"])
                if "from job.outbox_events" in sql:
                    return deepcopy(source["events"])
                if "from job.background_jobs" in sql:
                    return deepcopy(source["background_jobs"])
                if "from app.import_files" in sql:
                    return deepcopy(source["files"])
                raise AssertionError(sql)

        plan = build_failed_import_job_recovery_plan(
            discover_failed_import_job_recovery_snapshot(
                Connection(),
                import_job_id="import-job-1",
            )
        )

        self.assertEqual(plan["target"], source["recovery_requested"][0])

    def test_execute_processes_candidate_before_resolving_exact_dead_letter(self) -> None:
        plan = build_failed_import_job_recovery_plan(_failed_import_recovery_snapshot())
        import_repository = Mock()
        import_repository.create_or_get_job.return_value = SimpleNamespace(
            import_job_id="import-job-1",
            status="pending",
        )
        queue = Mock()
        queue.get_event.return_value = SimpleNamespace(
            event_type="import.process.requested",
            status="dead_lettered",
        )
        queue.resolve_dead_letter_event.return_value = True
        handler = Mock(return_value={"processed": True})
        processor_factory = Mock()
        processor_factory.build_processors.return_value = {"file_import.confirm": Mock()}
        processed = _failed_import_recovery_snapshot(completed=True, event_status="dead_lettered")
        completed = _failed_import_recovery_snapshot(completed=True)

        with (
            patch(
                "fin_ops_platform.services.import_job_queue.ImportJobRepository",
                return_value=import_repository,
            ),
            patch(
                "fin_ops_platform.services.runtime_queue.RuntimeQueueRepository",
                return_value=queue,
            ),
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.ImportRuntimeProcessorFactory",
                return_value=processor_factory,
            ),
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.build_import_job_handler_bundle",
                return_value=SimpleNamespace(
                    handlers={"import.process.requested": handler}
                ),
            ),
            patch(
                "fin_ops_platform.services.postgres_repositories.import_audit_repair.load_failed_import_job_recovery_snapshot",
                side_effect=[processed, completed],
            ),
        ):
            result = execute_failed_import_job_recovery(object(), plan)

        self.assertEqual(result["canonical_bank_transaction_count"], 8)
        processor_factory.retry_file_import_preview.assert_called_once_with(
            session_id="session-bank-1",
            selected_file_ids=["file-bank-1", "file-bank-2"],
        )
        handler.assert_called_once_with(queue.get_event.return_value)
        queue.resolve_dead_letter_event.assert_called_once_with(
            "event-1",
            reason="candidate_import_recovery_succeeded",
        )

    def test_execute_keeps_dead_letter_when_candidate_business_facts_are_incomplete(self) -> None:
        plan = build_failed_import_job_recovery_plan(_failed_import_recovery_snapshot())
        import_repository = Mock()
        import_repository.create_or_get_job.return_value = SimpleNamespace(
            import_job_id="import-job-1",
            status="pending",
        )
        queue = Mock()
        queue.get_event.return_value = SimpleNamespace(
            event_type="import.process.requested",
            status="dead_lettered",
        )
        incomplete = _failed_import_recovery_snapshot(completed=True, event_status="dead_lettered")
        incomplete["background_jobs"][0]["status"] = "partial_success"

        with (
            patch(
                "fin_ops_platform.services.import_job_queue.ImportJobRepository",
                return_value=import_repository,
            ),
            patch(
                "fin_ops_platform.services.runtime_queue.RuntimeQueueRepository",
                return_value=queue,
            ),
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.ImportRuntimeProcessorFactory"
            ) as processor_factory,
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.build_import_job_handler_bundle",
                return_value=SimpleNamespace(
                    handlers={"import.process.requested": Mock(return_value={"processed": True})}
                ),
            ),
            patch(
                "fin_ops_platform.services.postgres_repositories.import_audit_repair.load_failed_import_job_recovery_snapshot",
                return_value=incomplete,
            ),
            self.assertRaisesRegex(RuntimeError, "background job did not reach succeeded"),
        ):
            processor_factory.return_value.build_processors.return_value = {}
            execute_failed_import_job_recovery(object(), plan)

        queue.resolve_dead_letter_event.assert_not_called()

    def test_execute_keeps_dead_letter_when_candidate_canonical_fields_do_not_match(self) -> None:
        plan = build_failed_import_job_recovery_plan(_failed_import_recovery_snapshot())
        import_repository = Mock()
        import_repository.create_or_get_job.return_value = SimpleNamespace(
            import_job_id="import-job-1",
            status="pending",
        )
        queue = Mock()
        queue.get_event.return_value = SimpleNamespace(
            event_type="import.process.requested",
            status="dead_lettered",
        )
        incomplete = _failed_import_recovery_snapshot(completed=True, event_status="dead_lettered")
        incomplete["files"][1]["canonical_audit_issue_count"] = 38

        with (
            patch(
                "fin_ops_platform.services.import_job_queue.ImportJobRepository",
                return_value=import_repository,
            ),
            patch(
                "fin_ops_platform.services.runtime_queue.RuntimeQueueRepository",
                return_value=queue,
            ),
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.ImportRuntimeProcessorFactory"
            ) as processor_factory,
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.build_import_job_handler_bundle",
                return_value=SimpleNamespace(
                    handlers={"import.process.requested": Mock(return_value={"processed": True})}
                ),
            ),
            patch(
                "fin_ops_platform.services.postgres_repositories.import_audit_repair.load_failed_import_job_recovery_snapshot",
                return_value=incomplete,
            ),
            self.assertRaisesRegex(RuntimeError, "file-bank-2 is incomplete"),
        ):
            processor_factory.return_value.build_processors.return_value = {}
            execute_failed_import_job_recovery(object(), plan)

        queue.resolve_dead_letter_event.assert_not_called()


class ImportAuditRepairPlanTests(unittest.TestCase):
    def test_canonical_bank_audit_accepts_strict_v3_to_v2_reference_match(self) -> None:
        self.assertIn("rows.data_fingerprint = bank_transaction.data_fingerprint", _FAILED_IMPORT_FILE_SQL)
        self.assertIn("'normalized_row'->>'account_detail_no'", _FAILED_IMPORT_FILE_SQL)
        self.assertIn("bank_transaction.bank_serial_no", _FAILED_IMPORT_FILE_SQL)
        self.assertIn(") && array_remove(", _FAILED_IMPORT_FILE_SQL)
        self.assertIn("like 'bank:%%'", _FAILED_IMPORT_FILE_SQL)
        self.assertIn("like 'bank-v2:%%'", _FAILED_IMPORT_FILE_SQL)
        self.assertIn("like 'bank-v3:%%'", _FAILED_IMPORT_FILE_SQL)
        self.assertNotIn("like 'bank:%'", _FAILED_IMPORT_FILE_SQL)
        self.assertNotIn("like 'bank-v2:%'", _FAILED_IMPORT_FILE_SQL)
        self.assertNotIn("like 'bank-v3:%'", _FAILED_IMPORT_FILE_SQL)

    def test_plan_normalizes_only_exact_reverted_preview_batch_payloads(self) -> None:
        plan = build_import_audit_repair_plan(_reverted_batch_snapshot())

        self.assertEqual(
            [row["batch_id"] for row in plan["reverted_batch_normalizations"]],
            ["batch-reverted-1", "batch-reverted-2"],
        )
        self.assertEqual(
            plan["rollback_manifest"]["restore_reverted_import_batches"],
            [row["before"] for row in plan["reverted_batch_normalizations"]],
        )
        self.assertEqual(
            public_repair_report(plan, mode="dry_run", written=False)["authorized_write_scope"],
            ["app.import_batches"],
        )

    def test_reverted_batch_normalization_is_idempotent_and_rejects_runtime_work(self) -> None:
        self.assertEqual(
            build_import_audit_repair_plan(_reverted_batch_snapshot(payload_status="reverted"))[
                "reverted_batch_normalizations"
            ],
            [],
        )
        snapshot = _reverted_batch_snapshot()
        snapshot["reverted_batch_normalization_targets"][0]["active_or_succeeded_job_count"] = 1

        with self.assertRaisesRegex(ValueError, "canonical or runtime work"):
            build_import_audit_repair_plan(snapshot)

    def test_repository_applies_reverted_batch_normalization_with_exact_precondition(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()

        apply_import_audit_repair(connection, build_import_audit_repair_plan(_reverted_batch_snapshot()))

        self.assertEqual(
            [params for _, params in connection.calls],
            [("batch-reverted-1",), ("batch-reverted-2",)],
        )
        self.assertTrue(all("batch.status = 'reverted'" in sql for sql, _ in connection.calls))

    def test_etc_session_snapshot_does_not_scan_unrelated_import_repair_domains(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
                self.calls.append((sql, params))
                return []

        connection = Connection()

        snapshot = load_import_audit_repair_snapshot(
            connection,
            etc_deleted_task_session_ids=["session-deleted-1"],
        )

        self.assertEqual(len(connection.calls), 1)
        self.assertIn("from app.etc_import_sessions", connection.calls[0][0])
        self.assertEqual(snapshot["bank_files"], [])

    def test_plan_retires_only_exact_inactive_sessions_for_formally_deleted_tasks(self) -> None:
        plan = build_import_audit_repair_plan(_etc_session_retirement_snapshot())

        self.assertEqual(
            [row["session_id"] for row in plan["etc_session_retirements"]],
            ["session-deleted-1", "session-deleted-2"],
        )
        self.assertEqual(
            plan["rollback_manifest"]["restore_etc_import_sessions"],
            [row["before"] for row in plan["etc_session_retirements"]],
        )
        self.assertTrue(plan["etc_session_retirement_mode"])
        self.assertEqual(
            import_audit_repair_ops.public_repair_report(plan, mode="dry_run", written=False)[
                "authorized_write_scope"
            ],
            ["app.etc_import_sessions"],
        )

    def test_plan_is_idempotent_after_deleted_task_sessions_are_retired(self) -> None:
        plan = build_import_audit_repair_plan(_etc_session_retirement_snapshot(retired=True))

        self.assertEqual(plan["etc_session_retirements"], [])

    def test_plan_refuses_etc_session_retirement_with_active_runtime_work(self) -> None:
        snapshot = _etc_session_retirement_snapshot()
        snapshot["etc_session_retirement_targets"][0]["active_job_count"] = 1

        with self.assertRaisesRegex(ValueError, "active runtime work"):
            build_import_audit_repair_plan(snapshot)

    def test_plan_refuses_etc_session_retirement_for_non_deleted_task(self) -> None:
        snapshot = _etc_session_retirement_snapshot()
        snapshot["etc_session_retirement_targets"][0]["task_status"] = "closed"
        snapshot["etc_session_retirement_targets"][0]["task_raw_payload"] = {
            "normalized_payload": {"status": "closed"}
        }

        with self.assertRaisesRegex(ValueError, "not formally deleted"):
            build_import_audit_repair_plan(snapshot)

    def test_repository_retires_etc_session_with_exact_preconditions(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 1

        connection = Connection()
        plan = build_import_audit_repair_plan(_etc_session_retirement_snapshot())

        apply_import_audit_repair(connection, plan)

        self.assertEqual(len(connection.calls), 2)
        self.assertTrue(all("update app.etc_import_sessions" in sql for sql, _ in connection.calls))
        self.assertEqual(connection.calls[0][1][1:], ("session-deleted-1", "task-deleted-1", "preview_ready"))

    def test_plan_repairs_exact_downgraded_lifecycle_from_succeeded_job_and_canonical_closure(self) -> None:
        plan = build_import_audit_repair_plan(_lifecycle_snapshot())

        self.assertEqual(len(plan["lifecycle_repairs"]), 1)
        repair = plan["lifecycle_repairs"][0]
        self.assertEqual((repair["batch_id"], repair["file_id"]), ("batch-import-1", "file-import-1"))
        self.assertEqual(len(repair["row_links"]), 3)
        self.assertEqual(repair["before"]["batch_status"], "pending")
        self.assertEqual(plan["rollback_manifest"]["restore_import_lifecycle"], [repair["before"]])
        self.assertEqual(len(plan["rollback_manifest"]["restore_import_row_links"]), 3)

    def test_plan_is_idempotent_after_lifecycle_is_terminal(self) -> None:
        plan = build_import_audit_repair_plan(_lifecycle_snapshot(terminal=True))

        self.assertEqual(plan["lifecycle_repairs"], [])

    def test_plan_refuses_lifecycle_repair_without_single_succeeded_job(self) -> None:
        snapshot = _lifecycle_snapshot()
        snapshot["lifecycle_jobs"][0]["status"] = "processing"

        with self.assertRaisesRegex(ValueError, "job is active"):
            build_import_audit_repair_plan(snapshot)

    def test_plan_refuses_lifecycle_repair_without_canonical_invoice_closure(self) -> None:
        snapshot = _lifecycle_snapshot()
        snapshot["lifecycle_row_links"][0]["candidate_count"] = 0
        snapshot["lifecycle_row_links"][0]["candidate_invoice_id"] = None

        with self.assertRaisesRegex(ValueError, "not one-to-one"):
            build_import_audit_repair_plan(snapshot)

    def test_repository_applies_lifecycle_batch_and_file_with_exact_preconditions(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
                self.calls.append((sql, params))
                return 3 if "jsonb_to_recordset" in sql else 1

        connection = Connection()
        plan = build_import_audit_repair_plan(_lifecycle_snapshot())

        apply_import_audit_repair(connection, plan)

        self.assertEqual(len(connection.calls), 3)
        self.assertEqual(connection.calls[1][1], ("batch-import-1",))
        self.assertEqual(connection.calls[2][1], ("batch-import-1", "file-import-1", "batch-import-1"))
        self.assertIn("jsonb_to_recordset", connection.calls[0][0])
        self.assertIn("status = 'completed'", connection.calls[1][0])
        self.assertIn("status = 'confirmed'", connection.calls[2][0])

    def test_plan_restores_bank_provenance_and_aggregates_invoice_components(self) -> None:
        plan = build_import_audit_repair_plan(_snapshot())

        self.assertEqual(len(plan["bank_rows"]), 1)
        self.assertEqual(plan["bank_rows"][0]["row_id"], "batch_row:batch-bank-1:00001")
        self.assertEqual(plan["bank_rows"][0]["linked_object_id"], "transaction-1")
        self.assertEqual(len(plan["invoice_updates"]), 1)
        self.assertEqual(plan["invoice_updates"][0]["amount"], "37.81")
        self.assertEqual(plan["invoice_updates"][0]["tax_amount"], "4.92")
        self.assertEqual(plan["invoice_updates"][0]["total_with_tax"], "42.73")
        self.assertEqual(plan["affected_invoice_months"], ["2026-07"])
        self.assertEqual(
            plan["rollback_manifest"]["delete_bank_row_ids"],
            ["batch_row:batch-bank-1:00001"],
        )

    def test_plan_is_idempotent_when_deterministic_bank_row_and_invoice_totals_exist(self) -> None:
        snapshot = _snapshot()
        first_plan = build_import_audit_repair_plan(snapshot)
        bank_row = first_plan["bank_rows"][0]
        snapshot["bank_rows"] = [
            {
                key: bank_row.get(key)
                for key in (
                    "row_id",
                    "batch_id",
                    "row_no",
                    "source_unique_key",
                    "data_fingerprint",
                    "decision",
                    "linked_object_id",
                    "identity_kind",
                )
            }
        ]
        invoice_update = first_plan["invoice_updates"][0]
        for component in snapshot["invoice_rows"]:
            component.update(
                {
                    "amount": invoice_update["amount"],
                    "signed_amount": invoice_update["signed_amount"],
                    "tax_amount": invoice_update["tax_amount"],
                    "total_with_tax": invoice_update["total_with_tax"],
                    "tax_rate": invoice_update["tax_rate"],
                }
            )

        second_plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual(second_plan["bank_rows"], [])
        self.assertEqual(second_plan["invoice_updates"], [])

    def test_plan_does_not_sum_identical_duplicate_invoice_rows(self) -> None:
        snapshot = _snapshot()
        duplicate = deepcopy(snapshot["invoice_rows"][0])
        duplicate["row_id"] = "row-invoice-duplicate"
        duplicate["row_no"] = 2
        snapshot["invoice_rows"] = [snapshot["invoice_rows"][0], duplicate]

        plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual(plan["invoice_updates"], [])

    def test_plan_fails_closed_when_registered_counts_conflict_with_canonical_bank_owner(self) -> None:
        snapshot = _snapshot()
        snapshot["bank_transactions"][0]["source_batch_id"] = "different-batch"

        with self.assertRaisesRegex(ValueError, "decision counts"):
            build_import_audit_repair_plan(snapshot)

    def test_plan_resolves_preview_created_duplicate_from_canonical_batch_ownership(self) -> None:
        snapshot = _snapshot()
        bank_file = snapshot["bank_files"][0]
        payload = bank_file["raw_payload"]["normalized_payload"]
        payload["row_results"].append(deepcopy(payload["row_results"][0]))
        payload["normalized_rows"].append(deepcopy(payload["normalized_rows"][0]))
        bank_file.update({"row_count": 2, "success_count": 1, "duplicate_count": 1})

        plan = build_import_audit_repair_plan(snapshot)

        self.assertEqual([row["decision"] for row in plan["bank_rows"]], ["created", "duplicate_skipped"])
        self.assertEqual(
            [row["linked_object_id"] for row in plan["bank_rows"]],
            ["transaction-1", "transaction-1"],
        )

    def test_plan_fails_closed_on_legacy_existing_bank_row_ids(self) -> None:
        snapshot = _snapshot()
        snapshot["bank_rows"] = [
            {
                "row_id": "batch_row_00001",
                "batch_id": "batch-bank-1",
                "row_no": 1,
                "source_unique_key": "bank-key-1",
                "decision": "created",
            }
        ]

        with self.assertRaisesRegex(ValueError, "non-deterministic ids"):
            build_import_audit_repair_plan(snapshot)

    def test_cli_dry_run_uses_repeatable_read_snapshot(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.statements: list[str] = []

            @contextmanager
            def transaction(self):
                yield self

            def execute(self, sql: str, _params: tuple = ()) -> int:
                self.statements.append(sql)
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(import_audit_repair_ops, "load_import_audit_repair_snapshot", return_value=_snapshot()),
        ):
            result = import_audit_repair_ops.main(["--dry-run"], stdout=output)

        self.assertEqual(result, 0)
        self.assertEqual(connection.statements, ["set transaction isolation level repeatable read read only"])
        self.assertFalse(json.loads(output.getvalue())["written"])

    def test_cli_requires_batch_and_file_target_together(self) -> None:
        with self.assertRaisesRegex(SystemExit, "provided together"):
            import_audit_repair_ops.main(["--dry-run", "--batch-id", "batch-import-1"])

    def test_cli_passes_exact_lifecycle_target_to_snapshot_loader(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "load_import_audit_repair_snapshot",
                return_value=_lifecycle_snapshot(),
            ) as load_snapshot,
        ):
            result = import_audit_repair_ops.main(
                ["--dry-run", "--batch-id", "batch-import-1", "--file-id", "file-import-1"],
                stdout=output,
            )

        self.assertEqual(result, 0)
        load_snapshot.assert_called_once_with(
            connection,
            lifecycle_batch_id="batch-import-1",
            lifecycle_file_id="file-import-1",
            etc_deleted_task_session_ids=[],
            reverted_batch_ids=[],
        )
        self.assertEqual(json.loads(output.getvalue())["lifecycle_repair_count"], 1)

    def test_cli_passes_explicit_etc_session_retirement_targets_to_snapshot_loader(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "load_import_audit_repair_snapshot",
                return_value=_etc_session_retirement_snapshot(),
            ) as load_snapshot,
        ):
            result = import_audit_repair_ops.main(
                [
                    "--dry-run",
                    "--retire-etc-session-id",
                    "session-deleted-1",
                    "--retire-etc-session-id",
                    "session-deleted-2",
                ],
                stdout=output,
            )

        self.assertEqual(result, 0)
        load_snapshot.assert_called_once_with(
            connection,
            lifecycle_batch_id=None,
            lifecycle_file_id=None,
            etc_deleted_task_session_ids=["session-deleted-1", "session-deleted-2"],
            reverted_batch_ids=[],
        )
        self.assertEqual(json.loads(output.getvalue())["etc_session_retirement_count"], 2)

    def test_cli_passes_explicit_reverted_batch_targets_to_snapshot_loader(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "load_import_audit_repair_snapshot",
                return_value=_reverted_batch_snapshot(),
            ) as load_snapshot,
        ):
            result = import_audit_repair_ops.main(
                [
                    "--dry-run",
                    "--normalize-reverted-batch-id",
                    "batch-reverted-1",
                    "--normalize-reverted-batch-id",
                    "batch-reverted-2",
                ],
                stdout=output,
            )

        self.assertEqual(result, 0)
        load_snapshot.assert_called_once_with(
            connection,
            lifecycle_batch_id=None,
            lifecycle_file_id=None,
            etc_deleted_task_session_ids=[],
            reverted_batch_ids=["batch-reverted-1", "batch-reverted-2"],
        )
        self.assertEqual(json.loads(output.getvalue())["reverted_batch_normalization_count"], 2)

    def test_cli_failed_import_recovery_requires_complete_explicit_target(self) -> None:
        with self.assertRaisesRegex(SystemExit, "requires job, event"):
            import_audit_repair_ops.main(
                ["--dry-run", "--recover-import-job-id", "import-job-1"]
            )

    def test_cli_bank_repair_prints_structured_relation_evidence_without_writing(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        candidates = [
            {
                "duplicate_transaction": {"transaction_id": "target-1", "amount": "496.20"},
                "keeper_transaction": {"transaction_id": "keeper-1", "amount": "496.20"},
                "written_off_amount": "0",
                "relation_counts": {"category_count": 1, "category_event_count": 1},
            }
        ]
        arguments = [
            "--dry-run",
            "--repair-bank-source",
            "session-1=file-1",
            "--expected-bank-target-count",
            "1",
            "--expected-bank-protected-count",
            "1",
            "--expected-bank-replay-create-count",
            "0",
            "--operator-id",
            "system_repair",
        ]
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(import_audit_repair_ops, "load_bank_import_dedup_repair_snapshot", return_value={}),
            patch.object(
                import_audit_repair_ops,
                "build_bank_import_dedup_repair_plan",
                side_effect=BankImportDedupRelationEvidenceError(candidates),
            ),
            patch.object(import_audit_repair_ops, "apply_bank_import_dedup_repair") as apply_repair,
        ):
            result = import_audit_repair_ops.main(arguments, stdout=output)

        report = json.loads(output.getvalue())
        self.assertEqual(result, 2)
        self.assertFalse(report["written"])
        self.assertFalse(report["eligible"])
        self.assertEqual(report["error_code"], "relationful_delete_candidates")
        self.assertEqual(report["candidates"], candidates)
        apply_repair.assert_not_called()

    def test_bank_repair_state_store_reuses_configured_object_storage(self) -> None:
        connection = Mock()
        settings = SimpleNamespace(enabled=True)
        repository = Mock()
        state_store = Mock()

        with (
            patch.object(
                import_audit_repair_ops.ObjectStorageSettings,
                "from_env",
                return_value=settings,
            ),
            patch.object(
                import_audit_repair_ops,
                "S3ObjectStorageRepository",
                return_value=repository,
            ) as build_repository,
            patch.object(
                import_audit_repair_ops,
                "default_data_dir",
                return_value="/var/lib/fin-ops",
            ),
            patch.object(
                import_audit_repair_ops,
                "PostgresStateStore",
                return_value=state_store,
            ) as build_state_store,
        ):
            result = import_audit_repair_ops._build_bank_repair_state_store(connection)

        self.assertIs(result, state_store)
        build_repository.assert_called_once_with(settings)
        build_state_store.assert_called_once_with(
            data_dir="/var/lib/fin-ops",
            connection=connection,
            object_storage_repository=repository,
        )

    def test_bank_repair_state_store_keeps_local_storage_without_adapter(self) -> None:
        connection = Mock()
        settings = SimpleNamespace(enabled=False)

        with (
            patch.object(
                import_audit_repair_ops.ObjectStorageSettings,
                "from_env",
                return_value=settings,
            ),
            patch.object(import_audit_repair_ops, "S3ObjectStorageRepository") as build_repository,
            patch.object(
                import_audit_repair_ops,
                "default_data_dir",
                return_value="/var/lib/fin-ops",
            ),
            patch.object(import_audit_repair_ops, "PostgresStateStore") as build_state_store,
        ):
            import_audit_repair_ops._build_bank_repair_state_store(connection)

        build_repository.assert_not_called()
        build_state_store.assert_called_once_with(
            data_dir="/var/lib/fin-ops",
            connection=connection,
        )

    def test_cli_related_bank_cleanup_requires_exact_8_plus_1_expectations(self) -> None:
        with self.assertRaisesRegex(SystemExit, "exact category/workbench counts"):
            import_audit_repair_ops.main(
                [
                    "--dry-run",
                    "--repair-bank-source",
                    "session-1=file-1",
                    "--expected-bank-target-count",
                    "731",
                    "--expected-bank-protected-count",
                    "1129",
                    "--expected-bank-replay-create-count",
                    "0",
                    "--operator-id",
                    "system_repair",
                    "--cleanup-related-bank-duplicates",
                ]
            )

    def test_cli_bank_cleanup_executes_withdraw_delete_audit_refresh_and_replay(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

            def fetch_one(self, _sql: str, _params: tuple = ()) -> dict[str, object]:
                return {"locked": True}

        connection = Connection()
        output = io.StringIO()
        plan = {
            "operation": "bank_import_identity_v3_recovery",
            "source_fingerprint": "f" * 64,
            "target_count": 731,
            "protected_count": 1129,
            "duplicate_delete_count": 674,
            "import_row_update_count": 709,
            "created_owner_transition_count": 674,
            "source_files": [{"file_id": "file-1"}],
            "affected_months": ["2026-02", "2026-05"],
            "category_cleanup_actions": [{"category_id": "category-1"}],
            "workbench_withdraw_actions": [{"case_id": "case-1"}],
        }
        runtime = Mock()
        runtime.replay_confirmed_file_import_session.side_effect = [
            {"audit_summary": {"created_count": 0}},
            {"audit_summary": {"created_count": 0}},
        ]
        refresh_gateway = Mock()
        refresh_gateway.enqueue_many.side_effect = lambda scope_type, scopes, **_kwargs: list(
            scopes
        )
        arguments = [
            "--execute",
            "--expected-fingerprint",
            "f" * 64,
            "--repair-bank-source",
            "session-1=file-1",
            "--expected-bank-target-count",
            "731",
            "--expected-bank-protected-count",
            "1129",
            "--expected-bank-replay-create-count",
            "0",
            "--operator-id",
            "system_repair",
            "--cleanup-related-bank-duplicates",
            "--expected-bank-category-cleanup-count",
            "8",
            "--expected-bank-workbench-withdraw-count",
            "1",
            "--expected-bank-workbench-transaction-id",
            "txn-300",
        ]
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "load_bank_import_dedup_repair_snapshot",
                return_value={},
            ) as load_snapshot,
            patch.object(
                import_audit_repair_ops,
                "build_bank_import_dedup_repair_plan",
                side_effect=[deepcopy(plan), deepcopy(plan)],
            ),
            patch.object(
                import_audit_repair_ops,
                "verify_bank_import_repair_source_files",
            ),
            patch.object(
                import_audit_repair_ops,
                "withdraw_bank_import_dedup_workbench_relations",
                return_value=[{"case_id": "case-1", "status": "withdrawn"}],
            ) as withdraw,
            patch.object(
                import_audit_repair_ops,
                "apply_bank_import_dedup_repair",
                return_value={"transaction_delete_count": 674},
            ) as apply_repair,
            patch.object(import_audit_repair_ops, "AuditTrailService") as audit_service,
            patch(
                "fin_ops_platform.services.read_model_refresh_gateway.ReadModelRefreshGateway",
                return_value=refresh_gateway,
            ),
            patch("fin_ops_platform.services.runtime_queue.RuntimeQueueRepository"),
            patch(
                "fin_ops_platform.services.runtime_worker_handlers.ImportRuntimeProcessorFactory",
                return_value=runtime,
            ),
        ):
            result = import_audit_repair_ops.main(arguments, stdout=output)

        self.assertEqual(result, 0)
        self.assertEqual(load_snapshot.call_count, 2)
        self.assertTrue(load_snapshot.call_args.kwargs["cleanup_related_duplicates"])
        self.assertEqual(load_snapshot.call_args.kwargs["expected_category_cleanup_count"], 8)
        withdraw.assert_called_once_with(connection, plan, operator_id="system_repair")
        apply_repair.assert_called_once_with(connection, plan, operator_id="system_repair")
        audit_service.return_value.record_action.assert_called_once()
        self.assertEqual(refresh_gateway.enqueue_many.call_count, 2)
        self.assertEqual(runtime.replay_confirmed_file_import_session.call_count, 2)
        report = json.loads(output.getvalue())
        self.assertEqual(report["apply_result"]["transaction_delete_count"], 674)

    def test_cli_failed_import_recovery_dry_run_bypasses_global_audit_scan(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        arguments = [
            "--dry-run",
            "--recover-import-job-id",
            "import-job-1",
            "--recover-event-id",
            "event-1",
            "--recover-background-job-id",
            "background-job-1",
            "--recover-session-id",
            "session-bank-1",
            "--recover-file-id",
            "file-bank-1",
            "--recover-file-id",
            "file-bank-2",
        ]
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "load_failed_import_job_recovery_snapshot",
                return_value=_failed_import_recovery_snapshot(),
            ) as load_snapshot,
            patch.object(import_audit_repair_ops, "load_import_audit_repair_snapshot") as global_scan,
        ):
            result = import_audit_repair_ops.main(arguments, stdout=output)

        self.assertEqual(result, 0)
        load_snapshot.assert_called_once_with(
            connection,
            import_job_id="import-job-1",
            event_id="event-1",
            background_job_id="background-job-1",
            session_id="session-bank-1",
            file_ids=["file-bank-1", "file-bank-2"],
        )
        global_scan.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["operation"], "failed_bank_import_recovery")

    def test_cli_failed_import_recovery_discovery_is_read_only(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "discover_failed_import_job_recovery_snapshot",
                return_value=_failed_import_recovery_snapshot(),
            ) as discover,
            patch.object(import_audit_repair_ops, "execute_failed_import_job_recovery") as execute,
        ):
            result = import_audit_repair_ops.main(
                ["--dry-run", "--discover-recover-import-job-id", "import-job-1"],
                stdout=output,
            )

        self.assertEqual(result, 0)
        discover.assert_called_once_with(connection, import_job_id="import-job-1")
        execute.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())["mode"], "discovery")

    def test_cli_failed_import_recovery_discovery_reports_ineligible_file_facts(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

        connection = Connection()
        snapshot = _failed_import_recovery_snapshot()
        snapshot["files"][0]["canonical_bank_transaction_count"] = 1
        output = io.StringIO()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(
                import_audit_repair_ops,
                "discover_failed_import_job_recovery_snapshot",
                return_value=snapshot,
            ),
        ):
            result = import_audit_repair_ops.main(
                ["--dry-run", "--discover-recover-import-job-id", "import-job-1"],
                stdout=output,
            )

        report = json.loads(output.getvalue())
        self.assertEqual(result, 2)
        self.assertFalse(report["eligible"])
        self.assertEqual(report["target"]["import_job_id"], "import-job-1")
        self.assertEqual(report["files"][0]["canonical_bank_transaction_count"], 1)

    def test_cli_execute_rejects_changed_fingerprint_before_writes(self) -> None:
        class Connection:
            @contextmanager
            def transaction(self):
                yield self

            def execute(self, _sql: str, _params: tuple = ()) -> int:
                return 0

            def fetch_one(self, _sql: str, _params: tuple = ()) -> dict[str, object]:
                return {"locked": True}

        connection = Connection()
        with (
            patch.object(import_audit_repair_ops.PostgresSettings, "from_env", return_value=object()),
            patch.object(import_audit_repair_ops, "PostgresConnection", return_value=connection),
            patch.object(import_audit_repair_ops, "load_import_audit_repair_snapshot", return_value=_snapshot()),
            patch.object(import_audit_repair_ops, "apply_import_audit_repair") as apply_repair,
            self.assertRaisesRegex(RuntimeError, "source changed"),
        ):
            import_audit_repair_ops.main(["--execute", "--expected-fingerprint", "stale"])

        apply_repair.assert_not_called()


if __name__ == "__main__":
    unittest.main()

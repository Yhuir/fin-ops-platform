from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fin_ops_platform.services.postgres_repositories import etc_tickets_page_audit


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.batches = [
            {
                "business_batch_id": "batch-1",
                "task_id": "task-1",
                "status": "draft",
                "scope_month": "2026-07",
                "invoice_count": 0,
                "total_amount": "0.00",
                "version": 1,
                "raw_payload": {
                    "normalized_payload": {
                        "business_batch_id": "batch-1",
                        "task_id": "task-1",
                        "title": "七月 ETC",
                        "status": "draft",
                        "version": 1,
                        "task_active_key": "task-1:active",
                        "invoice_ids": [],
                        "invoice_summary": {"count": 0, "amount": "0.00"},
                        "import_batch_ids": [],
                    }
                },
            }
        ]
        self.tasks = [
            {
                "task_id": "task-1",
                "status": "draft",
                "scope_month": "2026-07",
                "source_file_id": None,
                "result_summary": {},
                "version": 1,
                "raw_payload": {
                    "normalized_payload": {
                        "task_id": "task-1",
                        "status": "draft",
                        "version": 1,
                        "title": "七月 ETC",
                        "source_files": [],
                        "credit_card_items": [],
                        "ticket_root_items": [],
                        "supplement_evidences": [],
                        "reconciled_items": [],
                    }
                },
            }
        ]
        self.files: list[dict[str, object]] = []
        self.invoices: list[dict[str, object]] = []
        self.import_batches: list[dict[str, object]] = []
        self.submission_batches: list[dict[str, object]] = []
        self.invoice_links: list[dict[str, object]] = []
        self.import_jobs: list[dict[str, object]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if "from app.etc_business_batches" in sql:
            return [dict(row) for row in self.batches]
        if "from app.etc_reconciliation_tasks" in sql:
            return [dict(row) for row in self.tasks]
        if "from app.etc_reconciliation_files" in sql:
            return [dict(row) for row in self.files]
        if "from app.etc_invoices" in sql:
            return [dict(row) for row in self.invoices]
        if "from app.etc_import_batches" in sql:
            return [dict(row) for row in self.import_batches]
        if "from app.etc_submission_batches" in sql:
            return [dict(row) for row in self.submission_batches]
        if "from app.etc_batch_invoice_links" in sql:
            return [dict(row) for row in self.invoice_links]
        if "from job.import_jobs" in sql:
            return [dict(row) for row in self.import_jobs]
        raise AssertionError(f"unexpected SQL: {sql}")

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        raise AssertionError("ETC page Audit must be read-only")


class EtcTicketsPageAuditTests(unittest.TestCase):
    def test_batch_controls_use_etc_invoice_total_before_oa_reported_amount(self) -> None:
        count, amount = etc_tickets_page_audit._batch_controls(
            {
                "invoice_ids": ["etc-invoice-1"],
                "invoice_summary": {"count": 1, "amount": "1879.45"},
                "oa_total_amount": "1935.45",
                "amount_breakdown": {
                    "coverage_status": "partial",
                    "etc_invoice_amount": "1879.45",
                    "gap_amount": "56.00",
                    "gap_reason": "OA 金额包含非 ETC 费用",
                },
            },
            {"oa_total_amount": "1935.45"},
        )

        self.assertEqual(count, 1)
        self.assertEqual(amount, Decimal("1879.45"))

    def test_clean_direct_canonical_facts_pass_without_writes(self) -> None:
        connection = FakeConnection()

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["audit_contract"]["derived_tables"], [])
        self.assertIn("bidirectional equality", report["audit_contract"]["relation_edge_equality"])
        self.assertEqual(report["summary"]["unsubmitted_business_batch_count"], 1)
        self.assertEqual(report["summary"]["staged_business_batch_count"], 0)
        self.assertEqual(connection.executed, [])

    def test_creating_attempt_is_staged_without_an_external_oa_timeout_check(self) -> None:
        connection = FakeConnection()
        connection.batches[0].update(
            {
                "status": "oa_draft_creating",
                "updated_at": datetime.now(UTC),
                "audit_events": [
                    {
                        "event_type": "oa_draft_prepared",
                        "created_at": datetime.now(UTC) - timedelta(minutes=16),
                    }
                ],
            }
        )
        payload = connection.batches[0]["raw_payload"]["normalized_payload"]
        payload.update(
            {
                "status": "oa_draft_creating",
                "submission_batch_id": "submission-1",
                "oa_draft_idempotency_key": "oa-intent-1",
                "updated_at": datetime.now(UTC) - timedelta(minutes=16),
            }
        )
        connection.submission_batches = [
            {
                "submission_batch_id": "submission-1",
                "status": "draft_creating",
                "invoice_ids": [],
                "raw_payload": {"normalized_payload": {"invoice_ids": []}},
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertNotIn("etc_oa_draft_creating_stale", report["summary"]["issue_sample_counts_by_code"])
        self.assertNotIn("etc_oa_draft_attempt_missing", report["summary"]["issue_sample_counts_by_code"])
        self.assertEqual(report["summary"]["unsubmitted_business_batch_count"], 0)
        self.assertEqual(report["summary"]["staged_business_batch_count"], 1)

    def test_creating_without_durable_attempt_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.batches[0]["status"] = "oa_draft_creating"
        connection.batches[0]["updated_at"] = datetime.now(UTC)
        payload = connection.batches[0]["raw_payload"]["normalized_payload"]
        payload["status"] = "oa_draft_creating"

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn("etc_oa_draft_attempt_missing", report["summary"]["issue_sample_counts_by_code"])

    def test_pending_without_persisted_draft_is_blocking_and_counted_only_as_staged(self) -> None:
        connection = FakeConnection()
        connection.batches[0]["status"] = "oa_confirmation_pending"
        payload = connection.batches[0]["raw_payload"]["normalized_payload"]
        payload.update({"status": "oa_confirmation_pending", "submission_batch_id": "submission-1"})
        connection.submission_batches = [
            {
                "submission_batch_id": "submission-1",
                "status": "draft_created",
                "invoice_ids": [],
                "raw_payload": {"normalized_payload": {"invoice_ids": []}},
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn("etc_oa_confirmation_draft_missing", report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("etc_reconciliation_task_oa_draft_mismatch", report["summary"]["issue_sample_counts_by_code"])
        self.assertEqual(report["summary"]["unsubmitted_business_batch_count"], 0)
        self.assertEqual(report["summary"]["staged_business_batch_count"], 1)

    def test_not_submitted_preserves_membership_but_rejects_occupied_resources(self) -> None:
        connection = FakeConnection()
        connection.batches[0].update({"status": "not_submitted", "invoice_count": 1, "total_amount": "100.00"})
        payload = connection.batches[0]["raw_payload"]["normalized_payload"]
        payload.update(
            {
                "status": "not_submitted",
                "invoice_ids": ["etc-invoice-1"],
                "invoice_summary": {"count": 1, "amount": "100.00"},
                "import_batch_ids": ["import-1"],
            }
        )
        connection.tasks[0]["raw_payload"]["normalized_payload"]["oa_total_amount"] = "120.00"
        connection.tasks[0]["result_summary"]["oa_total_amount"] = "120.00"
        connection.invoices = [
            {
                "etc_invoice_id": "etc-invoice-1",
                "status": "unsubmitted",
                "business_batch_id": None,
                "batch_id": None,
                "task_id": "task-1",
                "amount": "100.00",
                "tax_amount": "0.00",
                "total_with_tax": "100.00",
                "raw_payload": {
                    "normalized_payload": {
                        "id": "etc-invoice-1",
                        "status": "unsubmitted",
                        "task_id": "task-1",
                        "import_batch_id": "import-1",
                        "current_batch_id": None,
                        "business_batch_id": None,
                        "amount_without_tax": "100.00",
                        "tax_amount": "0.00",
                        "total_amount": "100.00",
                    }
                },
            }
        ]
        connection.import_batches = [
            {
                "batch_id": "import-1",
                "invoice_count": 1,
                "raw_payload": {
                    "normalized_payload": {
                        "invoice_ids": ["etc-invoice-1"],
                        "submission_batch_id": None,
                    }
                },
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["overall_status"], "pass", report)
        self.assertNotIn("etc_business_batch_invoice_edge_mismatch", report["summary"]["issue_sample_counts_by_code"])
        self.assertNotIn("etc_not_submitted_occupancy_mismatch", report["summary"]["issue_sample_counts_by_code"])

        connection.invoices[0]["business_batch_id"] = "batch-1"
        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)
        self.assertIn("etc_not_submitted_occupancy_mismatch", report["summary"]["issue_sample_counts_by_code"])

        connection.invoices[0]["business_batch_id"] = "batch-2"
        connection.batches.append(
            {
                "business_batch_id": "batch-2",
                "task_id": "task-2",
                "status": "manually_marked_submitted",
                "scope_month": "2026-07",
                "invoice_count": 1,
                "total_amount": "100.00",
                "version": 1,
                "raw_payload": {
                    "normalized_payload": {
                        "business_batch_id": "batch-2",
                        "task_id": "task-2",
                        "title": "七月 ETC 新批次",
                        "status": "manually_marked_submitted",
                        "version": 1,
                        "task_active_key": None,
                        "invoice_ids": ["etc-invoice-1"],
                        "invoice_summary": {"count": 1, "amount": "100.00"},
                        "import_batch_ids": ["import-1"],
                        "submission_batch_id": "submission-2",
                    }
                },
            }
        )
        connection.tasks.append(
            {
                "task_id": "task-2",
                "status": "imported",
                "scope_month": "2026-07",
                "source_file_id": None,
                "result_summary": {},
                "version": 1,
                "raw_payload": {
                    "normalized_payload": {
                        "task_id": "task-2",
                        "status": "imported",
                        "version": 1,
                        "title": "七月 ETC 新批次",
                        "source_files": [],
                        "credit_card_items": [],
                        "ticket_root_items": [],
                        "supplement_evidences": [],
                        "reconciled_items": [],
                    }
                },
            }
        )
        connection.submission_batches = [
            {
                "submission_batch_id": "submission-2",
                "status": "submitted_confirmed",
                "invoice_ids": ["etc-invoice-1"],
                "raw_payload": {
                    "normalized_payload": {
                        "invoice_ids": ["etc-invoice-1"],
                    }
                },
            }
        ]
        connection.invoices[0]["status"] = "submitted"
        connection.invoices[0]["batch_id"] = "submission-2"
        invoice_payload = connection.invoices[0]["raw_payload"]["normalized_payload"]
        invoice_payload["status"] = "submitted"
        invoice_payload["business_batch_id"] = "batch-2"
        invoice_payload["current_batch_id"] = "submission-2"

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["overall_status"], "pass", report)

    def test_missing_batch_task_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.tasks = []

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn("etc_business_batch_task_missing", report["summary"]["issue_sample_counts_by_code"])

    def test_batch_invoice_edge_is_bidirectional(self) -> None:
        connection = FakeConnection()
        connection.batches[0]["invoice_count"] = 1
        payload = connection.batches[0]["raw_payload"]["normalized_payload"]
        payload["invoice_ids"] = ["etc-invoice-1"]
        payload["invoice_summary"] = {"count": 1, "amount": "100.00"}
        connection.batches[0]["total_amount"] = "100.00"

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn("etc_business_batch_invoice_missing", report["summary"]["issue_sample_counts_by_code"])
        self.assertIn("etc_business_batch_invoice_edge_mismatch", report["summary"]["issue_sample_counts_by_code"])

    def test_reimport_event_can_reference_an_invoice_owned_by_an_earlier_import(self) -> None:
        connection = FakeConnection()
        connection.invoices = [
            {
                "etc_invoice_id": "etc-invoice-1",
                "status": "unsubmitted",
                "amount": "100.00",
                "tax_amount": "0.00",
                "total_with_tax": "100.00",
                "raw_payload": {"normalized_payload": {"id": "etc-invoice-1", "import_batch_id": "import-1"}},
            }
        ]
        connection.import_batches = [
            {"batch_id": "import-1", "invoice_count": 1, "raw_payload": {"normalized_payload": {"invoice_ids": ["etc-invoice-1"]}}},
            {"batch_id": "import-2", "invoice_count": 1, "raw_payload": {"normalized_payload": {"invoice_ids": ["etc-invoice-1"]}}},
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertNotIn("etc_import_batch_invoice_edge_mismatch", report["summary"]["issue_sample_counts_by_code"])
        self.assertNotIn("etc_import_batch_invoice_missing", report["summary"]["issue_sample_counts_by_code"])

    def test_current_import_owner_must_declare_the_invoice_member(self) -> None:
        connection = FakeConnection()
        connection.invoices = [
            {
                "etc_invoice_id": "etc-invoice-1",
                "status": "unsubmitted",
                "amount": "100.00",
                "tax_amount": "0.00",
                "total_with_tax": "100.00",
                "raw_payload": {"normalized_payload": {"id": "etc-invoice-1", "import_batch_id": "import-1"}},
            }
        ]
        connection.import_batches = [
            {"batch_id": "import-1", "invoice_count": 0, "raw_payload": {"normalized_payload": {"invoice_ids": []}}}
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn(
            "etc_invoice_import_owner_membership_mismatch",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_card_ticket_edge_rejects_an_orphan_card_reference(self) -> None:
        connection = FakeConnection()
        payload = connection.tasks[0]["raw_payload"]["normalized_payload"]
        payload["credit_card_items"] = [{"item_id": "card-1", "task_id": "task-1"}]
        payload["ticket_root_items"] = [
            {
                "item_id": "ticket-1",
                "task_id": "task-1",
                "linked_credit_card_item_ids": ["missing-card"],
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertIn("etc_ticket_root_card_missing", report["summary"]["issue_sample_counts_by_code"])

    def test_active_import_job_blocks_freshness_and_queue(self) -> None:
        connection = FakeConnection()
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "status": "processing",
                "attempt_count": 1,
                "max_attempts": 5,
                "task_status": "imported",
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "pass")
        self.assertEqual(report["audit_status"]["freshness"], "not_fresh")
        self.assertEqual(report["audit_status"]["queue"], "backlog")

    def test_failed_import_job_is_terminal_before_max_attempts(self) -> None:
        connection = FakeConnection()
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "status": "failed",
                "attempt_count": 1,
                "max_attempts": 5,
                "last_error": "parse failed",
                "import_session_id": "session-1",
                "session_status": "failed",
                "task_id": "task-1",
                "task_status": "ready_for_import",
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["audit_status"]["queue"], "drained")
        self.assertIn(
            "etc_import_job_terminal_failure",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_failed_import_job_is_covered_by_imported_task(self) -> None:
        connection = FakeConnection()
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "status": "failed",
                "attempt_count": 1,
                "max_attempts": 5,
                "last_error": "worker acknowledgement failed",
                "import_session_id": "session-1",
                "session_status": "succeeded",
                "task_id": "task-1",
                "task_status": "imported",
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["summary"]["covered_failed_import_job_count"], 1)

    def test_dead_lettered_import_job_without_completed_task_blocks_integrity(self) -> None:
        connection = FakeConnection()
        connection.import_jobs = [
            {
                "job_id": "job-1",
                "status": "dead_lettered",
                "attempt_count": 5,
                "max_attempts": 5,
                "last_error": "parse failed",
                "import_session_id": "session-1",
                "session_status": "failed",
                "task_id": "task-1",
                "task_status": "ready_for_import",
            }
        ]

        report = etc_tickets_page_audit.audit_etc_tickets_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["audit_status"]["queue"], "drained")


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest
from contextlib import contextmanager
from unittest.mock import patch

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    evaluate_audit_issues,
    read_only_audit_snapshot,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import audit_import_center_page


class OperationsAuditReportTests(unittest.TestCase):
    def test_database_audit_snapshot_is_repeatable_read_and_read_only(self) -> None:
        transaction = _SnapshotTransaction()
        connection = _SnapshotConnection(transaction)

        with read_only_audit_snapshot(connection) as snapshot:
            self.assertIs(snapshot.connection, transaction)
            self.assertEqual(snapshot.consistency, "repeatable_read_read_only")
            self.assertTrue(snapshot.database_snapshot)

        self.assertEqual(
            transaction.executed,
            [
                ("set transaction isolation level repeatable read read only", ()),
                ("select set_config('statement_timeout', %s, true)", ("60000",)),
            ],
        )
        self.assertEqual(connection.transaction_count, 1)

    def test_reports_samples_and_separates_freshness_from_integrity(self) -> None:
        evaluation = evaluate_audit_issues(
            [
                AuditIssue("error", "read_model_scope_not_fresh", "scope pending"),
                AuditIssue("error", "row_mismatch", "row mismatch", subject_id="row-1"),
                AuditIssue("error", "row_mismatch", "row mismatch", subject_id="row-2"),
            ],
            sample_limit=1,
        )

        self.assertEqual(evaluation.overall_status, "issues_found")
        self.assertEqual(
            evaluation.audit_status,
            {"integrity": "issues_found", "freshness": "not_fresh", "queue": "drained"},
        )
        self.assertEqual(evaluation.summary["blocking_issue_sample_count"], 2)
        self.assertEqual(
            evaluation.summary["issue_sample_counts_by_code"],
            {"read_model_scope_not_fresh": 1, "row_mismatch": 1},
        )
        self.assertTrue(evaluation.summary["issue_samples_truncated"])

    def test_workbench_convergence_issue_invalidates_freshness(self) -> None:
        convergence = evaluate_audit_issues(
            [AuditIssue("error", "workbench_matching_scope_not_converged", "scope pending")],
            sample_limit=1,
        )

        self.assertEqual(
            convergence.audit_status,
            {"integrity": "pass", "freshness": "not_fresh", "queue": "backlog"},
        )

    def test_import_center_uses_one_snapshot_and_fails_when_any_import_proof_fails(self) -> None:
        clean = {
            "overall_status": "pass",
            "audit_status": {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
            "issues": [],
        }
        blocked = {
            "overall_status": "issues_found",
            "audit_status": {"integrity": "issues_found", "freshness": "fresh", "queue": "drained"},
            "issues": [{"severity": "error", "code": "file_mismatch"}],
        }
        with (
            patch(
                "fin_ops_platform.services.postgres_repositories.operations_audit.audit_bank_transaction_import_page",
                return_value=clean,
            ),
            patch(
                "fin_ops_platform.services.postgres_repositories.operations_audit.audit_invoice_import_page",
                return_value=blocked,
            ),
            patch(
                "fin_ops_platform.services.postgres_repositories.operations_audit.audit_etc_import_page",
                return_value=clean,
            ),
        ):
            report = audit_import_center_page(object())

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(report["summary"]["blocking_component_count"], 1)


class _SnapshotTransaction:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        return 0


class _SnapshotConnection:
    def __init__(self, transaction: _SnapshotTransaction) -> None:
        self._transaction = transaction
        self.transaction_count = 0

    @contextmanager
    def transaction(self):  # type: ignore[no-untyped-def]
        self.transaction_count += 1
        yield self._transaction


if __name__ == "__main__":
    unittest.main()

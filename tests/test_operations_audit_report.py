from __future__ import annotations

import unittest
from contextlib import contextmanager

from fin_ops_platform.services.postgres_repositories.audit_report import (
    AuditIssue,
    evaluate_audit_issues,
    read_only_audit_snapshot,
)


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

    def test_workbench_convergence_and_source_version_issues_invalidate_freshness(self) -> None:
        convergence = evaluate_audit_issues(
            [AuditIssue("error", "workbench_matching_scope_not_converged", "scope pending")],
            sample_limit=1,
        )
        source_version = evaluate_audit_issues(
            [AuditIssue("error", "workbench_generation_source_versions_mismatch", "version mismatch")],
            sample_limit=1,
        )

        self.assertEqual(
            convergence.audit_status,
            {"integrity": "pass", "freshness": "not_fresh", "queue": "backlog"},
        )
        self.assertEqual(
            source_version.audit_status,
            {"integrity": "pass", "freshness": "not_fresh", "queue": "drained"},
        )


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

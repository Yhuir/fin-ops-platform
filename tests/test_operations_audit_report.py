from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.audit_report import AuditIssue, evaluate_audit_issues


class OperationsAuditReportTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

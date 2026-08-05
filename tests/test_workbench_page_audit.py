from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    audit_workbench_relation_display,
)
from fin_ops_platform.services.postgres_repositories.workbench_projection_audit import (
    _PROOF_QUERIES,
)


class _Connection:
    def __init__(self, issues: list[dict[str, object]] | None = None) -> None:
        self.issues = list(issues or [])
        self.integrity_sql = ""

    def fetch_all(self, sql: str, _params: tuple[object, ...]) -> list[dict[str, object]]:
        self.integrity_sql = sql
        return self.issues

    def fetch_one(self, _sql: str) -> dict[str, int]:
        return {
            "oa_count": 1,
            "bank_count": 1,
            "invoice_count": 1,
            "active_relation_count": 1,
        }


class WorkbenchPageAuditTests(unittest.TestCase):
    def test_projection_audit_ignores_legacy_exception_controls(self) -> None:
        override_sql = next(
            sql
            for sql, code, _message in _PROOF_QUERIES
            if code == "workbench_override_exception_fields_mismatch"
        )

        self.assertNotIn("exception_members as", override_sql)
        self.assertNotIn("exception_mismatch as", override_sql)
        self.assertIn("override.override_payload->'ignored' is distinct from 'true'::jsonb", override_sql)
        self.assertIn("not (override.override_payload ? 'exception_case_id')", override_sql)

    def test_exact_canonical_etc_summary_contract_is_part_of_integrity_audit(self) -> None:
        connection = _Connection()

        report = audit_workbench_relation_display(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertIn("app.etc_business_batches", report["audit_contract"]["source_tables"])
        self.assertIn("app.etc_submission_batches", report["audit_contract"]["source_tables"])
        self.assertIn("app.etc_batch_invoice_links", report["audit_contract"]["source_tables"])
        self.assertIn(
            "'etc-summary-' || regexp_replace(",
            connection.integrity_sql,
        )
        self.assertIn(
            "etc_batch.external_batch_id = member.external_etc_batch_id",
            connection.integrity_sql,
        )
        self.assertIn(
            "invoice.id is null and etc_batch.external_batch_id is null",
            connection.integrity_sql,
        )

    def test_invalid_noncanonical_summary_member_remains_blocking(self) -> None:
        connection = _Connection(
            [
                {
                    "mismatch_kind": "missing_canonical_invoice_member",
                    "subject_id": "CASE-INVALID",
                    "scope_key": "2026-07",
                    "row_id": "etc-summary-not-a-canonical-batch",
                    "row_type": "invoice",
                }
            ]
        )

        report = audit_workbench_relation_display(connection)

        self.assertEqual(report["overall_status"], "issues_found")
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertEqual(
            report["issues"][0]["details"]["mismatch_kind"],
            "missing_canonical_invoice_member",
        )


if __name__ == "__main__":
    unittest.main()

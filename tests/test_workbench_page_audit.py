from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    audit_workbench_relation_display,
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
        self.assertIn("ranked_modern_etc_rows", connection.integrity_sql)
        self.assertIn(
            "etc_summary_modern_source_parity_mismatch",
            connection.integrity_sql,
        )
        self.assertIn("submitted_etc_relation_gaps", connection.integrity_sql)
        self.assertIn("submitted_etc_batch_oa_missing", connection.integrity_sql)
        self.assertIn("submitted_etc_batch_relation_missing", connection.integrity_sql)
        self.assertIn("submitted_etc_batch_relation_member_missing", connection.integrity_sql)
        self.assertIn("member.row_id = batch.summary_row_id", connection.integrity_sql)

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

    def test_partial_bridge_parity_mismatch_is_diagnostic_warning(self) -> None:
        connection = _Connection(
            [
                {
                    "mismatch_kind": "etc_summary_modern_source_parity_mismatch",
                    "subject_id": "ETC-PARTIAL",
                    "scope_key": "2026-07",
                    "row_id": "etc-summary-ETC-PARTIAL",
                    "row_type": "invoice",
                }
            ]
        )

        report = audit_workbench_relation_display(connection)

        self.assertEqual(report["summary"]["warning_count"], 1)
        self.assertEqual(report["summary"]["error_count"], 0)
        self.assertEqual(report["issues"][0]["severity"], "warning")
        self.assertIn("ETC 业务批次", report["issues"][0]["message"])

    def test_submitted_batch_relation_gap_is_reported_with_specific_warning_code(self) -> None:
        connection = _Connection(
            [
                {
                    "mismatch_kind": "submitted_etc_batch_relation_missing",
                    "subject_id": "ETC-UNPAIRED",
                    "scope_key": "2026-06",
                    "row_id": "etc-summary-ETC-UNPAIRED",
                    "row_type": "invoice",
                }
            ]
        )

        report = audit_workbench_relation_display(connection)

        self.assertEqual(report["summary"]["warning_count"], 1)
        self.assertEqual(report["summary"]["error_count"], 0)
        self.assertEqual(report["issues"][0]["code"], "submitted_etc_batch_relation_missing")
        self.assertIn("active relation", report["issues"][0]["message"])

    def test_metadata_only_etc_relation_is_reported_as_missing_actual_member(self) -> None:
        connection = _Connection(
            [
                {
                    "mismatch_kind": "submitted_etc_batch_relation_member_missing",
                    "subject_id": "ETC-METADATA-ONLY",
                    "scope_key": "2026-05",
                    "row_id": "etc-summary-ETC-METADATA-ONLY",
                    "row_type": "invoice",
                }
            ]
        )

        report = audit_workbench_relation_display(connection)

        self.assertEqual(report["summary"]["warning_count"], 1)
        self.assertEqual(
            report["issues"][0]["code"],
            "submitted_etc_batch_relation_member_missing",
        )
        self.assertIn("发票汇总成员", report["issues"][0]["message"])


if __name__ == "__main__":
    unittest.main()

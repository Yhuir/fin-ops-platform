from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.tax_offset_page_audit import (
    audit_tax_offset_page,
)


class FakeConnection:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.queries: list[str] = []
        self.invoices = [
            {
                "scope_key": "2026-05",
                "row_id": "output-1",
                "invoice_type": "output",
                "invoice_no": "OUT-1",
                "invoice_date": "2026-05-02",
                "buyer_name": "购方",
                "buyer_tax_no": "BUY-TAX",
                "tax_amount": "10.00",
                "amount": "100.00",
                "tax_rate": "0.1",
            },
            {
                "scope_key": "2026-05",
                "row_id": "input-1",
                "invoice_type": "input",
                "invoice_no": "IN-1",
                "digital_invoice_no": "DIG-1",
                "invoice_date": "2026-05-03",
                "seller_name": "销方",
                "seller_tax_no": "SELL-TAX",
                "tax_amount": "6.00",
                "amount": "60.00",
                "tax_rate": "0.1",
                "raw_payload": {"risk_level": "低"},
            },
        ]
        self.certified = [
            {
                "scope_key": "2026-05",
                "certified_unique_key": "cert-1",
                "digital_invoice_no": "DIG-1",
                "invoice_no": "IN-1",
                "seller_name": "销方",
                "seller_tax_no": "SELL-TAX",
                "invoice_date": "2026-05-03",
                "amount": "60.00",
                "tax_amount": "6.00",
                "status": "已认证",
            }
        ]
        self.plans = [
            {
                "scope_key": "2026-05",
                "selected_output_ids": ["output-1", "missing-output"],
                "selected_input_ids": ["input-1", "missing-input"],
            }
        ]

    def fetch_all(
        self,
        sql: str,
        params: tuple[object, ...] = (),
    ) -> list[dict[str, object]]:
        del params
        self.queries.append(sql)
        if "from app.invoices" in sql:
            return [dict(row) for row in self.invoices]
        if "from app.tax_certified_import_records" in sql:
            return [dict(row) for row in self.certified]
        if "from app.tax_offset_plans" in sql:
            return [dict(row) for row in self.plans]
        raise AssertionError(f"unexpected audit query: {sql}")

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        del params
        self.executed.append(sql)
        raise AssertionError("tax offset audit must be read-only")


class TaxOffsetPageAuditTests(unittest.TestCase):
    def test_direct_canonical_audit_has_no_read_model_queue_or_relation_dependency(self) -> None:
        connection = FakeConnection()

        report = audit_tax_offset_page(connection)

        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(
            report["audit_status"],
            {"integrity": "pass", "freshness": "fresh", "queue": "drained"},
        )
        self.assertEqual(report["audit_contract"]["derived_tables"], [])
        self.assertEqual(report["audit_contract"]["relation_tables"], [])
        self.assertIn(
            "does not consume",
            report["audit_contract"]["relation_edge_equality"],
        )
        self.assertEqual(connection.executed, [])
        self.assertEqual(len(connection.queries), 3)
        self.assertFalse(
            any(
                "read_model." in sql
                or "job.read_model_dirty_scopes" in sql
                or "job.outbox_events" in sql
                or "workbench_pair_relations" in sql
                for sql in connection.queries
            )
        )
        self.assertEqual(
            report["summary"]["page_statistics"],
            {
                "input_invoice_count": 1,
                "output_invoice_count": 1,
                "certification_record_count": 1,
                "matched_certification_count": 1,
                "unmatched_certification_count": 0,
                "out_of_scope_certification_count": 0,
                "deductible_invoice_count": 1,
                "selected_invoice_count": 1,
                "unselected_invoice_count": 1,
            },
        )

    def test_ambiguous_certified_identity_is_blocking(self) -> None:
        connection = FakeConnection()
        connection.invoices.append({**connection.invoices[1], "row_id": "input-2"})

        report = audit_tax_offset_page(connection)

        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertIn(
            "tax_offset_certified_match_ambiguous",
            report["summary"]["issue_sample_counts_by_code"],
        )

    def test_duplicate_certifications_cannot_claim_one_input_without_an_issue(self) -> None:
        connection = FakeConnection()
        connection.certified.append(
            {
                **connection.certified[0],
                "certified_unique_key": "cert-2",
            }
        )

        report = audit_tax_offset_page(connection)

        self.assertIn(
            "tax_offset_input_matched_by_multiple_certified_records",
            report["summary"]["issue_sample_counts_by_code"],
        )


if __name__ == "__main__":
    unittest.main()

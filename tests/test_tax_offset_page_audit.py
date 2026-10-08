from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.tax_offset_page_audit import audit_tax_offset_page
from tests.test_tax_offset_canonical_repository import FakeConnection


class AuditConnection(FakeConnection):
    def __init__(self, invalid=None, unresolved=None):
        super().__init__(count=1)
        self.invalid = invalid or []
        self.unresolved = unresolved or []

    def fetch_all(self, sql, params=()):
        if "where status not in ('revoked', 'deleted') and invoice_id is null" in sql:
            self.queries.append((sql, params))
            return self.unresolved
        if "select c.certified_unique_key" in sql:
            self.queries.append((sql, params))
            return self.invalid
        return super().fetch_all(sql, params)


class TaxOffsetPageAuditTests(unittest.TestCase):
    def test_audit_uses_fixed_snapshot_without_plan_or_cache(self):
        connection = AuditConnection()
        report = audit_tax_offset_page(connection)
        self.assertEqual(report["overall_status"], "pass")
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(report["summary"]["canonical_invoice_count"], 1)
        self.assertEqual(report["audit_contract"]["source_tables"], ["app.invoices", "app.tax_certified_import_records"])
        self.assertTrue(report["audit_contract"]["database_snapshot"])
        self.assertFalse(any("tax_offset_plans" in sql or "read_model" in sql or "workbench_pair" in sql for sql, _ in connection.queries))
        self.assertTrue(all(sql.startswith("set ") or sql.startswith("select set_config") for sql in connection.commands))

    def test_invalid_strong_binding_is_reported(self):
        connection = AuditConnection([{"certified_unique_key": "digital:123", "invoice_id": "invoice-id", "tax_period": None}])
        report = audit_tax_offset_page(connection)
        self.assertEqual(report["audit_status"]["integrity"], "issues_found")
        self.assertIn("tax_offset_invalid_certification_binding", report["summary"]["issue_sample_counts_by_code"])
        self.assertEqual(report["issues"][0]["subject_id"], "digital:123")

    def test_unresolved_certification_evidence_is_visible_warning(self):
        connection = AuditConnection(unresolved=[{"certified_unique_key": "legacy", "tax_period": "2026-09"}])
        report = audit_tax_offset_page(connection)
        self.assertEqual(report["summary"]["unresolved_record_count"], 1)
        self.assertIn("tax_offset_unresolved_certification", report["summary"]["issue_sample_counts_by_code"])
        self.assertEqual(report["issues"][0]["severity"], "warning")

from __future__ import annotations

import unittest
from contextlib import contextmanager
from io import BytesIO
from types import SimpleNamespace
from uuid import uuid4

from fin_ops_platform.services.invoice_kind import invoice_kind_fields
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.tax_offset import PostgresTaxOffsetCanonicalRepository
from fin_ops_platform.services.postgres_repositories.tax_offset_page_audit import audit_tax_offset_page
from fin_ops_platform.services.tax_offset_export_service import TaxOffsetExportService
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQueryService
from openpyxl import load_workbook

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class TaxCertificationQueryPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = require_postgres_test_database_url()
        apply_test_migrations(cls.dsn)
        cls.connection = PostgresConnection(PostgresSettings(database_url=cls.dsn, pool_enabled=False))

    @classmethod
    def tearDownClass(cls):
        cls.connection.close()

    def setUp(self):
        truncate_test_database(self.dsn)
        self.addCleanup(truncate_test_database, self.dsn)
        self.repo = PostgresTaxOffsetCanonicalRepository(self.connection)
        self.service = TaxOffsetQueryService(canonical_repository=self.repo)

    def invoice(self, *, kind="数电票(专用发票)", invoice_type="input", status="pending", day="2026-09-01",
                digital=None, code="CODE", number=None, buyer="BUYER", amount="100.00", tax="13.00", seller="供应商"):
        identity = str(uuid4())
        self.connection.execute("""insert into app.invoices(id,invoice_type,invoice_no,invoice_code,digital_invoice_no,
            invoice_date,invoice_month,seller_name,seller_tax_no,buyer_tax_no,amount,signed_amount,tax_amount,status,raw_payload)
            values(%s::uuid,%s,%s,%s,%s,%s::date,date_trunc('month',%s::date),%s,'SELLER',%s,%s,%s,%s,%s,%s)""",
            (identity, invoice_type, number or identity, code, digital or identity, day, day, seller, buyer,
             amount, amount, tax, status, jsonb({"normalized_payload": {**invoice_kind_fields(kind)}})))
        return identity

    def certify(self, invoice, *, selected="2026-10-02 10:30:00", period=None, deductible="12.123456", status="active"):
        source = self.connection.fetch_one("select * from app.invoices where id=%s::uuid", (invoice,))
        self.connection.execute("""insert into app.tax_certified_import_records(certified_unique_key,invoice_id,invoice_no,
            invoice_code,digital_invoice_no,buyer_tax_no,invoice_date,amount,tax_amount,deductible_tax_amount,selection_time,
            scope_month,status,match_status,raw_payload)
            values(%s,%s::uuid,%s,%s,%s,%s,%s,%s,%s,%s,%s::timestamp,%s::date,%s,'matched_invoice',%s)""",
            ("cert:" + invoice, invoice, source["invoice_no"], source["invoice_code"], source["digital_invoice_no"],
             source["buyer_tax_no"], source["invoice_date"], source["amount"], source["tax_amount"], deductible,
             selected, period + "-01" if period else None, status,
             jsonb({"normalized_payload": {"source_fields": {"risk_status": "无", "amount": "999"}}})))

    def test_all_month_inventory_filters_certification_and_preserves_null_decimal_sources(self):
        older = self.invoice(day="2025-01-01", amount=None, tax=None)
        current = self.invoice(kind="电子发票（增值税专用发票）", amount="12.123456", tax="0")
        self.certify(older)
        self.invoice(invoice_type="output")
        self.invoice(kind="普通发票")
        self.invoice(status="deleted")
        all_rows = self.service.list_payload({})
        self.assertEqual(all_rows["total"], 2)
        self.assertEqual({row["id"] for row in all_rows["rows"]}, {older, current})
        certified = all_rows["summary"]["certified"]
        self.assertEqual(certified["missing_amount_count"], 1)
        self.assertEqual(certified["missing_tax_count"], 1)
        self.assertIsNone(certified["amount"])
        self.assertEqual(certified["deductible_tax_amount"], "12.123456")
        self.assertEqual(all_rows["summary"]["uncertified"]["amount"], "12.123456")
        row = next(row for row in all_rows["rows"] if row["id"] == older)
        self.assertIsNone(row["tax_period"])
        self.assertIsNone(row["amount"])
        self.assertEqual(row["risk_status"], "无")
        certified_only = self.service.list_payload({"status": "certified", "selection_month": "2026-10"})
        self.assertEqual([row["id"] for row in certified_only["rows"]], [older])
        self.assertEqual(certified_only["summary"]["uncertified"]["count"], 0)
        self.assertEqual(self.service.list_payload({"issue_month": "2026-10"})["total"], 0)
        self.assertEqual(self.service.list_payload({"selection_month": "2025-01"})["total"], 0)

    def test_literal_search_sort_pagination_export_share_current_filtered_result(self):
        first = self.invoice(day="2026-01-01", seller="精确_%来源")
        second = self.invoice(day="2026-02-01", seller="精确_%来源")
        self.invoice(seller="精确其他来源")
        filters = {"search": "_%", "sort_by": "issue_date", "sort_direction": "asc", "page_size": 1, "page": 2}
        payload = self.service.list_payload(filters)
        self.assertEqual(payload["total"], 2)
        self.assertEqual([row["id"] for row in payload["rows"]], [second])
        self.assertEqual(payload["summary"]["uncertified"]["amount"], "200.00")
        _, content = TaxOffsetExportService(query_service=self.service).export(filters, ["digital_invoice_no", "amount"])
        workbook = load_workbook(BytesIO(content))
        self.assertEqual(list(workbook.active.values)[1:], [(first, 100), (second, 100)])
        workbook.close()
        self.assertEqual(self.service.list_payload({"search": "' or 1=1--"})["total"], 0)

    def test_matching_requires_strong_identity_buyer_and_special_invoice_scope(self):
        invoice = self.invoice(digital="DIG", code="CODE", number="NUMBER")
        ordinary = self.invoice(kind="普通发票", digital="ORDINARY")
        self.assertTrue(ordinary)
        rows = [
            {"unique_key": "strong", "digital_invoice_no": "DIG", "buyer_tax_no": "BUYER"},
            {"unique_key": "buyer-mismatch", "digital_invoice_no": "DIG", "buyer_tax_no": "OTHER"},
            {"unique_key": "buyer-missing", "digital_invoice_no": "DIG"},
            {"unique_key": "no-fallback", "digital_invoice_no": "WRONG", "invoice_code": "CODE", "invoice_no": "NUMBER", "buyer_tax_no": "BUYER"},
            {"unique_key": "pair", "invoice_code": "CODE", "invoice_no": "NUMBER", "buyer_tax_no": "BUYER"},
            {"unique_key": "weak", "invoice_no": "NUMBER", "buyer_tax_no": "BUYER"},
            {"unique_key": "ordinary", "digital_invoice_no": "ORDINARY", "buyer_tax_no": "BUYER"},
        ]
        matched = self.repo.match_certified_rows(rows)
        self.assertEqual(matched["strong"]["matched_invoice_id"], invoice)
        self.assertEqual(matched["pair"]["matched_invoice_id"], invoice)
        for key in ("buyer-mismatch", "buyer-missing", "no-fallback", "weak", "ordinary"):
            self.assertEqual(matched[key]["match_status"], "outside_invoices")

    def test_read_snapshot_prevents_rows_summary_race(self):
        invoice = self.invoice(amount="100")
        connection = self.connection
        @contextmanager
        def transaction():
            with connection.transaction() as tx:
                def fetch_all(sql, params=()):
                    result = tx.fetch_all(sql, params)
                    if "group by certification_status" in sql:
                        with connection.transaction() as writer:
                            writer.execute("set local fin_ops.correction_reason='isolated certification snapshot test'")
                            writer.execute("update app.invoices set amount=999,signed_amount=999 where id=%s::uuid", (invoice,))
                    return result
                yield SimpleNamespace(execute=tx.execute, fetch_all=fetch_all, fetch_one=tx.fetch_one)
        service = TaxOffsetQueryService(canonical_repository=PostgresTaxOffsetCanonicalRepository(SimpleNamespace(transaction=transaction)))
        payload = service.list_payload({})
        self.assertEqual(payload["rows"][0]["amount"], "100.00")
        self.assertEqual(payload["summary"]["uncertified"]["amount"], "100.00")
        self.assertEqual(self.service.list_payload({})["rows"][0]["amount"], "999.00")

    def test_revocation_and_normal_invoice_deletion_preserve_evidence_and_unresolved_is_reported(self):
        invoice = self.invoice()
        self.certify(invoice)
        self.connection.execute("update app.tax_certified_import_records set status='revoked'")
        self.assertEqual(self.service.list_payload({})["rows"][0]["certification_status"], "uncertified")
        self.connection.execute("update app.tax_certified_import_records set status='active'")
        self.connection.execute("update app.invoices set status='deleted' where id=%s::uuid", (invoice,))
        self.assertEqual(self.service.list_payload({})["total"], 0)
        self.assertEqual(audit_tax_offset_page(self.connection)["overall_status"], "pass")
        self.connection.execute("""insert into app.tax_certified_import_records(certified_unique_key,status,match_status)
                                  values('unresolved','active','unresolved'),('unknown-status','待核对','unresolved'),
                                        ('revoked-evidence','revoked','unresolved')""")
        self.assertEqual(self.service.list_payload({"issue_month": "2030-01"})["unresolved_record_count"], 2)
        report = audit_tax_offset_page(self.connection)
        self.assertEqual(report["summary"]["unresolved_record_count"], 2)
        self.assertIn("tax_offset_unresolved_certification", report["summary"]["issue_sample_counts_by_code"])

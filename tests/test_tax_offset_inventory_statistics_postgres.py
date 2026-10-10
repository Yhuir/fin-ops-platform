from __future__ import annotations

import unittest

from fin_ops_platform.services.invoice_kind import INVOICE_KIND_NAMES
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.tax_offset import PostgresTaxOffsetCanonicalRepository
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQueryService
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class TaxInventoryStatisticsPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = require_postgres_test_database_url()
        apply_test_migrations(cls.dsn)

    def setUp(self):
        truncate_test_database(self.dsn)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.dsn, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.service = TaxOffsetQueryService(canonical_repository=PostgresTaxOffsetCanonicalRepository(self.connection))
        self.sequence = 0

    def invoice(self, code, *, invoice_type="input", status="pending", red=False, nested=True, year="2026"):
        self.sequence += 1
        raw = {"invoice_kind_code": code, "source_links": [{"source_id": "first"}, {"source_id": "second"}]}
        payload = {"normalized_payload": raw} if nested else raw
        amount = -100 if red else 100
        self.connection.execute("""insert into app.invoices(invoice_type,invoice_no,digital_invoice_no,
            buyer_tax_no,invoice_date,invoice_month,amount,signed_amount,tax_amount,total_with_tax,status,raw_payload)
            values(%s,%s,%s,'BUYER',%s::date,%s::date,%s,%s,%s,%s,%s,%s)""",
            (invoice_type, str(self.sequence), str(self.sequence), f"{year}-09-24", f"{year}-09-01",
             amount, amount, amount * 13 // 100, amount * 113 // 100, status, jsonb(payload)))

    def test_empty_inventory_returns_explicit_zero_counts(self):
        result = self.service.list_payload({})
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["rows"], [])
        self.assertEqual(result["inventory_statistics"], {
            "input_invoice_count": 0, "special_invoice_count": 0, "general_invoice_count": 0,
            "toll_invoice_count": 0, "other_invoice_count": 0, "unclassified_invoice_count": 0})

    def test_every_kind_unknown_red_and_duplicate_sources_partition_without_deleted_or_output(self):
        for code in INVOICE_KIND_NAMES:
            self.invoice(code, nested=code != "rail_ticket")
        for code in (None, "", "future_kind"):
            self.invoice(code)
        self.invoice("vat_special", red=True)
        self.invoice("vat_special", status="deleted")
        self.invoice("vat_general", invoice_type="output")
        result = self.service.list_payload({})
        self.assertEqual(result["inventory_statistics"], {
            "input_invoice_count": 11, "special_invoice_count": 2, "general_invoice_count": 1,
            "toll_invoice_count": 1, "other_invoice_count": 4, "unclassified_invoice_count": 3})
        self.assertEqual(result["total"], 2)
        self.assertEqual(len(result["rows"]), 2)
        self.assertEqual(result["summary"]["uncertified"]["amount"], "0.00")

    def test_filters_and_export_keep_their_special_scope_without_changing_inventory(self):
        self.invoice("vat_special", year="2025")
        self.invoice("vat_special")
        self.invoice("toll")
        baseline = self.service.list_payload({})["inventory_statistics"]
        for filters, expected in (({"issue_year": "2025"}, 1), ({"issue_month": "2026-09"}, 1),
                                  ({"status": "certified"}, 0), ({"selection_year": "2026"}, 0),
                                  ({"selection_month": "2026-09"}, 0), ({"search": "absent"}, 0),
                                  ({"page": 2, "page_size": 1, "sort_direction": "asc"}, 2)):
            with self.subTest(filters=filters):
                result = self.service.list_payload(filters)
                self.assertEqual(result["inventory_statistics"], baseline)
                self.assertEqual(result["total"], expected)
        exported = self.service.export_rows({"issue_year": "2025"}, limit=20001)
        self.assertEqual(exported["total"], 1)
        self.assertEqual(len(exported["rows"]), 1)
        self.assertNotIn("inventory_statistics", exported)

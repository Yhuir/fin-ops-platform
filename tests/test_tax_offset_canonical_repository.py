from __future__ import annotations

import unittest
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal

from fin_ops_platform.services.postgres_repositories.tax_offset import PostgresTaxOffsetCanonicalRepository
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQuery


class FakeConnection:
    def __init__(self, count=21):
        self.count = count
        self.commands = []
        self.queries = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def execute(self, sql, params=()):
        self.commands.append(sql)

    def fetch_one(self, sql, params=()):
        self.queries.append((sql, params))
        return {"count": 2}

    def fetch_all(self, sql, params=()):
        self.queries.append((sql, params))
        if "group by certification_status" in sql:
            return [{"certification_status": "certified", "count": self.count, "amount": None,
                     "tax_amount": Decimal("0"), "deductible_tax_amount": Decimal("1.234567"),
                     "missing_amount_count": 1, "missing_tax_count": 0, "missing_deductible_tax_count": 0}]
        return [{"id": "invoice-id", "digital_invoice_no": "001234567890123456789", "invoice_code": None,
                 "invoice_no": None, "issue_date": date(2026, 9, 1), "seller_name": "源销方", "seller_tax_no": "000123",
                 "amount": None, "tax_amount": Decimal("0"), "deductible_tax_amount": Decimal("1.234567"),
                 "selection_time": datetime(2026, 10, 1, 10, 30), "certification_status": "certified", "tax_period": None,
                 "invoice_source_fields": {"invoice_kind": "数电票(专用发票)"},
                 "certification_source_fields": {"source_fields": {"risk_status": "无", "amount": "999"}}}]


class TaxOffsetCanonicalRepositoryTests(unittest.TestCase):
    def test_pagination_and_summary_share_snapshot_filters_and_preserve_source_nulls(self):
        connection = FakeConnection()
        query = TaxOffsetQuery.parse({"status": "certified", "issue_month": "2026-09", "selection_month": "2026-10",
                                      "search": "a_%", "page": 2, "page_size": 20, "sort_by": "selection_time"})
        payload = PostgresTaxOffsetCanonicalRepository(connection).load_page(query)
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(connection.commands, ["set transaction isolation level repeatable read read only"])
        self.assertEqual(len(connection.queries), 3)
        self.assertEqual(connection.queries[0][1], connection.queries[1][1][:-2])
        self.assertEqual(connection.queries[1][1][-2:], (20, 20))
        sql = connection.queries[1][0]
        self.assertIn("c.id is not null", sql)
        self.assertIn("selection_time desc nulls last, id asc", sql)
        self.assertNotIn("tax_offset_plans", sql)
        self.assertNotIn("read_model", sql)
        self.assertEqual(payload["rows"][0]["sequence"], 21)
        self.assertIsNone(payload["rows"][0]["amount"])
        self.assertEqual(payload["rows"][0]["tax_amount"], "0.00")
        self.assertEqual(payload["rows"][0]["deductible_tax_amount"], "1.234567")
        self.assertEqual(payload["rows"][0]["risk_status"], "无")
        self.assertEqual(payload["summary"]["certified"]["missing_amount_count"], 1)
        self.assertIsNone(payload["summary"]["certified"]["amount"])
        self.assertEqual(payload["total"], 21)
        self.assertEqual(payload["unresolved_record_count"], 2)

    def test_out_of_range_page_clamps_inside_snapshot(self):
        connection = FakeConnection(count=1)
        payload = PostgresTaxOffsetCanonicalRepository(connection).load_page(TaxOffsetQuery(page=2, page_size=20))
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["total"], 1)
        self.assertEqual(connection.queries[1][1][-2:], (20, 0))
        self.assertEqual(payload["rows"][0]["sequence"], 1)

    def test_export_ignores_page_and_matching_never_uses_amount_or_name(self):
        connection = FakeConnection()
        repo = PostgresTaxOffsetCanonicalRepository(connection)
        repo.load_page(TaxOffsetQuery(page=4), limit_override=20001)
        self.assertEqual(connection.queries[-2][1][-2:], (20001, 0))
        self.assertEqual(repo.match_certified_rows([]), {})
        class MatchConnection:
            def fetch_all(self, sql, params):
                self.sql = sql
                return [{"unique_key": "digital:1", "invoice_ids": ["one"]},
                        {"unique_key": "digital:2", "invoice_ids": ["one", "two"]},
                        {"unique_key": "digital:3", "invoice_ids": None}]
        matching = MatchConnection()
        result = PostgresTaxOffsetCanonicalRepository(matching).match_certified_rows(
            [{"unique_key": "digital:1", "digital_invoice_no": "1", "buyer_tax_no": "buyer"}])
        self.assertEqual(result["digital:1"], {"match_status": "matched_invoice", "matched_invoice_id": "one"})
        self.assertEqual(result["digital:2"]["match_status"], "ambiguous")
        self.assertEqual(result["digital:3"]["match_status"], "outside_invoices")
        self.assertNotIn("i.amount", matching.sql)
        self.assertNotIn("i.seller_name", matching.sql)
        self.assertIn("i.buyer_tax_no = r.buyer_tax_no", matching.sql)

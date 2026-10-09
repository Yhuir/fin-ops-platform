from __future__ import annotations

import unittest
from copy import deepcopy

from fin_ops_platform.services.invoice_source_attribute_repair import build_source_attribute_repair_plan
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.invoice_source_attribute_repair import apply_updates, load_snapshot
from fin_ops_platform.services.postgres_repositories.tax_offset import PostgresTaxOffsetCanonicalRepository
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQueryService
from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class InvoiceKindRepairPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = require_postgres_test_database_url()
        apply_test_migrations(cls.dsn)

    def setUp(self):
        truncate_test_database(self.dsn)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.dsn, pool_enabled=False))
        self.addCleanup(self.connection.close)
        payload = {
            "normalized_payload": {
                "invoice_kind": None,
                "amount": "100",
                "tax_amount": "13",
                "total_with_tax": "113",
                "source_links": [{"source_id": "retained"}],
            }
        }
        self.id = self.connection.fetch_one(
            """insert into app.invoices(invoice_type,invoice_no,digital_invoice_no,
            buyer_tax_no,invoice_date,invoice_month,amount,signed_amount,tax_amount,total_with_tax,status,raw_payload)
            values('input','26532000000000000001','26532000000000000001','BUYER','2026-09-24',
            '2026-09-01',100,100,13,113,'pending',%s) returning id::text as id""",
            (jsonb(payload),),
        )["id"]
        self.source = {
            "file_id": "file-1",
            "sha256": "a" * 64,
            "source_kind": "invoice_export",
            "invoice_ids": [self.id],
            "rows": [
                {
                    "digital_invoice_no": "26532000000000000001",
                    "buyer_tax_no": "BUYER",
                    "invoice_date": "2026-09-24",
                    "invoice_kind": "电子发票（增值税专用发票）",
                }
            ],
        }
        self.query = TaxOffsetQueryService(canonical_repository=PostgresTaxOffsetCanonicalRepository(self.connection))

    def test_repair_query_summary_and_repeat_preserve_all_financial_facts(self):
        before = self.connection.fetch_one("select * from app.invoices where id=%s::uuid", (self.id,))
        self.assertEqual(self.query.list_payload({})["total"], 0)
        with self.connection.transaction() as tx:
            snapshot = load_snapshot(tx, lock=True)
            plan = build_source_attribute_repair_plan(snapshot, [self.source], [])
            apply_updates(tx, plan["updates"])
        result = self.query.list_payload({})
        self.assertEqual(result["total"], 1)
        self.assertEqual(result["summary"]["uncertified"]["tax_amount"], "13.00")
        after = self.connection.fetch_one("select * from app.invoices where id=%s::uuid", (self.id,))
        for field in (
            "id",
            "invoice_no",
            "digital_invoice_no",
            "invoice_date",
            "buyer_tax_no",
            "amount",
            "signed_amount",
            "tax_amount",
            "total_with_tax",
            "source_links",
            "status",
        ):
            self.assertEqual(before[field], after[field])
        repeat = build_source_attribute_repair_plan(load_snapshot(self.connection), [self.source], [])
        self.assertEqual(repeat["update_count"], 0)

    def test_stale_version_rolls_back_every_write(self):
        before = load_snapshot(self.connection)
        plan = build_source_attribute_repair_plan(before, [self.source], [])
        stale = deepcopy(plan["updates"][0])
        stale["before"]["raw_payload"]["normalized_payload"]["invoice_kind"] = "stale"
        with self.assertRaisesRegex(RuntimeError, "Concurrent"):
            with self.connection.transaction() as tx:
                apply_updates(tx, [plan["updates"][0], stale])
        self.assertEqual(load_snapshot(self.connection), before)
        self.assertEqual(self.query.list_payload({})["total"], 0)

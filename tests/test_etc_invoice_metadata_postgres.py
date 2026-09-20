from __future__ import annotations

import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event

from fin_ops_platform.services.import_audit_repair_service import build_etc_invoice_payload_repair_plan
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.import_audit_repair import load_etc_invoice_payload_repair_snapshot

from tests.postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database
from tests.test_etc_invoice_metadata import etc_invoice, formal_invoice


class EtcInvoiceMetadataPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.url = require_postgres_test_database_url()
        apply_test_migrations(cls.url)

    def setUp(self):
        truncate_test_database(self.url)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.repository = PostgresCoreRepository(self.connection)
        self.invoice = formal_invoice()
        self.repository.save_invoices([self.invoice])
        ImportNormalizationService(existing_invoices=[self.invoice]).upsert_etc_invoice(etc_invoice())

    def row(self):
        return self.connection.fetch_one("select * from app.invoices where legacy_mongo_id='formal-1'")

    def test_metadata_preserves_financial_facts_and_concurrent_source_links(self):
        ready, release = Event(), Event()
        manual_link = {"source_type": "oa_expense_item_invoice", "source_id": "oa-1:item-1", "batch_id": "oa-1"}

        def assign():
            with self.connection.transaction() as tx:
                tx.fetch_all("select id from app.invoices where legacy_mongo_id='formal-1' for update")
                tx.execute(
                    "update app.invoices set source_links=source_links || %s::jsonb where legacy_mongo_id='formal-1'",
                    (jsonb([manual_link]),),
                )
                ready.set()
                if not release.wait(5):
                    raise AssertionError("Metadata concurrency test did not release its writer.")

        with ThreadPoolExecutor(max_workers=2) as pool:
            first = pool.submit(assign)
            self.assertTrue(ready.wait(5))
            second = pool.submit(self.repository.save_invoice_etc_metadata, [self.invoice])
            release.set()
            first.result(timeout=10)
            second.result(timeout=10)
        row = self.row()
        self.assertIsNone(row["tax_rate"])
        self.assertIsNone(row["raw_payload"]["normalized_payload"]["tax_rate"])
        self.assertEqual(row["legacy_source_batch_id"], "manual-batch")
        self.assertEqual(
            {x["source_type"] for x in row["source_links"]},
            {"manual_invoice_import", "oa_expense_item_invoice", "etc_invoice_import"},
        )
        self.assertEqual(row["source_links"], row["raw_payload"]["normalized_payload"]["source_links"])
        self.repository.save_invoice_etc_metadata([self.invoice])
        self.assertEqual(self.row(), row)

    def test_missing_target_rolls_back_entire_batch(self):
        missing = deepcopy(self.invoice)
        missing.id = "missing"
        before = self.row()
        with self.assertRaisesRegex(ValueError, "no longer exists"):
            self.repository.save_invoice_etc_metadata([self.invoice, missing])
        self.assertEqual(self.row(), before)

    def test_repair_snapshot_reads_original_import_and_etc_evidence(self):
        self.repository.save_invoice_etc_metadata([self.invoice])
        self.connection.execute(
            "insert into app.etc_invoices(legacy_mongo_id,etc_invoice_id,status,raw_payload) values ('etc-1','etc-1','submitted',%s)",
            (jsonb({"normalized_payload": {"tax_rate": "0.03"}}),),
        )
        self.connection.execute(
            "insert into app.import_batch_rows(legacy_batch_id,row_no,source_record_type,decision,linked_object_id,raw_payload) values ('manual-batch',1,'invoice','created','formal-1',%s)",
            (jsonb({"normalized_payload": {"normalized_row": {"tax_rate": None}}}),),
        )
        self.connection.execute(
            "update app.invoices set raw_payload=jsonb_set(raw_payload, '{normalized_payload,tax_rate}', '\"0.03\"'::jsonb) where legacy_mongo_id='formal-1'"
        )
        rows = load_etc_invoice_payload_repair_snapshot(self.connection, ["formal-1"])
        self.assertEqual(len(rows), 1)
        plan = build_etc_invoice_payload_repair_plan(rows)
        self.assertEqual(plan["unresolved_invoice_ids"], [])
        self.assertEqual(len(plan["updates"]), 1)
        self.assertEqual(load_etc_invoice_payload_repair_snapshot(self.connection, []), rows)

    def test_repair_is_local_and_conflict_rolls_back(self):
        self.connection.execute(
            "update app.invoices set raw_payload=jsonb_set(raw_payload, '{normalized_payload,tax_rate}', '\"0.03\"'::jsonb) where legacy_mongo_id='formal-1'"
        )
        before = self.row()
        delta = {"invoice_id": "formal-1", "before_payload": before["raw_payload"]}
        with self.assertRaisesRegex(RuntimeError, "changed after preview"):
            with self.connection.transaction() as tx:
                self.repository.repair_etc_invoice_payload(tx, [delta, {"invoice_id": "missing", "before_payload": {}}])
        self.assertEqual(self.row(), before)
        with self.connection.transaction() as tx:
            self.assertEqual(self.repository.repair_etc_invoice_payload(tx, [delta]), 1)
        after = self.row()
        self.assertIsNone(after["raw_payload"]["normalized_payload"]["tax_rate"])
        self.assertEqual(after["total_with_tax"], before["total_with_tax"])
        self.assertEqual(after["source_links"], before["source_links"])

from __future__ import annotations

import json
from pathlib import Path
import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)


class InvoiceProvenancePostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0133")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def test_0134_restores_all_manual_import_edges_without_losing_oa_source(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.import_batches(
                legacy_mongo_id, batch_type, source_name, imported_by, row_count,
                success_count, duplicate_count, status, imported_at
            ) values
                ('batch_import_0042', 'input_invoice', 'first.xlsx', 'tester', 1, 1, 0, 'completed', now()),
                ('batch_import_0127', 'input_invoice', 'second.xlsx', 'tester', 1, 0, 1, 'completed', now());

            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, digital_invoice_no,
                source_unique_key, invoice_date, invoice_month, amount, signed_amount, currency,
                status, tags, source_links, raw_payload
            ) values (
                'inv_imported_0788', 'input', '26532000001017882406',
                '26532000001017882406', '26532000001017882406', '2026-06-29', '2026-06-01',
                482, 482, 'CNY', 'pending', array['OA附件'],
                '[{
                    "source_type":"oa_attachment_invoice",
                    "source_id":"oa-exp-2321:meal.pdf",
                    "derived_from_oa_id":"oa-exp-2321",
                    "source_expense_item_id":"oa-exp-2321:item:1"
                }]'::jsonb,
                '{
                    "normalized_payload":{
                        "id":"oa-att-inv-stale",
                        "source_unique_key":"26532000001017882406",
                        "tags":["OA附件"],
                        "source_links":[{
                            "source_type":"oa_attachment_invoice",
                            "source_id":"oa-exp-2321:meal.pdf",
                            "derived_from_oa_id":"oa-exp-2321",
                            "source_expense_item_id":"oa-exp-2321:item:1"
                        }]
                    }
                }'::jsonb
            );

            insert into app.import_batch_rows(
                legacy_mongo_id, import_batch_id, legacy_batch_id, row_no,
                source_record_type, source_unique_key, decision, linked_object_type,
                linked_object_id, raw_payload
            )
            select
                'row_' || batch.legacy_mongo_id,
                batch.id,
                batch.legacy_mongo_id,
                1,
                'invoice',
                '26532000001017882406',
                case when batch.legacy_mongo_id = 'batch_import_0042' then 'created' else 'duplicate_skipped' end,
                'invoice',
                'inv_imported_0788',
                '{"normalized_payload":{"normalized_row":{}}}'::jsonb
            from app.import_batches batch;
            """,
        )

        apply_test_migrations_through(self.database_url, "0134")

        row = json.loads(
            fetch_scalar(
                self.database_url,
                """
                select jsonb_build_object(
                    'legacy_source_batch_id', legacy_source_batch_id,
                    'typed_batch_id', source_batch_id::text,
                    'owner_batch_id', (
                        select id::text from app.import_batches
                        where legacy_mongo_id = 'batch_import_0042'
                    ),
                    'tags', to_jsonb(tags),
                    'source_links', source_links,
                    'raw_id', raw_payload->'normalized_payload'->>'id',
                    'raw_source_batch_id', raw_payload->'normalized_payload'->>'source_batch_id',
                    'raw_tags', raw_payload->'normalized_payload'->'tags',
                    'raw_source_links', raw_payload->'normalized_payload'->'source_links'
                )::text
                from app.invoices
                where legacy_mongo_id = 'inv_imported_0788';
                """,
            )
        )
        manual_links = [
            link for link in row["source_links"] if link["source_type"] == "manual_invoice_import"
        ]
        self.assertEqual(len(row["source_links"]), 3)
        self.assertEqual(
            {(link["batch_id"], link["source_id"]) for link in manual_links},
            {
                ("batch_import_0042", "26532000001017882406"),
                ("batch_import_0127", "26532000001017882406"),
            },
        )
        self.assertEqual(row["legacy_source_batch_id"], "batch_import_0042")
        self.assertEqual(row["typed_batch_id"], row["owner_batch_id"])
        self.assertEqual(row["raw_id"], "inv_imported_0788")
        self.assertEqual(row["raw_source_batch_id"], "batch_import_0042")
        self.assertEqual(row["tags"], ["OA附件", "人工导入"])
        self.assertEqual(row["raw_tags"], row["tags"])
        self.assertEqual(row["raw_source_links"], row["source_links"])
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from audit.events where actor_id = 'migration:0134';",
            ),
            "1",
        )

        migration_sql = Path(
            "backend/src/fin_ops_platform/postgres/migrations/0134_restore_invoice_import_provenance.sql"
        ).read_text(encoding="utf-8")
        migrate.run_psql(self.database_url, sql=migration_sql)
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select count(*)
                from app.invoices invoice
                cross join lateral jsonb_array_elements(invoice.source_links) link
                where invoice.legacy_mongo_id = 'inv_imported_0788'
                  and link->>'source_type' = 'manual_invoice_import';
                """,
            ),
            "2",
        )
        self.assertEqual(
            fetch_scalar(
                self.database_url,
                "select count(*) from audit.events where actor_id = 'migration:0134';",
            ),
            "1",
        )


if __name__ == "__main__":
    unittest.main()

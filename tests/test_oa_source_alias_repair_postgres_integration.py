from __future__ import annotations

from pathlib import Path
import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)


MIGRATION_SQL = (
    Path(__file__).resolve().parents[1]
    / "backend/src/fin_ops_platform/postgres/migrations/0153_oa_source_alias_attachment_identity_repair.sql"
).read_text(encoding="utf-8")


class OASourceAliasRepairPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0152")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def test_0153_bridges_immutable_legacy_invoice_items_to_current_oa_items(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            with canonical_oa as (
                insert into app.oa_applications(
                    oa_source_id, form_id, row_id, status
                ) values (
                    'source-current', 'daily-expense',
                    'oa-exp-6a86a63777bca2d0c5f62d07', 'active'
                )
                returning id
            ), current_items as (
                insert into app.oa_application_items(
                    oa_application_id, oa_source_id, form_id, row_id, item_type, item_no, amount
                )
                select id, 'source-current', 'daily-expense',
                       'oa-exp-6a86a63777bca2d0c5f62d07:item:0:f45376305de2',
                       'expense', '0', 145
                from canonical_oa
                union all
                select id, 'source-current', 'daily-expense',
                       'oa-exp-6a86a63777bca2d0c5f62d07:item:1:32417101b6eb',
                       'expense', '1', 145
                from canonical_oa
            )
            insert into app.oa_attachments(
                oa_application_id, oa_source_id, form_id, row_id,
                source_attachment_key, filename, normalized_payload
            )
            select id, 'source-current', 'daily-expense', 'attachment-0',
                   'owned-attachment-0', 'invoice-0.pdf', '{}'::jsonb
            from canonical_oa
            union all
            select id, 'source-current', 'daily-expense', 'attachment-1',
                   'owned-attachment-1', 'invoice-1.pdf', '{}'::jsonb
            from canonical_oa;

            insert into app.oa_attachment_invoice_cache(
                source_attachment_key, parser_version, cache_schema_version,
                parsed_at, evidences, invoices, artifacts
            ) values
                ('cache-attachment-0', 'test', 'test', now(), '[]', '[]', '[]'),
                ('cache-attachment-1', 'test', 'test', now(), '[]', '[]', '[]');

            insert into app.oa_attachment_invoice_cache_sources(
                cache_source_attachment_key, source_attachment_key, source_kind,
                source_expense_item_id, source_expense_row_index, source_attachment_name
            ) values
                (
                    'cache-attachment-0', 'owned-attachment-0', 'invoice',
                    'oa-exp-6a86a63777bca2d0c5f62d07:item:0:f45376305de2', '0', 'invoice-0.pdf'
                ),
                (
                    'cache-attachment-1', 'owned-attachment-1', 'invoice',
                    'oa-exp-6a86a63777bca2d0c5f62d07:item:1:32417101b6eb', '1', 'invoice-1.pdf'
                );

            insert into app.invoices(
                legacy_mongo_id, invoice_type, invoice_no, source_unique_key,
                invoice_date, invoice_month, amount, signed_amount, currency,
                workbench_visibility, status, tags, source_links
            ) values
                (
                    'inv_imported_0898', 'input', 'invoice-0898', 'invoice-0898',
                    '2026-07-02', '2026-07-01', 145, 145, 'CNY', 'visible', 'pending',
                    array['OA附件'],
                    '[{"source_type":"oa_attachment_invoice","source_expense_item_id":"oa-exp-2327:item:0:d91d8bb509c9","source_expense_row_index":"0","source_attachment_key":"cache-attachment-0"}]'::jsonb
                ),
                (
                    'inv_imported_0899', 'input', 'invoice-0899', 'invoice-0899',
                    '2026-07-02', '2026-07-01', 145, 145, 'CNY', 'visible', 'pending',
                    array['OA附件'],
                    '[{"source_type":"oa_attachment_invoice","source_expense_item_id":"oa-exp-2327:item:1:a48a5229fa61","source_expense_row_index":"1","source_attachment_key":"cache-attachment-1"}]'::jsonb
                );
            """,
        )

        migrate.run_psql(self.database_url, sql=MIGRATION_SQL)

        self.assertEqual(
            fetch_scalar(
                self.database_url,
                """
                select concat_ws('|', alias_row_id, canonical_row_id, status, reviewed_by,
                                 raw_payload->>'contract')
                from app.oa_source_aliases
                where alias_row_id = 'oa-exp-2327';
                """,
            ),
            "oa-exp-2327|oa-exp-6a86a63777bca2d0c5f62d07|active|system:migration:0153|oa-source-alias-attachment-identity-repair-v2",
        )


if __name__ == "__main__":
    unittest.main()

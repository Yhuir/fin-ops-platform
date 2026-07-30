from __future__ import annotations

import unittest

from fin_ops_platform.postgres import migrate
from tests.postgres_test_utils import (
    apply_test_migrations_through,
    fetch_scalar,
    require_postgres_test_database_url,
    reset_test_database,
)


class CanonicalFinanceDomainContractsPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        reset_test_database(self.database_url)
        apply_test_migrations_through(self.database_url, "0129")

    def tearDown(self) -> None:
        reset_test_database(self.database_url)

    def test_contracts_preserve_history_and_reject_new_invalid_facts(self) -> None:
        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.invoices(
                invoice_type, invoice_no, invoice_date, amount, signed_amount, status
            ) values ('input', 'historical-invalid-month', date '2026-05-10', 1, 1, 'active');

            insert into app.bank_transactions(
                account_no, txn_direction, counterparty_name_raw, amount, signed_amount, status
            ) values ('0001', 'sideways', 'historical-invalid-direction', 1, 1, 'active');

            insert into app.workbench_pair_relations(
                case_id, relation_mode, status
            ) values ('historical-empty-relation', 'manual', 'active');

            insert into job.background_jobs(
                job_id, job_type, status, affected_months
            ) values ('historical-invalid-month', 'test', 'done', array['2026-13']);
            """,
        )

        apply_test_migrations_through(self.database_url, "0130")

        constraint_state = fetch_scalar(
            self.database_url,
            """
            select
                count(*) filter (where not convalidated)::text
                || '/'
                || count(*)::text
            from pg_constraint
            where conname = any(array[
                'invoices_canonical_date_month_chk',
                'invoices_source_links_array_chk',
                'invoices_raw_payload_object_chk',
                'bank_transactions_direction_chk',
                'bank_transactions_canonical_date_month_chk',
                'bank_transactions_text_fields_array_chk',
                'bank_transactions_raw_payload_object_chk',
                'workbench_pair_relations_version_chk',
                'workbench_pair_relations_month_scope_chk',
                'workbench_pair_relations_row_cardinality_chk',
                'workbench_pair_relations_row_values_chk',
                'workbench_pair_relations_json_objects_chk',
                'background_jobs_affected_months_chk',
                'background_jobs_json_objects_chk'
            ]);
            """,
        )
        self.assertEqual(constraint_state, "14/14")

        invalid_writes = {
            "invoice_missing_month": """
                insert into app.invoices(
                    invoice_type, invoice_no, invoice_date, amount, signed_amount, status
                ) values ('input', 'invalid-missing-month', date '2026-05-10', 1, 1, 'active');
            """,
            "invoice_source_links_shape": """
                insert into app.invoices(
                    invoice_type, invoice_no, amount, signed_amount, status, source_links
                ) values ('input', 'invalid-links', 1, 1, 'active', '{}'::jsonb);
            """,
            "invoice_raw_payload_shape": """
                insert into app.invoices(
                    invoice_type, invoice_no, amount, signed_amount, status, raw_payload
                ) values ('input', 'invalid-raw', 1, 1, 'active', '[]'::jsonb);
            """,
            "bank_direction": """
                insert into app.bank_transactions(
                    account_no, txn_direction, counterparty_name_raw, amount, signed_amount, status
                ) values ('0002', 'sideways', 'invalid-direction', 1, 1, 'active');
            """,
            "bank_missing_month": """
                insert into app.bank_transactions(
                    account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
                    txn_date, status
                ) values ('0002', 'inflow', 'invalid-month', 1, 1, date '2026-05-10', 'active');
            """,
            "bank_text_fields_shape": """
                insert into app.bank_transactions(
                    account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
                    bank_text_fields, status
                ) values ('0002', 'inflow', 'invalid-fields', 1, 1, '{}'::jsonb, 'active');
            """,
            "bank_raw_payload_shape": """
                insert into app.bank_transactions(
                    account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
                    raw_payload, status
                ) values ('0002', 'inflow', 'invalid-raw', 1, 1, '[]'::jsonb, 'active');
            """,
            "relation_version": """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, version, row_ids, row_types
                ) values ('invalid-version', 'manual', 'active', 0, array['bank-1'], array['bank']);
            """,
            "relation_scope": """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, month_scope, row_ids, row_types
                ) values (
                    'invalid-scope', 'manual', 'active', date '2026-05-02',
                    array['bank-1'], array['bank']
                );
            """,
            "relation_empty": """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status
                ) values ('invalid-empty', 'manual', 'active');
            """,
            "relation_blank": """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, row_ids, row_types
                ) values ('invalid-blank', 'manual', 'active', array['   '], array['bank']);
            """,
            "relation_json_shape": """
                insert into app.workbench_pair_relations(
                    case_id, relation_mode, status, row_ids, row_types, amount_check
                ) values (
                    'invalid-json', 'manual', 'active',
                    array['bank-1'], array['bank'], '[]'::jsonb
                );
            """,
            "background_month": """
                insert into job.background_jobs(
                    job_id, job_type, status, affected_months
                ) values ('invalid-month', 'test', 'done', array['2026-13']);
            """,
            "background_json_shape": """
                insert into job.background_jobs(
                    job_id, job_type, status, progress
                ) values ('invalid-json', 'test', 'done', '[]'::jsonb);
            """,
        }
        for case_name, sql in invalid_writes.items():
            with self.subTest(case_name=case_name), self.assertRaises(migrate.MigrationError):
                migrate.run_psql(self.database_url, sql=sql)

        migrate.run_psql(
            self.database_url,
            sql="""
            insert into app.invoices(
                invoice_type, invoice_no, invoice_date, invoice_month,
                amount, signed_amount, status
            ) values (
                'input', 'valid-invoice', date '2026-05-10', date '2026-05-01',
                1, 1, 'active'
            );
            insert into app.bank_transactions(
                account_no, txn_direction, counterparty_name_raw, amount, signed_amount,
                txn_date, txn_month, status
            ) values (
                '0003', 'outflow', 'valid-bank', 1, -1,
                date '2026-05-10', date '2026-05-01', 'active'
            );
            insert into app.workbench_pair_relations(
                case_id, relation_mode, status, month_scope, row_ids, row_types
            ) values (
                'valid-relation', 'manual', 'active', date '2026-05-01',
                array['bank-1'], array['bank']
            );
            insert into job.background_jobs(
                job_id, job_type, status, affected_months
            ) values ('valid-job', 'test', 'done', array['2026-05']);
            """,
        )


if __name__ == "__main__":
    unittest.main()

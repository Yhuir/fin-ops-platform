from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class BatchAccountingPostgresIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self) -> None:
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.repository = PostgresReadModelRepository(self.connection)

    def test_bulk_relation_proof_executes_with_real_postgres(self) -> None:
        self.connection.execute(
            """
            insert into read_model.workbench_relation_scopes(
                tenant_id, scope_key, scope_month, row_count, group_count, source_versions
            )
            select
                'default',
                '2026-' || lpad(month_number::text, 2, '0'),
                make_date(2026, month_number, 1),
                case when month_number = 1 then 1 else 0 end,
                case when month_number = 1 then 1 else 0 end,
                '{"workbench_relation_schema_version":"bulk-v1"}'::jsonb
            from generate_series(1, 12) month_number
            """
        )
        self.connection.execute(
            """
            insert into read_model.workbench_relation_groups(
                tenant_id, group_id, scope_key, scope_month, relation_source,
                relation_kind, relation_status, oa_row_ids, bank_transaction_ids,
                source_versions, payload
            )
            values (
                'default', 'CASE-BATCH-1', '2026-01', '2026-01-01', 'manual',
                'oa_bank', 'linked', array['oa-batch-1'], array['txn-batch-1'],
                '{"workbench_relation_schema_version":"bulk-v1"}'::jsonb,
                '{
                  "group_id":"CASE-BATCH-1",
                  "relation_mode":"batch_accounting",
                  "relation_status":"linked",
                  "row_ids":["txn-batch-1","oa-batch-1"],
                  "row_types":["bank","oa"],
                  "special_metadata":{"source":"batch_accounting","bank_year":"2026"}
                }'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into read_model.workbench_relation_rows(
                tenant_id, row_id, row_type, scope_key, scope_month, relation_status,
                group_ids, linked_oa, linked_bank_transactions, source_versions, payload
            )
            values (
                'default', 'txn-batch-1', 'bank_transaction', '2026-01', '2026-01-01', 'linked',
                array['CASE-BATCH-1'], '[{"id":"oa-batch-1"}]'::jsonb,
                '[{"id":"txn-batch-1"}]'::jsonb,
                '{"workbench_relation_schema_version":"bulk-v1"}'::jsonb,
                '{"row_id":"txn-batch-1","row_type":"bank_transaction"}'::jsonb
            )
            """
        )

        count_payload = self.repository.count_batch_accounting_relations_by_year(year="2026")
        list_payload = self.repository.list_batch_accounting_relation_groups_by_year(year="2026")
        row_payload = self.repository.get_batch_accounting_relation_rows_by_ids(
            ["txn-batch-1"],
            scope_keys_hint=["2026-01"],
        )

        self.assertEqual(count_payload["read_model_status"], "fresh")
        self.assertEqual(count_payload["submitted_count"], 1)
        self.assertEqual(list_payload["read_model_status"], "fresh")
        self.assertEqual(list_payload["groups"][0]["group_id"], "CASE-BATCH-1")
        self.assertEqual(row_payload["read_model_status"], "fresh")
        self.assertEqual(row_payload["rows"][0]["row_id"], "txn-batch-1")

        self.connection.execute(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id, scope_type, scope_key, source_version, status
            )
            values ('default', 'workbench_relation', '2026-01', 2, 'processing')
            """
        )
        refreshing = self.repository.count_batch_accounting_relations_by_year(year="2026")
        self.assertEqual(refreshing["read_model_status"], "refreshing")
        self.assertIn("refreshing:2026-01", refreshing["stale_reasons"])
        self.assertEqual(refreshing["submitted_count"], 0)

    def test_unsubmitted_candidate_and_attachment_reads_use_hot_paths(self) -> None:
        self.connection.execute(
            """
            insert into read_model.workbench_generations(
                generation_id, tenant_id, scope_key, status, source_versions,
                completed_at, activated_at
            )
            values (
                'batch-accounting-pg-2026-01', 'default', '2026-01', 'active',
                '{"workbench_schema_version":"test"}'::jsonb, now(), now()
            )
            """
        )
        self.connection.execute(
            """
            insert into read_model.workbench_rows(
                row_id, scope_month, scope_key, source_kind, status, counterparty_name,
                generated_at, generation_id, payload
            )
            values
              (
                'txn-batch-structured-1', '2026-01-01', '2026-01', 'bank', 'unpaired',
                '批量账务集中处理', now(), 'batch-accounting-pg-2026-01',
                '{"id":"txn-batch-structured-1","type":"bank","counterparty_name":"批量账务集中处理"}'::jsonb
              ),
              (
                'txn-batch-legacy-json-1', '2026-01-01', '2026-01', 'bank', 'unpaired',
                '其他对方', now(), 'batch-accounting-pg-2026-01',
                '{"id":"txn-batch-legacy-json-1","type":"bank","counterparty_name":"批量账务集中处理"}'::jsonb
              ),
              (
                'oa-batch-1', '2026-01-01', '2026-01', 'oa', 'unpaired', null,
                now(), 'batch-accounting-pg-2026-01',
                '{"id":"oa-batch-1","type":"oa","apply_type":"日常报销","amount":"10.00"}'::jsonb
              ),
              (
                'oa-att-inv-oa-batch-1-01', '2026-01-01', '2026-01',
                'oa_attachment_invoice', 'unpaired', null, now(),
                'batch-accounting-pg-2026-01',
                '{"id":"oa-att-inv-oa-batch-1-01","type":"invoice","derived_from_oa_id":"oa-batch-1"}'::jsonb
              ),
              (
                'oa-att-inv-unrelated-01', '2026-01-01', '2026-01',
                'oa_attachment_invoice', 'unpaired', null, now(),
                'batch-accounting-pg-2026-01',
                '{"id":"oa-att-inv-unrelated-01","type":"invoice","derived_from_oa_id":"oa-unrelated"}'::jsonb
              )
            """
        )
        self.connection.execute(
            """
            insert into read_model.workbench_rows(
                row_id, scope_month, scope_key, source_kind, status, counterparty_name,
                generated_at, generation_id, payload
            )
            select
                'oa-batch-non-match-' || item_number::text,
                '2026-01-01',
                '2026-01',
                'oa',
                'unpaired',
                null,
                now(),
                'batch-accounting-pg-2026-01',
                jsonb_build_object(
                    'id', 'oa-batch-non-match-' || item_number::text,
                    'type', 'oa',
                    'apply_type', '其他流程'
                )
            from generate_series(1, 5000) item_number
            """
        )
        self.connection.execute("analyze read_model.workbench_rows")

        payload = self.repository.load_batch_accounting_workbench_payload(bank_year="2026")
        group = payload["unpaired"]["groups"][0]
        submit_payload = self.repository.load_batch_accounting_submit_workbench_payload(
            bank_year="2026",
            bank_row_id="txn-batch-structured-1",
            oa_row_ids=["oa-batch-1"],
        )
        submit_group = submit_payload["unpaired"]["groups"][0]
        explain_row = self.connection.fetch_one(
            """
            explain (format json)
            select row_id
            from read_model.workbench_rows
            where scope_key <> 'all'
              and source_kind = 'oa'
              and (
                    coalesce(payload->>'apply_type', '')
                    || ' '
                    || coalesce(payload->>'expense_type', '')
                  ) like %s
            """,
            ("%日常报销%",),
        )

        self.assertEqual([row["id"] for row in group["bank_rows"]], ["txn-batch-structured-1"])
        self.assertEqual([row["id"] for row in group["oa_rows"]], ["oa-batch-1"])
        self.assertEqual(
            [row["id"] for row in group["invoice_rows"]],
            ["oa-att-inv-oa-batch-1-01"],
        )
        self.assertEqual(
            [row["id"] for row in submit_group["invoice_rows"]],
            ["oa-att-inv-oa-batch-1-01"],
        )
        self.assertIn(
            "workbench_rows_batch_accounting_oa_type_trgm_idx",
            json.dumps(explain_row, ensure_ascii=False),
        )

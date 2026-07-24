from __future__ import annotations

import json
import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.cost_statistics_sql_projection import CostStatisticsSqlProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
)
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class CostStatisticsPostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.repository = PostgresReadModelRepository(self.connection)

    def test_all_facet_views_execute_through_psycopg_placeholder_parser(self) -> None:
        self.connection.execute(
            """
            insert into read_model.cost_statistics_rows(
                scope_key, project_scope, scope_month, row_key, transaction_id,
                trade_time_text, trade_date, payment_account_label, direction,
                project_name, expense_type, amount
            )
            values (
                'active:2026-05', 'active', '2026-05-01', 'txn-1:0', 'txn-1',
                '2026-05-02 10:00:00', '2026-05-02', '工商银行 0001', '支出',
                '项目A', '材料', 100
            )
            """
        )

        for view in ("project", "bank", "expense_type"):
            with self.subTest(view=view):
                payload = self.repository.get_cost_statistics_page(
                    project_scope="active",
                    scope_kind="all",
                    scope_value=None,
                    view=view,
                    filters={},
                    selected_tag_codes=None,
                    cursor_values=None,
                    page_size=50,
                )

                self.assertIsInstance(payload, dict)
                facets = payload["primary_facets"]
                self.assertEqual(len(facets), 1)
                self.assertTrue(facets[0]["percentage_label"].endswith("%"))

    def test_bank_flow_views_preserve_stable_bank_page_identity(self) -> None:
        self.connection.execute(
            f"""
            insert into read_model.bank_detail_rows(
                tenant_id, transaction_id, scope_key, scope_month, account_key,
                bank_name, account_last4, trade_time_sort, trade_date,
                direction, direction_label, amount,
                effective_category_code, effective_category_label,
                effective_category_primary_label, effective_category_sub_label,
                effective_category_label_path, schema_version, payload
            )
            values (
                'default', '64bf2e9b-0ccb-59da-b89e-bf537be30b56',
                '2026-03', '2026-03-01', 'test-account',
                '工商银行', '0001', '2026-03-05', '2026-03-05',
                'expense', '支出', 200000,
                'repayment', '归还借款', '外部往来款', '归还借款',
                array['外部往来款', '归还借款'], {BANK_DETAIL_READ_MODEL_SCHEMA_VERSION},
                '{{"id": "txn_imported_1348", "trade_time": "2026-03-05"}}'::jsonb
            )
            """
        )

        page = self.repository.get_cost_statistics_page(
            project_scope="active",
            scope_kind="month",
            scope_value="2026-03",
            view="bank_tag",
            filters={
                "bank_tag_primary_label": "外部往来款",
                "bank_tag_sub_label": "归还借款",
            },
            selected_tag_codes=None,
            cursor_values=None,
            page_size=50,
        )
        detail = self.repository.get_cost_statistics_transaction(
            project_scope="active",
            transaction_id="txn_imported_1348",
            dependency_profile="bank_flow",
            scope_kind="month",
            scope_value="2026-03",
        )

        self.assertEqual(page["rows"][0]["transaction_id"], "txn_imported_1348")
        self.assertEqual(detail["transaction_id"], "txn_imported_1348")

    def test_parent_freshness_gate_returns_exact_child_when_embedded_workbench_version_drifts(
        self,
    ) -> None:
        child_source_versions = {
            "cost_statistics_read_model_schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "workbench_scope_key": "2026-03",
            "workbench_read_model_schema_version": "workbench-month-v6",
            "bank_auto_tag_rules_version": 1,
            "bank_account_mappings_fingerprint": "[]",
            "oa_projection_sync_version": "test",
            "workbench_source_versions": {"source_version": 7},
            "bank_detail_source_versions": {"source_version": 1, "signature": "bank-v1"},
        }
        parent_source_versions = {
            "cost_statistics_read_model_schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "workbench_scope_key": "all",
            "workbench_read_model_schema_version": "workbench-month-v6",
            "bank_auto_tag_rules_version": 1,
            "bank_account_mappings_fingerprint": "[]",
            "oa_projection_sync_version": "test",
            "cost_statistics_parent_source": "materialized_shards",
            "source_shard_count": 1,
            "source_shards": {"active:2026-03": child_source_versions},
        }
        self.connection.execute(
            """
            insert into app.app_settings(settings_key, settings_payload)
            values (
                'app_settings',
                '{
                    "bank_transaction_tags": {},
                    "bank_account_mappings": [],
                    "cost_statistics_tag_selection": {}
                }'::jsonb
            )
            """
        )
        self.connection.execute(
            """
            insert into read_model.workbench_generations(
                generation_id, tenant_id, scope_key, status, source_versions,
                completed_at, activated_at
            )
            values (
                'cost-parent-workbench-2026-03', 'default', '2026-03', 'active',
                '{"source_version": 8}'::jsonb, now(), now()
            )
            """
        )
        self.connection.execute(
            """
            insert into read_model.bank_detail_scopes(
                tenant_id, scope_type, scope_key, scope_month, schema_version,
                status, row_count, source_version, source_versions, generated_at
            )
            values (
                'default', 'bank_detail', '2026-03', '2026-03-01', %s,
                'fresh', 0, 1, '{"source_version": 1, "signature": "bank-v1"}'::jsonb, now()
            )
            """,
            (BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,),
        )
        self.connection.execute(
            """
            insert into read_model.cost_statistics_read_models(
                scope_key, project_scope, scope_month, generated_at, entry_count,
                source_versions, payload, published_source_version
            )
            values
                (
                    'active:2026-03', 'active', '2026-03-01', now(), 0,
                    %s::jsonb,
                    jsonb_build_object('schema_version', %s::text, 'payload', '{}'::jsonb),
                    7
                ),
                (
                    'active:all', 'active', null, now(), 0,
                    %s::jsonb,
                    jsonb_build_object(
                        'schema_version', %s::text,
                        'payload', jsonb_build_object(
                            'statistics',
                            jsonb_build_object(
                                'transaction_count', 0,
                                'expense_transaction_count', 0,
                                'income_transaction_count', 0,
                                'cost_group_count', 0,
                                'tagged_transaction_count', 0,
                                'untagged_transaction_count', 0,
                                'project_count', 0,
                                'expense_type_count', 0,
                                'bank_tag_count', 0,
                                'cost_transaction_count', 0
                            )
                        )
                    ),
                    7
                )
            """,
            (
                json.dumps(child_source_versions),
                COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                json.dumps(parent_source_versions),
                COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            ),
        )

        gate = self.repository.get_cost_statistics_freshness_gate(scope_key="active:all")

        self.assertEqual(gate["refresh_status"], "stale")
        self.assertEqual(gate["workbench_refresh_scope_keys"], [])
        self.assertEqual(gate["child_refresh_scope_keys"], ["active:2026-03"])
        self.assertIn("cost_statistics_parent_child_scope_not_fresh", gate["stale_reasons"])
        self.assertEqual(gate["bank_flow_refresh_status"], "fresh")
        self.assertEqual(gate["bank_flow_bank_detail_refresh_scope_keys"], [])
        self.assertEqual(gate["bank_flow_child_refresh_scope_keys"], [])

    def test_split_transaction_detail_aggregates_all_cost_allocations(self) -> None:
        self.connection.execute(
            """
            insert into read_model.cost_statistics_rows(
                scope_key, project_scope, scope_month, row_key, transaction_id,
                trade_time_text, trade_date, direction, project_name, expense_type,
                expense_content, oa_applicant, amount
            )
            values
                (
                    'active:2026-05', 'active', '2026-05-01', 'txn-split:oa:oa-a', 'txn-split',
                    '2026-05-02 10:00:00', '2026-05-02', '支出', '项目A', '材料',
                    '采购材料', '申请人A', 60000
                ),
                (
                    'active:2026-05', 'active', '2026-05-01', 'txn-split:oa:oa-b', 'txn-split',
                    '2026-05-02 10:00:00', '2026-05-02', '支出', '项目B', '服务',
                    '技术服务', '申请人B', 40000
                )
            """
        )

        row = self.repository.get_cost_statistics_transaction(
            project_scope="active",
            transaction_id="txn-split",
            dependency_profile="workbench",
            scope_kind="month",
            scope_value="2026-05",
        )

        self.assertIsNotNone(row)
        self.assertEqual(
            [(item["row_key"], item["amount"]) for item in row["cost_allocations"]],
            [
                ("txn-split:oa:oa-a", "60000.000000"),
                ("txn-split:oa:oa-b", "40000.000000"),
            ],
        )

    def test_unchanged_scope_acknowledgement_advances_only_exact_current_version(self) -> None:
        self.connection.execute(
            """
            insert into read_model.cost_statistics_read_models(
                scope_key,
                project_scope,
                scope_month,
                generated_at,
                entry_count,
                source_versions,
                payload,
                raw_payload,
                published_source_version
            )
            values (
                'active:2026-05',
                'active',
                '2026-05-01',
                now(),
                1,
                '{"proof": "v1"}'::jsonb,
                '{"summary": {"total_amount": "10.00"}}'::jsonb,
                '{"normalized_payload": {"proof": "keep"}}'::jsonb,
                6
            )
            """
        )
        self.connection.execute(
            """
            insert into job.read_model_dirty_scopes(
                tenant_id,
                scope_type,
                scope_key,
                source_version,
                status
            )
            values ('default', 'cost_statistics', 'active:2026-05', 7, 'processing')
            """
        )

        acknowledged = self.repository.acknowledge_unchanged_cost_statistics_scope(
            tenant_id="default",
            scope_key="active:2026-05",
            source_version=7,
            source_versions={"proof": "v1"},
        )

        self.assertTrue(acknowledged)
        row = self.connection.fetch_one(
            """
            select published_source_version, source_versions, payload, raw_payload
            from read_model.cost_statistics_read_models
            where scope_key = 'active:2026-05'
            """
        )
        self.assertEqual(row["published_source_version"], 7)
        self.assertEqual(row["source_versions"], {"proof": "v1"})
        self.assertEqual(row["payload"], {"summary": {"total_amount": "10.00"}})
        self.assertEqual(row["raw_payload"], {"normalized_payload": {"proof": "keep"}})

        self.connection.execute(
            """
            update job.read_model_dirty_scopes
            set source_version = 8
            where tenant_id = 'default'
              and scope_type = 'cost_statistics'
              and scope_key = 'active:2026-05'
              and status = 'processing'
            """
        )
        self.assertFalse(
            self.repository.acknowledge_unchanged_cost_statistics_scope(
                tenant_id="default",
                scope_key="active:2026-05",
                source_version=7,
                source_versions={"proof": "v1"},
            )
        )
        self.assertFalse(
            self.repository.acknowledge_unchanged_cost_statistics_scope(
                tenant_id="default",
                scope_key="active:2026-05",
                source_version=8,
                source_versions={"proof": "v2"},
            )
        )

    def test_parent_metadata_aggregate_reads_only_current_shards(self) -> None:
        self.connection.execute(
            """
            insert into read_model.cost_statistics_rows(
                scope_key, project_scope, scope_month, row_key, transaction_id,
                trade_time_text, trade_date, direction, project_name, expense_type, amount
            )
            values
                ('active:2026-05', 'active', '2026-05-01', 'current:0', 'current',
                 '2026-05-02', '2026-05-02', '支出', '当前项目', '材料', 10),
                ('active:2026-04', 'active', '2026-04-01', 'obsolete:0', 'obsolete',
                 '2026-04-02', '2026-04-02', '支出', '旧项目', '材料', 999)
            """
        )
        self.connection.execute(
            f"""
            insert into read_model.bank_detail_rows(
                tenant_id, transaction_id, scope_key, scope_month, account_key,
                bank_name, account_last4, trade_time_sort, trade_date,
                direction, direction_label, amount, schema_version
            )
            values
                ('default', 'current', '2026-05', '2026-05-01', 'current-account',
                 '工商银行', '0001', '2026-05-02', '2026-05-02',
                 'expense', '支出', 20, {BANK_DETAIL_READ_MODEL_SCHEMA_VERSION}),
                ('default', 'obsolete', '2026-04', '2026-04-01', 'obsolete-account',
                 '工商银行', '0001', '2026-04-02', '2026-04-02',
                 'income', '收入', 999, {BANK_DETAIL_READ_MODEL_SCHEMA_VERSION})
            """
        )
        builder = CostStatisticsSqlProjectionBuilder(
            connection=self.connection,
            read_model_repository=self.repository,
        )

        payload = builder._cost_statistics_parent_metadata_payload(
            project_scope="active",
            scope_keys=["active:2026-05"],
        )

        self.assertEqual(payload["summary"], {"row_count": 1, "transaction_count": 1, "total_amount": "10.00"})
        self.assertEqual(payload["statistics"]["transaction_count"], 1)
        self.assertEqual(payload["statistics"]["expense_transaction_count"], 1)
        self.assertEqual(payload["statistics"]["income_transaction_count"], 0)
        self.assertEqual(payload["project_rows"], [
            {
                "project_name": "当前项目",
                "total_amount": "10.00",
                "transaction_count": 1,
                "expense_type_count": 1,
            }
        ])
        self.assertEqual(payload["expense_type_rows"], [
            {
                "expense_type": "材料",
                "total_amount": "10.00",
                "transaction_count": 1,
                "project_count": 1,
            }
        ])

if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
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


if __name__ == "__main__":
    unittest.main()

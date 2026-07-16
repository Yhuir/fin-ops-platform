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


if __name__ == "__main__":
    unittest.main()

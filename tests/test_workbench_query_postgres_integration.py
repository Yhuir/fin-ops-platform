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


class WorkbenchQueryPostgresIntegrationTests(unittest.TestCase):
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
        self._insert_active_bank_group()

    def tearDown(self) -> None:
        self.connection.close()
        truncate_test_database(self.database_url)

    def _insert_active_bank_group(self) -> None:
        generation_id = "workbench:2026-07:query-integration"
        group_id = "unpaired:bank:query-integration"
        row_id = "txn-query-integration"
        counterparty = "云南腾安科技有限公司"
        self.connection.execute(
            """
            insert into read_model.workbench_generations(
                generation_id, tenant_id, scope_key, status, source_versions,
                completed_at, activated_at, row_count, group_count, summary_count
            ) values (%s, 'default', '2026-07', 'active', %s::jsonb, now(), now(), 1, 1, 0)
            """,
            (generation_id, json.dumps({"source_version": 1})),
        )
        self.connection.execute(
            """
            insert into read_model.workbench_groups(
                generation_id, group_id, scope_key, scope_month, zone, status,
                group_type, source_kinds, row_count, searchable_text, source_versions,
                payload, raw_payload
            ) values (
                %s, %s, '2026-07', '2026-07-01', 'unpaired', 'unpaired',
                'unpaired', array['bank_transaction'], 1, %s, %s::jsonb, %s::jsonb, '{}'::jsonb
            )
            """,
            (
                generation_id,
                group_id,
                counterparty,
                json.dumps({"source_version": 1}),
                json.dumps(
                    {
                        "group_id": group_id,
                        "zone": "unpaired",
                        "status": "unpaired",
                        "group_type": "unpaired",
                        "oa_rows": [],
                        "bank_rows": [
                            {
                                "id": row_id,
                                "type": "bank",
                                "counterparty_name": counterparty,
                                "amount": "10000.00",
                            }
                        ],
                        "invoice_rows": [],
                    },
                    ensure_ascii=False,
                ),
            ),
        )
        self.connection.execute(
            """
            insert into read_model.workbench_group_rows(
                generation_id, scope_key, scope_month, zone, group_id, pane, row_id,
                row_role, row_index, source_kind, status, time_value, time_date,
                column_values, searchable_text, source_versions, payload, raw_payload
            ) values (
                %s, '2026-07', '2026-07-01', 'unpaired', %s, 'bank', %s,
                'normal', 0, 'bank_transaction', 'unpaired', '2026-07-22', '2026-07-22',
                %s::jsonb, %s, %s::jsonb, %s::jsonb, '{}'::jsonb
            )
            """,
            (
                generation_id,
                group_id,
                row_id,
                json.dumps({"counterparty": counterparty}, ensure_ascii=False),
                counterparty,
                json.dumps({"source_version": 1}),
                json.dumps(
                    {
                        "id": row_id,
                        "type": "bank",
                        "counterparty_name": counterparty,
                        "amount": "10000.00",
                    },
                    ensure_ascii=False,
                ),
            ),
        )

    def test_all_scope_member_filters_execute_without_ambiguous_zone(self) -> None:
        queries = (
            {"search": "云南腾安科技有限公司"},
            {"source_kind": "bank_transaction"},
            {"column_filters": {"bank": {"counterparty": ["云南腾安科技有限公司"]}}},
            {"time_filters": {"bank": {"mode": "month", "month": "2026-07"}}},
        )

        read_model_version = None
        for query in queries:
            with self.subTest(query=query):
                page = self.repository.get_workbench_groups_page(
                    scope_key="all",
                    zone="unpaired",
                    page=1,
                    page_size=25,
                    **query,
                )

                self.assertIsNotNone(page)
                assert page is not None
                self.assertEqual(page["total"], 1)
                self.assertEqual(page["row_counts"]["bank"], 1)
                self.assertEqual(
                    [group["group_id"] for group in page["groups"]],
                    ["unpaired:bank:query-integration"],
                )
                read_model_version = read_model_version or page["read_model_version"]
                self.assertEqual(page["read_model_version"], read_model_version)

        empty_page = self.repository.get_workbench_groups_page(
            scope_key="all",
            zone="unpaired",
            search="不存在的往来单位",
        )
        self.assertIsNotNone(empty_page)
        assert empty_page is not None
        self.assertEqual(empty_page["total"], 0)
        self.assertEqual(empty_page["groups"], [])


if __name__ == "__main__":
    unittest.main()

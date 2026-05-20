from __future__ import annotations

import unittest

from tests.postgres_test_utils import apply_test_migrations, fetch_scalar, require_postgres_test_database_url


class RuntimeInfrastructurePostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)

    def test_runtime_infrastructure_tables_exist(self) -> None:
        for table in ("job.read_model_dirty_scopes", "job.runtime_worker_heartbeats"):
            exists = fetch_scalar(
                self.database_url,
                f"select to_regclass('{table}') is not null;",
            )
            self.assertEqual(exists, "t", table)

    def test_outbox_events_runtime_columns_exist(self) -> None:
        columns = (
            "tenant_id",
            "scope_type",
            "scope_key",
            "dedupe_key",
            "attempts",
            "processed_at",
        )
        column_list = ", ".join(f"'{column}'" for column in columns)
        count = fetch_scalar(
            self.database_url,
            f"""
            select count(*)
            from information_schema.columns
            where table_schema = 'job'
              and table_name = 'outbox_events'
              and column_name in ({column_list});
            """,
        )
        self.assertEqual(count, str(len(columns)))


if __name__ == "__main__":
    unittest.main()

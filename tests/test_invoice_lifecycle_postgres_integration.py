from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from tests.postgres_test_utils import (
    apply_test_migrations,
    require_postgres_test_database_url,
    truncate_test_database,
)


class InvoiceLifecyclePostgresIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.database_url = require_postgres_test_database_url()
        apply_test_migrations(self.database_url)
        truncate_test_database(self.database_url)
        self.connection = PostgresConnection(
            PostgresSettings(database_url=self.database_url, pool_enabled=False)
        )
        self.repository = PostgresReadModelRepository(self.connection)

    def test_reads_pending_invoice_rows_from_exact_fresh_month_shard(self) -> None:
        self.repository.save_pending_invoice_rows(
            scope_key="expense:all:2026-05",
            rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {
                            "id": "txn-1",
                            "trade_time": "2026-05-20",
                            "amount": "100.00",
                        },
                        "invoice_acquisition_status": {"code": "missing_invoice"},
                    }
                }
            ],
            source_versions={"pending_invoice_signature": "expense-v1"},
        )

        payload = self.repository.list_pending_invoice_lifecycle_source_rows(
            month="2026-05",
            direction="expense",
        )

        self.assertEqual(payload["scope_key"], "expense:all:2026-05")
        self.assertEqual(payload["refresh_status"], "fresh")
        self.assertEqual(payload["source_versions"], {"pending_invoice_signature": "expense-v1"})
        self.assertEqual([row["id"] for row in payload["rows"]], ["txn-1"])


if __name__ == "__main__":
    unittest.main()

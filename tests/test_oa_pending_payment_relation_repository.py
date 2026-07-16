from __future__ import annotations

import unittest

from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    PostgresOaPendingPaymentRelationRepository,
)


class OaPendingPaymentRelationRepositoryTests(unittest.TestCase):
    def test_source_version_reads_the_month_and_tenant_watermark(self) -> None:
        connection = RecordingConnection(fetch_one_row={"version": 7})
        repository = PostgresOaPendingPaymentRelationRepository(connection)

        result = repository.source_versions(scope_key="2026-06-18", tenant_id="tenant-a")

        self.assertEqual(result, {"oa_pending_payment_relation_version": 7})
        self.assertEqual(connection.fetches[0][1], ("oa_pending_payment_relation:tenant-a:2026-06",))

    def test_ensure_scope_source_version_uses_caller_transaction_without_increment(self) -> None:
        connection = RecordingConnection()
        transaction = RecordingConnection()
        repository = PostgresOaPendingPaymentRelationRepository(connection)

        repository.ensure_scope_source_version(
            scope_key="2026-06",
            tenant_id="tenant-a",
            transaction=transaction,
        )

        self.assertEqual(connection.executions, [])
        self.assertEqual(len(transaction.executions), 1)
        sql, params = transaction.executions[0]
        self.assertIn("insert into app.oa_sync_watermarks", sql)
        self.assertIn("version = app.oa_sync_watermarks.version ,", sql)
        self.assertNotIn("version = app.oa_sync_watermarks.version + 1", sql)
        self.assertEqual(params[0], "oa_pending_payment_relation:tenant-a:2026-06")

    def test_mutation_source_version_touch_increments_existing_watermark(self) -> None:
        connection = RecordingConnection()

        PostgresOaPendingPaymentRelationRepository._touch_scope_source_version(
            connection,
            scope_key="2026-06",
            tenant_id="tenant-a",
            increment=True,
        )

        sql, params = connection.executions[0]
        self.assertIn("version = app.oa_sync_watermarks.version + 1", sql)
        self.assertEqual(params[0], "oa_pending_payment_relation:tenant-a:2026-06")


class RecordingConnection:
    def __init__(self, *, fetch_one_row: dict[str, object] | None = None) -> None:
        self.fetch_one_row = fetch_one_row
        self.executions: list[tuple[str, tuple[object, ...]]] = []
        self.fetches: list[tuple[str, tuple[object, ...]]] = []

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.executions.append((" ".join(sql.split()), params))

    def fetch_one(self, sql: str, params: tuple[object, ...]) -> dict[str, object] | None:
        self.fetches.append((" ".join(sql.split()), params))
        return self.fetch_one_row


if __name__ == "__main__":
    unittest.main()

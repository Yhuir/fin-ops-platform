from __future__ import annotations

from contextlib import contextmanager
import unittest

from fin_ops_platform.services.cost_statistics_canonical_repository import (
    PostgresCostStatisticsCanonicalRepository,
)


class _SnapshotTransaction:
    def __init__(self) -> None:
        self.executed: list[str] = []
        self.fetched: list[str] = []

    def execute(self, sql: str, _params: tuple = ()) -> None:
        self.executed.append(" ".join(sql.lower().split()))

    def fetch_one(self, sql: str, _params: tuple = ()):
        self.fetched.append(" ".join(sql.lower().split()))
        if "from app.app_settings" in self.fetched[-1]:
            return {"settings_payload": {}}
        return None

    def fetch_all(self, sql: str, _params: tuple = ()):
        normalized = " ".join(sql.lower().split())
        self.fetched.append(normalized)
        return []


class _Connection:
    def __init__(self) -> None:
        self.transaction_count = 0
        self.snapshot_transaction = _SnapshotTransaction()

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self.snapshot_transaction


class CostStatisticsCanonicalRepositoryTests(unittest.TestCase):
    def test_load_uses_one_repeatable_read_snapshot_and_only_canonical_tables(self) -> None:
        connection = _Connection()

        snapshot = PostgresCostStatisticsCanonicalRepository(connection).load_snapshot()

        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            connection.snapshot_transaction.executed,
            ["set transaction isolation level repeatable read read only"],
        )
        sql = "\n".join(connection.snapshot_transaction.fetched)
        self.assertIn("from app.app_settings", sql)
        self.assertIn("from app.bank_transactions", sql)
        self.assertIn("from app.bank_transaction_categories", sql)
        self.assertIn("from app.bank_transaction_category_confirmations", sql)
        self.assertIn("from app.workbench_pair_relations", sql)
        self.assertNotIn("read_model.", sql)
        self.assertNotIn("job.", sql)
        self.assertEqual(snapshot["bank_rows"], [])
        self.assertEqual(snapshot["cost_groups"], [])


if __name__ == "__main__":
    unittest.main()

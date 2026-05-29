from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_account_balance_projection import BankAccountBalanceProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
)


class FakeConnection:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = list(rows or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append(("fetch_all", sql, params))
        value = self.rows.pop(0) if self.rows else []
        return list(value) if isinstance(value, list) else []

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.calls.append(("execute", sql, params))
        return 0

    def transaction(self):
        connection = self

        class Transaction:
            def __enter__(self) -> FakeConnection:
                return connection

            def __exit__(self, exc_type, exc, traceback) -> bool:
                return False

        return Transaction()


class CaptureAccountBalanceRepository:
    def __init__(self) -> None:
        self.saved_rows: list[dict[str, object]] = []

    def save_bank_account_balances(self, *, rows: list[dict[str, object]], tenant_id: str = "default") -> None:
        self.saved_rows = list(rows)


class BankAccountBalanceProjectionTests(unittest.TestCase):
    def test_projection_uses_latest_non_empty_balance_with_stable_account_identity(self) -> None:
        repository = CaptureAccountBalanceRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-old",
                        "transaction_id": "pg-old",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "txn_date": "2026-04-01",
                        "trade_time": "2026-04-01 09:00:00",
                        "trade_time_sort": "2026-04-01 09:00:00",
                        "bank_serial_no": "001",
                        "balance": "900.00",
                        "currency": "CNY",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-new-empty",
                        "transaction_id": "pg-new-empty",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 10:00:00",
                        "trade_time_sort": "2026-04-03 10:00:00",
                        "bank_serial_no": "003",
                        "balance": None,
                        "currency": "CNY",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-latest-balance",
                        "transaction_id": "pg-latest-balance",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "txn_date": "2026-04-02",
                        "trade_time": "2026-04-02 09:00:00",
                        "trade_time_sort": "2026-04-02 09:00:00",
                        "bank_serial_no": "002",
                        "balance": "117644.93",
                        "currency": "CNY",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-same-tail",
                        "transaction_id": "pg-same-tail",
                        "account_no": "9558800011116386",
                        "account_name": "一般户",
                        "txn_date": "2026-04-02",
                        "trade_time": "2026-04-02 09:00:00",
                        "trade_time_sort": "2026-04-02 09:00:00",
                        "bank_serial_no": "002",
                        "balance": "200.00",
                        "currency": "CNY",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                ]
            ]
        )

        result = BankAccountBalanceProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        ).rebuild_bank_account_balance_read_model()

        self.assertEqual(result["row_count"], 2)
        self.assertEqual(len(repository.saved_rows), 2)
        by_account_no = {row["account_no"]: row for row in repository.saved_rows}
        self.assertEqual(by_account_no["6222000011116386"]["latest_balance"], "117644.93")
        self.assertEqual(by_account_no["6222000011116386"]["latest_balance_transaction_id"], "txn-latest-balance")
        self.assertEqual(by_account_no["9558800011116386"]["latest_balance"], "200.00")
        self.assertNotEqual(
            by_account_no["6222000011116386"]["account_identity"],
            by_account_no["9558800011116386"]["account_identity"],
        )

    def test_projection_normalizes_renminbi_currency_aliases(self) -> None:
        repository = CaptureAccountBalanceRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-rmb",
                        "transaction_id": "pg-rmb",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "txn_date": "2026-04-01",
                        "trade_time": "2026-04-01 09:00:00",
                        "trade_time_sort": "2026-04-01 09:00:00",
                        "bank_serial_no": "001",
                        "balance": "900.00",
                        "currency": "人民币元",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    }
                ]
            ]
        )

        BankAccountBalanceProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        ).rebuild_bank_account_balance_read_model()

        self.assertEqual(repository.saved_rows[0]["currency"], "CNY")

    def test_repository_lists_balances_without_reading_bank_detail_rows_for_balance(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    {
                        "scope_key": "all",
                        "scope_type": "bank_account_balance",
                        "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                        "status": "fresh",
                        "row_count": 2,
                        "source_version": 1,
                        "source_versions": {},
                        "generated_at": "2026-04-02 10:00:00",
                    }
                ],
                [],
                [
                    {
                        "account_identity": "acct:one",
                        "account_key": "acct:one",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "identity_confidence": "account_no",
                        "latest_balance": "117644.93",
                        "latest_balance_at": "2026-04-02 09:00:00",
                        "latest_balance_transaction_id": "txn-latest",
                        "currency": "CNY",
                        "transaction_total_count": 3,
                        "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                    },
                    {
                        "account_identity": "acct:empty",
                        "account_key": "acct:empty",
                        "bank_name": "交通银行",
                        "account_last4": "3847",
                        "account_no": "531899991015003383847",
                        "account_name": "一般户",
                        "identity_confidence": "account_no",
                        "latest_balance": None,
                        "latest_balance_at": None,
                        "latest_balance_transaction_id": None,
                        "currency": "CNY",
                        "transaction_total_count": 1,
                        "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                    },
                ],
                [
                    {"account_key": "acct:one", "transaction_count": 1},
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_account_balances(date_from="2026-03-01", date_to="2026-03-31")

        self.assertEqual(payload["total_balance"], "117644.93")
        self.assertEqual(payload["total_balances_by_currency"], {"CNY": "117644.93"})
        self.assertEqual(payload["balance_account_count"], 1)
        self.assertEqual(payload["missing_balance_account_count"], 1)
        self.assertEqual(payload["accounts"][0]["transaction_count"], 1)
        self.assertEqual(payload["accounts"][0]["latest_balance_transaction_id"], "txn-latest")
        balance_call = next(call for call in connection.calls if "from read_model.bank_account_balances" in call[1].lower())
        balance_sql = " ".join(balance_call[1].lower().split())
        self.assertIn("from read_model.bank_account_balances", balance_sql)
        self.assertNotIn("from read_model.bank_detail_rows", balance_sql)

    def test_repository_returns_empty_fresh_payload_after_empty_projection(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    {
                        "scope_key": "all",
                        "scope_type": "bank_account_balance",
                        "schema_version": BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                        "status": "fresh",
                        "row_count": 0,
                        "source_version": 1,
                        "source_versions": {},
                        "generated_at": "2026-04-02 10:00:00",
                    }
                ],
                [],
                [],
                [],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_account_balances(date_from="2026-03-01", date_to="2026-03-31")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["accounts"], [])
        self.assertIsNone(payload["total_balance"])
        self.assertEqual(payload["balance_read_model_status"], "fresh")


if __name__ == "__main__":
    unittest.main()

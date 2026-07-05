from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_account_balance_projection import BankAccountBalanceProjectionBuilder, _account_identity
from fin_ops_platform.services.bank_account_balance_read_model_repository import BankAccountBalanceReadModelRepositoryPort
from fin_ops_platform.services.bank_account_balance_read_model_refresh import BankAccountBalanceReadModelRefreshService
from fin_ops_platform.services.bank_account_balance_read_model_refresh_producer import BankAccountBalanceReadModelRefreshProducer
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


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

    def execute_many(self, sql: str, params_seq: list[tuple[object, ...]]) -> int:
        self.calls.append(("execute_many", sql, tuple(params_seq)))
        return len(params_seq)

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


class _UnderlyingBankAccountBalanceRepository:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []

    def bank_account_balance_scope_summary(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("bank_account_balance_scope_summary", dict(kwargs)))
        return {"read_model_status": "fresh", "read_model_scope_keys": ["all"]}

    def list_bank_account_balances(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(("list_bank_account_balances", dict(kwargs)))
        return {"accounts": [{"account_key": "acct:one"}], "balance_read_model_status": "fresh"}

    def save_bank_account_balances(self, **kwargs: object) -> None:
        self.calls.append(("save_bank_account_balances", dict(kwargs)))

    def list_bank_detail_transactions(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("bank_account_balance port must not expose bank detail repository methods")

    def search_index(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("bank_account_balance port must not expose search repository methods")


class _CaptureRefreshGateway:
    def __init__(self, *, can_enqueue: bool = True) -> None:
        self._can_enqueue = can_enqueue
        self.calls: list[dict[str, object]] = []

    def can_enqueue(self) -> bool:
        return self._can_enqueue

    def enqueue_many(
        self,
        scope_type: str,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        self.calls.append(
            {
                "scope_type": scope_type,
                "scope_keys": list(scope_keys),
                "reason": reason,
                "metadata": metadata,
            }
        )
        return list(scope_keys)


class BankAccountBalanceProjectionTests(unittest.TestCase):
    def test_refresh_producer_enqueues_all_scope_through_gateway(self) -> None:
        gateway = _CaptureRefreshGateway()
        producer = BankAccountBalanceReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        enqueued = producer.enqueue_scope_keys(
            ["2026-03", "all", "account:legacy"],
            reason="unit_test",
            metadata={"source": "test"},
        )

        self.assertEqual(enqueued, ["all"])
        self.assertEqual(
            gateway.calls,
            [
                {
                    "scope_type": "bank_account_balance",
                    "scope_keys": ["all"],
                    "reason": "unit_test",
                    "metadata": {"source": "test"},
                }
            ],
        )

    def test_refresh_producer_returns_false_when_gateway_unavailable(self) -> None:
        gateway = _CaptureRefreshGateway(can_enqueue=False)
        producer = BankAccountBalanceReadModelRefreshProducer(refresh_gateway_provider=lambda: gateway)

        self.assertFalse(producer.enqueue_all(reason="unit_test"))
        self.assertEqual(gateway.calls, [])

    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        underlying = _UnderlyingBankAccountBalanceRepository()
        port = BankAccountBalanceReadModelRepositoryPort(underlying)

        self.assertEqual(port.bank_account_balance_scope_summary()["read_model_status"], "fresh")
        self.assertEqual(port.list_bank_account_balances(date_from=None, date_to=None)["balance_read_model_status"], "fresh")
        port.save_bank_account_balances(rows=[])

        self.assertFalse(hasattr(port, "list_bank_detail_transactions"))
        self.assertFalse(hasattr(port, "search_index"))
        self.assertEqual(
            [name for name, _payload in underlying.calls],
            [
                "bank_account_balance_scope_summary",
                "list_bank_account_balances",
                "save_bank_account_balances",
            ],
        )

    def test_projection_saves_account_level_sql_projection_rows(self) -> None:
        repository = CaptureAccountBalanceRepository()
        account_one_identity, _ = _account_identity(
            account_no="6222000011116386",
            bank_name="工商银行",
            account_last4="6386",
        )
        account_two_identity, _ = _account_identity(
            account_no="9558800011116386",
            bank_name="工商银行",
            account_last4="6386",
        )
        connection = FakeConnection(
            rows=[
                [
                    {
                        "account_identity": account_one_identity,
                        "account_key": account_one_identity,
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "identity_confidence": "account_no",
                        "currency": "CNY",
                        "transaction_total_count": 3,
                        "latest_balance": "117644.93",
                        "latest_balance_at": "2026-04-02 09:00:00",
                        "latest_balance_transaction_id": "txn-latest-balance",
                        "latest_trade_time_sort": "2026-04-02 09:00:00",
                        "latest_bank_serial_no": "002",
                        "source_batch_id": "batch-one",
                        "legacy_source_batch_id": "legacy-one",
                        "raw_payload": {"latest_transaction": {"id": "txn-latest-balance"}},
                    },
                    {
                        "account_identity": account_two_identity,
                        "account_key": account_two_identity,
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "account_no": "9558800011116386",
                        "account_name": "一般户",
                        "identity_confidence": "account_no",
                        "currency": "CNY",
                        "transaction_total_count": 1,
                        "latest_balance": "200.00",
                        "latest_balance_at": "2026-04-02 09:00:00",
                        "latest_balance_transaction_id": "txn-same-tail",
                        "latest_trade_time_sort": "2026-04-02 09:00:00",
                        "latest_bank_serial_no": "002",
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
        self.assertEqual(by_account_no["6222000011116386"]["transaction_total_count"], 3)
        self.assertEqual(by_account_no["9558800011116386"]["latest_balance"], "200.00")
        self.assertNotEqual(
            by_account_no["6222000011116386"]["account_identity"],
            by_account_no["9558800011116386"]["account_identity"],
        )
        projection_sql = " ".join(connection.calls[0][1].lower().split())
        self.assertIn("select distinct on (account_identity)", projection_sql)
        self.assertIn("digest(normalized_account_no, 'sha256')", projection_sql)

    def test_projection_normalizes_renminbi_currency_aliases(self) -> None:
        repository = CaptureAccountBalanceRepository()
        account_identity, _ = _account_identity(
            account_no="6222000011116386",
            bank_name="工商银行",
            account_last4="6386",
        )
        connection = FakeConnection(
            rows=[
                [
                    {
                        "account_identity": account_identity,
                        "account_key": account_identity,
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "account_no": "6222000011116386",
                        "account_name": "基本户",
                        "identity_confidence": "account_no",
                        "latest_balance": "900.00",
                        "currency": "人民币元",
                        "transaction_total_count": 1,
                    }
                ]
            ]
        )

        BankAccountBalanceProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        ).rebuild_bank_account_balance_read_model()

        self.assertEqual(repository.saved_rows[0]["currency"], "CNY")

    def test_refresh_service_skips_stale_source_version_without_rebuild(self) -> None:
        class ProjectionBuilder:
            def rebuild_bank_account_balance_read_model(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale bank account balance event must not rebuild")

        class QueueRepository:
            def __init__(self) -> None:
                self.current_checks: list[dict[str, object]] = []
                self.completions: list[dict[str, object]] = []

            def read_model_refresh_is_current(self, **kwargs: object) -> bool:
                self.current_checks.append(dict(kwargs))
                return False

            def complete_read_model_refresh(self, **kwargs: object) -> None:
                self.completions.append(dict(kwargs))

        queue = QueueRepository()
        service = BankAccountBalanceReadModelRefreshService(
            projection_builder=ProjectionBuilder(),
            queue_repository=queue,
        )

        result = service.handle_runtime_event(
            RuntimeQueueEvent(
                event_id="evt-stale",
                tenant_id="default",
                event_type="bank_account_balance.read_model.refresh",
                aggregate_type="read_model",
                aggregate_id="all",
                scope_type="bank_account_balance",
                scope_key="all",
                dedupe_key="bank_account_balance.read_model.refresh:bank_account_balance:all",
                payload={"scope_type": "bank_account_balance", "scope_key": "all", "source_version": 4},
                attempts=1,
                status="processing",
                source_version=4,
            )
        )

        self.assertEqual(result["skip_reason"], "stale_source_version")
        self.assertEqual(
            queue.current_checks,
            [
                {
                    "tenant_id": "default",
                    "scope_type": "bank_account_balance",
                    "scope_key": "all",
                    "source_version": 4,
                }
            ],
        )
        self.assertEqual(queue.completions, [])

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

    def test_repository_saves_balances_with_bulk_insert(self) -> None:
        connection = FakeConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_bank_account_balances(
            rows=[
                {
                    "account_identity": "acct:one",
                    "account_key": "acct:one",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "account_no": "6222000011116386",
                    "identity_confidence": "account_no",
                    "latest_balance": "117644.93",
                    "latest_balance_at": "2026-04-02 09:00:00",
                    "latest_balance_transaction_id": "txn-latest",
                    "currency": "CNY",
                    "transaction_total_count": 3,
                    "source_versions": {"source_version": 7},
                    "generated_at": "2026-04-02 10:00:00",
                }
            ]
        )

        execute_many_calls = [
            call for call in connection.calls if call[0] == "execute_many" and "insert into read_model.bank_account_balances" in call[1].lower()
        ]
        self.assertEqual(len(execute_many_calls), 1)
        self.assertEqual(len(execute_many_calls[0][2]), 1)
        per_row_executes = [
            call for call in connection.calls if call[0] == "execute" and "insert into read_model.bank_account_balances" in call[1].lower()
        ]
        self.assertEqual(per_row_executes, [])

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

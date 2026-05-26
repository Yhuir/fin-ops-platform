from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_detail_read_model_refresh import BankDetailReadModelRefreshService
from fin_ops_platform.services.bank_detail_sql_projection import BankDetailSqlProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class FakeConnection:
    def __init__(self, rows: list[object] | None = None) -> None:
        self.rows = list(rows or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        value = self.rows.pop(0) if self.rows else None
        return value if isinstance(value, dict) else None

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


class CaptureBankDetailReadModelRepository:
    def __init__(self) -> None:
        self.saved_rows: list[dict[str, object]] = []
        self.marked_scopes: list[dict[str, object]] = []

    def save_bank_detail_rows(self, *, scope_key: str, rows: list[dict[str, object]], tenant_id: str = "default") -> None:
        self.saved_rows = list(rows)

    def mark_bank_detail_scope(self, **kwargs: object) -> None:
        self.marked_scopes.append(dict(kwargs))


def scope_row(scope_key: str, **overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "scope_key": scope_key,
        "scope_type": "bank_detail",
        "schema_version": BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
        "status": "fresh",
        "row_count": 0,
        "source_version": 3,
        "source_versions": {"source_version": 3},
        "generated_at": "2026-05-25T00:00:00+00:00",
        "last_error": None,
    }
    row.update(overrides)
    return row


def runtime_event(scope_key: str) -> RuntimeQueueEvent:
    return RuntimeQueueEvent(
        event_id="event-1",
        tenant_id="default",
        event_type="bank_detail.read_model.refresh",
        aggregate_type="read_model",
        aggregate_id=scope_key,
        scope_type="bank_detail",
        scope_key=scope_key,
        dedupe_key=f"bank_detail.read_model.refresh:bank_detail:{scope_key}",
        payload={"scope_type": "bank_detail", "scope_key": scope_key, "source_version": 7},
        attempts=0,
        status="processing",
        source_version=7,
    )


class BankDetailSqlRepositoryTests(unittest.TestCase):
    def test_transactions_return_none_when_month_scope_is_missing(self) -> None:
        connection = FakeConnection(rows=[[]])
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNone(payload)
        self.assertIn("from read_model.bank_detail_scopes", " ".join(connection.calls[0][1].lower().split()))

    def test_transactions_return_fresh_empty_payload_for_built_empty_scope(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05")],
                {"total": 0},
                [],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 0})

    def test_transactions_rebuild_bank_text_columns_from_raw_payload_or_sql_columns(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=2)],
                {"total": 2},
                [],
                [
                    {
                        "payload": {
                            "id": "txn-fields",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                        },
                        "raw_payload": {
                            "normalized_payload": {
                                "bank_text_fields": [
                                    {"label": "用途", "value": "工行用途"},
                                    {"label": "摘要", "value": "工行摘要"},
                                    {"label": "附言", "value": "工行附言"},
                                ]
                            }
                        },
                        "summary": None,
                        "purpose": None,
                    },
                    {
                        "payload": {
                            "id": "txn-legacy",
                            "bank_name": "建设银行",
                            "account_last4": "8106",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                        },
                        "raw_payload": {},
                        "summary": "SQL摘要",
                        "purpose": "SQL用途",
                    },
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(date_from="2026-05-01", date_to="2026-05-31")

        self.assertIsNotNone(payload)
        rows = {row["id"]: row for row in payload["rows"]}
        self.assertEqual(rows["txn-fields"]["purpose_text"], "工行用途")
        self.assertEqual(rows["txn-fields"]["summary_text"], "工行摘要")
        self.assertEqual(rows["txn-fields"]["note_text"], "工行附言")
        self.assertEqual(rows["txn-legacy"]["purpose_text"], "")
        self.assertEqual(rows["txn-legacy"]["summary_text"], "SQL摘要")
        self.assertEqual(rows["txn-legacy"]["note_text"], "SQL用途")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("select payload, raw_payload, summary, purpose", sql_text)

    def test_transactions_map_legacy_minsheng_text_to_note_only(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-04", row_count=1)],
                {"total": 1},
                [],
                [
                    {
                        "payload": {
                            "id": "txn-cmbc-legacy",
                            "bank_name": "民生银行",
                            "account_last4": "9486",
                            "purpose_text": "",
                            "summary_text": "",
                            "note_text": "",
                            "purpose": "客户附言内容",
                            "summary": "客户附言内容",
                        },
                        "raw_payload": {},
                        "summary": "客户附言内容",
                        "purpose": "客户附言内容",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(date_from="2026-04-01", date_to="2026-04-30")

        self.assertIsNotNone(payload)
        row = payload["rows"][0]
        self.assertEqual(row["purpose_text"], "")
        self.assertEqual(row["summary_text"], "")
        self.assertEqual(row["note_text"], "客户附言内容")

    def test_accounts_aggregate_from_bank_detail_rows_only_when_scopes_are_fresh(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=2)],
                [
                    {
                        "account_key": "工商银行:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 2,
                        "latest_balance": "100.25",
                        "latest_balance_at": "2026-05-02 09:00:00",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(date_from="2026-05-01", date_to="2026-05-31")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["accounts"][0]["account_key"], "工商银行:6386")
        self.assertEqual(payload["total_balance"], "100.25")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("from app.bank_transactions", sql_text)


class BankDetailSqlProjectionBuilderTests(unittest.TestCase):
    def test_normalized_row_splits_bank_text_fields_for_bank_detail_table(self) -> None:
        builder = BankDetailSqlProjectionBuilder(connection=FakeConnection())

        row = builder._normalize_transaction_row(  # noqa: SLF001
            {
                "id": "txn-sql-text",
                "transaction_id": "uuid-sql-text",
                "account_no": "6222000011116386",
                "txn_direction": "expense",
                "counterparty_name_raw": "供应商",
                "amount": "100.00",
                "signed_amount": "-100.00",
                "balance": "900.00",
                "txn_date": "2026-04-23",
                "trade_time": "2026-04-23 17:33:58+08:00",
                "summary": "旧摘要",
                "remark": "旧备注",
                "bank_text_fields": [
                    {"label": "交易用途", "value": "平安交易用途"},
                    {"label": "摘要", "value": "平安摘要"},
                    {"label": "客户附言", "value": "客户附言内容"},
                ],
                "raw_payload": {
                    "normalized_payload": {
                        "imported_bank_name": "平安银行",
                        "imported_bank_last4": "6386",
                    }
                },
            }
        )

        self.assertEqual(row["trade_time"], "2026-04-23 17:33:58")
        self.assertEqual(row["purpose_text"], "平安交易用途")
        self.assertEqual(row["summary_text"], "平安摘要")
        self.assertEqual(row["note_text"], "客户附言内容")

    def test_normalized_row_does_not_copy_missing_bank_columns_from_summary_or_remark(self) -> None:
        builder = BankDetailSqlProjectionBuilder(connection=FakeConnection())

        row = builder._normalize_transaction_row(  # noqa: SLF001
            {
                "id": "txn-sql-cmbc",
                "transaction_id": "uuid-sql-cmbc",
                "account_no": "641979486",
                "txn_direction": "expense",
                "counterparty_name_raw": "供应商",
                "amount": "100.00",
                "signed_amount": "-100.00",
                "balance": "900.00",
                "txn_date": "2026-04-16",
                "trade_time": "2026-04-16 11:09:14+08:00",
                "summary": "旧摘要",
                "remark": "民生客户附言",
                "bank_text_fields": [
                    {"label": "客户附言", "value": "民生客户附言"},
                ],
                "raw_payload": {
                    "normalized_payload": {
                        "imported_bank_name": "民生银行",
                        "imported_bank_last4": "9486",
                    }
                },
            }
        )

        self.assertEqual(row["trade_time"], "2026-04-16 11:09:14")
        self.assertEqual(row["purpose_text"], "")
        self.assertEqual(row["summary_text"], "")
        self.assertEqual(row["note_text"], "民生客户附言")

    def test_rebuild_persists_internal_transfer_auto_category_before_text_category(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-transfer-out",
                        "transaction_id": "uuid-transfer-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                        "amount": "13000.00",
                        "signed_amount": "-13000.00",
                        "balance": "900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 10:00:00",
                        "summary": "手续费",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-transfer-in",
                        "transaction_id": "uuid-transfer-in",
                        "account_no": "6227000011111410",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "云南溯源科技有限公司工商银行账户",
                        "amount": "13000.00",
                        "signed_amount": "13000.00",
                        "balance": "13900.00",
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 12:00:00",
                        "summary": "工资",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": "1410"}},
                    },
                ],
                [],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        self.assertEqual(result["row_count"], 2)
        self.assertEqual({row["auto_category_code"] for row in repository.saved_rows}, {"internal_transfer"})
        self.assertEqual({row["effective_category_code"] for row in repository.saved_rows}, {"internal_transfer"})
        self.assertEqual({row["auto_category_label"] for row in repository.saved_rows}, {"内部往来款"})

    def test_rebuild_uses_boundary_context_for_cross_month_internal_transfer_auto_category(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            rows=[
                [
                    {
                        "id": "txn-transfer-out",
                        "transaction_id": "uuid-transfer-out",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "云南溯源科技有限公司建设银行账户",
                        "amount": "13000.00",
                        "signed_amount": "-13000.00",
                        "balance": "900.00",
                        "txn_date": "2026-04-30",
                        "trade_time": "2026-04-30 23:10:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "工商银行", "imported_bank_last4": "6386"}},
                    },
                    {
                        "id": "txn-transfer-in",
                        "transaction_id": "uuid-transfer-in",
                        "account_no": "6227000011111410",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "income",
                        "counterparty_name_raw": "云南溯源科技有限公司工商银行账户",
                        "amount": "13000.00",
                        "signed_amount": "13000.00",
                        "balance": "13900.00",
                        "txn_date": "2026-05-01",
                        "trade_time": "2026-05-01 00:20:00",
                        "summary": "内部转账",
                        "remark": "",
                        "raw_payload": {"normalized_payload": {"imported_bank_name": "建设银行", "imported_bank_last4": "1410"}},
                    },
                ],
                [],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        self.assertEqual(result["row_count"], 1)
        self.assertEqual([row["id"] for row in repository.saved_rows], ["txn-transfer-out"])
        self.assertEqual(repository.saved_rows[0]["auto_category_code"], "internal_transfer")
        self.assertEqual(repository.saved_rows[0]["effective_category_code"], "internal_transfer")


class FakeProjectionBuilder:
    def __init__(self) -> None:
        self.rebuilt: list[str] = []

    def list_bank_detail_scope_shards(self, scope_key: str) -> list[str]:
        self.rebuilt.append(f"list:{scope_key}")
        return ["2026-04", "2026-05"]

    def rebuild_bank_detail_read_model_scope(self, scope_key: str, *, source_version: int | None = None) -> dict[str, object]:
        self.rebuilt.append(f"rebuild:{scope_key}:{source_version}")
        return {"scope_key": scope_key, "row_count": 1}


class FakeQueue:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, object]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.enqueued.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str, source_version: object = None) -> bool:
        self.completed.append((scope_type, scope_key, source_version))
        return True


class BankDetailReadModelRefreshServiceTests(unittest.TestCase):
    def test_all_scope_fans_out_to_month_shards_without_sync_history_rebuild(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("all"))

        self.assertEqual(payload["enqueued_scope_keys"], ["2026-04", "2026-05"])
        self.assertEqual(
            queue.enqueued,
            [
                ("bank_detail", "2026-04", "bank_detail_all_shard"),
                ("bank_detail", "2026-05", "bank_detail_all_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("bank_detail", "all", 7)])
        self.assertEqual(builder.rebuilt, ["list:all"])

    def test_month_scope_rebuilds_and_completes_matching_source_version(self) -> None:
        builder = FakeProjectionBuilder()
        queue = FakeQueue()
        service = BankDetailReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )

        payload = service.handle_runtime_event(runtime_event("2026-05"))

        self.assertEqual(payload["scope_key"], "2026-05")
        self.assertEqual(builder.rebuilt, ["rebuild:2026-05:7"])
        self.assertEqual(queue.completed, [("bank_detail", "2026-05", 7)])


if __name__ == "__main__":
    unittest.main()

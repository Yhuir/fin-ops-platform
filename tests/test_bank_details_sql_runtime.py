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
    def __init__(
        self,
        rows: list[object] | None = None,
        app_settings_payload: dict[str, object] | None = None,
        dirty_scope_rows: list[dict[str, object]] | None = None,
    ) -> None:
        self.rows = list(rows or [])
        self.app_settings_payload = app_settings_payload
        self.dirty_scope_rows = list(dirty_scope_rows or [])
        self.calls: list[tuple[str, str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.calls.append(("fetch_one", sql, params))
        if "from app.app_settings" in " ".join(sql.lower().split()):
            if self.app_settings_payload is not None:
                return {"settings_payload": self.app_settings_payload}
            if self.rows and isinstance(self.rows[0], dict) and "settings_payload" in self.rows[0]:
                value = self.rows.pop(0)
                return value if isinstance(value, dict) else None
            return None
        value = self.rows.pop(0) if self.rows else None
        return value if isinstance(value, dict) else None

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        self.calls.append(("fetch_all", sql, params))
        if "from job.read_model_dirty_scopes" in " ".join(sql.lower().split()):
            return list(self.dirty_scope_rows)
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

    def test_transactions_filter_uncategorized_rows_by_null_effective_category(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05")],
                {"total": 1},
                [{"category_code": "uncategorized", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-uncategorized",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "供应商",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "普通付款",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "effective_category_code": None,
                            "effective_category_label": None,
                        },
                        "raw_payload": {},
                        "summary": "普通付款",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            category_code="uncategorized",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rows"][0]["id"], "txn-uncategorized")
        self.assertEqual(payload["category_counts"]["uncategorized"], 1)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("effective_category_code is null", sql_text)
        self.assertNotIn("effective_category_code = %s", sql_text)
        self.assertNotIn("uncategorized", [param for call in connection.calls for param in call[2]])

    def test_transactions_serve_previous_schema_rows_while_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", schema_version=BANK_DETAIL_READ_MODEL_SCHEMA_VERSION - 1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-old-schema",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "银行",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "手续费",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "auto_category_code": "fee",
                            "auto_category_label": "手续费",
                            "effective_category_code": "fee",
                            "effective_category_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "手续费",
                        "purpose": "",
                    }
                ],
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
        self.assertEqual(payload["read_model_status"], "schema_mismatch")
        self.assertEqual(payload["read_model_scope_keys"], ["2026-05"])
        self.assertEqual(payload["rows"][0]["id"], "txn-old-schema")
        self.assertEqual(payload["category_counts"]["fee"], 1)
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("schema_version = %s", sql_text)

    def test_accounts_serve_previous_schema_rows_while_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", schema_version=BANK_DETAIL_READ_MODEL_SCHEMA_VERSION - 1)],
                [
                    {
                        "account_key": "icbc:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 1,
                        "latest_balance": "90.00",
                        "latest_balance_at": "2026-05-01 10:00:00",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(
            date_from="2026-05-01",
            date_to="2026-05-31",
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "schema_mismatch")
        self.assertEqual(payload["accounts"][0]["account_key"], "icbc:6386")
        self.assertEqual(payload["total_balance"], "90.00")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from read_model.bank_detail_rows", sql_text)
        self.assertNotIn("schema_version = %s", sql_text)

    def test_transactions_treat_pending_bank_detail_dirty_scope_as_refreshing(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-05", row_count=1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-refreshing",
                            "trade_time": "2026-05-01 10:00:00",
                            "counterparty_name": "银行",
                            "direction": "expense",
                            "direction_label": "支",
                            "amount": "10.00",
                            "balance": "90.00",
                            "summary": "手续费",
                            "purpose": "",
                            "bank_name": "工商银行",
                            "account_last4": "6386",
                            "auto_category_code": "fee",
                            "auto_category_label": "手续费",
                            "effective_category_code": "fee",
                            "effective_category_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "手续费",
                        "purpose": "",
                    }
                ],
            ],
            dirty_scope_rows=[
                {
                    "scope_key": "2026-05",
                    "status": "pending",
                    "updated_at": "2026-05-27T21:00:00+00:00",
                    "last_error": None,
                    "source_version": 8,
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-05-01",
            date_to="2026-05-31",
            page=1,
            page_size=100,
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"][0]["id"], "txn-refreshing")
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 100, "total": 1})
        self.assertEqual(payload["dirty_scopes"][0]["scope_key"], "2026-05")
        self.assertEqual(payload["read_model_scope_signatures"]["2026-05"]["dirty_status"], "pending")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("from job.read_model_dirty_scopes", sql_text)
        self.assertIn("from read_model.bank_detail_rows", sql_text)

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

    def test_transactions_filter_by_effective_primary_and_sub_category_labels(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-04", row_count=1)],
                {"total": 1},
                [{"category_code": "fee", "count": 1}],
                [
                    {
                        "payload": {
                            "id": "txn-fee",
                            "effective_category_code": "fee",
                            "effective_category_primary_label": "费用",
                            "effective_category_sub_label": "手续费",
                        },
                        "raw_payload": {},
                        "summary": "",
                        "purpose": "",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_transactions(
            date_from="2026-04-01",
            date_to="2026-04-30",
            category_primary_label="费用",
            category_sub_label="手续费",
        )

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rows"][0]["id"], "txn-fee")
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertIn("effective_category_primary_label = %s", sql_text)
        self.assertIn("effective_category_sub_label = %s", sql_text)
        flattened_params = [param for _kind, _sql, params in connection.calls for param in params]
        self.assertIn("费用", flattened_params)
        self.assertIn("手续费", flattened_params)

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

    def test_accounts_use_all_available_rows_for_latest_balances_and_date_range_only_for_counts(self) -> None:
        connection = FakeConnection(
            rows=[
                [scope_row("2026-03", row_count=1)],
                [
                    {
                        "account_key": "工商银行:6386",
                        "bank_name": "工商银行",
                        "account_last4": "6386",
                        "transaction_count": 1,
                        "latest_balance": "117644.93",
                        "latest_balance_at": "2026-05-02 09:00:00",
                    }
                ],
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_bank_detail_accounts(date_from="2026-03-01", date_to="2026-03-31")

        self.assertIsNotNone(payload)
        self.assertEqual(payload["accounts"][0]["transaction_count"], 1)
        self.assertEqual(payload["accounts"][0]["latest_balance"], "117644.93")
        self.assertEqual(payload["total_balance"], "117644.93")
        account_sql = next(
            " ".join(call[1].lower().split())
            for call in connection.calls
            if "latest_balances" in call[1].lower()
        )
        self.assertIn("filtered as", account_sql)
        self.assertIn("all_rows as", account_sql)
        self.assertIn("from all_rows", account_sql)
        self.assertIn("from filtered", account_sql)


class BankDetailSqlProjectionBuilderTests(unittest.TestCase):
    def test_rebuild_loads_custom_auto_tag_rules_from_app_settings(self) -> None:
        repository = CaptureBankDetailReadModelRepository()
        connection = FakeConnection(
            app_settings_payload={
                "bank_transaction_tags": {
                    "version": 2,
                    "definitions": [
                        {
                            "code": "custom_netbank_certificate_service_fee",
                            "label": "网银证书服务费",
                            "path": ["自动识别", "网银证书服务费"],
                            "output_primary_label": "费用",
                            "output_sub_label": "手续费",
                            "source": "custom",
                            "status": "active",
                            "priority": 80,
                            "rule_code": "custom_netbank_certificate_service_fee",
                            "rules": {
                                "match_fields": [
                                    "all_text",
                                    "detail_text",
                                    "note_text",
                                    "summary_text",
                                    "purpose_text",
                                    "counterparty_name",
                                ],
                                "exact": [],
                                "contains": [],
                                "contains_all": ["网银", "服务费"],
                                "excludes": [],
                            },
                        }
                    ],
                },
            },
            rows=[
                [
                    {
                        "id": "txn-netbank-certificate-fee",
                        "transaction_id": "uuid-netbank-certificate-fee",
                        "account_no": "6222000011116386",
                        "account_name": "云南溯源科技有限公司",
                        "txn_direction": "expense",
                        "counterparty_name_raw": "中国工商银行云南昆明分行",
                        "amount": "100.00",
                        "signed_amount": "-100.00",
                        "balance": "2138.00",
                        "currency": "CNY",
                        "txn_date": "2026-01-24",
                        "trade_time": "2026-01-24 21:48:34",
                        "summary": "网银证书服务费",
                        "remark": "",
                        "bank_text_fields": [{"label": "摘要", "value": "网银证书服务费"}],
                        "raw_payload": {
                            "normalized_payload": {
                                "imported_bank_name": "工商银行",
                                "imported_bank_last4": "6386",
                            }
                        },
                    }
                ],
                [],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection, read_model_repository=repository)

        result = builder.rebuild_bank_detail_read_model_scope("2026-01", source_version=9)

        self.assertEqual(result["row_count"], 1)
        self.assertEqual(repository.saved_rows[0]["auto_category_code"], "custom_netbank_certificate_service_fee")
        self.assertEqual(repository.saved_rows[0]["auto_category_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["auto_category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["auto_category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["auto_category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["effective_category_code"], "custom_netbank_certificate_service_fee")
        self.assertEqual(repository.saved_rows[0]["effective_category_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["effective_category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["effective_category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["effective_category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["category_primary_label"], "费用")
        self.assertEqual(repository.saved_rows[0]["category_sub_label"], "手续费")
        self.assertEqual(repository.saved_rows[0]["category_label_path"], ["费用", "手续费"])
        self.assertEqual(repository.saved_rows[0]["source_versions"]["bank_auto_tag_rules_version"], 2)

    def test_relation_tags_use_pair_relation_row_types_for_oa_attachment_invoices(self) -> None:
        connection = FakeConnection(
            rows=[
                [
                    {
                        "case_id": "CASE-AUTO-0003",
                        "row_ids": [
                            "txn_imported_1242",
                            "oa-exp-1964",
                            "oa-att-inv-oa-exp-1964-96685fdf79d36cc6",
                        ],
                        "row_types": ["bank", "oa", "invoice"],
                    }
                ],
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection)

        tags = builder._load_relation_tags(["txn_imported_1242"])  # noqa: SLF001

        self.assertEqual(tags["txn_imported_1242"]["oa_relation_tag"], "有oa")
        self.assertEqual(tags["txn_imported_1242"]["invoice_relation_tag"], "有发票")
        self.assertEqual(tags["txn_imported_1242"]["relation_case_id"], "CASE-AUTO-0003")

    def test_relation_tags_do_not_read_legacy_candidate_matches_in_projection(self) -> None:
        connection = FakeConnection(
            rows=[
                [],
            ]
        )
        builder = BankDetailSqlProjectionBuilder(connection=connection)

        tags = builder._load_relation_tags(["txn-oa-bank"])  # noqa: SLF001

        self.assertEqual(tags, {})
        sql_text = " ".join(" ".join(call[1].lower().split()) for call in connection.calls)
        self.assertNotIn("workbench_candidate_matches", sql_text)

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

    def test_rebuild_embeds_internal_transfer_counterpart_summary(self) -> None:
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
                        "txn_date": "2026-04-03",
                        "trade_time": "2026-04-03 12:00:00",
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

        builder.rebuild_bank_detail_read_model_scope("2026-04", source_version=9)

        rows_by_id = {str(row["id"]): row for row in repository.saved_rows}
        out_counterpart = rows_by_id["txn-transfer-out"]["internal_transfer_counterpart"]
        self.assertEqual(
            out_counterpart,
            {
                "transaction_id": "txn-transfer-in",
                "trade_time": "2026-04-03 12:00:00",
                "bank_name": "建设银行",
                "account_last4": "1410",
                "amount": "13000.00",
                "direction_label": "收",
                "counterparty_name": "云南溯源科技有限公司工商银行账户",
            },
        )
        self.assertEqual(rows_by_id["txn-transfer-out"]["payload"]["internal_transfer_counterpart"], out_counterpart)
        in_counterpart = rows_by_id["txn-transfer-in"]["internal_transfer_counterpart"]
        self.assertEqual(in_counterpart["transaction_id"], "txn-transfer-out")
        self.assertEqual(in_counterpart["bank_name"], "工商银行")
        self.assertEqual(in_counterpart["account_last4"], "6386")
        self.assertEqual(in_counterpart["direction_label"], "支")

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

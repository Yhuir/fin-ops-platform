from __future__ import annotations

from decimal import Decimal
import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.invoice_usage_collection_read_model_refresh import (
    InvoiceUsageCollectionReadModelRefreshService,
)
from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    input_invoice_usage_source_versions,
    oa_pending_payment_source_versions,
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import InvoiceUsageCollectionSqlProjectionBuilder
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueEvent
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str, int | None]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int | str | None = None,
    ) -> None:
        self.completed.append((tenant_id, scope_type, scope_key, int(source_version) if source_version is not None else None))


class EmptyTransactionConnection:
    def transaction(self) -> "EmptyTransactionConnection":
        return self

    def __enter__(self) -> "EmptyTransactionConnection":
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def fetch_all(self, *_args: object, **_kwargs: object) -> list[dict]:
        return []


class FreshEmptyWorkbenchRelationFacade:
    @property
    def last_source_versions(self) -> dict[str, object]:
        return {}

    def list_by_month(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return {
            "status": "fresh",
            "rows": [],
            "groups": [],
            "source_versions": {},
            "read_model_scope_keys": [],
            "refresh_enqueued": False,
            "stale_reasons": [],
        }

    def get_by_row_ids(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        return self.list_by_month()


class InvoiceReadModelConnection:
    def __init__(
        self,
        *,
        input_rows: list[dict] | None = None,
        output_rows: list[dict] | None = None,
        oa_rows: list[dict] | None = None,
        input_scope_rows: list[dict] | None = None,
        output_scope_rows: list[dict] | None = None,
        oa_scope_rows: list[dict] | None = None,
        dirty: bool = False,
        scope_exists: bool = True,
    ) -> None:
        self.input_rows = list(input_rows or [])
        self.output_rows = list(output_rows or [])
        self.oa_rows = list(oa_rows or [])
        self.input_scope_rows = list(input_scope_rows or [])
        self.output_scope_rows = list(output_scope_rows or [])
        self.oa_scope_rows = list(oa_scope_rows or [])
        self.dirty = dirty
        self.scope_exists = scope_exists
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.input_invoice_usage_rows" in normalized:
            return self.input_rows
        if "from read_model.output_invoice_collection_rows" in normalized:
            return self.output_rows
        if "from read_model.oa_pending_payment_rows" in normalized:
            return self.oa_rows
        if "from read_model.input_invoice_usage_scopes" in normalized:
            return self.input_scope_rows
        if "from read_model.output_invoice_collection_scopes" in normalized:
            return self.output_scope_rows
        if "from read_model.oa_pending_payment_scopes" in normalized:
            return self.oa_scope_rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-25T03:00:00+00:00"} if self.dirty else None
        if "from read_model.input_invoice_usage_scopes" in normalized:
            return {"scope_key": params[0] if params else "2026-05", "source_versions": input_invoice_usage_source_versions()} if self.scope_exists else None
        if "from read_model.output_invoice_collection_scopes" in normalized:
            return {"scope_key": params[0] if params else "2026-05", "source_versions": output_invoice_collection_source_versions()} if self.scope_exists else None
        if "from read_model.oa_pending_payment_scopes" in normalized:
            return {"scope_key": params[0] if params else "2026-05", "source_versions": oa_pending_payment_source_versions()} if self.scope_exists else None
        if "from read_model.input_invoice_usage_rows" in normalized:
            return {
                "count": len(self.input_rows),
                "total_with_tax": "118.00",
                "matched_oa_count": 1,
                "matched_bank_transaction_count": 1,
                "pending_count": 0,
            }
        if "from read_model.output_invoice_collection_rows" in normalized:
            return {
                "count": len(self.output_rows),
                "total_with_tax": "118.00",
                "collected_amount": "118.00",
                "pending_amount": "0.00",
                "pending_collection_count": 0,
                "partial_collection_count": 0,
                "receipt_pending_count": 1,
            }
        if "from read_model.oa_pending_payment_rows" in normalized:
            if "select scope_key, source_versions, payload, raw_payload" in normalized:
                if not self.oa_rows:
                    return None
                row = dict(self.oa_rows[0])
                row.setdefault("scope_key", "2026-05")
                row.setdefault("source_versions", oa_pending_payment_source_versions())
                return row
            return {
                "count": len(self.oa_rows),
                "oa_amount_total": "100.00",
                "bank_paid_total": "100.00",
            }
        return None


class ProjectionCoreRepository:
    def __init__(
        self,
        *,
        invoices: list[Invoice] | None = None,
        transactions: list[BankTransaction] | None = None,
    ) -> None:
        self.invoices = list(invoices or [])
        self.transactions = list(transactions or [])

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        **_kwargs: object,
    ) -> tuple[list[Invoice], int]:
        rows = list(self.invoices)
        if month:
            rows = [invoice for invoice in rows if str(invoice.invoice_date or "").startswith(month[:7])]
        if invoice_type:
            rows = [invoice for invoice in rows if invoice.invoice_type.value == invoice_type]
        offset = (page - 1) * page_size
        return rows[offset : offset + page_size], len(rows)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **_kwargs: object,
    ) -> tuple[list[BankTransaction], int]:
        offset = (page - 1) * page_size
        return self.transactions[offset : offset + page_size], len(self.transactions)


class EmptyWorkbenchRepository:
    def load_workbench_pair_relations(self) -> dict[str, object]:
        return {"pair_relations": {}}


class EmptyOAProjectionRepository:
    def list_application_records_by_row_ids(self, _row_ids: list[str]) -> list[object]:
        return []

    def list_all_application_records(self) -> list[object]:
        return []


class RecordingInvoiceRelationReadRepository:
    def __init__(self) -> None:
        self.saved_input: dict[str, object] | None = None
        self.saved_output: dict[str, object] | None = None
        self.saved_oa: dict[str, object] | None = None
        self.marked_input: dict[str, object] | None = None
        self.marked_output: dict[str, object] | None = None
        self.marked_oa: dict[str, object] | None = None

    def save_input_invoice_usage_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_input = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def save_output_invoice_collection_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_output = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def mark_input_invoice_usage_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_input = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}

    def mark_output_invoice_collection_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_output = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}

    def save_oa_pending_payment_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, object]],
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.saved_oa = {"scope_key": scope_key, "rows": rows, "source_versions": source_versions}

    def mark_oa_pending_payment_scope(
        self,
        *,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.marked_oa = {"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}


class WriteRecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, object]] = []

    def execute(self, sql: str, params: object = ()) -> None:
        self.executed.append((" ".join(sql.lower().split()), params))


class InvoiceUsageCollectionSqlRuntimeTests(unittest.TestCase):
    def test_input_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        repository = PostgresReadModelRepository(InvoiceReadModelConnection(input_rows=[], dirty=False, scope_exists=True))

        payload = repository.list_input_invoice_usage_rows(month="2026-05", page=1, page_size=50)

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

    def test_input_repository_uses_native_bank_account_and_direction_columns(self) -> None:
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_rows(
            month="2026-05",
            filters='[{"field":"bank_account","operator":"in","values":["交通银行 3847"]},{"field":"bank_direction","operator":"in","values":["outflow"]}]',
            sort_field="bank_account",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("bank_account", executed_sql)
        self.assertIn("bank_direction", executed_sql)
        self.assertIn("bank_account asc", executed_sql)

    def test_input_repository_save_persists_bank_account_and_direction_columns(self) -> None:
        connection = WriteRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_input_invoice_usage_rows(
            scope_key="2026-05",
            rows=[
                {
                    "id": "input_invoice_usage_row_1",
                    "invoiceId": "invoice-1",
                    "invoice": {"invoiceNo": "1001", "invoiceDate": "2026-05-21", "totalWithTax": "118.00"},
                    "paymentStatus": {"code": "pending", "label": "待处理"},
                    "oa": {"relationCount": 1},
                    "bankTransactions": {
                        "primaryBankTransactionId": "bank-1",
                        "tradeTime": "2026-05-21 10:00:00",
                        "amount": "118.00",
                        "direction": "outflow",
                        "directionLabel": "支出",
                        "bankName": "交通银行",
                        "accountLast4": "3847",
                        "bankAccount": "交通银行 3847",
                        "relationCount": 1,
                    },
                }
            ],
            source_versions=input_invoice_usage_source_versions(),
        )

        insert_calls = [(sql, params) for sql, params in connection.executed if "insert into read_model.input_invoice_usage_rows" in sql]
        self.assertEqual(len(insert_calls), 1)
        sql, params = insert_calls[0]
        self.assertIn("bank_account", sql)
        self.assertIn("bank_direction", sql)
        self.assertEqual(params["bank_account"], "交通银行 3847")
        self.assertEqual(params["bank_direction"], "outflow")

    def test_input_repository_all_scope_keeps_base_source_versions_when_relation_versions_differ(self) -> None:
        base_versions = input_invoice_usage_source_versions()
        connection = InvoiceReadModelConnection(
            input_rows=[
                {
                    "payload": {
                        "id": "input_invoice_usage_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "paymentStatus": {"code": "pending", "label": "待处理"},
                        "oa": {"relationCount": 1},
                        "bankTransactions": {"relationCount": 1},
                    },
                    "raw_payload": {},
                }
            ],
            input_scope_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": {
                        **base_versions,
                        "workbench_relation_source_versions": {
                            "workbench_pair_relations_updated_at": "2026-06-10 01:39:49+08",
                            "workbench_reconciliation_decisions_updated_at": "2026-06-10 03:06:22+08",
                        },
                    },
                    "cache_status": "fresh",
                },
                {
                    "scope_key": "2026-04",
                    "source_versions": {
                        **base_versions,
                        "workbench_relation_source_versions": {
                            "workbench_pair_relations_updated_at": "2026-06-10 09:58:40+08",
                            "workbench_reconciliation_decisions_updated_at": "2026-06-10 09:13:13+08",
                        },
                    },
                    "cache_status": "fresh",
                },
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_input_invoice_usage_rows(month=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["source_versions"], base_versions)

    def test_output_repository_uses_native_columns_for_filters_and_sort(self) -> None:
        connection = InvoiceReadModelConnection(
            output_rows=[
                {
                    "payload": {
                        "id": "output_invoice_collection_row_1",
                        "invoiceId": "invoice-1",
                        "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                        "collectionStatus": {"code": "collected", "label": "已收款", "collectedAmount": "118.00", "pendingAmount": "0.00"},
                        "bankTransactions": {"relationCount": 1},
                        "redInvoiceRelation": {"relationCount": 0},
                        "receipt": {"status": "pending", "label": "待出收据"},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_output_invoice_collection_rows(
            month="2026-05",
            filters='[{"field":"collection_status","operator":"in","values":["collected"]}]',
            sort_field="buyer_name",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("collection_status", executed_sql)
        self.assertIn("buyer_name asc", executed_sql)

    def test_oa_repository_uses_native_columns_for_filters_sort_and_bank_total_summary(self) -> None:
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00"},
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"paidTotal": "100.00"},
                        "invoice": {},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(
            month="2026-05",
            filters='[{"field":"payment_status","operator":"in","values":["paid"]}]',
            sort_field="bank_trade_time",
            sort_direction="desc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["bankPaidTotal"], "100.00")
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("payment_status", executed_sql)
        self.assertIn("bank_trade_time desc", executed_sql)

    def test_oa_repository_all_scope_aggregates_monthly_scope_source_versions(self) -> None:
        source_versions = oa_pending_payment_source_versions()
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00"},
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"paidTotal": "100.00"},
                        "invoice": {},
                    },
                    "raw_payload": {},
                }
            ],
            oa_scope_rows=[
                {"scope_key": "2026-05", "source_versions": source_versions, "cache_status": "fresh"},
                {"scope_key": "2026-04", "source_versions": source_versions, "cache_status": "fresh"},
            ],
            scope_exists=False,
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_oa_pending_payment_rows(month=None, page=1, page_size=50)

        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["source_versions"], source_versions)
        self.assertEqual(payload["pagination"]["total"], 1)
        executed_scope_fetches = [
            sql
            for sql, _params in connection.fetch_all_calls
            if "from read_model.oa_pending_payment_scopes" in sql
        ]
        self.assertTrue(executed_scope_fetches)

    def test_oa_repository_save_persists_source_versions_and_bank_total(self) -> None:
        connection = WriteRecordingConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_oa_pending_payment_rows(
            scope_key="2026-05",
            rows=[
                {
                    "id": "oa_pending_payment_row_1",
                    "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00", "month": "2026-05"},
                    "paymentStatus": {"code": "paid", "label": "已支付"},
                    "bankTransaction": {
                        "primaryBankTransactionId": "bank-1",
                        "tradeTime": "2026-05-21 10:00:00",
                        "amount": "40.00",
                        "paidTotal": "100.00",
                    },
                    "invoice": {},
                }
            ],
            source_versions=oa_pending_payment_source_versions(),
        )

        insert_calls = [(sql, params) for sql, params in connection.executed if "insert into read_model.oa_pending_payment_rows" in sql]
        self.assertEqual(len(insert_calls), 1)
        sql, params = insert_calls[0]
        self.assertIn("bank_paid_total", sql)
        self.assertEqual(params["bank_paid_total"], "100.00")
        self.assertEqual(params["source_versions"].obj, oa_pending_payment_source_versions())

    def test_oa_repository_detail_lookups_use_native_columns(self) -> None:
        connection = InvoiceReadModelConnection(
            oa_rows=[
                {
                    "scope_key": "2026-05",
                    "source_versions": oa_pending_payment_source_versions(),
                    "payload": {
                        "id": "oa_pending_payment_row_1",
                        "oa": {"id": "oa-1", "applicantName": "张三", "amount": "100.00"},
                        "paymentStatus": {"code": "paid", "label": "已支付"},
                        "bankTransaction": {"primaryBankTransactionId": "bank-1", "paidTotal": "100.00"},
                        "invoice": {"primaryInvoiceId": "inv-1"},
                    },
                    "raw_payload": {},
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        oa_payload = repository.get_oa_pending_payment_row_by_oa_id("oa-1")
        bank_payload = repository.get_oa_pending_payment_row_by_bank_transaction_id("bank-1")
        invoice_payload = repository.get_oa_pending_payment_row_by_invoice_id("inv-1")
        row_payload = repository.get_oa_pending_payment_row_by_row_id("oa_pending_payment_row_1")

        self.assertEqual(oa_payload["row"]["oa"]["id"], "oa-1")
        self.assertEqual(bank_payload["row"]["bankTransaction"]["primaryBankTransactionId"], "bank-1")
        self.assertEqual(invoice_payload["row"]["invoice"]["primaryInvoiceId"], "inv-1")
        self.assertEqual(row_payload["row"]["id"], "oa_pending_payment_row_1")
        executed_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertIn("oa_id = %s", executed_sql)
        self.assertIn("bank_transaction_id = %s", executed_sql)
        self.assertIn("invoice_id = %s", executed_sql)
        self.assertIn("row_id = %s", executed_sql)

    def test_input_api_miss_enqueues_refresh_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_sql_read_repository = type(
            "InputRepo",
            (),
            {"list_input_invoice_usage_rows": lambda *_args, **_kwargs: None},
        )()
        app._input_invoice_usage_query_service = type(
            "InputService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("input API miss must not live scan"))},
        )()

        response = app._handle_api_input_invoice_usage_rows({"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_miss")])

    def test_input_api_source_version_miss_enqueues_refresh_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_sql_read_repository = type(
            "InputRepo",
            (),
            {
                "list_input_invoice_usage_rows": lambda *_args, **_kwargs: {
                    "rows": [
                        {
                            "id": "stale-source-row",
                            "invoice": {},
                            "paymentStatus": {},
                            "oa": {},
                            "bankTransactions": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"invoiceCount": 1},
                    "filterConfig": [],
                    "refresh_status": "fresh",
                    "source_versions": {},
                }
            },
        )()

        response = app._handle_api_input_invoice_usage_rows({"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("input_invoice_usage_source_version_missing", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("input_invoice_usage", "2026-05", "api_source_versions_stale")])

    def test_input_api_all_scope_uses_rows_when_month_relation_versions_differ(self) -> None:
        base_versions = input_invoice_usage_source_versions()
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            import_service=ImportNormalizationService(),
        )
        app._input_invoice_usage_sql_read_repository = PostgresReadModelRepository(
            InvoiceReadModelConnection(
                input_rows=[
                    {
                        "payload": {
                            "id": "input_invoice_usage_row_1",
                            "invoiceId": "invoice-1",
                            "invoice": {"invoiceNo": "1001", "totalWithTax": "118.00"},
                            "paymentStatus": {"code": "pending", "label": "待处理"},
                            "oa": {"relationCount": 1},
                            "bankTransactions": {"relationCount": 1},
                        },
                        "raw_payload": {},
                    }
                ],
                input_scope_rows=[
                    {
                        "scope_key": "2026-05",
                        "source_versions": {
                            **base_versions,
                            "workbench_relation_source_versions": {
                                "workbench_pair_relations_updated_at": "2026-06-10 01:39:49+08",
                            },
                        },
                        "cache_status": "fresh",
                    },
                    {
                        "scope_key": "2026-04",
                        "source_versions": {
                            **base_versions,
                            "workbench_relation_source_versions": {
                                "workbench_pair_relations_updated_at": "2026-06-10 09:58:40+08",
                            },
                        },
                        "cache_status": "fresh",
                    },
                ],
                scope_exists=False,
            )
        )

        response = app._handle_api_input_invoice_usage_rows({"page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["id"], "input_invoice_usage_row_1")
        self.assertNotIn("read_model_stale_reasons", payload)
        self.assertEqual(queue.refreshes, [])

    def test_output_api_stale_returns_refreshing_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._import_service = ImportNormalizationService()
        app._workbench_pair_relation_service = WorkbenchPairRelationService()
        app._output_invoice_collection_sql_read_repository = type(
            "OutputRepo",
            (),
            {
                "list_output_invoice_collection_rows": lambda *_args, **_kwargs: {
                    "rows": [
                        {
                            "id": "stale-row",
                            "invoice": {},
                            "collectionStatus": {},
                            "bankTransactions": {},
                            "redInvoiceRelation": {},
                            "receipt": {},
                        }
                    ],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"invoiceCount": 1},
                    "filterConfig": [],
                    "refresh_status": "stale",
                }
            },
        )()

        response = app._handle_api_output_invoice_collections_rows({"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "api_stale")])

    def test_projection_builder_persists_invoice_relation_source_versions(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(
            connection=EmptyTransactionConnection(),
            workbench_relation_read_facade=FreshEmptyWorkbenchRelationFacade(),
        )
        builder._core_repository = ProjectionCoreRepository(
            invoices=[
                self._invoice("input-invoice-1", InvoiceType.INPUT),
                self._invoice("output-invoice-1", InvoiceType.OUTPUT),
            ]
        )
        builder._workbench_repository = EmptyWorkbenchRepository()
        builder._oa_projection_repository = EmptyOAProjectionRepository()
        builder._read_repository = read_repository

        builder._oa_projection_repository = type(
            "OaProjection",
            (),
            {"list_all_application_records": lambda _self: []},
        )()

        input_result = builder.rebuild_input_invoice_usage_read_model_scope("2026-05")
        output_result = builder.rebuild_output_invoice_collection_read_model_scope("2026-05")
        oa_result = builder.rebuild_oa_pending_payment_read_model_scope("2026-05")

        self.assertEqual(input_result["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(output_result["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(oa_result["source_versions"], oa_pending_payment_source_versions())
        self.assertIsNotNone(read_repository.saved_input)
        self.assertIsNotNone(read_repository.saved_output)
        self.assertIsNotNone(read_repository.saved_oa)
        self.assertEqual(read_repository.saved_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.saved_output["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(read_repository.saved_oa["source_versions"], oa_pending_payment_source_versions())
        self.assertEqual(input_result["row_count"], 1)
        self.assertEqual(output_result["row_count"], 1)
        self.assertEqual(oa_result["row_count"], 0)

    def test_projection_builder_marks_empty_scopes_with_source_versions(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=object())
        builder._read_repository = read_repository

        builder.mark_input_invoice_usage_scope_empty("2026-05")
        builder.mark_output_invoice_collection_scope_empty("2026-05")
        builder.mark_oa_pending_payment_scope_empty("2026-05")

        self.assertEqual(read_repository.marked_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.marked_output["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(read_repository.marked_oa["source_versions"], oa_pending_payment_source_versions())

    def test_refresh_handler_expands_all_scopes_and_completes_with_source_version(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(f"input-list:{scope_key}")
                return ["2026-05", "2026-04"]

            def rebuild_input_invoice_usage_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.calls.append(f"input-build:{scope_key}")
                return {"scope_key": scope_key, "row_count": 1}

            def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        service = InvoiceUsageCollectionReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="input_invoice_usage.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="input_invoice_usage",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(
            queue.refreshes,
            [
                ("input_invoice_usage", "2026-05", "input_invoice_usage_month_shard"),
                ("input_invoice_usage", "2026-04", "input_invoice_usage_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "input_invoice_usage", "all", 7)])

    def test_oa_refresh_handler_expands_all_scopes_and_completes_with_source_version(self) -> None:
        class FakeBuilder:
            def list_oa_pending_payment_scope_shards(self, scope_key: str) -> list[str]:
                self.scope_key = scope_key
                return ["2026-05"]

            def rebuild_oa_pending_payment_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"all scope should enqueue shards before rebuild: {scope_key}")

        queue = QueueRecorder()
        service = InvoiceUsageCollectionReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-oa",
            tenant_id="tenant-a",
            event_type="oa_pending_payment.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="oa_pending_payment",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
            source_version=9,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05"], "row_count": 0})
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "oa_pending_payment_month_shard")])
        self.assertEqual(queue.completed, [("tenant-a", "oa_pending_payment", "all", 9)])

    def test_rabbitmq_event_types_include_invoice_usage_collection_read_models(self) -> None:
        self.assertIn("input_invoice_usage.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("output_invoice_collection.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("oa_pending_payment.read_model.refresh", SUPPORTED_EVENT_TYPES)
        self.assertIn("input_invoice_usage.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("output_invoice_collection.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("oa_pending_payment.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)

    @staticmethod
    def _invoice(invoice_id: str, invoice_type: InvoiceType) -> Invoice:
        counterparty = Counterparty(
            id=f"cp-{invoice_id}",
            name="测试往来单位",
            normalized_name="测试往来单位",
            counterparty_type="supplier" if invoice_type == InvoiceType.INPUT else "customer",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=invoice_type,
            invoice_no=f"NO-{invoice_id}",
            counterparty=counterparty,
            amount=Decimal("118.00"),
            signed_amount=Decimal("118.00"),
            invoice_date="2026-05-20",
            seller_name="测试销方",
            buyer_name="测试购方",
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal("6.68"),
            total_with_tax=Decimal("118.00"),
            taxable_item_name="服务费",
        )


if __name__ == "__main__":
    unittest.main()

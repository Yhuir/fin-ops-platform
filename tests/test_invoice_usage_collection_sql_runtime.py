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
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import InvoiceUsageCollectionSqlProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.rabbitmq_runtime import SUPPORTED_EVENT_TYPES
from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES, RuntimeQueueEvent


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


class InvoiceReadModelConnection:
    def __init__(
        self,
        *,
        input_rows: list[dict] | None = None,
        output_rows: list[dict] | None = None,
        dirty: bool = False,
        scope_exists: bool = True,
    ) -> None:
        self.input_rows = list(input_rows or [])
        self.output_rows = list(output_rows or [])
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
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-25T03:00:00+00:00"} if self.dirty else None
        if "from read_model.input_invoice_usage_scopes" in normalized or "from read_model.output_invoice_collection_scopes" in normalized:
            return {"scope_key": params[0]} if self.scope_exists else None
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
        self.marked_input: dict[str, object] | None = None
        self.marked_output: dict[str, object] | None = None

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


class InvoiceUsageCollectionSqlRuntimeTests(unittest.TestCase):
    def test_input_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        repository = PostgresReadModelRepository(InvoiceReadModelConnection(input_rows=[], dirty=False, scope_exists=True))

        payload = repository.list_input_invoice_usage_rows(month="2026-05", page=1, page_size=50)

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

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

    def test_output_api_stale_returns_refreshing_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
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
        builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=object())
        builder._core_repository = ProjectionCoreRepository(
            invoices=[
                self._invoice("input-invoice-1", InvoiceType.INPUT),
                self._invoice("output-invoice-1", InvoiceType.OUTPUT),
            ]
        )
        builder._workbench_repository = EmptyWorkbenchRepository()
        builder._oa_projection_repository = EmptyOAProjectionRepository()
        builder._read_repository = read_repository

        input_result = builder.rebuild_input_invoice_usage_read_model_scope("2026-05")
        output_result = builder.rebuild_output_invoice_collection_read_model_scope("2026-05")

        self.assertEqual(input_result["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(output_result["source_versions"], output_invoice_collection_source_versions())
        self.assertIsNotNone(read_repository.saved_input)
        self.assertIsNotNone(read_repository.saved_output)
        self.assertEqual(read_repository.saved_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.saved_output["source_versions"], output_invoice_collection_source_versions())
        self.assertEqual(input_result["row_count"], 1)
        self.assertEqual(output_result["row_count"], 1)

    def test_projection_builder_marks_empty_scopes_with_source_versions(self) -> None:
        read_repository = RecordingInvoiceRelationReadRepository()
        builder = InvoiceUsageCollectionSqlProjectionBuilder(connection=object())
        builder._read_repository = read_repository

        builder.mark_input_invoice_usage_scope_empty("2026-05")
        builder.mark_output_invoice_collection_scope_empty("2026-05")

        self.assertEqual(read_repository.marked_input["source_versions"], input_invoice_usage_source_versions())
        self.assertEqual(read_repository.marked_output["source_versions"], output_invoice_collection_source_versions())

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

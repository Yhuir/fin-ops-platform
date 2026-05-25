from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.invoice_usage_collection_read_model_refresh import (
    InvoiceUsageCollectionReadModelRefreshService,
)
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
        self.assertIn("input_invoice_usage.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)
        self.assertIn("output_invoice_collection.read_model.refresh", DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES)


if __name__ == "__main__":
    unittest.main()

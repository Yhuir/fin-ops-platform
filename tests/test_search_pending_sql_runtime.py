from __future__ import annotations

from contextlib import contextmanager
import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.search_pending_read_model_refresh import SearchPendingReadModelRefreshService
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
        self.completed.append((tenant_id, scope_type, scope_key))


class SearchPendingConnection:
    def __init__(
        self,
        *,
        search_rows: list[dict] | None = None,
        pending_rows: list[dict] | None = None,
        pending_source_counts: dict[str, int] | None = None,
        dirty: bool = False,
        pending_scope_exists: bool = True,
    ) -> None:
        self.search_rows = list(search_rows or [])
        self.pending_rows = list(pending_rows or [])
        self.pending_source_counts = dict(pending_source_counts or {"expense": len(self.pending_rows)})
        self.dirty = dirty
        self.pending_scope_exists = pending_scope_exists
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.transaction_count = 0

    @contextmanager
    def transaction(self):
        self.transaction_count += 1
        yield self

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.search_index_rows" in normalized:
            return self.search_rows
        if "from read_model.pending_invoice_rows" in normalized and "group by direction" in normalized:
            return [
                {"direction": direction, "count": count}
                for direction, count in sorted(self.pending_source_counts.items())
            ]
        if "from read_model.pending_invoice_rows" in normalized:
            return self.pending_rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        if "from read_model.pending_invoice_scopes" in normalized:
            return {"scope_key": params[0]} if self.pending_scope_exists else None
        if "count(*)" in normalized and "from read_model.pending_invoice_rows" in normalized:
            return {"count": len(self.pending_rows)}
        return None


class PendingProjectionConnection:
    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return [
                {
                    "transaction_id": "txn-1",
                    "counterparty_name_raw": "云南供应商",
                    "trade_time": "2026-05-20 10:00:00",
                    "txn_date": "2026-05-20",
                    "amount": "118.00",
                    "balance": "1000.00",
                    "currency": "CNY",
                    "summary": "转账",
                    "remark": "服务费",
                    "bank_serial_no": "SERIAL-1",
                    "account_name": "工商银行",
                    "account_no": "622200001234",
                    "category_payload": {"category_code": "service_fee", "category_label": "服务费"},
                    "invoices": [],
                    "paid_total": "0.00",
                    "oa_applicant": "",
                    "oa_project_name": "",
                    "relation_case_ids": [],
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "pending_invoice_tag_groups": {
                        "groups": {
                            "requires_invoice": {"tag_codes": ["service_fee"]},
                            "bank_statement_as_invoice": {"tag_codes": []},
                            "no_invoice_required": {"tag_codes": []},
                        }
                    }
                }
            }
        return None


class SearchPendingSqlRuntimeTests(unittest.TestCase):
    def test_search_repository_reads_index_rows_without_state_fallback(self) -> None:
        connection = SearchPendingConnection(
            search_rows=[
                {
                    "source_kind": "bank",
                    "payload": {
                        "row_id": "txn-1",
                        "record_type": "bank",
                        "month": "2026-05",
                        "zone_hint": "open",
                        "matched_field": "对方户名",
                        "title": "昆明供应商",
                        "primary_meta": "2026-05-02 / 10.00 / 支出",
                        "secondary_meta": "工行 / 项目A",
                        "status_label": "未配对",
                        "jump_target": {"month": "2026-05", "row_id": "txn-1", "record_type": "bank", "zone_hint": "open"},
                    },
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.search_index(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit=20)

        self.assertEqual(payload["summary"], {"total": 1, "oa": 0, "bank": 1, "invoice": 0})
        self.assertEqual(payload["bank_results"][0]["row_id"], "txn-1")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_all_calls))

    def test_search_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._search_sql_read_repository = type("SearchRepo", (), {"search_index": lambda *_args, **_kwargs: None})()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("search", "2026-05", "api_miss")])

    def test_search_api_reads_sql_index(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._search_sql_read_repository = type(
            "SearchRepo",
            (),
            {
                "search_index": lambda *_args, **_kwargs: {
                    "query": "昆明",
                    "filters": {"scope": "all", "month": "2026-05", "project_name": None, "status": None, "limit": 20},
                    "summary": {"total": 1, "oa": 0, "bank": 1, "invoice": 0},
                    "oa_results": [],
                    "bank_results": [{"row_id": "txn-1"}],
                    "invoice_results": [],
                    "refresh_status": "fresh",
                    "source_versions": app._search_index_expected_source_versions(),
                }
            },
        )()
        app._search_service = type(
            "SearchService",
            (),
            {"search": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("search SQL hit must not scan in-memory state"))},
        )()

        response = app._handle_api_search(q="昆明", scope="all", month="2026-05", project_name=None, status=None, limit="20")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_results"], [{"row_id": "txn-1"}])
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_repository_reads_rows_page_and_summary(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "invoices": [],
                        "can_create_invoice": True,
                    },
                    "missing_invoice": True,
                    "can_create_invoice": True,
                }
            ],
            pending_source_counts={"expense": 356, "income": 75},
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(direction="expense", filter="all", date_from=None, date_to=None, keyword=None, page=1, page_size=50)

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["summary"]["missing_invoice_rows"], 1)
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(
            payload["summary"]["source_summary"],
            {
                "bank_transaction_rows": 431,
                "expense_rows": 356,
                "income_rows": 75,
                "current_direction_rows": 356,
                "excluded_direction_rows": 75,
            },
        )

    def test_pending_invoice_repository_returns_fresh_empty_scope_without_api_miss(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsInstance(payload, dict)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"], {"page": 1, "page_size": 50, "total": 0})
        self.assertEqual(payload["refresh_status"], "fresh")

    def test_pending_invoice_repository_returns_none_when_scope_was_never_built(self) -> None:
        connection = SearchPendingConnection(pending_rows=[], dirty=False, pending_scope_exists=False)
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            page=1,
            page_size=50,
        )

        self.assertIsNone(payload)

    def test_pending_invoice_repository_accepts_filter_json_and_native_sort_fields(self) -> None:
        connection = SearchPendingConnection(
            pending_rows=[
                {
                    "payload": {
                        "id": "txn-1",
                        "bank_transaction": {"id": "txn-1", "counterparty_name": "昆明供应商"},
                        "input_invoices": {"primary": {"seller_name": "昆明供应商"}},
                    },
                    "missing_invoice": False,
                    "can_create_invoice": False,
                }
            ]
        )
        repository = PostgresReadModelRepository(connection)

        payload = repository.list_pending_invoice_rows(
            direction="expense",
            filter="all",
            date_from=None,
            date_to=None,
            keyword=None,
            filters='[{"field":"status_code","operator":"in","values":["paid_invoiced"]}]',
            sort_field="seller_name",
            sort_direction="asc",
            page=1,
            page_size=50,
        )

        self.assertEqual(payload["pagination"]["total"], 1)
        executed_sql = " ".join(sql for sql, _params in connection.fetch_all_calls + connection.fetch_one_calls)
        self.assertIn("status_code", executed_sql)
        self.assertIn("seller_name asc", executed_sql)

    def test_pending_invoice_api_miss_enqueues_refresh_without_sync_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"list_pending_invoice_rows": lambda *_args, **_kwargs: None},
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice API miss must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_miss")])

    def test_pending_invoice_api_reads_sql_page(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": app._pending_invoice_expected_source_versions(),
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("pending invoice SQL hit must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-1")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_pending_invoice_api_treats_legacy_sql_payload_shape_as_refreshing(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [{"id": "txn-legacy", "bank_transaction": {"id": "txn-legacy"}, "invoices": []}],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": app._pending_invoice_expected_source_versions(),
                }
            },
        )()
        app._pending_invoice_query_service = type(
            "PendingService",
            (),
            {"list_rows": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("legacy SQL shape must not scan in-memory state"))},
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("pending_invoice", "expense:all", "api_schema_stale")])

    def test_pending_invoice_api_serves_existing_rows_while_scope_refreshes(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-stale",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "refreshing",
                },
                "pending_invoice_source_summary": lambda *_args, **_kwargs: {
                    "bank_transaction_rows": 431,
                    "expense_rows": 356,
                    "income_rows": 75,
                    "current_direction_rows": 356,
                    "excluded_direction_rows": 75,
                },
            },
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["id"], "txn-stale")
        self.assertEqual(payload["summary"]["source_summary"]["bank_transaction_rows"], 431)
        self.assertEqual(payload["summary"]["source_summary"]["income_rows"], 75)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [])

    def test_pending_invoice_sql_page_preserves_bank_tag_settings(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._app_settings_service = type(
            "SettingsService",
            (),
            {"get_settings_payload": lambda *_args: {"bank_transaction_tags": {"version": 7, "items": [{"code": "A1"}]}}},
        )()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {
                "list_pending_invoice_rows": lambda *_args, **_kwargs: {
                    "direction": "expense",
                    "filter": "all",
                    "rows": [
                        {
                            "id": "txn-1",
                            "invoice_acquisition_status": {"code": "paid_pending_invoice"},
                            "input_invoices": {"primary": None, "summaries": []},
                            "oa": {"primary": None, "summaries": []},
                        }
                    ],
                    "pagination": {"page": 1, "page_size": 50, "total": 1},
                    "summary": {"total_rows": 1, "missing_invoice_rows": 1, "create_invoice_available_rows": 1},
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": "fresh",
                    "source_versions": app._pending_invoice_expected_source_versions(),
                }
            },
        )()

        response = app._handle_api_pending_invoice_rows({"direction": ["expense"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["bank_transaction_tags"], {"version": 7, "items": [{"code": "A1"}]})
        self.assertEqual(payload["bank_transaction_tags_version"], 7)

    def test_pending_invoice_worker_rebuild_paginates_all_rows(self) -> None:
        saved: list[dict[str, object]] = []

        class PendingService:
            def list_rows(self, **kwargs: object) -> dict[str, object]:
                page = int(kwargs["page"])
                rows = [
                    {
                        "id": f"txn-{index}",
                        "bank_transaction": {
                            "id": f"txn-{index}",
                            "trade_time": "2026-05-01",
                            "amount": "1.00",
                            "counterparty_name": f"供应商{index}",
                        },
                        "invoices": [],
                        "can_create_invoice": True,
                    }
                    for index in range(1, 201)
                ]
                if page == 2:
                    rows = [
                        {
                            "id": "txn-201",
                            "bank_transaction": {
                                "id": "txn-201",
                                "trade_time": "2026-05-02",
                                "amount": "2.00",
                                "counterparty_name": "供应商201",
                            },
                            "invoices": [],
                            "can_create_invoice": True,
                        }
                    ]
                return {
                    "rows": rows,
                    "pagination": {"page": page, "page_size": 200, "total": 201},
                }

        app = object.__new__(Application)
        app._pending_invoice_query_service = PendingService()
        app._pending_invoice_sql_read_repository = type(
            "PendingRepo",
            (),
            {"save_pending_invoice_rows": lambda *_args, **kwargs: saved.extend(kwargs["rows"])},
        )()

        result = app.rebuild_pending_invoice_read_model_scope("expense:all")

        self.assertEqual(result["row_count"], 201)
        self.assertEqual(len(saved), 201)
        self.assertEqual(saved[-1]["payload"]["id"], "txn-201")

    def test_pending_invoice_sql_projection_emits_upgraded_four_zone_payload(self) -> None:
        builder = SearchPendingSqlProjectionBuilder(connection=PendingProjectionConnection())

        rows = builder._pending_invoice_rows(direction="expense", filter_name="all", month="2026-05")

        payload = rows[0]["payload"]
        self.assertEqual(payload["id"], "txn-1")
        self.assertEqual(payload["invoice_acquisition_status"]["code"], "paid_pending_invoice")
        self.assertEqual(payload["invoice_acquisition_status"]["label"], "已支付待开票")
        self.assertIn("input_invoices", payload)
        self.assertIn("oa", payload)
        self.assertEqual(payload["bank_transaction"]["account_last4"], "1234")

    def test_refresh_handler_rebuilds_search_and_pending_scopes(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.search_rebuilt: list[str] = []
                self.pending_rebuilt: list[str] = []

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.search_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.pending_rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        search_event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="search",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )
        pending_event = RuntimeQueueEvent(
            event_id="event-2",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        self.assertEqual(service.handle_runtime_event(search_event)["row_count"], 1)
        self.assertEqual(service.handle_runtime_event(pending_event)["row_count"], 2)

        self.assertEqual(builder.search_rebuilt, ["2026-05"])
        self.assertEqual(builder.pending_rebuilt, ["expense:all"])
        self.assertEqual(
            queue.completed,
            [("tenant-a", "search", "2026-05"), ("tenant-a", "pending_invoice", "expense:all")],
        )

    def test_refresh_handler_expands_search_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_search_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["2026-05", "2026-04"]

            def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="search.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="search",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:all"])
        self.assertEqual(
            queue.refreshes,
            [("search", "2026-05", "search_all_shard"), ("search", "2026-04", "search_all_shard")],
        )
        self.assertEqual(queue.completed, [("tenant-a", "search", "all")])

    def test_refresh_handler_expands_legacy_pending_scope_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
                self.rebuilt.append(f"list:{scope_key}")
                return ["expense:all:2026-05", "expense:all:2026-04"]

            def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = SearchPendingReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-pending-all",
            tenant_id="tenant-a",
            event_type="pending_invoice.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="expense:all",
            scope_type="pending_invoice",
            scope_key="expense:all",
            dedupe_key=None,
            payload={"scope_key": "expense:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result, {"scope_key": "expense:all", "enqueued_scope_keys": ["expense:all:2026-05", "expense:all:2026-04"], "row_count": 0})
        self.assertEqual(builder.rebuilt, ["list:expense:all"])
        self.assertEqual(
            queue.refreshes,
            [
                ("pending_invoice", "expense:all:2026-05", "pending_invoice_month_shard"),
                ("pending_invoice", "expense:all:2026-04", "pending_invoice_month_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "pending_invoice", "expense:all")])


if __name__ == "__main__":
    unittest.main()

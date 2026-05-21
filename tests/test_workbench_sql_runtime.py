from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService


class WorkbenchSqlReadConnection:
    def __init__(self, *, snapshot_row: dict | None = None, dirty: bool = False) -> None:
        self.snapshot_row = snapshot_row
        self.dirty = dirty
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized:
            return self.snapshot_row
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_rows" in normalized:
            return [
                {
                    "row_id": "bank-row-1",
                    "source_kind": "bank_transaction",
                    "status": "open",
                    "payload": {"id": "bank-row-1"},
                }
            ]
        return []


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class WorkbenchWriteConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


class FakeWorkbenchReadModelService:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    def delete_read_model(self, scope_key: str) -> None:
        self.deleted.append(scope_key)


class WorkbenchSqlRuntimeTests(unittest.TestCase):
    def test_repository_reads_workbench_snapshot_and_dirty_status_without_state_fallback(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"open": {"groups": []}},
                "raw_payload": {},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="2026-05")

        self.assertEqual(view["payload"], {"open": {"groups": []}})
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_reads_paginated_workbench_rows_from_sql_read_model(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "2026-05",
                "cache_status": "fresh",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "payload": {"open": {"groups": []}},
                "row_count": 1,
            }
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="2026-05",
            page=2,
            page_size=25,
            status="open",
            source_kind="bank_transaction",
            search="供应商",
        )

        self.assertEqual(view["rows_page"]["page"], 2)
        self.assertEqual(view["rows_page"]["page_size"], 25)
        self.assertEqual(view["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertTrue(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))

    def test_workbench_api_returns_sql_read_model_without_sync_build(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {"get_workbench_view": lambda _self, **_kwargs: {"payload": {"open": {"groups": []}}, "refresh_status": "fresh"}},
        )()

        def explode_builder(_month: str):
            raise AssertionError("API request path must not synchronously build workbench payload")

        app._build_raw_workbench_payload = explode_builder

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["open"], {"groups": []})
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(queue.refreshes, [])

    def test_workbench_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = type(
            "SqlWorkbench",
            (),
            {"get_workbench_view": lambda _self, **_kwargs: None},
        )()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("API request path must not synchronously build workbench payload")
        )

        response = app._handle_api_workbench("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("workbench", "2026-05", "api_miss")])

    def test_workbench_api_passes_page_and_filter_to_sql_read_model(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        calls: list[dict[str, object]] = []

        class SqlWorkbench:
            def get_workbench_view(self, **kwargs):
                calls.append(kwargs)
                return {
                    "payload": {"open": {"groups": []}},
                    "refresh_status": "fresh",
                    "rows_page": {"page": 3, "page_size": 10, "rows": [{"id": "bank-row-1"}], "has_more": False},
                }

        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_sql_read_repository = SqlWorkbench()
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("API request path must not synchronously build workbench payload")
        )

        response = app._handle_api_workbench(
            "2026-05",
            page="3",
            page_size="10",
            status="open",
            source_kind="bank_transaction",
            search="供应商",
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows_page"]["rows"], [{"id": "bank-row-1"}])
        self.assertEqual(
            calls,
            [
                {
                    "scope_key": "2026-05",
                    "page": "3",
                    "page_size": "10",
                    "status": "open",
                    "source_kind": "bank_transaction",
                    "search": "供应商",
                }
            ],
        )

    def test_repository_persists_workbench_rows_alongside_snapshot(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {
                            "open": {
                                "groups": [
                                    {
                                        "bank_rows": [
                                            {
                                                "id": "bank-row-1",
                                                "source_kind": "bank_transaction",
                                                "status": "open",
                                                "counterparty_name": "供应商A",
                                                "amount": "100.00",
                                            }
                                        ]
                                    }
                                ]
                            }
                        },
                        "source_versions": {"case_snapshot_version": "v1"},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("delete from read_model.workbench_rows", sql)
        self.assertIn("insert into read_model.workbench_rows", sql)

    def test_repository_deletes_workbench_rows_when_scope_snapshot_is_removed(self) -> None:
        connection = WorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models({"read_models": {}}, changed_scope_keys={"2026-05"})

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertIn("delete from read_model.workbench_snapshots", sql)
        self.assertIn("delete from read_model.workbench_rows", sql)

    def test_workbench_invalidation_marks_dirty_scope_without_sync_rebuild(self) -> None:
        app = object.__new__(Application)
        queue = QueueRecorder()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._workbench_read_model_service = FakeWorkbenchReadModelService()
        app._expand_workbench_read_model_scope_keys_for_base_scopes = lambda scope_keys: scope_keys
        app._invalidate_cost_statistics_read_model_scopes = lambda *_args, **_kwargs: []
        app._build_raw_workbench_payload = lambda _month: (_ for _ in ()).throw(
            AssertionError("Invalidation must only enqueue refresh, not rebuild synchronously")
        )

        changed = app._invalidate_workbench_read_model_scopes(["2026-05"], invalidate_cost_statistics=False)

        self.assertEqual(changed, ["2026-05"])
        self.assertEqual(queue.refreshes, [("workbench", "2026-05", "workbench_scope_invalidated")])

    def test_workbench_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeApplication:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def rebuild_workbench_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "row_count": 1}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str]] = []

            def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
                self.completed.append((tenant_id, scope_type, scope_key))

        application = FakeApplication()
        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(application=application, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(application.rebuilt, ["2026-05"])
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05")])
        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 1)


if __name__ == "__main__":
    unittest.main()

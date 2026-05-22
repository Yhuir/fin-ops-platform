from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.workbench_read_model_refresh import WorkbenchReadModelRefreshService
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder


class WorkbenchSqlReadConnection:
    def __init__(
        self,
        *,
        snapshot_row: dict | None = None,
        snapshot_rows: list[dict] | None = None,
        dirty: bool = False,
    ) -> None:
        self.snapshot_row = snapshot_row
        self.snapshot_rows = list(snapshot_rows or [])
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
        if "from read_model.workbench_snapshots" in normalized:
            return list(self.snapshot_rows)
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


class WorkbenchAllRowsPageConnection(WorkbenchSqlReadConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "count(*) as total_count" in normalized:
            return {"total_count": 1}
        return super().fetch_one(sql, params)

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_snapshots" in normalized:
            if "payload, raw_payload" in normalized:
                raise AssertionError("all-scope filtered rows_page must not load full grouped workbench snapshots")
            return [
                {
                    "scope_key": "2026-05",
                    "row_count": 100,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "cache_status": "fresh",
                    "summary": {"oa_count": 1, "bank_count": 2, "invoice_count": 3, "paired_count": 4, "open_count": 5},
                },
                {
                    "scope_key": "2026-04",
                    "row_count": 10,
                    "generated_at": "2026-05-21T08:00:00+00:00",
                    "cache_status": "fresh",
                    "summary": {"oa_count": 10, "bank_count": 20, "invoice_count": 30, "paired_count": 40, "open_count": 50},
                },
            ]
        if "from read_model.workbench_rows" in normalized:
            return [
                {
                    "row_id": "oa-att-inv-1",
                    "source_kind": "oa_attachment_invoice",
                    "status": "paired",
                    "payload": {"id": "oa-att-inv-1", "source_kind": "oa_attachment_invoice"},
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
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        return None

    def execute(self, sql: str, params: tuple = ()) -> int:
        self.executed.append((" ".join(sql.lower().split()), params))
        return 1


class StaleWorkbenchWriteConnection(WorkbenchWriteConnection):
    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
        if "from read_model.workbench_snapshots" in self.fetch_one_calls[-1][0]:
            return {"source_versions": {"source_version": 5}}
        if "from read_model.workbench_candidate_matches" in self.fetch_one_calls[-1][0]:
            return {"source_version": 5}
        return None


class WorkbenchProjectionSettingsConnection:
    def __init__(
        self,
        *,
        overrides: list[dict[str, object]] | None = None,
        exception_cases: list[dict[str, object]] | None = None,
    ) -> None:
        self.overrides = list(overrides or [])
        self.exception_cases = list(exception_cases or [])

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        if "from app.app_settings" in normalized:
            return {"settings_payload": {"oa_invoice_offset": {"applicant_names": []}}}
        if "from job.read_model_dirty_scopes" in normalized:
            return {"source_version": 1}
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        if "from app.workbench_row_overrides" in normalized:
            return list(self.overrides)
        if "from app.workbench_exception_cases" in normalized:
            return list(self.exception_cases)
        return []


class CandidateSnapshotRecorder:
    def __init__(self) -> None:
        self.saved_snapshots: list[tuple[dict[str, object], set[str] | None]] = []

    def save_workbench_candidate_matches(
        self,
        snapshot: dict[str, object],
        *,
        changed_scope_months: set[str] | None = None,
    ) -> None:
        self.saved_snapshots.append((snapshot, changed_scope_months))


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

    def test_repository_synthesizes_all_workbench_view_from_month_snapshots(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_rows=[
                {
                    "scope_key": "2026-05",
                    "row_count": 1,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1},
                            "open": {"groups": [{"oa_rows": [{"id": "oa-1"}], "bank_rows": [], "invoice_rows": []}]},
                            "paired": {"groups": []},
                        }
                    },
                },
                {
                    "scope_key": "2026-04",
                    "row_count": 1,
                    "generated_at": "2026-05-21T08:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {"oa_count": 0, "bank_count": 1, "invoice_count": 0, "paired_count": 1, "open_count": 0},
                            "open": {"groups": []},
                            "paired": {"groups": [{"oa_rows": [], "bank_rows": [{"id": "bank-1"}], "invoice_rows": []}]},
                        }
                    },
                },
            ],
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        self.assertEqual(view["row_count"], 2)
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertEqual(view["payload"]["summary"]["oa_count"], 1)
        self.assertEqual(view["payload"]["summary"]["bank_count"], 1)
        self.assertEqual(len(view["payload"]["open"]["groups"]), 1)
        self.assertEqual(len(view["payload"]["paired"]["groups"]), 1)

    def test_repository_ignores_stale_all_workbench_snapshot_and_synthesizes_from_months(self) -> None:
        connection = WorkbenchSqlReadConnection(
            snapshot_row={
                "scope_key": "all",
                "row_count": 1,
                "generated_at": "2026-05-21T10:00:00+00:00",
                "payload": {
                    "summary": {"oa_count": 1, "bank_count": 0, "invoice_count": 0, "paired_count": 0, "open_count": 1},
                    "open": {"groups": [{"oa_rows": [{"id": "stale-oa"}], "bank_rows": [], "invoice_rows": []}]},
                    "paired": {"groups": []},
                },
            },
            snapshot_rows=[
                {
                    "scope_key": "2026-04",
                    "row_count": 2,
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "payload": {
                        "payload": {
                            "summary": {
                                "oa_count": 0,
                                "bank_count": 1,
                                "invoice_count": 1,
                                "paired_count": 1,
                                "open_count": 1,
                            },
                            "open": {"groups": [{"oa_rows": [], "bank_rows": [], "invoice_rows": [{"id": "invoice-open"}]}]},
                            "paired": {"groups": [{"oa_rows": [], "bank_rows": [{"id": "bank-paired"}], "invoice_rows": []}]},
                        }
                    },
                },
            ],
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(scope_key="all")

        self.assertEqual(view["row_count"], 2)
        self.assertEqual(view["payload"]["summary"]["invoice_count"], 1)
        self.assertEqual(view["payload"]["open"]["groups"][0]["invoice_rows"][0]["id"], "invoice-open")
        self.assertEqual(view["payload"]["paired"]["groups"][0]["bank_rows"][0]["id"], "bank-paired")
        self.assertNotEqual(view["payload"]["open"]["groups"][0]["oa_rows"], [{"id": "stale-oa"}])

    def test_repository_reads_all_scope_filtered_page_without_full_snapshot_payloads(self) -> None:
        connection = WorkbenchAllRowsPageConnection()
        repository = PostgresReadModelRepository(connection)

        view = repository.get_workbench_view(
            scope_key="all",
            page=1,
            page_size=50,
            source_kind="oa_attachment_invoice",
        )

        self.assertEqual(view["payload"]["summary"]["invoice_count"], 33)
        self.assertEqual(view["payload"]["paired"]["groups"], [])
        self.assertEqual(view["payload"]["open"]["groups"], [])
        self.assertEqual(view["rows_page"]["total"], 1)
        self.assertEqual(view["rows_page"]["rows"][0]["id"], "oa-att-inv-1")
        self.assertTrue(any("from read_model.workbench_rows" in sql for sql, _params in connection.fetch_all_calls))
        self.assertFalse(
            any(
                "from read_model.workbench_snapshots" in sql and "payload, raw_payload" in sql
                for sql, _params in connection.fetch_all_calls
            )
        )

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

    def test_repository_skips_stale_workbench_snapshot_write_by_source_version(self) -> None:
        connection = StaleWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_read_models(
            {
                "read_models": {
                    "2026-05": {
                        "scope_key": "2026-05",
                        "payload": {"open": {"groups": []}},
                        "source_versions": {"source_version": 4},
                    }
                }
            },
            changed_scope_keys={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("insert into read_model.workbench_snapshots", sql)
        self.assertNotIn("delete from read_model.workbench_rows", sql)

    def test_repository_skips_stale_workbench_candidate_write_by_source_version(self) -> None:
        connection = StaleWorkbenchWriteConnection()
        repository = PostgresReadModelRepository(connection)

        repository.save_workbench_candidate_matches(
            {
                "candidates": {
                    "candidate-old": {
                        "candidate_key": "candidate-old",
                        "scope_month": "2026-05",
                        "status": "incomplete",
                        "row_ids": ["bank-1"],
                        "source_versions": {"source_version": 4},
                    }
                },
                "scope_runs": {"2026-05": {"source_versions": {"source_version": 4}}},
            },
            changed_scope_months={"2026-05"},
        )

        sql = "\n".join(statement for statement, _params in connection.executed)
        self.assertNotIn("delete from read_model.workbench_candidate_matches", sql)
        self.assertNotIn("insert into read_model.workbench_candidate_matches", sql)

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
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[tuple[str, object]] = []

            def rebuild_workbench_read_model_scope(self, scope_key: str, *, source_version: object = None) -> dict[str, object]:
                self.rebuilt.append((scope_key, source_version))
                return {"scope_key": scope_key, "row_count": 1}

        class FakeQueue:
            def __init__(self) -> None:
                self.completed: list[tuple[str, str, str]] = []

            def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
                self.completed.append((tenant_id, scope_type, scope_key))

        builder = FakeBuilder()
        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="workbench",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05", "source_version": 7},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, [("2026-05", 7)])
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "2026-05")])
        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(result["row_count"], 1)

    def test_workbench_refresh_handler_expands_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def list_workbench_scope_shards(self, scope_key: str) -> list[str]:
                self.calls.append(scope_key)
                return ["2026-05", "2026-04"]

            def rebuild_workbench_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        class FakeQueue:
            def __init__(self) -> None:
                self.refreshes: list[tuple[str, str, str]] = []
                self.completed: list[tuple[str, str, str]] = []

            def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
                self.refreshes.append((scope_type, scope_key, reason))

            def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
                self.completed.append((tenant_id, scope_type, scope_key))

        builder = FakeBuilder()
        queue = FakeQueue()
        service = WorkbenchReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="workbench.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="workbench",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.calls, ["all"])
        self.assertEqual(result, {"scope_key": "all", "enqueued_scope_keys": ["2026-05", "2026-04"], "row_count": 0})
        self.assertEqual(
            queue.refreshes,
            [("workbench", "2026-05", "workbench_all_shard"), ("workbench", "2026-04", "workbench_all_shard")],
        )
        self.assertEqual(queue.completed, [("tenant-a", "workbench", "all")])

    def test_sql_projection_pairs_materialized_attachment_rows_by_source_oa_relation(self) -> None:
        relation = {
            "row_ids": ["oa-exp-1", "legacy-attachment-row-id"],
            "row_types": ["oa", "invoice"],
        }
        rows_by_id = {
            "oa-exp-1": {"id": "oa-exp-1", "type": "oa", "source_kind": "oa"},
            "oa-att-inv-new": {
                "id": "oa-att-inv-new",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "derived_from_oa_id": "oa-exp-1",
            },
        }

        row_ids = WorkbenchSqlProjectionBuilder._attachment_row_ids_for_relation(relation, rows_by_id)

        self.assertEqual(row_ids, ["oa-att-inv-new"])

    def test_sql_projection_materializes_invoice_like_expense_item_artifacts_only(self) -> None:
        payload = {
            "expense_items": [
                {
                    "expense_item_id": "item-1",
                    "row_index": "0",
                    "attachment_artifacts": [
                        {"source_attachment_name": "交通发票.pdf", "source_attachment_key": "invoice-pdf"},
                        {"source_attachment_name": "付款截图.jpg", "source_attachment_key": "screenshot", "suffix": "jpg"},
                    ],
                }
            ]
        }

        evidences = WorkbenchSqlProjectionBuilder._attachment_evidences_from_expense_items(payload)

        self.assertEqual(len(evidences), 1)
        self.assertEqual(evidences[0]["source_attachment_key"], "invoice-pdf")
        self.assertEqual(evidences[0]["source_expense_item_id"], "item-1")
        self.assertEqual(evidences[0]["source_expense_row_index"], "0")

    def test_sql_projection_materializes_attachment_invoice_rows_from_structured_oa_tables(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-structured",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-structured:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "oa-exp-structured:invoice:1",
                                "filename": "发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "invoice_no": "INV-STRUCT-001",
                                    "seller_name": "杭州供应商",
                                    "total_with_tax": "199.00",
                                }
                            ],
                            "cache_evidences": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-structured": {
                    "id": "oa-exp-structured",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "199.00",
                    "counterparty_name": "杭州供应商",
                    "detail_fields": {"申请日期": "2026-05-02"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_kind"], "oa_attachment_invoice")
        self.assertEqual(rows[0]["derived_from_oa_id"], "oa-exp-structured")
        self.assertEqual(rows[0]["source_expense_item_id"], "oa-exp-structured:item:1")
        self.assertEqual(rows[0]["source_attachment_key"], "oa-exp-structured:invoice:1")
        self.assertIn("INV-STRUCT-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_matches_legacy_attachment_cache_by_nested_source_key(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    if "oa_attachment_invoice_cache_sources" not in normalized:
                        return []
                    return [
                        {
                            "oa_row_id": "oa-exp-legacy-cache",
                            "scope_month": "2026-05-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-legacy-cache:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "actual-attachment-key",
                                "filename": "历史发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "actual-attachment-key",
                                    "invoice_no": "INV-LEGACY-CACHE-001",
                                    "seller_name": "历史供应商",
                                    "total_with_tax": "299.00",
                                }
                            ],
                            "cache_evidences": [],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-05",
            {
                "oa-exp-legacy-cache": {
                    "id": "oa-exp-legacy-cache",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "299.00",
                    "counterparty_name": "历史供应商",
                    "detail_fields": {"申请日期": "2026-05-02"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_attachment_key"], "actual-attachment-key")
        self.assertIn("INV-LEGACY-CACHE-001", rows[0]["detail_fields"]["发票号码"])

    def test_sql_projection_ignores_artifact_placeholders_when_cache_has_parsed_invoice(self) -> None:
        class StructuredOAConnection(WorkbenchProjectionSettingsConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from app.oa_application_items" in normalized:
                    return [
                        {
                            "oa_row_id": "oa-exp-with-artifact-placeholder",
                            "scope_month": "2026-02-01",
                            "item_payload": {
                                "expense_item_id": "oa-exp-with-artifact-placeholder:item:1",
                                "row_index": "0",
                            },
                            "attachment_payload": {
                                "source_attachment_key": "attachment-key-1",
                                "filename": "发票.pdf",
                            },
                            "cache_invoices": [
                                {
                                    "source_attachment_key": "attachment-key-1",
                                    "seller_name": "供应商A",
                                    "buyer_name": "云南溯源科技有限公司",
                                    "amount": "165.35",
                                    "tax_amount": "1.65",
                                    "total_with_tax": "167.00",
                                    "issue_date": "2026-02-04",
                                }
                            ],
                            "cache_evidences": [],
                            "cache_artifacts": [
                                {
                                    "source_attachment_key": "attachment-key-1",
                                    "source_attachment_name": "发票.pdf",
                                    "document_kind": "发票附件",
                                }
                            ],
                        }
                    ]
                if "from app.oa_applications" in normalized:
                    return []
                return super().fetch_all(sql, params)

        builder = WorkbenchSqlProjectionBuilder(
            connection=StructuredOAConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows = builder._attachment_invoice_rows_from_expense_items(
            "2026-02",
            {
                "oa-exp-with-artifact-placeholder": {
                    "id": "oa-exp-with-artifact-placeholder",
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "amount": "652.99",
                    "counterparty_name": "",
                    "detail_fields": {"申请日期": "2026-02-26"},
                }
            },
        )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["seller_name"], "供应商A")
        self.assertEqual(rows[0]["amount"], "165.35")
        self.assertEqual(rows[0]["total_with_tax"], "167.00")

    def test_sql_projection_keeps_attachment_invoice_rows_source_bound_to_parent_oa(self) -> None:
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=CandidateSnapshotRecorder(),
        )
        rows_by_id = {
            "oa-left": {
                "id": "oa-left",
                "type": "oa",
                "source_kind": "oa",
                "status": "open",
                "amount": "100.00",
                "counterparty_name": "供应商A",
                "apply_type": "付款",
                "pay_receive_time": "2026-02-10",
            },
            "oa-right": {
                "id": "oa-right",
                "type": "oa",
                "source_kind": "oa",
                "status": "open",
                "amount": "100.00",
                "counterparty_name": "供应商A",
                "apply_type": "付款",
                "pay_receive_time": "2026-02-10",
            },
            "oa-left-att-inv": {
                "id": "oa-left-att-inv",
                "type": "invoice",
                "source_kind": "oa_attachment_invoice",
                "status": "open",
                "derived_from_oa_id": "oa-left",
                "seller_name": "供应商A",
                "buyer_name": "云南溯源科技有限公司",
                "invoice_type": "进项发票",
                "amount": "100.00",
                "total_with_tax": "100.00",
                "issue_date": "2026-02-10",
            },
        }

        payload = builder._group_payload("2026-02", rows_by_id, [])
        groups = payload["open"]["groups"]
        linked_groups = [
            group
            for group in groups
            if any(row.get("source_kind") == "oa_attachment_invoice" for row in group["invoice_rows"])
        ]

        self.assertEqual(len(linked_groups), 1)
        self.assertEqual([row["id"] for row in linked_groups[0]["oa_rows"]], ["oa-left"])
        self.assertEqual(
            {row["derived_from_oa_id"] for row in linked_groups[0]["invoice_rows"]},
            {"oa-left"},
        )

    def test_sql_projection_rebuilds_candidate_matches_from_sql_rows(self) -> None:
        recorder = CandidateSnapshotRecorder()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=recorder,
        )
        rows_by_id = {
            "oa-1": {
                "id": "oa-1",
                "type": "oa",
                "source_kind": "oa",
                "amount": "100.00",
                "counterparty_name": "杭州测试供应商",
                "application_date": "2026-05-10",
                "project_name": "测试项目",
                "reason": "测试采购",
            },
            "bank-1": {
                "id": "bank-1",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "100.00",
                "counterparty_name": "杭州测试供应商",
                "trade_time": "2026-05-11 10:00",
                "summary": "测试采购付款",
            },
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        snapshot, months = recorder.saved_snapshots[-1]
        candidates = snapshot["candidates"]
        self.assertEqual(months, {"2026-05"})
        self.assertTrue(any(candidate["status"] == "incomplete" for candidate in candidates.values()))
        open_rows = [
            row
            for group in payload["open"]["groups"]
            for row in [*group.get("oa_rows", []), *group.get("bank_rows", [])]
        ]
        self.assertEqual({row["id"] for row in open_rows}, {"oa-1", "bank-1"})
        self.assertTrue(all(str(row.get("case_id", "")).startswith("candidate:") for row in open_rows))
        self.assertTrue(any(group["group_type"] == "candidate" for group in payload["open"]["groups"]))

    def test_sql_projection_active_no_oa_relation_uses_grouping_contract(self) -> None:
        recorder = CandidateSnapshotRecorder()
        builder = WorkbenchSqlProjectionBuilder(
            connection=WorkbenchProjectionSettingsConnection(),
            read_model_repository=recorder,
        )
        rows_by_id = {
            "bank-a": {
                "id": "bank-a",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "12.00",
                "trade_time": "2026-05-01 09:00",
                "counterparty_name": "手续费",
            },
            "bank-b": {
                "id": "bank-b",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "8.00",
                "trade_time": "2026-05-02 09:00",
                "counterparty_name": "手续费",
            },
        }
        relation = {
            "case_id": "CASE-NO-OA-1",
            "relation_mode": "no_oa_bank_batch",
            "row_ids": ["bank-a", "bank-b"],
            "row_types": ["bank", "bank"],
        }

        payload = builder._group_payload("2026-05", rows_by_id, [relation])

        paired = payload["paired"]["groups"]
        self.assertEqual(len(paired), 1)
        self.assertEqual(paired[0]["relation_mode"], "no_oa_bank_batch")
        self.assertEqual(paired[0]["bank_rows"][0]["invoice_relation"]["code"], "no_oa_bank_batch")

    def test_sql_projection_applies_row_overrides_before_grouping(self) -> None:
        recorder = CandidateSnapshotRecorder()
        connection = WorkbenchProjectionSettingsConnection(
            overrides=[
                {
                    "row_id": "bank-override",
                    "override_payload": {
                        "ignored": True,
                        "case_id": "CASE-OVERRIDE-1",
                        "relation": {"code": "manual_exception", "label": "人工异常", "tone": "danger"},
                    },
                }
            ]
        )
        builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=recorder)
        rows_by_id = {
            "bank-override": {
                "id": "bank-override",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "10.00",
                "counterparty_name": "供应商",
            }
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        row = payload["open"]["groups"][0]["bank_rows"][0]
        self.assertTrue(row["ignored"])
        self.assertEqual(row["case_id"], "CASE-OVERRIDE-1")
        self.assertEqual(row["invoice_relation"]["code"], "manual_exception")

    def test_sql_projection_applies_active_exception_case_projection(self) -> None:
        recorder = CandidateSnapshotRecorder()
        connection = WorkbenchProjectionSettingsConnection(
            exception_cases=[
                {
                    "case_id": "CASE-EXCEPTION-1",
                    "raw_payload": {
                        "case_id": "CASE-EXCEPTION-1",
                        "id": "CASE-EXCEPTION-1",
                        "status": "confirmed",
                        "exception_code": "bank_fee",
                        "exception_label": "银行手续费",
                        "category": "bank",
                        "row_ids": ["bank-exception"],
                        "row_types": ["bank"],
                        "scope_months": ["2026-05"],
                        "resolution": {"action_code": "manual_review"},
                    },
                }
            ]
        )
        builder = WorkbenchSqlProjectionBuilder(connection=connection, read_model_repository=recorder)
        rows_by_id = {
            "bank-exception": {
                "id": "bank-exception",
                "type": "bank",
                "source_kind": "bank",
                "debit_amount": "10.00",
                "counterparty_name": "银行",
            }
        }

        payload = builder._group_payload("2026-05", rows_by_id, [])

        row = payload["open"]["groups"][0]["bank_rows"][0]
        self.assertEqual(row["exception_case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["case_id"], "CASE-EXCEPTION-1")
        self.assertEqual(row["invoice_relation"]["tone"], "danger")


if __name__ == "__main__":
    unittest.main()

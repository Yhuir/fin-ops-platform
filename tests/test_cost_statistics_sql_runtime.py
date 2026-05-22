from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))

    def complete_read_model_refresh(self, *, tenant_id: str, scope_type: str, scope_key: str) -> None:
        self.completed.append((tenant_id, scope_type, scope_key))


class RedisRecorder:
    def __init__(self, value: dict | None = None) -> None:
        self.value = value
        self.gets: list[str] = []
        self.sets: list[tuple[str, dict, int]] = []
        self.deletes: list[str] = []

    def get_json(self, key: str) -> dict | None:
        self.gets.append(key)
        return self.value

    def set_json(self, key: str, value: dict, *, ttl_seconds: int) -> bool:
        self.sets.append((key, value, ttl_seconds))
        return True

    def delete(self, key: str) -> bool:
        self.deletes.append(key)
        return True


class CostStatisticsReadConnection:
    def __init__(self, *, read_model_row: dict | None = None, dirty: bool = False) -> None:
        self.read_model_row = read_model_row
        self.dirty = dirty
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.cost_statistics_read_models" in normalized:
            return self.read_model_row
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        return []


class CostStatisticsSqlRuntimeTests(unittest.TestCase):
    def test_repository_reads_cost_statistics_view_and_dirty_status_from_sql(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "project_scope": "active",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "payload": {"month": "2026-05", "time_rows": [{"transaction_id": "txn-1"}]},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_cost_statistics_view(scope_key="active:2026-05")

        self.assertEqual(view["payload"]["time_rows"], [{"transaction_id": "txn-1"}])
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_cost_statistics_api_reads_redis_hot_cache_without_sql_or_sync_build(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": RedisRecorder({"payload": {"month": "2026-05", "time_rows": []}})},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SQL should not be hit on Redis cache"))},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics_explorer("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["month"], "2026-05")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_cost_statistics_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: None},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics_explorer("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_miss")])

    def test_production_postgres_cost_statistics_requires_sql_read_model_without_sync_build(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._cost_statistics_sql_read_repository = None
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("production API must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics_explorer("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_sql_repository_unavailable")])

    def test_cost_statistics_month_summary_miss_enqueues_refresh_without_sync_build(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {"get_cost_statistics_view": lambda *_args, **_kwargs: None},
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_month_statistics": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_month_miss")])

    def test_cost_statistics_month_summary_reads_sql_aggregate_and_populates_redis(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {
                        "month": "2026-05",
                        "time_rows": [
                            {
                                "transaction_id": "txn-1",
                                "project_name": "项目A",
                                "expense_type": "材料",
                                "expense_content": "钢材",
                                "amount": "10.00",
                            },
                            {
                                "transaction_id": "txn-2",
                                "project_name": "项目A",
                                "expense_type": "材料",
                                "expense_content": "钢材",
                                "amount": "5.50",
                            },
                        ],
                    },
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_month_statistics": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API SQL hit must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["summary"]["total_amount"], "15.50")
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["rows"][0]["amount"], "15.50")
        self.assertEqual(redis.sets[0][0], "cost_statistics:month:active:2026-05")
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_cost_statistics_api_reads_sql_and_populates_short_redis_cache(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_view": lambda *_args, **_kwargs: {
                    "payload": {"month": "2026-05", "time_rows": [{"transaction_id": "txn-1"}]},
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                }
            },
        )()
        app._cost_statistics_service = type(
            "CostStats",
            (),
            {"get_explorer": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API SQL hit must not sync rebuild"))},
        )()

        response = app._handle_api_cost_statistics_explorer("2026-05", "active")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["time_rows"], [{"transaction_id": "txn-1"}])
        self.assertEqual(redis.sets[0][0], "cost_statistics:explorer:active:2026-05")
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_cost_statistics_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def rebuild_cost_statistics_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={"scope_key": "active:2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, ["active:2026-05"])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:2026-05")])
        self.assertEqual(result["entry_count"], 1)

    def test_cost_statistics_refresh_handler_expands_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def list_cost_statistics_scope_shards(self, scope_key: str) -> list[str]:
                return ["active:2026-05", "active:2026-04"]

            def rebuild_cost_statistics_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        service = CostStatisticsReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={"scope_key": "active:all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "cost_statistics_all_shard"),
                ("cost_statistics", "active:2026-04", "cost_statistics_all_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:all")])
        self.assertEqual(result["entry_count"], 0)

    def test_cost_statistics_invalidation_marks_dirty_even_when_no_cached_model_exists(self) -> None:
        class EmptyCostReadModelService:
            def invalidate_months(self, *_args, **_kwargs) -> list[str]:
                return []

            def snapshot(self) -> dict[str, object]:
                return {"read_models": {}}

            def scope_key(self, month: str, project_scope: str) -> str:
                return f"{project_scope}:{month}"

        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_read_model_service = EmptyCostReadModelService()
        app._persist_cost_statistics_read_models_best_effort = lambda **_kwargs: None
        app._schedule_cost_statistics_cache_warmup = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("SQL runtime invalidation should enqueue durable refresh when queue exists")
        )

        deleted = app._invalidate_cost_statistics_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )
        self.assertEqual(
            redis.deletes,
            [
                "cost_statistics:explorer:active:2026-05",
                "cost_statistics:month:active:2026-05",
                "cost_statistics:explorer:all:2026-05",
                "cost_statistics:month:all:2026-05",
            ],
        )


if __name__ == "__main__":
    unittest.main()

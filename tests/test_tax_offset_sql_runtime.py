from __future__ import annotations

import json
from http import HTTPStatus
import unittest

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.tax_offset_read_model_refresh import TaxOffsetReadModelRefreshService


def tax_payload(month: str = "2026-05") -> dict[str, object]:
    return {
        "month": month,
        "summary": {
            "output_tax": "0.00",
            "input_tax": "0.00",
            "planned_input_tax": "0.00",
            "certified_input_tax": "0.00",
            "deductible_tax": "0.00",
            "result_label": "本月留抵税额",
            "result_amount": "0.00",
        },
        "output_items": [{"id": "output-1"}],
        "input_plan_items": [{"id": "input-1"}],
        "certified_items": [],
        "certified_matched_rows": [],
        "certified_outside_plan_rows": [],
        "locked_certified_input_ids": [],
        "default_selected_output_ids": [],
        "default_selected_input_ids": [],
    }


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


class FailingRedisRecorder(RedisRecorder):
    def get_json(self, key: str) -> dict | None:
        self.gets.append(key)
        raise TimeoutError("redis timeout")

    def set_json(self, key: str, value: dict, *, ttl_seconds: int) -> bool:
        self.sets.append((key, value, ttl_seconds))
        raise TimeoutError("redis timeout")

    def delete(self, key: str) -> bool:
        self.deletes.append(key)
        raise TimeoutError("redis timeout")


class TaxOffsetReadConnection:
    def __init__(self, *, read_model_row: dict | None = None, item_rows: list[dict] | None = None, dirty: bool = False) -> None:
        self.read_model_row = read_model_row
        self.item_rows = list(item_rows or [])
        self.dirty = dirty
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.tax_offset_read_models" in normalized:
            return self.read_model_row
        if "from job.read_model_dirty_scopes" in normalized:
            return {"status": "pending", "updated_at": "2026-05-21T09:00:00+00:00"} if self.dirty else None
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.tax_offset_items" in normalized:
            return self.item_rows
        return []


class TaxOffsetSqlRuntimeTests(unittest.TestCase):
    def test_repository_reads_tax_offset_view_and_dirty_status_from_sql(self) -> None:
        connection = TaxOffsetReadConnection(
            read_model_row={
                "scope_key": "2026-05",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 2,
                "schema_version": "2026-05-tax-offset-month-v1",
                "payload": {"payload": tax_payload("2026-05"), "schema_version": "2026-05-tax-offset-month-v1"},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_tax_offset_view(scope_key="2026-05")

        self.assertEqual(view["payload"]["input_plan_items"], [{"id": "input-1"}])
        self.assertEqual(view["schema_version"], "2026-05-tax-offset-month-v1")
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_prefers_tax_offset_item_table_over_snapshot_item_arrays(self) -> None:
        connection = TaxOffsetReadConnection(
            read_model_row={
                "scope_key": "2026-05",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "schema_version": "2026-05-tax-offset-month-v1",
                "payload": {"payload": tax_payload("2026-05"), "schema_version": "2026-05-tax-offset-month-v1"},
            },
            item_rows=[
                {
                    "item_type": "input_plan",
                    "item_index": 0,
                    "item_id": "input-native",
                    "payload": {"id": "input-native", "seller_name": "供应商A"},
                }
            ],
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_tax_offset_view(scope_key="2026-05")

        self.assertEqual(view["payload"]["input_plan_items"], [{"id": "input-native", "seller_name": "供应商A"}])
        self.assertEqual(view["payload"]["output_items"], [])

    def test_tax_offset_api_reads_redis_hot_cache_without_sql_or_sync_build(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": RedisRecorder({"payload": tax_payload("2026-05")})},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {"get_tax_offset_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SQL should not be hit on Redis cache"))},
        )()
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {"get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API cache hit must not sync rebuild"))},
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["month"], "2026-05")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_tax_offset_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {"get_tax_offset_view": lambda *_args, **_kwargs: None},
        )()
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {"get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API miss must not sync rebuild"))},
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["input_plan_items"], [])
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "api_miss")])

    def test_production_postgres_tax_offset_requires_sql_read_model_without_sync_build(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._tax_offset_sql_read_repository = None
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {"get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("production API must not sync rebuild"))},
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "api_sql_repository_unavailable")])

    def test_tax_offset_api_reads_sql_and_populates_short_redis_cache(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {
                "get_tax_offset_view": lambda *_args, **_kwargs: {
                    "payload": tax_payload("2026-05"),
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "schema_version": "2026-05-tax-offset-month-v1",
                    "source_versions": app._tax_offset_expected_source_versions(),
                }
            },
        )()
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {"get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("API SQL hit must not sync rebuild"))},
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["input_plan_items"], [{"id": "input-1"}])
        self.assertTrue(
            redis.sets[0][0].startswith("tax_offset:month:2026-05:schema:2026-05-tax-offset-month-v1:sources:")
        )
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_tax_offset_api_falls_back_to_sql_when_redis_times_out(self) -> None:
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": FailingRedisRecorder()},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {
                "get_tax_offset_view": lambda *_args, **_kwargs: {
                    "payload": tax_payload("2026-05"),
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "schema_version": "2026-05-tax-offset-month-v1",
                    "source_versions": app._tax_offset_expected_source_versions(),
                }
            },
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["month"], "2026-05")
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_tax_offset_summary_api_uses_small_redis_key_and_omits_items(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {
                "get_tax_offset_view": lambda *_args, **_kwargs: {
                    "payload": tax_payload("2026-05"),
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "schema_version": "2026-05-tax-offset-month-v1",
                    "source_versions": app._tax_offset_expected_source_versions(),
                }
            },
        )()

        response = app._handle_api_tax_offset_summary("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["month"], "2026-05")
        self.assertEqual(payload["item_counts"]["output_items"], 1)
        self.assertEqual(payload["item_counts"]["input_plan_items"], 1)
        self.assertNotIn("output_items", payload)
        self.assertNotIn("input_plan_items", payload)
        self.assertTrue(
            redis.sets[0][0].startswith("tax_offset:summary:2026-05:schema:2026-05-tax-offset-month-v1:sources:")
        )

    def test_tax_offset_summary_api_reads_small_redis_cache_without_sql(self) -> None:
        cached_summary = {
            "month": "2026-05",
            "summary": {"output_tax": "0.00"},
            "item_counts": {"output_items": 8},
        }
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": RedisRecorder({"payload": cached_summary})},
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {"get_tax_offset_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("SQL should not be hit on summary Redis cache"))},
        )()

        response = app._handle_api_tax_offset_summary("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["item_counts"]["output_items"], 8)
        self.assertEqual(payload["read_model_status"], "fresh")

    def test_tax_offset_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def rebuild_tax_offset_read_model_scope(self, scope_key: str) -> dict[str, object]:
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = TaxOffsetReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-1",
            tenant_id="tenant-a",
            event_type="tax_offset.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="2026-05",
            scope_type="tax_offset",
            scope_key="2026-05",
            dedupe_key=None,
            payload={"scope_key": "2026-05"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, ["2026-05"])
        self.assertEqual(queue.completed, [("tenant-a", "tax_offset", "2026-05")])
        self.assertEqual(result["entry_count"], 2)

    def test_tax_offset_refresh_handler_expands_all_into_month_shards(self) -> None:
        class FakeBuilder:
            def list_tax_offset_scope_shards(self, scope_key: str) -> list[str]:
                return ["2026-05", "2026-04"]

            def rebuild_tax_offset_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        service = TaxOffsetReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="tax_offset.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="tax_offset",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all"},
            attempts=1,
            status="processing",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            queue.refreshes,
            [
                ("tax_offset", "2026-05", "tax_offset_all_shard"),
                ("tax_offset", "2026-04", "tax_offset_all_shard"),
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "tax_offset", "all")])
        self.assertEqual(result["entry_count"], 0)

    def test_tax_offset_invalidation_marks_dirty_and_deletes_redis_even_when_no_cached_model_exists(self) -> None:
        class EmptyTaxOffsetReadModelService:
            def invalidate_months(self, *_args, **_kwargs) -> list[str]:
                return []

            def snapshot(self) -> dict[str, object]:
                return {"read_models": {}}

            def scope_key(self, month: str) -> str:
                return month

        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._tax_offset_service = type("TaxOffsetService", (), {"clear_month_cache": lambda *_args, **_kwargs: None})()
        app._tax_offset_read_model_service = EmptyTaxOffsetReadModelService()
        app._persist_tax_offset_read_models_best_effort = lambda **_kwargs: None
        app._schedule_tax_offset_cache_warmup = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("SQL runtime invalidation should enqueue durable refresh when queue exists")
        )

        deleted = app._invalidate_tax_offset_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "unit_test")])
        self.assertIn("tax_offset:month:2026-05", redis.deletes)
        self.assertIn("tax_offset:summary:2026-05", redis.deletes)
        self.assertTrue(any(":schema:2026-05-tax-offset-month-v1:sources:" in key for key in redis.deletes))

    def test_tax_offset_invalidation_ignores_redis_delete_timeout(self) -> None:
        queue = QueueRecorder()
        redis = FailingRedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()

        app._delete_tax_offset_redis_cache("2026-05")

        self.assertIn("tax_offset:month:2026-05", redis.deletes)
        self.assertIn("tax_offset:summary:2026-05", redis.deletes)
        self.assertTrue(any(":schema:2026-05-tax-offset-month-v1:sources:" in key for key in redis.deletes))


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from http import HTTPStatus

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent
from fin_ops_platform.services.tax_offset_read_model_refresh import TaxOffsetReadModelRefreshService
from fin_ops_platform.services.tax_offset_read_model_repository import TaxOffsetReadModelRepositoryPort
from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetReadModelService,
)
from fin_ops_platform.services.tax_offset_sql_projection import TaxOffsetSqlProjectionBuilder
from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService


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


def redis_fresh_payload(
    payload: dict[str, object],
    *,
    scope_key: str,
    source_versions: dict[str, object],
) -> dict[str, object]:
    cached_payload = dict(payload)
    cached_payload["read_model_status"] = "fresh"
    cached_payload["read_model_scope_key"] = scope_key
    cached_payload["read_model_schema_version"] = TAX_OFFSET_READ_MODEL_SCHEMA_VERSION
    cached_payload["source_versions"] = dict(source_versions)
    return {
        "payload": cached_payload,
        "fresh_gate": {
            "scope_key": scope_key,
            "read_model_status": "fresh",
            "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            "source_versions": dict(source_versions),
        },
    }


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.refresh_requests: list[dict[str, object]] = []
        self.completed: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(
        self,
        *,
        scope_type: str,
        scope_key: str,
        reason: str,
        tenant_id: str = "default",
        priority: str = "normal",
        trace_id: str | None = None,
        metadata: dict[str, object] | None = None,
    ) -> None:
        self.refreshes.append((scope_type, scope_key, reason))
        self.refresh_requests.append(
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "reason": reason,
                "tenant_id": tenant_id,
                "priority": priority,
                "trace_id": trace_id,
                "metadata": dict(metadata) if isinstance(metadata, dict) else None,
            }
        )

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


class TaxOffsetReadModelRepositoryPortTests(unittest.TestCase):
    def test_projection_source_version_uses_certified_record_created_at(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.sql: list[str] = []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object]:
                self.sql.append(sql)
                return {"row_count": 0, "max_updated_at": None}

        connection = Connection()
        builder = TaxOffsetSqlProjectionBuilder(connection=connection, tax_offset_read_model_repository=object())

        versions = builder._source_versions()

        certified_sql = next(sql for sql in connection.sql if "tax_certified_import_records" in sql)
        self.assertIn("max(created_at)", certified_sql)
        self.assertEqual(versions["tax_certified_import_source_version"], "rows:0|max_updated_at:")

    def test_api_source_version_uses_same_certified_created_at_contract(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.sql: list[str] = []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object]:
                self.sql.append(sql)
                return {"row_count": 1, "max_updated_at": "2026-05-11 00:00:00+00"}

        connection = Connection()
        app = object.__new__(Application)
        app._state_store = type("StateStore", (), {"_connection": connection})()

        version = app._tax_offset_certified_import_source_version()

        self.assertIn("max(created_at)", connection.sql[0])
        self.assertEqual(version, "rows:1|max_updated_at:2026-05-11 00:00:00+00")

    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Underlying:
            def load_tax_offset_read_models(self) -> dict[str, object]:
                return {"read_models": {}}

            def get_tax_offset_view(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "payload": {}}

            def save_tax_offset_read_models(
                self,
                _snapshot: dict[str, object],
                *,
                changed_scope_keys: set[str] | None = None,
            ) -> None:
                _ = changed_scope_keys

            def get_cost_statistics_view(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("Tax offset port must not expose cost statistics reads.")

            def list_turnover_ledger_view(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("Tax offset port must not expose turnover ledger reads.")

        port = TaxOffsetReadModelRepositoryPort(Underlying())

        self.assertEqual(port.load_tax_offset_read_models(), {"read_models": {}})
        self.assertEqual(port.get_tax_offset_view(scope_key="2026-05")["scope_key"], "2026-05")
        self.assertFalse(hasattr(port, "get_cost_statistics_view"))
        self.assertFalse(hasattr(port, "list_turnover_ledger_view"))

    def test_projection_builder_saves_tax_scope_through_tax_port(self) -> None:
        saved: list[tuple[dict[str, object], set[str] | None]] = []

        class TaxPort:
            def save_tax_offset_read_models(
                self,
                snapshot: dict[str, object],
                *,
                changed_scope_keys: set[str] | None = None,
            ) -> None:
                saved.append((snapshot, changed_scope_keys))

        builder = object.__new__(TaxOffsetSqlProjectionBuilder)
        builder._tax_offset_read_model_repository = TaxPort()
        builder._build_tax_payload = lambda month: tax_payload(month)
        builder._source_versions = lambda: {"tax_source": "v1"}
        builder._set_redis_json = lambda *_args, **_kwargs: True

        result = builder.rebuild_tax_offset_read_model_scope("2026-05")

        self.assertEqual(result["scope_key"], "2026-05")
        self.assertEqual(saved[0][1], {"2026-05"})
        self.assertIn("2026-05", saved[0][0]["read_models"])


class TaxOffsetReadConnection:
    def __init__(
        self,
        *,
        read_model_row: dict | None = None,
        item_rows: list[dict] | None = None,
        dirty: bool = False,
        statistics_row: dict | None = None,
    ) -> None:
        self.read_model_row = read_model_row
        self.item_rows = list(item_rows or [])
        self.dirty = dirty
        self.statistics_row = statistics_row
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "check: tax_offset_page_statistics" in normalized:
            return self.statistics_row
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
    def test_runtime_refuses_shared_cache_keys_without_a_statistics_generation_token(self) -> None:
        runtime = TaxOffsetRuntimeService()
        source_versions = {"tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION}

        with self.assertRaises(ValueError):
            runtime.redis_cache_key(
                "2026-05",
                source_versions=source_versions,
            )
        with self.assertRaises(ValueError):
            runtime.summary_redis_cache_key(
                "2026-05",
                source_versions=source_versions,
            )

    def test_tax_offset_all_scope_shards_include_existing_projection_scopes(self) -> None:
        class ScopeConnection:
            def __init__(self) -> None:
                self.sql = ""

            def fetch_all(self, sql: str, _params: tuple = ()) -> list[dict[str, str]]:
                self.sql = " ".join(sql.lower().split())
                return [
                    {"scope_key": "2026-07"},
                    {"scope_key": "2023-05"},
                    {"scope_key": "invalid"},
                ]

        connection = ScopeConnection()
        builder = TaxOffsetSqlProjectionBuilder(connection=connection)

        scopes = builder.list_tax_offset_scope_shards("all")

        self.assertEqual(scopes, ["2026-07", "2023-05"])
        self.assertIn("from app.invoices", connection.sql)
        self.assertIn("from app.tax_certified_import_records", connection.sql)
        self.assertIn("from read_model.tax_offset_read_models", connection.sql)

    def test_repository_reads_tax_offset_view_and_dirty_status_from_sql(self) -> None:
        connection = TaxOffsetReadConnection(
            read_model_row={
                "scope_key": "2026-05",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 2,
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "payload": {"payload": tax_payload("2026-05"), "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION},
            },
            dirty=True,
        )
        repository = PostgresReadModelRepository(connection)

        view = repository.get_tax_offset_view(scope_key="2026-05")

        self.assertEqual(view["payload"]["input_plan_items"], [{"id": "input-1"}])
        self.assertEqual(view["schema_version"], TAX_OFFSET_READ_MODEL_SCHEMA_VERSION)
        self.assertEqual(view["refresh_status"], "refreshing")
        self.assertTrue(all("app_settings" not in sql for sql, _params in connection.fetch_one_calls))

    def test_repository_returns_only_fresh_unfiltered_tax_statistics(self) -> None:
        connection = TaxOffsetReadConnection(
            read_model_row={
                "scope_key": "2026-05",
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "cache_status": "fresh",
                "payload": {"payload": tax_payload("2026-05")},
            },
            statistics_row={
                "statistics_fresh": True,
                "input_invoice_count": 8,
                "output_invoice_count": 5,
                "certification_record_count": 4,
                "matched_certification_count": 3,
                "out_of_scope_certification_count": 1,
                "selected_invoice_count": 10,
            },
        )

        view = PostgresReadModelRepository(connection).get_tax_offset_view(scope_key="2026-05")

        self.assertEqual(view["payload"]["statistics"]["input_invoice_count"], 8)
        self.assertEqual(view["payload"]["statistics"]["unmatched_certification_count"], 1)
        self.assertEqual(view["payload"]["statistics"]["unselected_invoice_count"], 3)

        connection.statistics_row = {"statistics_fresh": False}
        stale_view = PostgresReadModelRepository(connection).get_tax_offset_view(scope_key="2026-05")
        self.assertIsNone(stale_view["payload"]["statistics"])

    def test_repository_prefers_tax_offset_item_table_over_snapshot_item_arrays(self) -> None:
        connection = TaxOffsetReadConnection(
            read_model_row={
                "scope_key": "2026-05",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "payload": {"payload": tax_payload("2026-05"), "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION},
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
        source_versions = app._tax_offset_source_versions()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {
                "queue_repository": QueueRecorder(),
                "redis_helper": RedisRecorder(
                    redis_fresh_payload(
                        tax_payload("2026-05"),
                        scope_key="2026-05",
                        source_versions=source_versions,
                    )
                ),
            },
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {
                "tax_offset_statistics_generation_token": lambda _self: "generation-1",
                "get_tax_offset_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("SQL should not be hit on Redis cache")
                )
            },
        )()
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {
                "get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("API cache hit must not sync rebuild")
                )
            },
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
            {
                "get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("API miss must not sync rebuild")
                )
            },
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
            {
                "get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("production API must not sync rebuild")
                )
            },
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["error"], "read_model_unavailable")
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "api_sql_repository_unavailable")])

    def test_production_postgres_tax_offset_calculate_miss_queues_refresh_without_sync_build(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
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
            {
                "calculate": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("production calculate must not sync rebuild")
                )
            },
        )()

        response = app._handle_api_tax_offset_calculate(
            json.dumps(
                {
                    "month": "2026-05",
                    "selected_output_ids": ["output-1"],
                    "selected_input_ids": ["input-1"],
                }
            )
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "api_miss")])

    def test_tax_offset_api_reads_sql_without_shared_cache_when_generation_token_is_missing(self) -> None:
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
                    "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                    "source_versions": app._tax_offset_expected_source_versions(),
                }
            },
        )()
        app._tax_api_routes = type(
            "TaxRoutes",
            (),
            {
                "get_tax_offset": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("API SQL hit must not sync rebuild")
                )
            },
        )()

        response = app._handle_api_tax_offset("2026-05")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["input_plan_items"], [{"id": "input-1"}])
        self.assertEqual(redis.gets, [])
        self.assertEqual(redis.sets, [])

    def test_tax_offset_api_invalidates_cross_month_statistics_cache_and_enqueues_all(self) -> None:
        class StatisticsRepository:
            def __init__(self, source_versions: dict[str, object]) -> None:
                self.token = "generation-1"
                self.source_versions = source_versions

            def tax_offset_statistics_generation_token(self) -> str:
                return self.token

            def get_tax_offset_view(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                payload = tax_payload("2026-05")
                payload["statistics"] = None
                payload["statistics_status"] = "refreshing"
                return {
                    "payload": payload,
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                    "source_versions": self.source_versions,
                }

        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        repository = StatisticsRepository(app._tax_offset_expected_source_versions())
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._tax_offset_sql_read_repository = repository

        first = json.loads(app._handle_api_tax_offset("2026-05").body)
        repository.token = "generation-2"
        second = json.loads(app._handle_api_tax_offset("2026-05").body)

        self.assertIsNone(first["statistics"])
        self.assertEqual(first["statistics_status"], "refreshing")
        self.assertIsNone(second["statistics"])
        self.assertNotEqual(redis.sets[0][0], redis.sets[1][0])
        self.assertEqual(
            queue.refreshes,
            [
                ("tax_offset", "all", "api_statistics_refreshing"),
                ("tax_offset", "all", "api_statistics_refreshing"),
            ],
        )

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
                    "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
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
                "tax_offset_statistics_generation_token": lambda _self: "generation-1",
                "get_tax_offset_view": lambda *_args, **_kwargs: {
                    "payload": tax_payload("2026-05"),
                    "refresh_status": "fresh",
                    "generated_at": "2026-05-21T09:00:00+00:00",
                    "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
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
            redis.sets[0][0].startswith(
                f"tax_offset:summary:2026-05:schema:{TAX_OFFSET_READ_MODEL_SCHEMA_VERSION}:sources:"
            )
        )

    def test_tax_offset_summary_api_reads_small_redis_cache_without_sql(self) -> None:
        cached_summary = {
            "month": "2026-05",
            "summary": {"output_tax": "0.00"},
            "item_counts": {"output_items": 8},
        }
        app = object.__new__(Application)
        source_versions = app._tax_offset_source_versions()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {
                "queue_repository": QueueRecorder(),
                "redis_helper": RedisRecorder(
                    redis_fresh_payload(
                        cached_summary,
                        scope_key="2026-05",
                        source_versions=source_versions,
                    )
                ),
            },
        )()
        app._tax_offset_sql_read_repository = type(
            "SqlTaxOffset",
            (),
            {
                "tax_offset_statistics_generation_token": lambda _self: "generation-1",
                "get_tax_offset_view": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("SQL should not be hit on summary Redis cache")
                )
            },
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

    def test_tax_offset_all_force_refresh_propagates_control_metadata_to_month_shards(self) -> None:
        class FakeBuilder:
            def list_tax_offset_scope_shards(self, scope_key: str) -> list[str]:
                return ["2026-05", "2026-04"]

            def rebuild_tax_offset_read_model_scope(self, scope_key: str) -> dict[str, object]:
                raise AssertionError(scope_key)

        queue = QueueRecorder()
        service = TaxOffsetReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all-force",
            tenant_id="tenant-a",
            event_type="tax_offset.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="all",
            scope_type="tax_offset",
            scope_key="all",
            dedupe_key=None,
            payload={"scope_key": "all", "metadata": {"force_refresh": True}},
            attempts=1,
            status="processing",
            priority="high",
            trace_id="tax-offset-force-trace",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["enqueued_scope_keys"], ["2026-05", "2026-04"])
        self.assertEqual(
            queue.refresh_requests,
            [
                {
                    "scope_type": "tax_offset",
                    "scope_key": "2026-05",
                    "reason": "tax_offset_all_shard",
                    "tenant_id": "tenant-a",
                    "priority": "high",
                    "trace_id": "tax-offset-force-trace",
                    "metadata": {"force_refresh": True},
                },
                {
                    "scope_type": "tax_offset",
                    "scope_key": "2026-04",
                    "reason": "tax_offset_all_shard",
                    "tenant_id": "tenant-a",
                    "priority": "high",
                    "trace_id": "tax-offset-force-trace",
                    "metadata": {"force_refresh": True},
                },
            ],
        )
        self.assertEqual(queue.completed, [("tenant-a", "tax_offset", "all")])

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
        app._tax_offset_sql_read_repository = type(
            "StatisticsTokenRepository",
            (),
            {"tax_offset_statistics_generation_token": lambda _self: "generation-1"},
        )()
        app._persist_tax_offset_read_models_best_effort = lambda **_kwargs: None
        app._schedule_tax_offset_cache_warmup = lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("SQL runtime invalidation should enqueue durable refresh when queue exists")
        )

        deleted = app._invalidate_tax_offset_read_model_scopes(["2026-05"], reason="unit_test")

        self.assertEqual(deleted, [])
        self.assertEqual(queue.refreshes, [("tax_offset", "2026-05", "unit_test")])
        self.assertEqual(len(redis.deletes), 2)
        self.assertTrue(all(f":schema:{TAX_OFFSET_READ_MODEL_SCHEMA_VERSION}:sources:" in key for key in redis.deletes))
        self.assertTrue(all("missing" not in key for key in redis.deletes))

    def test_invoice_change_invalidates_all_tax_scopes_because_source_version_is_global(self) -> None:
        read_models = TaxOffsetReadModelService()
        for month in ("2026-04", "2026-06"):
            read_models.upsert_read_model(
                month,
                tax_payload(month),
                generated_at="2026-07-01T00:00:00+00:00",
            )
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._tax_offset_sql_read_repository = type(
            "StatisticsTokenRepository",
            (),
            {"tax_offset_statistics_generation_token": lambda _self: "generation-1"},
        )()
        app._tax_offset_service = type("TaxOffsetService", (), {"clear_month_cache": lambda *_args: None})()
        app._tax_offset_read_model_service = read_models
        app._persist_tax_offset_read_models_best_effort = lambda **_kwargs: None
        app._schedule_tax_offset_cache_warmup = lambda *_args, **_kwargs: None

        deleted = app._invalidate_tax_offset_read_model_scopes(["2026-05"], reason="invoice_import_confirmed")

        self.assertEqual(deleted, ["2026-04", "2026-06"])
        self.assertEqual(
            queue.refreshes,
            [
                ("tax_offset", "2026-04", "invoice_import_confirmed"),
                ("tax_offset", "2026-05", "invoice_import_confirmed"),
                ("tax_offset", "2026-06", "invoice_import_confirmed"),
            ],
        )

    def test_tax_offset_invalidation_ignores_redis_delete_timeout(self) -> None:
        queue = QueueRecorder()
        redis = FailingRedisRecorder()
        app = object.__new__(Application)
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._tax_offset_sql_read_repository = type(
            "StatisticsTokenRepository",
            (),
            {"tax_offset_statistics_generation_token": lambda _self: "generation-1"},
        )()

        app._delete_tax_offset_redis_cache("2026-05")

        self.assertEqual(len(redis.deletes), 2)
        self.assertTrue(all(f":schema:{TAX_OFFSET_READ_MODEL_SCHEMA_VERSION}:sources:" in key for key in redis.deletes))
        self.assertTrue(all("missing" not in key for key in redis.deletes))


if __name__ == "__main__":
    unittest.main()

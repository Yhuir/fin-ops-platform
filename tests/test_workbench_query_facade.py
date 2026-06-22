from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.services.workbench_groups_page_cache import (
    WorkbenchGroupsPageCacheWarmer,
    build_workbench_groups_redis_cache_key_from_version,
    workbench_groups_sync_cache_warmup_enabled_from_env,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str]] = []

    def enqueue(self, scope_key: str, *, reason: str) -> None:
        self.refreshes.append((scope_key, reason))


class MetricRecorder:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def emit(self, **kwargs: object) -> None:
        self.calls.append(dict(kwargs))


class RedisRecorder:
    def __init__(self, *, json_values: dict[str, object] | None = None, text_values: dict[str, str] | None = None) -> None:
        self.json_values = dict(json_values or {})
        self.text_values = dict(text_values or {})
        self.get_json_calls: list[str] = []
        self.get_text_calls: list[str] = []
        self.set_json_calls: list[tuple[str, dict[str, object], int]] = []
        self.set_text_calls: list[tuple[str, str, int]] = []

    def get_json(self, key: str) -> object:
        self.get_json_calls.append(key)
        return self.json_values.get(key)

    def get_text(self, key: str) -> str | None:
        self.get_text_calls.append(key)
        return self.text_values.get(key)

    def set_json(self, key: str, value: dict[str, object], *, ttl_seconds: int) -> bool:
        self.set_json_calls.append((key, value, ttl_seconds))
        self.json_values[key] = value
        return True

    def set_text(self, key: str, value: str, *, ttl_seconds: int) -> bool:
        self.set_text_calls.append((key, value, ttl_seconds))
        self.text_values[key] = value
        return True


def no_stale_reasons(_source_versions: object, *, scope_key: str | None = None) -> list[str]:
    return []


def scope_key_for_month(month: str | None) -> str:
    return str(month or "all").strip() or "all"


class WorkbenchQueryFacadeTests(unittest.TestCase):
    def test_row_detail_reads_sql_row_without_application_live_sync(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def get_workbench_row_detail(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "row": {
                        "id": "oa-pay-1976",
                        "type": "oa",
                        "applicant": "刘际涛",
                        "detail_fields": {"OA单号": "oa-pay-1976"},
                    },
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                }

        repository = Repository()
        facade = WorkbenchQueryFacade(
            repository=repository,
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.row_detail(None, row_id="oa-pay-1976")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["row"]["id"], "oa-pay-1976")
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(repository.calls, [{"scope_key": "all", "row_id": "oa-pay-1976"}])

    def test_group_detail_stale_source_versions_do_not_return_stale_group(self) -> None:
        class Repository:
            def get_workbench_group_detail(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "group_id": "case:1",
                    "oa_rows": [{"id": "oa-1", "type": "oa"}],
                    "bank_rows": [],
                    "invoice_rows": [],
                    "source_versions": {"builder": "old"},
                    "read_model_status": "fresh",
                }

        def stale_reasons(_source_versions: object, *, scope_key: str | None = None) -> list[str]:
            return ["source_version_mismatch"]

        queue = QueueRecorder()
        metrics = MetricRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=stale_reasons,
            emit_status_metric=metrics.emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.group_detail("all", zone="open", group_id="case:1")

        self.assertEqual(result.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(result.payload["read_model_status"], "stale")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["source_version_mismatch"])
        self.assertNotIn("group", result.payload)
        self.assertEqual(queue.refreshes, [("all", "api_group_detail_source_versions_stale")])
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/groups/detail")
        self.assertEqual(metrics.calls[0]["read_model_status"], "stale")

    def test_group_detail_refreshing_status_does_not_return_stale_group(self) -> None:
        class Repository:
            def get_workbench_group_detail(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "group_id": "case:1",
                    "oa_rows": [{"id": "oa-1", "type": "oa"}],
                    "bank_rows": [],
                    "invoice_rows": [],
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "refreshing",
                }

        queue = QueueRecorder()
        metrics = MetricRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=metrics.emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.group_detail("all", zone="open", group_id="case:1")

        self.assertEqual(result.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertNotIn("group", result.payload)
        self.assertEqual(queue.refreshes, [("all", "api_group_detail_stale")])
        self.assertEqual(metrics.calls[0]["read_model_status"], "refreshing")

    def test_summary_missing_payload_enqueues_refresh_without_application_dependency(self) -> None:
        class Repository:
            def get_workbench_summary(self, **_kwargs: object) -> None:
                return None

        queue = QueueRecorder()
        metrics = MetricRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=metrics.emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.summary("all")

        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("all", "api_summary_miss")])
        self.assertEqual(metrics.calls[0]["reason"], "api_summary_miss")

    def test_groups_cache_hit_uses_granular_redis_dependency_without_page_query(self) -> None:
        class Repository:
            def get_workbench_groups_page(self, **_kwargs: object) -> object:
                raise AssertionError("cache hit must not query page")

        cache_key = "workbench:v7:groups:digest"
        redis = RedisRecorder(
            text_values={"workbench:groups:version:all": "v7"},
            json_values={
                cache_key: {
                    "payload": {
                        "month": "all",
                        "zone": "open",
                        "groups": [{"group_id": "cached"}],
                    }
                }
            },
        )
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=redis,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            groups_redis_version_key=lambda scope_key: f"workbench:groups:version:{scope_key}",
            groups_cache_key_from_version=lambda **_kwargs: cache_key,
        )

        result = facade.groups("all", zone="open")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["groups"][0]["group_id"], "cached")
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(redis.get_text_calls, ["workbench:groups:version:all"])
        self.assertEqual(redis.get_json_calls, [cache_key])

    def test_groups_uses_fast_freshness_status_instead_of_heavy_refresh_status(self) -> None:
        class Repository:
            def get_workbench_groups_freshness_status(self, **_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "fresh", "scope_key": "all"}

            def get_workbench_refresh_status(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("groups hot path must not run heavy refresh-status consistency audit")

            def get_workbench_groups_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "month": "all",
                    "zone": "open",
                    "groups": [{"group_id": "fresh-db"}],
                    "read_model_status": "fresh",
                    "source_versions": {"builder": "v1"},
                }

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.groups("all", zone="open")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["groups"][0]["group_id"], "fresh-db")
        self.assertEqual(result.payload["read_model_status"], "fresh")

    def test_groups_refreshing_status_bypasses_and_does_not_write_redis_payload(self) -> None:
        class Repository:
            def get_workbench_refresh_status(self, **_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "refreshing", "dirty_scopes": [{"scope_key": "all"}]}

            def get_workbench_groups_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "month": "all",
                    "zone": "open",
                    "groups": [{"group_id": "fresh-db"}],
                    "read_model_status": "fresh",
                    "source_versions": {"builder": "v1"},
                }

        cache_key = "workbench:v7:groups:digest"
        redis = RedisRecorder(
            text_values={"workbench:groups:version:all": "v7"},
            json_values={
                cache_key: {
                    "payload": {
                        "month": "all",
                        "zone": "open",
                        "groups": [{"group_id": "stale-cached"}],
                    }
                }
            },
        )
        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=redis,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            groups_redis_version_key=lambda scope_key: f"workbench:groups:version:{scope_key}",
            groups_cache_key_from_version=lambda **_kwargs: cache_key,
            groups_cache_version_from_key=lambda _cache_key: "v7",
            groups_redis_ttl_seconds=lambda: 600,
        )

        result = facade.groups("all", zone="open")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["groups"][0]["group_id"], "fresh-db")
        self.assertEqual(redis.get_json_calls, [])
        self.assertEqual(redis.set_json_calls, [])
        self.assertEqual(queue.refreshes, [("all", "api_groups_source_versions_stale")])

    def test_groups_query_timeout_returns_retryable_unavailable(self) -> None:
        class Repository:
            def get_workbench_groups_freshness_status(self, **_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "fresh", "scope_key": "all"}

            def get_workbench_groups_page(self, **_kwargs: object) -> dict[str, object]:
                raise RuntimeError("canceling statement due to statement timeout")

        metrics = MetricRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=metrics.emit,
            missing_read_model_error=lambda _error: False,
            transient_read_model_error=lambda error: "statement timeout" in str(error).lower(),
        )

        result = facade.groups("all", zone="open")

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "read_model_temporarily_unavailable")
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["scope_key"], "all")
        self.assertEqual(result.payload["retryable"], True)
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/groups")
        self.assertEqual(metrics.calls[0]["reason"], "query_timeout")

    def test_refresh_status_query_timeout_returns_retryable_unavailable(self) -> None:
        class Repository:
            def get_workbench_refresh_status(self, **_kwargs: object) -> dict[str, object]:
                raise RuntimeError("canceling statement due to statement timeout")

        metrics = MetricRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=metrics.emit,
            missing_read_model_error=lambda _error: False,
            transient_read_model_error=lambda error: "statement timeout" in str(error).lower(),
        )

        result = facade.refresh_status("all")

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "read_model_temporarily_unavailable")
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["scope_key"], "all")
        self.assertEqual(result.payload["retryable"], True)
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/refresh-status")
        self.assertEqual(metrics.calls[0]["reason"], "query_timeout")


class WorkbenchGroupsPageCacheWarmerTests(unittest.TestCase):
    def test_sync_cache_warmup_is_disabled_by_default_and_explicitly_enabled(self) -> None:
        from unittest.mock import patch

        with patch.dict("os.environ", {}, clear=True):
            self.assertFalse(workbench_groups_sync_cache_warmup_enabled_from_env())
        with patch.dict("os.environ", {"FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED": "1"}):
            self.assertTrue(workbench_groups_sync_cache_warmup_enabled_from_env())

    def test_warmer_sets_version_key_and_homepage_summary_pages(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.page_calls: list[dict[str, object]] = []

            def workbench_groups_cache_version(self, **kwargs: object) -> str:
                self.version_kwargs = kwargs
                return "gen-active"

            def get_workbench_groups_page(self, **kwargs: object) -> dict[str, object]:
                self.page_calls.append(kwargs)
                return {
                    "month": kwargs["scope_key"],
                    "zone": kwargs["zone"],
                    "page": kwargs["page"],
                    "page_size": kwargs["page_size"],
                    "groups": [{"group_id": f"{kwargs['zone']}-1"}],
                    "read_model_status": "fresh",
                }

        repository = Repository()
        redis = RedisRecorder()
        warmer = WorkbenchGroupsPageCacheWarmer(
            repository=repository,
            redis_helper=redis,
            schema_version="schema-v1",
            ttl_seconds=120,
        )

        result = warmer.warm_scope("all")

        self.assertEqual(result["status"], "warmed")
        self.assertEqual(result["scope_key"], "all")
        self.assertEqual(result["cache_version"], "gen-active")
        self.assertEqual(result["warmed_pages"], 2)
        self.assertEqual(result["skipped_pages"], 0)
        self.assertEqual(redis.set_text_calls, [("workbench:groups:version:all", "gen-active", 120)])
        self.assertEqual([call["zone"] for call in repository.page_calls], ["paired", "open"])
        for call in repository.page_calls:
            self.assertEqual(call["page"], 1)
            self.assertEqual(call["page_size"], 200)
            self.assertEqual(call["detail_level"], "summary")
            self.assertEqual(call["search_mode"], "pane")
        expected_keys = [
            build_workbench_groups_redis_cache_key_from_version(
                cache_version="gen-active",
                schema_version="schema-v1",
                scope_key="all",
                zone=zone,
                page="1",
                page_size="200",
                status=None,
                source_kind=None,
                search=None,
                search_mode="pane",
                sort=None,
                detail_level="summary",
            )
            for zone in ("paired", "open")
        ]
        self.assertEqual([call[0] for call in redis.set_json_calls], expected_keys)
        self.assertEqual([call[2] for call in redis.set_json_calls], [120, 120])
        self.assertEqual(redis.set_json_calls[0][1]["payload"]["read_model_status"], "fresh")

    def test_warmer_does_not_cache_non_fresh_page_payload(self) -> None:
        class Repository:
            def workbench_groups_cache_version(self, **_kwargs: object) -> str:
                return "gen-active"

            def get_workbench_groups_page(self, **kwargs: object) -> dict[str, object]:
                return {
                    "month": kwargs["scope_key"],
                    "zone": kwargs["zone"],
                    "read_model_status": "refreshing",
                }

        redis = RedisRecorder()
        warmer = WorkbenchGroupsPageCacheWarmer(
            repository=Repository(),
            redis_helper=redis,
            schema_version="schema-v1",
            ttl_seconds=120,
        )

        result = warmer.warm_scope("all")

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["warmed_pages"], 0)
        self.assertEqual(result["skipped_pages"], 2)
        self.assertEqual(redis.set_text_calls, [("workbench:groups:version:all", "gen-active", 120)])
        self.assertEqual(redis.set_json_calls, [])


if __name__ == "__main__":
    unittest.main()

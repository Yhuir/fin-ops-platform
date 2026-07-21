from __future__ import annotations

from http import HTTPStatus
import unittest

from fin_ops_platform.services.workbench_groups_page_cache import (
    build_workbench_initial_redis_cache_key,
    build_workbench_groups_redis_cache_key_from_version,
    is_default_workbench_initial_query,
)
from fin_ops_platform.services.workbench_query_facade import WorkbenchQueryFacade
from fin_ops_platform.services.workbench_read_model_version import WorkbenchReadModelVersionConflictError


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
    def test_initial_page_reads_one_repository_contract_and_adds_oa_status(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def get_workbench_initial_page(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {"oa_count": 1},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-1",
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
            oa_status_provider=lambda: {"status": "ready"},
        )

        result = facade.initial_page(
            "all",
            paired_query={"sort": "bank:desc"},
            unpaired_query={"search": "云南"},
        )

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_version"], "generation-set-1")
        self.assertEqual(result.payload["oa_status"], {"status": "ready"})
        self.assertEqual(
            repository.calls,
            [
                {
                    "scope_key": "all",
                    "paired_query": {"sort": "bank:desc"},
                    "unpaired_query": {"search": "云南"},
                }
            ],
        )

    def test_initial_page_missing_generation_enqueues_refresh_and_returns_accepted(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> None:
                return None

        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.initial_page(None)

        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("all", "api_initial_page_miss")])

    def test_default_initial_page_cache_hit_skips_cold_repository_query(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-1",
                }

            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> object:
                raise AssertionError("version-matched cache hit must skip the cold query")

        cache_key = build_workbench_initial_redis_cache_key(
            cache_version="generation-set-1",
            scope_key="all",
        )
        assert cache_key is not None
        redis = RedisRecorder(
            json_values={
                cache_key: {
                    "payload": {
                        "month": "all",
                        "scope_key": "all",
                        "summary": {"oa_count": 7},
                        "paired": {"groups": [], "total": 0},
                        "unpaired": {"groups": [], "total": 0},
                        "source_versions": {"builder": "v1"},
                        "read_model_status": "fresh",
                        "read_model_version": "generation-set-1",
                    }
                }
            }
        )
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=redis,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["summary"]["oa_count"], 7)
        self.assertEqual(redis.get_json_calls, [cache_key])

    def test_default_initial_page_cache_miss_reads_cold_path_and_populates_versioned_cache(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.initial_calls = 0

            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-2",
                }

            def get_workbench_initial_page(self, **_kwargs: object) -> dict[str, object]:
                self.initial_calls += 1
                return {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {"oa_count": 2},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-2",
                }

        repository = Repository()
        redis = RedisRecorder()
        facade = WorkbenchQueryFacade(
            repository=repository,
            redis_helper=redis,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
            groups_redis_ttl_seconds=lambda: 120,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(repository.initial_calls, 1)
        self.assertEqual(len(redis.set_json_calls), 1)
        self.assertEqual(redis.set_json_calls[0][2], 120)
        self.assertEqual(redis.set_json_calls[0][1]["payload"]["read_model_version"], "generation-set-2")

    def test_month_initial_cache_key_changes_when_all_period_statistics_generation_changes(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.all_version = "generation-set-1"
                self.initial_calls = 0

            def get_workbench_groups_freshness_status(self, *, scope_key: str) -> dict[str, object]:
                return {
                    "scope_key": scope_key,
                    "read_model_status": "fresh",
                    "read_model_version": self.all_version if scope_key == "all" else "month-generation-1",
                }

            def get_workbench_initial_page(self, **_kwargs: object) -> dict[str, object]:
                self.initial_calls += 1
                return {
                    "month": "2026-05",
                    "scope_key": "2026-05",
                    "summary": {"oa_count": 1},
                    "statistics": {"oa_count": self.initial_calls},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                    "read_model_version": "month-generation-1",
                }

        repository = Repository()
        redis = RedisRecorder()
        facade = WorkbenchQueryFacade(
            repository=repository,
            redis_helper=redis,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        first = facade.initial_page("2026-05")
        repository.all_version = "generation-set-2"
        second = facade.initial_page("2026-05")

        self.assertEqual(first.payload["statistics"], {"oa_count": 1})
        self.assertEqual(second.payload["statistics"], {"oa_count": 2})
        self.assertEqual(repository.initial_calls, 2)
        self.assertEqual(len(redis.set_json_calls), 2)
        self.assertNotEqual(redis.set_json_calls[0][0], redis.set_json_calls[1][0])

    def test_default_initial_page_version_drift_fails_closed_without_caching_old_payload(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {
                    "scope_key": "all",
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-current",
                }

            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> dict[str, object]:
                return {
                    "month": "all",
                    "scope_key": "all",
                    "summary": {"oa_count": 7},
                    "paired": {"groups": [{"group_id": "old-paired"}], "total": 1},
                    "unpaired": {"groups": [{"group_id": "old-unpaired"}], "total": 1},
                    "source_versions": {"builder": "old"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-old",
                }

        queue = QueueRecorder()
        redis = RedisRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=redis,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["error"], "workbench_initial_page_version_drift")
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(result.payload["paired"]["groups"], [])
        self.assertEqual(result.payload["unpaired"]["groups"], [])
        self.assertEqual(queue.refreshes, [("all", "api_initial_page_version_drift")])
        self.assertEqual(redis.set_json_calls, [])

    def test_default_initial_page_redis_failure_degrades_to_same_cold_path(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "fresh", "read_model_version": "generation-set-3"}

            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"oa_count": 3},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-3",
                }

        class BrokenRedis:
            @staticmethod
            def get_json(_key: str) -> object:
                raise ConnectionError("redis down")

            @staticmethod
            def set_json(_key: str, _value: object, **_kwargs: object) -> object:
                raise ConnectionError("redis down")

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=BrokenRedis(),
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["summary"]["oa_count"], 3)

    def test_default_initial_page_refreshing_uses_same_version_cache_without_enqueuing_again(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {
                    "read_model_status": "refreshing",
                    "read_model_version": "generation-set-4",
                    "dirty_scopes": [{"scope_key": "2026-06", "status": "processing"}],
                }

            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> object:
                raise AssertionError("refreshing may reuse the immutable active generation payload")

        cache_key = build_workbench_initial_redis_cache_key(
            cache_version="generation-set-4",
            scope_key="all",
        )
        assert cache_key is not None
        redis = RedisRecorder(
            json_values={
                cache_key: {
                    "payload": {
                        "summary": {"oa_count": 4},
                        "paired": {"groups": [], "total": 0},
                        "unpaired": {"groups": [], "total": 0},
                        "source_versions": {"builder": "v1"},
                        "read_model_status": "fresh",
                        "read_model_version": "generation-set-4",
                    }
                }
            }
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
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [])

    def test_filtered_initial_page_bypasses_default_cache_and_reads_the_same_cold_contract(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def get_workbench_initial_page(self, **kwargs: object) -> dict[str, object]:
                self.calls.append(dict(kwargs))
                return {
                    "summary": {},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-5",
                }

        repository = Repository()
        redis = RedisRecorder(json_values={"unused": {"payload": {"read_model_version": "generation-set-5"}}})
        facade = WorkbenchQueryFacade(
            repository=repository,
            redis_helper=redis,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            initial_cache_key_from_version=build_workbench_initial_redis_cache_key,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all", paired_query={"search": "供应商"})

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(redis.get_json_calls, [])
        self.assertEqual(redis.set_json_calls, [])
        self.assertEqual(repository.calls[0]["paired_query"], {"search": "供应商"})

    def test_initial_page_stale_payload_is_explicit_and_enqueues_one_refresh(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "old"},
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-old",
                }

        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=lambda _versions, **_kwargs: ["builder_mismatch"],
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "stale")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["builder_mismatch"])
        self.assertEqual(queue.refreshes, [("all", "api_initial_page_stale")])

    def test_filtered_initial_page_refreshing_payload_does_not_enqueue_all_fan_out(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {},
                    "paired": {"groups": [], "total": 0},
                    "unpaired": {"groups": [], "total": 0},
                    "source_versions": {"builder": "v1"},
                    "read_model_status": "refreshing",
                    "read_model_version": "generation-set-current",
                }

        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            is_default_initial_query=is_default_workbench_initial_query,
        )

        result = facade.initial_page("all", paired_query={"search": "ETC"})

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [])

    def test_initial_page_timeout_returns_503_without_false_refresh_enqueue(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_initial_page(**_kwargs: object) -> object:
                raise RuntimeError("canceling statement due to statement timeout")

        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
            transient_read_model_error=lambda error: "statement timeout" in str(error).lower(),
        )

        result = facade.initial_page("all")

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "query_timeout")
        self.assertEqual(result.payload["read_model_status"], "unavailable")
        self.assertEqual(queue.refreshes, [])

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

    def test_row_detail_all_scope_does_not_run_a_second_scope_lookup_or_fallback_query(self) -> None:
        class Repository:
            def __init__(self) -> None:
                self.calls: list[dict[str, object]] = []

            def get_workbench_row_detail(self, **kwargs: object) -> dict[str, object] | None:
                self.calls.append(dict(kwargs))
                return None

            def find_workbench_row_scope_key(self, *, row_id: str) -> str | None:
                raise AssertionError(f"row detail must not run legacy scope lookup: {row_id}")

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

        result = facade.row_detail("all", row_id="txn_imported_0396")

        self.assertEqual(result.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(repository.calls, [{"scope_key": "all", "row_id": "txn_imported_0396"}])

    def test_row_detail_version_conflict_returns_409_contract(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_row_detail(**_kwargs: object) -> object:
                raise WorkbenchReadModelVersionConflictError(expected="old", current="current")

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.row_detail("all", row_id="bank-1", expected_read_model_version="old")

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["error"], "workbench_read_model_version_conflict")
        self.assertEqual(result.payload["read_model_version"], "current")

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

        result = facade.group_detail("all", zone="unpaired", group_id="case:1")

        self.assertEqual(result.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(result.payload["read_model_status"], "stale")
        self.assertEqual(result.payload["read_model_stale_reasons"], ["source_version_mismatch"])
        self.assertNotIn("group", result.payload)
        self.assertEqual(queue.refreshes, [("all", "api_group_detail_source_versions_stale")])
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/groups/detail")
        self.assertEqual(metrics.calls[0]["read_model_status"], "stale")

    def test_group_detail_refreshing_status_does_not_return_or_enqueue_stale_group(self) -> None:
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

        result = facade.group_detail("all", zone="unpaired", group_id="case:1")

        self.assertEqual(result.status_code, HTTPStatus.NOT_FOUND)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertNotIn("group", result.payload)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(metrics.calls[0]["read_model_status"], "refreshing")

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
                        "zone": "unpaired",
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

        result = facade.groups("all", zone="unpaired")

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
                    "zone": "unpaired",
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

        result = facade.groups("all", zone="unpaired")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["groups"][0]["group_id"], "fresh-db")
        self.assertEqual(result.payload["read_model_status"], "fresh")

    def test_groups_missing_exact_generation_stats_enqueues_refresh_and_returns_accepted(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "fresh", "scope_key": "all"}

            @staticmethod
            def get_workbench_groups_page(**_kwargs: object) -> None:
                return None

        queue = QueueRecorder()
        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=queue.enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.groups("all", zone="paired")

        self.assertEqual(result.status_code, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("all", "api_groups_miss")])

    def test_groups_version_conflict_is_rejected_before_cache_or_page_read(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "fresh", "read_model_version": "current"}

            @staticmethod
            def get_workbench_groups_page(**_kwargs: object) -> object:
                raise AssertionError("version conflict must stop before the page query")

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.groups("all", zone="paired", expected_read_model_version="old")

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["read_model_version"], "current")

    def test_groups_refreshing_status_bypasses_and_does_not_write_redis_payload(self) -> None:
        class Repository:
            def get_workbench_refresh_status(self, **_kwargs: object) -> dict[str, object]:
                return {"read_model_status": "refreshing", "dirty_scopes": [{"scope_key": "all"}]}

            def get_workbench_groups_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "month": "all",
                    "zone": "unpaired",
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
                        "zone": "unpaired",
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

        result = facade.groups("all", zone="unpaired")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["groups"][0]["group_id"], "fresh-db")
        self.assertEqual(redis.get_json_calls, [])
        self.assertEqual(redis.set_json_calls, [])
        self.assertEqual(queue.refreshes, [])

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

        result = facade.groups("all", zone="unpaired")

        self.assertEqual(result.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result.payload["error"], "query_timeout")
        self.assertEqual(result.payload["read_model_status"], "unavailable")
        self.assertEqual(result.payload["scope_key"], "all")
        self.assertEqual(result.payload["retryable"], True)
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/groups")
        self.assertEqual(metrics.calls[0]["reason"], "query_timeout")

    def test_write_precondition_requires_expected_generation_before_repository_access(self) -> None:
        facade = WorkbenchQueryFacade(
            repository=None,
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.write_precondition("all", expected_read_model_version=" ")

        self.assertEqual(result.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(result.payload["error"], "expected_read_model_version_required")

    def test_write_precondition_uses_fast_freshness_status_and_accepts_matching_fresh_generation(self) -> None:
        class Repository:
            def get_workbench_groups_freshness_status(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "read_model_status": "fresh",
                    "read_model_version": "generation-set-1",
                }

            def get_workbench_refresh_status(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("action gate must not run the heavy refresh-status consistency audit")

        facade = WorkbenchQueryFacade(
            repository=Repository(),
            redis_helper=None,
            enqueue_refresh=QueueRecorder().enqueue,
            scope_key_for_month=scope_key_for_month,
            stale_reasons=no_stale_reasons,
            emit_status_metric=MetricRecorder().emit,
            missing_read_model_error=lambda _error: False,
        )

        result = facade.write_precondition("all", expected_read_model_version="generation-set-1")

        self.assertEqual(result.status_code, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(result.payload["read_model_version"], "generation-set-1")

    def test_write_precondition_rejects_generation_conflict_before_freshness_status(self) -> None:
        class Repository:
            @staticmethod
            def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                return {
                    "read_model_status": "refreshing",
                    "read_model_version": "generation-set-2",
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

        result = facade.write_precondition("all", expected_read_model_version="generation-set-1")

        self.assertEqual(result.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(result.payload["error"], "workbench_read_model_version_conflict")
        self.assertEqual(result.payload["read_model_version"], "generation-set-2")

    def test_write_precondition_rejects_nonfresh_and_unavailable_statuses(self) -> None:
        for status, expected_http_status, expected_error in (
            ("refreshing", HTTPStatus.CONFLICT, "workbench_read_model_not_fresh"),
            ("stale", HTTPStatus.CONFLICT, "workbench_read_model_not_fresh"),
            ("failed", HTTPStatus.SERVICE_UNAVAILABLE, "workbench_read_model_unavailable"),
            ("unavailable", HTTPStatus.SERVICE_UNAVAILABLE, "workbench_read_model_unavailable"),
        ):
            with self.subTest(status=status):
                class Repository:
                    @staticmethod
                    def get_workbench_groups_freshness_status(**_kwargs: object) -> dict[str, object]:
                        return {
                            "read_model_status": status,
                            "read_model_version": "generation-set-1",
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

                result = facade.write_precondition("all", expected_read_model_version="generation-set-1")

                self.assertEqual(result.status_code, expected_http_status)
                self.assertEqual(result.payload["error"], expected_error)
                self.assertEqual(result.payload["read_model_status"], status)

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
        self.assertEqual(result.payload["error"], "query_timeout")
        self.assertEqual(result.payload["read_model_status"], "unavailable")
        self.assertEqual(result.payload["scope_key"], "all")
        self.assertEqual(result.payload["retryable"], True)
        self.assertEqual(metrics.calls[0]["endpoint"], "/api/workbench/refresh-status")
        self.assertEqual(metrics.calls[0]["reason"], "query_timeout")



if __name__ == "__main__":
    unittest.main()

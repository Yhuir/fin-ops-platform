from __future__ import annotations

import json
import unittest
from http import HTTPStatus

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.cost_statistics_query_service import (
    CostStatisticsExportLimitError,
    CostStatisticsQueryService,
    CostStatisticsReadModelNotFreshError,
)
from fin_ops_platform.services.cost_statistics_read_model_refresh import CostStatisticsReadModelRefreshService
from fin_ops_platform.services.cost_statistics_read_model_repository import CostStatisticsReadModelRepositoryPort
from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    cost_statistics_bank_flow_source_versions,
    cost_statistics_semantic_source_versions,
    cost_statistics_source_versions,
)
from fin_ops_platform.services.cost_statistics_sql_projection import CostStatisticsSqlProjectionBuilder
from fin_ops_platform.services.postgres_repositories.read_models import (
    BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
    PostgresReadModelRepository,
    _cost_statistics_page_statistics,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueEvent


class QueueRecorder:
    def __init__(self, *, complete_result: bool = True) -> None:
        self.refreshes: list[tuple[str, str, str]] = []
        self.refresh_details: list[dict[str, object]] = []
        self.completed: list[tuple[str, str, str, int]] = []
        self.complete_result = complete_result

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
        self.refresh_details.append(
            {
                "scope_type": scope_type,
                "scope_key": scope_key,
                "reason": reason,
                "tenant_id": tenant_id,
                "priority": priority,
                "trace_id": trace_id,
                **({"metadata": dict(metadata)} if isinstance(metadata, dict) else {}),
            }
        )

    def complete_read_model_refresh(
        self,
        *,
        tenant_id: str,
        scope_type: str,
        scope_key: str,
        source_version: int,
    ) -> bool:
        self.completed.append((tenant_id, scope_type, scope_key, source_version))
        return self.complete_result


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


class CostStatisticsAppSettingsStub:
    def get_bank_auto_tag_rules_payload(self, **_kwargs: object) -> dict[str, object]:
        return {"version": 7, "active_rules": []}

    def get_bank_account_mappings_payload(self) -> list[dict[str, str]]:
        return [{"bank_name": "工商银行", "last4": "0001", "id": "bank_mapping_0001", "short_name": ""}]

    def get_cost_statistics_source_settings_payload(self) -> dict[str, object]:
        return {
            "bank_transaction_tags": {"version": 7, "active_rules": []},
            "bank_account_mappings": self.get_bank_account_mappings_payload(),
            "cost_statistics_tag_selection": {},
        }

    def get_cost_statistics_tag_selection_payload(self, *, can_save: bool = False) -> dict[str, object]:
        del can_save
        return {
            "version": 1,
            "bank_auto_tag_rules_version": 7,
            "effective_selected_tag_codes": None,
            "selected_tag_codes": None,
        }


class CostStatisticsRuntimeStub:
    def request_scope_key(self, month: str, project_scope: str) -> str:
        return f"{project_scope}:{month}"

    def page_redis_cache_key(
        self,
        scope_key: str,
        query_fingerprint: str,
        *,
        source_versions: dict[str, object],
    ) -> str:
        return f"page:{scope_key}:{query_fingerprint}:{json.dumps(source_versions, sort_keys=True)}"

    def redis_ttl_seconds(self) -> int:
        return 120

    def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
        del scope_key, reason
        return True


class CostStatisticsSqlReadRepositoryStub:
    def __init__(
        self,
        payload: dict[str, object],
        source_versions: dict[str, object],
        *,
        source_settings: dict[str, object] | None = None,
    ) -> None:
        self.payload = payload
        self.source_versions = source_versions
        self.source_settings = source_settings or _cost_statistics_source_settings_fixture()

    def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
        return cost_statistics_fresh_gate(
            scope_key=scope_key,
            source_versions=self.source_versions,
            source_settings=self.source_settings,
        )

    def get_cost_statistics_transaction(
        self,
        *,
        project_scope: str,
        transaction_id: str,
    ) -> dict[str, object] | None:
        del project_scope
        for rows_key in ("time_rows", "bank_flow_time_rows"):
            for row in list(self.payload.get(rows_key) or []):
                if isinstance(row, dict) and row.get("transaction_id") == transaction_id:
                    return dict(row)
        return None


def _cost_statistics_source_settings_fixture() -> dict[str, object]:
    return CostStatisticsAppSettingsStub().get_cost_statistics_source_settings_payload()


def _cost_statistics_source_versions_fixture(scope_key: str) -> dict[str, object]:
    _project_scope, month = str(scope_key).split(":", 1)
    dependency_versions = {"source_version": 1} if month != "all" else None
    return cost_statistics_source_versions(
        month=month,
        settings_payload=_cost_statistics_source_settings_fixture(),
        workbench_source_versions=dependency_versions,
        bank_detail_source_versions=dependency_versions,
    )


def _fresh_workbench_dependency_versions(
    _scope_key: str,
) -> tuple[dict[str, object], dict[str, object]]:
    source_versions = {"source_version": 1}
    return source_versions, source_versions


def _fresh_workbench_dependency_versions_by_scope(
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    return {}, {}


def _enqueue_workbench_dependency_refresh(_scope_key: str, *, reason: str) -> bool:
    del reason
    return True


def cost_statistics_fresh_gate(
    *,
    scope_key: str,
    source_versions: dict[str, object],
    published_source_version: int = 0,
    refresh_status: str = "fresh",
    stale_reasons: list[str] | None = None,
    source_settings: dict[str, object] | None = None,
    workbench_source_versions: dict[str, object] | None = None,
    bank_detail_source_versions: dict[str, object] | None = None,
) -> dict[str, object]:
    normalized_source_settings = source_settings or _cost_statistics_source_settings_fixture()
    current_workbench_source_versions = (
        workbench_source_versions
        if workbench_source_versions is not None
        else source_versions.get("workbench_source_versions")
    )
    current_bank_detail_source_versions = (
        bank_detail_source_versions
        if bank_detail_source_versions is not None
        else source_versions.get("bank_detail_source_versions")
    )
    return {
        "scope_key": scope_key,
        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
        "generated_at": "2026-05-21T09:00:00+00:00",
        "source_versions": dict(source_versions),
        "source_settings": normalized_source_settings,
        "workbench_source_versions": (
            dict(current_workbench_source_versions)
            if isinstance(current_workbench_source_versions, dict)
            else {}
        ),
        "bank_detail_source_versions": (
            dict(current_bank_detail_source_versions)
            if isinstance(current_bank_detail_source_versions, dict)
            else {}
        ),
        "published_source_version": published_source_version,
        "dirty_source_version": published_source_version,
        "refresh_status": refresh_status,
        "bank_flow_refresh_status": refresh_status,
        "bank_flow_stale_reasons": list(stale_reasons or []),
        "bank_flow_bank_detail_refresh_scope_keys": [],
        "bank_flow_child_refresh_scope_keys": [],
        "statistics": {
            "transaction_count": 0,
            "expense_transaction_count": 0,
            "income_transaction_count": 0,
            "cost_group_count": 0,
            "tagged_transaction_count": 0,
            "untagged_transaction_count": 0,
            "project_count": 0,
            "expense_type_count": 0,
            "bank_tag_count": 0,
            "cost_transaction_count": 0,
        },
        "statistics_status": "fresh",
        "statistics_scope_key": f"{scope_key.split(':', 1)[0]}:all",
        "statistics_published_source_version": published_source_version,
        "stale_reasons": list(stale_reasons or []),
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
    cached_payload["read_model_schema_version"] = COST_STATISTICS_READ_MODEL_SCHEMA_VERSION
    cached_payload["source_versions"] = dict(source_versions)
    return {
        "payload": cached_payload,
        "fresh_gate": {
            "scope_key": scope_key,
            "read_model_status": "fresh",
            "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "source_versions": dict(source_versions),
        },
    }


class CostStatisticsQueryServiceTagFilterTests(unittest.TestCase):
    def test_bank_detail_execution_counter_change_does_not_stale_unchanged_cost_business_data(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        stored_versions = _cost_statistics_source_versions_fixture("active:2026-05")
        stored_versions["bank_detail_source_versions"] = {
            "source_version": 10,
            "bank_detail_source_signature": "same-business-data",
            "bank_auto_tag_rules_version": 7,
            "workbench_relation_source_versions": {"source_version": 20},
        }

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=stored_versions,
                    bank_detail_source_versions={
                        "source_version": 11,
                        "bank_detail_source_signature": "same-business-data",
                        "bank_auto_tag_rules_version": 7,
                        "workbench_relation_source_versions": {"source_version": 21},
                    },
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                    "available_years": [],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [],
                    "row_count": 0,
                    "next_cursor_values": None,
                }

        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "fresh", payload)

    def test_month_access_keeps_current_rows_and_refreshes_exact_stale_statistics_child(
        self,
    ) -> None:
        class Runtime(CostStatisticsRuntimeStub):
            def __init__(self) -> None:
                self.cost_refreshes: list[tuple[str, str]] = []

            def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
                self.cost_refreshes.append((scope_key, reason))
                return True

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                gate = cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=_cost_statistics_source_versions_fixture(scope_key),
                )
                gate["statistics"] = None
                gate["statistics_status"] = "stale"
                gate["statistics_child_refresh_scope_keys"] = ["active:2026-03"]
                return gate

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                    "available_years": [],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [],
                    "row_count": 0,
                    "next_cursor_values": None,
                }

        runtime = Runtime()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(
            runtime.cost_refreshes,
            [("active:2026-03", "api_statistics_stale")],
        )

    def test_month_access_refreshes_stale_workbench_dependency_before_cost_scope(self) -> None:
        class Runtime(CostStatisticsRuntimeStub):
            def __init__(self) -> None:
                self.cost_refreshes: list[tuple[str, str]] = []

            def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
                self.cost_refreshes.append((scope_key, reason))
                return True

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"stale Workbench must stop Cost gate I/O: {scope_key}")

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale Workbench must stop Cost payload I/O")

        runtime = Runtime()
        workbench_refreshes: list[tuple[str, str]] = []
        expected_versions = {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v2"}
        active_versions = {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v1"}
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=lambda _scope_key: (expected_versions, active_versions),
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=lambda scope_key, *, reason: (
                workbench_refreshes.append((scope_key, reason)) or True
            ),
        )

        payload, cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertFalse(cache_hit)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_dependency"], "workbench")
        self.assertEqual(
            payload["read_model_stale_reasons"],
            ["workbench_dependency_workbench_pair_relations_updated_at_mismatch"],
        )
        self.assertEqual(
            workbench_refreshes,
            [("2026-05", "cost_statistics_workbench_dependency_stale")],
        )
        self.assertEqual(runtime.cost_refreshes, [])

    def test_bank_tag_access_reads_fresh_bank_flow_rows_while_workbench_refreshes(self) -> None:
        workbench_refreshes: list[tuple[str, str]] = []
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                gate = cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    refresh_status="refreshing",
                    stale_reasons=["cost_statistics_dependency_refreshing"],
                )
                gate["bank_flow_refresh_status"] = "fresh"
                gate["bank_flow_stale_reasons"] = []
                return gate

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "88.00"},
                    "available_years": [2026],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [{"transaction_id": "bank-1", "amount": "88.00"}],
                    "row_count": 1,
                    "next_cursor_values": None,
                }

        expected_versions = {"builder": "workbench-month-v6", "relation": "v2"}
        active_versions = {"builder": "workbench-month-v6", "relation": "v1"}
        service = CostStatisticsQueryService(
            runtime_service=CostStatisticsRuntimeStub(),
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=lambda _scope_key: (
                expected_versions,
                active_versions,
            ),
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=lambda scope_key, *, reason: (
                workbench_refreshes.append((scope_key, reason)) or True
            ),
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="bank_tag",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "fresh", payload)
        self.assertEqual(payload["rows"][0]["transaction_id"], "bank-1")
        self.assertEqual(workbench_refreshes, [])

    def test_all_access_ignores_unrelated_active_dependency_events(self) -> None:
        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=_cost_statistics_source_versions_fixture(scope_key),
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                return {
                    "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                    "available_years": [],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [],
                    "row_count": 0,
                    "next_cursor_values": None,
                }

        service = CostStatisticsQueryService(
            runtime_service=CostStatisticsRuntimeStub(),
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="all",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "fresh")

    def test_parent_access_enqueues_only_exact_stale_bank_detail_dependency(self) -> None:
        bank_detail_refreshes: list[tuple[list[str], str]] = []

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return {
                    **cost_statistics_fresh_gate(
                        scope_key=scope_key,
                        source_versions=_cost_statistics_source_versions_fixture(scope_key),
                        refresh_status="stale",
                        stale_reasons=["cost_statistics_parent_bank_detail_dependency_not_fresh"],
                    ),
                    "bank_detail_refresh_scope_keys": ["2026-03"],
                }

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale Bank Detail dependency must stop Cost payload I/O")

        service = CostStatisticsQueryService(
            runtime_service=CostStatisticsRuntimeStub(),
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
            bank_detail_refresh_enqueuer=lambda scope_keys, *, reason: (
                bank_detail_refreshes.append((list(scope_keys), reason)) or True
            ),
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="all",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_dependency"], "bank_detail")
        self.assertEqual(payload["refresh_scope_keys"], ["2026-03"])
        self.assertEqual(
            bank_detail_refreshes,
            [
                (
                    ["2026-03"],
                    "cost_statistics_bank_detail_dependency_stale",
                )
            ],
        )

    def test_month_access_refreshes_only_cost_after_workbench_dependency_is_fresh(self) -> None:
        class Runtime(CostStatisticsRuntimeStub):
            def __init__(self) -> None:
                self.cost_refreshes: list[tuple[str, str]] = []

            def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
                self.cost_refreshes.append((scope_key, reason))
                return True

        current_workbench_versions = {
            "builder": "workbench-month-v6",
            "workbench_pair_relations_updated_at": "v2",
        }
        stale_cost_versions = cost_statistics_source_versions(
            month="2026-05",
            settings_payload=_cost_statistics_source_settings_fixture(),
            workbench_source_versions={
                "builder": "workbench-month-v6",
                "workbench_pair_relations_updated_at": "v1",
            },
            bank_detail_source_versions={"source_version": 1},
        )

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=stale_cost_versions,
                    workbench_source_versions=current_workbench_versions,
                    bank_detail_source_versions={"source_version": 1},
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale Cost gate must stop payload I/O")

        runtime = Runtime()
        workbench_refreshes: list[tuple[str, str]] = []
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=lambda _scope_key: (
                current_workbench_versions,
                current_workbench_versions,
            ),
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=lambda scope_key, *, reason: (
                workbench_refreshes.append((scope_key, reason)) or True
            ),
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(workbench_refreshes, [])
        self.assertEqual(
            runtime.cost_refreshes,
            [("active:2026-05", "api_page_source_versions_stale")],
        )

    def test_parent_access_refreshes_only_canonically_stale_workbench_months(self) -> None:
        class Runtime(CostStatisticsRuntimeStub):
            def __init__(self) -> None:
                self.cost_refreshes: list[tuple[str, str]] = []

            def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
                self.cost_refreshes.append((scope_key, reason))
                return True

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                raise AssertionError(f"stale Workbench must stop parent Cost gate I/O: {scope_key}")

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale Workbench must stop parent Cost payload I/O")

        expected_by_scope = {
            "2026-03": {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v2"},
            "2026-04": {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v2"},
        }
        active_by_scope = {
            "2026-03": {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v1"},
            "2026-04": {"builder": "workbench-month-v6", "workbench_pair_relations_updated_at": "v1"},
        }
        runtime = Runtime()
        workbench_refreshes: list[tuple[str, str]] = []
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=lambda: (
                expected_by_scope,
                active_by_scope,
            ),
            workbench_refresh_enqueuer=lambda scope_key, *, reason: (
                workbench_refreshes.append((scope_key, reason)) or True
            ),
        )

        payload, cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="all",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertFalse(cache_hit)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_dependency"], "workbench")
        self.assertEqual(payload["refresh_scope_keys"], ["2026-03", "2026-04"])
        self.assertEqual(
            payload["read_model_stale_reasons"],
            [
                "workbench_dependency_2026-03_workbench_pair_relations_updated_at_mismatch",
                "workbench_dependency_2026-04_workbench_pair_relations_updated_at_mismatch",
            ],
        )
        self.assertEqual(
            workbench_refreshes,
            [
                ("2026-03", "cost_statistics_workbench_dependency_stale"),
                ("2026-04", "cost_statistics_workbench_dependency_stale"),
            ],
        )
        self.assertEqual(runtime.cost_refreshes, [])

    def test_parent_access_refreshes_exact_stale_cost_children_instead_of_parent(self) -> None:
        class Runtime(CostStatisticsRuntimeStub):
            def __init__(self) -> None:
                self.cost_refreshes: list[tuple[str, str]] = []

            def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
                self.cost_refreshes.append((scope_key, reason))
                return True

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return {
                    **cost_statistics_fresh_gate(
                        scope_key=scope_key,
                        source_versions=_cost_statistics_source_versions_fixture(scope_key),
                        refresh_status="stale",
                        stale_reasons=["cost_statistics_parent_child_scope_not_fresh"],
                    ),
                    "child_refresh_scope_keys": ["active:2026-03"],
                }

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("stale Cost child must stop parent payload I/O")

        runtime = Runtime()
        workbench_refreshes: list[tuple[str, str]] = []
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=lambda scope_key, *, reason: (
                workbench_refreshes.append((scope_key, reason)) or True
            ),
        )

        payload, _cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="all",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_scope_keys"], ["active:2026-03"])
        self.assertEqual(workbench_refreshes, [])
        self.assertEqual(
            runtime.cost_refreshes,
            [("active:2026-03", "api_page_stale")],
        )

    def test_page_and_detail_use_exactly_one_cost_gate_and_stop_before_payload_io_when_nonfresh(self) -> None:
        runtime = CostStatisticsRuntimeStub()

        class Repository:
            def __init__(self) -> None:
                self.gate_calls: list[str] = []

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                self.gate_calls.append(scope_key)
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=_cost_statistics_source_versions_fixture(scope_key),
                    refresh_status="refreshing",
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("non-fresh gate must stop page payload I/O")

            def get_cost_statistics_transaction(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("non-fresh gate must stop detail payload I/O")

        repository = Repository()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=repository,
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )
        with self.assertRaises(CostStatisticsReadModelNotFreshError):
            service.get_transaction_detail("txn-1", project_scope="active")

        self.assertEqual(
            repository.gate_calls,
            ["active:2026-05", "active:all"],
        )

    def test_current_settings_change_locks_old_cost_snapshot_without_loading_rows(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        old_settings = _cost_statistics_source_settings_fixture()
        current_settings = {
            **old_settings,
            "bank_transaction_tags": {"version": 8, "active_rules": []},
        }
        actual_source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=actual_source_versions,
                    source_settings=current_settings,
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("settings mismatch must stop payload I/O")

        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        payload, cache_hit, _etag, _not_modified = service.get_explorer_page(
            scope="2026-05",
            view="time",
            project_scope="active",
            filters={},
            cursor=None,
            page_size=50,
        )

        self.assertFalse(cache_hit)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("bank_auto_tag_rules_version_mismatch", payload["read_model_stale_reasons"])

    def test_tag_rules_filter_transaction_detail(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")
        payload = {
            "month": "2026-05",
            "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "130.00"},
            "time_rows": [
                {
                    "transaction_id": "oa-fee",
                    "trade_time": "2026-05-21 09:00:00",
                    "direction": "支出",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "100.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "oa-travel",
                    "trade_time": "2026-05-22 09:00:00",
                    "direction": "支出",
                    "project_name": "项目B",
                    "expense_type": "交通",
                    "expense_content": "打车",
                    "amount": "30.00",
                    "counterparty_name": "司机",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "travel",
                    "bank_tag_label": "交通",
                    "bank_tag_primary_label": "差旅",
                    "bank_tag_sub_label": "交通",
                    "bank_tag_label_path": ["差旅", "交通"],
                },
            ],
            "bank_flow_summary": {"row_count": 4, "transaction_count": 4, "total_amount": "355.00"},
            "bank_flow_time_rows": [
                {
                    "transaction_id": "oa-fee",
                    "trade_time": "2026-05-21 09:00:00",
                    "direction": "支出",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "100.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "flow-fee",
                    "trade_time": "2026-05-23 09:00:00",
                    "direction": "支出",
                    "project_name": "未配对OA",
                    "expense_type": "材料",
                    "expense_content": "耗材",
                    "amount": "50.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
                {
                    "transaction_id": "flow-uncategorized",
                    "trade_time": "2026-05-24 09:00:00",
                    "direction": "支出",
                    "project_name": "未配对OA",
                    "expense_type": "未分类",
                    "expense_content": "其他",
                    "amount": "5.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "",
                    "bank_tag_label": "未标记",
                    "bank_tag_primary_label": "未标记",
                    "bank_tag_sub_label": "未标记",
                    "bank_tag_label_path": ["未标记"],
                },
                {
                    "transaction_id": "income-fee",
                    "trade_time": "2026-05-25 09:00:00",
                    "direction": "收入",
                    "project_name": "未配对OA",
                    "expense_type": "材料",
                    "expense_content": "退款",
                    "amount": "200.00",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "remark": "",
                    "bank_tag_code": "fee",
                    "bank_tag_label": "费用",
                    "bank_tag_primary_label": "费用",
                    "bank_tag_sub_label": "材料",
                    "bank_tag_label_path": ["费用", "材料"],
                },
            ],
            "bank_accounts": [],
            "project_rows": [],
            "expense_type_rows": [],
        }
        tag_selection_mapper = lambda _settings: {
            "version": 2,
            "bank_auto_tag_rules_version": 7,
            "effective_selected_tag_codes": ["fee"],
            "selected_tag_codes": ["fee"],
        }
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=CostStatisticsSqlReadRepositoryStub(payload, source_versions),
            tag_selection_mapper=tag_selection_mapper,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        detail_source_versions = _cost_statistics_source_versions_fixture("active:all")
        detail_service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=CostStatisticsSqlReadRepositoryStub(payload, detail_source_versions),
            tag_selection_mapper=tag_selection_mapper,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )
        income_detail = detail_service.get_transaction_detail("income-fee", project_scope="active")
        self.assertEqual(income_detail["transaction"]["direction"], "收入")
        self.assertEqual(income_detail["transaction"]["amount"], "200.00")
        with self.assertRaises(KeyError):
            detail_service.get_transaction_detail("flow-uncategorized", project_scope="active")

    def test_transaction_detail_uses_freshness_gate_and_indexed_point_lookup_only(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:all")

        class Repository:
            def __init__(self) -> None:
                self.transaction_calls: list[tuple[str, str]] = []

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(scope_key=scope_key, source_versions=source_versions)

            def get_cost_statistics_transaction(
                self,
                *,
                project_scope: str,
                transaction_id: str,
            ) -> dict[str, object]:
                self.transaction_calls.append((project_scope, transaction_id))
                return {
                    "transaction_id": transaction_id,
                    "month": "2026-05-01",
                    "trade_time": "2026-05-21 09:00:00",
                    "direction": "支出",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "88.50",
                    "counterparty_name": "供应商",
                    "payment_account_label": "工行",
                    "bank_tag_code": "fee",
                    "bank_tag_label_path": ["费用", "材料"],
                    "cost_allocations": [
                        {
                            "row_key": "txn-1:oa:oa-a",
                            "project_name": "项目A",
                            "project_id": "P-A",
                            "expense_type": "材料",
                            "expense_content": "钢材",
                            "oa_applicant": "张三",
                            "amount": "60.00",
                        },
                        {
                            "row_key": "txn-1:oa:oa-b",
                            "project_name": "项目B",
                            "project_id": "P-B",
                            "expense_type": "劳务",
                            "expense_content": "安装",
                            "oa_applicant": "李四",
                            "amount": "40.00",
                        },
                    ],
                }

        repository = Repository()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=repository,
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        detail = service.get_transaction_detail("txn-1", project_scope="active")

        self.assertEqual(repository.transaction_calls, [("active", "txn-1")])
        self.assertEqual(detail["month"], "2026-05")
        self.assertEqual(detail["transaction"]["amount"], "100.00")
        self.assertEqual(detail["transaction"]["project_name"], "多项目")
        self.assertEqual(detail["transaction"]["expense_type"], "多费用类型")
        self.assertEqual(len(detail["transaction"]["cost_allocations"]), 2)

    def test_transaction_detail_non_fresh_gate_blocks_point_lookup(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:all")

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    published_source_version=7,
                    refresh_status="refreshing",
                )

            def get_cost_statistics_transaction(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("non-fresh detail must not execute the point lookup")

        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        with self.assertRaises(CostStatisticsReadModelNotFreshError) as error:
            service.get_transaction_detail("txn-1", project_scope="active")

        self.assertEqual(error.exception.payload["read_model_status"], "refreshing")

    def test_export_preview_reads_only_eight_filtered_rows_without_full_view(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def __init__(self) -> None:
                self.export_calls: list[dict[str, object]] = []

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    published_source_version=7,
                )

            def get_cost_statistics_export_page(self, **query: object) -> dict[str, object]:
                self.export_calls.append(dict(query))
                rows = [
                    {
                        "transaction_id": f"txn-{index}",
                        "scope_month": "2026-05-01",
                        "trade_time_text": f"2026-05-{index + 1:02d} 09:00:00",
                        "direction": "支出",
                        "project_name": "项目A",
                        "expense_type": "材料",
                        "expense_content": "钢材",
                        "amount": "10.00",
                        "counterparty_name": "供应商",
                        "payment_account_label": "工行",
                    }
                    for index in range(8)
                ]
                return {
                    "summary": {
                        "source_row_count": 123,
                        "row_count": 123,
                        "transaction_count": 123,
                        "total_amount": "1230.00",
                        "expense_amount": "1230.00",
                        "income_amount": "0.00",
                        "expense_transaction_count": 123,
                        "income_transaction_count": 0,
                    },
                    "rows": rows,
                    "next_offset": 8,
                }

        repository = Repository()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=repository,
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        preview = service.get_export_preview(month="2026-05", view="time", project_scope="active")

        self.assertEqual(preview["summary"]["row_count"], 123)
        self.assertEqual(len(preview["rows"]), 8)
        self.assertEqual(len(repository.export_calls), 1)
        self.assertEqual(repository.export_calls[0]["page_size"], 8)
        self.assertEqual(repository.export_calls[0]["offset"], 0)
        self.assertTrue(repository.export_calls[0]["include_summary"])

    def test_bulk_export_uses_bounded_pages_and_rechecks_same_published_version(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def __init__(self) -> None:
                self.gate_calls = 0
                self.export_calls: list[dict[str, object]] = []

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                self.gate_calls += 1
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    published_source_version=7,
                )

            def get_cost_statistics_export_page(self, **query: object) -> dict[str, object]:
                self.export_calls.append(dict(query))
                offset = int(query["offset"])
                return {
                    "summary": (
                        {
                            "source_row_count": 2,
                            "row_count": 2,
                            "transaction_count": 2,
                            "total_amount": "30.00",
                        }
                        if bool(query["include_summary"])
                        else None
                    ),
                    "rows": [
                        {
                            "transaction_id": f"txn-{offset}",
                            "scope_month": "2026-05-01",
                            "trade_time_text": f"2026-05-{offset + 1:02d} 09:00:00",
                            "direction": "支出",
                            "project_name": "项目A",
                            "expense_type": "材料",
                            "expense_content": "钢材",
                            "amount": "10.00" if offset == 0 else "20.00",
                            "counterparty_name": "供应商",
                            "payment_account_label": "工行",
                        }
                    ],
                    "next_offset": 1 if offset == 0 else None,
                }

        repository = Repository()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=repository,
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        filename, content = service.export_view(month="2026-05", view="time", project_scope="active")

        self.assertEqual(filename, "成本统计_2026-05_按时间统计.xlsx")
        self.assertTrue(content.startswith(b"PK"))
        self.assertEqual(repository.gate_calls, 2)
        self.assertEqual([call["offset"] for call in repository.export_calls], [0, 1])
        self.assertTrue(all(call["page_size"] == 1000 for call in repository.export_calls))
        self.assertEqual([call["include_summary"] for call in repository.export_calls], [True, False])

    def test_bulk_export_fails_closed_when_published_version_changes_after_rows(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def __init__(self) -> None:
                self.gate_calls = 0

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                self.gate_calls += 1
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    published_source_version=self.gate_calls,
                )

            def get_cost_statistics_export_page(self, **_query: object) -> dict[str, object]:
                return {
                    "summary": {"source_row_count": 1, "row_count": 1, "total_amount": "10.00"},
                    "rows": [
                        {
                            "transaction_id": "txn-1",
                            "scope_month": "2026-05-01",
                            "trade_time_text": "2026-05-01 09:00:00",
                            "direction": "支出",
                            "project_name": "项目A",
                            "expense_type": "材料",
                            "expense_content": "钢材",
                            "amount": "10.00",
                        }
                    ],
                    "next_offset": None,
                }

        repository = Repository()
        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=repository,
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )

        with self.assertRaises(CostStatisticsReadModelNotFreshError) as error:
            service.export_view(month="2026-05", view="time", project_scope="active")

        self.assertEqual(repository.gate_calls, 2)
        self.assertEqual(error.exception.payload["read_model_stale_reasons"], ["export_snapshot_changed"])

    def test_bulk_export_rejects_row_limit_before_workbook_creation(self) -> None:
        runtime = CostStatisticsRuntimeStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")

        class Repository:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(scope_key=scope_key, source_versions=source_versions)

            def get_cost_statistics_export_page(self, **_query: object) -> dict[str, object]:
                return {
                    "summary": {"source_row_count": 20001, "row_count": 20001, "total_amount": "0.00"},
                    "rows": [],
                    "next_offset": None,
                }

        service = CostStatisticsQueryService(
            runtime_service=runtime,
            sql_read_repository=Repository(),
            tag_selection_mapper=AppSettingsService.cost_statistics_tag_selection_payload_from_settings,
            workbench_dependency_versions_provider=_fresh_workbench_dependency_versions,
            workbench_dependency_versions_by_scope_provider=(
                _fresh_workbench_dependency_versions_by_scope
            ),
            workbench_refresh_enqueuer=_enqueue_workbench_dependency_refresh,
        )
        service._table_workbook = lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("workbook created"))  # type: ignore[method-assign]

        with self.assertRaises(CostStatisticsExportLimitError):
            service.export_view(month="2026-05", view="time", project_scope="active")


class CostStatisticsReadConnection:
    def __init__(
        self,
        *,
        read_model_row: dict | None = None,
        cost_rows: list[dict] | None = None,
        bank_flow_rows: list[dict] | None = None,
        dirty: bool = False,
        dirty_status: str | None = None,
        dirty_source_version: int | None = None,
    ) -> None:
        self.read_model_row = read_model_row
        self.cost_rows = list(cost_rows or [])
        self.bank_flow_rows = list(bank_flow_rows or [])
        self.dirty_status = dirty_status or ("pending" if dirty else None)
        self.dirty_source_version = dirty_source_version
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.fetch_all_calls: list[tuple[str, tuple]] = []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "with candidate as" in normalized and "read_model.cost_statistics_bank_flow_rows" in normalized:
            project_scope, transaction_id = params[:2]
            for row in [*self.cost_rows, *self.bank_flow_rows]:
                if row.get("project_scope") == project_scope and row.get("transaction_id") == transaction_id:
                    result = dict(row)
                    result["cost_allocations"] = [
                        {
                            "row_key": item.get("row_key"),
                            "project_name": item.get("project_name") or (item.get("payload") or {}).get("project_name"),
                            "project_id": item.get("project_id") or "",
                            "expense_type": item.get("expense_type") or (item.get("payload") or {}).get("expense_type"),
                            "expense_content": item.get("expense_content") or "",
                            "oa_applicant": item.get("oa_applicant") or "—",
                            "amount": item.get("amount"),
                        }
                        for item in self.cost_rows
                        if item.get("project_scope") == project_scope
                        and item.get("transaction_id") == transaction_id
                    ]
                    return result
            return None
        if "left join lateral" in normalized and "read_model.cost_statistics_read_models" in normalized:
            if not isinstance(self.read_model_row, dict):
                return None
            row = dict(self.read_model_row)
            row["dirty_status"] = self.dirty_status
            row["dirty_source_version"] = self.dirty_source_version
            if self.dirty_status is not None and self.dirty_source_version is None:
                row["dirty_source_version"] = int(row.get("published_source_version") or 0) + 1
            row.setdefault("source_settings", _cost_statistics_source_settings_fixture())
            row.setdefault("workbench_source_versions", {"source_version": 1})
            row.setdefault("workbench_dirty_source_version", 1)
            row.setdefault("workbench_dirty_status", "done")
            row.setdefault("bank_detail_schema_version", BANK_DETAIL_READ_MODEL_SCHEMA_VERSION)
            row.setdefault("statistics_scope_key", "active:all")
            row.setdefault("statistics", cost_statistics_fresh_gate(
                scope_key="active:all",
                source_versions=_cost_statistics_source_versions_fixture("active:all"),
            )["statistics"])
            row.setdefault("statistics_schema_version", COST_STATISTICS_READ_MODEL_SCHEMA_VERSION)
            row.setdefault("statistics_published_source_version", row.get("published_source_version"))
            row.setdefault("statistics_dirty_source_version", row.get("published_source_version"))
            row.setdefault("statistics_dirty_status", "done")
            row.setdefault("statistics_child_has_failed", False)
            row.setdefault("statistics_child_has_active", False)
            row.setdefault("workbench_refresh_scope_keys", [])
            row.setdefault("child_refresh_scope_keys", [])
            row.setdefault("parent_child_has_failed", False)
            row.setdefault("parent_child_has_active", False)
            row.setdefault("parent_source_shards_match", True)
            row.setdefault("bank_flow_bank_detail_refresh_scope_keys", [])
            row.setdefault("bank_flow_child_refresh_scope_keys", [])
            row.setdefault("bank_flow_has_failed", False)
            row.setdefault("bank_flow_has_active", False)
            row.setdefault("bank_detail_status", "fresh")
            row.setdefault("bank_detail_source_version", 1)
            row.setdefault("bank_detail_source_versions", {"source_version": 1})
            row.setdefault("bank_detail_dirty_source_version", 1)
            row.setdefault("bank_detail_dirty_status", "done")
            return row
        if "from read_model.cost_statistics_read_models" in normalized:
            return self.read_model_row
        return None

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.cost_statistics_bank_flow_rows" in normalized:
            return self.bank_flow_rows
        if "from read_model.cost_statistics_rows" in normalized:
            return self.cost_rows
        return []


class CostStatisticsWriteConnection:
    def __init__(
        self,
        *,
        current_source_version: int | None = None,
        acknowledge_result: bool = True,
    ) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []
        self.current_source_version = current_source_version
        self.acknowledge_result = acknowledge_result
        self.transaction_count = 0

    def transaction(self):
        self.transaction_count += 1
        return self

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from job.read_model_dirty_scopes" in normalized and self.current_source_version is not None:
            return {"source_version": self.current_source_version}
        if "update read_model.cost_statistics_read_models" in normalized and self.acknowledge_result:
            return {"scope_key": params[1]}
        return None

    def execute(self, sql: str, params: tuple = ()) -> int:
        normalized = " ".join(sql.lower().split())
        self.executed.append((normalized, params))
        if (
            "insert into read_model.cost_statistics_rows" in normalized
            or "insert into read_model.cost_statistics_bank_flow_rows" in normalized
        ) and params[2] is None:
            raise AssertionError("parent cost statistics scope must not write rows with null scope_month")
        return 1


class CostStatisticsProjectionConnection:
    def __init__(
        self,
        *,
        include_open_candidate: bool = False,
        include_unpaired_relation: bool = False,
    ) -> None:
        self.include_open_candidate = include_open_candidate
        self.include_unpaired_relation = include_unpaired_relation
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "read_model.workbench_groups" in normalized:
            rows = [
                {
                    "group_id": "group-1",
                    "zone": "paired",
                    "payload": {
                        "group_id": "group-1",
                        "group_type": "manual_confirmed",
                        "relation_status": "linked",
                        "workbench_group_rows_materialized": True,
                    },
                    "raw_payload": {},
                    "pane": "oa",
                    "row_id": "oa-1",
                    "row_role": "normal",
                    "row_index": 0,
                    "row_payload": {
                        "id": "oa-1",
                        "type": "oa",
                        "project_name": "项目A",
                        "project_id": "P-A",
                        "expense_type": "材料",
                        "expense_content": "钢材",
                        "applicant": "张三",
                    },
                    "member_payload": {"row_id": "oa-1", "type": "oa"},
                },
                {
                    "group_id": "group-1",
                    "zone": "paired",
                    "payload": {
                        "group_id": "group-1",
                        "group_type": "manual_confirmed",
                        "relation_status": "linked",
                        "workbench_group_rows_materialized": True,
                    },
                    "raw_payload": {},
                    "pane": "bank",
                    "row_id": "bank-1",
                    "row_role": "normal",
                    "row_index": 1,
                    "row_payload": {
                        "id": "bank-1",
                        "type": "bank",
                        "trade_time": "2026-05-02 10:00:00",
                        "counterparty_name": "供应商A",
                        "payment_account_label": "建行",
                        "direction": "支出",
                        "remark": "采购",
                        "amount": "10.00",
                    },
                    "member_payload": {"row_id": "bank-1", "type": "bank"},
                }
            ]
            if self.include_unpaired_relation or (
                self.include_open_candidate and "g.group_type = 'relation'" not in normalized
            ):
                extra_group_type = "relation" if self.include_unpaired_relation else "candidate"
                rows.extend(
                    [
                        {
                            "group_id": "group-candidate",
                            "zone": "unpaired",
                            "payload": {
                                "group_id": "group-candidate",
                                "group_type": extra_group_type,
                                "relation_status": "candidate",
                                "reason": "attached_unique_candidate",
                                "workbench_group_rows_materialized": True,
                            },
                            "raw_payload": {},
                            "pane": "oa",
                            "row_id": "oa-candidate",
                            "row_role": "normal",
                            "row_index": 0,
                            "row_payload": {
                                "id": "oa-candidate",
                                "type": "oa",
                                "project_name": "项目A",
                                "project_id": "P-A",
                                "expense_type": "材料",
                                "expense_content": "候选材料",
                                "applicant": "李四",
                            },
                            "member_payload": {"row_id": "oa-candidate", "type": "oa"},
                        },
                        {
                            "group_id": "group-candidate",
                            "zone": "unpaired",
                            "payload": {
                                "group_id": "group-candidate",
                                "group_type": extra_group_type,
                                "relation_status": "candidate",
                                "reason": "attached_unique_candidate",
                                "workbench_group_rows_materialized": True,
                            },
                            "raw_payload": {},
                            "pane": "bank",
                            "row_id": "bank-candidate",
                            "row_role": "normal",
                            "row_index": 1,
                            "row_payload": {
                                "id": "bank-candidate",
                                "type": "bank",
                                "trade_time": "2026-05-03 10:00:00",
                                "counterparty_name": "候选供应商",
                                "payment_account_label": "建行",
                                "direction": "支出",
                                "remark": "候选采购",
                                "amount": "999.00",
                                "available_actions": ["detail", "view_relation", "cancel_link"],
                            },
                            "member_payload": {"row_id": "bank-candidate", "type": "bank"},
                        },
                    ]
                )
            return rows
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_account_mappings": [
                        {"bank_name": "工商银行", "last4": "0001"},
                        {"bank_name": "民生银行", "last4": "9486"},
                    ],
                    "projects": [{"name": "项目A", "active": True}],
                    "bank_transaction_tags": {"version": 7},
                }
            }
        return None


class CostStatisticsBankTagFacade:
    def __init__(self, *, status: str = "fresh") -> None:
        self.status = status
        self.source_version_calls: list[tuple[list[str], dict[str, object]]] = []
        self.category_calls: list[tuple[list[str], dict[str, object]]] = []
        self.month_calls: list[tuple[str, dict[str, object]]] = []
        self.snapshot_calls: list[tuple[str, dict[str, object]]] = []

    def source_versions_for_scope_keys(self, scope_keys: list[str], **kwargs: object) -> dict[str, object]:
        self.source_version_calls.append((list(scope_keys), dict(kwargs)))
        return {
            "status": self.status,
            "source_versions": {"bank_detail_scope_version": "bank-detail-v2"},
            "scope_keys": list(scope_keys),
        }

    def get_by_transaction_ids(self, transaction_ids: list[str], **kwargs: object) -> dict[str, object]:
        self.category_calls.append((list(transaction_ids), dict(kwargs)))
        return {
            "status": self.status,
            "rows": [
                {
                    "transaction_id": "bank-1",
                    "effective_category_code": "project_material",
                    "effective_category_label": "设备材料",
                    "effective_category_primary_label": "项目开销",
                    "effective_category_sub_label": "设备材料",
                    "effective_category_label_path": ["项目开销", "设备材料"],
                }
            ],
        }

    def list_by_month(self, month: str, **kwargs: object) -> dict[str, object]:
        self.month_calls.append((month, dict(kwargs)))
        return self._snapshot_payload()

    def snapshot_for_month(self, month: str, **kwargs: object) -> dict[str, object]:
        self.snapshot_calls.append((month, dict(kwargs)))
        return self._snapshot_payload()

    def _snapshot_payload(self) -> dict[str, object]:
        month_rows = [
            {
                "transaction_id": "bank-expense",
                "trade_time": "2026-05-04 10:00:00",
                "direction": "expense",
                "amount": "20.00",
                "counterparty_name": "供应商",
                "bank_name": "工商银行",
                "account_last4": "0001",
                "summary": "采购",
                "effective_category_code": "project_material",
                "effective_category_label": "设备材料",
            },
            {
                "transaction_id": "bank-income",
                "trade_time": "2026-05-05 10:00:00",
                "direction": "income",
                "amount": "30.00",
                "counterparty_name": "客户",
                "bank_name": "工商银行",
                "account_last4": "0001",
                "summary": "回款",
                "effective_category_code": "project_collection",
                "effective_category_label": "项目回款",
            },
        ]
        return {
            "status": self.status,
            "source_versions": {
                "2026-04": {"bank_detail_scope_version": "bank-detail-v1"},
                "2026-05": {"bank_detail_scope_version": "bank-detail-v2"},
            },
            "read_model_scope_signatures": {
                "2026-04": {"source_versions": {"bank_detail_scope_version": "bank-detail-v1"}},
                "2026-05": {"source_versions": {"bank_detail_scope_version": "bank-detail-v2"}},
            },
            "rows": [
                {
                    "transaction_id": "bank-1",
                    "effective_category_code": "project_material",
                    "effective_category_label": "设备材料",
                    "effective_category_primary_label": "项目开销",
                    "effective_category_sub_label": "设备材料",
                    "effective_category_label_path": ["项目开销", "设备材料"],
                },
                *month_rows,
            ],
            "month_rows": month_rows,
        }


class CostStatisticsParentAggregationConnection:
    def __init__(self, *, missing_or_stale_shards: list[str] | None = None) -> None:
        self.missing_or_stale_shards = list(missing_or_stale_shards or [])
        self.fetch_all_calls: list[tuple[str, tuple]] = []
        self.fetch_one_calls: list[tuple[str, tuple]] = []

    def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
        normalized = " ".join(sql.lower().split())
        self.fetch_all_calls.append((normalized, params))
        if "from read_model.workbench_groups" in normalized:
            raise RuntimeError("parent rebuild must not read workbench all payload")
        if "from read_model.cost_statistics_read_models" in normalized:
            if "scope_key ~" in normalized:
                return []
            project_scope = str(params[0])
            return [
                {
                    "scope_key": f"{project_scope}:2026-04",
                    "source_versions": {"scope": f"{project_scope}:2026-04"},
                },
                {
                    "scope_key": f"{project_scope}:2026-05",
                    "source_versions": {"scope": f"{project_scope}:2026-05"},
                },
            ]
        if "from read_model.cost_statistics_bank_flow_rows" in normalized:
            return [
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "bank-flow-1:0",
                    "transaction_id": "bank-flow-1",
                    "trade_time_text": "2026-05-08 10:00:00",
                    "trade_date": "2026-05-08",
                    "counterparty_name": "供应商C",
                    "payment_account_label": "工行",
                    "direction": "支出",
                    "remark": "耗材",
                    "project_name": "未配对OA",
                    "expense_type": "设备材料",
                    "expense_content": "耗材",
                    "amount": "20.00",
                    "bank_tag_code": "project_material",
                    "bank_tag_label": "设备材料",
                    "bank_tag_primary_label": "项目开销",
                    "bank_tag_sub_label": "设备材料",
                    "bank_tag_label_path": ["项目开销", "设备材料"],
                    "source_versions": {"scope": "active:2026-05"},
                    "payload": {"transaction_id": "bank-flow-1"},
                    "raw_payload": {},
                }
            ]
        if "from read_model.cost_statistics_rows" in normalized:
            return [
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:0",
                    "transaction_id": "txn-1",
                    "group_id": "group-1",
                    "trade_time_text": "2026-05-02 10:00:00",
                    "trade_date": "2026-05-02",
                    "counterparty_name": "供应商A",
                    "payment_account_label": "建行",
                    "direction": "支出",
                    "remark": "采购",
                    "project_id": "P-A",
                    "project_name": "项目A",
                    "expense_type": "材料",
                    "expense_content": "钢材",
                    "amount": "10.00",
                    "oa_applicant": "张三",
                    "source_versions": {"scope": "active:2026-05"},
                    "generated_at": "2026-06-04T10:00:00+00:00",
                    "cache_status": "fresh",
                    "payload": {
                        "transaction_id": "txn-1",
                        "group_id": "group-1",
                        "trade_time": "2026-05-02 10:00:00",
                        "direction": "支出",
                        "project_name": "项目A",
                        "project_id": "P-A",
                        "expense_type": "材料",
                        "expense_content": "钢材",
                        "amount": "10.00",
                        "counterparty_name": "供应商A",
                        "payment_account_label": "建行",
                        "remark": "采购",
                        "oa_applicant": "张三",
                        "bank_tag_code": "project_material",
                        "bank_tag_label": "设备材料",
                        "bank_tag_primary_label": "项目开销",
                        "bank_tag_sub_label": "设备材料",
                        "bank_tag_label_path": ["项目开销", "设备材料"],
                    },
                    "raw_payload": {},
                },
                {
                    "scope_key": "active:2026-04",
                    "project_scope": "active",
                    "scope_month": "2026-04-01",
                    "row_key": "txn-2:0",
                    "transaction_id": "txn-2",
                    "group_id": "group-2",
                    "trade_time_text": "2026-04-11 09:00:00",
                    "trade_date": "2026-04-11",
                    "counterparty_name": "供应商B",
                    "payment_account_label": "招行",
                    "direction": "支出",
                    "remark": "服务",
                    "project_id": "P-B",
                    "project_name": "项目B",
                    "expense_type": "服务",
                    "expense_content": "咨询",
                    "amount": "5.50",
                    "oa_applicant": "李四",
                    "source_versions": {"scope": "active:2026-04"},
                    "generated_at": "2026-06-04T10:01:00+00:00",
                    "cache_status": "fresh",
                    "payload": {
                        "transaction_id": "txn-2",
                        "group_id": "group-2",
                        "trade_time": "2026-04-11 09:00:00",
                        "direction": "支出",
                        "project_name": "项目B",
                        "project_id": "P-B",
                        "expense_type": "服务",
                        "expense_content": "咨询",
                        "amount": "5.50",
                        "counterparty_name": "供应商B",
                        "payment_account_label": "招行",
                        "remark": "服务",
                        "oa_applicant": "李四",
                    },
                    "raw_payload": {},
                },
            ]
        return []

    def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
        normalized = " ".join(sql.lower().split())
        self.fetch_one_calls.append((normalized, params))
        if "from read_model.cost_statistics_rows" in normalized:
            return {
                "row_count": 2,
                "transaction_count": 2,
                "group_count": 2,
                "project_count": 2,
                "expense_type_count": 2,
                "total_amount": "15.50",
            }
        if "from read_model.cost_statistics_bank_flow_rows" in normalized:
            return {
                "row_count": 1,
                "transaction_count": 1,
                "total_amount": "20.00",
                "expense_amount": "20.00",
                "income_amount": "0",
                "expense_transaction_count": 1,
                "income_transaction_count": 0,
                "tagged_transaction_count": 1,
                "bank_tag_count": 1,
            }
        if "from app.app_settings" in normalized:
            return {
                "settings_payload": {
                    "bank_account_mappings": [{"bank_name": "工商银行", "last4": "0001"}],
                    "bank_transaction_tags": {"version": 7},
                }
            }
        return None


class CostStatisticsSaveRecorder:
    def __init__(self, *, publish_result: bool = True, acknowledge_result: bool = True) -> None:
        self.saved: list[tuple[dict, set[str] | None]] = []
        self.publish_calls: list[tuple[str, str, int, set[str] | None]] = []
        self.acknowledge_calls: list[tuple[str, str, int, dict[str, object]]] = []
        self.aggregate_calls: list[dict[str, object]] = []
        self.publish_result = publish_result
        self.acknowledge_result = acknowledge_result
        self.workbench_source_versions: dict[str, object] = {}

    def get_cost_statistics_scope_metadata(self, *, scope_key: str) -> dict[str, object]:
        return {
            "scope_key": scope_key,
            "entry_count": 0,
            "source_versions": {"bank_detail_source_versions": {"source_version": 3}},
            "statistics_ready": True,
        }

    def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, object]:
        del scope_key
        return dict(self.workbench_source_versions)

    def cost_statistics_aggregate_payload(
        self,
        *,
        project_scope: str,
        scope_keys: list[str],
        bank_accounts: list[dict[str, object]],
    ) -> dict[str, object]:
        self.aggregate_calls.append(
            {
                "project_scope": project_scope,
                "scope_keys": list(scope_keys),
                "bank_accounts": list(bank_accounts),
            }
        )
        return {
            "month": "all",
            "project_scope": project_scope,
            "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "15.50"},
            "bank_flow_summary": {
                "row_count": 1,
                "transaction_count": 1,
                "total_amount": "20.00",
                "expense_amount": "20.00",
                "income_amount": "0.00",
                "expense_transaction_count": 1,
                "income_transaction_count": 0,
            },
            "bank_accounts": list(bank_accounts),
            "project_rows": [
                {
                    "project_name": "项目A",
                    "total_amount": "10.00",
                    "transaction_count": 1,
                    "expense_type_count": 1,
                },
                {
                    "project_name": "项目B",
                    "total_amount": "5.50",
                    "transaction_count": 1,
                    "expense_type_count": 1,
                },
            ],
            "expense_type_rows": [
                {
                    "expense_type": "材料",
                    "total_amount": "10.00",
                    "transaction_count": 1,
                    "project_count": 1,
                },
                {
                    "expense_type": "服务",
                    "total_amount": "5.50",
                    "transaction_count": 1,
                    "project_count": 1,
                },
            ],
            "source_scope_keys": list(scope_keys),
        }

    def publish_cost_statistics_read_models(
        self,
        snapshot: dict,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        changed_scope_keys: set[str] | None = None,
    ) -> bool:
        self.publish_calls.append((tenant_id, scope_key, source_version, changed_scope_keys))
        if self.publish_result:
            self.saved.append((snapshot, changed_scope_keys))
        return self.publish_result

    def acknowledge_unchanged_cost_statistics_scope(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        source_versions: dict[str, object],
    ) -> bool:
        self.acknowledge_calls.append((tenant_id, scope_key, source_version, dict(source_versions)))
        return self.acknowledge_result


class UnchangedCostStatisticsSaveRecorder(CostStatisticsSaveRecorder):
    def __init__(self, *, refresh_status: str = "fresh", acknowledge_result: bool = True) -> None:
        super().__init__(acknowledge_result=acknowledge_result)
        self.refresh_status = refresh_status
        self.source_versions: dict[str, object] = {}
        self.metadata_scopes: list[str] = []
        self.workbench_source_versions = {"workbench_generation": "stable-v1", "source_version": 42}

    def get_cost_statistics_scope_metadata(self, *, scope_key: str) -> dict[str, object]:
        self.metadata_scopes.append(scope_key)
        return {
            "scope_key": scope_key,
            "entry_count": 1,
            "source_versions": dict(self.source_versions),
            "statistics_ready": True,
        }


class CostStatisticsReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Repository:
            def get_cost_statistics_scope_metadata(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "entry_count": 1, "source_versions": {"proof": "v1"}}

            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "published_source_version": 7}

            def get_cost_statistics_page(self, **query: object) -> dict[str, object]:
                return {"view": query["view"], "rows": []}

            def get_cost_statistics_export_page(self, **query: object) -> dict[str, object]:
                return {"row_shape": query["row_shape"], "rows": []}

            def get_cost_statistics_transaction(
                self,
                *,
                project_scope: str,
                transaction_id: str,
            ) -> dict[str, object]:
                return {"project_scope": project_scope, "transaction_id": transaction_id}

            def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, object]:
                return {"scope_key": scope_key, "source_version": 42}

            def active_workbench_source_versions_by_scope(
                self,
                *,
                scope_keys: list[str],
            ) -> dict[str, dict[str, object]]:
                return {
                    scope_key: {"scope_key": scope_key, "source_version": index}
                    for index, scope_key in enumerate(scope_keys, start=1)
                }

            def cost_statistics_aggregate_payload(self, **kwargs: object) -> dict[str, object]:
                return {"project_scope": kwargs["project_scope"], "summary": {"row_count": 1}}

            def publish_cost_statistics_read_models(
                self,
                snapshot: dict[str, object],
                *,
                tenant_id: str,
                scope_key: str,
                source_version: int,
                changed_scope_keys: set[str] | None = None,
            ) -> bool:
                self.published = (snapshot, tenant_id, scope_key, source_version, changed_scope_keys)
                return True

            def acknowledge_unchanged_cost_statistics_scope(
                self,
                *,
                tenant_id: str,
                scope_key: str,
                source_version: int,
                source_versions: dict[str, object],
            ) -> bool:
                self.acknowledged = (tenant_id, scope_key, source_version, source_versions)
                return True

            def get_tax_offset_view(self, *, scope_key: str) -> dict[str, object]:
                raise AssertionError("tax offset should not be exposed through cost statistics port")

            def list_turnover_ledger_view(self, **_kwargs) -> dict[str, object]:
                raise AssertionError("turnover should not be exposed through cost statistics port")

            def save_search_index_rows(self, **_kwargs) -> None:
                raise AssertionError("search should not be exposed through cost statistics port")

        port = CostStatisticsReadModelRepositoryPort(Repository())

        self.assertEqual(
            port.get_cost_statistics_scope_metadata(scope_key="active:2026-05"),
            {"scope_key": "active:2026-05", "entry_count": 1, "source_versions": {"proof": "v1"}},
        )
        self.assertEqual(
            port.get_cost_statistics_freshness_gate(scope_key="active:2026-05")["published_source_version"],
            7,
        )
        self.assertEqual(port.get_cost_statistics_page(view="time"), {"view": "time", "rows": []})
        self.assertEqual(
            port.get_cost_statistics_export_page(row_shape="raw_cost"),
            {"row_shape": "raw_cost", "rows": []},
        )
        self.assertEqual(
            port.get_cost_statistics_transaction(project_scope="active", transaction_id="txn-1"),
            {"project_scope": "active", "transaction_id": "txn-1"},
        )
        self.assertEqual(
            port.active_workbench_source_versions(scope_key="2026-05"),
            {"scope_key": "2026-05", "source_version": 42},
        )
        self.assertEqual(
            port.active_workbench_source_versions_by_scope(
                scope_keys=["2026-05", "2026-06"]
            ),
            {
                "2026-05": {"scope_key": "2026-05", "source_version": 1},
                "2026-06": {"scope_key": "2026-06", "source_version": 2},
            },
        )
        self.assertEqual(
            port.cost_statistics_aggregate_payload(
                project_scope="active",
                scope_keys=["active:2026-05"],
                bank_accounts=[],
            ),
            {"project_scope": "active", "summary": {"row_count": 1}},
        )
        self.assertTrue(
            port.acknowledge_unchanged_cost_statistics_scope(
                tenant_id="default",
                scope_key="active:2026-05",
                source_version=7,
                source_versions={"proof": "v1"},
            )
        )
        self.assertTrue(
            port.publish_cost_statistics_read_models(
                {"read_models": {}},
                tenant_id="default",
                scope_key="active:2026-05",
                source_version=7,
                changed_scope_keys={"active:2026-05"},
            )
        )
        self.assertFalse(hasattr(port, "get_tax_offset_view"))
        self.assertFalse(hasattr(port, "list_turnover_ledger_view"))
        self.assertFalse(hasattr(port, "save_search_index_rows"))
        self.assertFalse(hasattr(port, "publish_cost_statistics_relation_delta"))
        self.assertFalse(hasattr(port, "load_" + "cost_statistics_read_models"))
        self.assertFalse(hasattr(port, "save_" + "cost_statistics_read_models"))


class CostStatisticsSqlRuntimeTests(unittest.TestCase):
    def test_page_statistics_reject_invalid_partition_totals(self) -> None:
        statistics = {
            "transaction_count": 4,
            "expense_transaction_count": 3,
            "income_transaction_count": 1,
            "cost_group_count": 2,
            "tagged_transaction_count": 3,
            "untagged_transaction_count": 1,
            "project_count": 2,
            "expense_type_count": 2,
            "bank_tag_count": 2,
            "cost_transaction_count": 2,
        }

        self.assertEqual(_cost_statistics_page_statistics(statistics), statistics)
        self.assertIsNone(
            _cost_statistics_page_statistics({**statistics, "untagged_transaction_count": 2})
        )

    def test_parent_aggregate_statistics_come_from_unfiltered_structured_rows(self) -> None:
        connection = CostStatisticsParentAggregationConnection()
        repository = PostgresReadModelRepository(connection)

        payload = repository.cost_statistics_aggregate_payload(
            project_scope="active",
            scope_keys=["active:2026-04", "active:2026-05"],
            bank_accounts=[],
        )

        self.assertEqual(
            payload["statistics"],
            {
                "transaction_count": 1,
                "expense_transaction_count": 1,
                "income_transaction_count": 0,
                "cost_group_count": 2,
                "tagged_transaction_count": 1,
                "untagged_transaction_count": 0,
                "project_count": 2,
                "expense_type_count": 2,
                "bank_tag_count": 1,
                "cost_transaction_count": 2,
            },
        )
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls)
        self.assertIn("count(distinct transaction_id)", queried_sql)
        self.assertNotIn("limit", queried_sql)

    def test_cost_statistics_page_etag_short_circuits_sql_and_cursor_rejects_new_generation(self) -> None:
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")
        gate_version = {"value": 7}
        page_calls: list[dict[str, object]] = []

        class SqlCostStats:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    published_source_version=gate_version["value"],
                )

            def get_cost_statistics_page(self, **query: object) -> dict[str, object]:
                page_calls.append(dict(query))
                return {
                    "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "30.00"},
                    "cost_transaction_count": 1,
                    "available_years": ["2026"],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [{"transaction_id": "txn-2", "trade_time": "2026-05-02 10:00:00"}],
                    "row_count": 2,
                    "next_cursor_values": ("2026-05-02", "2026-05-02 10:00:00", "txn-2", "txn-2:0"),
                }

        app._cost_statistics_sql_read_repository = SqlCostStats()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": RedisRecorder()},
        )()
        query = {
            "scope": ["2026-05"],
            "view": ["time"],
            "page_size": ["1"],
            "project_scope": ["active"],
        }

        first = app._cost_statistics_routes().route("GET", "/api/cost-statistics/explorer", query)
        first_payload = json.loads(first.body)
        etag = first.headers["ETag"]
        self.assertEqual(first.status_code, int(HTTPStatus.OK))
        self.assertTrue(first_payload["next_cursor"])
        self.assertEqual(first_payload["statistics"]["cost_transaction_count"], 1)
        self.assertEqual(len(page_calls), 1)

        not_modified = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            query,
            headers={"If-None-Match": etag},
        )
        self.assertEqual(not_modified.status_code, int(HTTPStatus.NOT_MODIFIED))
        self.assertEqual(len(page_calls), 1)

        gate_version["value"] = 8
        stale_cursor = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {**query, "cursor": [first_payload["next_cursor"]]},
        )
        self.assertEqual(stale_cursor.status_code, int(HTTPStatus.BAD_REQUEST))
        self.assertEqual(json.loads(stale_cursor.body)["error"], "invalid_cost_statistics_cursor")
        self.assertEqual(len(page_calls), 1)

    def test_cost_statistics_page_repository_uses_one_set_based_statement(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
                self.fetch_one_calls.append((" ".join(sql.split()), params))
                return {
                    "payload": {
                        "summary": {"row_count": 2, "transaction_count": 2, "total_amount": "30.00"},
                        "available_years": ["2026"],
                        "primary_facets": [{"project_name": "项目A"}],
                        "secondary_facets": [{"expense_type": "材料"}],
                        "row_count": 2,
                        "rows": [
                            {
                                "transaction_id": "txn-2",
                                "_cursor_date": "2026-05-02",
                                "_cursor_time": "2026-05-02 10:00:00",
                                "_cursor_transaction_id": "txn-2",
                                "_cursor_row_key": "txn-2:0",
                            },
                            {
                                "transaction_id": "txn-1",
                                "_cursor_date": "2026-05-01",
                                "_cursor_time": "2026-05-01 10:00:00",
                                "_cursor_transaction_id": "txn-1",
                                "_cursor_row_key": "txn-1:0",
                            },
                        ],
                    }
                }

        connection = Connection()
        repository = PostgresReadModelRepository(connection)
        payload = repository.get_cost_statistics_page(
            project_scope="active",
            scope_kind="month",
            scope_value="2026-05",
            view="project",
            filters={"project_name": "项目A", "expense_type": "材料"},
            selected_tag_codes=None,
            cursor_values=None,
            page_size=1,
        )

        self.assertEqual(len(connection.fetch_one_calls), 1)
        sql, params = connection.fetch_one_calls[0]
        self.assertEqual(sql.count("%s"), len(params))
        self.assertIn("from read_model.cost_statistics_rows", sql.lower())
        self.assertIn("with available_years as materialized", sql.lower())
        self.assertIn("selected_cost_transactions as materialized", sql.lower())
        self.assertIn("count(distinct transaction_id)", sql.lower())
        self.assertIn("raw_base as materialized", sql.lower())
        self.assertIn("then '0.0%%'", sql)
        self.assertIn("::text || '%%'", sql)
        self.assertEqual(params[:2], ("active", "active"))
        self.assertEqual([row["transaction_id"] for row in payload["rows"]], ["txn-2"])
        self.assertEqual(payload["next_cursor_values"], ("2026-05-02", "2026-05-02 10:00:00", "txn-2", "txn-2:0"))
        self.assertNotIn("_cursor_date", payload["rows"][0])

    def test_shared_postgres_repository_exposes_active_workbench_versions_to_cost_port(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.fetch_one_calls: list[tuple[str, tuple]] = []

            def fetch_one(self, sql: str, params: tuple = ()) -> dict[str, object] | None:
                self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
                return {"source_versions": {"builder": "workbench-v5", "source_version": 2512}}

        connection = Connection()
        repository = PostgresReadModelRepository(connection)
        port = CostStatisticsReadModelRepositoryPort(repository)

        self.assertEqual(
            port.active_workbench_source_versions(scope_key="2026-05"),
            {"builder": "workbench-v5", "source_version": 2512},
        )
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("from read_model.workbench_generations", sql)
        self.assertIn("status = 'active'", sql)
        self.assertEqual(params, ("2026-05",))

    def test_repository_parses_grouped_display_amount_into_structured_cost_row(self) -> None:
        connection = CostStatisticsWriteConnection(current_source_version=7)
        repository = PostgresReadModelRepository(connection)

        published = repository.publish_cost_statistics_read_models(
            {
                "read_models": {
                    "all:2026-05": {
                        "scope_key": "all:2026-05",
                        "month": "2026-05",
                        "project_scope": "all",
                        "generated_at": "2026-07-10T10:00:00+00:00",
                        "entry_count": 1,
                        "source_versions": {"proof": "v1"},
                        "payload": {
                            "month": "2026-05",
                            "project_scope": "all",
                            "summary": {"transaction_count": 1, "total_amount": "1,872.93"},
                            "time_rows": [
                                {
                                    "transaction_id": "txn-1",
                                    "trade_time": "2026-05-02 10:00:00",
                                    "project_name": "项目A",
                                    "expense_type": "材料",
                                    "amount": "1,872.93",
                                }
                            ],
                            "bank_flow_time_rows": [
                                {
                                    "transaction_id": "bank-1",
                                    "trade_time": "2026-05-03 10:00:00",
                                    "direction": "支出",
                                    "project_name": "未配对OA",
                                    "expense_type": "材料",
                                    "amount": "25.50",
                                    "bank_tag_code": "project_material",
                                    "bank_tag_label_path": ["项目开销", "设备材料"],
                                }
                            ],
                        },
                    }
                }
            },
            tenant_id="default",
            scope_key="all:2026-05",
            source_version=7,
            changed_scope_keys={"all:2026-05"},
        )

        self.assertTrue(published)

        insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.cost_statistics_rows" in sql
        )
        self.assertEqual(insert[16], "1872.93")
        bank_flow_insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.cost_statistics_bank_flow_rows" in sql
        )
        self.assertEqual(bank_flow_insert[16], "25.50")
        parent_insert = next(
            params
            for sql, params in connection.executed
            if "insert into read_model.cost_statistics_read_models" in sql
        )
        stored_snapshot = parent_insert[7].obj
        self.assertNotIn("time_rows", stored_snapshot["payload"])
        self.assertNotIn("bank_flow_time_rows", stored_snapshot["payload"])
        raw_snapshot = parent_insert[8].obj["normalized_payload"]
        self.assertNotIn("time_rows", raw_snapshot["payload"])
        self.assertNotIn("bank_flow_time_rows", raw_snapshot["payload"])

    def test_repository_saves_parent_scope_snapshot_without_writing_month_rows(self) -> None:
        connection = CostStatisticsWriteConnection(current_source_version=7)
        repository = PostgresReadModelRepository(connection)

        published = repository.publish_cost_statistics_read_models(
            {
                "read_models": {
                    "active:all": {
                        "scope_key": "active:all",
                        "month": "all",
                        "project_scope": "active",
                        "generated_at": "2026-06-06T10:00:00+00:00",
                        "entry_count": 1,
                        "source_versions": {"cost_statistics_parent_source": "materialized_shards"},
                        "payload": {
                            "month": "all",
                            "project_scope": "active",
                            "summary": {"row_count": 1, "total_amount": "10.00"},
                            "time_rows": [
                                {
                                    "transaction_id": "txn-parent-1",
                                    "trade_time": "2026-05-02 10:00:00",
                                    "trade_date": "2026-05-02",
                                    "project_name": "项目A",
                                    "expense_type": "材料",
                                    "amount": "10.00",
                                }
                            ],
                            "project_rows": [],
                            "expense_type_rows": [],
                        },
                    }
                }
            },
            tenant_id="default",
            scope_key="active:all",
            source_version=7,
            changed_scope_keys={"active:all"},
        )

        self.assertTrue(published)
        self.assertTrue(any("insert into read_model.cost_statistics_read_models" in sql for sql, _params in connection.executed))
        self.assertTrue(any("delete from read_model.cost_statistics_rows where scope_key" in sql for sql, _params in connection.executed))
        self.assertFalse(any("insert into read_model.cost_statistics_rows" in sql for sql, _params in connection.executed))

    def test_repository_conditionally_publishes_cost_scope_and_obsolete_deletes_in_one_transaction(self) -> None:
        connection = CostStatisticsWriteConnection(current_source_version=7)
        repository = PostgresReadModelRepository(connection)
        snapshot = {
            "read_models": {
                "active:all": {
                    "scope_key": "active:all",
                    "month": "all",
                    "project_scope": "active",
                    "source_versions": {"proof": "v1"},
                    "payload": {"month": "all", "project_scope": "active", "time_rows": []},
                }
            }
        }

        published = repository.publish_cost_statistics_read_models(
            snapshot,
            tenant_id="default",
            scope_key="active:all",
            source_version=7,
            changed_scope_keys={"active:all", "active:2023-05"},
        )

        self.assertTrue(published)
        self.assertEqual(connection.transaction_count, 1)
        cas_sql, cas_params = connection.fetch_one_calls[0]
        self.assertIn("status in ('pending', 'processing')", cas_sql)
        self.assertNotIn("order by source_version", cas_sql)
        self.assertIn("for update", cas_sql)
        self.assertEqual(cas_params, ("default", "active:all"))
        self.assertTrue(any(params == ("active:2023-05",) for _sql, params in connection.executed))
        self.assertTrue(
            any(
                "delete from read_model.cost_statistics_bank_flow_rows where scope_key" in sql
                and params == ("active:2023-05",)
                for sql, params in connection.executed
            )
        )
        self.assertTrue(any("insert into read_model.cost_statistics_read_models" in sql for sql, _params in connection.executed))
        self.assertTrue(
            any(
                "set published_source_version = %s" in sql and params == (7, "active:all")
                for sql, params in connection.executed
            )
        )

    def test_repository_rejects_stale_cost_publish_without_any_write(self) -> None:
        for current_source_version in (8, None):
            with self.subTest(current_source_version=current_source_version):
                connection = CostStatisticsWriteConnection(current_source_version=current_source_version)
                repository = PostgresReadModelRepository(connection)

                published = repository.publish_cost_statistics_read_models(
                    {"read_models": {}},
                    tenant_id="default",
                    scope_key="active:2026-05",
                    source_version=7,
                    changed_scope_keys={"active:2026-05"},
                )

                self.assertFalse(published)
                self.assertEqual(connection.transaction_count, 1)
                self.assertEqual(connection.executed, [])

    def test_repository_acknowledges_unchanged_cost_scope_without_rewriting_rows_or_payload(self) -> None:
        connection = CostStatisticsWriteConnection(current_source_version=7)
        repository = PostgresReadModelRepository(connection)
        source_versions = {"workbench_source_versions": {"source_version": 42}}

        acknowledged = repository.acknowledge_unchanged_cost_statistics_scope(
            tenant_id="default",
            scope_key="active:2026-05",
            source_version=7,
            source_versions=source_versions,
        )

        self.assertTrue(acknowledged)
        self.assertEqual(connection.transaction_count, 1)
        self.assertEqual(connection.executed, [])
        self.assertEqual(len(connection.fetch_one_calls), 2)
        lock_sql, lock_params = connection.fetch_one_calls[0]
        self.assertIn("from job.read_model_dirty_scopes", lock_sql)
        self.assertIn("status in ('pending', 'processing')", lock_sql)
        self.assertIn("for update", lock_sql)
        self.assertEqual(lock_params, ("default", "active:2026-05"))
        update_sql, update_params = connection.fetch_one_calls[1]
        self.assertIn("update read_model.cost_statistics_read_models", update_sql)
        self.assertIn("source_versions = %s::jsonb", update_sql)
        self.assertIn("returning scope_key", update_sql)
        self.assertEqual(update_params[0], 7)
        self.assertEqual(update_params[1], "active:2026-05")
        self.assertEqual(update_params[2].obj, source_versions)
        self.assertEqual(update_params[3], 7)

    def test_repository_rejects_unchanged_cost_ack_on_dirty_version_or_source_race(self) -> None:
        cases = (
            (8, True, 1),
            (None, True, 1),
            (7, False, 2),
        )
        for current_source_version, acknowledge_result, expected_fetches in cases:
            with self.subTest(
                current_source_version=current_source_version,
                acknowledge_result=acknowledge_result,
            ):
                connection = CostStatisticsWriteConnection(
                    current_source_version=current_source_version,
                    acknowledge_result=acknowledge_result,
                )
                repository = PostgresReadModelRepository(connection)

                acknowledged = repository.acknowledge_unchanged_cost_statistics_scope(
                    tenant_id="default",
                    scope_key="active:2026-05",
                    source_version=7,
                    source_versions={"proof": "v1"},
                )

                self.assertFalse(acknowledged)
                self.assertEqual(connection.transaction_count, 1)
                self.assertEqual(connection.executed, [])
                self.assertEqual(len(connection.fetch_one_calls), expected_fetches)

    def test_repository_reads_cost_statistics_scope_metadata_without_payload_or_row_scans(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "entry_count": 3,
                "source_versions": {"proof": "v1"},
                "payload": {"time_rows": [{"transaction_id": "must-not-load"}]},
            },
            cost_rows=[{"transaction_id": "must-not-scan"}],
            bank_flow_rows=[{"transaction_id": "must-not-scan"}],
            dirty_status="processing",
            dirty_source_version=8,
        )
        repository = PostgresReadModelRepository(connection)

        metadata = repository.get_cost_statistics_scope_metadata(scope_key="active:2026-05")

        self.assertEqual(
            metadata,
            {
                "scope_key": "active:2026-05",
                "entry_count": 3,
                "source_versions": {"proof": "v1"},
                "statistics_ready": False,
            },
        )
        self.assertEqual(len(connection.fetch_one_calls), 1)
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("select scope_key, entry_count, source_versions", sql)
        self.assertIn("payload #> '{payload,statistics}' is not null as statistics_ready", sql)
        self.assertNotIn("payload->", sql)
        self.assertNotIn("join", sql)
        self.assertNotIn("job.read_model_dirty_scopes", sql)
        self.assertEqual(params, ("active:2026-05",))
        self.assertEqual(connection.fetch_all_calls, [])

    def test_repository_reads_cost_statistics_freshness_with_one_gate_query(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "project_scope": "active",
                "scope_month": "2026-05-01",
                "generated_at": "2026-05-21T09:00:00+00:00",
                "entry_count": 1,
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "source_versions": {"proof": "v1"},
                "published_source_version": 7,
                "payload": {"month": "2026-05"},
            },
            cost_rows=[
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:0",
                    "transaction_id": "txn-1",
                    "amount": "10.00",
                    "payload": {"transaction_id": "txn-1"},
                }
            ],
            dirty_status="pending",
            dirty_source_version=8,
        )
        repository = PostgresReadModelRepository(connection)

        gate = repository.get_cost_statistics_freshness_gate(scope_key="active:2026-05")
        self.assertEqual(gate["refresh_status"], "refreshing")
        self.assertEqual(gate["published_source_version"], 7)
        self.assertEqual(gate["dirty_source_version"], 8)
        gate_sql = connection.fetch_one_calls[0][0]
        self.assertIn("left join lateral", gate_sql)
        self.assertIn("order by source_version desc", gate_sql)
        self.assertIn("from app.app_settings", gate_sql)
        self.assertIn("from read_model.workbench_generations", gate_sql)
        self.assertIn("from read_model.bank_detail_scopes", gate_sql)
        self.assertIn(
            "scope_key like split_part(model.scope_key, ':', 1) || ':%%'",
            gate_sql,
        )
        self.assertNotIn(
            "scope_key like split_part(model.scope_key, ':', 1) || ':%'",
            gate_sql,
        )
        self.assertEqual(len(connection.fetch_one_calls), 1)
        self.assertEqual(connection.fetch_all_calls, [])

    def test_repository_reads_active_workbench_versions_for_cost_parent_in_one_query(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_all(
                self,
                sql: str,
                params: tuple[object, ...] = (),
            ) -> list[dict[str, object]]:
                self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
                return [
                    {"scope_key": "2026-03", "source_versions": {"source_version": 7}},
                    {"scope_key": "2026-04", "source_versions": {"source_version": 8}},
                ]

        connection = Connection()
        versions = PostgresReadModelRepository(
            connection
        ).active_workbench_source_versions_by_scope(
            scope_keys=["2026-03", "2026-04", "2026-03"]
        )

        self.assertEqual(
            versions,
            {
                "2026-03": {"source_version": 7},
                "2026-04": {"source_version": 8},
            },
        )
        self.assertEqual(len(connection.fetch_all_calls), 1)
        sql, params = connection.fetch_all_calls[0]
        self.assertIn("select distinct on (scope_key)", sql)
        self.assertIn("scope_key = any(%s::text[])", sql)
        self.assertEqual(params, (["2026-03", "2026-04"],))

    def test_repository_parent_gate_fails_closed_with_exact_stale_child_scopes(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:all",
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "source_versions": {
                    **_cost_statistics_source_versions_fixture("active:all"),
                    "cost_statistics_parent_source": "materialized_shards",
                    "source_shard_count": 1,
                    "source_shards": {
                        "active:2026-03": _cost_statistics_source_versions_fixture(
                            "active:2026-03"
                        )
                    },
                },
                "published_source_version": 7,
                "workbench_refresh_scope_keys": [],
                "bank_detail_refresh_scope_keys": [],
                "child_refresh_scope_keys": ["active:2026-03"],
                "parent_child_has_failed": False,
                "parent_child_has_active": False,
                "parent_source_shards_match": False,
            },
            dirty_status="done",
            dirty_source_version=7,
        )

        gate = PostgresReadModelRepository(connection).get_cost_statistics_freshness_gate(
            scope_key="active:all"
        )

        self.assertEqual(gate["refresh_status"], "stale")
        self.assertEqual(gate["child_refresh_scope_keys"], ["active:2026-03"])
        self.assertEqual(gate["workbench_refresh_scope_keys"], [])
        self.assertEqual(gate["bank_detail_refresh_scope_keys"], [])
        self.assertIn("cost_statistics_parent_child_scope_not_fresh", gate["stale_reasons"])
        self.assertIn("cost_statistics_parent_source_shards_mismatch", gate["stale_reasons"])
        gate_sql = connection.fetch_one_calls[0][0]
        self.assertIn("with active_months as", gate_sql)
        self.assertIn("jsonb_object_agg(child_scope_key, child_source_versions)", gate_sql)
        self.assertIn("workbench_refresh_scope_keys", gate_sql)
        self.assertIn("bank_detail_refresh_scope_keys", gate_sql)
        self.assertIn("child_refresh_scope_keys", gate_sql)
        self.assertEqual(len(connection.fetch_one_calls), 1)
        self.assertEqual(connection.fetch_all_calls, [])

    def test_repository_month_gate_keeps_current_rows_but_marks_global_statistics_stale(
        self,
    ) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "source_versions": _cost_statistics_source_versions_fixture("active:2026-05"),
                "published_source_version": 7,
                "workbench_refresh_scope_keys": [],
                "child_refresh_scope_keys": ["active:2026-03"],
                "parent_child_has_failed": False,
                "parent_child_has_active": False,
                "parent_source_shards_match": False,
            },
            dirty_status="done",
            dirty_source_version=7,
        )

        gate = PostgresReadModelRepository(connection).get_cost_statistics_freshness_gate(
            scope_key="active:2026-05"
        )

        self.assertEqual(gate["refresh_status"], "fresh")
        self.assertEqual(gate["statistics_status"], "stale")
        self.assertEqual(gate["statistics_child_refresh_scope_keys"], ["active:2026-03"])
        self.assertEqual(len(connection.fetch_one_calls), 1)

    def test_repository_cost_statistics_gate_handles_done_failed_mismatch_and_pruned_history(self) -> None:
        cases = (
            ("done", 7, 7, "fresh", []),
            ("failed", 8, 7, "failed", ["dirty_scope_failed"]),
            ("done", 8, 7, "stale", ["published_source_version_mismatch"]),
            (None, None, 7, "fresh", []),
            (None, None, None, "stale", ["published_source_version_missing"]),
        )
        for dirty_status, dirty_version, published_version, expected_status, expected_reasons in cases:
            with self.subTest(dirty_status=dirty_status, dirty_version=dirty_version):
                connection = CostStatisticsReadConnection(
                    read_model_row={
                        "scope_key": "active:2026-05",
                        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                        "source_versions": {"proof": "v1"},
                        "published_source_version": published_version,
                    },
                    dirty_status=dirty_status,
                    dirty_source_version=dirty_version,
                )
                gate = PostgresReadModelRepository(connection).get_cost_statistics_freshness_gate(
                    scope_key="active:2026-05"
                )

                self.assertEqual(gate["refresh_status"], expected_status)
                self.assertEqual(gate["stale_reasons"], expected_reasons)

    def test_repository_cost_statistics_gate_fails_closed_for_dependency_state_and_version_drift(self) -> None:
        cases = (
            ({"workbench_dirty_status": "pending"}, "refreshing", "cost_statistics_dependency_refreshing"),
            ({"bank_detail_dirty_status": "failed"}, "failed", "cost_statistics_dependency_dirty_scope_failed"),
            (
                {"source_settings": {"bank_transaction_tags": [], "bank_account_mappings": []}},
                "stale",
                "cost_statistics_source_settings_missing",
            ),
            ({"bank_detail_source_versions": {}}, "stale", "bank_detail_source_versions_missing"),
            (
                {"workbench_dirty_source_version": 2},
                "stale",
                "workbench_published_source_version_mismatch",
            ),
            (
                {"bank_detail_dirty_source_version": 2},
                "stale",
                "bank_detail_published_source_version_mismatch",
            ),
        )
        for overrides, expected_status, expected_reason in cases:
            with self.subTest(overrides=overrides):
                connection = CostStatisticsReadConnection(
                    read_model_row={
                        "scope_key": "active:2026-05",
                        "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                        "source_versions": _cost_statistics_source_versions_fixture("active:2026-05"),
                        "published_source_version": 7,
                        **overrides,
                    },
                    dirty_status="done",
                    dirty_source_version=7,
                )

                gate = PostgresReadModelRepository(connection).get_cost_statistics_freshness_gate(
                    scope_key="active:2026-05"
                )

                self.assertEqual(gate["refresh_status"], expected_status)
                self.assertIn(expected_reason, gate["stale_reasons"])

    def test_repository_bank_flow_gate_ignores_workbench_dirty_state_only(self) -> None:
        connection = CostStatisticsReadConnection(
            read_model_row={
                "scope_key": "active:2026-05",
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "source_versions": _cost_statistics_source_versions_fixture("active:2026-05"),
                "published_source_version": 7,
                "workbench_dirty_status": "processing",
            },
            dirty_status="done",
            dirty_source_version=7,
        )

        gate = PostgresReadModelRepository(connection).get_cost_statistics_freshness_gate(
            scope_key="active:2026-05"
        )

        self.assertEqual(gate["refresh_status"], "refreshing")
        self.assertEqual(gate["bank_flow_refresh_status"], "fresh")
        self.assertEqual(gate["bank_flow_bank_detail_refresh_scope_keys"], [])
        self.assertEqual(gate["bank_flow_child_refresh_scope_keys"], [])

    def test_repository_gets_cost_statistics_transaction_by_indexed_identity(self) -> None:
        connection = CostStatisticsReadConnection(
            cost_rows=[
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:0",
                    "transaction_id": "txn-1",
                    "amount": "19.25",
                    "payload": {"project_name": "项目A", "expense_type": "材料"},
                }
            ],
            bank_flow_rows=[
                {
                    "scope_key": "active:2026-05",
                    "project_scope": "active",
                    "scope_month": "2026-05-01",
                    "row_key": "txn-1:bank",
                    "transaction_id": "txn-1",
                    "amount": "99.00",
                    "payload": {"project_name": "未配对OA", "expense_type": "其他"},
                }
            ],
        )

        row = PostgresReadModelRepository(connection).get_cost_statistics_transaction(
            project_scope="active",
            transaction_id="txn-1",
        )

        self.assertEqual(row["transaction_id"], "txn-1")
        self.assertEqual(row["amount"], "19.25")
        self.assertEqual(row["cost_allocations"][0]["amount"], "19.25")
        sql, params = connection.fetch_one_calls[0]
        self.assertIn("from read_model.cost_statistics_rows", sql)
        self.assertIn("from read_model.cost_statistics_bank_flow_rows", sql)
        self.assertIn("order by row_priority", sql)
        self.assertEqual(
            params,
            ("active", "txn-1", "active", "txn-1", "active", "txn-1"),
        )

    def test_repository_cost_export_page_filters_and_bounds_structured_rows(self) -> None:
        class Connection:
            def __init__(self) -> None:
                self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
                self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
                self.fetch_one_calls.append((" ".join(sql.lower().split()), params))
                return {
                    "source_row_count": 25,
                    "row_count": 25,
                    "transaction_count": 25,
                    "total_amount": "250.00",
                    "expense_amount": "250.00",
                    "income_amount": "0.00",
                    "expense_transaction_count": 25,
                    "income_transaction_count": 0,
                    "expense_type_count": 1,
                }

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
                self.fetch_all_calls.append((" ".join(sql.lower().split()), params))
                return [
                    {
                        "transaction_id": "txn-1",
                        "scope_month": "2026-05-01",
                        "trade_time_text": "2026-05-21 09:00:00",
                        "amount": "10.00",
                    }
                ]

        connection = Connection()
        page = PostgresReadModelRepository(connection).get_cost_statistics_export_page(
            project_scope="active",
            month="all",
            start_month="2026-04",
            end_month="2026-06",
            start_date="2026-04-15",
            end_date="2026-06-20",
            project_names=["项目A"],
            expense_types=["材料"],
            selected_tag_codes=["fee"],
            row_shape="raw_cost",
            offset=0,
            page_size=1000,
            include_summary=True,
        )

        self.assertEqual(page["summary"]["source_row_count"], 25)
        self.assertEqual(page["rows"][0]["transaction_id"], "txn-1")
        self.assertIsNone(page["next_offset"])
        summary_sql, summary_params = connection.fetch_one_calls[0]
        page_sql, page_params = connection.fetch_all_calls[0]
        for sql in (summary_sql, page_sql):
            self.assertIn("from read_model.cost_statistics_rows", sql)
            self.assertIn("scope_month >= %s::date", sql)
            self.assertIn("scope_month < (%s::date + interval '1 month')", sql)
            self.assertIn("trade_date >= %s::date", sql)
            self.assertIn("trade_date <= %s::date", sql)
            self.assertIn("project_name = any(%s)", sql)
            self.assertIn("expense_type = any(%s)", sql)
            self.assertIn("coalesce(nullif(payload->>'bank_tag_code', ''), %s) = any(%s)", sql)
        self.assertEqual(summary_params[:3], ("active", "2026-04-01", "2026-06-01"))
        self.assertEqual(page_params[-2:], (0, 1000))

    def test_cost_statistics_api_reads_redis_hot_cache_after_postgres_gate_without_full_payload(self) -> None:
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        source_versions = _cost_statistics_source_versions_fixture("active:2026-05")
        gate_calls: list[str] = []
        call_order: list[str] = []
        gate_version = {"value": 7}
        redis = RedisRecorder(
            redis_fresh_payload(
                {
                    "scope": "2026-05",
                    "view": "time",
                    "summary": {"row_count": 0, "transaction_count": 0, "total_amount": "0.00"},
                    "available_years": ["2026"],
                    "facets": {
                        "projects": [],
                        "expense_types": [],
                        "bank_accounts": [],
                        "bank_tag_primary": [],
                        "bank_tag_sub": [],
                    },
                    "rows": [],
                    "row_count": 0,
                    "next_cursor": None,
                },
                scope_key="active:2026-05",
                source_versions=cost_statistics_semantic_source_versions(source_versions),
            )
        )
        redis_get_json = redis.get_json
        redis.get_json = lambda key: (call_order.append("redis"), redis_get_json(key))[1]  # type: ignore[method-assign]
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {
                "queue_repository": QueueRecorder(),
                "redis_helper": redis,
            },
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_freshness_gate": lambda _self, *, scope_key: (
                    gate_calls.append(scope_key)
                    or call_order.append("gate")
                    or cost_statistics_fresh_gate(
                        scope_key=scope_key,
                        source_versions=source_versions,
                        published_source_version=gate_version["value"],
                    )
                ),
                "get_cost_statistics_page": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("page SQL should not be hit on Redis cache")
                ),
            },
        )()
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["scope"], "2026-05")
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(gate_calls, ["active:2026-05"])
        self.assertEqual(call_order, ["gate", "redis"])

        first_cache_key = redis.gets[-1]
        gate_version["value"] = 8
        second_response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )

        self.assertEqual(second_response.status_code, int(HTTPStatus.OK))
        self.assertNotEqual(redis.gets[-1], first_cache_key)

    def test_cost_statistics_non_fresh_postgres_gate_blocks_redis_and_full_payload(self) -> None:
        for gate_status, stale_reasons in (
            ("refreshing", []),
            ("failed", ["dirty_scope_failed"]),
            ("stale", ["published_source_version_mismatch"]),
        ):
            with self.subTest(gate_status=gate_status):
                queue = QueueRecorder()
                redis = RedisRecorder({"payload": {"month": "2026-05", "read_model_status": "fresh"}})
                app = object.__new__(Application)
                app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
                app._cost_statistics_workbench_dependency_versions_by_scope = (
                    _fresh_workbench_dependency_versions_by_scope
                )
                app._app_settings_service = CostStatisticsAppSettingsStub()
                app._runtime_repositories = type(
                    "RuntimeRepos",
                    (),
                    {"queue_repository": queue, "redis_helper": redis},
                )()
                app._cost_statistics_sql_read_repository = type(
                    "SqlCostStats",
                    (),
                    {
                        "get_cost_statistics_freshness_gate": lambda _self, *, scope_key: (
                            cost_statistics_fresh_gate(
                                scope_key=scope_key,
                                source_versions={},
                                published_source_version=7,
                                refresh_status=gate_status,
                                stale_reasons=stale_reasons,
                            )
                        ),
                        "get_cost_statistics_page": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                            AssertionError("non-fresh gate must not load page payload")
                        ),
                    },
                )()

                response = app._cost_statistics_routes().route(
                    "GET",
                    "/api/cost-statistics/explorer",
                    {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
                )
                payload = json.loads(response.body)

                self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
                self.assertEqual(payload["read_model_status"], "refreshing")
                self.assertEqual(payload["rows"], [])
                self.assertEqual(payload["facets"]["projects"], [])
                self.assertEqual(redis.gets, [])
                self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_page_stale")])

    def test_cost_statistics_api_miss_enqueues_refresh_and_returns_refreshing(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_freshness_gate": lambda *_args, **_kwargs: None,
                "get_cost_statistics_page": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("missing gate must not load page payload")
                ),
            },
        )()
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_page_miss")])

    def test_production_postgres_cost_statistics_requires_sql_read_model_without_sync_build(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._bootstrap_mode = "production"
        app._state_store = type("PostgresStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._cost_statistics_sql_read_repository = None
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["refresh_reason"], "api_page_sql_repository_unavailable")
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_page_sql_repository_unavailable")])

    def test_cost_statistics_api_reads_sql_and_populates_short_redis_cache(self) -> None:
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": QueueRecorder(), "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_freshness_gate": lambda _self, *, scope_key: cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=_cost_statistics_source_versions_fixture(scope_key),
                ),
                "get_cost_statistics_page": lambda *_args, **_kwargs: {
                    "summary": {"row_count": 1, "transaction_count": 1, "total_amount": "100.00"},
                    "available_years": ["2026"],
                    "primary_facets": [],
                    "secondary_facets": [],
                    "rows": [
                            {
                                "transaction_id": "txn-1",
                                "trade_time": "2026-05-21 09:00:00",
                                "direction": "支出",
                                "project_name": "云南溯源科技",
                                "expense_type": "设备货款及材料费",
                                "expense_content": "PLC 模块采购",
                                "amount": "100.00",
                                "counterparty_name": "供应商",
                                "payment_account_label": "工行",
                                "remark": "",
                            }
                    ],
                    "row_count": 1,
                    "next_cursor_values": None,
                },
            },
        )()
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.OK))
        self.assertEqual(payload["rows"][0]["transaction_id"], "txn-1")
        self.assertTrue(
            redis.sets[0][0].startswith("cost_statistics:page:")
        )
        self.assertLessEqual(redis.sets[0][2], 120)

    def test_cost_statistics_api_rejects_old_bank_tag_schema_parent_payload_without_old_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_freshness_gate": lambda _self, *, scope_key: {
                    **cost_statistics_fresh_gate(
                        scope_key=scope_key,
                        source_versions=_cost_statistics_source_versions_fixture(scope_key),
                    ),
                    "schema_version": "2026-07-cost-statistics-bank-accounts-v3",
                },
                "get_cost_statistics_page": lambda *_args, **_kwargs: (_ for _ in ()).throw(
                    AssertionError("schema mismatch gate must not load page rows")
                ),
            },
        )()
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["all"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:all")
        self.assertEqual(payload["read_model_stale_reasons"], ["schema_version_mismatch"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["facets"]["projects"], [])
        self.assertEqual(payload["facets"]["expense_types"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:all", "api_page_source_versions_stale")])

    def test_cost_statistics_api_rejects_malformed_fresh_sql_payload_and_requeues(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()
        app._cost_statistics_sql_read_repository = type(
            "SqlCostStats",
            (),
            {
                "get_cost_statistics_freshness_gate": lambda _self, *, scope_key: cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=_cost_statistics_source_versions_fixture(scope_key),
                ),
                "get_cost_statistics_page": lambda *_args, **_kwargs: None,
            },
        )()
        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:2026-05")
        self.assertEqual(payload["refresh_reason"], "api_page_miss")
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["facets"]["projects"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_page_miss")])
        self.assertEqual(redis.sets, [])

    def test_cost_statistics_refresh_handler_rebuilds_scope_and_marks_dirty_scope_done(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[tuple[str, str, int]] = []

            def rebuild_cost_statistics_month_scope(
                self,
                scope_key: str,
                *,
                tenant_id: str,
                source_version: int,
            ) -> dict[str, object]:
                self.rebuilt.append((scope_key, tenant_id, source_version))
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
            payload={"scope_key": "active:2026-05", "source_version": 0},
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-cost-month",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, [("active:2026-05", "tenant-a", 0)])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:2026-05", 0)])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:all", "cost_statistics_shard_converged")])
        self.assertEqual(
            queue.refresh_details,
            [
                {
                    "scope_type": "cost_statistics",
                    "scope_key": "active:all",
                    "reason": "cost_statistics_shard_converged",
                    "tenant_id": "tenant-a",
                    "priority": "high",
                    "trace_id": "trace-cost-month",
                }
            ],
        )
        self.assertEqual(result["entry_count"], 1)

    def test_cost_statistics_force_refresh_rebuilds_full_month(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.month_calls: list[tuple[str, str, int, bool]] = []

            def rebuild_cost_statistics_month_scope(
                self,
                scope_key: str,
                *,
                tenant_id: str,
                source_version: int,
                force_refresh: bool = False,
            ) -> dict[str, object]:
                self.month_calls.append(
                    (scope_key, tenant_id, source_version, force_refresh)
                )
                return {"scope_key": scope_key, "published": True, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(
            projection_builder=builder,
            queue_repository=queue,
        )
        event = RuntimeQueueEvent(
            event_id="event-force-month",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={
                "scope_key": "active:2026-05",
                "source_version": 9,
                "metadata": {"force_refresh": True},
            },
            attempts=1,
            status="processing",
            priority="high",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            builder.month_calls,
            [("active:2026-05", "tenant-a", 9, True)],
        )
        self.assertEqual(result["refresh_kind"], "month")

    def test_cost_statistics_refresh_handler_ignores_unowned_metadata_and_rebuilds_month(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.month_calls: list[tuple[str, str, int]] = []

            def rebuild_cost_statistics_month_scope(
                self,
                scope_key: str,
                *,
                tenant_id: str,
                source_version: int,
            ) -> dict[str, object]:
                self.month_calls.append((scope_key, tenant_id, source_version))
                return {"scope_key": scope_key, "published": True, "row_count": 1}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-no-state",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={
                "scope_key": "active:2026-05",
                "source_version": 10,
                "metadata": {"row_ids": ["oa-1", "txn-1"], "case_ids": ["CASE-1"]},
            },
            attempts=1,
            status="processing",
            priority="normal",
            trace_id="trace-no-state",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.month_calls, [("active:2026-05", "tenant-a", 10)])
        self.assertEqual(result["refresh_kind"], "month")

    def test_cost_statistics_refresh_handler_rejects_invalid_source_versions(self) -> None:
        class FakeBuilder:
            def rebuild_cost_statistics_month_scope(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("invalid source version must fail before rebuild")

        service = CostStatisticsReadModelRefreshService(
            projection_builder=FakeBuilder(),
            queue_repository=QueueRecorder(),
        )
        for source_version in (None, -1, True, "1.5"):
            with self.subTest(source_version=source_version):
                event = RuntimeQueueEvent(
                    event_id="event-invalid",
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
                    source_version=source_version,
                )
                with self.assertRaisesRegex(ValueError, "non-negative integer source_version"):
                    service.handle_runtime_event(event)

    def test_cost_statistics_refresh_handler_does_not_complete_or_fan_out_rejected_publish(self) -> None:
        class FakeBuilder:
            def rebuild_cost_statistics_month_scope(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {
                    "scope_key": "active:2026-05",
                    "published": False,
                    "skip_reason": "stale_source_version_at_publish",
                }

        queue = QueueRecorder()
        service = CostStatisticsReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-stale",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={"scope_key": "active:2026-05", "source_version": 7},
            attempts=1,
            status="processing",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["readiness_status"], "refreshing")
        self.assertEqual(result["skip_reason"], "stale_source_version_at_publish")
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [])

    def test_cost_statistics_refresh_handler_keeps_new_dirty_when_completion_loses_race(self) -> None:
        class FakeBuilder:
            def rebuild_cost_statistics_month_scope(self, *_args: object, **_kwargs: object) -> dict[str, object]:
                return {"scope_key": "active:2026-05", "published": True, "entry_count": 1}

        queue = QueueRecorder(complete_result=False)
        service = CostStatisticsReadModelRefreshService(projection_builder=FakeBuilder(), queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-raced",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:2026-05",
            scope_type="cost_statistics",
            scope_key="active:2026-05",
            dedupe_key=None,
            payload={"scope_key": "active:2026-05", "source_version": 7},
            attempts=1,
            status="processing",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(result["skip_reason"], "stale_source_version_after_rebuild")
        self.assertEqual(result["readiness_status"], "refreshing")
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:2026-05", 7)])
        self.assertEqual(queue.refreshes, [])

    def test_cost_statistics_refresh_handler_requires_projection_builder_boundary(self) -> None:
        with self.assertRaisesRegex(ValueError, "projection_builder is required"):
            CostStatisticsReadModelRefreshService(queue_repository=object())

    def test_cost_statistics_sql_projection_excludes_open_candidate_groups_from_amounts(self) -> None:
        repository = CostStatisticsSaveRecorder()
        connection = CostStatisticsProjectionConnection(include_open_candidate=True)
        tag_facade = CostStatisticsBankTagFacade()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
            bank_transaction_tag_read_facade=tag_facade,
        )

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(result["entry_count"], 1)
        snapshot, changed_scope_keys = repository.saved[0]
        self.assertEqual(changed_scope_keys, {"active:2026-05"})
        payload = snapshot["read_models"]["active:2026-05"]["payload"]
        self.assertEqual(payload["summary"]["transaction_count"], 1)
        self.assertEqual(payload["summary"]["total_amount"], "10.00")
        self.assertEqual(
            [(row["transaction_id"], row["direction"]) for row in payload["bank_flow_time_rows"]],
            [("bank-income", "收入"), ("bank-expense", "支出")],
        )
        self.assertEqual(payload["bank_flow_summary"]["expense_amount"], "20.00")
        self.assertEqual(payload["bank_flow_summary"]["income_amount"], "30.00")
        self.assertNotIn("direction", tag_facade.snapshot_calls[0][1])
        self.assertEqual([row["transaction_id"] for row in payload["time_rows"]], ["bank-1"])
        self.assertEqual(payload["time_rows"][0]["group_id"], "group-1")
        self.assertEqual(payload["time_rows"][0]["project_id"], "P-A")
        self.assertEqual(payload["time_rows"][0]["bank_tag_primary_label"], "项目开销")
        self.assertEqual(payload["time_rows"][0]["bank_tag_sub_label"], "设备材料")
        self.assertEqual(payload["time_rows"][0]["bank_tag_label_path"], ["项目开销", "设备材料"])
        self.assertIn("g.group_type = 'relation'", connection.fetch_all_calls[0][0])
        self.assertEqual(tag_facade.source_version_calls, [])
        self.assertEqual(tag_facade.category_calls, [])
        self.assertEqual(tag_facade.month_calls, [])
        self.assertEqual(len(tag_facade.snapshot_calls), 1)
        self.assertEqual(tag_facade.snapshot_calls[0][1]["include_transaction_ids"], ["bank-1"])
        self.assertEqual(tag_facade.snapshot_calls[0][1]["reason"], "downstream_bank_tag_read")
        self.assertEqual(tag_facade.snapshot_calls[0][1]["require_fresh"], False)
        self.assertEqual(
            snapshot["read_models"]["active:2026-05"]["source_versions"]["bank_detail_source_versions"],
            {"bank_detail_scope_version": "bank-detail-v2"},
        )
        self.assertEqual(
            payload["bank_accounts"],
            [
                {
                    "bank_name": "工商银行",
                    "account_last4": "0001",
                    "payment_account_label": "工商银行 账户 0001",
                    "source": "settings",
                },
                {
                    "bank_name": "民生银行",
                    "account_last4": "9486",
                    "payment_account_label": "民生银行 账户 9486",
                    "source": "settings",
                },
            ],
        )
        self.assertIn(
            "bank_account_mappings_fingerprint",
            snapshot["read_models"]["active:2026-05"]["source_versions"],
        )
        workbench_sql, workbench_params = next(
            (sql, params) for sql, params in connection.fetch_all_calls if "read_model.workbench_groups" in sql
        )
        self.assertEqual(workbench_params, ("2026-05", "2026-05"))
        self.assertIn("with active_generation as", workbench_sql)
        self.assertIn("join read_model.workbench_groups", workbench_sql)
        self.assertIn("join read_model.workbench_group_rows", workbench_sql)
        self.assertIn("left join read_model.workbench_rows", workbench_sql)
        self.assertIn("g.generation_id = active.generation_id", workbench_sql)
        self.assertNotIn("jsonb_path_exists", workbench_sql)
        settings_reads = [
            sql
            for sql, _params in connection.fetch_one_calls
            if "from app.app_settings" in sql
        ]
        self.assertEqual(len(settings_reads), 1)

    def test_cost_statistics_sql_projection_includes_unpaired_formal_relation_without_invoice(self) -> None:
        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(include_unpaired_relation=True),
            read_model_repository=repository,
            bank_transaction_tag_read_facade=CostStatisticsBankTagFacade(),
        )

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(result["entry_count"], 2)
        payload = repository.saved[0][0]["read_models"]["active:2026-05"]["payload"]
        self.assertEqual(payload["summary"]["transaction_count"], 2)
        self.assertEqual(payload["summary"]["total_amount"], "1,009.00")
        self.assertEqual(
            {row["transaction_id"] for row in payload["time_rows"]},
            {"bank-1", "bank-candidate"},
        )

    def test_cost_statistics_sql_projection_reports_rejected_publish(self) -> None:
        repository = CostStatisticsSaveRecorder(publish_result=False)
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
            bank_transaction_tag_read_facade=CostStatisticsBankTagFacade(),
        )

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
        )

        self.assertFalse(result["published"])
        self.assertEqual(result["skip_reason"], "stale_source_version_at_publish")
        self.assertEqual(repository.saved, [])

    def test_cost_statistics_sql_projection_rejects_legacy_redis_dependency(self) -> None:
        with self.assertRaises(TypeError):
            CostStatisticsSqlProjectionBuilder(
                connection=CostStatisticsProjectionConnection(),
                read_model_repository=CostStatisticsSaveRecorder(),
                redis_helper=RedisRecorder(),
                bank_transaction_tag_read_facade=CostStatisticsBankTagFacade(),
            )

    def test_cost_statistics_sql_projection_defers_when_bank_detail_tags_are_not_fresh(self) -> None:
        repository = CostStatisticsSaveRecorder()
        tag_facade = CostStatisticsBankTagFacade(status="refreshing")
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
            bank_transaction_tag_read_facade=tag_facade,
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "bank_detail_read_model_not_fresh: operation=month_snapshot status=refreshing scope_keys=2026-05",
        ):
            builder.rebuild_cost_statistics_read_model_scope(
                "active:2026-05",
                tenant_id="default",
                source_version=7,
            )

        self.assertEqual(repository.saved, [])
        self.assertEqual(tag_facade.source_version_calls, [])
        self.assertEqual(tag_facade.category_calls, [])
        self.assertEqual(tag_facade.month_calls, [])
        self.assertEqual(len(tag_facade.snapshot_calls), 1)
        self.assertEqual(tag_facade.snapshot_calls[0][1]["reason"], "downstream_bank_tag_read")
        self.assertEqual(tag_facade.snapshot_calls[0][1]["require_fresh"], False)

    def test_cost_statistics_source_version_mapper_includes_gate_dependency_snapshots(self) -> None:
        source_versions = cost_statistics_source_versions(
            month="2026-05",
            settings_payload=_cost_statistics_source_settings_fixture(),
            workbench_source_versions={"builder": "workbench-v5", "source_version": 2511},
            bank_detail_source_versions={"bank_detail_scope_version": "bank-detail-v2"},
        )

        self.assertEqual(
            source_versions["bank_detail_source_versions"],
            {"bank_detail_scope_version": "bank-detail-v2"},
        )
        self.assertEqual(
            source_versions["workbench_source_versions"],
            {"builder": "workbench-v5", "source_version": 2511},
        )
        self.assertNotIn("oa_attachment_invoice_parser_version", source_versions)
        self.assertEqual(
            source_versions["cost_statistics_read_model_schema_version"],
            "2026-07-cost-statistics-oa-bank-flow-v11",
        )
        parent_source_versions = cost_statistics_source_versions(
            month="all",
            settings_payload=_cost_statistics_source_settings_fixture(),
            workbench_source_versions={"source_version": 2511},
            bank_detail_source_versions={"source_version": 12},
        )
        self.assertNotIn("workbench_source_versions", parent_source_versions)
        self.assertNotIn("bank_detail_source_versions", parent_source_versions)

    def test_cost_statistics_semantic_versions_ignore_only_bank_detail_nonconsumed_provenance(self) -> None:
        first = cost_statistics_semantic_source_versions(
            {
                "bank_detail_source_versions": {
                    "source_version": 10,
                    "bank_detail_source_signature": "same-business-data",
                    "bank_auto_tag_rules_version": 7,
                    "workbench_relation_source_versions": {"source_version": 30},
                },
                "workbench_source_versions": {"source_version": 20},
            }
        )
        second = cost_statistics_semantic_source_versions(
            {
                "bank_detail_source_versions": {
                    "source_version": 11,
                    "bank_detail_source_signature": "same-business-data",
                    "bank_auto_tag_rules_version": 7,
                    "workbench_relation_source_versions": {"source_version": 31},
                },
                "workbench_source_versions": {"source_version": 20},
            }
        )

        self.assertEqual(first, second)
        self.assertEqual(first["workbench_source_versions"]["source_version"], 20)
        self.assertNotIn("workbench_relation_source_versions", first["bank_detail_source_versions"])
        self.assertNotEqual(
            first,
            cost_statistics_semantic_source_versions(
                {
                    **second,
                    "bank_detail_source_versions": {
                        "source_version": 11,
                        "bank_detail_source_signature": "changed-business-data",
                        "bank_auto_tag_rules_version": 7,
                    },
                }
            ),
        )

    def test_bank_flow_versions_exclude_workbench_and_keep_bank_business_proof(self) -> None:
        payload = cost_statistics_bank_flow_source_versions(
            {
                "cost_statistics_read_model_schema_version": "v11",
                "workbench_scope_key": "2026-05",
                "workbench_read_model_schema_version": "workbench-v6",
                "workbench_source_versions": {"source_version": 20},
                "oa_projection_sync_version": "oa-v3",
                "bank_auto_tag_rules_version": 7,
                "bank_detail_source_versions": {
                    "source_version": 11,
                    "bank_detail_source_signature": "business-v2",
                    "workbench_relation_source_versions": {"source_version": 31},
                },
            }
        )

        self.assertEqual(
            payload,
            {
                "cost_statistics_read_model_schema_version": "v11",
                "bank_auto_tag_rules_version": 7,
                "bank_detail_source_versions": {
                    "bank_detail_source_signature": "business-v2",
                },
            },
        )

    def test_cost_statistics_api_rejects_snapshot_built_from_old_workbench_generation(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        current_workbench_versions = {"builder": "workbench-v5", "source_version": 2511}
        old_workbench_versions = {"builder": "workbench-v5", "source_version": 2504}

        class SqlCostStats:
            def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, object]:
                source_versions = _cost_statistics_source_versions_fixture(scope_key)
                source_versions["workbench_source_versions"] = old_workbench_versions
                return cost_statistics_fresh_gate(
                    scope_key=scope_key,
                    source_versions=source_versions,
                    workbench_source_versions=current_workbench_versions,
                )

            def get_cost_statistics_page(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("source mismatch gate must not load page payload")

        repository = SqlCostStats()
        app._cost_statistics_sql_read_repository = repository
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": RedisRecorder()},
        )()

        response = app._cost_statistics_routes().route(
            "GET",
            "/api/cost-statistics/explorer",
            {"scope": ["2026-05"], "view": ["time"], "project_scope": ["active"]},
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "active:2026-05")
        self.assertEqual(payload["read_model_stale_reasons"], ["workbench_source_versions_mismatch"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(queue.refreshes, [("cost_statistics", "active:2026-05", "api_page_source_versions_stale")])

    def test_cost_statistics_scope_shards_are_listed_from_active_workbench_generations(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                self.fetch_all_calls.append((normalized, params))
                if "from read_model.workbench_rows" in normalized:
                    raise AssertionError("cost statistics shard discovery must not scan historical workbench rows")
                if "from read_model.workbench_generations" in normalized:
                    return [
                        {"scope_key": "2026-06"},
                        {"scope_key": "all"},
                        {"scope_key": "legacy"},
                        {"scope_key": "2026-05"},
                    ]
                return []

        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=CostStatisticsSaveRecorder(),
        )

        self.assertEqual(
            builder.list_cost_statistics_scope_shards("active:all"),
            ["active:2026-06", "active:2026-05"],
        )
        workbench_sql = next(sql for sql, _params in connection.fetch_all_calls if "from read_model.workbench_generations" in sql)
        self.assertIn("status = 'active'", workbench_sql)

    def test_cost_statistics_sql_projection_skips_unchanged_month_scope_without_workbench_scan(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized:
                    return {"source_versions": {"workbench_generation": "stable-v1", "source_version": 42}}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_groups" in normalized:
                    raise AssertionError("unchanged cost statistics scope must not scan workbench groups")
                return super().fetch_all(sql, params)

        repository = UnchangedCostStatisticsSaveRecorder()
        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        repository.source_versions = builder._source_versions("2026-05")

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(repository.metadata_scopes, ["active:2026-05"])
        self.assertEqual(result["scope_key"], "active:2026-05")
        self.assertEqual(result["row_count"], 1)
        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertTrue(result["published"])
        self.assertTrue(result["skipped_rebuild"])
        self.assertNotIn("skipped", result)
        self.assertEqual(
            repository.acknowledge_calls,
            [("default", "active:2026-05", 7, repository.source_versions)],
        )
        self.assertEqual(result["source_versions"]["workbench_source_versions"]["workbench_generation"], "stable-v1")

    def test_cost_statistics_sql_projection_skips_unchanged_scope_while_dirty_scope_is_processing(self) -> None:
        class Connection(CostStatisticsProjectionConnection):
            def fetch_one(self, sql: str, params: tuple = ()) -> dict | None:
                normalized = " ".join(sql.lower().split())
                self.fetch_one_calls.append((normalized, params))
                if "from read_model.workbench_generations" in normalized:
                    return {"source_versions": {"workbench_generation": "stable-v1", "source_version": 42}}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_groups" in normalized:
                    raise AssertionError("current dirty scope must not defeat unchanged source-version skip")
                return super().fetch_all(sql, params)

        repository = UnchangedCostStatisticsSaveRecorder(refresh_status="refreshing")
        connection = Connection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        repository.source_versions = builder._source_versions("2026-05")

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(result["skip_reason"], "source_versions_unchanged")
        self.assertTrue(result["published"])
        self.assertTrue(result["skipped_rebuild"])
        self.assertNotIn("skipped", result)
        self.assertEqual(
            repository.acknowledge_calls,
            [("default", "active:2026-05", 7, repository.source_versions)],
        )

    def test_cost_statistics_sql_projection_force_refresh_bypasses_unchanged_scope(self) -> None:
        repository = UnchangedCostStatisticsSaveRecorder()
        connection = CostStatisticsProjectionConnection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )
        repository.source_versions = builder._source_versions("2026-05")

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:2026-05",
            tenant_id="default",
            source_version=7,
            force_refresh=True,
        )

        self.assertTrue(result["published"])
        self.assertNotIn("skip_reason", result)
        self.assertEqual(repository.acknowledge_calls, [])
        self.assertTrue(
            any(
                "read_model.workbench_groups" in " ".join(sql.lower().split())
                for sql, _params in connection.fetch_all_calls
            )
        )

    def test_cost_statistics_sql_projection_rejects_unchanged_ack_after_dirty_version_race(self) -> None:
        repository = UnchangedCostStatisticsSaveRecorder(acknowledge_result=False)
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
        )
        source_versions = {"proof": "v1"}
        repository.source_versions = source_versions

        result = builder._unchanged_cost_statistics_scope_result(
            scope_key="active:2026-05",
            month="2026-05",
            project_scope="active",
            source_versions=source_versions,
            refresh_kind="month",
            tenant_id="default",
            source_version=7,
        )

        self.assertFalse(result["published"])
        self.assertTrue(result["skipped"])
        self.assertEqual(result["skip_reason"], "stale_source_version_at_unchanged_ack")
        self.assertEqual(repository.publish_calls, [])

    def test_cost_statistics_sql_projection_rebuilds_parent_without_statistics(self) -> None:
        repository = UnchangedCostStatisticsSaveRecorder()
        repository.source_versions = {"proof": "v1"}
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
        )
        original_get_metadata = repository.get_cost_statistics_scope_metadata

        def metadata_without_statistics(*, scope_key: str) -> dict[str, object]:
            metadata = original_get_metadata(scope_key=scope_key)
            metadata["statistics_ready"] = False
            return metadata

        repository.get_cost_statistics_scope_metadata = metadata_without_statistics

        result = builder._unchanged_cost_statistics_scope_result(
            scope_key="active:all",
            month="all",
            project_scope="active",
            source_versions=repository.source_versions,
            refresh_kind="parent",
            tenant_id="default",
            source_version=7,
        )

        self.assertIsNone(result)
        self.assertEqual(repository.acknowledge_calls, [])

    def test_cost_statistics_sql_projection_does_not_skip_mismatched_scope_metadata(self) -> None:
        repository = UnchangedCostStatisticsSaveRecorder()
        repository.source_versions = {"proof": "published-v1"}
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsProjectionConnection(),
            read_model_repository=repository,
        )

        result = builder._unchanged_cost_statistics_scope_result(
            scope_key="active:2026-05",
            month="2026-05",
            project_scope="active",
            source_versions={"proof": "current-v2"},
            refresh_kind="month",
            tenant_id="default",
            source_version=7,
        )

        self.assertIsNone(result)
        self.assertEqual(repository.metadata_scopes, ["active:2026-05"])

    def test_cost_statistics_sql_projection_rebuilds_active_all_from_shard_metadata_without_loading_rows(self) -> None:
        repository = CostStatisticsSaveRecorder()
        connection = CostStatisticsParentAggregationConnection()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=connection,
            read_model_repository=repository,
        )

        result = builder.rebuild_cost_statistics_read_model_scope(
            "active:all",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["month"], "all")
        self.assertEqual(result["project_scope"], "active")
        self.assertEqual(result["entry_count"], 2)
        self.assertTrue(all("workbench_groups" not in sql for sql, _params in connection.fetch_all_calls))
        snapshot, changed_scope_keys = repository.saved[0]
        self.assertEqual(changed_scope_keys, {"active:all"})
        self.assertIn("active:all", snapshot["read_models"])
        payload = snapshot["read_models"]["active:all"]["payload"]
        self.assertEqual(payload["month"], "all")
        self.assertEqual(payload["summary"]["total_amount"], "15.50")
        self.assertEqual(payload["bank_flow_summary"]["total_amount"], "20.00")
        self.assertEqual(len(payload["project_rows"]), 2)
        self.assertEqual(len(payload["expense_type_rows"]), 2)
        self.assertEqual(payload["bank_accounts"][0]["payment_account_label"], "工商银行 账户 0001")
        self.assertEqual(snapshot["read_models"]["active:all"]["source_versions"]["source_shard_count"], 2)
        self.assertFalse(any("read_model.cost_statistics_rows" in sql for sql, _params in connection.fetch_all_calls))
        self.assertFalse(any("read_model.cost_statistics_bank_flow_rows" in sql for sql, _params in connection.fetch_all_calls))
        self.assertEqual(
            repository.aggregate_calls[0]["scope_keys"],
            ["active:2026-04", "active:2026-05"],
        )

    def test_cost_statistics_sql_projection_rebuilds_all_all_as_first_class_read_model(self) -> None:
        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=CostStatisticsParentAggregationConnection(),
            read_model_repository=repository,
        )

        result = builder.rebuild_cost_statistics_read_model_scope(
            "all:all",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(result["scope_key"], "all:all")
        self.assertEqual(result["month"], "all")
        self.assertEqual(result["project_scope"], "all")
        self.assertEqual(repository.saved[0][1], {"all:all"})

    def test_cost_statistics_parent_rebuild_removes_obsolete_month_scopes(self) -> None:
        class Connection(CostStatisticsParentAggregationConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_generations" in normalized:
                    return [{"scope_key": "2026-05"}, {"scope_key": "2026-04"}]
                if "from read_model.cost_statistics_read_models" in normalized and "scope_key ~" in normalized:
                    return [
                        {"scope_key": "active:2026-05"},
                        {"scope_key": "active:2026-04"},
                        {"scope_key": "active:2023-05"},
                    ]
                return super().fetch_all(sql, params)

        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=Connection(),
            read_model_repository=repository,
        )

        builder.rebuild_cost_statistics_read_model_scope(
            "active:all",
            tenant_id="default",
            source_version=7,
        )

        self.assertEqual(repository.saved[0][1], {"active:all", "active:2023-05"})
        self.assertEqual(repository.publish_calls[0], ("default", "active:all", 7, {"active:all", "active:2023-05"}))

    def test_cost_statistics_parent_source_manifest_keeps_fresh_empty_month_shards(self) -> None:
        class Connection(CostStatisticsParentAggregationConnection):
            def fetch_all(self, sql: str, params: tuple = ()) -> list[dict]:
                normalized = " ".join(sql.lower().split())
                if "from read_model.cost_statistics_read_models" in normalized and "scope_key ~" not in normalized:
                    return [
                        {"scope_key": "active:2026-03", "source_versions": {"scope": "active:2026-03"}},
                        *super().fetch_all(sql, params),
                    ]
                return super().fetch_all(sql, params)

        repository = CostStatisticsSaveRecorder()
        builder = CostStatisticsSqlProjectionBuilder(
            connection=Connection(),
            read_model_repository=repository,
        )

        builder.rebuild_cost_statistics_read_model_scope(
            "active:all",
            tenant_id="default",
            source_version=7,
        )

        snapshot, _changed_scope_keys = repository.saved[0]
        source_versions = snapshot["read_models"]["active:all"]["source_versions"]
        self.assertEqual(source_versions["source_shard_count"], 3)
        self.assertEqual(source_versions["source_shards"]["active:2026-03"], {"scope": "active:2026-03"})

    def test_cost_statistics_access_parent_rebuild_does_not_fan_out_from_readiness(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt: list[str] = []

            def list_cost_statistics_scope_shards(self, scope_key: str) -> list[str]:
                raise AssertionError(f"normal parent refresh must not enumerate child shards: {scope_key}")

            def rebuild_cost_statistics_parent_scope(
                self,
                scope_key: str,
                *,
                tenant_id: str,
                source_version: int,
            ) -> dict[str, object]:
                self.asserted_tenant_id = tenant_id
                self.asserted_source_version = source_version
                self.rebuilt.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 2, "source_shard_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={
                "scope_key": "active:all",
                "source_version": 7,
                "reason": "api_statistics_stale",
            },
            attempts=1,
            status="processing",
            source_version=7,
            priority="high",
            trace_id="trace-cost-parent",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt, ["active:all"])
        self.assertEqual(builder.asserted_tenant_id, "tenant-a")
        self.assertEqual(builder.asserted_source_version, 7)
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:all", 7)])
        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["readiness_status"], "fresh")
        self.assertEqual(result["refresh_kind"], "parent")

    def test_cost_statistics_refresh_handler_publishes_parent_after_shards_converge(self) -> None:
        class FakeBuilder:
            def __init__(self) -> None:
                self.rebuilt_parent: list[str] = []

            def rebuild_cost_statistics_parent_scope(
                self,
                scope_key: str,
                *,
                tenant_id: str,
                source_version: int,
            ) -> dict[str, object]:
                self.asserted_tenant_id = tenant_id
                self.asserted_source_version = source_version
                self.rebuilt_parent.append(scope_key)
                return {"scope_key": scope_key, "entry_count": 2, "source_shard_count": 2}

        queue = QueueRecorder()
        builder = FakeBuilder()
        service = CostStatisticsReadModelRefreshService(projection_builder=builder, queue_repository=queue)
        event = RuntimeQueueEvent(
            event_id="event-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={
                "scope_key": "active:all",
                "source_version": 7,
                "reason": "cost_statistics_shard_converged",
            },
            attempts=1,
            status="processing",
            source_version=7,
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(builder.rebuilt_parent, ["active:all"])
        self.assertEqual(queue.refreshes, [])
        self.assertEqual(queue.completed, [("tenant-a", "cost_statistics", "active:all", 7)])
        self.assertEqual(result["scope_key"], "active:all")
        self.assertEqual(result["readiness_status"], "fresh")
        self.assertEqual(result["refresh_kind"], "parent")

    def test_cost_statistics_force_refresh_propagates_to_every_month_shard(self) -> None:
        class FakeBuilder:
            @staticmethod
            def list_cost_statistics_scope_shards(_scope_key: str) -> list[str]:
                return ["active:2026-05", "active:2026-04"]

        queue = QueueRecorder()
        service = CostStatisticsReadModelRefreshService(
            projection_builder=FakeBuilder(),
            queue_repository=queue,
        )
        event = RuntimeQueueEvent(
            event_id="event-force-all",
            tenant_id="tenant-a",
            event_type="cost_statistics.read_model.refresh",
            aggregate_type="read_model",
            aggregate_id="active:all",
            scope_type="cost_statistics",
            scope_key="active:all",
            dedupe_key=None,
            payload={
                "scope_key": "active:all",
                "source_version": 8,
                "metadata": {"force_refresh": True},
            },
            attempts=1,
            status="processing",
            priority="high",
            trace_id="trace-force-cost",
        )

        result = service.handle_runtime_event(event)

        self.assertEqual(
            result["enqueued_scope_keys"],
            ["active:2026-05", "active:2026-04"],
        )
        self.assertEqual(
            [item.get("metadata") for item in queue.refresh_details],
            [{"force_refresh": True}, {"force_refresh": True}],
        )
        self.assertEqual(queue.completed, [])

    def test_cost_statistics_invalidation_marks_dirty_even_when_no_cached_model_exists(self) -> None:
        queue = QueueRecorder()
        redis = RedisRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type(
            "RuntimeRepos",
            (),
            {"queue_repository": queue, "redis_helper": redis},
        )()

        invalidated = app._cost_statistics_runtime().invalidate_read_model_scopes(
            ["2026-05"],
            reason="unit_test",
        )

        self.assertEqual(invalidated, ["active:2026-05", "all:2026-05"])
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
            ],
        )
        self.assertEqual(redis.deletes, [])

    def test_generic_cost_statistics_enqueue_expands_month_scopes(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._cost_statistics_workbench_dependency_versions = _fresh_workbench_dependency_versions
        app._cost_statistics_workbench_dependency_versions_by_scope = (
            _fresh_workbench_dependency_versions_by_scope
        )
        app._app_settings_service = CostStatisticsAppSettingsStub()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        enqueued = app._enqueue_generic_read_model_refreshes(
            "cost_statistics",
            ["2026-05", "all"],
            reason="unit_test",
        )

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.refreshes,
            [
                ("cost_statistics", "active:2026-05", "unit_test"),
                ("cost_statistics", "all:2026-05", "unit_test"),
                ("cost_statistics", "active:all", "unit_test"),
                ("cost_statistics", "all:all", "unit_test"),
            ],
        )


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import hashlib
import json
import os
from typing import Any


WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION = "2026-07-14-formalized-decision-origin-visibility"


def normalize_workbench_group_search_mode(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    return "linked_context" if normalized == "linked_context" else "pane"


def normalize_workbench_group_detail_level(value: str | None) -> str:
    normalized = str(value or "full").strip().lower()
    return "summary" if normalized == "summary" else "full"


def stable_json_value(value: object) -> object:
    if isinstance(value, dict):
        return {
            str(key): stable_json_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
            if value[key] is not None
        }
    if isinstance(value, list):
        normalized_items = [stable_json_value(item) for item in value]
        if all(not isinstance(item, (dict, list)) for item in normalized_items):
            return sorted(normalized_items, key=lambda item: json.dumps(item, ensure_ascii=False, sort_keys=True))
        return normalized_items
    return value


def workbench_groups_redis_version_key(scope_key: str) -> str:
    safe_scope_key = str(scope_key or "all").strip() or "all"
    return f"workbench:groups:version:{safe_scope_key}"


def workbench_groups_redis_cache_version_from_key(cache_key: str) -> str | None:
    parts = str(cache_key or "").split(":")
    if len(parts) >= 3 and parts[0] == "workbench" and parts[2] == "groups":
        return parts[1]
    return None


def _workbench_groups_cache_version_token(cache_version: str) -> str:
    return hashlib.sha256(str(cache_version).encode("utf-8")).hexdigest()[:24]


def build_workbench_groups_redis_cache_key_from_version(
    *,
    cache_version: str | None,
    scope_key: str,
    zone: str,
    page: str | None,
    page_size: str | None,
    status: str | None,
    source_kind: str | None,
    search: str | None,
    search_mode: str | None = None,
    search_by_pane: dict[str, object] | None = None,
    sort: str | None,
    detail_level: str | None,
    column_filters: dict[str, object] | None = None,
    time_filters: dict[str, object] | None = None,
    schema_version: str = WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION,
) -> str | None:
    if not cache_version:
        return None
    version_token = _workbench_groups_cache_version_token(str(cache_version))
    key_payload = {
        "workbench_read_model_schema_version": schema_version,
        "scope": scope_key,
        "zone": zone,
        "page": page or "1",
        "page_size": page_size or "50",
        "status": status or "",
        "source_kind": source_kind or "",
        "search": search or "",
        "search_mode": normalize_workbench_group_search_mode(search_mode),
        "search_by_pane": stable_json_value(search_by_pane or {}),
        "sort": sort or "",
        "detail_level": normalize_workbench_group_detail_level(detail_level),
        "column_filters": stable_json_value(column_filters or {}),
        "time_filters": stable_json_value(time_filters or {}),
        "filter_semantics": "linked_context_v1",
    }
    digest = hashlib.sha256(json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"workbench:{version_token}:groups:{digest}"


def workbench_groups_redis_ttl_seconds_from_env() -> int:
    raw_value = os.getenv("FIN_OPS_WORKBENCH_GROUPS_REDIS_TTL_SECONDS", "600").strip()
    try:
        return min(900, max(60, int(raw_value)))
    except ValueError:
        return 600


def workbench_groups_sync_cache_warmup_enabled_from_env() -> bool:
    return str(os.getenv("FIN_OPS_WORKBENCH_GROUPS_SYNC_CACHE_WARMUP_ENABLED", "") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class WorkbenchGroupsPageCacheWarmer:
    def __init__(
        self,
        *,
        repository: object | None,
        redis_helper: object | None,
        schema_version: str = WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION,
        ttl_seconds: int = 600,
        zones: tuple[str, ...] = ("paired", "open"),
        page_size: int = 200,
    ) -> None:
        self._repository = repository
        self._redis_helper = redis_helper
        self._schema_version = schema_version
        self._ttl_seconds = ttl_seconds
        self._zones = zones
        self._page_size = page_size

    def warm_scope(self, scope_key: str) -> dict[str, Any]:
        safe_scope_key = str(scope_key or "all").strip() or "all"
        set_text = getattr(self._redis_helper, "set_text", None)
        set_json = getattr(self._redis_helper, "set_json", None)
        get_cache_version = getattr(self._repository, "workbench_groups_cache_version", None)
        get_page = getattr(self._repository, "get_workbench_groups_page", None)
        if not callable(set_text) or not callable(set_json) or not callable(get_cache_version) or not callable(get_page):
            return {
                "status": "skipped",
                "scope_key": safe_scope_key,
                "reason": "cache_dependency_unavailable",
                "warmed_pages": 0,
                "skipped_pages": len(self._zones),
            }
        cache_version = get_cache_version(scope_key=safe_scope_key)
        if not cache_version:
            return {
                "status": "skipped",
                "scope_key": safe_scope_key,
                "reason": "cache_version_unavailable",
                "warmed_pages": 0,
                "skipped_pages": len(self._zones),
            }
        ttl_seconds = int(self._ttl_seconds)
        set_text(workbench_groups_redis_version_key(safe_scope_key), str(cache_version), ttl_seconds=ttl_seconds)
        warmed_pages = 0
        skipped_pages = 0
        for zone in self._zones:
            page_payload = get_page(
                scope_key=safe_scope_key,
                zone=zone,
                page=1,
                page_size=self._page_size,
                status=None,
                source_kind=None,
                search=None,
                search_mode="pane",
                search_by_pane={},
                sort=None,
                detail_level="summary",
                column_filters={},
                time_filters={},
            )
            if not isinstance(page_payload, dict) or page_payload.get("read_model_status") != "fresh":
                skipped_pages += 1
                continue
            cache_key = build_workbench_groups_redis_cache_key_from_version(
                cache_version=str(cache_version),
                schema_version=self._schema_version,
                scope_key=safe_scope_key,
                zone=zone,
                page="1",
                page_size=str(self._page_size),
                status=None,
                source_kind=None,
                search=None,
                search_mode="pane",
                search_by_pane={},
                sort=None,
                detail_level="summary",
                column_filters={},
                time_filters={},
            )
            if cache_key:
                set_json(cache_key, {"payload": page_payload}, ttl_seconds=ttl_seconds)
                warmed_pages += 1
            else:
                skipped_pages += 1
        return {
            "status": "warmed" if warmed_pages else "skipped",
            "scope_key": safe_scope_key,
            "cache_version": str(cache_version),
            "warmed_pages": warmed_pages,
            "skipped_pages": skipped_pages,
        }

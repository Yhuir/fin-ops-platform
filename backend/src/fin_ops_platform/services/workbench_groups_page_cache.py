from __future__ import annotations

import hashlib
import json
import os

from fin_ops_platform.services.workbench_read_model_version import WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION


WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION = f"{WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION}:relation-completion-v1"
WORKBENCH_INITIAL_PAGE_CACHE_SCHEMA_VERSION = f"{WORKBENCH_GROUPS_PAGE_CACHE_SCHEMA_VERSION}:initial-v2"


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


def is_default_workbench_initial_query(
    paired_query: dict[str, object] | None,
    unpaired_query: dict[str, object] | None,
) -> bool:
    for query in (paired_query, unpaired_query):
        if not isinstance(query, dict):
            continue
        for key, value in query.items():
            if value in (None, "", [], {}):
                continue
            if key == "search_mode" and normalize_workbench_group_search_mode(str(value)) == "pane":
                continue
            return False
    return True


def build_workbench_initial_redis_cache_key(
    *,
    cache_version: str | None,
    scope_key: str,
    schema_version: str = WORKBENCH_INITIAL_PAGE_CACHE_SCHEMA_VERSION,
) -> str | None:
    if not cache_version:
        return None
    version_token = _workbench_groups_cache_version_token(str(cache_version))
    key_payload = {
        "workbench_read_model_schema_version": schema_version,
        "scope": str(scope_key or "all").strip() or "all",
        "page": 1,
        "page_size": 200,
        "detail_level": "summary",
        "query": "default",
    }
    digest = hashlib.sha256(json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"workbench:{version_token}:initial:{digest}"


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
        "filter_semantics": "linked_context_scalar_multiselect_or_v2",
    }
    digest = hashlib.sha256(json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    return f"workbench:{version_token}:groups:{digest}"


def workbench_groups_redis_ttl_seconds_from_env() -> int:
    raw_value = os.getenv("FIN_OPS_WORKBENCH_GROUPS_REDIS_TTL_SECONDS", "600").strip()
    try:
        return min(900, max(60, int(raw_value)))
    except ValueError:
        return 600

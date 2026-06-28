from __future__ import annotations


def normalize_workbench_group_detail_level(value: str | None) -> str:
    normalized = str(value or "full").strip().lower()
    return "summary" if normalized == "summary" else "full"


def workbench_groups_redis_version_key(scope_key: str) -> str:
    safe_scope_key = str(scope_key or "all").strip() or "all"
    return f"workbench:groups:version:{safe_scope_key}"

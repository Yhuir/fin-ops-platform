from __future__ import annotations

import re
from typing import Any


WORKBENCH_ETC_BATCH_LINK_VERSION = "workbench-etc-batch-link-v6"


def workbench_etc_summary_row_id(external_batch_id: str) -> str:
    """Return the single canonical Workbench member id for one ETC batch."""
    safe_batch_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(external_batch_id or "")).strip("-")
    return f"etc-summary-{safe_batch_id or 'unknown'}"


def relation_external_etc_batch_ids(relation: dict[str, Any]) -> frozenset[str]:
    """Return every durable ETC batch marker shape without silently choosing a winner."""
    values: set[str] = set()
    amount_check = relation.get("amount_check")
    if isinstance(amount_check, dict):
        for key in ("external_etc_batch_id", "etc_batch_id"):
            value = str(amount_check.get(key) or "").strip()
            if value:
                values.add(value)

    special_metadata = relation.get("special_metadata")
    if not isinstance(special_metadata, dict):
        return frozenset(values)
    for key in ("external_etc_batch_id", "etc_batch_id"):
        value = str(special_metadata.get(key) or "").strip()
        if value:
            values.add(value)
    for nested_key in ("etc_batch_link", "historical_etc_business_batch_migration"):
        nested = special_metadata.get(nested_key)
        if not isinstance(nested, dict):
            continue
        value = str(nested.get("external_etc_batch_id") or nested.get("etc_batch_id") or "").strip()
        if value:
            values.add(value)
    return frozenset(values)


def relation_external_etc_batch_id(relation: dict[str, Any]) -> str:
    """Resolve one owner only when all current and legacy marker shapes agree."""
    values = relation_external_etc_batch_ids(relation)
    return next(iter(values)) if len(values) == 1 else ""

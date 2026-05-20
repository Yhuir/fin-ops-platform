from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION
from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_SCHEMA_VERSION
from fin_ops_platform.services.turnover_relation_service import TURNOVER_RELATION_SCHEMA_VERSION


def normalize_app_health_alerts(rows_by_id: dict[str, Any] | None) -> dict[str, Any]:
    records: dict[str, Any] = {}
    for row_id, payload in (rows_by_id or {}).items():
        if isinstance(payload, dict) and isinstance(payload.get("records"), dict):
            records.update({str(key): value for key, value in payload["records"].items()})
            continue
        records[str(row_id)] = payload
    return {"records": records}


def normalize_workbench_pair_relations(
    pair_relations: dict[str, Any] | None,
    history: list[Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    relation_payload = pair_relations if isinstance(pair_relations, dict) else source.get("pair_relations")
    history_payload = history if isinstance(history, list) else source.get("pair_relation_history")
    return {
        "pair_relations": dict(relation_payload) if isinstance(relation_payload, dict) else {},
        "pair_relation_history": expand_wrapped_events(history_payload, "pair_relation_history"),
    }


def normalize_no_oa_bank_batches(
    batches: dict[str, Any] | None,
    audit_log: list[Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    batch_payload = batches if isinstance(batches, dict) else source.get("batches")
    audit_payload = audit_log if isinstance(audit_log, list) else source.get("audit_log")
    return {
        **_metadata_without(source, {"batches", "audit_log"}),
        "schema_version": source.get("schema_version") or NO_OA_BANK_BATCH_SCHEMA_VERSION,
        "batches": dict(batch_payload) if isinstance(batch_payload, dict) else {},
        "audit_log": expand_wrapped_events(audit_payload, "audit_log"),
    }


def normalize_bank_transaction_categories(
    categories: dict[str, Any] | None,
    audit_log: list[Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    source_categories = source.get("categories") if isinstance(source.get("categories"), dict) else {}
    merged_categories = dict(source_categories)
    if isinstance(categories, dict):
        merged_categories.update(categories)
    audit_payload = audit_log if isinstance(audit_log, list) else source.get("audit_log")
    return {
        **_metadata_without(source, {"categories", "audit_log"}),
        "schema_version": source.get("schema_version") or BANK_TRANSACTION_CATEGORY_SCHEMA_VERSION,
        "categories": merged_categories,
        "audit_log": expand_wrapped_events(audit_payload, "audit_log"),
    }


def normalize_turnover_relations(
    relations: list[Any] | None,
    audit_log: list[Any] | None,
    *,
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    source = snapshot if isinstance(snapshot, dict) else {}
    source_relations = source.get("relations") if isinstance(source.get("relations"), (dict, list)) else []
    relation_payload = relations if isinstance(relations, list) else source_relations
    normalized_relations: Any
    if isinstance(relation_payload, dict):
        normalized_relations = dict(relation_payload)
    else:
        normalized_relations = [item for item in relation_payload if isinstance(item, dict)]
    audit_payload = audit_log if isinstance(audit_log, list) else source.get("audit_log")
    return {
        **_metadata_without(source, {"relations", "audit_log"}),
        "schema_version": source.get("schema_version") or TURNOVER_RELATION_SCHEMA_VERSION,
        "relations": normalized_relations,
        "audit_log": expand_wrapped_events(audit_payload, "audit_log"),
    }


def expand_wrapped_events(items: Any, wrapper_key: str) -> list[Any]:
    if not isinstance(items, list):
        return []
    events: list[Any] = []
    for item in items:
        if isinstance(item, dict) and isinstance(item.get(wrapper_key), list):
            events.extend(child for child in item[wrapper_key] if isinstance(child, dict))
            continue
        if isinstance(item, dict):
            events.append(item)
    return events


def _metadata_without(source: dict[str, Any], keys: set[str]) -> dict[str, Any]:
    return {str(key): value for key, value in source.items() if key not in keys}

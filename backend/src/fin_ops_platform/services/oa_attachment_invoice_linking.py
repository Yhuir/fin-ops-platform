from __future__ import annotations

from typing import Any


OA_SOURCE_ALIAS_FIELD_NAMES = (
    "id",
    "row_id",
    "oa_row_id",
    "oa_id",
    "source_oa_row_id",
    "object_identity_key",
    "Mongo文档ID",
    "mongo_document_id",
    "document_id",
    "_id",
    "OA单号",
    "流程请求ID",
    "oa_number",
    "request_id",
    "external_id",
)


def oa_attachment_parent_oa_id(source_id: object) -> str:
    value = str(source_id or "").strip()
    if not value:
        return ""
    marker = ":item:"
    if marker in value:
        return value.split(marker, 1)[0]
    return value


def oa_attachment_source_ids(row: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    for field_name in (
        "source_workbench_row_id",
        "derived_from_oa_id",
        "source_expense_item_id",
        "oa_row_id",
        "oa_id",
        "source_oa_row_id",
        "linked_oa_row_id",
        "parent_oa_row_id",
    ):
        value = str(row.get(field_name) or "").strip()
        if value:
            source_ids.append(value)
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        for field_name in (
            "source_workbench_row_id",
            "derived_from_oa_id",
            "source_expense_item_id",
            "source_oa_row_id",
            "oa_row_id",
            "oa_id",
        ):
            value = str(metadata.get(field_name) or "").strip()
            if value:
                source_ids.append(value)
    return _dedupe(source_ids)


def oa_row_source_ids(row: dict[str, Any]) -> list[str]:
    source_ids: list[str] = []
    identity_values: list[str] = []
    for field_name in (
        "canonical_object_identity",
        "id",
        "row_id",
        "oa_row_id",
        "oa_id",
        "source_oa_row_id",
        "object_identity_key",
    ):
        value = str(row.get(field_name) or "").strip()
        if value:
            source_ids.append(value)
            identity_values.append(value)

    raw_source_aliases = row.get("source_aliases")
    source_aliases = raw_source_aliases if isinstance(raw_source_aliases, (list, tuple, set)) else ()
    for source_alias in source_aliases:
        parent_alias = oa_attachment_parent_oa_id(source_alias)
        if not parent_alias:
            continue
        source_ids.append(parent_alias)
        for prefix in ("oa-exp-", "oa-pay-"):
            if parent_alias.startswith(prefix) and len(parent_alias) > len(prefix):
                source_ids.append(parent_alias[len(prefix):])

    payload = row.get("normalized_payload")
    containers = [row, payload] if isinstance(payload, dict) else [row]
    prefixes = {
        prefix
        for value in identity_values
        for prefix in ("oa-exp", "oa-pay")
        if value.startswith(f"{prefix}-")
    } or {"oa-exp"}
    for parent in containers:
        for field_name in ("oa_row_id", "oa_id", "source_oa_row_id", "object_identity_key"):
            value = str(parent.get(field_name) or "").strip()
            if value:
                source_ids.append(value)
        for container_name in ("detail_fields", "summary_fields", "metadata"):
            container = parent.get(container_name)
            if not isinstance(container, dict):
                continue
            _append_external_oa_ids(source_ids, container, prefixes=prefixes)
        _append_external_oa_ids(source_ids, parent, prefixes=prefixes)

    return _dedupe(source_ids)


def oa_row_source_alias_map(rows: list[dict[str, Any]]) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for row in rows:
        canonical = str(
            row.get("canonical_object_identity")
            or row.get("id")
            or row.get("row_id")
            or ""
        ).strip()
        if not canonical:
            raise ValueError("Canonical OA row identity is required for source alias mapping.")
        for alias in oa_row_source_ids(row):
            prior = aliases.setdefault(alias, canonical)
            if prior != canonical:
                raise ValueError(
                    f"OA source alias {alias} resolves to multiple canonical rows: {prior},{canonical}."
                )
    return aliases


def canonical_oa_expense_item_id(
    *,
    oa_row: dict[str, Any],
    invoice_row: dict[str, Any],
) -> str:
    source_item_id = _first_field_value(invoice_row, "source_expense_item_id")
    if not source_item_id:
        return ""
    if oa_attachment_parent_oa_id(source_item_id) not in set(oa_row_source_ids(oa_row)):
        return ""

    source_row_index = _first_field_value(invoice_row, "source_expense_row_index")
    if not source_row_index:
        parts = source_item_id.split(":item:", 1)
        source_row_index = parts[1].split(":", 1)[0] if len(parts) == 2 else ""
    if not source_row_index:
        return ""

    matches = {
        str(item.get("id") or item.get("expense_item_id") or "").strip()
        for item in list(oa_row.get("expense_items") or [])
        if isinstance(item, dict)
        and str(item.get("row_index") if item.get("row_index") is not None else "").strip()
        == source_row_index
        and str(item.get("id") or item.get("expense_item_id") or "").strip()
    }
    return next(iter(matches)) if len(matches) == 1 else ""


def _append_external_oa_ids(
    source_ids: list[str],
    container: dict[str, Any],
    *,
    prefixes: set[str],
) -> None:
    for field_name in ("Mongo文档ID", "mongo_document_id", "document_id", "_id"):
        value = str(container.get(field_name) or "").strip()
        if value:
            source_ids.append(value)
            source_ids.extend(f"{prefix}-{value}" for prefix in prefixes)
    for field_name in ("OA单号", "流程请求ID", "oa_number", "request_id", "external_id"):
        value = str(container.get(field_name) or "").strip()
        if value:
            source_ids.append(value)
            source_ids.extend(f"{prefix}-{value}" for prefix in prefixes)


def _first_field_value(row: dict[str, Any], field_name: str) -> str:
    for container in (
        row,
        row.get("detail_fields"),
        row.get("metadata"),
    ):
        if not isinstance(container, dict):
            continue
        value = str(container.get(field_name) or "").strip()
        if value:
            return value
    return ""


def oa_attachment_matches_oa(row: dict[str, Any], oa_row_id: object) -> bool:
    normalized_oa_row_id = str(oa_row_id or "").strip()
    if not normalized_oa_row_id:
        return False
    for source_id in oa_attachment_source_ids(row):
        if source_id == normalized_oa_row_id or oa_attachment_parent_oa_id(source_id) == normalized_oa_row_id:
            return True
    row_id = str(row.get("id") or "").strip()
    return oa_attachment_row_id_matches_oa(row_id, normalized_oa_row_id)


def oa_attachment_row_id_matches_oa(row_id: object, oa_row_id: object) -> bool:
    normalized_row_id = str(row_id or "").strip()
    normalized_oa_row_id = str(oa_row_id or "").strip()
    if not normalized_row_id or not normalized_oa_row_id:
        return False
    prefix = "oa-att-inv-"
    if not normalized_row_id.startswith(prefix):
        return False
    tail = normalized_row_id[len(prefix):]
    return tail == normalized_oa_row_id or tail.startswith(f"{normalized_oa_row_id}-")


def oa_attachment_best_source_link(
    source_links: list[dict[str, Any]],
    source_type: str,
    *,
    oa_row_ids: set[str] | None = None,
) -> dict[str, Any] | None:
    matching_links = [
        source_link
        for source_link in source_links
        if str(source_link.get("source_type") or "").strip() == source_type
    ]
    if not matching_links:
        return None
    if oa_row_ids:
        for source_link in matching_links:
            link_row = {
                "id": source_link.get("source_workbench_row_id"),
                "source_workbench_row_id": source_link.get("source_workbench_row_id"),
                "derived_from_oa_id": source_link.get("derived_from_oa_id"),
                "source_expense_item_id": source_link.get("source_expense_item_id"),
            }
            if any(oa_attachment_matches_oa(link_row, oa_row_id) for oa_row_id in oa_row_ids):
                return source_link
    for source_link in matching_links:
        if oa_attachment_source_ids(source_link) or str(source_link.get("source_workbench_row_id") or "").strip():
            return source_link
    return matching_links[0]


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result

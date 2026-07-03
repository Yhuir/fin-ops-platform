from __future__ import annotations

from typing import Any


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
    for field_name in ("id", "row_id", "oa_row_id", "oa_id", "source_oa_row_id", "object_identity_key"):
        value = str(row.get(field_name) or "").strip()
        if value:
            source_ids.append(value)

    for container_name in ("detail_fields", "summary_fields", "metadata"):
        container = row.get(container_name)
        if not isinstance(container, dict):
            continue
        for field_name in ("Mongo文档ID", "mongo_document_id", "document_id", "_id"):
            value = str(container.get(field_name) or "").strip()
            if value:
                source_ids.append(value)
                source_ids.append(f"oa-exp-{value}")
        for field_name in ("OA单号", "流程请求ID", "oa_number", "request_id", "external_id"):
            value = str(container.get(field_name) or "").strip()
            if value:
                source_ids.append(value)
                source_ids.append(f"oa-exp-{value}")

    return _dedupe(source_ids)


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

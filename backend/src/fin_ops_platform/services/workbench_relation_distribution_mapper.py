from __future__ import annotations

from copy import deepcopy
from typing import Any


def relation_dicts_from_distribution_payload(payload: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    relations: list[dict[str, Any]] = []
    for group in list(payload.get("groups") or []):
        if not isinstance(group, dict):
            continue
        relation = relation_dict_from_distribution_group(group)
        if relation is not None:
            relations.append(relation)
    return relations


def relation_dict_from_distribution_group(group: dict[str, Any]) -> dict[str, Any] | None:
    group_id = _text(group.get("group_id") or group.get("case_id"))
    if not group_id:
        return None
    payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
    row_ids = _text_list(payload.get("row_ids"))
    row_types = _text_list(payload.get("row_types"))
    if not row_ids:
        typed_rows = [
            *[(row_id, "oa") for row_id in _text_list(group.get("oa_row_ids"))],
            *[(row_id, "bank") for row_id in _text_list(group.get("bank_transaction_ids"))],
            *[(row_id, "invoice") for row_id in _text_list(group.get("input_invoice_ids"))],
            *[(row_id, "invoice") for row_id in _text_list(group.get("output_invoice_ids"))],
        ]
        row_ids = [row_id for row_id, _row_type in typed_rows]
        row_types = [row_type for _row_id, row_type in typed_rows]
    if len(row_types) < len(row_ids):
        row_types = [*row_types, *["" for _ in range(len(row_ids) - len(row_types))]]
    return {
        "case_id": group_id,
        "relation_mode": _text(payload.get("relation_mode")),
        "status": "active",
        "month_scope": _text(group.get("scope_month") or group.get("scope_key")),
        "row_ids": row_ids,
        "row_types": row_types,
        "amount_check": deepcopy(payload.get("amount_check")) if isinstance(payload.get("amount_check"), dict) else {},
        "special_metadata": deepcopy(payload.get("special_metadata")) if isinstance(payload.get("special_metadata"), dict) else {},
        "source_versions": deepcopy(payload.get("source_versions")) if isinstance(payload.get("source_versions"), dict) else {},
        "note": _text(payload.get("note")),
        "raw_payload": deepcopy(payload),
    }


def relation_dicts_by_row_id_from_distribution_payload(payload: dict[str, Any] | None) -> dict[str, list[dict[str, Any]]]:
    relations = relation_dicts_from_distribution_payload(payload)
    groups_by_id = {_text(relation.get("case_id")): relation for relation in relations if _text(relation.get("case_id"))}
    result: dict[str, list[dict[str, Any]]] = {}
    for row in list((payload or {}).get("rows") or []):
        if not isinstance(row, dict):
            continue
        row_id = _text(row.get("row_id"))
        if not row_id:
            continue
        result.setdefault(row_id, [])
        for group_id in _text_list(row.get("group_ids")):
            relation = groups_by_id.get(group_id)
            if relation is not None and all(_text(existing.get("case_id")) != group_id for existing in result[row_id]):
                result[row_id].append(relation)
    for relation in relations:
        for row_id in _text_list(relation.get("row_ids")):
            result.setdefault(row_id, [])
            case_id = _text(relation.get("case_id"))
            if case_id and all(_text(existing.get("case_id")) != case_id for existing in result[row_id]):
                result[row_id].append(relation)
    return result


def _text(value: Any) -> str:
    return str(value or "").strip()


def _text_list(value: Any) -> list[str]:
    return [_text(item) for item in list(value or []) if _text(item)]

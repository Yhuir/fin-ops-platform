from __future__ import annotations

from typing import Any, Iterable


COST_LINKED_RELATION_CODES = frozenset({"fully_linked", "automatic_match"})


def is_candidate_workbench_group(group: dict[str, Any]) -> bool:
    if _relation_status(group) == "candidate":
        return True
    if any(_relation_status(row) == "candidate" for row in _iter_group_rows(group)):
        return True
    if _is_linked_cost_open_group(group):
        return False
    return _clean_text(group.get("group_type")).lower() == "candidate"


def is_cost_eligible_open_group(group: dict[str, Any]) -> bool:
    if is_candidate_workbench_group(group):
        return False
    if _is_linked_cost_open_group(group):
        return True
    for row in list(group.get("bank_rows") or []):
        if not isinstance(row, dict):
            continue
        actions = {
            str(action).strip()
            for action in list(row.get("available_actions") or [])
            if str(action).strip()
        }
        if "cancel_link" in actions:
            return True
    return False


def _is_linked_cost_open_group(group: dict[str, Any]) -> bool:
    for row in list(group.get("oa_rows") or []):
        if not isinstance(row, dict):
            continue
        relation = row.get("oa_bank_relation")
        if isinstance(relation, dict) and _clean_text(relation.get("code")) in COST_LINKED_RELATION_CODES:
            return True
    return False


def _iter_group_rows(group: dict[str, Any]) -> Iterable[dict[str, Any]]:
    for collection_key in ("oa_rows", "bank_rows", "invoice_rows"):
        for row in list(group.get(collection_key) or []):
            if isinstance(row, dict):
                yield row


def _relation_status(payload: dict[str, Any]) -> str:
    for key in ("relation_status", "relationStatus", "status"):
        value = _clean_text(payload.get(key)).lower()
        if value:
            return value
    return ""


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in {"-", "--", "—", "——"} else text

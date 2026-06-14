from __future__ import annotations

from copy import deepcopy
from typing import Any


VALID_WORKBENCH_RELATION_MODES = frozenset(
    {
        "manual_confirmed",
        "normal_match",
        "oa_exempt",
        "pending_invoice_attach_existing_invoice",
        "pending_invoice_attach_existing",
        "pending_invoice_manual_invoice",
        "no_oa_bank_batch",
        "turnover_manual_closure",
        "batch_accounting",
        "etc_business_batch",
        "etc_historical_repair",
        "etc_batch_invoice_link",
        "input_invoice_oa_reverse",
        "personal_advance_repayment_settlement",
        "oa_invoice_offset_auto_match",
    }
)

DISPLAY_ONLY_WORKBENCH_RELATION_MODES = frozenset({"existing_case"})
WORKBENCH_RELATION_RESTORABLE_ON_WITHDRAW = "restorable_on_withdraw"


def relation_has_withdraw_restore_marker(relation: Any) -> bool:
    if not isinstance(relation, dict):
        return False
    if relation.get(WORKBENCH_RELATION_RESTORABLE_ON_WITHDRAW) is True:
        return True
    special_metadata = relation.get("special_metadata")
    return (
        isinstance(special_metadata, dict)
        and special_metadata.get(WORKBENCH_RELATION_RESTORABLE_ON_WITHDRAW) is True
    )


def mark_relation_restorable_on_withdraw(relation: dict[str, Any]) -> dict[str, Any]:
    marked = deepcopy(relation)
    special_metadata = marked.get("special_metadata")
    if not isinstance(special_metadata, dict):
        special_metadata = {}
    marked["special_metadata"] = {
        **deepcopy(special_metadata),
        WORKBENCH_RELATION_RESTORABLE_ON_WITHDRAW: True,
    }
    return marked


def workbench_relation_row_id_set(relation: Any) -> frozenset[str]:
    if not isinstance(relation, dict):
        return frozenset()
    return frozenset(
        str(row_id).strip()
        for row_id in list(relation.get("row_ids") or [])
        if str(row_id).strip()
    )


def workbench_relations_have_same_row_set(left: Any, right: Any) -> bool:
    left_row_ids = workbench_relation_row_id_set(left)
    right_row_ids = workbench_relation_row_id_set(right)
    return bool(left_row_ids) and left_row_ids == right_row_ids


def relation_mode_can_be_restored_on_withdraw(relation_mode: str) -> bool:
    mode = str(relation_mode or "").strip()
    return mode in VALID_WORKBENCH_RELATION_MODES or mode in DISPLAY_ONLY_WORKBENCH_RELATION_MODES


def is_workbench_relation_snapshot_restorable(
    relation: Any,
    *,
    active_relation: dict[str, Any] | None = None,
) -> bool:
    if not isinstance(relation, dict):
        return False
    if active_relation is not None and workbench_relations_have_same_row_set(relation, active_relation):
        return False
    if not relation_has_withdraw_restore_marker(relation):
        return False
    relation_mode = str(relation.get("relation_mode") or "").strip()
    return relation_mode_can_be_restored_on_withdraw(relation_mode)

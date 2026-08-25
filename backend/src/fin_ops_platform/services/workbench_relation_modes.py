from __future__ import annotations

from copy import deepcopy
from typing import Any


MANUAL_CONFIRMED_RELATION_MODE = "manual_confirmed"
TURNOVER_MANUAL_CLOSURE_RELATION_MODE = "turnover_manual_closure"
OUTPUT_INVOICE_REVERSAL_RELATION_MODE = "output_invoice_reversal"


VALID_WORKBENCH_RELATION_MODES = frozenset(
    {
        MANUAL_CONFIRMED_RELATION_MODE,
        "normal_match",
        "oa_exempt",
        "pending_invoice_attach_existing_invoice",
        "pending_invoice_attach_existing",
        "pending_invoice_manual_invoice",
        "no_oa_bank_batch",
        "bank_flow_rule_batch",
        TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
        "batch_accounting",
        "etc_business_batch",
        "etc_historical_repair",
        "etc_batch_invoice_link",
        "input_invoice_oa_reverse",
        "personal_advance_repayment_settlement",
        "oa_invoice_offset_auto_match",
        OUTPUT_INVOICE_REVERSAL_RELATION_MODE,
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


def _canonical_workbench_relation_row_id(row_id: Any, row_id_aliases: dict[str, str] | None) -> str:
    value = str(row_id).strip()
    if not value or not row_id_aliases:
        return value
    seen = {value}
    current = value
    while True:
        candidate = str(row_id_aliases.get(current, current)).strip()
        if not candidate or candidate == current or candidate in seen:
            return current
        seen.add(candidate)
        current = candidate


def workbench_relation_row_id_set(
    relation: Any,
    *,
    row_id_aliases: dict[str, str] | None = None,
) -> frozenset[str]:
    if not isinstance(relation, dict):
        return frozenset()
    return frozenset(
        _canonical_workbench_relation_row_id(row_id, row_id_aliases)
        for row_id in list(relation.get("row_ids") or [])
        if str(row_id).strip()
    )


def workbench_relations_have_same_row_set(
    left: Any,
    right: Any,
    *,
    row_id_aliases: dict[str, str] | None = None,
) -> bool:
    left_row_ids = workbench_relation_row_id_set(left, row_id_aliases=row_id_aliases)
    right_row_ids = workbench_relation_row_id_set(right, row_id_aliases=row_id_aliases)
    return bool(left_row_ids) and left_row_ids == right_row_ids


def relation_mode_can_be_restored_on_withdraw(relation_mode: str) -> bool:
    mode = str(relation_mode or "").strip()
    return mode in VALID_WORKBENCH_RELATION_MODES or mode in DISPLAY_ONLY_WORKBENCH_RELATION_MODES


def is_workbench_relation_snapshot_restorable(
    relation: Any,
    *,
    active_relation: dict[str, Any] | None = None,
    row_id_aliases: dict[str, str] | None = None,
) -> bool:
    if not isinstance(relation, dict):
        return False
    if (
        active_relation is not None
        and workbench_relations_have_same_row_set(
            relation,
            active_relation,
            row_id_aliases=row_id_aliases,
        )
    ):
        return False
    if not relation_has_withdraw_restore_marker(relation):
        return False
    relation_mode = str(relation.get("relation_mode") or "").strip()
    return relation_mode_can_be_restored_on_withdraw(relation_mode)

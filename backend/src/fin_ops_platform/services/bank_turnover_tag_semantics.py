from __future__ import annotations

from typing import Any


EXTERNAL_TURNOVER_CATEGORY_CODE = "external_turnover"
EXTERNAL_TURNOVER_ROLE = "external_turnover"

EXTERNAL_TURNOVER_PAYMENT_LABEL = "外部往来款付款"
EXTERNAL_TURNOVER_RECEIPT_LABEL = "外部往来款收款"
LEGACY_EXTERNAL_TURNOVER_PAYMENT_LABEL = "往来款付款"
LEGACY_EXTERNAL_TURNOVER_RECEIPT_LABEL = "往来款收款"

EXTERNAL_TURNOVER_PRIMARY_LABELS = {
    EXTERNAL_TURNOVER_PAYMENT_LABEL,
    EXTERNAL_TURNOVER_RECEIPT_LABEL,
    LEGACY_EXTERNAL_TURNOVER_PAYMENT_LABEL,
    LEGACY_EXTERNAL_TURNOVER_RECEIPT_LABEL,
}

EXTERNAL_TURNOVER_THIRD_LABELS = ("个人往来", "公司往来", "银行往来", "业务往来")
EXTERNAL_TURNOVER_THIRD_LABEL_OPTIONS = tuple(
    {"value": label, "label": label}
    for label in EXTERNAL_TURNOVER_THIRD_LABELS
)

TURNOVER_FAMILY_BY_THIRD_LABEL = {
    "个人往来": "personal",
    "公司往来": "company",
    "银行往来": "bank",
    "业务往来": "business",
}

TURNOVER_ACTION_TYPE_OPTIONS = (
    {
        "value": "pending_collection",
        "label": "待收款",
        "expected_direction": "outflow",
        "business_type": "borrow_out",
        "side": "principal",
        "direction_semantics": "borrow_out_principal",
    },
    {
        "value": "collected",
        "label": "已收款",
        "expected_direction": "inflow",
        "business_type": "borrow_out",
        "side": "settlement",
        "direction_semantics": "borrow_out_collection",
    },
    {
        "value": "pending_repayment",
        "label": "待还款",
        "expected_direction": "inflow",
        "business_type": "borrow_in",
        "side": "principal",
        "direction_semantics": "borrow_in_principal",
    },
    {
        "value": "repaid",
        "label": "已还款",
        "expected_direction": "outflow",
        "business_type": "borrow_in",
        "side": "settlement",
        "direction_semantics": "borrow_in_repayment",
    },
)
TURNOVER_ACTION_TYPES = {str(option["value"]) for option in TURNOVER_ACTION_TYPE_OPTIONS}
TURNOVER_ACTION_TYPE_BY_VALUE = {
    str(option["value"]): dict(option)
    for option in TURNOVER_ACTION_TYPE_OPTIONS
}

_PAYMENT_PRIMARY_LABELS = {EXTERNAL_TURNOVER_PAYMENT_LABEL, LEGACY_EXTERNAL_TURNOVER_PAYMENT_LABEL}
_RECEIPT_PRIMARY_LABELS = {EXTERNAL_TURNOVER_RECEIPT_LABEL, LEGACY_EXTERNAL_TURNOVER_RECEIPT_LABEL}
_PAYMENT_REPAID_SUB_TERMS = ("归还", "还借款", "还暂借款", "偿还", "还款")
_RECEIPT_COLLECTION_SUB_TERMS = ("收回", "退", "退款", "返还")


def text(value: Any) -> str:
    return str(value or "").strip()


def canonical_external_primary_label(value: Any) -> str:
    label = text(value)
    if label == LEGACY_EXTERNAL_TURNOVER_PAYMENT_LABEL:
        return EXTERNAL_TURNOVER_PAYMENT_LABEL
    if label == LEGACY_EXTERNAL_TURNOVER_RECEIPT_LABEL:
        return EXTERNAL_TURNOVER_RECEIPT_LABEL
    return label


def normalize_external_third_label(value: Any) -> str:
    label = text(value)
    return label if label in TURNOVER_FAMILY_BY_THIRD_LABEL else ""


def turnover_family_for_third_label(value: Any) -> str:
    return TURNOVER_FAMILY_BY_THIRD_LABEL.get(text(value), "")


def is_external_turnover_primary_label(value: Any) -> bool:
    return text(value) in EXTERNAL_TURNOVER_PRIMARY_LABELS


def is_external_turnover_definition(definition: dict[str, Any] | None) -> bool:
    if not isinstance(definition, dict):
        return False
    if text(definition.get("code") or definition.get("category_code")) == EXTERNAL_TURNOVER_CATEGORY_CODE:
        return True
    if text(definition.get("turnover_role")) == EXTERNAL_TURNOVER_ROLE:
        return True
    return is_external_turnover_primary_label(definition.get("output_primary_label"))


def infer_turnover_action_type(
    *,
    primary_label: Any,
    sub_label: Any,
    direction: Any = "",
) -> str:
    primary = text(primary_label)
    sub = text(sub_label)
    normalized_direction = text(direction)
    if primary in _PAYMENT_PRIMARY_LABELS:
        if any(term in sub for term in _PAYMENT_REPAID_SUB_TERMS):
            return "repaid"
        return "pending_collection"
    if primary in _RECEIPT_PRIMARY_LABELS:
        if any(term in sub for term in _RECEIPT_COLLECTION_SUB_TERMS):
            return "collected"
        return "pending_repayment"
    if normalized_direction == "expense":
        return "pending_collection"
    if normalized_direction == "income":
        return "pending_repayment"
    return ""


def normalize_turnover_action_type(value: Any) -> str:
    action_type = text(value)
    return action_type if action_type in TURNOVER_ACTION_TYPES else ""


def normalize_external_turnover_metadata(
    *,
    primary_label: Any,
    sub_label: Any,
    third_label: Any = "",
    action_type: Any = "",
    direction: Any = "",
) -> dict[str, str]:
    primary = canonical_external_primary_label(primary_label)
    sub = text(sub_label)
    third = normalize_external_third_label(third_label)
    normalized_action = normalize_turnover_action_type(action_type)
    if not normalized_action:
        normalized_action = infer_turnover_action_type(
            primary_label=primary,
            sub_label=sub,
            direction=direction,
        )
    return {
        "turnover_role": EXTERNAL_TURNOVER_ROLE,
        "output_primary_label": primary,
        "output_sub_label": sub,
        "output_third_label": third,
        "category_primary_label": primary,
        "category_sub_label": sub,
        "category_third_label": third,
        "turnover_action_type": normalized_action,
        "turnover_family": turnover_family_for_third_label(third),
    }


def label_path(primary_label: Any, sub_label: Any, third_label: Any = "") -> list[str]:
    return [
        item
        for item in (
            text(primary_label),
            text(sub_label),
            text(third_label),
        )
        if item
    ]


def external_turnover_candidate_variants(payload: dict[str, Any]) -> list[dict[str, Any]]:
    base_primary = canonical_external_primary_label(payload.get("category_primary_label") or payload.get("output_primary_label"))
    base_sub = text(payload.get("category_sub_label") or payload.get("output_sub_label"))
    action_type = normalize_turnover_action_type(payload.get("turnover_action_type"))
    if not base_primary or not base_sub or not action_type:
        return []
    candidates: list[dict[str, Any]] = []
    for third_label in EXTERNAL_TURNOVER_THIRD_LABELS:
        family = turnover_family_for_third_label(third_label)
        candidates.append(
            {
                **payload,
                "category_third_label": third_label,
                "output_third_label": third_label,
                "category_label_path": label_path(base_primary, base_sub, third_label),
                "turnover_role": EXTERNAL_TURNOVER_ROLE,
                "turnover_action_type": action_type,
                "turnover_family": family,
            }
        )
    return candidates


def selected_external_turnover_payload(
    *,
    category_code: Any,
    category_label: Any = "",
    category_primary_label: Any,
    category_sub_label: Any,
    category_third_label: Any,
    turnover_action_type: Any,
) -> dict[str, Any]:
    primary = canonical_external_primary_label(category_primary_label)
    sub = text(category_sub_label)
    third = normalize_external_third_label(category_third_label)
    action = normalize_turnover_action_type(turnover_action_type)
    return {
        "category_code": text(category_code),
        "category_label": text(category_label) or sub or primary,
        "category_primary_label": primary or None,
        "category_sub_label": sub or None,
        "category_third_label": third or None,
        "category_label_path": label_path(primary, sub, third),
        "turnover_role": EXTERNAL_TURNOVER_ROLE,
        "turnover_action_type": action or None,
        "turnover_family": turnover_family_for_third_label(third) or None,
    }


def turnover_relation_rule_from_bank_category(row: dict[str, Any]) -> dict[str, str] | None:
    if not isinstance(row, dict):
        return None
    if text(row.get("turnover_role")) != EXTERNAL_TURNOVER_ROLE and not is_external_turnover_primary_label(
        row.get("category_primary_label")
    ):
        return None
    third_label = text(row.get("category_third_label"))
    if not third_label:
        path = row.get("category_label_path")
        if isinstance(path, list) and len(path) >= 3:
            third_label = text(path[2])
    family = text(row.get("turnover_family")) or turnover_family_for_third_label(third_label)
    action_type = normalize_turnover_action_type(row.get("turnover_action_type"))
    if not family or not action_type:
        return None
    action = TURNOVER_ACTION_TYPE_BY_VALUE[action_type]
    return {
        "category_family": family,
        "business_type": str(action["business_type"]),
        "side": str(action["side"]),
        "expected_direction": str(action["expected_direction"]),
        "direction_semantics": str(action["direction_semantics"]),
    }

from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService

PENDING_INVOICE_REQUIRES_GROUP = "requires_invoice"
PENDING_INVOICE_BANK_STATEMENT_GROUP = "bank_statement_as_invoice"
PENDING_INVOICE_NO_INVOICE_GROUP = "no_invoice_required"
PENDING_INVOICE_CASH_INCOME_GROUP = "cash_income"
PENDING_INVOICE_EDITABLE_GROUPS = (
    PENDING_INVOICE_BANK_STATEMENT_GROUP,
    PENDING_INVOICE_NO_INVOICE_GROUP,
)
PENDING_OUTPUT_INVOICE_EDITABLE_GROUPS = (
    PENDING_INVOICE_NO_INVOICE_GROUP,
    PENDING_INVOICE_CASH_INCOME_GROUP,
)
PENDING_INVOICE_ACTIVE_TAG_CODES_KEY = "active_tag_codes"
PENDING_INVOICE_DIRECTIONS = {"expense", "income"}

PENDING_INVOICE_GROUP_LABELS_BY_DIRECTION = {
    "expense": {
        PENDING_INVOICE_REQUIRES_GROUP: "需要开票",
        PENDING_INVOICE_BANK_STATEMENT_GROUP: "流水代替发票",
        PENDING_INVOICE_NO_INVOICE_GROUP: "无需开票",
    },
    "income": {
        PENDING_INVOICE_REQUIRES_GROUP: "待开发票",
        PENDING_INVOICE_NO_INVOICE_GROUP: "无需开票",
        PENDING_INVOICE_CASH_INCOME_GROUP: "现金收入",
    },
}


def normalize_pending_invoice_direction(direction: str | None) -> str:
    normalized = str(direction or "expense").strip() or "expense"
    if normalized not in PENDING_INVOICE_DIRECTIONS:
        return "expense"
    return normalized


def pending_invoice_settings_key(direction: str | None) -> str:
    return "pending_output_invoice_tag_groups" if normalize_pending_invoice_direction(direction) == "income" else "pending_invoice_tag_groups"


def pending_invoice_editable_groups(direction: str | None) -> tuple[str, ...]:
    return PENDING_OUTPUT_INVOICE_EDITABLE_GROUPS if normalize_pending_invoice_direction(direction) == "income" else PENDING_INVOICE_EDITABLE_GROUPS


def pending_invoice_group_labels(direction: str | None) -> dict[str, str]:
    return dict(PENDING_INVOICE_GROUP_LABELS_BY_DIRECTION[normalize_pending_invoice_direction(direction)])


def _pending_invoice_rule_tag(raw_tag: dict[str, Any], *, direction: str | None = None) -> dict[str, str] | None:
    code = str(raw_tag.get("code") or "").strip()
    if not code or str(raw_tag.get("status") or "active") != "active":
        return None
    normalized_direction = normalize_pending_invoice_direction(direction)
    rule_direction = str(raw_tag.get("direction") or "any").strip() or "any"
    if rule_direction not in {"any", normalized_direction}:
        return None
    label = str(raw_tag.get("label") or code)
    return {
        "code": code,
        "label": label,
        "status": "active",
        "output_primary_label": str(raw_tag.get("output_primary_label") or label or code),
        "output_sub_label": str(raw_tag.get("output_sub_label") or ""),
    }


def active_pending_invoice_rule_tags(
    tag_dictionary: dict[str, Any] | None,
    *,
    direction: str | None = "expense",
) -> list[dict[str, str]]:
    if not isinstance(tag_dictionary, dict):
        return []
    normalized_direction = normalize_pending_invoice_direction(direction)
    auto_rules_payload = BankTransactionCategoryService.auto_tag_rules_payload(tag_dictionary)
    raw_tags: list[Any] = []
    system_rule = auto_rules_payload.get("system_rule")
    if isinstance(system_rule, dict):
        raw_tags.append(system_rule)
    raw_tags.extend(list(auto_rules_payload.get("active_rules") or []))
    result: list[dict[str, str]] = []
    seen: set[str] = set()
    for raw_tag in list(raw_tags):
        if not isinstance(raw_tag, dict):
            continue
        tag = _pending_invoice_rule_tag(raw_tag, direction=normalized_direction)
        if tag is None or tag["code"] in seen:
            continue
        seen.add(tag["code"])
        result.append(tag)
    return result


def pending_invoice_available_rule_tags(
    settings_payload: dict[str, Any] | None,
    *,
    direction: str | None = "expense",
) -> list[dict[str, str]]:
    if not isinstance(settings_payload, dict):
        return []
    normalized_direction = normalize_pending_invoice_direction(direction)
    available_key = f"pending_invoice_available_tags_{normalized_direction}"
    if available_key in settings_payload:
        raw_available_tags = settings_payload.get(available_key)
    elif "pending_invoice_available_tags" in settings_payload:
        raw_available_tags = settings_payload.get("pending_invoice_available_tags")
    else:
        raw_available_tags = settings_payload.get("available_tags")
    if isinstance(raw_available_tags, list):
        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_tag in raw_available_tags:
            if not isinstance(raw_tag, dict):
                continue
            tag = _pending_invoice_rule_tag(raw_tag, direction=normalized_direction)
            if tag is None or tag["code"] in seen:
                continue
            seen.add(tag["code"])
            result.append(tag)
        return result
    return active_pending_invoice_rule_tags(
        settings_payload.get("bank_transaction_tags")
        if isinstance(settings_payload.get("bank_transaction_tags"), dict)
        else None,
        direction=normalized_direction,
    )


def pending_invoice_raw_groups(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    groups = value.get("groups")
    return groups if isinstance(groups, dict) else value


def pending_invoice_group_codes(groups_payload: Any, group_name: str) -> list[str]:
    groups = pending_invoice_raw_groups(groups_payload)
    raw_group = groups.get(group_name)
    if isinstance(raw_group, dict):
        raw_codes = raw_group.get("tag_codes")
    elif isinstance(raw_group, list):
        raw_codes = raw_group
    else:
        raw_codes = []
    tag_codes: list[str] = []
    seen: set[str] = set()
    for raw_code in list(raw_codes or []):
        code = str(raw_code).strip()
        if not code or code in seen:
            continue
        seen.add(code)
        tag_codes.append(code)
    return tag_codes


def pending_invoice_effective_category_payload(category: dict[str, Any] | None) -> dict[str, Any]:
    raw = category if isinstance(category, dict) else {}
    code = str(
        raw.get("effective_category_code")
        or raw.get("category_code")
        or raw.get("category")
        or ""
    ).strip()
    label = str(
        raw.get("effective_category_label")
        or raw.get("category_label")
        or raw.get("label")
        or code
        or ""
    ).strip()
    primary_label = str(raw.get("effective_category_primary_label") or raw.get("category_primary_label") or "").strip()
    sub_label = str(raw.get("effective_category_sub_label") or raw.get("category_sub_label") or "").strip()
    raw_path = (
        raw.get("effective_category_label_path")
        or raw.get("category_label_path")
        or raw.get("effective_category_path")
        or raw.get("category_path")
        or raw.get("path")
        or []
    )
    label_path = [
        str(item).strip()
        for item in list(raw_path if isinstance(raw_path, list) else [])
        if str(item).strip()
    ]
    if not primary_label and label_path:
        primary_label = label_path[0]
    if not sub_label and len(label_path) > 1:
        sub_label = label_path[1]
    if not label_path:
        label_path = [part for part in [primary_label, sub_label or label] if part]
    return {
        "category_code": code or None,
        "category_label": label or None,
        "category_primary_label": primary_label or None,
        "category_sub_label": sub_label or None,
        "category_label_path": label_path,
    }


def editable_pending_invoice_tag_groups_payload(value: dict[str, Any], *, direction: str | None = "expense") -> dict[str, Any]:
    return {
        "groups": {
            group_name: {"tag_codes": pending_invoice_group_codes(value, group_name)}
            for group_name in pending_invoice_editable_groups(direction)
        }
    }


def pending_invoice_tag_group_sets(
    settings_payload: dict[str, Any],
    *,
    direction: str | None = "expense",
) -> dict[str, set[str]]:
    normalized_direction = normalize_pending_invoice_direction(direction)
    active_codes = {
        tag["code"]
        for tag in pending_invoice_available_rule_tags(settings_payload, direction=normalized_direction)
    }
    pending_groups = (
        settings_payload.get(pending_invoice_settings_key(normalized_direction))
        if isinstance(settings_payload, dict)
        else {}
    )
    result = {
        PENDING_INVOICE_ACTIVE_TAG_CODES_KEY: set(active_codes),
    }
    for group_name in pending_invoice_editable_groups(normalized_direction):
        result[group_name] = set(pending_invoice_group_codes(pending_groups, group_name)).intersection(active_codes)
    return result


def pending_invoice_group_for_category(
    category_code: str | None,
    tag_groups: dict[str, set[str]],
    *,
    direction: str | None = "expense",
) -> str | None:
    code = str(category_code or "").strip()
    if not code:
        return None
    normalized_direction = normalize_pending_invoice_direction(direction)
    if code in tag_groups.get(PENDING_INVOICE_NO_INVOICE_GROUP, set()):
        return PENDING_INVOICE_NO_INVOICE_GROUP
    if normalized_direction == "income" and code in tag_groups.get(PENDING_INVOICE_CASH_INCOME_GROUP, set()):
        return PENDING_INVOICE_CASH_INCOME_GROUP
    if normalized_direction == "expense" and code in tag_groups.get(PENDING_INVOICE_BANK_STATEMENT_GROUP, set()):
        return PENDING_INVOICE_BANK_STATEMENT_GROUP
    if code in tag_groups.get(PENDING_INVOICE_ACTIVE_TAG_CODES_KEY, set()):
        return PENDING_INVOICE_REQUIRES_GROUP
    return None


def pending_invoice_enriched_group(
    tag_codes: list[str],
    *,
    tags_by_code: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    return {
        "tag_codes": tag_codes,
        "tags": [
            {
                "code": code,
                "label": str(tags_by_code.get(code, {}).get("label") or code),
                "status": str(tags_by_code.get(code, {}).get("status") or "active"),
                "output_primary_label": str(
                    tags_by_code.get(code, {}).get("output_primary_label")
                    or tags_by_code.get(code, {}).get("label")
                    or code
                ),
                "output_sub_label": str(tags_by_code.get(code, {}).get("output_sub_label") or ""),
            }
            for code in tag_codes
            if code in tags_by_code
        ],
    }


def pending_invoice_rules_payload(
    settings: dict[str, Any],
    *,
    direction: str | None = "expense",
) -> dict[str, Any]:
    normalized_direction = normalize_pending_invoice_direction(direction)
    tag_dictionary = settings.get("bank_transaction_tags") if isinstance(settings.get("bank_transaction_tags"), dict) else {}
    settings_key = pending_invoice_settings_key(normalized_direction)
    pending_groups = settings.get(settings_key) if isinstance(settings.get(settings_key), dict) else {}
    groups = pending_groups.get("groups") if isinstance(pending_groups.get("groups"), dict) else {}
    active_tags = pending_invoice_available_rule_tags(settings, direction=normalized_direction)
    tags_by_code = {str(tag["code"]): tag for tag in active_tags}
    active_codes = set(tags_by_code)
    selected_codes: set[str] = set()
    enriched_groups: dict[str, Any] = {}
    compatible_groups: dict[str, Any] = {}
    for group_name in pending_invoice_editable_groups(normalized_direction):
        codes = [
            code
            for code in pending_invoice_group_codes(groups, group_name)
            if code in active_codes
        ]
        selected_codes.update(codes)
        enriched_groups[group_name] = pending_invoice_enriched_group(codes, tags_by_code=tags_by_code)
        compatible_groups[group_name] = {"tag_codes": codes}
    requires_invoice_codes = [
        str(tag["code"])
        for tag in active_tags
        if str(tag["code"]) not in selected_codes
    ]
    enriched_groups[PENDING_INVOICE_REQUIRES_GROUP] = pending_invoice_enriched_group(
        requires_invoice_codes,
        tags_by_code=tags_by_code,
    )
    compatible_groups[PENDING_INVOICE_REQUIRES_GROUP] = {"tag_codes": requires_invoice_codes}
    labels = pending_invoice_group_labels(normalized_direction)
    ordered_groups: dict[str, Any] = {}
    for group_name in labels:
        group_payload = dict(enriched_groups.get(group_name) or {"tag_codes": [], "tags": []})
        group_payload["label"] = labels[group_name]
        ordered_groups[group_name] = group_payload
    compatible_pending_groups = {
        **pending_groups,
        "groups": {
            **(groups if isinstance(groups, dict) else {}),
            **compatible_groups,
        },
    }
    return {
        "version": int(pending_groups.get("version") or 1) if isinstance(pending_groups, dict) else 1,
        "direction": normalized_direction,
        "groups": ordered_groups,
        "available_tags": active_tags,
        "bank_transaction_tags": tag_dictionary,
        settings_key: compatible_pending_groups,
        "pending_invoice_tag_groups": compatible_pending_groups if normalized_direction == "expense" else settings.get("pending_invoice_tag_groups", {}),
    }

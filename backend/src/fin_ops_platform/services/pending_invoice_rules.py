from __future__ import annotations

from typing import Any

from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService

PENDING_INVOICE_REQUIRES_GROUP = "requires_invoice"
PENDING_INVOICE_BANK_STATEMENT_GROUP = "bank_statement_as_invoice"
PENDING_INVOICE_NO_INVOICE_GROUP = "no_invoice_required"
PENDING_INVOICE_EDITABLE_GROUPS = (
    PENDING_INVOICE_BANK_STATEMENT_GROUP,
    PENDING_INVOICE_NO_INVOICE_GROUP,
)
PENDING_INVOICE_ACTIVE_TAG_CODES_KEY = "active_tag_codes"


def _pending_invoice_rule_tag(raw_tag: dict[str, Any]) -> dict[str, str] | None:
    code = str(raw_tag.get("code") or "").strip()
    if not code or str(raw_tag.get("status") or "active") != "active":
        return None
    label = str(raw_tag.get("label") or code)
    return {
        "code": code,
        "label": label,
        "status": "active",
        "output_primary_label": str(raw_tag.get("output_primary_label") or label or code),
        "output_sub_label": str(raw_tag.get("output_sub_label") or ""),
    }


def active_pending_invoice_rule_tags(tag_dictionary: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(tag_dictionary, dict):
        return []
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
        tag = _pending_invoice_rule_tag(raw_tag)
        if tag is None or tag["code"] in seen:
            continue
        seen.add(tag["code"])
        result.append(tag)
    return result


def pending_invoice_available_rule_tags(settings_payload: dict[str, Any] | None) -> list[dict[str, str]]:
    if not isinstance(settings_payload, dict):
        return []
    raw_available_tags = settings_payload.get("pending_invoice_available_tags") or settings_payload.get("available_tags")
    if isinstance(raw_available_tags, list):
        result: list[dict[str, str]] = []
        seen: set[str] = set()
        for raw_tag in raw_available_tags:
            if not isinstance(raw_tag, dict):
                continue
            tag = _pending_invoice_rule_tag(raw_tag)
            if tag is None or tag["code"] in seen:
                continue
            seen.add(tag["code"])
            result.append(tag)
        return result
    return active_pending_invoice_rule_tags(
        settings_payload.get("bank_transaction_tags")
        if isinstance(settings_payload.get("bank_transaction_tags"), dict)
        else None
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


def editable_pending_invoice_tag_groups_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "groups": {
            group_name: {"tag_codes": pending_invoice_group_codes(value, group_name)}
            for group_name in PENDING_INVOICE_EDITABLE_GROUPS
        }
    }


def pending_invoice_tag_group_sets(settings_payload: dict[str, Any]) -> dict[str, set[str]]:
    active_codes = {
        tag["code"]
        for tag in pending_invoice_available_rule_tags(settings_payload)
    }
    pending_groups = (
        settings_payload.get("pending_invoice_tag_groups")
        if isinstance(settings_payload, dict)
        else {}
    )
    return {
        PENDING_INVOICE_ACTIVE_TAG_CODES_KEY: set(active_codes),
        PENDING_INVOICE_BANK_STATEMENT_GROUP: set(
            pending_invoice_group_codes(pending_groups, PENDING_INVOICE_BANK_STATEMENT_GROUP)
        ).intersection(active_codes),
        PENDING_INVOICE_NO_INVOICE_GROUP: set(
            pending_invoice_group_codes(pending_groups, PENDING_INVOICE_NO_INVOICE_GROUP)
        ).intersection(active_codes),
    }


def pending_invoice_group_for_category(category_code: str | None, tag_groups: dict[str, set[str]]) -> str | None:
    code = str(category_code or "").strip()
    if not code:
        return None
    if code in tag_groups.get(PENDING_INVOICE_NO_INVOICE_GROUP, set()):
        return PENDING_INVOICE_NO_INVOICE_GROUP
    if code in tag_groups.get(PENDING_INVOICE_BANK_STATEMENT_GROUP, set()):
        return PENDING_INVOICE_BANK_STATEMENT_GROUP
    if code in tag_groups.get(PENDING_INVOICE_ACTIVE_TAG_CODES_KEY, set()):
        return PENDING_INVOICE_REQUIRES_GROUP
    return None

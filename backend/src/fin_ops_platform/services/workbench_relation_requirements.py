from __future__ import annotations

from typing import Any, Iterable


def build_bank_relation_requirement_metadata(
    *,
    tag_codes: Iterable[str],
    rules_payload: dict[str, Any] | None,
) -> dict[str, object]:
    """Build the frozen Workbench completion requirement for bank members."""

    payload = rules_payload if isinstance(rules_payload, dict) else {}
    raw_requirements = payload.get("requirements_by_tag_code")
    requirements = dict(raw_requirements) if isinstance(raw_requirements, dict) else {}
    for item in list(payload.get("rules") or []):
        if not isinstance(item, dict):
            continue
        tag_code = str(item.get("tag_code") or item.get("code") or "").strip()
        if tag_code:
            requirements[tag_code] = item
    raw_tags = [str(value or "").strip() for value in tag_codes]
    has_missing_tag = any(not tag_code for tag_code in raw_tags)
    normalized_tags = list(dict.fromkeys(tag_code for tag_code in raw_tags if tag_code))
    requires_oa = False
    requires_invoice = False
    for tag_code in normalized_tags:
        rule = requirements.get(tag_code)
        if isinstance(rule, dict):
            requires_oa = requires_oa or bool(rule.get("requires_oa"))
            requires_invoice = requires_invoice or bool(rule.get("requires_invoice"))
        else:
            requires_oa = True
            requires_invoice = True
    if has_missing_tag or not normalized_tags:
        requires_oa = True
        requires_invoice = True
    metadata: dict[str, object] = {
        "paired_requirement_source": "bank_transaction_paired_policy",
        "paired_requirement_tag_codes": normalized_tags,
        "paired_requirement_version": max(1, _integer(payload.get("version"), default=1)),
        "requires_oa": requires_oa,
        "requires_invoice": requires_invoice,
    }
    if len(normalized_tags) == 1:
        metadata["paired_requirement_tag_code"] = normalized_tags[0]
    return metadata


def evaluate_bank_relation_completion(
    *,
    row_types: Iterable[str],
    special_metadata: dict[str, Any] | None,
    relation_mode: str = "",
    amount_check: dict[str, Any] | None = None,
    oa_workflow_statuses: Iterable[str] | None = None,
) -> dict[str, object]:
    normalized_types = tuple(str(value or "").strip().lower() for value in row_types)
    metadata = special_metadata if isinstance(special_metadata, dict) else {}
    present = set(normalized_types)
    missing: list[str] = []
    if str(metadata.get("source") or "").strip() != "batch_accounting":
        if "oa" in present and "bank" not in present:
            missing.append("bank")
        elif "bank" in present:
            if _requirement(metadata, "requires_oa", "paired_requires_oa") and "oa" not in present:
                missing.append("oa")
            if _requirement(metadata, "requires_invoice", "paired_requires_invoice") and "invoice" not in present:
                missing.append("invoice")

    blocking_reasons: list[str] = []
    if "oa" in present:
        statuses = (
            ["completed"] * normalized_types.count("oa")
            if oa_workflow_statuses is None
            else [str(value or "").strip().lower() for value in oa_workflow_statuses]
        )
        if "in_progress" in statuses:
            blocking_reasons.append("oa_in_progress")
        if len(statuses) != normalized_types.count("oa") or any(
            status not in {"completed", "in_progress"} for status in statuses
        ):
            blocking_reasons.append("oa_workflow_status_unknown")
    material_complete = not missing
    workflow_complete = not blocking_reasons
    result: dict[str, object] = {
        "is_complete": material_complete and workflow_complete,
        "missing_row_types": missing,
    }
    if blocking_reasons:
        result["blocking_reasons"] = blocking_reasons
    return result


def _requirement(metadata: dict[str, Any], primary: str, legacy: str) -> bool:
    if primary in metadata:
        return bool(metadata[primary])
    if legacy in metadata:
        return bool(metadata[legacy])
    return True


def _integer(value: Any, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default

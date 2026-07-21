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
    normalized_tags = list(dict.fromkeys(str(value or "").strip() for value in tag_codes if str(value or "").strip()))
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
    if not normalized_tags:
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
) -> dict[str, object]:
    normalized_types = tuple(str(value or "").strip().lower() for value in row_types)
    if "bank" not in normalized_types:
        return {"is_complete": True, "missing_row_types": []}
    metadata = special_metadata if isinstance(special_metadata, dict) else {}
    check = amount_check if isinstance(amount_check, dict) else {}
    is_etc_batch_relation = bool(
        isinstance(metadata.get("etc_batch_link"), dict)
        or str(check.get("external_etc_batch_id") or check.get("etc_batch_id") or "").strip()
    )
    if (
        str(relation_mode or "").strip() == "turnover_manual_closure"
        or str(metadata.get("source") or "").strip() == "batch_accounting"
        or is_etc_batch_relation
    ):
        return {"is_complete": True, "missing_row_types": []}
    requires_oa = _requirement(metadata, "requires_oa", "paired_requires_oa")
    requires_invoice = _requirement(metadata, "requires_invoice", "paired_requires_invoice")
    present = set(normalized_types)
    missing: list[str] = []
    if requires_oa and "oa" not in present:
        missing.append("oa")
    if requires_invoice and "invoice" not in present:
        missing.append("invoice")
    return {"is_complete": not missing, "missing_row_types": missing}


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

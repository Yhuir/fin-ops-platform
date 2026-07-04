from __future__ import annotations

from typing import Any


UNTAGGED_BANK_TAG_LABEL = "未标记"


def bank_tag_context_from_row(row: dict[str, Any]) -> dict[str, Any]:
    code = _text(row.get("bank_tag_code") or row.get("effective_category_code") or row.get("category_code"))
    label = _text(row.get("bank_tag_label") or row.get("effective_category_label") or row.get("category_label"))
    primary = _text(
        row.get("bank_tag_primary_label")
        or row.get("effective_category_primary_label")
        or row.get("category_primary_label")
    )
    sub = _text(row.get("bank_tag_sub_label") or row.get("effective_category_sub_label") or row.get("category_sub_label"))
    label_path = _text_list(
        row.get("bank_tag_label_path")
        or row.get("effective_category_label_path")
        or row.get("category_label_path")
        or row.get("effective_category_path")
        or row.get("category_path")
    )
    if label_path:
        primary = primary or label_path[0]
        sub = sub or (label_path[1] if len(label_path) > 1 else "")
    primary = primary or label or UNTAGGED_BANK_TAG_LABEL
    sub = sub or label or primary
    if not label_path:
        label_path = [primary] if primary == sub else [primary, sub]
    return {
        "bank_tag_code": code,
        "bank_tag_label": label or sub,
        "bank_tag_primary_label": primary,
        "bank_tag_sub_label": sub,
        "bank_tag_label_path": label_path,
    }


def _text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in {"-", "--", "—", "——"} else text


def _text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [_text(item) for item in value if _text(item)]

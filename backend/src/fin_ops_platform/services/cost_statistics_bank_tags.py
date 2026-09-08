from __future__ import annotations

from typing import Any

UNTAGGED_BANK_TAG_LABEL = "未标记"


def bank_tag_context_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Consume normalized bank fields only; never infer hierarchy from a flat label."""
    code = str(row.get("bank_tag_code") or "").strip()
    if not code:
        return {
            "bank_tag_code": "", "bank_tag_label": UNTAGGED_BANK_TAG_LABEL,
            "bank_tag_primary_label": UNTAGGED_BANK_TAG_LABEL,
            "bank_tag_sub_label": UNTAGGED_BANK_TAG_LABEL,
            "bank_tag_label_path": [UNTAGGED_BANK_TAG_LABEL],
        }
    return {
        "bank_tag_code": code,
        "bank_tag_label": str(row["bank_tag_label"] or ""),
        "bank_tag_primary_label": str(row["bank_tag_primary_label"] or ""),
        "bank_tag_sub_label": str(row["bank_tag_sub_label"] or ""),
        "bank_tag_label_path": list(row["bank_tag_label_path"]),
    }

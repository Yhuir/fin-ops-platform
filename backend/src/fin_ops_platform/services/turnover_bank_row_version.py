from __future__ import annotations


def turnover_bank_row_version(row: dict[str, object]) -> object:
    zero_candidate: object | None = None
    for field_name in ("category_version", "manual_category_version", "version"):
        value = row.get(field_name)
        if value is None or value == "":
            continue
        try:
            numeric_value = int(str(value).strip())
        except (TypeError, ValueError):
            return value
        if numeric_value != 0:
            return numeric_value
        if zero_candidate is None:
            zero_candidate = numeric_value
    return zero_candidate


def turnover_bank_row_selection_version(row: dict[str, object]) -> str:
    bank_updated_at = str(row.get("bank_transaction_updated_at") or "").strip()
    category_code = str(row.get("effective_category_code") or row.get("category_code") or "").strip()
    turnover_role = str(row.get("effective_turnover_role") or row.get("turnover_role") or "").strip()
    turnover_action = str(
        row.get("effective_turnover_action_type")
        or row.get("turnover_action_type")
        or ""
    ).strip()
    turnover_family = str(row.get("effective_turnover_family") or row.get("turnover_family") or "").strip()
    if not bank_updated_at or not category_code or not turnover_action or not turnover_family:
        return ""
    return "|".join(
        (
            "v1",
            bank_updated_at,
            str(turnover_bank_row_version(row) or 0),
            str(row.get("category_rule_version") or "").strip(),
            category_code,
            turnover_role,
            turnover_action,
            turnover_family,
        )
    )

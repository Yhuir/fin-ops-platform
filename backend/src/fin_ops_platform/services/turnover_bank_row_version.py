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

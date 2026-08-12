from __future__ import annotations

import re
from datetime import datetime
from typing import Any

WORKBENCH_FILTER_OPTION_COLUMNS = {
    "oa": frozenset({"applicant", "projectName", "counterparty"}),
    "bank": frozenset({"counterparty", "amount", "loanRepaymentDate"}),
    "invoice": frozenset({"sellerName", "buyerName"}),
}
WORKBENCH_FILTER_OPTION_FACETS = frozenset({"column", "time_year"})
WORKBENCH_FILTER_MISSING_VALUE = "__workbench_missing__"
WORKBENCH_FILTER_PLACEHOLDERS = frozenset({"", "--", "—"})
WORKBENCH_FILTER_VALUE_MAX_LENGTH = 200
WORKBENCH_FILTER_VALUES_PER_COLUMN_MAX = 20
WORKBENCH_FILTER_VALUES_TOTAL_MAX = 80
WORKBENCH_ALLOWED_FILTER_COLUMNS = {
    "oa": frozenset(
        {
            "applicant",
            "projectName",
            "applicationType",
            "counterparty",
            "reconciliationStatus",
        }
    ),
    "bank": frozenset(
        {
            "counterparty",
            "amount",
            "direction",
            "paymentAccount",
            "invoiceRelationStatus",
            "loanRepaymentDate",
        }
    ),
    "invoice": frozenset({"sellerName", "buyerName", "invoiceType"}),
}


def normalize_workbench_filter_option_target(
    *,
    pane: str | None,
    facet: str | None,
    column: str | None,
) -> tuple[str, str, str | None]:
    normalized_pane = str(pane or "").strip()
    normalized_facet = str(facet or "column").strip()
    normalized_column = str(column or "").strip() or None
    if normalized_pane not in WORKBENCH_FILTER_OPTION_COLUMNS:
        raise ValueError("pane must be oa, bank, or invoice.")
    if normalized_facet not in WORKBENCH_FILTER_OPTION_FACETS:
        raise ValueError("facet must be column or time_year.")
    if normalized_facet == "column":
        if normalized_column not in WORKBENCH_FILTER_OPTION_COLUMNS[normalized_pane]:
            raise ValueError("column is not filterable for the selected pane.")
    else:
        normalized_column = None
    return normalized_pane, normalized_facet, normalized_column


def normalize_workbench_column_filters(
    value: Any,
) -> dict[str, dict[str, list[str]]]:
    """Normalize the bounded, page-owned Workbench column filter contract."""

    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("column_filters must be a JSON object.")
    payload = value
    unknown_panes = sorted(set(payload) - set(WORKBENCH_ALLOWED_FILTER_COLUMNS))
    if unknown_panes:
        raise ValueError(
            "column_filters contains unsupported panes: " + ", ".join(unknown_panes)
        )
    result: dict[str, dict[str, list[str]]] = {}
    total_values = 0
    for pane in ("oa", "bank", "invoice"):
        raw_pane = payload.get(pane)
        if raw_pane is None:
            continue
        if not isinstance(raw_pane, dict):
            raise ValueError(f"column_filters.{pane} must be a JSON object.")
        pane_filters: dict[str, list[str]] = {}
        for raw_column, raw_values in raw_pane.items():
            column = str(raw_column or "").strip()
            if column not in WORKBENCH_ALLOWED_FILTER_COLUMNS[pane]:
                raise ValueError(
                    f"column_filters.{pane} contains unsupported column: {column or '<empty>'}."
                )
            if not isinstance(raw_values, list):
                raise ValueError(f"column_filters.{pane}.{column} must be an array.")
            if len(raw_values) > WORKBENCH_FILTER_VALUES_PER_COLUMN_MAX:
                raise ValueError(
                    f"column_filters.{pane}.{column} must contain at most "
                    f"{WORKBENCH_FILTER_VALUES_PER_COLUMN_MAX} values."
                )
            values = raw_values
            normalized = sorted(
                {
                    text
                    for item in values
                    if (text := str(item or "").strip())
                    and text not in WORKBENCH_FILTER_PLACEHOLDERS
                }
            )
            overlong = [
                text for text in normalized if len(text) > WORKBENCH_FILTER_VALUE_MAX_LENGTH
            ]
            if overlong:
                raise ValueError(
                    f"column_filters.{pane}.{column} values must be at most "
                    f"{WORKBENCH_FILTER_VALUE_MAX_LENGTH} characters."
                )
            if not normalized:
                continue
            if total_values + len(normalized) > WORKBENCH_FILTER_VALUES_TOTAL_MAX:
                raise ValueError(
                    f"column_filters must contain at most "
                    f"{WORKBENCH_FILTER_VALUES_TOTAL_MAX} values."
                )
            pane_filters[column] = normalized
            total_values += len(pane_filters[column])
        if pane_filters:
            result[pane] = pane_filters
    return result


def normalize_workbench_time_filters(value: Any) -> dict[str, dict[str, str]]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ValueError("time_filters must be a JSON object.")
    payload = value
    unknown_panes = sorted(set(payload) - {"oa", "bank", "invoice"})
    if unknown_panes:
        raise ValueError(
            "time_filters contains unsupported panes: " + ", ".join(unknown_panes)
        )
    result: dict[str, dict[str, str]] = {}
    for pane in ("oa", "bank", "invoice"):
        raw_filter = payload.get(pane)
        if raw_filter is None:
            continue
        if not isinstance(raw_filter, dict):
            raise ValueError(f"time_filters.{pane} must be a JSON object.")
        unknown_fields = sorted(set(raw_filter) - {"mode", "year", "month"})
        if unknown_fields:
            raise ValueError(
                f"time_filters.{pane} contains unsupported fields: "
                + ", ".join(unknown_fields)
            )
        mode = str(raw_filter.get("mode") or "").strip()
        if mode == "year":
            year = str(raw_filter.get("year") or "").strip()
            if not re.fullmatch(r"\d{4}", year):
                raise ValueError(f"time_filters.{pane}.year must be YYYY.")
            result[pane] = {"mode": "year", "year": year}
        elif mode == "month":
            month = str(raw_filter.get("month") or "").strip()
            try:
                datetime.strptime(month, "%Y-%m")
            except ValueError as error:
                raise ValueError(f"time_filters.{pane}.month must be YYYY-MM.") from error
            result[pane] = {"mode": "month", "month": month}
        else:
            raise ValueError(f"time_filters.{pane}.mode must be year or month.")
    return result


def normalize_workbench_scope_key(value: object) -> str:
    normalized = str(value or "").strip() or "all"
    if normalized == "all":
        return normalized
    if not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", normalized):
        raise ValueError("month must be all or YYYY-MM.")
    try:
        datetime.strptime(normalized, "%Y-%m")
    except ValueError as error:
        raise ValueError("month must be all or YYYY-MM.") from error
    return normalized


def workbench_time_range(value: dict[str, str] | None) -> tuple[str | None, str | None]:
    payload = value if isinstance(value, dict) else {}
    if payload.get("mode") == "year":
        year = str(payload.get("year") or "")
        if re.fullmatch(r"\d{4}", year):
            return f"{year}-01-01", f"{int(year) + 1:04d}-01-01"
    if payload.get("mode") == "month":
        month = str(payload.get("month") or "")
        if re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            year_number = int(month[:4])
            month_number = int(month[5:])
            if month_number == 12:
                return f"{year_number:04d}-12-01", f"{year_number + 1:04d}-01-01"
            return (
                f"{year_number:04d}-{month_number:02d}-01",
                f"{year_number:04d}-{month_number + 1:02d}-01",
            )
    return None, None


__all__ = [
    "WORKBENCH_ALLOWED_FILTER_COLUMNS",
    "WORKBENCH_FILTER_MISSING_VALUE",
    "WORKBENCH_FILTER_OPTION_COLUMNS",
    "normalize_workbench_column_filters",
    "normalize_workbench_filter_option_target",
    "normalize_workbench_scope_key",
    "normalize_workbench_time_filters",
    "workbench_time_range",
]

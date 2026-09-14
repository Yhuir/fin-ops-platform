"""Relation scope derived exclusively from canonical selection descriptors."""
from __future__ import annotations

from datetime import date
from typing import Any

from fin_ops_platform.services.workbench_filter_options import normalize_workbench_scope_key


class WorkbenchRelationScopeError(ValueError):
    """A canonical source supplied a malformed, non-null month."""


def canonical_month(value: object) -> str | None:
    if value is None:
        return None
    try:
        if isinstance(value, date):
            return value.strftime("%Y-%m")
        text = str(value).strip()
        if len(text) == 10:
            text = date.fromisoformat(text).strftime("%Y-%m")
        if not text or text == "all":
            raise ValueError("A source month must be a date or YYYY-MM.")
        return normalize_workbench_scope_key(text)
    except (ValueError, TypeError) as error:
        raise WorkbenchRelationScopeError("关联记录的业务月份无效，请修正来源数据后重新预览。") from error


def relation_scope(rows: list[dict[str, Any]]) -> str:
    months = {canonical_month(row.get("scope_month")) for row in rows}
    return next(iter(months)) if len(months) == 1 and None not in months else "all"


def affected_months(rows: list[dict[str, Any]]) -> list[str]:
    return sorted({month for row in rows if (month := canonical_month(row.get("scope_month")))})


def validate_relation_scope(value: object) -> str:
    try:
        return normalize_workbench_scope_key(value)
    except ValueError as error:
        raise WorkbenchRelationScopeError("关联记录的业务月份无效，请修正来源数据后重新预览。") from error

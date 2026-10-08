from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol


@dataclass(frozen=True)
class TaxOffsetQuery:
    status: str = "all"
    issue_month: str | None = None
    selection_month: str | None = None
    search: str = ""
    sort_by: str = "issue_date"
    sort_direction: str = "desc"
    page: int = 1
    page_size: int = 50

    @classmethod
    def parse(cls, filters: dict[str, object]) -> "TaxOffsetQuery":
        if not isinstance(filters, dict):
            raise ValueError("筛选须为对象。")
        allowed = set(cls.__dataclass_fields__)
        if set(filters) - allowed:
            raise ValueError("筛选包含不支持的字段。")
        status = filters.get("status", "all")
        sort_by = filters.get("sort_by", "issue_date")
        direction = filters.get("sort_direction", "desc")
        if status not in ("all", "certified", "uncertified"):
            raise ValueError("认证状态无效。")
        if sort_by not in ("issue_date", "selection_time") or direction not in ("asc", "desc"):
            raise ValueError("排序字段或方向无效。")
        search = filters.get("search", "")
        if not isinstance(search, str) or len(search) > 200:
            raise ValueError("搜索条件须为不超过 200 字的文本。")
        return cls(status=status, issue_month=_month(filters.get("issue_month")),
                   selection_month=_month(filters.get("selection_month")), search=search.strip(),
                   sort_by=sort_by, sort_direction=direction,
                   page=_positive_integer(filters.get("page", 1), "page", 1000000),
                   page_size=_positive_integer(filters.get("page_size", 50), "page_size", 200))


# The field order follows the certification source workbook, then platform state.
TAX_OFFSET_EXPORT_FIELDS = (
    ("sequence", "序号"), ("selection_status", "勾选状态"), ("invoice_source", "发票来源"),
    ("domestic_sales_certificate_no", "转内销证明编号"), ("digital_invoice_no", "数电发票号码"),
    ("invoice_code", "发票代码"), ("invoice_no", "发票号码"), ("issue_date", "开票日期"),
    ("seller_tax_no", "销售方纳税人识别号"), ("seller_name", "销售方纳税人名称"),
    ("amount", "金额"), ("tax_amount", "税额"), ("deductible_tax_amount", "有效抵扣税额"),
    ("invoice_kind", "票种"), ("invoice_kind_label", "票种标签"), ("invoice_status", "发票状态"),
    ("selection_time", "勾选时间"), ("risk_level", "发票风险等级"), ("risk_status", "风险状态"),
    ("certification_status", "认证状态"), ("tax_period", "所属期"),
)
DEFAULT_EXPORT_FIELDS = (
    "sequence", "digital_invoice_no", "issue_date", "seller_tax_no", "seller_name",
    "amount", "tax_amount", "deductible_tax_amount",
)


def export_field_catalog() -> list[dict[str, object]]:
    return [{"key": key, "label": label, "default_selected": key in DEFAULT_EXPORT_FIELDS}
            for key, label in TAX_OFFSET_EXPORT_FIELDS]


class TaxOffsetRepository(Protocol):
    def load_page(self, query: TaxOffsetQuery, *, limit_override: int | None = None) -> dict[str, Any]: ...
    def match_certified_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]: ...


class TaxOffsetQueryService:
    """Certification inventory; no monthly plan, calculation, or page cache."""

    def __init__(self, *, canonical_repository: TaxOffsetRepository) -> None:
        self._repository = canonical_repository

    def list_payload(self, filters: dict[str, object]) -> dict[str, Any]:
        query = TaxOffsetQuery.parse(filters)
        return {**self._repository.load_page(query), "export_fields": export_field_catalog()}

    def export_rows(self, filters: dict[str, object], *, limit: int) -> dict[str, Any]:
        query = TaxOffsetQuery.parse(filters)
        return self._repository.load_page(query, limit_override=limit)

    def match_certified_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self._repository.match_certified_rows(rows)


def _month(value: object) -> str | None:
    if value in (None, ""):
        return None
    if not isinstance(value, str) or len(value) != 7:
        raise ValueError("月份须为 YYYY-MM。")
    try:
        parsed = date.fromisoformat(value + "-01")
    except ValueError as exc:
        raise ValueError("月份须为有效的 YYYY-MM。") from exc
    if parsed.strftime("%Y-%m") != value:
        raise ValueError("月份须为 YYYY-MM。")
    return value


def _positive_integer(value: object, field: str, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"{field} 须为正整数。")
    if isinstance(value, str) and not value.isdecimal():
        raise ValueError(f"{field} 须为正整数。")
    number = int(value)
    if not 1 <= number <= maximum:
        raise ValueError(f"{field} 须在 1 到 {maximum} 之间。")
    return number

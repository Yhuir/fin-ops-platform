from __future__ import annotations

from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Iterator

from fin_ops_platform.services.postgres_repositories.common import jsonb
from fin_ops_platform.services.tax_offset_query_service import TaxOffsetQuery

from fin_ops_platform.services.invoice_kind import SPECIAL_INVOICE_CODE

_RAW_INVOICE = "coalesce(i.raw_payload->'normalized_payload', i.raw_payload)"
SPECIAL_INVOICE_SCOPE_SQL = f"i.status <> 'deleted' and i.invoice_type = 'input' and {_RAW_INVOICE}->>'invoice_kind_code' = %s"



class PostgresTaxOffsetCanonicalRepository:
    """Read the special-invoice inventory and certification facts in one snapshot."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Tax offset query requires PostgreSQL.")
        self._connection = connection

    @contextmanager
    def _snapshot(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction

    def load_page(self, query: TaxOffsetQuery, *, limit_override: int | None = None) -> dict[str, Any]:
        with self._snapshot() as transaction:
            return load_tax_offset_page(transaction, query, limit_override=limit_override)

    def match_certified_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        if not rows:
            return {}
        unique_rows: dict[str, dict[str, Any]] = {}
        for row in rows:
            key = row.get("unique_key")
            if not isinstance(key, str) or not key:
                raise ValueError("认证记录缺少唯一标识。")
            identity = {field: row.get(field) for field in
                        ("unique_key", "digital_invoice_no", "invoice_code", "invoice_no", "buyer_tax_no")}
            if key in unique_rows and unique_rows[key] != identity:
                raise ValueError("同一认证标识包含不同发票身份。")
            unique_rows[key] = identity
        matched = self._connection.fetch_all(
            f"""with requested as (
                select * from jsonb_to_recordset(%s::jsonb) as r(
                    unique_key text, digital_invoice_no text, invoice_code text, invoice_no text, buyer_tax_no text)
            )
            select r.unique_key, array_agg(i.id::text order by i.id) filter (where i.id is not null) as invoice_ids
            from requested r
            left join app.invoices i on {SPECIAL_INVOICE_SCOPE_SQL}
                and nullif(r.buyer_tax_no, '') is not null and i.buyer_tax_no = r.buyer_tax_no
                and ((nullif(r.digital_invoice_no, '') is not null and i.digital_invoice_no = r.digital_invoice_no)
                     or (nullif(r.digital_invoice_no, '') is null and nullif(r.invoice_code, '') is not null
                         and nullif(r.invoice_no, '') is not null
                         and i.invoice_code = r.invoice_code and i.invoice_no = r.invoice_no))
            group by r.unique_key""", (jsonb(list(unique_rows.values())), SPECIAL_INVOICE_CODE))
        result = {}
        for row in matched:
            ids = row["invoice_ids"] or []
            result[row["unique_key"]] = {
                "match_status": "matched_invoice" if len(ids) == 1 else "ambiguous" if ids else "outside_invoices",
                "matched_invoice_id": ids[0] if len(ids) == 1 else None,
            }
        return result


def _inventory_query(query: TaxOffsetQuery) -> tuple[str, tuple[Any, ...]]:
    clauses = [SPECIAL_INVOICE_SCOPE_SQL]
    params: list[Any] = [SPECIAL_INVOICE_CODE]
    if query.status != "all":
        clauses.append("c.id is not null" if query.status == "certified" else "c.id is null")
    for year, month, column, sql_type in (
        (query.issue_year, query.issue_month, "i.invoice_date", "date"),
        (query.selection_year, query.selection_month, "c.selection_time", "timestamp"),
    ):
        if year or month:
            start = f"{year}-01-01" if year else f"{month}-01"
            interval = "1 year" if year else "1 month"
            clauses.append(f"{column} >= %s::{sql_type} and {column} < (%s::{sql_type} + interval '{interval}')")
            params.extend([start, start])
    if query.search:
        clauses.append("(i.digital_invoice_no ilike %s escape '\\' or i.invoice_no ilike %s escape '\\' "
                       "or i.invoice_code ilike %s escape '\\' or i.seller_name ilike %s escape '\\' "
                       "or i.seller_tax_no ilike %s escape '\\')")
        escaped = query.search.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        params.extend([f"%{escaped}%"] * 5)
    return f"""with inventory as (
        select i.id::text as id, i.digital_invoice_no, i.invoice_code, i.invoice_no,
               i.invoice_date as issue_date, i.seller_name, i.seller_tax_no,
               i.amount, i.tax_amount, c.deductible_tax_amount, c.selection_time,
               case when c.id is null then 'uncertified' else 'certified' end as certification_status,
               to_char(c.scope_month, 'YYYY-MM') as tax_period,
               jsonb_build_object('invoice_source', {_RAW_INVOICE}->>'invoice_source',
                   'invoice_kind', {_RAW_INVOICE}->>'invoice_kind', 'risk_level', {_RAW_INVOICE}->>'risk_level',
                   'invoice_status_from_source', {_RAW_INVOICE}->>'invoice_status_from_source') as invoice_source_fields,
               jsonb_build_object('source_fields',
                   coalesce(c.raw_payload->'normalized_payload', c.raw_payload)->'source_fields') as certification_source_fields
        from app.invoices i
        left join app.tax_certified_import_records c on c.invoice_id = i.id and c.status = 'active'
        where {' and '.join(clauses)}
    )""", tuple(params)


def load_tax_offset_page(connection: Any, query: TaxOffsetQuery, *, limit_override: int | None = None) -> dict[str, Any]:
    """Caller owns the fixed read snapshot; page and export share filter and ordering."""
    cte, params = _inventory_query(query)
    summaries = connection.fetch_all(cte + """
        select certification_status, count(*) as count, sum(amount) as amount,
               sum(tax_amount) as tax_amount, sum(deductible_tax_amount) as deductible_tax_amount,
               count(*) filter (where amount is null) as missing_amount_count,
               count(*) filter (where tax_amount is null) as missing_tax_count,
               count(*) filter (where deductible_tax_amount is null) as missing_deductible_tax_count
        from inventory group by certification_status""", params)
    summary: dict[str, dict[str, Any]] = {}
    for status in ("certified", "uncertified"):
        group = next((row for row in summaries if row["certification_status"] == status), {})
        summary[status] = {"count": int(group.get("count", 0)), "amount": _money(group.get("amount")),
                           "tax_amount": _money(group.get("tax_amount")),
                           "missing_amount_count": int(group.get("missing_amount_count", 0)),
                           "missing_tax_count": int(group.get("missing_tax_count", 0))}
        if status == "certified":
            summary[status].update(deductible_tax_amount=_money(group.get("deductible_tax_amount")),
                                  missing_deductible_tax_count=int(group.get("missing_deductible_tax_count", 0)))
    total = sum(group["count"] for group in summary.values())
    page = min(query.page, max(1, (total + query.page_size - 1) // query.page_size)) if limit_override is None else 1
    limit = query.page_size if limit_override is None else limit_override
    offset = (page - 1) * query.page_size if limit_override is None else 0
    # Columns and direction are validated enum values, never user SQL fragments.
    ordering = f"{query.sort_by} {query.sort_direction} nulls last, id asc"
    rows = connection.fetch_all(cte + f" select * from inventory order by {ordering} limit %s offset %s",
                                (*params, limit, offset))
    return {"rows": [_row_payload(row, sequence=offset + index) for index, row in enumerate(rows, 1)],
            "total": total,
            "page": page, "page_size": query.page_size, "summary": summary}


def _row_payload(row: dict[str, Any], *, sequence: int) -> dict[str, Any]:
    source = row["invoice_source_fields"] or {}
    certification = row["certification_source_fields"] or {}
    source_fields = certification.get("source_fields") or {}
    result = {key: row[key] for key in ("id", "digital_invoice_no", "invoice_code", "invoice_no", "seller_name",
                                       "seller_tax_no", "certification_status", "tax_period")}
    result.update(sequence=sequence, issue_date=_date_text(row["issue_date"]), selection_time=_date_text(row["selection_time"]),
                  amount=_money(row["amount"]), tax_amount=_money(row["tax_amount"]),
                  deductible_tax_amount=_money(row["deductible_tax_amount"]))
    for key in ("selection_status", "domestic_sales_certificate_no", "invoice_kind_label", "risk_status"):
        result[key] = source_fields.get(key)
    for key in ("invoice_source", "invoice_kind", "risk_level"):
        result[key] = source_fields.get(key) if row["certification_status"] == "certified" else source.get(key)
    result["invoice_status"] = (source_fields.get("invoice_status") if row["certification_status"] == "certified"
                                else source.get("invoice_status_from_source"))
    result["source_fields"] = source_fields
    return result


def _money(value: Any) -> str | None:
    if value is None:
        return None
    amount = Decimal(str(value))
    if amount == amount.quantize(Decimal("0.01")):
        return format(amount, ".2f")
    return format(amount, "f")


def _date_text(value: Any) -> str | None:
    if value is None:
        return None
    return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else str(value)

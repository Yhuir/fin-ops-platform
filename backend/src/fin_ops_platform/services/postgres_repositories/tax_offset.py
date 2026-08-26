from __future__ import annotations

from contextlib import contextmanager
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import re
from typing import Any, Iterator

from fin_ops_platform.services.live_workbench_service import format_decimal
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.tax_offset_service import TaxOffsetService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ZERO = Decimal("0.00")


class PostgresTaxOffsetCanonicalRepository:
    """Load one tax-offset month from canonical tables in one DB snapshot."""

    def __init__(self, connection: Any) -> None:
        if connection is None:
            raise ValueError("Tax offset canonical repository requires a PostgreSQL connection.")
        self._connection = connection

    def load_month_payload(self, month: str) -> dict[str, Any]:
        normalized_month = _normalize_month(month)
        with self._snapshot_transaction() as transaction:
            return load_tax_offset_month(transaction, normalized_month)

    @contextmanager
    def _snapshot_transaction(self) -> Iterator[Any]:
        with self._connection.transaction() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield transaction


class LocalTaxOffsetCanonicalRepository:
    """Canonical local-state adapter used by tests and non-PostgreSQL development."""

    def __init__(self, tax_offset_service: Any) -> None:
        if not callable(getattr(tax_offset_service, "get_month_payload", None)):
            raise ValueError("Tax offset local repository requires a tax offset service.")
        self._tax_offset_service = tax_offset_service

    def load_month_payload(self, month: str) -> dict[str, Any]:
        normalized_month = _normalize_month(month)
        return _finalize_payload(dict(self._tax_offset_service.get_month_payload(normalized_month)))


def load_tax_offset_month(connection: Any, month: str) -> dict[str, Any]:
    """Build a month payload from a caller-owned canonical database snapshot."""

    normalized_month = _normalize_month(month)
    invoice_rows = connection.fetch_all(
        """
        select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
               digital_invoice_no, invoice_date, seller_name, seller_tax_no, buyer_name, buyer_tax_no,
               tax_amount, total_with_tax, amount, tax_rate, raw_payload
        from app.invoices
        where invoice_month = %s::date
          and status <> 'deleted'
        order by invoice_date nulls last, row_id
        """,
        (month_start(normalized_month),),
    )
    certified_rows = connection.fetch_all(
        """
        select certified_unique_key, invoice_no, invoice_code, digital_invoice_no, seller_name, seller_tax_no,
               invoice_date, amount, tax_amount, status, raw_payload
        from app.tax_certified_import_records
        where scope_month = %s::date
          and status <> 'deleted'
        order by invoice_date nulls last, certified_unique_key
        """,
        (month_start(normalized_month),),
    )
    saved_plan_row = connection.fetch_one(
        """
        select selected_output_ids, selected_input_ids
        from app.tax_offset_plans
        where scope_month = %s::date
          and status = 'saved'
        order by updated_at desc, plan_id desc
        limit 1
        """,
        (month_start(normalized_month),),
    )
    output_items: list[dict[str, Any]] = []
    input_items: list[dict[str, Any]] = []
    for row in invoice_rows:
        output = _is_output_invoice(row.get("invoice_type"))
        (output_items if output else input_items).append(_tax_invoice_item(row, output=output))
    certified_items = [_certified_item(row) for row in certified_rows]
    service = TaxOffsetService(
        month_data={
            normalized_month: {
                "output_items": output_items,
                "input_plan_items": input_items,
            }
        },
        certified_records_loader=lambda _requested_month: certified_items,
    )
    payload = dict(service.get_month_payload(normalized_month))
    canonical_snapshot_version = _canonical_snapshot_version(payload)
    if isinstance(saved_plan_row, dict):
        _apply_saved_plan(payload, saved_plan_row, service=service)
    payload["canonical_snapshot_version"] = canonical_snapshot_version
    return _finalize_payload(payload)


def _apply_saved_plan(
    payload: dict[str, Any],
    saved_plan: dict[str, Any],
    *,
    service: TaxOffsetService,
) -> None:
    available_output_ids = {
        str(item.get("id") or "")
        for item in list(payload.get("output_items") or [])
        if isinstance(item, dict)
    }
    locked_input_ids = {
        str(value) for value in list(payload.get("locked_certified_input_ids") or [])
    }
    available_input_ids = {
        str(item.get("id") or "")
        for item in list(payload.get("input_plan_items") or [])
        if isinstance(item, dict) and str(item.get("id") or "") not in locked_input_ids
    }
    selected_output_ids = [
        str(value)
        for value in list(saved_plan.get("selected_output_ids") or [])
        if str(value) in available_output_ids
    ]
    selected_input_ids = [
        str(value)
        for value in list(saved_plan.get("selected_input_ids") or [])
        if str(value) in available_input_ids
    ]
    payload["default_selected_output_ids"] = selected_output_ids
    payload["default_selected_input_ids"] = selected_input_ids
    payload["summary"] = service.calculate_from_month_payload(
        month=str(payload["month"]),
        month_payload=payload,
        selected_output_ids=selected_output_ids,
        selected_input_ids=selected_input_ids,
    )["summary"]


def _finalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    payload["statistics"] = tax_offset_scope_statistics(payload)
    payload.setdefault("canonical_snapshot_version", _canonical_snapshot_version(payload))
    return payload


def _canonical_snapshot_version(payload: dict[str, Any]) -> str:
    canonical_payload = {
        key: payload.get(key)
        for key in (
            "month",
            "output_items",
            "input_plan_items",
            "certified_items",
            "certified_matched_rows",
            "certified_outside_plan_rows",
            "locked_certified_input_ids",
        )
    }
    encoded = json.dumps(
        canonical_payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return f"tax-offset-v1:{sha256(encoded).hexdigest()}"


def _normalize_month(value: Any) -> str:
    month = str(value or "").strip()
    if not MONTH_RE.fullmatch(month):
        raise ValueError("month must be YYYY-MM.")
    return month


def _is_output_invoice(invoice_type: Any) -> bool:
    normalized = str(invoice_type or "").strip().lower()
    return "output" in normalized or "销" in normalized


def _tax_invoice_item(row: dict[str, Any], *, output: bool) -> dict[str, Any]:
    common = {
        "id": str(row.get("row_id") or ""),
        "issue_date": str(row.get("invoice_date") or ""),
        "invoice_no": row.get("invoice_no"),
        "invoice_code": row.get("invoice_code"),
        "digital_invoice_no": row.get("digital_invoice_no"),
        "tax_amount": _money(row.get("tax_amount")),
        "total_with_tax": _money(
            row.get("total_with_tax")
            or ((_decimal(row.get("amount")) or ZERO) + (_decimal(row.get("tax_amount")) or ZERO))
        ),
        "invoice_type": "销项发票" if output else "进项发票",
        "tax_rate": row.get("tax_rate") or "—",
    }
    if output:
        return {
            **common,
            "buyer_name": row.get("buyer_name") or "",
            "buyer_tax_no": row.get("buyer_tax_no"),
        }
    raw_payload = row_payload(row, "raw_payload")
    return {
        **common,
        "seller_name": row.get("seller_name") or "",
        "seller_tax_no": row.get("seller_tax_no"),
        "risk_level": (
            raw_payload.get("risk_level") if isinstance(raw_payload, dict) else None
        )
        or "待评估",
    }


def _certified_item(row: dict[str, Any]) -> dict[str, Any]:
    raw_payload = row_payload(row, "raw_payload")
    return {
        **(raw_payload if isinstance(raw_payload, dict) else {}),
        "id": str(row.get("certified_unique_key") or ""),
        "unique_key": row.get("certified_unique_key"),
        "invoice_no": row.get("invoice_no"),
        "invoice_code": row.get("invoice_code"),
        "digital_invoice_no": row.get("digital_invoice_no"),
        "seller_name": row.get("seller_name"),
        "seller_tax_no": row.get("seller_tax_no"),
        "issue_date": str(row.get("invoice_date") or ""),
        "amount": _money(row.get("amount")),
        "tax_amount": _money(row.get("tax_amount")),
        "status": row.get("status") or "已认证",
    }


def tax_offset_scope_statistics(payload: dict[str, Any]) -> dict[str, int]:
    return {
        "input_invoice_count": len(list(payload.get("input_plan_items") or [])),
        "output_invoice_count": len(list(payload.get("output_items") or [])),
    }


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "—", "--"):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _money(value: Any) -> str:
    return format_decimal(_decimal(value) or ZERO)

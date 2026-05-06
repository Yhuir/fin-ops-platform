from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation
from typing import Callable
from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import Invoice
from fin_ops_platform.services.imports import ImportNormalizationService


ZERO = Decimal("0.00")


class TaxOffsetService:
    def __init__(
        self,
        *,
        import_service: ImportNormalizationService | None = None,
        month_data: dict[str, dict[str, Any]] | None = None,
        certified_records_loader: Callable[[str], list[Any]] | None = None,
        oa_attachment_invoice_rows_loader: Callable[[str], list[dict[str, Any]]] | None = None,
    ) -> None:
        self._import_service = import_service
        self._month_data = month_data or {}
        self._month_data_cache: dict[str, dict[str, Any] | None] = {}
        self._certified_records_loader = certified_records_loader or (lambda month: [])
        self._oa_attachment_invoice_rows_loader = oa_attachment_invoice_rows_loader or (lambda month: [])

    def clear_month_cache(self, months: list[str] | None = None) -> None:
        if months is None:
            self._month_data_cache.clear()
            return
        for month in months:
            self._month_data_cache.pop(month, None)

    def get_month_payload(self, month: str) -> dict[str, object]:
        month_snapshot = self._build_month_snapshot(month)
        default_selected_output_ids = [item["id"] for item in month_snapshot["output_items"]]
        default_selected_input_ids = [
            item["id"] for item in month_snapshot["input_plan_items"] if item["id"] not in month_snapshot["locked_certified_input_ids"]
        ]
        summary = self._calculate_from_month_snapshot(
            month=month,
            month_snapshot=month_snapshot,
            selected_input_ids=default_selected_input_ids,
        )["summary"]
        return {
            "month": month,
            "output_items": month_snapshot["output_items"],
            "input_items": month_snapshot["input_plan_items"],
            "input_plan_items": month_snapshot["input_plan_items"],
            "certified_items": month_snapshot["certified_items"],
            "certified_matched_rows": month_snapshot["certified_matched_rows"],
            "certified_outside_plan_rows": month_snapshot["certified_outside_plan_rows"],
            "locked_certified_input_ids": month_snapshot["locked_certified_input_ids"],
            "default_selected_output_ids": default_selected_output_ids,
            "default_selected_input_ids": default_selected_input_ids,
            "summary": summary,
        }

    def calculate(
        self,
        *,
        month: str,
        selected_output_ids: list[str],
        selected_input_ids: list[str],
    ) -> dict[str, object]:
        month_snapshot = self._build_month_snapshot(month)
        return self._calculate_from_month_snapshot(
            month=month,
            month_snapshot=month_snapshot,
            selected_input_ids=selected_input_ids,
        )

    def _calculate_from_month_snapshot(
        self,
        *,
        month: str,
        month_snapshot: dict[str, Any],
        selected_input_ids: list[str],
    ) -> dict[str, object]:
        locked_ids = set(month_snapshot["locked_certified_input_ids"])
        selected_uncertified_input = [
            item
            for item in month_snapshot["input_plan_items"]
            if item["id"] in selected_input_ids and item["id"] not in locked_ids
        ]
        output_tax = sum((self._to_decimal(item["tax_amount"]) for item in month_snapshot["output_items"]), start=ZERO)
        certified_input_tax = sum((self._certified_tax_amount(item) for item in month_snapshot["certified_items"]), start=ZERO)
        planned_input_tax = sum((self._to_decimal(item["tax_amount"]) for item in selected_uncertified_input), start=ZERO)
        input_tax = certified_input_tax + planned_input_tax
        deductible_tax = min(output_tax, input_tax)
        payable_tax = output_tax - deductible_tax
        carry_forward_tax = input_tax - deductible_tax

        return {
            "month": month,
            "selected_output_ids": [item["id"] for item in month_snapshot["output_items"]],
            "selected_input_ids": list(selected_input_ids),
            "summary": {
                "output_tax": self._format_money(output_tax),
                "certified_input_tax": self._format_money(certified_input_tax),
                "planned_input_tax": self._format_money(planned_input_tax),
                "input_tax": self._format_money(input_tax),
                "deductible_tax": self._format_money(deductible_tax),
                "result_label": "本月应纳税额" if payable_tax > ZERO else "本月留抵税额",
                "result_amount": self._format_money(payable_tax if payable_tax > ZERO else carry_forward_tax),
            },
        }

    def _build_month_snapshot(self, month: str) -> dict[str, Any]:
        month_data = self._resolve_month_data(month)
        output_items = [dict(item) for item in month_data["output_items"]]
        input_plan_items = [dict(item) for item in month_data["input_plan_items"]]
        certified_items = [self._normalize_certified_item(item) for item in self._certified_records_loader(month)]

        input_plan_by_id = {item["id"]: item for item in input_plan_items}
        certified_matched_rows: list[dict[str, Any]] = []
        certified_outside_plan_rows: list[dict[str, Any]] = []
        locked_certified_input_ids: list[str] = []

        for certified_item in certified_items:
            matched_plan_item = self._match_certified_to_plan(certified_item, input_plan_items)
            if matched_plan_item is None:
                certified_outside_plan_rows.append(dict(certified_item))
                continue

            matched_plan_id = matched_plan_item["id"]
            if matched_plan_id not in locked_certified_input_ids:
                locked_certified_input_ids.append(matched_plan_id)
            input_plan_by_id[matched_plan_id]["certified_status"] = "已认证"
            input_plan_by_id[matched_plan_id]["is_locked_certified"] = True

            certified_matched_rows.append(
                {
                    **dict(certified_item),
                    "matched_input_id": matched_plan_id,
                    "matched_invoice_no": matched_plan_item["invoice_no"],
                }
            )

        for input_plan_item in input_plan_items:
            input_plan_item.setdefault("certified_status", "待认证")
            input_plan_item.setdefault("is_locked_certified", False)

        return {
            "output_items": output_items,
            "input_plan_items": input_plan_items,
            "certified_items": certified_items,
            "certified_matched_rows": certified_matched_rows,
            "certified_outside_plan_rows": certified_outside_plan_rows,
            "locked_certified_input_ids": locked_certified_input_ids,
        }

    def summarize_certified_preview_rows(self, month: str, rows: list[Any]) -> dict[str, int]:
        month_data = self._resolve_month_data(month)
        input_plan_items = [dict(item) for item in month_data["input_plan_items"]]
        matched_plan_count = 0
        outside_plan_count = 0

        for row in rows:
            certified_item = self._normalize_certified_item(row)
            if self._match_certified_to_plan(certified_item, input_plan_items) is None:
                outside_plan_count += 1
            else:
                matched_plan_count += 1

        return {
            "matched_plan_count": matched_plan_count,
            "outside_plan_count": outside_plan_count,
        }

    def _resolve_month_data(self, month: str) -> dict[str, Any]:
        if month not in self._month_data_cache:
            real_month_data = self._build_month_data_from_imported_invoices(month)
            self._month_data_cache[month] = deepcopy(real_month_data) if real_month_data is not None else None

        cached_month_data = self._month_data_cache[month]
        if cached_month_data is not None:
            return deepcopy(cached_month_data)

        fallback_month_data = self._month_data.get(
            month,
            {
                "output_items": [],
                "input_plan_items": [],
            },
        )
        return deepcopy(fallback_month_data)

    def _build_month_data_from_imported_invoices(self, month: str) -> dict[str, Any] | None:
        output_items: list[dict[str, Any]] = []
        input_plan_items: list[dict[str, Any]] = []
        found_any = False

        if self._import_service is not None:
            for invoice in self._import_service.list_invoices():
                if not invoice.invoice_date or not invoice.invoice_date.startswith(month):
                    continue
                if invoice.tax_amount is None:
                    continue
                found_any = True
                if invoice.invoice_type == InvoiceType.OUTPUT:
                    output_items.append(self._build_output_item(invoice))
                else:
                    input_plan_items.append(self._build_input_plan_item(invoice))

        for row in self._oa_attachment_invoice_rows_loader(month):
            item = self._build_oa_attachment_invoice_item(row, month)
            if item is None:
                continue
            found_any = True
            if self._is_output_invoice_item(item):
                output_items.append(item)
            else:
                input_plan_items.append(item)

        if not found_any:
            return None
        return {
            "output_items": self._dedupe_tax_items(output_items),
            "input_plan_items": self._dedupe_tax_items(input_plan_items),
        }

    def _build_output_item(self, invoice: Invoice) -> dict[str, Any]:
        return {
            "id": invoice.id,
            "buyer_name": invoice.buyer_name or invoice.counterparty.name,
            "issue_date": invoice.invoice_date or "",
            "invoice_no": invoice.invoice_no,
            "tax_rate": invoice.tax_rate or "—",
            "tax_amount": self._format_money(invoice.tax_amount or ZERO),
            "total_with_tax": self._format_money(self._resolve_total_with_tax(invoice)),
            "invoice_type": self._resolve_invoice_display_type(invoice),
            "invoice_code": invoice.invoice_code,
            "digital_invoice_no": invoice.digital_invoice_no,
            "buyer_tax_no": invoice.buyer_tax_no,
            "seller_tax_no": invoice.seller_tax_no,
        }

    def _build_input_plan_item(self, invoice: Invoice) -> dict[str, Any]:
        return {
            "id": invoice.id,
            "seller_name": invoice.seller_name or invoice.counterparty.name,
            "seller_tax_no": invoice.seller_tax_no,
            "issue_date": invoice.invoice_date or "",
            "invoice_no": invoice.invoice_no,
            "invoice_code": invoice.invoice_code,
            "digital_invoice_no": invoice.digital_invoice_no,
            "tax_amount": self._format_money(invoice.tax_amount or ZERO),
            "total_with_tax": self._format_money(self._resolve_total_with_tax(invoice)),
            "risk_level": invoice.risk_level or "待评估",
            "invoice_type": self._resolve_invoice_display_type(invoice),
            "tax_rate": invoice.tax_rate or "—",
        }

    def _build_oa_attachment_invoice_item(self, row: dict[str, Any], month: str) -> dict[str, Any] | None:
        if row.get("source_kind") != "oa_attachment_invoice":
            return None
        issue_date = self._clean_optional(row.get("issue_date")) or self._clean_row_detail(row, "开票日期")
        if not issue_date or not issue_date.startswith(month):
            return None

        tax_amount = self._format_optional_money(row.get("tax_amount"))
        if tax_amount is None:
            return None

        total_with_tax = self._format_optional_money(row.get("total_with_tax")) or self._format_optional_money(row.get("amount"))
        if total_with_tax is None:
            total_with_tax = tax_amount

        invoice_no = (
            self._clean_optional(row.get("invoice_no"))
            or self._clean_row_detail(row, "发票号码")
            or self._clean_optional(row.get("digital_invoice_no"))
            or self._clean_row_detail(row, "数电发票号码")
            or str(row.get("id") or "oa-attachment-invoice")
        )
        invoice_code = self._clean_optional(row.get("invoice_code")) or self._clean_row_detail(row, "发票代码")
        digital_invoice_no = self._clean_optional(row.get("digital_invoice_no")) or self._clean_row_detail(row, "数电发票号码")
        invoice_type = self._clean_optional(row.get("invoice_type")) or "进项发票"

        return {
            "id": str(row.get("id") or f"oa-attachment-invoice:{invoice_no}"),
            "buyer_name": self._clean_optional(row.get("buyer_name")) or "",
            "buyer_tax_no": self._clean_optional(row.get("buyer_tax_no")),
            "seller_name": self._clean_optional(row.get("seller_name")) or "",
            "seller_tax_no": self._clean_optional(row.get("seller_tax_no")),
            "issue_date": issue_date,
            "invoice_no": invoice_no,
            "invoice_code": invoice_code,
            "digital_invoice_no": digital_invoice_no,
            "tax_amount": tax_amount,
            "total_with_tax": total_with_tax,
            "risk_level": self._clean_row_detail(row, "发票风险等级") or "待评估",
            "invoice_type": invoice_type,
            "tax_rate": self._clean_optional(row.get("tax_rate")) or "—",
            "source_kind": "oa_attachment_invoice",
            "derived_from_oa_id": self._clean_optional(row.get("derived_from_oa_id")),
        }

    @staticmethod
    def _is_output_invoice_item(item: dict[str, Any]) -> bool:
        return "销" in str(item.get("invoice_type") or "")

    @classmethod
    def _dedupe_tax_items(cls, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, ...]] = set()
        for item in items:
            key = cls._tax_item_identity_key(item)
            if key in seen_keys:
                continue
            seen_keys.add(key)
            deduped.append(item)
        return deduped

    @classmethod
    def _tax_item_identity_key(cls, item: dict[str, Any]) -> tuple[str, ...]:
        digital_invoice_no = cls._clean_optional(item.get("digital_invoice_no"))
        if digital_invoice_no:
            return ("digital", digital_invoice_no)
        invoice_code = cls._clean_optional(item.get("invoice_code"))
        invoice_no = cls._clean_optional(item.get("invoice_no"))
        if invoice_code and invoice_no:
            return ("code-number", invoice_code, invoice_no)
        return (
            "fallback",
            invoice_no or cls._clean_optional(item.get("id")) or "",
            cls._clean_optional(item.get("seller_tax_no")) or "",
            cls._clean_optional(item.get("issue_date")) or "",
            cls._clean_optional(item.get("tax_amount")) or "",
        )

    @classmethod
    def _clean_row_detail(cls, row: dict[str, Any], key: str) -> str | None:
        detail_fields = row.get("detail_fields") or row.get("_detail_fields")
        if not isinstance(detail_fields, dict):
            return None
        return cls._clean_optional(detail_fields.get(key))

    @staticmethod
    def _clean_optional(value: Any) -> str | None:
        if value is None:
            return None
        cleaned = str(value).strip()
        if cleaned in {"", "—", "--", "None"}:
            return None
        return cleaned

    def _format_optional_money(self, value: Any) -> str | None:
        cleaned = self._clean_optional(value)
        if cleaned is None:
            return None
        try:
            return self._format_money(self._to_decimal(cleaned))
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _resolve_total_with_tax(invoice: Invoice) -> Decimal:
        if invoice.total_with_tax is not None:
            return invoice.total_with_tax
        tax_amount = invoice.tax_amount or ZERO
        return invoice.amount + tax_amount

    @staticmethod
    def _resolve_invoice_display_type(invoice: Invoice) -> str:
        raw_kind = (invoice.invoice_kind or "").strip()
        if raw_kind:
            if raw_kind.startswith("进项") or raw_kind.startswith("销项") or "发票" in raw_kind:
                return raw_kind
            prefix = "销项" if invoice.invoice_type == InvoiceType.OUTPUT else "进项"
            return f"{prefix}{raw_kind}"
        return "销项发票" if invoice.invoice_type == InvoiceType.OUTPUT else "进项发票"

    def _match_certified_to_plan(
        self,
        certified_item: dict[str, Any],
        input_plan_items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        certified_digital_invoice_no = certified_item.get("digital_invoice_no")
        if certified_digital_invoice_no:
            for input_plan_item in input_plan_items:
                if input_plan_item.get("digital_invoice_no") == certified_digital_invoice_no:
                    return input_plan_item

        certified_invoice_code = certified_item.get("invoice_code")
        certified_invoice_no = certified_item.get("invoice_no")
        if certified_invoice_code and certified_invoice_no:
            for input_plan_item in input_plan_items:
                if (
                    input_plan_item.get("invoice_code") == certified_invoice_code
                    and input_plan_item.get("invoice_no") == certified_invoice_no
                ):
                    return input_plan_item

        for input_plan_item in input_plan_items:
            certified_seller_tax_no = certified_item.get("seller_tax_no")
            seller_matches = False
            if certified_seller_tax_no and input_plan_item.get("seller_tax_no") == certified_seller_tax_no:
                seller_matches = True
            elif input_plan_item.get("seller_name") == certified_item.get("seller_name"):
                seller_matches = True
            plan_tax_amount = input_plan_item.get("tax_amount")
            certified_tax_amount = certified_item.get("tax_amount")
            tax_amount_matches = False
            if plan_tax_amount not in (None, "") and certified_tax_amount not in (None, ""):
                tax_amount_matches = self._to_decimal(str(plan_tax_amount)) == self._to_decimal(str(certified_tax_amount))
            if (
                seller_matches
                and input_plan_item.get("issue_date") == certified_item.get("issue_date")
                and tax_amount_matches
            ):
                return input_plan_item
        return None

    def _normalize_certified_item(self, raw_item: Any) -> dict[str, Any]:
        item = self._serialize_container(raw_item)
        amount = item.get("amount")
        tax_amount = item.get("tax_amount")
        total_with_tax = item.get("total_with_tax")
        if total_with_tax in (None, "") and amount not in (None, "") and tax_amount not in (None, ""):
            total_with_tax = self._format_money(self._to_decimal(str(amount)) + self._to_decimal(str(tax_amount)))
        return {
            "id": item.get("id") or item.get("unique_key") or item.get("invoice_no") or item.get("digital_invoice_no") or "certified",
            "unique_key": item.get("unique_key"),
            "digital_invoice_no": item.get("digital_invoice_no"),
            "invoice_code": item.get("invoice_code"),
            "invoice_no": item.get("invoice_no"),
            "seller_tax_no": item.get("seller_tax_no"),
            "seller_name": item.get("seller_name"),
            "issue_date": item.get("issue_date"),
            "amount": amount,
            "tax_amount": tax_amount,
            "deductible_tax_amount": item.get("deductible_tax_amount"),
            "total_with_tax": total_with_tax or tax_amount or "0.00",
            "status": item.get("status") or item.get("selection_status") or "已认证",
            "selection_status": item.get("selection_status"),
            "invoice_status": item.get("invoice_status"),
        }

    def _certified_tax_amount(self, certified_item: dict[str, Any]) -> Decimal:
        deductible_tax_amount = certified_item.get("deductible_tax_amount")
        if deductible_tax_amount not in (None, ""):
            return self._to_decimal(str(deductible_tax_amount))
        return self._to_decimal(str(certified_item.get("tax_amount") or "0.00"))

    @staticmethod
    def _serialize_container(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return dict(value)
        if hasattr(value, "__dataclass_fields__"):
            return {
                key: getattr(value, key)
                for key in value.__dataclass_fields__  # type: ignore[attr-defined]
            }
        raise TypeError("Unsupported certified record payload.")

    @staticmethod
    def _to_decimal(value: str) -> Decimal:
        return Decimal(value.replace(",", ""))

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value:,.2f}"

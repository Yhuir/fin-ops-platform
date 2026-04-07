from __future__ import annotations

from decimal import Decimal
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
    ) -> None:
        self._import_service = import_service
        self._month_data = month_data or {
            "2026-03": {
                "output_items": [
                    {
                        "id": "to-202603-001",
                        "buyer_name": "华东项目甲方",
                        "issue_date": "2026-03-25",
                        "invoice_no": "90342011",
                        "tax_rate": "13%",
                        "tax_amount": "41,600.00",
                        "total_with_tax": "361,600.00",
                        "invoice_type": "销项专票",
                    }
                ],
                "input_plan_items": [
                    {
                        "id": "ti-202603-001",
                        "seller_name": "设备供应商",
                        "issue_date": "2026-03-22",
                        "invoice_no": "11203490",
                        "tax_rate": "13%",
                        "tax_amount": "12,480.00",
                        "total_with_tax": "108,480.00",
                        "risk_level": "低",
                    },
                    {
                        "id": "ti-202603-002",
                        "seller_name": "集成服务商",
                        "issue_date": "2026-03-24",
                        "invoice_no": "11203491",
                        "tax_rate": "6%",
                        "tax_amount": "5,760.00",
                        "total_with_tax": "101,760.00",
                        "risk_level": "中",
                    },
                ],
            },
            "2026-04": {
                "output_items": [
                    {
                        "id": "to-202604-001",
                        "buyer_name": "智能工厂客户",
                        "issue_date": "2026-04-08",
                        "invoice_no": "90352011",
                        "tax_rate": "13%",
                        "tax_amount": "18,200.00",
                        "total_with_tax": "158,200.00",
                        "invoice_type": "销项专票",
                    },
                    {
                        "id": "to-202604-002",
                        "buyer_name": "项目维保客户",
                        "issue_date": "2026-04-18",
                        "invoice_no": "90352012",
                        "tax_rate": "6%",
                        "tax_amount": "4,800.00",
                        "total_with_tax": "84,800.00",
                        "invoice_type": "销项普票",
                    },
                ],
                "input_plan_items": [
                    {
                        "id": "ti-202604-001",
                        "seller_name": "系统设备商",
                        "issue_date": "2026-04-09",
                        "invoice_no": "21203490",
                        "tax_rate": "13%",
                        "tax_amount": "10,920.00",
                        "total_with_tax": "94,920.00",
                        "risk_level": "低",
                    },
                    {
                        "id": "ti-202604-002",
                        "seller_name": "实施外包服务商",
                        "issue_date": "2026-04-16",
                        "invoice_no": "21203491",
                        "tax_rate": "6%",
                        "tax_amount": "9,600.00",
                        "total_with_tax": "169,600.00",
                        "risk_level": "中",
                    },
                    {
                        "id": "ti-202604-003",
                        "seller_name": "办公耗材商",
                        "issue_date": "2026-04-20",
                        "invoice_no": "21203492",
                        "tax_rate": "13%",
                        "tax_amount": "2,340.00",
                        "total_with_tax": "20,340.00",
                        "risk_level": "低",
                    },
                ],
            },
        }
        self._certified_records_loader = certified_records_loader or (lambda month: [])

    def get_month_payload(self, month: str) -> dict[str, object]:
        month_snapshot = self._build_month_snapshot(month)
        default_selected_output_ids = [item["id"] for item in month_snapshot["output_items"]]
        default_selected_input_ids = [
            item["id"] for item in month_snapshot["input_plan_items"] if item["id"] not in month_snapshot["locked_certified_input_ids"]
        ]
        summary = self.calculate(
            month=month,
            selected_output_ids=default_selected_output_ids,
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
        real_month_data = self._build_month_data_from_imported_invoices(month)
        if real_month_data is not None:
            return real_month_data
        return self._month_data.get(
            month,
            {
                "output_items": [],
                "input_plan_items": [],
            },
        )

    def _build_month_data_from_imported_invoices(self, month: str) -> dict[str, Any] | None:
        if self._import_service is None:
            return None

        output_items: list[dict[str, Any]] = []
        input_plan_items: list[dict[str, Any]] = []
        found_any = False

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

        if not found_any:
            return None
        return {
            "output_items": output_items,
            "input_plan_items": input_plan_items,
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

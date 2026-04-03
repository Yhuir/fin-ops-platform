from __future__ import annotations

from decimal import Decimal
from typing import Any


ZERO = Decimal("0.00")


class TaxOffsetService:
    def __init__(self) -> None:
        self._month_data = {
            "2026-03": {
                "output_items": [
                    {
                        "id": "to-202603-001",
                        "buyer_name": "华东项目甲方",
                        "issue_date": "2026-03-25",
                        "invoice_no": "90342011",
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
                        "tax_amount": "12,480.00",
                        "total_with_tax": "108,480.00",
                        "risk_level": "低",
                    },
                    {
                        "id": "ti-202603-002",
                        "seller_name": "集成服务商",
                        "issue_date": "2026-03-24",
                        "invoice_no": "11203491",
                        "tax_amount": "5,760.00",
                        "total_with_tax": "101,760.00",
                        "risk_level": "中",
                    },
                ],
                "certified_items": [
                    {
                        "id": "tc-202603-001",
                        "seller_name": "设备供应商",
                        "issue_date": "2026-03-22",
                        "invoice_no": "11203490",
                        "tax_amount": "12,480.00",
                        "total_with_tax": "108,480.00",
                        "status": "已认证",
                    },
                    {
                        "id": "tc-202603-099",
                        "seller_name": "物业服务商",
                        "issue_date": "2026-03-28",
                        "invoice_no": "11203999",
                        "tax_amount": "1,600.00",
                        "total_with_tax": "13,600.00",
                        "status": "已认证",
                    }
                ],
            },
            "2026-04": {
                "output_items": [
                    {
                        "id": "to-202604-001",
                        "buyer_name": "智能工厂客户",
                        "issue_date": "2026-04-08",
                        "invoice_no": "90352011",
                        "tax_amount": "18,200.00",
                        "total_with_tax": "158,200.00",
                        "invoice_type": "销项专票",
                    },
                    {
                        "id": "to-202604-002",
                        "buyer_name": "项目维保客户",
                        "issue_date": "2026-04-18",
                        "invoice_no": "90352012",
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
                        "tax_amount": "10,920.00",
                        "total_with_tax": "94,920.00",
                        "risk_level": "低",
                    },
                    {
                        "id": "ti-202604-002",
                        "seller_name": "实施外包服务商",
                        "issue_date": "2026-04-16",
                        "invoice_no": "21203491",
                        "tax_amount": "9,600.00",
                        "total_with_tax": "169,600.00",
                        "risk_level": "中",
                    },
                    {
                        "id": "ti-202604-003",
                        "seller_name": "办公耗材商",
                        "issue_date": "2026-04-20",
                        "invoice_no": "21203492",
                        "tax_amount": "2,340.00",
                        "total_with_tax": "20,340.00",
                        "risk_level": "低",
                    },
                ],
                "certified_items": [
                    {
                        "id": "tc-202604-001",
                        "seller_name": "系统设备商",
                        "issue_date": "2026-04-09",
                        "invoice_no": "21203490",
                        "tax_amount": "10,920.00",
                        "total_with_tax": "94,920.00",
                        "status": "已认证",
                    },
                    {
                        "id": "tc-202604-099",
                        "seller_name": "外部物业服务商",
                        "issue_date": "2026-04-21",
                        "invoice_no": "21203999",
                        "tax_amount": "1,280.00",
                        "total_with_tax": "21,280.00",
                        "status": "已认证",
                    },
                ],
            },
        }

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
        certified_input_tax = sum((self._to_decimal(item["tax_amount"]) for item in month_snapshot["certified_items"]), start=ZERO)
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
        month_data = self._month_data.get(
            month,
            {
                "output_items": [],
                "input_plan_items": [],
                "certified_items": [],
            },
        )
        output_items = [dict(item) for item in month_data["output_items"]]
        input_plan_items = [dict(item) for item in month_data["input_plan_items"]]
        certified_items = [dict(item) for item in month_data.get("certified_items", [])]

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

    def _match_certified_to_plan(
        self,
        certified_item: dict[str, str],
        input_plan_items: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        certified_invoice_no = certified_item.get("invoice_no")
        if certified_invoice_no:
            for input_plan_item in input_plan_items:
                if input_plan_item.get("invoice_no") == certified_invoice_no:
                    return input_plan_item

        for input_plan_item in input_plan_items:
            if (
                input_plan_item.get("seller_name") == certified_item.get("seller_name")
                and input_plan_item.get("issue_date") == certified_item.get("issue_date")
                and input_plan_item.get("tax_amount") == certified_item.get("tax_amount")
            ):
                return input_plan_item
        return None

    @staticmethod
    def _to_decimal(value: str) -> Decimal:
        return Decimal(value.replace(",", ""))

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value:,.2f}"

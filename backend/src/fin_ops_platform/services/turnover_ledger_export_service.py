from __future__ import annotations

from collections.abc import Callable
from datetime import date
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font

XLSX_MIME_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
EXPORT_COLUMNS = [
    "序号",
    "行类型",
    "源银行流水ID",
    "流水方向",
    "流水金额",
    "往来大类",
    "对方户名",
    "待还款金额",
    "待收款金额",
    "余额",
    "借款金额",
    "借款日",
    "还款金额",
    "还款日",
    "对方开户机构",
    "还款备注",
    "利率类型",
    "利率值",
    "已还利息额",
    "借款天数",
    "应还利息",
    "还利息日期",
    "还利息方式",
    "备注",
    "关系状态",
    "流水标签",
    "往来标记",
]
FAMILY_SCOPE_LABELS = {
    "all": "全部",
    "personal": "个人往来",
    "company": "公司往来",
    "bank": "银行往来",
    "business": "业务往来",
}
MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")
TURNOVER_LEDGER_EXPORT_ROW_LIMIT = 20000


class TurnoverLedgerExportLimitError(ValueError):
    def __init__(self, *, total: int, limit: int = TURNOVER_LEDGER_EXPORT_ROW_LIMIT) -> None:
        super().__init__(f"当前筛选命中 {total} 行，超过 {limit} 行导出上限，请缩小筛选范围。")
        self.error_code = "turnover_ledger_export_row_limit_exceeded"
        self.details = {"total": total, "limit": limit}


class TurnoverLedgerExportService:
    def __init__(self, grouped_ledger_loader: Callable[..., dict[str, Any]]) -> None:
        self._grouped_ledger_loader = grouped_ledger_loader

    def export_summary(self, *, family: str = "all", query: str = "", settlement_status: str = "all") -> dict[str, int]:
        normalized_family = self._normalize_family(family)
        return self._grouped_ledger_loader(family=normalized_family, query=query,
                                          settlement_status=settlement_status, count_only=True)

    def export(self, *, family: str = "all", today: date | None = None, query: str = "", settlement_status: str = "all") -> tuple[str, bytes, int]:
        normalized_family = self._normalize_family(family)
        grouped_payload = self._grouped_ledger_loader(family=normalized_family, query=query, settlement_status=settlement_status, paginate=False)
        self._ensure_export_group_limit(grouped_payload)
        rows = self._formal_rows(grouped_payload, family=normalized_family)
        self._ensure_export_row_limit(len(rows))
        workbook = self._build_workbook(rows)
        scope = FAMILY_SCOPE_LABELS.get(normalized_family, FAMILY_SCOPE_LABELS["all"])
        filename = f"往来款台账-{scope}-{(today or date.today()).isoformat()}.xlsx"
        return filename, self._serialize_workbook(workbook), sum(1 for group in grouped_payload["groups"] if normalized_family == "all" or group["family"] == normalized_family)

    def _formal_rows(self, grouped_payload: dict[str, Any], *, family: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        sequence = 1
        for group in list(grouped_payload.get("groups") or []):
            if not isinstance(group, dict):
                continue
            group_family = str(group.get("family") or "").strip().lower()
            if family != "all" and group_family != family:
                continue
            for row_type, row in self._export_rows_for_group(group):
                rows.append(self._formal_row(sequence, group, row, row_type=row_type))
                sequence += 1
        return rows

    def _formal_row(self, sequence: int, group: dict[str, Any], row: dict[str, Any], *, row_type: str) -> dict[str, Any]:
        balance_amount = self._balance_amount(group, row)
        pending_repayment, pending_collection = self._pending_amounts(group, row, balance_amount=balance_amount)
        normalized_row_type = "flow" if row_type == "flow" else "summary"
        source_bank_row_id = str(row.get("source_bank_row_id") or "") if normalized_row_type == "flow" else ""
        flow_direction = str(row.get("flow_direction") or "") if normalized_row_type == "flow" else ""
        flow_amount = (
            self._format_money(self._money(row.get("flow_amount"))) if normalized_row_type == "flow" else "0.00"
        )
        return {
            "序号": sequence,
            "行类型": "真实流水" if normalized_row_type == "flow" else "合计",
            "源银行流水ID": source_bank_row_id,
            "流水方向": flow_direction,
            "流水金额": flow_amount,
            "往来大类": str(group.get("family_label") or row.get("family_label") or ""),
            "对方户名": str(group.get("counterparty_name") or row.get("counterparty_name") or ""),
            "待还款金额": self._format_money(pending_repayment),
            "待收款金额": self._format_money(pending_collection),
            "余额": self._format_money(balance_amount),
            "借款金额": self._format_money(self._money(row.get("borrow_amount", row.get("principal_amount")))),
            "借款日": self._date_text(row.get("borrow_date", row.get("first_transaction_at"))),
            "还款金额": self._format_money(self._money(row.get("repayment_amount", row.get("settled_amount")))),
            "还款日": self._date_text(row.get("repayment_date", row.get("last_settlement_at"))),
            "对方开户机构": self._counterparty_bank_name(row),
            "还款备注": str(row.get("repayment_remark") or row.get("summary_text") or ""),
            "利率类型": self._interest_rate_type_label(row.get("interest_rate_type")),
            "利率值": str(row.get("interest_rate_value") or row.get("annual_interest_rate") or "0.000000"),
            "已还利息额": self._format_money(self._money(row.get("interest_paid_amount"))),
            "借款天数": row.get("loan_days") if row.get("loan_days") is not None else "",
            "应还利息": self._format_money(self._money(row.get("accrued_interest"))),
            "还利息日期": self._date_text(row.get("interest_paid_date")),
            "还利息方式": str(row.get("interest_payment_method") or ""),
            "备注": str(row.get("note") or ""),
            "关系状态": str(row.get("status_label") or row.get("status") or ""),
            "流水标签": " / ".join(row.get("category_label_path") or []) if normalized_row_type == "flow" else "",
            "往来标记": str(row.get("turnover_action_label") or "") if normalized_row_type == "flow" else "",
            "row_type": normalized_row_type,
            "lot_id": "",
            "source_bank_row_id": source_bank_row_id,
            "flow_direction": flow_direction,
            "flow_amount": flow_amount,
            "balance_amount": self._format_money(balance_amount),
        }

    @classmethod
    def _export_rows_for_group(cls, group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        summary = group.get("summary_row")
        flow_rows = cls._deduplicated_flow_rows(group.get("flow_rows"))
        if isinstance(summary, dict):
            return [("summary", dict(summary)), *(("flow", row) for row in flow_rows)]
        raise ValueError("往来导出分组缺少 summary_row")

    @staticmethod
    def _ensure_export_group_limit(grouped_payload: dict[str, Any]) -> None:
        pagination = grouped_payload.get("pagination") if isinstance(grouped_payload.get("pagination"), dict) else {}
        try:
            total = int(pagination.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        if total > TURNOVER_LEDGER_EXPORT_ROW_LIMIT:
            raise TurnoverLedgerExportLimitError(total=total)

    @staticmethod
    def _ensure_export_row_limit(total: int) -> None:
        if total > TURNOVER_LEDGER_EXPORT_ROW_LIMIT:
            raise TurnoverLedgerExportLimitError(total=total)

    @staticmethod
    def _deduplicated_flow_rows(value: Any) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen_source_ids: set[str] = set()
        for row in list(value or []):
            if not isinstance(row, dict):
                continue
            source_bank_row_id = str(row.get("source_bank_row_id") or "").strip()
            if source_bank_row_id:
                if source_bank_row_id in seen_source_ids:
                    continue
                seen_source_ids.add(source_bank_row_id)
            rows.append(dict(row))
        return rows

    def _pending_amounts(
        self,
        group: dict[str, Any],
        row: dict[str, Any],
        *,
        balance_amount: Decimal,
    ) -> tuple[Decimal, Decimal]:
        business_type = str(row.get("business_type") or "").strip()
        pending_direction = str(group.get("pending_direction") or "").strip()
        if business_type == "borrow_in" or pending_direction == "repayment":
            return balance_amount, ZERO
        if business_type in {"borrow_out", "business_receivable"} or pending_direction == "collection":
            return ZERO, balance_amount
        return ZERO, ZERO

    def _balance_amount(self, group: dict[str, Any], row: dict[str, Any]) -> Decimal:
        if self._has_value(row.get("balance_amount")):
            return self._money(row.get("balance_amount"))
        return self._money(group.get("pending_amount"))

    @staticmethod
    def _build_workbook(rows: list[dict[str, Any]]) -> Workbook:
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "往来款台账"
        sheet.append(EXPORT_COLUMNS)
        for row in rows:
            sheet.append([row.get(column, "") for column in EXPORT_COLUMNS])
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        widths = {
            "A": 8,
            "B": 10,
            "C": 18,
            "D": 14,
            "E": 18,
            "F": 14,
            "G": 14,
            "H": 14,
            "I": 14,
            "J": 18,
            "K": 24,
            "L": 12,
            "M": 12,
            "N": 14,
            "O": 12,
            "P": 14,
            "Q": 14,
            "R": 16,
            "S": 24,
            "T": 14,
            "U": 14,
            "V": 16,
            "W": 24,
        }
        for column, width in widths.items():
            sheet.column_dimensions[column].width = width
        return workbook

    @staticmethod
    def _serialize_workbook(workbook: Workbook) -> bytes:
        buffer = BytesIO()
        workbook.save(buffer)
        return buffer.getvalue()

    @staticmethod
    def _has_value(value: Any) -> bool:
        return value is not None and str(value).strip() != ""

    @staticmethod
    def _counterparty_bank_name(row: dict[str, Any]) -> str:
        explicit = str(row.get("counterparty_bank_name") or "").strip()
        if explicit:
            return explicit
        labels = row.get("bank_account_labels")
        if isinstance(labels, list):
            return " / ".join(str(label) for label in labels if str(label).strip())
        return ""

    @staticmethod
    def _interest_rate_type_label(value: Any) -> str:
        normalized = str(value or "none").strip().lower()
        return {"annual": "年利率", "monthly": "月利率", "none": "无息"}.get(normalized, normalized)

    @staticmethod
    def _date_text(value: Any) -> str:
        text = str(value or "").strip()
        return text[:10] if text else ""

    @staticmethod
    def _normalize_family(family: str | None) -> str:
        normalized = str(family or "all").strip().lower()
        if normalized not in FAMILY_SCOPE_LABELS:
            raise ValueError("往来分类无效")
        return normalized

    @staticmethod
    def _money(value: Any) -> Decimal:
        if value is None:
            return ZERO
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO
        try:
            return Decimal(text).quantize(MONEY_QUANT)
        except (InvalidOperation, ValueError):
            return ZERO

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value.quantize(MONEY_QUANT):.2f}"

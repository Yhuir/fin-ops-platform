from __future__ import annotations

from collections import Counter
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import MatchingResultType
from fin_ops_platform.domain.models import BankTransaction, Invoice, MatchingResult
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService


ZERO = Decimal("0.00")
DEFAULT_COMPANY_NAME = "溯源科技有限公司"
LEGACY_DEMO_TRANSACTION_SOURCES = {"bank_transaction.json"}


class LiveWorkbenchService:
    def __init__(
        self,
        import_service: ImportNormalizationService,
        matching_service: MatchingEngineService,
        *,
        bank_account_resolver: BankAccountResolver | None = None,
    ) -> None:
        self._import_service = import_service
        self._matching_service = matching_service
        self._bank_account_resolver = bank_account_resolver or BankAccountResolver()
        self._detail_rows_by_id: dict[str, dict[str, Any]] = {}
        self._company_identity: tuple[str, str | None] = (DEFAULT_COMPANY_NAME, None)

    def has_rows_for_month(self, month: str) -> bool:
        return any(invoice.invoice_date and invoice.invoice_date.startswith(month) for invoice in self._import_service.list_invoices()) or any(
            transaction.txn_date and transaction.txn_date.startswith(month) for transaction in self._import_service.list_transactions()
        )

    def get_workbench(self, month: str) -> dict[str, Any]:
        self._rebuild_cache()

        paired: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        open_rows: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}

        for row in self._detail_rows_by_id.values():
            row_month = row.get("_month")
            if row_month != month:
                continue
            (paired if row["_section"] == "paired" else open_rows)[row["type"]].append(self._serialize_row(row))

        month_rows = [*paired["bank"], *paired["invoice"], *open_rows["bank"], *open_rows["invoice"]]
        return {
            "month": month,
            "summary": {
                "oa_count": 0,
                "bank_count": len(paired["bank"]) + len(open_rows["bank"]),
                "invoice_count": len(paired["invoice"]) + len(open_rows["invoice"]),
                "paired_count": len(paired["bank"]) + len(paired["invoice"]),
                "open_count": len(open_rows["bank"]) + len(open_rows["invoice"]),
                "exception_count": sum(1 for row in month_rows if row.get("invoice_relation", row.get("invoice_bank_relation", {})).get("tone") == "danger"),
            },
            "paired": paired,
            "open": open_rows,
        }

    def get_row_detail(self, row_id: str) -> dict[str, Any]:
        self._rebuild_cache()
        row = self._detail_rows_by_id.get(row_id)
        if row is None:
            raise KeyError(row_id)
        payload = self._serialize_row(row)
        payload["summary_fields"] = dict(row["_summary_fields"])
        payload["detail_fields"] = dict(row["_detail_fields"])
        return payload

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def _build_bank_row(self, transaction: BankTransaction, result: MatchingResult | None) -> dict[str, Any]:
        relation = relation_from_result(result)
        section = "paired" if result and result.result_type == MatchingResultType.AUTOMATIC_MATCH else "open"
        payment_account_label = self._bank_account_resolver.resolve_label(transaction.account_no, transaction.account_name)
        direction_label = "支出" if transaction.txn_direction.value == "outflow" else "收入"
        account_field_label = "支付账户" if transaction.txn_direction.value == "outflow" else "收款账户"
        return {
            "id": transaction.id,
            "type": "bank",
            "case_id": result.id if result else None,
            "direction": direction_label,
            "trade_time": transaction.trade_time,
            "debit_amount": format_decimal(transaction.amount) if transaction.txn_direction.value == "outflow" else "",
            "credit_amount": format_decimal(transaction.amount) if transaction.txn_direction.value == "inflow" else "",
            "counterparty_name": transaction.counterparty_name_raw,
            "payment_account_label": payment_account_label,
            "invoice_relation": relation,
            "pay_receive_time": transaction.pay_receive_time or transaction.trade_time,
            "remark": transaction.remark or transaction.summary or "",
            "repayment_date": "",
            "available_actions": self._available_actions("bank", section),
            "_month": transaction.txn_date[:7] if transaction.txn_date else "",
            "_section": section,
            "_summary_fields": {
                "资金方向": direction_label,
                "交易时间": transaction.trade_time or "--",
                "借方发生额": format_decimal(transaction.amount) if transaction.txn_direction.value == "outflow" else "—",
                "贷方发生额": format_decimal(transaction.amount) if transaction.txn_direction.value == "inflow" else "—",
                "对方户名": transaction.counterparty_name_raw,
                account_field_label: payment_account_label,
                "和发票关联情况": relation["label"],
                "支付/收款时间": transaction.pay_receive_time or transaction.trade_time or "--",
                "备注": transaction.remark or transaction.summary or "—",
                "还借款日期": "—",
            },
            "_detail_fields": {
                "资金方向": direction_label,
                "账号": transaction.account_no,
                "账户名称": transaction.account_name or "—",
                "余额": format_decimal(transaction.balance) if transaction.balance is not None else "—",
                "币种": transaction.currency or "CNY",
                "对方账号": transaction.counterparty_account_no or "—",
                "对方开户机构": transaction.counterparty_bank_name or "—",
                "记账日期": transaction.booked_date or transaction.txn_date or "—",
                "摘要": transaction.summary or "—",
                "备注": transaction.remark or "—",
                "账户明细编号-交易流水号": transaction.account_detail_no or "—",
                "企业流水号": transaction.enterprise_serial_no or "—",
                "凭证种类": transaction.voucher_kind or "—",
                "凭证号": transaction.voucher_no or "—",
            },
        }

    def _build_invoice_row(self, invoice: Invoice, result: MatchingResult | None) -> dict[str, Any]:
        relation = relation_from_result(result)
        section = "paired" if result and result.result_type == MatchingResultType.AUTOMATIC_MATCH else "open"
        seller_name, buyer_name = self._resolve_invoice_parties(invoice)
        seller_tax_no, buyer_tax_no = self._resolve_invoice_tax_nos(invoice)
        return {
            "id": invoice.id,
            "type": "invoice",
            "case_id": result.id if result else None,
            "seller_tax_no": seller_tax_no,
            "seller_name": seller_name,
            "buyer_tax_no": buyer_tax_no,
            "buyer_name": buyer_name,
            "issue_date": invoice.invoice_date,
            "amount": format_decimal(invoice.amount),
            "tax_rate": invoice.tax_rate or "—",
            "tax_amount": format_decimal(invoice.tax_amount) if invoice.tax_amount is not None else "—",
            "total_with_tax": format_decimal(invoice.total_with_tax) if invoice.total_with_tax is not None else "—",
            "invoice_type": "销项发票" if invoice.invoice_type.value == "output" else "进项发票",
            "invoice_bank_relation": relation,
            "available_actions": self._available_actions("invoice", section),
            "_month": invoice.invoice_date[:7] if invoice.invoice_date else "",
            "_section": section,
            "_summary_fields": {
                "销方识别号": seller_tax_no or "—",
                "销方名称": seller_name or "—",
                "购方识别号": buyer_tax_no or "—",
                "购买方名称": buyer_name or "—",
                "开票日期": invoice.invoice_date or "—",
                "金额": format_decimal(invoice.amount),
                "税率": invoice.tax_rate or "—",
                "税额": format_decimal(invoice.tax_amount) if invoice.tax_amount is not None else "—",
                "价税合计": format_decimal(invoice.total_with_tax) if invoice.total_with_tax is not None else "—",
                "发票类型": "销项发票" if invoice.invoice_type.value == "output" else "进项发票",
            },
            "_detail_fields": {
                "序号": invoice.id,
                "发票代码": invoice.invoice_code or "—",
                "发票号码": invoice.invoice_no or "—",
                "数电发票号码": invoice.digital_invoice_no or "—",
                "税收分类编码": invoice.tax_classification_code or "—",
                "特定业务类型": invoice.specific_business_type or "—",
                "货物或应税劳务名称": invoice.taxable_item_name or "—",
                "规格型号": invoice.specification_model or "—",
                "单位": invoice.unit or "—",
                "数量": format_decimal(invoice.quantity) if invoice.quantity is not None else "—",
                "单价": format_decimal(invoice.unit_price) if invoice.unit_price is not None else "—",
                "发票来源": invoice.invoice_source or "—",
                "发票票种": invoice.invoice_kind or "—",
                "发票状态": invoice.invoice_status_from_source or "—",
                "是否正数发票": invoice.is_positive_invoice or "—",
                "发票风险等级": invoice.risk_level or "—",
                "开票人": invoice.issuer or "—",
                "备注": invoice.remark or "—",
            },
        }

    def _rebuild_cache(self) -> None:
        self._company_identity = self._resolve_company_identity()
        excluded_transaction_batch_ids = self._excluded_transaction_batch_ids()
        latest_run = self._matching_service.latest_run()
        result_by_object_id: dict[str, MatchingResult] = {}
        if latest_run is not None:
            for result in latest_run.results:
                for invoice_id in result.invoice_ids:
                    result_by_object_id[invoice_id] = result
                for transaction_id in result.transaction_ids:
                    result_by_object_id[transaction_id] = result
        self._detail_rows_by_id = {}
        for invoice in self._import_service.list_invoices():
            self._detail_rows_by_id[invoice.id] = self._build_invoice_row(invoice, result_by_object_id.get(invoice.id))
        for transaction in self._import_service.list_transactions():
            if transaction.source_batch_id in excluded_transaction_batch_ids:
                continue
            self._detail_rows_by_id[transaction.id] = self._build_bank_row(transaction, result_by_object_id.get(transaction.id))

    def _excluded_transaction_batch_ids(self) -> set[str]:
        return {
            preview.id
            for preview in self._import_service.list_batches()
            if preview.batch.batch_type.value == "bank_transaction"
            and preview.batch.source_name in LEGACY_DEMO_TRANSACTION_SOURCES
        }

    def _resolve_company_identity(self) -> tuple[str, str | None]:
        candidates: Counter[tuple[str, str | None]] = Counter()
        for invoice in self._import_service.list_invoices():
            for tax_no, company_name in (
                (invoice.seller_tax_no, invoice.seller_name),
                (invoice.buyer_tax_no, invoice.buyer_name),
            ):
                if not is_company_identity(tax_no, company_name):
                    continue
                resolved_name = company_name.strip() if isinstance(company_name, str) and company_name.strip() else DEFAULT_COMPANY_NAME
                resolved_tax_no = tax_no.strip() if isinstance(tax_no, str) and tax_no.strip() else None
                candidates[(resolved_name, resolved_tax_no)] += 1

        if not candidates:
            return (DEFAULT_COMPANY_NAME, None)

        (company_name, company_tax_no), _ = max(
            candidates.items(),
            key=lambda item: (item[1], 1 if item[0][1] else 0, len(item[0][0] or "")),
        )
        return company_name or DEFAULT_COMPANY_NAME, company_tax_no

    def _resolve_invoice_parties(self, invoice: Invoice) -> tuple[str | None, str | None]:
        company_name, _ = self._company_identity
        if invoice.invoice_type.value == "output":
            return invoice.seller_name or company_name, invoice.buyer_name or invoice.counterparty.name
        return invoice.seller_name or invoice.counterparty.name, invoice.buyer_name or company_name

    def _resolve_invoice_tax_nos(self, invoice: Invoice) -> tuple[str | None, str | None]:
        _, company_tax_no = self._company_identity
        if invoice.invoice_type.value == "output":
            return invoice.seller_tax_no or company_tax_no, invoice.buyer_tax_no or invoice.counterparty.tax_no
        return invoice.seller_tax_no or invoice.counterparty.tax_no, invoice.buyer_tax_no or company_tax_no

    @staticmethod
    def _available_actions(row_type: str, section: str) -> list[str]:
        if row_type == "bank":
            if section == "open":
                return ["detail", "view_relation", "cancel_link", "handle_exception"]
            return ["detail"]
        if row_type == "invoice" and section == "open":
            return ["detail", "confirm_link", "mark_exception", "ignore"]
        return ["detail"]


def relation_from_result(result: MatchingResult | None) -> dict[str, str]:
    if result is None:
        return {"code": "pending_match", "label": "待匹配", "tone": "warn"}
    if result.result_type == MatchingResultType.AUTOMATIC_MATCH:
        return {"code": "automatic_match", "label": "自动匹配", "tone": "success"}
    if result.result_type == MatchingResultType.SUGGESTED_MATCH:
        return {"code": "suggested_match", "label": "待人工确认", "tone": "warn"}
    return {"code": "manual_review", "label": "待人工核查", "tone": "danger"}


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(ZERO + Decimal('0.01')):,.2f}"

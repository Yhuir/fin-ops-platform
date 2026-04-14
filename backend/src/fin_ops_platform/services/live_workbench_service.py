from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import MatchingConfidence, MatchingResultType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Invoice, MatchingResult
from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.import_file_service import is_company_identity
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.matching import MatchingEngineService


ZERO = Decimal("0.00")
DEFAULT_COMPANY_NAME = "溯源科技有限公司"
LEGACY_DEMO_TRANSACTION_SOURCES = {"bank_transaction.json"}
INTERNAL_TRANSFER_MATCH_WINDOW = timedelta(hours=72)
INTERNAL_TRANSFER_COMPANY_NAME = "云南溯源科技有限公司"
SALARY_AUTO_MATCH_RULE_CODE = "salary_personal_auto_match"
INTERNAL_TRANSFER_RULE_CODE = "internal_transfer_pair"


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
        if month == "all":
            return bool(self._import_service.list_invoices() or self._import_service.list_transactions())
        return any(invoice.invoice_date and invoice.invoice_date.startswith(month) for invoice in self._import_service.list_invoices()) or any(
            transaction.txn_date and transaction.txn_date.startswith(month) for transaction in self._import_service.list_transactions()
        )

    def get_workbench(self, month: str) -> dict[str, Any]:
        self._rebuild_cache()

        paired: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        open_rows: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}

        for row in self._detail_rows_by_id.values():
            row_month = row.get("_month")
            if month != "all" and row_month != month:
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
        rows = self.get_rows_detail([row_id])
        row = rows.get(row_id)
        if row is None:
            raise KeyError(row_id)
        return payload_from_cache_row(row)

    def get_rows_detail(self, row_ids: list[str]) -> dict[str, dict[str, Any]]:
        result_by_object_id = self._existing_results_by_object_id()
        self._company_identity = self._resolve_company_identity()
        excluded_transaction_batch_ids = self._excluded_transaction_batch_ids()
        payload: dict[str, dict[str, Any]] = {}
        for row_id in row_ids:
            normalized_row_id = str(row_id)
            row = self._build_detail_row_by_id(
                normalized_row_id,
                result_by_object_id=result_by_object_id,
                excluded_transaction_batch_ids=excluded_transaction_batch_ids,
            )
            if row is not None:
                payload[normalized_row_id] = row
        return payload

    def get_case_rows(self, case_id: str, *, month: str | None = None) -> list[dict[str, Any]]:
        self._rebuild_cache()
        rows: list[dict[str, Any]] = []
        for row in self._detail_rows_by_id.values():
            if row.get("case_id") != case_id:
                continue
            row_month = row.get("_month")
            if month not in (None, "", "all") and row_month != month:
                continue
            payload = self._serialize_row(row)
            payload["summary_fields"] = dict(row["_summary_fields"])
            payload["detail_fields"] = dict(row["_detail_fields"])
            rows.append(payload)
        return rows

    def _build_detail_row_by_id(
        self,
        row_id: str,
        *,
        result_by_object_id: dict[str, MatchingResult],
        excluded_transaction_batch_ids: set[str],
    ) -> dict[str, Any] | None:
        try:
            invoice = self._import_service.get_invoice(row_id)
        except KeyError:
            invoice = None
        if invoice is not None:
            return self._build_invoice_row(invoice, result_by_object_id.get(row_id))

        try:
            transaction = self._import_service.get_transaction(row_id)
        except KeyError:
            return None
        if transaction.source_batch_id in excluded_transaction_batch_ids:
            return None
        return self._build_bank_row(transaction, result_by_object_id.get(row_id))

    def list_auto_pair_candidates(self, month: str = "all") -> list[MatchingResult]:
        results_by_object_id = self._existing_results_by_object_id()
        auto_results = [
            *self._build_internal_transfer_results(results_by_object_id),
            *self._build_salary_auto_match_results(results_by_object_id),
        ]
        if month == "all":
            return auto_results
        return [
            result
            for result in auto_results
            if any(
                (transaction.txn_date or "").startswith(month)
                for transaction in self._transactions_for_result(result)
            )
        ]

    @staticmethod
    def _serialize_row(row: dict[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in row.items() if not key.startswith("_")}

    def _build_bank_row(self, transaction: BankTransaction, result: MatchingResult | None) -> dict[str, Any]:
        relation = relation_from_result(result)
        section = "paired" if result and result.result_type == MatchingResultType.AUTOMATIC_MATCH else "open"
        payment_account_label = self._bank_account_resolver.resolve_label(transaction.account_no, transaction.account_name)
        direction_label = "支出" if transaction.txn_direction.value == "outflow" else "收入"
        account_field_label = "支付账户" if transaction.txn_direction.value == "outflow" else "收款账户"
        remark_value = self._build_bank_remark(transaction, result)
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
            "remark": remark_value,
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
                "备注": remark_value or "—",
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
                "备注": remark_value or "—",
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
            "invoice_code": invoice.invoice_code or "—",
            "invoice_no": invoice.invoice_no or "—",
            "digital_invoice_no": invoice.digital_invoice_no or "—",
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
        result_by_object_id = self._existing_results_by_object_id()
        self._detail_rows_by_id = {}
        for invoice in self._import_service.list_invoices():
            self._detail_rows_by_id[invoice.id] = self._build_invoice_row(invoice, result_by_object_id.get(invoice.id))
        for transaction in self._import_service.list_transactions():
            if transaction.source_batch_id in excluded_transaction_batch_ids:
                continue
            self._detail_rows_by_id[transaction.id] = self._build_bank_row(transaction, result_by_object_id.get(transaction.id))

    def _existing_results_by_object_id(self) -> dict[str, MatchingResult]:
        latest_run = self._matching_service.latest_run()
        result_by_object_id: dict[str, MatchingResult] = {}
        if latest_run is None:
            return result_by_object_id

        for result in latest_run.results:
            for invoice_id in result.invoice_ids:
                result_by_object_id[invoice_id] = result
            for transaction_id in result.transaction_ids:
                result_by_object_id[transaction_id] = result
        return result_by_object_id

    def _build_internal_transfer_results(self, existing_results_by_object_id: dict[str, MatchingResult]) -> list[MatchingResult]:
        available_transactions = [
            transaction
            for transaction in self._import_service.list_transactions()
            if self._is_internal_transfer_candidate(transaction)
            and (
                existing_results_by_object_id.get(transaction.id) is None
                or existing_results_by_object_id[transaction.id].result_type != MatchingResultType.AUTOMATIC_MATCH
            )
        ]
        inflows = sorted(
            (transaction for transaction in available_transactions if transaction.txn_direction == TransactionDirection.INFLOW),
            key=self._internal_transfer_sort_key,
        )
        outflows = sorted(
            (transaction for transaction in available_transactions if transaction.txn_direction == TransactionDirection.OUTFLOW),
            key=self._internal_transfer_sort_key,
        )
        used_ids: set[str] = set()
        results: list[MatchingResult] = []

        for outflow in outflows:
            if outflow.id in used_ids:
                continue
            outflow_time = self._parse_transaction_time(outflow)
            if outflow_time is None:
                continue

            best_match: tuple[timedelta, BankTransaction] | None = None
            for inflow in inflows:
                if inflow.id in used_ids or inflow.amount != outflow.amount:
                    continue
                inflow_time = self._parse_transaction_time(inflow)
                if inflow_time is None:
                    continue
                delta = abs(inflow_time - outflow_time)
                if delta > INTERNAL_TRANSFER_MATCH_WINDOW:
                    continue
                if best_match is None or delta < best_match[0]:
                    best_match = (delta, inflow)

            if best_match is None:
                continue

            inflow = best_match[1]
            used_ids.add(outflow.id)
            used_ids.add(inflow.id)
            ordered_ids = sorted([outflow.id, inflow.id])
            results.append(
                MatchingResult(
                    id=f"internal_transfer_{ordered_ids[0]}_{ordered_ids[1]}",
                    run_id="internal_transfer",
                    result_type=MatchingResultType.AUTOMATIC_MATCH,
                    confidence=MatchingConfidence.HIGH,
                    rule_code=INTERNAL_TRANSFER_RULE_CODE,
                    explanation="Detected matched internal transfer between company accounts with equal amount and close timestamps.",
                    invoice_ids=[],
                    transaction_ids=ordered_ids,
                    amount=outflow.amount,
                    difference_amount=ZERO,
                    counterparty_name=INTERNAL_TRANSFER_COMPANY_NAME,
                )
            )

        return results

    def _build_salary_auto_match_results(self, existing_results_by_object_id: dict[str, MatchingResult]) -> list[MatchingResult]:
        results: list[MatchingResult] = []
        for transaction in self._import_service.list_transactions():
            existing_result = existing_results_by_object_id.get(transaction.id)
            if existing_result is not None and existing_result.result_type == MatchingResultType.AUTOMATIC_MATCH:
                continue
            if not self._is_salary_personal_candidate(transaction):
                continue
            results.append(
                MatchingResult(
                    id=f"salary_auto_{transaction.id}",
                    run_id="salary_auto_match",
                    result_type=MatchingResultType.AUTOMATIC_MATCH,
                    confidence=MatchingConfidence.HIGH,
                    rule_code=SALARY_AUTO_MATCH_RULE_CODE,
                    explanation="Detected salary payment to an individual counterparty from bank remark or summary.",
                    invoice_ids=[],
                    transaction_ids=[transaction.id],
                    amount=transaction.amount,
                    difference_amount=ZERO,
                    counterparty_name=transaction.counterparty_name_raw or "",
                )
            )
        return results

    def _transactions_for_result(self, result: MatchingResult) -> list[BankTransaction]:
        transaction_ids = set(result.transaction_ids)
        if not transaction_ids:
            return []
        return [
            transaction
            for transaction in self._import_service.list_transactions()
            if transaction.id in transaction_ids
        ]

    def _build_bank_remark(self, transaction: BankTransaction, result: MatchingResult | None) -> str:
        base_remark = (transaction.remark or transaction.summary or "").strip()
        if result is None or result.rule_code != INTERNAL_TRANSFER_RULE_CODE:
            return base_remark

        counterpart = self._internal_transfer_counterpart_transaction(transaction.id, result)
        if counterpart is None:
            return base_remark

        counterpart_account_label = self._compact_bank_account_label(counterpart.account_no, counterpart.account_name)
        if not counterpart_account_label:
            return base_remark

        counterpart_prefix = "支付账户" if transaction.txn_direction == TransactionDirection.INFLOW else "收款账户"
        counterpart_text = f"{counterpart_prefix}：{counterpart_account_label}"
        if not base_remark:
            return counterpart_text
        if counterpart_text in base_remark:
            return base_remark
        return f"{base_remark}；{counterpart_text}"

    def _internal_transfer_counterpart_transaction(
        self,
        transaction_id: str,
        result: MatchingResult,
    ) -> BankTransaction | None:
        counterpart_ids = [candidate_id for candidate_id in result.transaction_ids if candidate_id != transaction_id]
        if not counterpart_ids:
            return None
        transactions_by_id = {transaction.id: transaction for transaction in self._import_service.list_transactions()}
        return transactions_by_id.get(counterpart_ids[0])

    def _compact_bank_account_label(self, account_no: str | None, account_name: str | None) -> str:
        full_label = self._bank_account_resolver.resolve_label(account_no, account_name).strip()
        compact_label = full_label
        for marker in (" 基本户 ", " 一般户 ", " 专户 ", " 账户 "):
            compact_label = compact_label.replace(marker, " ")
        return " ".join(compact_label.split())

    @staticmethod
    def _is_internal_transfer_candidate(transaction: BankTransaction) -> bool:
        return is_company_identity(None, transaction.account_name) and is_company_identity(None, transaction.counterparty_name_raw)

    @staticmethod
    def _is_salary_personal_candidate(transaction: BankTransaction) -> bool:
        if transaction.txn_direction != TransactionDirection.OUTFLOW:
            return False
        remarks = " ".join(
            part.strip()
            for part in (transaction.remark or "", transaction.summary or "")
            if isinstance(part, str) and part.strip()
        )
        if "工资" not in remarks:
            return False
        counterparty_name = (transaction.counterparty_name_raw or "").strip()
        if not counterparty_name:
            return False
        return not is_company_identity(None, counterparty_name)

    @staticmethod
    def _internal_transfer_sort_key(transaction: BankTransaction) -> tuple[datetime, str]:
        parsed = LiveWorkbenchService._parse_transaction_time(transaction)
        if parsed is None:
            parsed = datetime.min
        return parsed, transaction.id

    @staticmethod
    def _parse_transaction_time(transaction: BankTransaction) -> datetime | None:
        for value in (transaction.pay_receive_time, transaction.trade_time):
            parsed = _parse_datetime(value)
            if parsed is not None:
                return parsed
        if transaction.txn_date:
            parsed_date = _parse_date_only(transaction.txn_date)
            if parsed_date is not None:
                return parsed_date
        return None

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
    if result.rule_code == INTERNAL_TRANSFER_RULE_CODE:
        return {"code": "internal_transfer_pair", "label": "已匹配：内部往来款", "tone": "success"}
    if result.rule_code == SALARY_AUTO_MATCH_RULE_CODE:
        return {"code": SALARY_AUTO_MATCH_RULE_CODE, "label": "已匹配：工资", "tone": "success"}
    if result.result_type == MatchingResultType.AUTOMATIC_MATCH:
        return {"code": "automatic_match", "label": "自动匹配", "tone": "success"}
    if result.result_type == MatchingResultType.SUGGESTED_MATCH:
        return {"code": "suggested_match", "label": "待人工确认", "tone": "warn"}
    return {"code": "manual_review", "label": "待人工核查", "tone": "danger"}


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{value.quantize(ZERO + Decimal('0.01')):,.2f}"


def payload_from_cache_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = LiveWorkbenchService._serialize_row(row)
    payload["summary_fields"] = dict(row["_summary_fields"])
    payload["detail_fields"] = dict(row["_detail_fields"])
    return payload


def _parse_datetime(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def _parse_date_only(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        return None

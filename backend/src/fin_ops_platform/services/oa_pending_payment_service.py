from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from http import HTTPStatus
import json
from typing import Any
from urllib.parse import unquote

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.invoice_relation_query_context import DistributedInvoiceRelationContext
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SOURCE_VERSION = "oa-pending-payment:v1"
READ_MODEL_STATUS = "live_query"


FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "oa_applicant": {"label": "OA申请人", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "oa_application_type": {"label": "类型", "mode": "enum_multi", "operators": {"in", "equals"}, "sortable": True},
    "oa_project_name": {"label": "项目名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "oa_amount": {"label": "金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "payment_status": {"label": "支付状态", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_trade_time": {"label": "交易时间", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "bank_name": {"label": "支出银行", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_account": {"label": "银行账户", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "bank_direction": {"label": "收支", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "bank_counterparty_name": {"label": "对方户名", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_summary": {"label": "摘要", "mode": "text", "operators": {"contains"}, "sortable": True},
    "invoice_no": {"label": "数电发票号码", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "seller_name": {"label": "进项发票方名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "invoice_date": {"label": "开票日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "invoice_total_with_tax": {"label": "价税合计", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
}

SORT_FIELDS = {field for field, config in FILTER_CONFIG.items() if config["sortable"]}


class OaPendingPaymentError(ValueError):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        status_code: HTTPStatus = HTTPStatus.BAD_REQUEST,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.status_code = status_code
        self.details = details or {}


class OaPendingPaymentQueryService:
    """Read-only OA-primary query facade for pending payment reconciliation.

    Data ownership mirrors the refactored invoice relation pages:
    - OA rows come from the OA projection;
    - bank transactions and invoices come from normalized import facts;
    - relationship evidence comes only from WorkbenchRelationReadFacade distribution.
    """

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        oa_projection: Any | None = None,
        lifecycle_policy: Any | None = None,
        require_fresh_relations: bool = True,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._oa_projection = oa_projection
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy()
        self._require_fresh_relations = require_fresh_relations

    def list_rows(
        self,
        *,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
        keyword: str | None = None,
        month: str | None = None,
        trade_date_from: str | None = None,
        trade_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = "bank_trade_time",
        sort_direction: str | None = "desc",
    ) -> dict[str, Any]:
        page_number = _parse_positive_int(page, "page")
        page_limit = _parse_positive_int(page_size, "page_size", maximum=200)
        parsed_filters = self._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = self._parse_sort(sort_field, sort_direction)
        context = self._query_context(month_hint=month)
        rows = self._filtered_sorted_rows(
            context=context,
            keyword=keyword,
            month=month,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=parsed_filters,
            sort_field=normalized_sort_field,
            sort_direction=normalized_sort_direction,
        )
        total = len(rows)
        paged_rows = rows[(page_number - 1) * page_limit : page_number * page_limit]
        return {
            "rows": paged_rows,
            "pagination": {"page": page_number, "pageSize": page_limit, "total": total},
            "summary": self._summary(rows),
            "appliedFilters": {"filters": parsed_filters},
            "sort": {"field": normalized_sort_field, "direction": normalized_sort_direction},
            "filterConfig": self._filter_config(),
            "read_model_status": READ_MODEL_STATUS,
            "readModelStatus": READ_MODEL_STATUS,
            "source_versions": self.source_versions(),
            "sourceVersions": self.source_versions(),
        }

    def filter_options(
        self,
        *,
        keyword: str | None = None,
        month: str | None = None,
        trade_date_from: str | None = None,
        trade_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        parsed_filters = self._parse_filters(filters)
        rows = self._filtered_sorted_rows(
            context=self._query_context(),
            keyword=keyword,
            month=month,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=parsed_filters,
            sort_field="bank_trade_time",
            sort_direction="desc",
        )
        return self.filter_options_for_rows(
            rows=rows,
            keyword=keyword,
            month=month,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=parsed_filters,
        )

    def filter_options_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        keyword: str | None = None,
        month: str | None = None,
        trade_date_from: str | None = None,
        trade_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        parsed_filters = self._parse_filters(filters)
        typed_rows = [row for row in list(rows or []) if isinstance(row, dict)]
        fields = []
        for field, config in FILTER_CONFIG.items():
            fields.append(
                {
                    "field": field,
                    "label": config["label"],
                    "mode": config["mode"],
                    "operators": sorted(config["operators"]),
                    "sortable": bool(config["sortable"]),
                    "options": self._options_for_field(typed_rows, field),
                }
            )
        return {
            "fields": fields,
            "context": {
                "keyword": keyword or "",
                "month": month,
                "tradeDateFrom": trade_date_from,
                "tradeDateTo": trade_date_to,
                "filters": parsed_filters,
            },
        }

    def row_by_id(self, row_id: str) -> dict[str, Any] | None:
        return self._row_by_id(row_id, context=self._query_context())

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        record = self._oa_records_by_id(month=None).get(str(oa_id))
        if record is None:
            raise OaPendingPaymentError("oa_not_found", f"OA detail not found: {oa_id}", status_code=HTTPStatus.NOT_FOUND)
        return {
            "id": record.id,
            "oaId": record.id,
            "title": "OA详情",
            "subtitle": record.project_name_display or record.project_name or record.case_id or record.id,
            "detailAvailable": True,
            "sections": [
                {
                    "title": "OA信息",
                    "fields": [
                        {"label": "申请人", "value": record.applicant},
                        {"label": "类型", "value": record.apply_type},
                        {"label": "项目名称", "value": record.project_name_display or record.project_name},
                        {"label": "金额", "value": _money(record.amount) if _parse_decimal(record.amount) is not None else ""},
                        {"label": "月份", "value": record.month},
                        {"label": "状态", "value": record.section},
                        {"label": "事由", "value": record.reason},
                        {"label": "往来方", "value": record.counterparty_name},
                    ],
                }
            ],
            "detailFields": deepcopy(record.detail_fields),
            "raw": _serialize_dataclass(record),
        }

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        context = self._query_context()
        transaction = context.bank_transactions_by_id().get(str(bank_transaction_id))
        if transaction is None:
            raise OaPendingPaymentError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return {
            "id": transaction.id,
            "title": "支出流水详情",
            "subtitle": transaction.counterparty_name_raw or transaction.summary or transaction.id,
            "sections": [
                {
                    "title": "凭证信息",
                    "fields": [
                        {"label": "账户明细编号-交易流水号", "value": transaction.account_detail_no},
                        {"label": "企业流水号", "value": transaction.enterprise_serial_no},
                        {"label": "凭证种类", "value": transaction.voucher_kind},
                        {"label": "凭证号", "value": transaction.voucher_no},
                    ],
                },
                {
                    "title": "流水信息",
                    "fields": [
                        {"label": "支出银行", "value": transaction.imported_bank_name},
                        {"label": "账户名称", "value": transaction.account_name},
                        {"label": "交易时间", "value": transaction.trade_time or transaction.txn_date},
                        {"label": "借方发生额", "value": _debit_amount(transaction)},
                        {"label": "贷方发生额", "value": _credit_amount(transaction)},
                        {"label": "余额", "value": _money(transaction.balance) if transaction.balance is not None else ""},
                        {"label": "币种", "value": transaction.currency},
                    ],
                },
                {
                    "title": "对方信息",
                    "fields": [
                        {"label": "对方户名", "value": transaction.counterparty_name_raw},
                        {"label": "对方账号", "value": transaction.counterparty_account_no},
                        {"label": "对方开户机构", "value": transaction.counterparty_bank_name},
                        {"label": "记账日期", "value": transaction.booked_date},
                        {"label": "摘要", "value": transaction.summary},
                        {"label": "备注", "value": transaction.remark},
                    ],
                },
            ],
            "relations": context.relation_summaries_for_row(transaction.id),
            "raw": _serialize_dataclass(transaction),
        }

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        invoice = self._input_invoices_by_id().get(str(invoice_id))
        if invoice is None:
            raise OaPendingPaymentError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return {
            "id": invoice.id,
            "title": "发票详情",
            "subtitle": invoice.digital_invoice_no or invoice.invoice_no or invoice.id,
            "sections": [
                {
                    "title": "发票情况",
                    "fields": [
                        {"label": "数电发票号码", "value": invoice.digital_invoice_no or invoice.invoice_no},
                        {"label": "进项发票方名称", "value": invoice.seller_name or invoice.counterparty.name},
                        {"label": "开票日期", "value": invoice.invoice_date},
                        {"label": "价税合计", "value": _money(_invoice_total(invoice))},
                        {"label": "买方名称", "value": invoice.buyer_name},
                        {"label": "备注", "value": invoice.remark},
                    ],
                }
            ],
            "raw": _serialize_dataclass(invoice),
        }

    def row_relation_details(self, row_id: str, *, kind: str) -> dict[str, Any]:
        normalized_kind = str(kind or "").strip()
        if normalized_kind not in {"bank", "invoice"}:
            raise OaPendingPaymentError("invalid_relation_kind", "kind must be bank or invoice.")
        context = self._query_context()
        row = self._row_by_id(row_id, context=context)
        if row is None:
            raise OaPendingPaymentError("row_not_found", f"OA pending payment row not found: {row_id}", status_code=HTTPStatus.NOT_FOUND)
        relation_payload = row["bankTransaction"] if normalized_kind == "bank" else row["invoice"]
        summaries = list(relation_payload.get("summaries") or [])
        return {
            "rowId": row["id"],
            "oaId": row["oa"]["id"],
            "kind": normalized_kind,
            "title": "支出流水关联明细" if normalized_kind == "bank" else "发票关联明细",
            "subtitle": row["oa"].get("applicantName") or row["oa"].get("projectName") or row["oa"]["id"],
            "detailAvailable": relation_payload.get("detailMode") != "none",
            "relationCount": relation_payload.get("relationCount", 0),
            "hasMultiple": relation_payload.get("hasMultiple", False),
            "summaries": summaries,
            "sections": _relation_detail_sections(normalized_kind, summaries),
            "relations": context.relation_summaries_for_row(row["oa"]["id"]),
        }

    @staticmethod
    def source_versions() -> dict[str, Any]:
        return {"oa_pending_payment": SOURCE_VERSION}

    def _query_context(self, *, month_hint: str | None = None) -> DistributedInvoiceRelationContext:
        return DistributedInvoiceRelationContext(
            import_service=self._import_service,
            relation_facade=self._relation_facade,
            oa_projection=self._oa_projection,
            month_hint=month_hint,
            require_fresh_relations=self._require_fresh_relations,
        )

    def _filtered_sorted_rows(
        self,
        *,
        context: DistributedInvoiceRelationContext,
        keyword: str | None,
        month: str | None,
        trade_date_from: str | None,
        trade_date_to: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
    ) -> list[dict[str, Any]]:
        rows = self._build_rows(month=month, context=context)
        rows = [row for row in rows if self._row_matches_trade_date(row, date_from=trade_date_from, date_to=trade_date_to)]
        if keyword:
            needle = str(keyword).strip().lower()
            rows = [row for row in rows if needle in str(row.get("searchText") or "").lower()]
        rows = [row for row in rows if self._row_matches_filters(row, filters)]
        rows.sort(key=lambda row: self._sort_value(row, sort_field), reverse=sort_direction == "desc")
        return rows

    def _build_rows(self, *, month: str | None, context: DistributedInvoiceRelationContext) -> list[dict[str, Any]]:
        records = self._oa_records(month=month)
        context.preload_relation_rows([record.id for record in records])
        oa_by_id = {record.id: record for record in records}
        bank_by_id = context.bank_transactions_by_id()
        invoices_by_id = self._input_invoices_by_id()
        rows = []
        for record in records:
            relations = context.distributed_relations_for_row_ids([record.id])
            bank_payload = self._bank_relation_payload(record, relations=relations, bank_by_id=bank_by_id)
            invoice_payload = self._invoice_relation_payload(record, relations=relations, invoices_by_id=invoices_by_id)
            payment_status = self._payment_status(
                record,
                bank_payload,
                relations,
                bank_by_id=bank_by_id,
                oa_by_id=oa_by_id,
                context=context,
            )
            row = {
                "id": _row_id(record.id),
                "oa": self._oa_summary(record),
                "paymentStatus": payment_status,
                "bankTransaction": bank_payload,
                "invoice": invoice_payload,
            }
            row["searchText"] = json.dumps(row, ensure_ascii=False, sort_keys=True)
            rows.append(row)
        return rows

    def _oa_records(self, *, month: str | None) -> list[OAApplicationRecord]:
        records = list(self._oa_records_by_id(month=month).values())
        normalized_month = str(month or "").strip()
        if normalized_month and normalized_month != "all":
            records = [record for record in records if str(record.month or "").startswith(normalized_month[:7])]
        records.sort(key=lambda record: (record.month or "", record.applicant or "", record.id))
        return records

    def _oa_records_by_id(self, *, month: str | None) -> dict[str, OAApplicationRecord]:
        if self._oa_projection is None:
            return {}
        list_all = getattr(self._oa_projection, "list_all_application_records", None)
        if callable(list_all):
            records = list_all()
        else:
            records = []
        return {record.id: record for record in records if isinstance(record, OAApplicationRecord)}

    def _input_invoices_by_id(self) -> dict[str, Invoice]:
        return {
            invoice.id: invoice
            for invoice in self._import_service.list_invoices(month="all", invoice_type=InvoiceType.INPUT)
        }

    @staticmethod
    def _oa_summary(record: OAApplicationRecord) -> dict[str, Any]:
        return {
            "id": record.id,
            "applicantName": record.applicant,
            "applicationType": record.apply_type,
            "projectName": record.project_name_display or record.project_name,
            "amount": _money(record.amount) if _parse_decimal(record.amount) is not None else "",
            "detailAvailable": True,
            "month": record.month,
            "workflowNo": record.case_id or "",
            "reason": record.reason,
            "counterpartyName": record.counterparty_name,
        }

    def _bank_relation_payload(
        self,
        record: OAApplicationRecord,
        *,
        relations: list[dict[str, Any]],
        bank_by_id: dict[str, BankTransaction],
    ) -> dict[str, Any]:
        summaries = []
        seen: set[str] = set()
        missing_bank_relation_count = 0
        non_outflow_relation_count = 0
        oa_amount = _parse_decimal(record.amount) or ZERO
        for relation in relations:
            for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
                if row_type != "bank":
                    continue
                bank = bank_by_id.get(row_id)
                if bank is None:
                    missing_bank_relation_count += 1
                    continue
                if _bank_direction(bank) != "outflow":
                    non_outflow_relation_count += 1
                    continue
                if bank.id not in seen:
                    seen.add(bank.id)
                    summaries.append(self._bank_summary(bank, oa_amount, relation))
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        paid_total = sum((_decimal(summary.get("amount")) for summary in public_summaries), start=ZERO)
        return {
            "primaryBankTransactionId": primary.get("bankTransactionId"),
            "accountDetailNo": primary.get("accountDetailNo", ""),
            "enterpriseSerialNo": primary.get("enterpriseSerialNo", ""),
            "voucherKind": primary.get("voucherKind", ""),
            "voucherNo": primary.get("voucherNo", ""),
            "bankName": primary.get("bankName", ""),
            "accountNo": primary.get("accountNo", ""),
            "accountLast4": primary.get("accountLast4", ""),
            "bankAccount": primary.get("bankAccount", ""),
            "accountName": primary.get("accountName", ""),
            "tradeTime": primary.get("tradeTime", ""),
            "debitAmount": primary.get("debitAmount", ""),
            "creditAmount": primary.get("creditAmount", ""),
            "balance": primary.get("balance", ""),
            "currency": primary.get("currency", ""),
            "counterpartyName": primary.get("counterpartyName", ""),
            "counterpartyAccountNo": primary.get("counterpartyAccountNo", ""),
            "counterpartyBankName": primary.get("counterpartyBankName", ""),
            "bookedDate": primary.get("bookedDate", ""),
            "summary": primary.get("summary", ""),
            "remark": primary.get("remark", ""),
            "amount": primary.get("amount", ""),
            "paidTotal": _money(paid_total),
            "direction": primary.get("direction", ""),
            "directionLabel": primary.get("directionLabel", ""),
            "relationCount": len(public_summaries),
            "hasMultiple": len(public_summaries) > 1,
            "detailMode": "none" if not public_summaries else "list" if len(public_summaries) > 1 else "single",
            "summaries": public_summaries,
            "missingBankRelationCount": missing_bank_relation_count,
            "nonOutflowBankRelationCount": non_outflow_relation_count,
        }

    @staticmethod
    def _bank_summary(bank: BankTransaction, oa_amount: Decimal, relation: dict[str, Any]) -> dict[str, Any]:
        bank_amount = abs(_decimal(bank.amount))
        diff = abs(bank_amount - oa_amount)
        timestamp = _sortable_time(bank.trade_time or bank.txn_date)
        return {
            "bankTransactionId": bank.id,
            "accountDetailNo": bank.account_detail_no or "",
            "enterpriseSerialNo": bank.enterprise_serial_no or "",
            "voucherKind": bank.voucher_kind or "",
            "voucherNo": bank.voucher_no or "",
            "bankName": bank.imported_bank_name or "",
            "accountNo": bank.account_no or "",
            "accountLast4": bank.imported_bank_last4 or str(bank.account_no or "")[-4:],
            "bankAccount": _bank_account_label(bank),
            "accountName": bank.account_name or "",
            "tradeTime": bank.trade_time or bank.txn_date or "",
            "debitAmount": _debit_amount(bank),
            "creditAmount": _credit_amount(bank),
            "balance": _money(bank.balance) if bank.balance is not None else "",
            "currency": bank.currency or "",
            "counterpartyName": bank.counterparty_name_raw or "",
            "counterpartyAccountNo": bank.counterparty_account_no or "",
            "counterpartyBankName": bank.counterparty_bank_name or "",
            "bookedDate": bank.booked_date or "",
            "summary": bank.summary or "",
            "remark": bank.remark or "",
            "amount": _money(bank_amount),
            "direction": _bank_direction(bank),
            "directionLabel": _bank_direction_label(bank),
            "relationCaseId": relation.get("case_id", ""),
            "_sort": (diff, -timestamp, bank.id),
        }

    def _invoice_relation_payload(
        self,
        record: OAApplicationRecord,
        *,
        relations: list[dict[str, Any]],
        invoices_by_id: dict[str, Invoice],
    ) -> dict[str, Any]:
        summaries = []
        seen: set[str] = set()
        oa_amount = _parse_decimal(record.amount) or ZERO
        for relation in relations:
            for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
                if row_type != "invoice":
                    continue
                invoice = invoices_by_id.get(row_id)
                if invoice is not None and invoice.id not in seen:
                    seen.add(invoice.id)
                    summaries.append(self._invoice_summary(invoice, oa_amount, relation))
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        return {
            "primaryInvoiceId": primary.get("invoiceId"),
            "digitalInvoiceNo": primary.get("digitalInvoiceNo", ""),
            "sellerName": primary.get("sellerName", ""),
            "invoiceDate": primary.get("invoiceDate", ""),
            "totalWithTax": primary.get("totalWithTax", ""),
            "relationCount": len(public_summaries),
            "hasMultiple": len(public_summaries) > 1,
            "detailMode": "none" if not public_summaries else "list" if len(public_summaries) > 1 else "single",
            "summaries": public_summaries,
        }

    @staticmethod
    def _invoice_summary(invoice: Invoice, oa_amount: Decimal, relation: dict[str, Any]) -> dict[str, Any]:
        total = _invoice_total(invoice)
        return {
            "invoiceId": invoice.id,
            "digitalInvoiceNo": invoice.digital_invoice_no or invoice.invoice_no or "",
            "sellerName": invoice.seller_name or invoice.counterparty.name,
            "invoiceDate": invoice.invoice_date or "",
            "totalWithTax": _money(total),
            "relationCaseId": relation.get("case_id", ""),
            "_sort": (abs(total - oa_amount), invoice.invoice_date or "", invoice.id),
        }

    def _payment_status(
        self,
        record: OAApplicationRecord,
        bank_payload: dict[str, Any],
        relations: list[dict[str, Any]],
        *,
        bank_by_id: dict[str, BankTransaction],
        oa_by_id: dict[str, OAApplicationRecord],
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, str]:
        oa_amount = _parse_decimal(record.amount)
        if oa_amount is None:
            return self._lifecycle_policy.evaluate_oa_payment(oa_amount=None, paid_total=ZERO, has_bank=False)
        bank_ids = [str(summary.get("bankTransactionId") or "") for summary in list(bank_payload.get("summaries") or [])]
        bank_ids = [bank_id for bank_id in bank_ids if bank_id]
        if not bank_ids:
            return self._lifecycle_policy.evaluate_oa_payment(
                oa_amount=oa_amount,
                paid_total=ZERO,
                has_bank=False,
                has_missing_bank_relation=int(bank_payload.get("missingBankRelationCount") or 0) > 0,
                has_non_outflow_bank_relation=int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0,
            )
        merged_payment = self._is_merged_payment(
            record.id,
            bank_ids,
            relations,
            bank_by_id=bank_by_id,
            oa_by_id=oa_by_id,
            context=context,
        )
        paid_total = sum((abs(_decimal(bank_by_id[bank_id].amount)) for bank_id in bank_ids if bank_id in bank_by_id), start=ZERO)
        return self._lifecycle_policy.evaluate_oa_payment(
            oa_amount=oa_amount,
            paid_total=paid_total,
            has_bank=True,
            merged_payment=merged_payment,
        )

    def _is_merged_payment(
        self,
        oa_id: str,
        bank_ids: list[str],
        relations: list[dict[str, Any]],
        *,
        bank_by_id: dict[str, BankTransaction],
        oa_by_id: dict[str, OAApplicationRecord],
        context: DistributedInvoiceRelationContext,
    ) -> bool:
        for bank_id in bank_ids:
            bank = bank_by_id.get(bank_id)
            if bank is None:
                continue
            related_oa_ids: list[str] = []
            for relation in context.distributed_relations_for_row_ids([bank_id]):
                for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
                    if row_type == "oa" and row_id not in related_oa_ids:
                        related_oa_ids.append(row_id)
            if len(related_oa_ids) < 2 or oa_id not in related_oa_ids:
                continue
            amounts = [_parse_decimal(oa_by_id[related_oa_id].amount) for related_oa_id in related_oa_ids if related_oa_id in oa_by_id]
            if len(amounts) == len(related_oa_ids) and all(amount is not None for amount in amounts):
                if _within_cent(sum((amount or ZERO for amount in amounts), start=ZERO), abs(_decimal(bank.amount))):
                    return True
        return False

    @staticmethod
    def _filter_config() -> list[dict[str, Any]]:
        return [
            {
                "field": field,
                "label": config["label"],
                "mode": config["mode"],
                "operators": sorted(config["operators"]),
                "sortable": bool(config["sortable"]),
            }
            for field, config in FILTER_CONFIG.items()
        ]

    def _parse_filters(self, filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if filters in (None, ""):
            return []
        if isinstance(filters, str):
            try:
                parsed = json.loads(unquote(filters))
            except json.JSONDecodeError as exc:
                raise OaPendingPaymentError("invalid_filter_json", "filters must be a URL-encoded JSON array.") from exc
        else:
            parsed = filters
        if not isinstance(parsed, list):
            raise OaPendingPaymentError("invalid_filter_json", "filters must be a JSON array.")
        normalized = []
        for item in parsed:
            if not isinstance(item, dict):
                raise OaPendingPaymentError("invalid_filter_json", "each filter must be an object.")
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if field not in FILTER_CONFIG:
                raise OaPendingPaymentError("invalid_filter_field", f"Unsupported filter field: {field}", details={"field": field})
            if operator not in FILTER_CONFIG[field]["operators"]:
                raise OaPendingPaymentError(
                    "invalid_filter_operator",
                    f"Unsupported operator for {field}: {operator}",
                    details={"field": field, "operator": operator},
                )
            normalized.append({"field": field, "operator": operator, "value": item.get("value"), "values": list(item.get("values") or [])})
        return normalized

    def _parse_sort(self, sort_field: str | None, sort_direction: str | None) -> tuple[str, str]:
        field = str(sort_field or "bank_trade_time").strip() or "bank_trade_time"
        direction = str(sort_direction or "desc").strip().lower() or "desc"
        if field not in SORT_FIELDS:
            raise OaPendingPaymentError("invalid_sort_field", f"Unsupported sort field: {field}", details={"field": field})
        if direction not in {"asc", "desc"}:
            raise OaPendingPaymentError("invalid_sort_direction", "sort_direction must be asc or desc.")
        return field, direction

    def _row_matches_filters(self, row: dict[str, Any], filters: list[dict[str, Any]]) -> bool:
        for filter_item in filters:
            field = filter_item["field"]
            operator = filter_item["operator"]
            value = self._field_value(row, field)
            if operator == "contains":
                if str(filter_item.get("value") or "").lower() not in str(value or "").lower():
                    return False
            elif operator == "equals":
                expected = filter_item.get("value")
                if FILTER_CONFIG[field]["mode"] == "money":
                    if not _within_cent(_decimal(value), _decimal(expected)):
                        return False
                elif str(value or "") != str(expected or ""):
                    return False
            elif operator == "in":
                values = {str(item) for item in list(filter_item.get("values") or [])}
                if str(value or "") not in values:
                    return False
            elif operator == "between":
                bounds = filter_item.get("value")
                if not isinstance(bounds, dict):
                    raise OaPendingPaymentError("invalid_filter_value", "between filter requires min/max object.")
                current = str(value or "")
                min_value = bounds.get("min")
                max_value = bounds.get("max")
                if FILTER_CONFIG[field]["mode"] == "money":
                    current_decimal = _decimal(current)
                    if min_value not in (None, "") and current_decimal < _decimal(min_value):
                        return False
                    if max_value not in (None, "") and current_decimal > _decimal(max_value):
                        return False
                else:
                    current_date = current[:10]
                    if min_value and current_date < str(min_value):
                        return False
                    if max_value and current_date > str(max_value):
                        return False
        return True

    @staticmethod
    def _row_matches_trade_date(row: dict[str, Any], *, date_from: str | None, date_to: str | None) -> bool:
        trade_time = str(row["bankTransaction"].get("tradeTime") or "")
        if date_from and trade_time[:10] < str(date_from):
            return False
        if date_to and trade_time[:10] > str(date_to):
            return False
        return True

    def _sort_value(self, row: dict[str, Any], field: str) -> Any:
        value = self._field_value(row, field)
        if FILTER_CONFIG[field]["mode"] == "money":
            return _decimal(value)
        if FILTER_CONFIG[field]["mode"] == "date":
            return str(value or "")
        return str(value or "")

    @staticmethod
    def _field_value(row: dict[str, Any], field: str) -> Any:
        oa = row["oa"]
        payment = row["paymentStatus"]
        bank = row["bankTransaction"]
        invoice = row["invoice"]
        values = {
            "oa_applicant": oa.get("applicantName"),
            "oa_application_type": oa.get("applicationType"),
            "oa_project_name": oa.get("projectName"),
            "oa_amount": oa.get("amount"),
            "payment_status": payment.get("code"),
            "bank_trade_time": bank.get("tradeTime"),
            "bank_name": bank.get("bankName"),
            "bank_account": bank.get("bankAccount"),
            "bank_direction": bank.get("direction"),
            "bank_counterparty_name": bank.get("counterpartyName"),
            "bank_summary": bank.get("summary"),
            "invoice_no": invoice.get("digitalInvoiceNo"),
            "seller_name": invoice.get("sellerName"),
            "invoice_date": invoice.get("invoiceDate"),
            "invoice_total_with_tax": invoice.get("totalWithTax"),
        }
        return values.get(field)

    def _options_for_field(self, rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        if FILTER_CONFIG[field]["mode"] in {"date", "money", "text"}:
            return []
        counts: dict[str, int] = {}
        labels: dict[str, str] = {}
        for row in rows:
            value = self._field_value(row, field)
            if value in (None, ""):
                continue
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
            if field == "payment_status":
                labels[key] = row["paymentStatus"]["label"]
            elif field == "bank_direction":
                labels[key] = _bank_direction_option_label(key)
            else:
                labels[key] = key
        return [{"value": value, "label": labels[value], "count": counts[value]} for value in sorted(counts)]

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        status_counts: dict[str, int] = {}
        for row in rows:
            code = str(row.get("paymentStatus", {}).get("code") or "")
            status_counts[code] = status_counts.get(code, 0) + 1
        return {
            "rowCount": len(rows),
            "oaAmountTotal": _money(sum((_decimal(row["oa"].get("amount")) for row in rows), start=ZERO)),
            "bankPaidTotal": _money(sum((_decimal(row["bankTransaction"].get("paidTotal")) for row in rows), start=ZERO)),
            "statusCounts": status_counts,
        }

    def _row_by_id(self, row_id: str, *, context: DistributedInvoiceRelationContext) -> dict[str, Any] | None:
        normalized_row_id = str(row_id or "").strip()
        for row in self._build_rows(month=None, context=context):
            if row["id"] == normalized_row_id:
                return row
        return None


def _parse_positive_int(value: int | str | None, field: str, *, maximum: int | None = None) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be a positive integer.") from exc
    if number < 1:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be a positive integer.")
    if maximum is not None and number > maximum:
        raise OaPendingPaymentError("invalid_paging", f"{field} must be <= {maximum}.")
    return number


def _status(code: str, label: str, reason: str) -> dict[str, str]:
    severity = "success" if code in {"paid", "merged_paid"} else "warning" if code in {"unpaid", "pending_review"} else "error"
    return {"code": code, "label": label, "reason": reason, "severity": severity}


def _row_id(oa_id: str) -> str:
    return "oa_pending_payment_row_" + sha1(str(oa_id).encode("utf-8")).hexdigest()[:16]


def _parse_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    parsed = _parse_decimal(value)
    return parsed if parsed is not None else ZERO


def _money(value: Any) -> str:
    return f"{_decimal(value).quantize(CENT)}"


def _within_cent(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= CENT


def _invoice_total(invoice: Invoice) -> Decimal:
    if invoice.total_with_tax is not None:
        return _decimal(invoice.total_with_tax)
    return _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def _bank_direction(transaction: BankTransaction) -> str:
    value = getattr(transaction.txn_direction, "value", str(transaction.txn_direction))
    return "outflow" if "outflow" in value else "inflow"


def _bank_direction_label(transaction: BankTransaction) -> str:
    return "支出" if _bank_direction(transaction) == "outflow" else "收入"


def _bank_direction_option_label(value: str) -> str:
    return "支出" if value == "outflow" else "收入" if value == "inflow" else value


def _bank_account_label(transaction: BankTransaction) -> str:
    bank_name = str(transaction.imported_bank_name or "").strip()
    account_last4 = str(transaction.imported_bank_last4 or str(transaction.account_no or "")[-4:]).strip()
    return " ".join(part for part in [bank_name, account_last4] if part)


def _debit_amount(transaction: BankTransaction) -> str:
    return _money(transaction.amount) if _bank_direction(transaction) == "outflow" else "0.00"


def _credit_amount(transaction: BankTransaction) -> str:
    return _money(transaction.amount) if _bank_direction(transaction) == "inflow" else "0.00"


def _sortable_time(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).timestamp()
    except ValueError:
        return 0


def _relation_detail_sections(kind: str, summaries: list[Any]) -> list[dict[str, Any]]:
    typed_summaries = [summary for summary in summaries if isinstance(summary, dict)]
    if not typed_summaries:
        return [{"title": "关联明细", "fields": [{"label": "状态", "value": "暂无关联记录"}]}]
    if kind == "bank":
        return [
            {
                "title": f"支出流水 {index}",
                "fields": [
                    {"label": "支出银行", "value": summary.get("bankName")},
                    {"label": "交易时间", "value": summary.get("tradeTime")},
                    {"label": "金额", "value": summary.get("amount")},
                    {"label": "对方户名", "value": summary.get("counterpartyName")},
                    {"label": "账户明细编号-交易流水号", "value": summary.get("accountDetailNo")},
                    {"label": "摘要", "value": summary.get("summary")},
                    {"label": "备注", "value": summary.get("remark")},
                ],
            }
            for index, summary in enumerate(typed_summaries, start=1)
        ]
    return [
        {
            "title": f"发票 {index}",
            "fields": [
                {"label": "数电发票号码", "value": summary.get("digitalInvoiceNo")},
                {"label": "进项发票方名称", "value": summary.get("sellerName")},
                {"label": "开票日期", "value": summary.get("invoiceDate")},
                {"label": "价税合计", "value": summary.get("totalWithTax")},
            ],
        }
        for index, summary in enumerate(typed_summaries, start=1)
    ]


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return dict(value) if isinstance(value, dict) else {}

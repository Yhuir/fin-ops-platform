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
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    InputInvoiceUsagePaymentRulesProvider,
    StaticInputInvoiceUsagePaymentRulesProvider,
)
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.invoice_relation_query_context import DistributedInvoiceRelationContext
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
READ_MODEL_STATUS = "live_query"
SOURCE_VERSION = "input-invoice-usage:v1"
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()


FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "invoice_no": {"label": "发票号码", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "invoice_date": {"label": "开票日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "seller_name": {"label": "销方名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "seller_tax_no": {"label": "销方识别号", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "total_with_tax": {"label": "价税合计", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "amount": {"label": "不含税金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "tax_rate": {"label": "税率", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "tax_amount": {"label": "税额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "specific_business_type": {"label": "特定业务类型", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "taxable_item_name": {"label": "货物或应税劳务名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "payment_status": {"label": "支付状态", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "oa_applicant": {"label": "OA申请人", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "oa_application_type": {"label": "报销/支付", "mode": "enum_multi", "operators": {"in", "equals"}, "sortable": True},
    "oa_project_name": {"label": "项目名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_counterparty_name": {"label": "对方户名", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_trade_time": {"label": "交易时间", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "bank_amount": {"label": "流水金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "bank_name": {"label": "支付银行", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_account": {"label": "银行账户", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_direction": {"label": "收支", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_summary": {"label": "摘要", "mode": "text", "operators": {"contains"}, "sortable": True},
}

SORT_FIELDS = {field for field, config in FILTER_CONFIG.items() if config["sortable"]}

TARGET_APPLICANTS = {
    "chen_xiuyun": "陈秀云",
    "zhou_jieying": "周洁莹",
    "liu_shugang_pay": "刘树刚付",
    "liu_shugang_no_pay": "刘树刚不付",
    "wei_dailian": "韦代连",
    "liu_hanjing": "刘涵静",
}


class InputInvoiceUsageError(ValueError):
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


class InputInvoiceUsageQueryService:
    """Read-only query facade for the 进项发票使用情况 page.

    Source-of-truth boundaries:
    - input invoices and line items come from ImportNormalizationService Invoice facts;
    - bank summaries/details come from ImportNormalizationService BankTransaction facts;
    - relation evidence comes only from WorkbenchRelationReadFacade distribution;
    - OA summaries/details come from the injected OA projection when available. Without a
      stable projection, OA detail is represented as detailAvailable=false.
    """

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        oa_projection: Any | None = None,
        payment_rules_provider: InputInvoiceUsagePaymentRulesProvider | None = None,
        lifecycle_policy: Any | None = None,
        require_fresh_relations: bool = True,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._oa_projection = oa_projection
        self._payment_rules_provider = payment_rules_provider or StaticInputInvoiceUsagePaymentRulesProvider()
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy(
            input_payment_rules_provider=self._payment_rules_provider,
        )
        self._require_fresh_relations = require_fresh_relations

    def list_rows(
        self,
        *,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = "invoice_date",
        sort_direction: str | None = "desc",
    ) -> dict[str, Any]:
        page_number = _parse_positive_int(page, "page")
        page_limit = _parse_positive_int(page_size, "page_size", maximum=200)
        parsed_filters = self._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = self._parse_sort(sort_field, sort_direction)
        context = self._query_context(month_hint=month)

        rows = self._filtered_sorted_rows(
            context=context,
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
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
        }

    def filter_options(
        self,
        *,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        parsed_filters = self._parse_filters(filters)
        context = self._query_context()
        rows = self._filtered_sorted_rows(
            context=context,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field="invoice_date",
            sort_direction="desc",
        )
        fields = []
        for field, config in FILTER_CONFIG.items():
            fields.append(
                {
                    "field": field,
                    "label": config["label"],
                    "mode": config["mode"],
                    "operators": sorted(config["operators"]),
                    "sortable": bool(config["sortable"]),
                    "options": self._options_for_field(rows, field),
                }
            )
        return {
            "fields": fields,
            "context": {
                "keyword": keyword or "",
                "invoiceDateFrom": invoice_date_from,
                "invoiceDateTo": invoice_date_to,
                "month": month,
                "filters": parsed_filters,
            },
        }

    def filter_options_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
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
                "invoiceDateFrom": invoice_date_from,
                "invoiceDateTo": invoice_date_to,
                "month": month,
                "filters": parsed_filters,
            },
        }

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
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
    ) -> list[dict[str, Any]]:
        rows = self._build_rows(month=month, context=context)
        rows = [
            row
            for row in rows
            if self._row_matches_date(row, date_from=invoice_date_from, date_to=invoice_date_to, month=month)
        ]
        if keyword:
            needle = str(keyword).strip().lower()
            rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).lower()]
        rows = [row for row in rows if self._row_matches_filters(row, filters)]
        rows.sort(
            key=lambda row: self._sort_value(row, sort_field),
            reverse=sort_direction == "desc",
        )
        return rows

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

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        context = self._query_context()
        group = self._invoice_group_for_invoice_id(invoice_id, context=context)
        if group is None:
            raise InputInvoiceUsageError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        primary = group["primary"]
        lines = group["line_items"]
        return {
            "id": primary.id,
            "invoiceIdentityKey": group["identity_key"],
            "invoiceNo": primary.invoice_no,
            "invoiceCode": primary.invoice_code or "",
            "digitalInvoiceNo": primary.digital_invoice_no or "",
            "invoiceDate": primary.invoice_date or "",
            "sellerName": primary.seller_name or primary.counterparty.name,
            "sellerTaxNo": primary.seller_tax_no or primary.counterparty.tax_no or "",
            "buyerName": primary.buyer_name or "",
            "buyerTaxNo": primary.buyer_tax_no or "",
            "amount": _money(sum((_decimal(line.amount) for line in lines), start=ZERO)),
            "taxAmount": _money(sum((_decimal(line.tax_amount) for line in lines), start=ZERO)),
            "totalWithTax": _money(sum((_invoice_total(line) for line in lines), start=ZERO)),
            "taxRate": primary.tax_rate or "",
            "taxClassificationCode": primary.tax_classification_code or "",
            "specificBusinessType": primary.specific_business_type or "",
            "taxableItemName": primary.taxable_item_name or "",
            "invoiceSource": primary.invoice_source or "",
            "invoiceKind": primary.invoice_kind or "",
            "invoiceStatus": primary.invoice_status_from_source or str(primary.status.value),
            "isPositiveInvoice": primary.is_positive_invoice or "",
            "riskLevel": primary.risk_level or "",
            "issuer": primary.issuer or "",
            "remark": primary.remark or "",
            "sourceBatchId": primary.source_batch_id or "",
            "sourceLinks": deepcopy(primary.source_links),
            "lineItems": [self._line_item_payload(line) for line in lines],
        }

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        context = self._query_context()
        transaction = context.bank_transactions_by_id().get(str(bank_transaction_id))
        if transaction is None:
            raise InputInvoiceUsageError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return {
            "id": transaction.id,
            "counterpartyName": transaction.counterparty_name_raw,
            "tradeTime": transaction.trade_time or transaction.txn_date or "",
            "amount": _money(transaction.amount),
            "direction": _bank_direction(transaction),
            "bankName": transaction.imported_bank_name or "",
            "accountNo": transaction.account_no,
            "accountLast4": transaction.imported_bank_last4 or str(transaction.account_no or "")[-4:],
            "counterpartyAccountNo": transaction.counterparty_account_no or "",
            "counterpartyBankName": transaction.counterparty_bank_name or "",
            "bookedDate": transaction.booked_date or "",
            "summary": transaction.summary or "",
            "remark": transaction.remark or "",
            "currency": transaction.currency or "CNY",
            "bankTextFields": deepcopy(transaction.bank_text_fields),
            "relations": context.relation_summaries_for_row(transaction.id),
        }

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        context = self._query_context()
        record = context.oa_records_by_id([str(oa_id)]).get(str(oa_id))
        if record is None:
            return {"oaId": str(oa_id), "detailAvailable": False}
        return {
            "oaId": record.id,
            "detailAvailable": True,
            "applicantName": record.applicant,
            "applicationType": record.apply_type,
            "projectName": record.project_name_display or record.project_name,
            "workflowNo": record.case_id or "",
            "status": record.section,
            "amount": _money(record.amount),
            "month": record.month,
            "reason": record.reason,
            "counterpartyName": record.counterparty_name,
            "detailFields": deepcopy(record.detail_fields),
            "openUrl": str(record.detail_fields.get("url") or record.detail_fields.get("open_url") or ""),
            "raw": _serialize_dataclass(record),
        }

    def row_relation_details(self, row_id: str, *, kind: str) -> dict[str, Any]:
        normalized_kind = str(kind or "").strip()
        if normalized_kind not in {"oa", "bank"}:
            raise InputInvoiceUsageError("invalid_relation_kind", "kind must be oa or bank.")
        context = self._query_context()
        row = self._row_by_id(row_id, context=context)
        if row is None:
            raise InputInvoiceUsageError(
                "row_not_found",
                f"Input invoice usage row not found: {row_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        relation_payload = row["oa"] if normalized_kind == "oa" else row["bankTransactions"]
        return {
            "rowId": row["id"],
            "invoiceId": row["invoiceId"],
            "kind": normalized_kind,
            "detailAvailable": relation_payload.get("detailMode") != "none",
            "relationCount": relation_payload.get("relationCount", 0),
            "hasMultiple": relation_payload.get("hasMultiple", False),
            "summaries": relation_payload.get("summaries", []),
            "relations": context.relation_summaries_for_row(row["invoiceId"]),
        }

    def payment_status_rules(self) -> dict[str, Any]:
        return self._payment_rules_provider.payment_status_rules_payload(can_save=True)

    def _build_rows(self, *, month: str | None, context: DistributedInvoiceRelationContext) -> list[dict[str, Any]]:
        groups = self._invoice_groups(month=month, context=context)
        context.preload_relation_rows([line.id for group in groups for line in group["line_items"]])
        context.preload_oa_records_from_relations(
            [line.id for group in groups for line in group["line_items"]]
        )
        return [self._row_payload(group, context=context) for group in groups]

    def _invoice_groups(
        self,
        *,
        month: str | None = None,
        context: DistributedInvoiceRelationContext,
    ) -> list[dict[str, Any]]:
        source_month = str(month).strip() if month not in (None, "") else "all"
        invoices = [
            invoice
            for invoice in context.list_invoices(month=source_month, invoice_type=InvoiceType.INPUT)
        ]
        grouped: dict[str, list[Invoice]] = {}
        for invoice in invoices:
            grouped.setdefault(self._identity_key(invoice), []).append(invoice)
        groups = []
        for identity_key, line_items in grouped.items():
            sorted_items = sorted(line_items, key=lambda item: str(item.id))
            groups.append({"identity_key": identity_key, "primary": sorted_items[0], "line_items": sorted_items})
        groups.sort(key=lambda group: (str(group["primary"].invoice_date or ""), str(group["identity_key"])))
        return groups

    def _invoice_group_for_invoice_id(
        self,
        invoice_id: str,
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any] | None:
        normalized_id = str(invoice_id)
        for group in self._invoice_groups(month=None, context=context):
            if normalized_id in {line.id for line in group["line_items"]}:
                return group
        return None

    def _row_by_id(self, row_id: str, *, context: DistributedInvoiceRelationContext) -> dict[str, Any] | None:
        normalized_id = str(row_id)
        for row in self._build_rows(month=None, context=context):
            if row["id"] == normalized_id:
                return row
        return None

    def _row_payload(self, group: dict[str, Any], *, context: DistributedInvoiceRelationContext) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        line_items: list[Invoice] = group["line_items"]
        invoice_ids = [line.id for line in line_items]
        relations = context.distributed_relations_for_row_ids(invoice_ids)
        bank_payload = self._bank_relation_payload(primary, line_items, relations, context=context)
        oa_payload = self._oa_relation_payload(primary, line_items, relations, context=context)
        payment_status = self._payment_status(primary, line_items, relations, oa_payload, bank_payload, context=context)
        row_id = "invoice_usage_row_" + sha1(str(group["identity_key"]).encode("utf-8")).hexdigest()[:16]
        return {
            "id": row_id,
            "invoiceId": primary.id,
            "invoiceIdentityKey": group["identity_key"],
            "invoice": self._invoice_summary(primary, line_items),
            "paymentStatus": payment_status,
            "oa": oa_payload,
            "bankTransactions": bank_payload,
        }

    def _invoice_summary(self, primary: Invoice, line_items: list[Invoice]) -> dict[str, Any]:
        total_with_tax = sum((_invoice_total(line) for line in line_items), start=ZERO)
        amount = sum((_decimal(line.amount) for line in line_items), start=ZERO)
        tax_amount = sum((_decimal(line.tax_amount) for line in line_items), start=ZERO)
        return {
            "invoiceNo": primary.digital_invoice_no or primary.invoice_no,
            "invoiceCode": primary.invoice_code or "",
            "digitalInvoiceNo": primary.digital_invoice_no or "",
            "invoiceDate": primary.invoice_date or "",
            "sellerName": primary.seller_name or primary.counterparty.name,
            "sellerTaxNo": primary.seller_tax_no or primary.counterparty.tax_no or "",
            "totalWithTax": _money(total_with_tax),
            "amount": _money(amount),
            "taxRate": primary.tax_rate or "",
            "taxAmount": _money(tax_amount),
            "specificBusinessType": primary.specific_business_type or "",
            "taxableItemName": primary.taxable_item_name or "",
            "lineItemCount": len(line_items),
            "hasMoreInvoiceLines": len(line_items) > 1,
        }

    def _bank_relation_payload(
        self,
        primary_invoice: Invoice,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        bank_map = context.bank_transactions_by_id()
        summaries = []
        seen: set[str] = set()
        for relation in relations:
            for row_id in list(relation.get("row_ids") or []):
                bank = bank_map.get(str(row_id))
                if bank is not None and bank.id not in seen:
                    seen.add(bank.id)
                    summaries.append(self._bank_summary(bank, primary_invoice, line_items, relation))
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        return {
            "primaryBankTransactionId": primary.get("bankTransactionId"),
            "counterpartyName": primary.get("counterpartyName", ""),
            "tradeTime": primary.get("tradeTime", ""),
            "amount": primary.get("amount", ""),
            "direction": primary.get("direction", ""),
            "directionLabel": primary.get("directionLabel", ""),
            "bankName": primary.get("bankName", ""),
            "accountLast4": primary.get("accountLast4", ""),
            "bankAccount": primary.get("bankAccount", ""),
            "summary": primary.get("summary", ""),
            "remark": primary.get("remark", ""),
            "relationCount": len(public_summaries),
            "hasMultiple": len(public_summaries) > 1,
            "detailMode": "none" if not public_summaries else "list" if len(public_summaries) > 1 else "single",
            "summaries": public_summaries,
        }

    def _bank_summary(
        self,
        bank: BankTransaction,
        primary_invoice: Invoice,
        line_items: list[Invoice],
        relation: dict[str, Any],
    ) -> dict[str, Any]:
        invoice_total = sum((_invoice_total(line) for line in line_items), start=ZERO)
        diff = abs(_decimal(bank.amount) - invoice_total)
        completeness = 0 if self._relation_has_invoice_oa_bank(relation) and self._relation_amount_check_is_matched(relation) else 1
        timestamp = _sortable_time(bank.trade_time or bank.txn_date)
        return {
            "bankTransactionId": bank.id,
            "counterpartyName": bank.counterparty_name_raw,
            "tradeTime": bank.trade_time or bank.txn_date or "",
            "amount": _money(bank.amount),
            "direction": _bank_direction(bank),
            "directionLabel": _bank_direction_label(bank),
            "bankName": bank.imported_bank_name or "",
            "accountLast4": bank.imported_bank_last4 or str(bank.account_no or "")[-4:],
            "bankAccount": _bank_account_label(bank),
            "summary": bank.summary or "",
            "remark": bank.remark or "",
            "relationCaseId": relation.get("case_id", ""),
            "_sort": (completeness, diff, -timestamp, bank.id),
        }

    def _oa_relation_payload(
        self,
        primary_invoice: Invoice,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        oa_ids = []
        for relation in relations:
            for row_id, row_type in self._typed_relation_rows(relation):
                if row_type == "oa" and row_id not in oa_ids:
                    oa_ids.append(row_id)
        records = context.oa_records_by_id(oa_ids)
        summaries = [
            self._oa_summary(oa_id, records.get(oa_id), primary_invoice, line_items, self._relation_for_row_id(relations, oa_id))
            for oa_id in oa_ids
        ]
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        return {
            "primaryOaId": primary.get("oaId"),
            "applicantName": primary.get("applicantName", ""),
            "applicationType": primary.get("applicationType", ""),
            "projectName": primary.get("projectName", ""),
            "relationCount": len(public_summaries),
            "hasMultiple": len(public_summaries) > 1,
            "detailMode": "none" if not public_summaries else "list" if len(public_summaries) > 1 else "single",
            "detailAvailable": any(summary.get("detailAvailable") for summary in public_summaries),
            "summaries": public_summaries,
        }

    def _oa_summary(
        self,
        oa_id: str,
        record: OAApplicationRecord | None,
        primary_invoice: Invoice,
        line_items: list[Invoice],
        relation: dict[str, Any] | None,
    ) -> dict[str, Any]:
        invoice_total = sum((_invoice_total(line) for line in line_items), start=ZERO)
        oa_amount = _decimal(record.amount) if record is not None else ZERO
        diff = abs(oa_amount - invoice_total) if record is not None else Decimal("999999999")
        completeness = 0 if relation and self._relation_has_invoice_oa_bank(relation) and self._relation_amount_check_is_matched(relation) else 1
        return {
            "oaId": oa_id,
            "applicantName": record.applicant if record is not None else "",
            "applicationType": record.apply_type if record is not None else "",
            "projectName": (record.project_name_display or record.project_name) if record is not None else "",
            "amount": _money(record.amount) if record is not None else "",
            "status": record.section if record is not None else "",
            "detailAvailable": record is not None,
            "relationCaseId": relation.get("case_id", "") if relation else "",
            "_sort": (completeness, diff, 0, oa_id),
        }

    def _payment_status(
        self,
        primary: Invoice,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        oa_payload: dict[str, Any],
        bank_payload: dict[str, Any],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, str]:
        has_oa = int(oa_payload.get("relationCount") or 0) > 0
        has_bank = int(bank_payload.get("relationCount") or 0) > 0
        applicant = str(oa_payload.get("applicantName") or "")
        fully_matched = self._has_fully_matched_relation(line_items, relations, context=context)
        return self._lifecycle_policy.evaluate_input_invoice_payment(
            has_oa=has_oa,
            has_bank=has_bank,
            applicant_name=applicant,
            fully_matched=fully_matched,
            invoice_oa_amount_matched=self._has_invoice_oa_amount_match(line_items, relations, context=context),
        )

    def _has_fully_matched_relation(
        self,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> bool:
        invoice_total = sum((_invoice_total(line) for line in line_items), start=ZERO)
        bank_map = context.bank_transactions_by_id()
        for relation in relations:
            if not self._relation_has_invoice_oa_bank(relation):
                continue
            if not self._relation_amount_check_is_matched(relation):
                continue
            oa_ids = [row_id for row_id, row_type in self._typed_relation_rows(relation) if row_type == "oa"]
            bank_ids = [row_id for row_id, row_type in self._typed_relation_rows(relation) if row_type == "bank"]
            oa_records = context.oa_records_by_id(oa_ids)
            if any(_within_cent(_decimal(record.amount), invoice_total) for record in oa_records.values()) and any(
                _within_cent(_decimal(bank_map[bank_id].amount), invoice_total)
                for bank_id in bank_ids
                if bank_id in bank_map
            ):
                return True
        return False

    def _has_invoice_oa_amount_match(
        self,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> bool:
        invoice_total = sum((_invoice_total(line) for line in line_items), start=ZERO)
        for relation in relations:
            if not self._relation_amount_check_is_matched(relation):
                continue
            oa_ids = [row_id for row_id, row_type in self._typed_relation_rows(relation) if row_type == "oa"]
            oa_records = context.oa_records_by_id(oa_ids)
            if any(_within_cent(_decimal(record.amount), invoice_total) for record in oa_records.values()):
                return True
        return False

    def _parse_filters(self, filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if filters in (None, ""):
            return []
        if isinstance(filters, str):
            try:
                parsed = json.loads(unquote(filters))
            except json.JSONDecodeError as exc:
                raise InputInvoiceUsageError("invalid_filter_json", "filters must be a URL-encoded JSON array.") from exc
        else:
            parsed = filters
        if not isinstance(parsed, list):
            raise InputInvoiceUsageError("invalid_filter_json", "filters must be a JSON array.")
        normalized = []
        for item in parsed:
            if not isinstance(item, dict):
                raise InputInvoiceUsageError("invalid_filter_json", "each filter must be an object.")
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if field not in FILTER_CONFIG:
                raise InputInvoiceUsageError("invalid_filter_field", f"Unsupported filter field: {field}", details={"field": field})
            if operator not in FILTER_CONFIG[field]["operators"]:
                raise InputInvoiceUsageError(
                    "invalid_filter_operator",
                    f"Unsupported operator for {field}: {operator}",
                    details={"field": field, "operator": operator},
                )
            normalized.append({"field": field, "operator": operator, "value": item.get("value"), "values": list(item.get("values") or [])})
        return normalized

    def _parse_sort(self, sort_field: str | None, sort_direction: str | None) -> tuple[str, str]:
        field = str(sort_field or "invoice_date").strip() or "invoice_date"
        direction = str(sort_direction or "desc").strip().lower() or "desc"
        if field not in SORT_FIELDS:
            raise InputInvoiceUsageError("invalid_sort_field", f"Unsupported sort field: {field}", details={"field": field})
        if direction not in {"asc", "desc"}:
            raise InputInvoiceUsageError("invalid_sort_direction", "sort_direction must be asc or desc.")
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
                else:
                    if str(value or "") != str(expected or ""):
                        return False
            elif operator == "in":
                values = {str(item) for item in list(filter_item.get("values") or [])}
                if str(value or "") not in values:
                    return False
            elif operator == "between":
                bounds = filter_item.get("value")
                if not isinstance(bounds, dict):
                    raise InputInvoiceUsageError("invalid_filter_value", "between filter requires min/max object.")
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
    def _row_matches_date(row: dict[str, Any], *, date_from: str | None, date_to: str | None, month: str | None) -> bool:
        invoice_date = str(row["invoice"].get("invoiceDate") or "")
        if month and str(month).strip() not in {"", "all"} and not invoice_date.startswith(str(month)[:7]):
            return False
        if date_from and invoice_date[:10] < str(date_from):
            return False
        if date_to and invoice_date[:10] > str(date_to):
            return False
        return True

    def _sort_value(self, row: dict[str, Any], field: str) -> Any:
        value = self._field_value(row, field)
        if FILTER_CONFIG[field]["mode"] == "money":
            return _decimal(value)
        if field == "invoice_no" and value in (None, ""):
            return "~~~~"
        return str(value or "")

    @staticmethod
    def _field_value(row: dict[str, Any], field: str) -> Any:
        invoice = row["invoice"]
        oa = row["oa"]
        bank = row["bankTransactions"]
        payment = row["paymentStatus"]
        values = {
            "invoice_no": invoice.get("invoiceNo"),
            "invoice_date": invoice.get("invoiceDate"),
            "seller_name": invoice.get("sellerName"),
            "seller_tax_no": invoice.get("sellerTaxNo"),
            "total_with_tax": invoice.get("totalWithTax"),
            "amount": invoice.get("amount"),
            "tax_rate": invoice.get("taxRate"),
            "tax_amount": invoice.get("taxAmount"),
            "specific_business_type": invoice.get("specificBusinessType"),
            "taxable_item_name": invoice.get("taxableItemName"),
            "payment_status": payment.get("code"),
            "oa_applicant": oa.get("applicantName"),
            "oa_application_type": oa.get("applicationType"),
            "oa_project_name": oa.get("projectName"),
            "bank_counterparty_name": bank.get("counterpartyName"),
            "bank_trade_time": bank.get("tradeTime"),
            "bank_amount": bank.get("amount"),
            "bank_name": bank.get("bankName"),
            "bank_account": bank.get("bankAccount"),
            "bank_direction": bank.get("direction"),
            "bank_summary": bank.get("summary"),
        }
        return values.get(field)

    def _options_for_field(self, rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        if FILTER_CONFIG[field]["mode"] in {"date", "money", "text"} and field not in {"payment_status"}:
            if FILTER_CONFIG[field]["mode"] != "enum_multi":
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
                labels[key] = "支出" if key == "outflow" else "收入" if key == "inflow" else key
            else:
                labels[key] = key
        return [{"value": value, "label": labels[value], "count": counts[value]} for value in sorted(counts)]

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invoiceCount": len(rows),
            "totalWithTax": _money(sum((_decimal(row["invoice"]["totalWithTax"]) for row in rows), start=ZERO)),
            "matchedOaCount": sum(1 for row in rows if row["oa"]["relationCount"]),
            "matchedBankTransactionCount": sum(1 for row in rows if row["bankTransactions"]["relationCount"]),
            "pendingCount": sum(1 for row in rows if row["paymentStatus"]["code"] == "pending"),
        }

    def _bank_transactions_by_id(self) -> dict[str, BankTransaction]:
        return {transaction.id: transaction for transaction in self._import_service.list_transactions(month="all")}

    def _oa_records_by_id(self, oa_ids: list[str]) -> dict[str, OAApplicationRecord]:
        normalized_ids = [str(oa_id).strip() for oa_id in oa_ids if str(oa_id).strip()]
        if not normalized_ids or self._oa_projection is None:
            return {}
        list_by_ids = getattr(self._oa_projection, "list_application_records_by_row_ids", None)
        if callable(list_by_ids):
            records = list_by_ids(normalized_ids)
        else:
            list_all = getattr(self._oa_projection, "list_all_application_records", None)
            records = list_all() if callable(list_all) else []
        return {record.id: record for record in records if isinstance(record, OAApplicationRecord)}

    @staticmethod
    def _identity_key(invoice: Invoice) -> str:
        return OBJECT_IDENTITY_POLICY.legacy_invoice_identity_key(invoice)

    @staticmethod
    def _line_item_payload(invoice: Invoice) -> dict[str, Any]:
        return {
            "id": invoice.id,
            "taxClassificationCode": invoice.tax_classification_code or "",
            "specificBusinessType": invoice.specific_business_type or "",
            "taxableItemName": invoice.taxable_item_name or "",
            "specificationModel": invoice.specification_model or "",
            "unit": invoice.unit or "",
            "quantity": _money(invoice.quantity) if invoice.quantity is not None else "",
            "unitPrice": _money(invoice.unit_price) if invoice.unit_price is not None else "",
            "amount": _money(invoice.amount),
            "taxRate": invoice.tax_rate or "",
            "taxAmount": _money(invoice.tax_amount),
            "totalWithTax": _money(_invoice_total(invoice)),
            "remark": invoice.remark or "",
        }

    @staticmethod
    def _typed_relation_rows(relation: dict[str, Any]) -> list[tuple[str, str]]:
        row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
        typed = []
        for index, row_id in enumerate(row_ids):
            row_type = row_types[index] if index < len(row_types) else _infer_row_type(row_id)
            typed.append((row_id, row_type))
        return typed

    def _relation_has_invoice_oa_bank(self, relation: dict[str, Any]) -> bool:
        types = {row_type for _, row_type in self._typed_relation_rows(relation)}
        return {"invoice", "oa", "bank"}.issubset(types)

    @staticmethod
    def _relation_amount_check_is_matched(relation: dict[str, Any]) -> bool:
        amount_check = relation.get("amount_check")
        return isinstance(amount_check, dict) and amount_check.get("matched") is True

    def _relation_for_row_id(self, relations: list[dict[str, Any]], row_id: str) -> dict[str, Any] | None:
        for relation in relations:
            if row_id in {typed_row_id for typed_row_id, _ in self._typed_relation_rows(relation)}:
                return relation
        return None

def _parse_positive_int(value: int | str | None, field: str, *, maximum: int | None = None) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise InputInvoiceUsageError("invalid_paging", f"{field} must be a positive integer.") from exc
    if number < 1:
        raise InputInvoiceUsageError("invalid_paging", f"{field} must be a positive integer.")
    if maximum is not None and number > maximum:
        raise InputInvoiceUsageError("invalid_paging", f"{field} must be <= {maximum}.")
    return number


def _payment_status(code: str, label: str, reason: str, matched_rule_id: str) -> dict[str, str]:
    return {"code": code, "label": label, "reason": reason, "matchedRuleId": matched_rule_id, "severity": "warning" if code == "pending" else "success"}


def _invoice_total(invoice: Invoice) -> Decimal:
    if invoice.total_with_tax is not None:
        return _decimal(invoice.total_with_tax)
    return _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def _decimal(value: Any) -> Decimal:
    if value in (None, ""):
        return ZERO
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return ZERO


def _money(value: Any) -> str:
    return f"{_decimal(value).quantize(CENT)}"


def _within_cent(left: Decimal, right: Decimal) -> bool:
    return abs(left - right) <= CENT


def _bank_direction(transaction: BankTransaction) -> str:
    value = getattr(transaction.txn_direction, "value", str(transaction.txn_direction))
    return "outflow" if "outflow" in value else "inflow"


def _bank_direction_label(transaction: BankTransaction) -> str:
    return "支出" if _bank_direction(transaction) == "outflow" else "收入"


def _bank_account_label(transaction: BankTransaction) -> str:
    bank_name = str(transaction.imported_bank_name or "").strip()
    account_last4 = str(transaction.imported_bank_last4 or str(transaction.account_no or "")[-4:]).strip()
    return " ".join(part for part in [bank_name, account_last4] if part)


def _sortable_time(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).timestamp()
    except ValueError:
        return 0


def _infer_row_type(row_id: str) -> str:
    if row_id.startswith("bank"):
        return "bank"
    if row_id.startswith("oa"):
        return "oa"
    return "invoice"


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return dict(value) if isinstance(value, dict) else {}

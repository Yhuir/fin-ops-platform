from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from http import HTTPStatus
from io import BytesIO
import json
import re
from typing import Any
from urllib.parse import unquote

from openpyxl import Workbook

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
    relation_is_linked,
    relation_status,
    summary_is_linked,
)
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.workbench_relation_modes import (
    OUTPUT_INVOICE_REVERSAL_RELATION_MODE,
)


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()
OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT = 20_000
OUTPUT_INVOICE_COLLECTION_EXPORT_COLUMNS = [
    "序号",
    "发票号码",
    "开票日期",
    "购方",
    "购方识别号",
    "价税合计",
    "收款状态",
    "已收金额",
    "待收金额",
    "收款方",
    "收款日期",
    "收款金额",
    "收款银行",
    "摘要",
    "冲红蓝字发票号码",
    "红蓝票关系",
]

REVERSED_BLUE_INVOICE_NO_PATTERN = re.compile(
    r"被红冲蓝字数电发票号码\s*[：:]\s*(\d{20})(?!\d)"
)

FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "invoice_no": {
        "label": "发票号码",
        "mode": "text",
        "operators": {"contains", "equals"},
        "sortable": True,
    },
    "invoice_date": {
        "label": "开票日期",
        "mode": "date",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "buyer_name": {
        "label": "购方",
        "mode": "enum_multi",
        "operators": {"in", "contains"},
        "sortable": True,
    },
    "buyer_tax_no": {
        "label": "购方识别号",
        "mode": "text",
        "operators": {"contains", "equals"},
        "sortable": True,
    },
    "seller_name": {
        "label": "销方",
        "mode": "enum_multi",
        "operators": {"in", "contains"},
        "sortable": True,
    },
    "total_with_tax": {
        "label": "价税合计",
        "mode": "money",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "tax_amount": {
        "label": "税额",
        "mode": "money",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "tax_rate": {
        "label": "税率",
        "mode": "enum_multi",
        "operators": {"in"},
        "sortable": True,
    },
    "specific_business_type": {
        "label": "特定业务类型",
        "mode": "enum_multi",
        "operators": {"in"},
        "sortable": False,
    },
    "taxable_item_name": {
        "label": "货物或应税劳务名称",
        "mode": "enum_multi",
        "operators": {"in", "contains"},
        "sortable": True,
    },
    "collection_status": {
        "label": "收款状态",
        "mode": "enum_multi",
        "operators": {"in"},
        "sortable": True,
    },
    "pending_amount": {
        "label": "待收款金额",
        "mode": "money",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "bank_counterparty_name": {
        "label": "付款方",
        "mode": "enum_multi",
        "operators": {"in", "contains"},
        "sortable": True,
    },
    "bank_trade_time": {
        "label": "收款日期",
        "mode": "date",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "bank_amount": {
        "label": "收款金额",
        "mode": "money",
        "operators": {"between", "equals"},
        "sortable": True,
    },
    "bank_name": {
        "label": "收款银行",
        "mode": "enum_multi",
        "operators": {"in"},
        "sortable": True,
    },
    "bank_summary": {
        "label": "摘要",
        "mode": "text",
        "operators": {"contains"},
        "sortable": True,
    },
}
SORT_FIELDS = {
    field for field, config in FILTER_CONFIG.items() if config["sortable"]
}


class OutputInvoiceCollectionError(ValueError):
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


class OutputInvoiceCollectionQueryService:
    """Read output invoices, canonical relations, and related income transactions."""

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_reader: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._relation_reader = relation_reader

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
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        del tenant_id
        page_number = _parse_positive_int(page, "page")
        page_limit = _parse_positive_int(page_size, "page_size", maximum=200)
        parsed_filters = self._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = self._parse_sort(
            sort_field,
            sort_direction,
        )
        rows = self._filtered_sorted_rows(
            context=self._query_context(month_hint=month),
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field=normalized_sort_field,
            sort_direction=normalized_sort_direction,
        )
        total = len(rows)
        return {
            "rows": rows[(page_number - 1) * page_limit : page_number * page_limit],
            "pagination": {
                "page": page_number,
                "pageSize": page_limit,
                "total": total,
            },
            "summary": self.summary_for_rows(rows),
            "appliedFilters": {"filters": parsed_filters},
            "sort": {
                "field": normalized_sort_field,
                "direction": normalized_sort_direction,
            },
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
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        del tenant_id
        parsed_filters = self._parse_filters(filters)
        rows = self._filtered_sorted_rows(
            context=self._query_context(month_hint=month),
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field="invoice_date",
            sort_direction="desc",
        )
        return self.filter_options_for_rows(
            rows=rows,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
        )

    def filter_options_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        del tenant_id
        parsed_filters = self._parse_filters(filters)
        return {
            "fields": [
                {
                    "field": field,
                    "label": config["label"],
                    "mode": config["mode"],
                    "operators": sorted(config["operators"]),
                    "sortable": bool(config["sortable"]),
                    "options": self._options_for_field(rows, field),
                }
                for field, config in FILTER_CONFIG.items()
            ],
            "context": {
                "keyword": keyword or "",
                "invoiceDateFrom": invoice_date_from,
                "invoiceDateTo": invoice_date_to,
                "month": month,
                "filters": parsed_filters,
            },
        }

    def export_preview(
        self,
        *,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = "invoice_date",
        sort_direction: str | None = "desc",
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self.export_preview_for_rows(
            rows=self._export_rows(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=filters,
                sort_field=sort_field,
                sort_direction=sort_direction,
                tenant_id=tenant_id,
            )
        )

    def export(
        self,
        *,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = "invoice_date",
        sort_direction: str | None = "desc",
        tenant_id: str = "default",
    ) -> tuple[str, bytes]:
        return self.export_for_rows(
            self._export_rows(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=filters,
                sort_field=sort_field,
                sort_direction=sort_direction,
                tenant_id=tenant_id,
            )
        )

    def export_preview_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        self._ensure_export_row_limit(rows)
        sample_rows = [
            self._export_row(index, row)
            for index, row in enumerate(rows[:5], start=1)
        ]
        file_name = self._export_file_name()
        return {
            "file_name": file_name,
            "fileName": file_name,
            "row_count": len(rows),
            "rowCount": len(rows),
            "scope_label": "当前筛选",
            "scopeLabel": "当前筛选",
            "columns": list(OUTPUT_INVOICE_COLLECTION_EXPORT_COLUMNS),
            "sample_rows": sample_rows,
            "sampleRows": sample_rows,
        }

    def export_for_rows(
        self,
        rows: list[dict[str, Any]],
    ) -> tuple[str, bytes]:
        self._ensure_export_row_limit(rows)
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "销项收款"
        sheet.append(list(OUTPUT_INVOICE_COLLECTION_EXPORT_COLUMNS))
        for index, row in enumerate(rows, start=1):
            export_row = self._export_row(index, row)
            sheet.append(
                [
                    export_row.get(column, "")
                    for column in OUTPUT_INVOICE_COLLECTION_EXPORT_COLUMNS
                ]
            )
        for column_cells in sheet.columns:
            first_cell = column_cells[0]
            sheet.column_dimensions[first_cell.column_letter].width = min(
                36,
                max(10, len(str(first_cell.value or "")) + 4),
            )
        buffer = BytesIO()
        workbook.save(buffer)
        return self._export_file_name(), buffer.getvalue()

    def row_by_id(
        self,
        row_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        del tenant_id
        normalized_id = str(row_id or "").strip()
        context = self._query_context()
        for row in self._build_rows(month=None, context=context):
            if row["id"] == normalized_id or row["invoiceId"] == normalized_id:
                return row
        return None

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        context = self._query_context()
        group = self._invoice_group_for_invoice_id(invoice_id, context=context)
        if group is None:
            raise OutputInvoiceCollectionError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return self.invoice_detail_for_group(group)

    def invoice_detail_for_group(
        self,
        group: dict[str, Any],
    ) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        lines: list[Invoice] = list(group["line_items"])
        return {
            "id": primary.id,
            "invoiceIdentityKey": group["identity_key"],
            "invoiceNo": primary.invoice_no,
            "invoiceCode": primary.invoice_code or "",
            "digitalInvoiceNo": primary.digital_invoice_no or "",
            "invoiceDate": primary.invoice_date or "",
            "sellerName": primary.seller_name or "",
            "sellerTaxNo": primary.seller_tax_no or "",
            "buyerName": primary.buyer_name or primary.counterparty.name,
            "buyerTaxNo": primary.buyer_tax_no
            or primary.counterparty.tax_no
            or "",
            "amount": _money(
                sum((_decimal(line.amount) for line in lines), start=ZERO)
            ),
            "taxAmount": _money(
                sum((_decimal(line.tax_amount) for line in lines), start=ZERO)
            ),
            "totalWithTax": _money(
                sum((_invoice_total(line) for line in lines), start=ZERO)
            ),
            "taxRate": primary.tax_rate or "",
            "taxClassificationCode": primary.tax_classification_code or "",
            "specificBusinessType": primary.specific_business_type or "",
            "taxableItemName": primary.taxable_item_name or "",
            "invoiceSource": primary.invoice_source or "",
            "invoiceKind": primary.invoice_kind or "",
            "invoiceStatus": primary.invoice_status_from_source
            or str(primary.status.value),
            "isPositiveInvoice": primary.is_positive_invoice or "",
            "riskLevel": primary.risk_level or "",
            "issuer": primary.issuer or "",
            "remark": _join_non_empty(line.remark for line in lines),
            "reversalTargetInvoiceNos": _reversal_target_invoice_nos(
                line.remark for line in lines
            ),
            "sourceBatchId": primary.source_batch_id or "",
            "sourceLinks": deepcopy(primary.source_links),
            "lineItems": [self._line_item_payload(line) for line in lines],
        }

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
    ) -> dict[str, Any]:
        context = self._query_context()
        transaction = context.bank_transactions_by_id().get(
            str(bank_transaction_id)
        )
        if transaction is None:
            raise OutputInvoiceCollectionError(
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
            "accountLast4": transaction.imported_bank_last4
            or str(transaction.account_no or "")[-4:],
            "counterpartyAccountNo": transaction.counterparty_account_no or "",
            "counterpartyBankName": transaction.counterparty_bank_name or "",
            "bookedDate": transaction.booked_date or "",
            "summary": transaction.summary or "",
            "remark": transaction.remark or "",
            "currency": transaction.currency or "",
            "bankTextFields": deepcopy(transaction.bank_text_fields),
            "relations": context.relation_summaries_for_row(transaction.id),
        }

    def _query_context(
        self,
        *,
        month_hint: str | None = None,
    ) -> DistributedInvoiceRelationContext:
        return DistributedInvoiceRelationContext(
            import_service=self._import_service,
            relation_reader=self._relation_reader,
            month_hint=month_hint,
        )

    def _export_rows(
        self,
        *,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        month: str | None,
        filters: str | list[dict[str, Any]] | None,
        sort_field: str | None,
        sort_direction: str | None,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        del tenant_id
        parsed_filters = self._parse_filters(filters)
        field, direction = self._parse_sort(sort_field, sort_direction)
        rows = self._filtered_sorted_rows(
            context=self._query_context(month_hint=month),
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field=field,
            sort_direction=direction,
        )
        self._ensure_export_row_limit(rows)
        return rows

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
        rows = [
            row
            for row in self._build_rows(month=month, context=context)
            if self._row_matches_date(
                row,
                date_from=invoice_date_from,
                date_to=invoice_date_to,
                month=month,
            )
        ]
        if keyword:
            needle = str(keyword).strip().lower()
            rows = [
                row
                for row in rows
                if needle in json.dumps(row, ensure_ascii=False).lower()
            ]
        rows = [row for row in rows if self._row_matches_filters(row, filters)]
        rows.sort(
            key=lambda row: self._sort_value(row, sort_field),
            reverse=sort_direction == "desc",
        )
        return rows

    def _build_rows(
        self,
        *,
        month: str | None,
        context: DistributedInvoiceRelationContext,
    ) -> list[dict[str, Any]]:
        groups = self._invoice_groups(month=month, context=context)
        context.preload_relation_rows(
            [
                invoice.id
                for group in groups
                for invoice in list(group["line_items"])
            ]
        )
        return [
            self._row_payload(group, groups, context=context)
            for group in groups
        ]

    def _invoice_groups(
        self,
        *,
        month: str | None,
        context: DistributedInvoiceRelationContext,
    ) -> list[dict[str, Any]]:
        source_month = str(month).strip() if month not in (None, "") else "all"
        invoices = context.list_invoices(
            month=source_month,
            invoice_type=InvoiceType.OUTPUT,
        )
        current_invoice_ids = {invoice.id for invoice in invoices}
        all_invoices_by_id = context.invoices_by_id(
            month="all",
            invoice_type=InvoiceType.OUTPUT,
        )
        context.preload_relation_rows([invoice.id for invoice in invoices])
        grouped: dict[str, list[Invoice]] = {}
        for invoice in invoices:
            grouped.setdefault(self._identity_key(invoice), []).append(invoice)
        base_groups = [
            self._base_group(identity_key, line_items)
            for identity_key, line_items in grouped.items()
        ]
        relation_groups: list[dict[str, Any]] = []
        emitted_invoice_ids: set[str] = set()
        emitted_case_ids: set[str] = set()
        for invoice in invoices:
            for relation in context.distributed_relations_for_row_ids([invoice.id]):
                case_id = str(
                    relation.get("case_id")
                    or relation.get("relation_id")
                    or ""
                ).strip()
                if (
                    not case_id
                    or case_id in emitted_case_ids
                    or not relation_is_linked(relation)
                    or str(relation.get("relation_mode") or "")
                    == OUTPUT_INVOICE_REVERSAL_RELATION_MODE
                ):
                    continue
                output_ids = [
                    row_id
                    for row_id, row_type in context.typed_relation_rows(relation)
                    if row_type == "invoice" and row_id in all_invoices_by_id
                ]
                if len(output_ids) <= 1 or invoice.id not in output_ids:
                    continue
                line_items = [all_invoices_by_id[row_id] for row_id in output_ids]
                primary = sorted(
                    line_items,
                    key=lambda item: (
                        0 if item.id in current_invoice_ids else 1,
                        str(item.invoice_date or ""),
                        str(item.id),
                    ),
                )[0]
                relation_groups.append(
                    {
                        "identity_key": self._identity_key(primary),
                        "group_key": f"relation:{case_id}",
                        "primary": primary,
                        "line_items": sorted(
                            line_items,
                            key=lambda item: str(item.id),
                        ),
                    }
                )
                emitted_case_ids.add(case_id)
                emitted_invoice_ids.update(item.id for item in line_items)
        groups = [
            *relation_groups,
            *[
                group
                for group in base_groups
                if not any(
                    line.id in emitted_invoice_ids
                    for line in list(group["line_items"])
                )
            ],
        ]
        groups.sort(
            key=lambda group: (
                str(group["primary"].invoice_date or ""),
                str(group["identity_key"]),
            )
        )
        return groups

    @staticmethod
    def _base_group(
        identity_key: str,
        line_items: list[Invoice],
    ) -> dict[str, Any]:
        items = sorted(line_items, key=lambda item: str(item.id))
        return {
            "identity_key": identity_key,
            "group_key": identity_key,
            "primary": items[0],
            "line_items": items,
        }

    def _invoice_group_for_invoice_id(
        self,
        invoice_id: str,
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any] | None:
        for group in self._invoice_groups(month=None, context=context):
            if str(invoice_id) in {
                str(line.id) for line in list(group["line_items"])
            }:
                return group
        return None

    def _row_payload(
        self,
        group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        line_items: list[Invoice] = list(group["line_items"])
        invoice_ids = [line.id for line in line_items]
        relations = context.distributed_relations_for_row_ids(invoice_ids)
        bank_payload = self._bank_relation_payload(
            primary,
            line_items,
            relations,
            context=context,
        )
        invoice_payload = self._invoice_relation_payload(
            group,
            all_groups,
            relations,
            context=context,
        )
        reversal_relations = [
            relation
            for relation in relations
            if relation_is_linked(relation)
            and str(relation.get("relation_mode") or "")
            == OUTPUT_INVOICE_REVERSAL_RELATION_MODE
        ]
        invoice_total = sum(
            (_invoice_total(line) for line in line_items),
            start=ZERO,
        )
        collected_total = self._bank_total(
            list(bank_payload["summaries"]),
            direction="inflow",
        )
        collection_status = _collection_status_for_facts(
            invoice_total=invoice_total,
            invoice_sign=_invoice_sign(primary, invoice_total),
            collected_total=collected_total,
            has_reversal=bool(reversal_relations),
        )
        row_id = "output_invoice_collection_row_" + sha1(
            str(group.get("group_key") or group["identity_key"]).encode("utf-8")
        ).hexdigest()[:16]
        return {
            "id": row_id,
            "invoiceId": primary.id,
            "invoiceIdentityKey": group["identity_key"],
            "invoice": self._invoice_summary(primary, line_items),
            "collectionStatus": collection_status,
            "bankTransactions": bank_payload,
            "invoiceRelations": invoice_payload,
        }

    def _invoice_summary(
        self,
        primary: Invoice,
        line_items: list[Invoice],
    ) -> dict[str, Any]:
        display_no = primary.digital_invoice_no or " ".join(
            item
            for item in [primary.invoice_code or "", primary.invoice_no or ""]
            if item
        )
        return {
            "id": primary.id,
            "displayNo": display_no,
            "invoiceNo": primary.invoice_no,
            "invoiceCode": primary.invoice_code or "",
            "digitalInvoiceNo": primary.digital_invoice_no or "",
            "invoiceDate": primary.invoice_date or "",
            "issueDate": primary.invoice_date or "",
            "sellerName": primary.seller_name or "",
            "sellerTaxNo": primary.seller_tax_no or "",
            "buyerName": primary.buyer_name or primary.counterparty.name,
            "buyerTaxNo": primary.buyer_tax_no
            or primary.counterparty.tax_no
            or "",
            "totalWithTax": _money(
                sum((_invoice_total(line) for line in line_items), start=ZERO)
            ),
            "amount": _money(
                sum((_decimal(line.amount) for line in line_items), start=ZERO)
            ),
            "amountWithoutTax": _money(
                sum((_decimal(line.amount) for line in line_items), start=ZERO)
            ),
            "taxRate": primary.tax_rate or "",
            "taxAmount": _money(
                sum(
                    (_decimal(line.tax_amount) for line in line_items),
                    start=ZERO,
                )
            ),
            "specificBusinessType": primary.specific_business_type or "",
            "taxableItemName": primary.taxable_item_name or "",
            "reversalTargetInvoiceNos": _reversal_target_invoice_nos(
                line.remark for line in line_items
            ),
            "lineItemCount": len(line_items),
            "hasMoreInvoiceLines": len(line_items) > 1,
            "isPositiveInvoice": primary.is_positive_invoice or "",
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
        summaries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for relation in relations:
            for row_id, row_type in context.typed_relation_rows(relation):
                bank = (
                    bank_map.get(row_id)
                    if row_type in {"bank", "bank_transaction"}
                    else None
                )
                if bank is None or bank.id in seen:
                    continue
                seen.add(bank.id)
                summaries.append(
                    self._bank_summary(
                        bank,
                        primary_invoice,
                        line_items,
                        relation,
                    )
                )
        summaries.sort(key=lambda item: item["_sort"])
        for item in summaries:
            item.pop("_sort", None)
        primary = summaries[0] if summaries else {}
        return {
            "primaryBankTransactionId": primary.get("bankTransactionId"),
            "counterpartyName": primary.get("counterpartyName", ""),
            "tradeTime": primary.get("tradeTime", ""),
            "amount": primary.get("amount", ""),
            "receivedTotal": _money(
                self._bank_total(summaries, direction="inflow")
            ),
            "direction": primary.get("direction", ""),
            "directionLabel": primary.get("directionLabel", ""),
            "bankName": primary.get("bankName", ""),
            "accountLast4": primary.get("accountLast4", ""),
            "summary": primary.get("summary", ""),
            "remark": primary.get("remark", ""),
            "relationCount": len(summaries),
            "hasMultiple": len(summaries) > 1,
            "detailMode": (
                "none"
                if not summaries
                else "list"
                if len(summaries) > 1
                else "single"
            ),
            "summaries": summaries,
        }

    def _bank_summary(
        self,
        bank: BankTransaction,
        primary_invoice: Invoice,
        line_items: list[Invoice],
        relation: dict[str, Any],
    ) -> dict[str, Any]:
        invoice_total = abs(
            sum((_invoice_total(line) for line in line_items), start=ZERO)
        )
        direction = _bank_direction(bank)
        amount_check = relation.get("amount_check")
        matched = (
            isinstance(amount_check, dict)
            and amount_check.get("matched") is True
        )
        return {
            "bankTransactionId": bank.id,
            "counterpartyName": bank.counterparty_name_raw,
            "tradeTime": bank.trade_time or bank.txn_date or "",
            "amount": _money(bank.amount),
            "direction": direction,
            "directionLabel": "收入" if direction == "inflow" else "支出",
            "bankName": bank.imported_bank_name or "",
            "accountLast4": bank.imported_bank_last4
            or str(bank.account_no or "")[-4:],
            "summary": bank.summary or "",
            "remark": bank.remark or "",
            "relationCaseId": relation.get("case_id", ""),
            "relationMode": str(relation.get("relation_mode") or ""),
            "relationStatus": relation_status(relation),
            "relationSource": str(relation.get("relation_source") or ""),
            "_sort": (
                0 if direction == "inflow" else 1,
                0 if matched else 1,
                abs(_decimal(bank.amount) - invoice_total),
                -_sortable_time(bank.trade_time or bank.txn_date),
                bank.id,
            ),
        }

    def _invoice_relation_payload(
        self,
        current_group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        groups_by_invoice_id = {
            invoice.id: group
            for group in all_groups
            for invoice in list(group["line_items"])
        }
        summaries: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for relation in relations:
            if not relation_is_linked(relation):
                continue
            case_id = str(
                relation.get("case_id")
                or relation.get("relation_id")
                or ""
            )
            for row_id, row_type in context.typed_relation_rows(relation):
                related_group = groups_by_invoice_id.get(row_id)
                if row_type != "invoice" or related_group is None:
                    continue
                key = (case_id, str(related_group.get("group_key") or ""))
                if key in seen:
                    continue
                seen.add(key)
                summaries.append(
                    self._invoice_relation_summary(related_group, relation)
                )
        current_group_key = str(current_group.get("group_key") or "")
        summaries.sort(
            key=lambda item: (
                0 if item["groupKey"] == current_group_key else 1,
                str(item.get("invoiceDate") or ""),
                str(item.get("invoiceId") or ""),
            )
        )
        return {
            "relationCount": len(summaries),
            "hasMultiple": len(summaries) > 1,
            "detailMode": "none" if not summaries else "list",
            "summaries": summaries,
        }

    def _invoice_relation_summary(
        self,
        group: dict[str, Any],
        relation: dict[str, Any],
    ) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        line_items: list[Invoice] = list(group["line_items"])
        return {
            "groupKey": str(group.get("group_key") or ""),
            "invoiceId": primary.id,
            "displayNo": primary.digital_invoice_no
            or " ".join(
                item
                for item in [
                    primary.invoice_code or "",
                    primary.invoice_no or "",
                ]
                if item
            ),
            "invoiceNo": primary.invoice_no,
            "invoiceDate": primary.invoice_date or "",
            "sellerName": primary.seller_name or "",
            "sellerTaxNo": primary.seller_tax_no or "",
            "buyerName": primary.buyer_name or primary.counterparty.name,
            "buyerTaxNo": primary.buyer_tax_no
            or primary.counterparty.tax_no
            or "",
            "totalWithTax": _money(
                sum((_invoice_total(item) for item in line_items), start=ZERO)
            ),
            "relationCaseId": str(relation.get("case_id") or ""),
            "relationMode": str(relation.get("relation_mode") or ""),
            "relationStatus": relation_status(relation),
            "relationSource": str(relation.get("relation_source") or ""),
        }

    @staticmethod
    def _bank_total(
        summaries: list[dict[str, Any]],
        *,
        direction: str,
    ) -> Decimal:
        return sum(
            (
                _decimal(summary.get("amount"))
                for summary in summaries
                if str(summary.get("direction") or "") == direction
                and summary_is_linked(summary)
            ),
            start=ZERO,
        )

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
            "quantity": (
                _money(invoice.quantity)
                if invoice.quantity is not None
                else ""
            ),
            "unitPrice": (
                _money(invoice.unit_price)
                if invoice.unit_price is not None
                else ""
            ),
            "amount": _money(invoice.amount),
            "taxRate": invoice.tax_rate or "",
            "taxAmount": _money(invoice.tax_amount),
            "totalWithTax": _money(_invoice_total(invoice)),
            "remark": invoice.remark or "",
            "reversalTargetInvoiceNos": _reversal_target_invoice_nos(
                [invoice.remark]
            ),
        }

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

    def _parse_filters(
        self,
        filters: str | list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if filters in (None, ""):
            return []
        if isinstance(filters, str):
            try:
                parsed = json.loads(unquote(filters))
            except json.JSONDecodeError as exc:
                raise OutputInvoiceCollectionError(
                    "invalid_filter_json",
                    "filters must be a URL-encoded JSON array.",
                ) from exc
        else:
            parsed = filters
        if not isinstance(parsed, list):
            raise OutputInvoiceCollectionError(
                "invalid_filter_json",
                "filters must be a JSON array.",
            )
        normalized: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise OutputInvoiceCollectionError(
                    "invalid_filter_json",
                    "each filter must be an object.",
                )
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if field not in FILTER_CONFIG:
                raise OutputInvoiceCollectionError(
                    "invalid_filter_field",
                    f"Unsupported filter field: {field}",
                    details={"field": field},
                )
            if operator not in FILTER_CONFIG[field]["operators"]:
                raise OutputInvoiceCollectionError(
                    "invalid_filter_operator",
                    f"Unsupported operator for {field}: {operator}",
                    details={"field": field, "operator": operator},
                )
            normalized.append(
                {
                    "field": field,
                    "operator": operator,
                    "value": item.get("value"),
                    "values": list(item.get("values") or []),
                }
            )
        return normalized

    def _parse_sort(
        self,
        sort_field: str | None,
        sort_direction: str | None,
    ) -> tuple[str, str]:
        field = str(sort_field or "invoice_date").strip() or "invoice_date"
        direction = str(sort_direction or "desc").strip().lower() or "desc"
        if field not in SORT_FIELDS:
            raise OutputInvoiceCollectionError(
                "invalid_sort_field",
                f"Unsupported sort field: {field}",
                details={"field": field},
            )
        if direction not in {"asc", "desc"}:
            raise OutputInvoiceCollectionError(
                "invalid_sort_direction",
                "sort_direction must be asc or desc.",
            )
        return field, direction

    def _row_matches_filters(
        self,
        row: dict[str, Any],
        filters: list[dict[str, Any]],
    ) -> bool:
        for filter_item in filters:
            field = filter_item["field"]
            operator = filter_item["operator"]
            value = self._field_value(row, field)
            if operator == "contains":
                if str(filter_item.get("value") or "").lower() not in str(
                    value or ""
                ).lower():
                    return False
            elif operator == "equals":
                expected = filter_item.get("value")
                if FILTER_CONFIG[field]["mode"] == "money":
                    if not _within_cent(_decimal(value), _decimal(expected)):
                        return False
                elif str(value or "") != str(expected or ""):
                    return False
            elif operator == "in":
                values = {
                    str(item)
                    for item in list(filter_item.get("values") or [])
                }
                if str(value or "") not in values:
                    return False
            elif operator == "between":
                bounds = filter_item.get("value")
                if not isinstance(bounds, dict):
                    raise OutputInvoiceCollectionError(
                        "invalid_filter_value",
                        "between filter requires min/max object.",
                    )
                minimum = bounds.get("min")
                maximum = bounds.get("max")
                if FILTER_CONFIG[field]["mode"] == "money":
                    current = _decimal(value)
                    if minimum not in (None, "") and current < _decimal(minimum):
                        return False
                    if maximum not in (None, "") and current > _decimal(maximum):
                        return False
                else:
                    current = str(value or "")[:10]
                    if minimum and current < str(minimum):
                        return False
                    if maximum and current > str(maximum):
                        return False
        return True

    @staticmethod
    def _row_matches_date(
        row: dict[str, Any],
        *,
        date_from: str | None,
        date_to: str | None,
        month: str | None,
    ) -> bool:
        invoice_date = str(row["invoice"].get("invoiceDate") or "")
        if (
            month
            and str(month).strip() not in {"", "all"}
            and not invoice_date.startswith(str(month)[:7])
        ):
            return False
        if date_from and invoice_date[:10] < str(date_from):
            return False
        return not date_to or invoice_date[:10] <= str(date_to)

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
        bank = row["bankTransactions"]
        collection = row["collectionStatus"]
        return {
            "invoice_no": invoice.get("displayNo") or invoice.get("invoiceNo"),
            "invoice_date": invoice.get("invoiceDate"),
            "buyer_name": invoice.get("buyerName"),
            "buyer_tax_no": invoice.get("buyerTaxNo"),
            "seller_name": invoice.get("sellerName"),
            "total_with_tax": invoice.get("totalWithTax"),
            "tax_amount": invoice.get("taxAmount"),
            "tax_rate": invoice.get("taxRate"),
            "specific_business_type": invoice.get("specificBusinessType"),
            "taxable_item_name": invoice.get("taxableItemName"),
            "collection_status": collection.get("code"),
            "pending_amount": collection.get("pendingAmount"),
            "bank_counterparty_name": bank.get("counterpartyName"),
            "bank_trade_time": bank.get("tradeTime"),
            "bank_amount": bank.get("amount"),
            "bank_name": bank.get("bankName"),
            "bank_summary": bank.get("summary"),
        }.get(field)

    def _options_for_field(
        self,
        rows: list[dict[str, Any]],
        field: str,
    ) -> list[dict[str, Any]]:
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
            labels[key] = (
                str(row["collectionStatus"]["label"])
                if field == "collection_status"
                else key
            )
        return [
            {
                "value": value,
                "label": labels[value],
                "count": counts[value],
            }
            for value in sorted(counts)
        ]

    @staticmethod
    def summary_for_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invoiceCount": sum(
                int(row["invoice"].get("lineItemCount") or 1)
                for row in rows
            ),
            "totalWithTax": _money(
                sum(
                    (_decimal(row["invoice"]["totalWithTax"]) for row in rows),
                    start=ZERO,
                )
            ),
            "collectedAmount": _money(
                sum(
                    (
                        _decimal(row["collectionStatus"]["collectedAmount"])
                        for row in rows
                    ),
                    start=ZERO,
                )
            ),
            "pendingAmount": _money(
                sum(
                    (
                        _decimal(row["collectionStatus"]["pendingAmount"])
                        for row in rows
                    ),
                    start=ZERO,
                )
            ),
            "pendingCollectionCount": sum(
                row["collectionStatus"]["code"] == "pending_collection"
                for row in rows
            ),
            "partialCollectionCount": sum(
                row["collectionStatus"]["code"] == "partial_collected"
                for row in rows
            ),
        }

    @staticmethod
    def _ensure_export_row_limit(rows: list[dict[str, Any]]) -> None:
        if len(rows) <= OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT:
            return
        raise OutputInvoiceCollectionError(
            "output_invoice_collection_export_row_limit_exceeded",
            f"销项发票收款情况导出超过 {OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT} 行，请缩小筛选范围后重试。",
            details={
                "total": len(rows),
                "limit": OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT,
            },
        )

    @staticmethod
    def _export_file_name() -> str:
        return f"销项发票收款情况-{datetime.now(UTC).date().isoformat()}.xlsx"

    @staticmethod
    def _export_row(index: int, row: dict[str, Any]) -> dict[str, Any]:
        invoice = dict(row.get("invoice") or {})
        collection = dict(row.get("collectionStatus") or {})
        bank = _first_relation_summary(
            dict(row.get("bankTransactions") or {})
        )
        reversal_invoices = [
            item
            for item in _relation_summaries(
                dict(row.get("invoiceRelations") or {})
            )
            if str(item.get("relationMode") or "")
            == OUTPUT_INVOICE_REVERSAL_RELATION_MODE
            and str(item.get("invoiceId") or "") != str(row.get("invoiceId") or "")
        ]
        return {
            "序号": index,
            "发票号码": invoice.get("displayNo")
            or invoice.get("invoiceNo")
            or "",
            "开票日期": invoice.get("invoiceDate")
            or invoice.get("issueDate")
            or "",
            "购方": invoice.get("buyerName") or "",
            "购方识别号": invoice.get("buyerTaxNo") or "",
            "价税合计": invoice.get("totalWithTax") or "",
            "收款状态": collection.get("label")
            or collection.get("code")
            or "",
            "已收金额": collection.get("collectedAmount") or "",
            "待收金额": collection.get("pendingAmount") or "",
            "收款方": bank.get("counterpartyName") or "",
            "收款日期": bank.get("tradeTime") or "",
            "收款金额": bank.get("amount") or "",
            "收款银行": bank.get("bankName") or "",
            "摘要": bank.get("summary") or "",
            "冲红蓝字发票号码": _join_non_empty(
                invoice.get("reversalTargetInvoiceNos") or []
            ),
            "红蓝票关系": _join_non_empty(
                item.get("displayNo") or item.get("invoiceNo")
                for item in reversal_invoices
            ),
        }


def _collection_status_for_facts(
    *,
    invoice_total: Decimal,
    invoice_sign: int,
    collected_total: Decimal,
    has_reversal: bool,
) -> dict[str, Any]:
    expected = abs(invoice_total)
    if has_reversal and invoice_sign > 0:
        return _collection_status(
            "reversed_by_red",
            "已被红冲",
            "蓝字发票已通过 canonical 配对关系关联红字发票。",
            collected_amount=ZERO,
            pending_amount=ZERO,
            severity="info",
        )
    if has_reversal and invoice_sign < 0:
        return _collection_status(
            "reverses_blue",
            "已冲销蓝票",
            "红字发票已通过 canonical 配对关系冲销蓝字发票。",
            collected_amount=ZERO,
            pending_amount=ZERO,
            severity="warning",
        )
    if invoice_sign < 0:
        return _collection_status(
            "unmatched_red",
            "红票待核对",
            "红字发票尚未形成唯一、确定的蓝字发票配对关系。",
            collected_amount=ZERO,
            pending_amount=ZERO,
            severity="danger",
        )
    if collected_total > ZERO and (
        _within_cent(collected_total, expected) or collected_total > expected
    ):
        return _collection_status(
            "collected",
            "已收款",
            "canonical 配对的收入流水已覆盖发票金额。",
            collected_amount=collected_total,
            pending_amount=ZERO,
            severity="success",
        )
    if collected_total > ZERO:
        return _collection_status(
            "partial_collected",
            "部分收款",
            "canonical 配对的收入流水尚未覆盖发票金额。",
            collected_amount=collected_total,
            pending_amount=max(ZERO, expected - collected_total),
            severity="warning",
        )
    return _collection_status(
        "pending_collection",
        "待收款",
        "尚无 canonical 配对的收入流水。",
        collected_amount=ZERO,
        pending_amount=expected,
        severity="pending",
    )


def _collection_status(
    code: str,
    label: str,
    reason: str,
    *,
    collected_amount: Decimal,
    pending_amount: Decimal,
    severity: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "reason": reason,
        "matchedRuleId": f"canonical:{code}",
        "severity": severity,
        "collectedAmount": _money(collected_amount),
        "pendingAmount": _money(pending_amount),
    }


def _parse_positive_int(
    value: int | str | None,
    field: str,
    *,
    maximum: int | None = None,
) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise OutputInvoiceCollectionError(
            "invalid_paging",
            f"{field} must be a positive integer.",
        ) from exc
    if number < 1 or (maximum is not None and number > maximum):
        limit = f" <= {maximum}" if maximum is not None else ""
        raise OutputInvoiceCollectionError(
            "invalid_paging",
            f"{field} must be a positive integer{limit}.",
        )
    return number


def _invoice_total(invoice: Invoice) -> Decimal:
    if invoice.total_with_tax is not None:
        return _decimal(invoice.total_with_tax)
    return _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def _invoice_sign(invoice: Invoice, total: Decimal) -> int:
    source = str(invoice.is_positive_invoice or "").strip().lower()
    if source in {"否", "false", "negative", "负数", "红字"} or total < ZERO:
        return -1
    return 1


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
    value = getattr(
        transaction.txn_direction,
        "value",
        str(transaction.txn_direction),
    )
    return "outflow" if "outflow" in value else "inflow"


def _sortable_time(value: str | None) -> float:
    text = str(value or "").strip()
    if not text:
        return 0
    try:
        return datetime.fromisoformat(text.replace(" ", "T")).timestamp()
    except ValueError:
        return 0


def _relation_summaries(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in list(payload.get("summaries") or [])
        if isinstance(item, dict)
    ]


def _first_relation_summary(payload: dict[str, Any]) -> dict[str, Any]:
    summaries = _relation_summaries(payload)
    return summaries[0] if summaries else {}


def _join_non_empty(values: Any) -> str:
    result: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return "；".join(result)


def _reversal_target_invoice_nos(remarks: Any) -> list[str]:
    invoice_nos: list[str] = []
    for remark in remarks:
        for invoice_no in REVERSED_BLUE_INVOICE_NO_PATTERN.findall(
            str(remark or "")
        ):
            if invoice_no not in invoice_nos:
                invoice_nos.append(invoice_no)
    return invoice_nos

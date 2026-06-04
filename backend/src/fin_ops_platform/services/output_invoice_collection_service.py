from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, is_dataclass
from datetime import UTC, datetime
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
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.output_invoice_collection_models import (
    OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION,
    RED_REFUND_STATUS_CODES,
)
from fin_ops_platform.services.output_invoice_collection_status_service import OutputInvoiceCollectionStatusOverlayService
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
READ_MODEL_STATUS = "live_query"
SOURCE_VERSION = OUTPUT_INVOICE_COLLECTION_SOURCE_VERSION
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()


FILTER_CONFIG: dict[str, dict[str, Any]] = {
    "invoice_no": {"label": "发票号码", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "invoice_date": {"label": "开票日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "buyer_name": {"label": "购方", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "buyer_tax_no": {"label": "购方识别号", "mode": "text", "operators": {"contains", "equals"}, "sortable": True},
    "seller_name": {"label": "销方", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "total_with_tax": {"label": "价税合计", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "tax_amount": {"label": "税额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "tax_rate": {"label": "税率", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "specific_business_type": {"label": "特定业务类型", "mode": "enum_multi", "operators": {"in"}, "sortable": False},
    "taxable_item_name": {"label": "货物或应税劳务名称", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "collection_status": {"label": "收款状态", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "pending_amount": {"label": "待收款金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "bank_counterparty_name": {"label": "付款方", "mode": "enum_multi", "operators": {"in", "contains"}, "sortable": True},
    "bank_trade_time": {"label": "收款日期", "mode": "date", "operators": {"between", "equals"}, "sortable": True},
    "bank_amount": {"label": "收款金额", "mode": "money", "operators": {"between", "equals"}, "sortable": True},
    "bank_name": {"label": "收款银行", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
    "bank_summary": {"label": "摘要", "mode": "text", "operators": {"contains"}, "sortable": True},
    "receipt_status": {"label": "收据情况", "mode": "enum_multi", "operators": {"in"}, "sortable": True},
}

SORT_FIELDS = {field for field, config in FILTER_CONFIG.items() if config["sortable"]}
RECEIPT_BLOCKED_STATUS_CODES = {"collected_red_refunded", "red_invoiced_no_collection"}


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


class OutputInvoiceCollectionStatusRuleService:
    """Sheet6 static status rules plus lifecycle manual override metadata."""

    def rules_payload(self) -> dict[str, Any]:
        return {
            "version": "sheet6-static-v1",
            "readOnly": True,
            "rules": [
                {
                    "id": "collected_red_refunded",
                    "label": "开票已收款，冲红并退款",
                    "description": "正数销项发票已有收入流水，后续出现对应红字发票，并且能找到退款支出流水。",
                    "recognitionMode": "自动识别",
                    "requiredFacts": ["销项正数发票", "收入流水", "对应红字发票", "退款支出流水"],
                    "workbenchRequirement": "关联台至少能证明发票与流水关系，红蓝票由同购方同金额反向发票推断。",
                    "priority": 1,
                },
                {
                    "id": "red_invoiced_no_collection",
                    "label": "开票后冲红",
                    "description": "销项发票存在对应红字/蓝字关系，且未发现收入流水。",
                    "recognitionMode": "自动识别",
                    "requiredFacts": ["销项正数发票", "对应红字发票", "无收入流水"],
                    "workbenchRequirement": "可自动识别或后续由人工关联红蓝票。",
                    "priority": 2,
                },
                {
                    "id": "collected",
                    "label": "已收款",
                    "description": "销项发票存在收入流水，收入流水合计与价税合计一致。",
                    "recognitionMode": "自动识别",
                    "requiredFacts": ["销项发票", "收入流水", "金额一致"],
                    "workbenchRequirement": "关联台完全匹配或一票多流水合计一致。",
                    "priority": 3,
                },
                {
                    "id": "partial_collected",
                    "label": "待收款，已收部分款",
                    "description": "销项发票存在收入流水，但收入流水合计小于价税合计。",
                    "recognitionMode": "自动识别",
                    "requiredFacts": ["销项发票", "收入流水", "收入合计小于发票金额"],
                    "workbenchRequirement": "关联台能证明已收部分流水。",
                    "priority": 4,
                },
                {
                    "id": "pending_collection",
                    "label": "待收款",
                    "description": "销项发票尚未发现收入流水。",
                    "recognitionMode": "手动标记/默认状态",
                    "requiredFacts": ["销项发票", "无收入流水"],
                    "workbenchRequirement": "无强制关联要求。",
                    "priority": 5,
                },
                {
                    "id": "pending_red_invoice",
                    "label": "待冲红",
                    "description": "Sheet6 预留的手动状态：有销项发票、无收入流水，业务确认未来需要冲红。",
                    "recognitionMode": "手动标记",
                    "requiredFacts": ["销项发票", "无收入流水", "人工确认待冲红"],
                    "workbenchRequirement": "可通过收款状态命令人工保存，并进入生命周期 facts 与审计链。",
                    "priority": 6,
                },
                {
                    "id": "pending_default",
                    "label": "待处理",
                    "description": "现有事实不足以证明任一自动状态。",
                    "recognitionMode": "系统兜底",
                    "requiredFacts": ["事实不完整或关系不足"],
                    "workbenchRequirement": "需要回到关联台补充关系。",
                    "priority": 7,
                },
            ],
            "futureWriteBoundary": {
                "statusRuleEditing": "后续可替换为版本化规则表和审计日志，本阶段无保存入口。",
                "manualStatus": "待冲红等人工状态已由正式命令服务落库；规则编辑仍保持只读。",
            },
        }

    def classify(
        self,
        *,
        invoice_total: Decimal,
        own_inflow_total: Decimal,
        related_inflow_total: Decimal,
        related_outflow_total: Decimal,
        has_red_relation: bool,
        fully_matched: bool,
    ) -> dict[str, Any]:
        absolute_total = abs(invoice_total)
        effective_inflow = own_inflow_total if own_inflow_total > ZERO else related_inflow_total
        if has_red_relation and effective_inflow > ZERO and related_outflow_total > ZERO:
            return _collection_status(
                "collected_red_refunded",
                "开票已收款，冲红并退款",
                "优先识别红蓝票关系、收入流水和退款支出流水。",
                "collected_red_refunded",
                collected_amount=effective_inflow,
                pending_amount=ZERO,
                severity="error",
            )
        if has_red_relation and effective_inflow <= ZERO:
            return _collection_status(
                "red_invoiced_no_collection",
                "开票后冲红",
                "识别到对应红字/蓝字发票，且未发现收入流水。",
                "red_invoiced_no_collection",
                collected_amount=ZERO,
                pending_amount=ZERO,
                severity="info",
            )
        if absolute_total > ZERO and _within_cent(own_inflow_total, absolute_total):
            reason = "收入流水合计与发票价税合计一致。"
            if fully_matched:
                reason = "关联台完全匹配，且收入流水合计与发票价税合计一致。"
            return _collection_status(
                "collected",
                "已收款",
                reason,
                "collected",
                collected_amount=own_inflow_total,
                pending_amount=ZERO,
                severity="success",
            )
        if ZERO < own_inflow_total < absolute_total:
            return _collection_status(
                "partial_collected",
                "待收款，已收部分款",
                "存在收入流水，但收入流水合计小于发票价税合计。",
                "partial_collected",
                collected_amount=own_inflow_total,
                pending_amount=absolute_total - own_inflow_total,
                severity="warning",
            )
        if own_inflow_total <= ZERO:
            return _collection_status(
                "pending_collection",
                "待收款",
                "尚未发现可证明的收入流水。",
                "pending_collection",
                collected_amount=ZERO,
                pending_amount=absolute_total,
                severity="warning",
            )
        return _collection_status(
            "pending",
            "待处理",
            "现有关系不能自动闭环，需要补充关联台事实。",
            "pending_default",
            collected_amount=own_inflow_total,
            pending_amount=max(ZERO, absolute_total - own_inflow_total),
            severity="warning",
        )


class OutputInvoiceReceiptPreviewService:
    """Sheet7 receipt preview boundary. Phase 1 never writes receipt facts."""

    def preview(
        self,
        *,
        row: dict[str, Any],
        selected_bank_transaction_id: str | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        status_code = str(row["collectionStatus"].get("code") or "")
        if status_code in RECEIPT_BLOCKED_STATUS_CODES:
            return {
                "canPreview": False,
                "reasonCode": "red_refund_blocked",
                "reason": "红冲/退款类记录第一阶段不自动生成待出收据预览。",
                "pendingAmount": row["collectionStatus"].get("pendingAmount", "0.00"),
                "candidates": self._income_candidates(row),
            }

        candidates = self._income_candidates(row)
        if not candidates:
            return {
                "canPreview": False,
                "reasonCode": "no_income_transaction",
                "reason": "未找到关联收入流水，不能生成收据预览。",
                "pendingAmount": row["collectionStatus"].get("pendingAmount", row["invoice"].get("totalWithTax", "0.00")),
                "candidates": [],
            }

        selected = None
        if selected_bank_transaction_id:
            selected = next(
                (candidate for candidate in candidates if candidate["bankTransactionId"] == selected_bank_transaction_id),
                None,
            )
            if selected is None:
                raise OutputInvoiceCollectionError(
                    "receipt_preview_bank_not_found",
                    f"Receipt preview bank transaction not found: {selected_bank_transaction_id}",
                    status_code=HTTPStatus.NOT_FOUND,
                )
        elif len(candidates) == 1:
            selected = candidates[0]

        if selected is None:
            return {
                "canPreview": False,
                "reasonCode": "bank_selection_required",
                "reason": "一张销项发票存在多笔收入流水，请先选择一笔流水作为本次收据金额。",
                "pendingAmount": row["collectionStatus"].get("pendingAmount", "0.00"),
                "candidates": candidates,
            }

        receipt_date = _date_only(selected.get("tradeTime")) or _date_only(generated_at) or _today()
        amount = _money(selected.get("amount"))
        invoice = row["invoice"]
        return {
            "canPreview": True,
            "reasonCode": "",
            "reason": "",
            "selectedBankTransactionId": selected["bankTransactionId"],
            "candidates": candidates,
            "receipt": {
                "templateVersion": "sheet7-static-v1",
                "companyName": "云南溯源科技有限公司",
                "title": "收 据",
                "date": receipt_date,
                "dateParts": _date_parts(receipt_date),
                "payerName": invoice.get("buyerName", ""),
                "summary": invoice.get("taxableItemName", "") or "服务费",
                "amount": amount,
                "amountUppercase": _uppercase_rmb(amount),
                "remark": f"销项发票 {invoice.get('displayNo') or invoice.get('invoiceNo') or row.get('invoiceId')}",
                "bankName": selected.get("bankName", ""),
                "bankTransactionId": selected["bankTransactionId"],
                "invoiceId": row["invoiceId"],
                "canCreateFormalReceipt": False,
                "nextAction": "future_contract_only",
            },
            "warnings": ["第一阶段仅生成预览，不创建正式收据编号，也不保存收据历史。"],
        }

    @staticmethod
    def _income_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
        candidates = [
            summary
            for summary in list(row.get("bankTransactions", {}).get("summaries") or [])
            if str(summary.get("direction") or "") == "inflow"
        ]
        return sorted(candidates, key=lambda item: (_sortable_time(item.get("tradeTime")), item.get("bankTransactionId", "")), reverse=True)


class OutputInvoiceCollectionQueryService:
    """Read-only query facade for the 销项发票收款情况 page."""

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        status_rule_service: OutputInvoiceCollectionStatusRuleService | None = None,
        receipt_preview_service: OutputInvoiceReceiptPreviewService | None = None,
        lifecycle_repository: Any | None = None,
        status_overlay_service: OutputInvoiceCollectionStatusOverlayService | None = None,
        lifecycle_policy: Any | None = None,
        require_fresh_relations: bool = True,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._status_rule_service = status_rule_service or OutputInvoiceCollectionStatusRuleService()
        self._receipt_preview_service = receipt_preview_service or OutputInvoiceReceiptPreviewService()
        self._lifecycle_repository = lifecycle_repository
        self._status_overlay_service = status_overlay_service or OutputInvoiceCollectionStatusOverlayService()
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy(
            output_collection_status_rule_service=self._status_rule_service,
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
        tenant_id: str = "default",
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
            tenant_id=tenant_id,
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
            "readModelStatus": READ_MODEL_STATUS,
            "generatedAt": _now_iso(),
            "sourceVersion": SOURCE_VERSION,
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
            tenant_id=tenant_id,
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
            "readModelStatus": READ_MODEL_STATUS,
            "generatedAt": _now_iso(),
            "sourceVersion": SOURCE_VERSION,
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
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        parsed_filters = self._parse_filters(filters)
        typed_rows = self.apply_lifecycle_overlays_to_rows(
            [row for row in list(rows or []) if isinstance(row, dict)],
            tenant_id=tenant_id,
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
            "readModelStatus": READ_MODEL_STATUS,
            "generatedAt": _now_iso(),
            "sourceVersion": SOURCE_VERSION,
        }

    def _query_context(self, *, month_hint: str | None = None) -> DistributedInvoiceRelationContext:
        return DistributedInvoiceRelationContext(
            import_service=self._import_service,
            relation_facade=self._relation_facade,
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
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        rows = self._build_rows(month=month, context=context, tenant_id=tenant_id)
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

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        context = self._query_context()
        group = self._invoice_group_for_invoice_id(invoice_id, context=context)
        if group is None:
            raise OutputInvoiceCollectionError(
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
            "sellerName": primary.seller_name or "",
            "sellerTaxNo": primary.seller_tax_no or "",
            "buyerName": primary.buyer_name or primary.counterparty.name,
            "buyerTaxNo": primary.buyer_tax_no or primary.counterparty.tax_no or "",
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

    def row_relation_details(self, row_id: str, *, kind: str) -> dict[str, Any]:
        normalized_kind = str(kind or "").strip()
        if normalized_kind not in {"bank", "red_invoice", "receipt"}:
            raise OutputInvoiceCollectionError("invalid_relation_kind", "kind must be bank, red_invoice or receipt.")
        context = self._query_context()
        row = self._row_by_id(row_id, context=context)
        if row is None:
            raise OutputInvoiceCollectionError(
                "row_not_found",
                f"Output invoice collection row not found: {row_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        if normalized_kind == "bank":
            relation_payload = row["bankTransactions"]
            summaries = relation_payload.get("summaries", [])
        elif normalized_kind == "red_invoice":
            relation_payload = row["redInvoiceRelation"]
            summaries = relation_payload.get("summaries", [])
        else:
            relation_payload = row["receipt"]
            summaries = []
        return {
            "rowId": row["id"],
            "invoiceId": row["invoiceId"],
            "kind": normalized_kind,
            "detailAvailable": normalized_kind != "receipt" and relation_payload.get("detailMode") != "none",
            "relationCount": relation_payload.get("relationCount", 0),
            "hasMultiple": relation_payload.get("hasMultiple", False),
            "summaries": summaries,
            "sourceAvailable": bool(relation_payload.get("sourceAvailable", normalized_kind != "receipt")),
            "relations": context.relation_summaries_for_row(row["invoiceId"]),
        }

    def status_rules(self) -> dict[str, Any]:
        return self._status_overlay_service.status_rules_payload(self._status_rule_service.rules_payload())

    def receipt_preview(self, request: dict[str, Any] | None, *, tenant_id: str = "default") -> dict[str, Any]:
        payload = dict(request or {})
        row_id = str(payload.get("rowId") or payload.get("row_id") or "").strip()
        invoice_id = str(payload.get("invoiceId") or payload.get("invoice_id") or "").strip()
        context = self._query_context()
        row = self._row_by_id(row_id, context=context, tenant_id=tenant_id) if row_id else self._row_by_invoice_id(invoice_id, context=context, tenant_id=tenant_id)
        if row is None:
            raise OutputInvoiceCollectionError(
                "row_not_found",
                "Output invoice collection row not found for receipt preview.",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return self._receipt_preview_service.preview(
            row=row,
            selected_bank_transaction_id=str(
                payload.get("selectedBankTransactionId") or payload.get("selected_bank_transaction_id") or ""
            ).strip()
            or None,
        )

    def receipt_history(self, *, invoice_id: str, tenant_id: str = "default") -> dict[str, Any]:
        context = self._query_context()
        group = self._invoice_group_for_invoice_id(invoice_id, context=context)
        if group is None:
            raise OutputInvoiceCollectionError(
                "invoice_not_found",
                f"Invoice not found for receipt history: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        repository = self._lifecycle_repository
        list_receipts = getattr(repository, "list_receipts", None)
        if callable(list_receipts):
            identity_key = str(group.get("identity_key") or "")
            receipts = list_receipts(invoice_id=invoice_id, invoice_identity_key=identity_key, tenant_id=tenant_id)
            return {
                "invoiceId": invoice_id,
                "sourceAvailable": True,
                "sourceName": "formal_receipt_lifecycle",
                "receipts": receipts,
            }
        return {
            "invoiceId": invoice_id,
            "sourceAvailable": False,
            "sourceName": "formal_receipt_lifecycle",
            "receipts": [],
            "message": "第一阶段没有正式收据历史事实源，不能伪造历史收据。",
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

    def _build_rows(self, *, month: str | None, context: DistributedInvoiceRelationContext, tenant_id: str = "default") -> list[dict[str, Any]]:
        groups = self._invoice_groups(month=month, context=context)
        context.preload_relation_rows([line.id for group in groups for line in group["line_items"]])
        rows = [self._row_payload(group, groups, context=context) for group in groups]
        return self.apply_lifecycle_overlays_to_rows(rows, tenant_id=tenant_id)

    def row_by_id(self, row_id: str, *, tenant_id: str = "default") -> dict[str, Any] | None:
        context = self._query_context()
        normalized_id = str(row_id or "").strip()
        row = self._row_by_id(normalized_id, context=context, tenant_id=tenant_id)
        if row is not None:
            return row
        return self._row_by_invoice_id(normalized_id, context=context, tenant_id=tenant_id)

    def _invoice_groups(
        self,
        *,
        month: str | None = None,
        context: DistributedInvoiceRelationContext,
    ) -> list[dict[str, Any]]:
        source_month = str(month).strip() if month not in (None, "") else "all"
        invoices = [
            invoice
            for invoice in context.list_invoices(month=source_month, invoice_type=InvoiceType.OUTPUT)
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

    def _row_by_id(self, row_id: str, *, context: DistributedInvoiceRelationContext, tenant_id: str = "default") -> dict[str, Any] | None:
        normalized_id = str(row_id)
        for row in self._build_rows(month=None, context=context, tenant_id=tenant_id):
            if row["id"] == normalized_id:
                return row
        return None

    def _row_by_invoice_id(
        self,
        invoice_id: str,
        *,
        context: DistributedInvoiceRelationContext,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_id = str(invoice_id)
        for row in self._build_rows(month=None, context=context, tenant_id=tenant_id):
            if row["invoiceId"] == normalized_id:
                return row
        return None

    def _row_payload(
        self,
        group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        line_items: list[Invoice] = group["line_items"]
        invoice_ids = [line.id for line in line_items]
        relations = context.distributed_relations_for_row_ids(invoice_ids)
        bank_payload = self._bank_relation_payload(primary, line_items, relations, context=context)
        red_payload = self._red_invoice_relation_payload(group, all_groups, context=context)
        related_groups = [
            related_group
            for related_group in all_groups
            if related_group["primary"].id in {summary["relatedInvoiceId"] for summary in red_payload["summaries"]}
        ]
        own_inflow_total = self._bank_total(bank_payload["summaries"], direction="inflow")
        related_bank_summaries = []
        for related_group in related_groups:
            related_ids = [line.id for line in related_group["line_items"]]
            related_relations = context.distributed_relations_for_row_ids(related_ids)
            related_bank_summaries.extend(
                self._bank_relation_payload(
                    related_group["primary"],
                    related_group["line_items"],
                    related_relations,
                    context=context,
                )["summaries"]
            )
        related_inflow_total = self._bank_total(related_bank_summaries + bank_payload["summaries"], direction="inflow")
        related_outflow_total = self._bank_total(related_bank_summaries + bank_payload["summaries"], direction="outflow")
        collection_status = self._lifecycle_policy.evaluate_output_invoice_collection(
            invoice_total=sum((_invoice_total(line) for line in line_items), start=ZERO),
            own_inflow_total=own_inflow_total,
            related_inflow_total=related_inflow_total,
            related_outflow_total=related_outflow_total,
            has_red_relation=red_payload["relationCount"] > 0,
            fully_matched=self._has_fully_matched_invoice_bank_relation(line_items, relations, context=context),
        )
        row_id = "output_invoice_collection_row_" + sha1(str(group["identity_key"]).encode("utf-8")).hexdigest()[:16]
        receipt_payload = self._receipt_payload(collection_status, bank_payload)
        return {
            "id": row_id,
            "invoiceId": primary.id,
            "invoiceIdentityKey": group["identity_key"],
            "invoice": self._invoice_summary(primary, line_items),
            "collectionStatus": collection_status,
            "bankTransactions": bank_payload,
            "redInvoiceRelation": red_payload,
            "receipt": receipt_payload,
        }

    def _invoice_summary(self, primary: Invoice, line_items: list[Invoice]) -> dict[str, Any]:
        total_with_tax = sum((_invoice_total(line) for line in line_items), start=ZERO)
        amount = sum((_decimal(line.amount) for line in line_items), start=ZERO)
        tax_amount = sum((_decimal(line.tax_amount) for line in line_items), start=ZERO)
        display_no = primary.digital_invoice_no or " ".join(
            item for item in [primary.invoice_code or "", primary.invoice_no or ""] if item
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
            "buyerTaxNo": primary.buyer_tax_no or primary.counterparty.tax_no or "",
            "totalWithTax": _money(total_with_tax),
            "amount": _money(amount),
            "amountWithoutTax": _money(amount),
            "taxRate": primary.tax_rate or "",
            "taxAmount": _money(tax_amount),
            "specificBusinessType": primary.specific_business_type or "",
            "taxableItemName": primary.taxable_item_name or "",
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
        received_total = self._bank_total(public_summaries, direction="inflow")
        return {
            "primaryBankTransactionId": primary.get("bankTransactionId"),
            "counterpartyName": primary.get("counterpartyName", ""),
            "tradeTime": primary.get("tradeTime", ""),
            "amount": primary.get("amount", ""),
            "receivedTotal": _money(received_total),
            "direction": primary.get("direction", ""),
            "directionLabel": primary.get("directionLabel", ""),
            "bankName": primary.get("bankName", ""),
            "accountLast4": primary.get("accountLast4", ""),
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
        invoice_total = abs(sum((_invoice_total(line) for line in line_items), start=ZERO))
        diff = abs(_decimal(bank.amount) - invoice_total)
        completeness = 0 if self._relation_amount_check_is_matched(relation) else 1
        direction = _bank_direction(bank)
        direction_rank = 0 if direction == "inflow" else 1
        timestamp = _sortable_time(bank.trade_time or bank.txn_date)
        return {
            "bankTransactionId": bank.id,
            "counterpartyName": bank.counterparty_name_raw,
            "tradeTime": bank.trade_time or bank.txn_date or "",
            "amount": _money(bank.amount),
            "direction": direction,
            "directionLabel": "收入" if direction == "inflow" else "支出",
            "bankName": bank.imported_bank_name or "",
            "accountLast4": bank.imported_bank_last4 or str(bank.account_no or "")[-4:],
            "summary": bank.summary or "",
            "remark": bank.remark or "",
            "relationCaseId": relation.get("case_id", ""),
            "_sort": (direction_rank, completeness, diff, -timestamp, bank.id),
        }

    def _red_invoice_relation_payload(
        self,
        group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any]:
        primary: Invoice = group["primary"]
        line_items: list[Invoice] = group["line_items"]
        current_total = sum((_invoice_total(line) for line in line_items), start=ZERO)
        current_sign = _invoice_sign(primary, current_total)
        summaries = []
        seen: set[str] = set()
        for candidate in all_groups:
            candidate_primary: Invoice = candidate["primary"]
            if candidate["identity_key"] == group["identity_key"]:
                continue
            candidate_total = sum((_invoice_total(line) for line in candidate["line_items"]), start=ZERO)
            if _invoice_sign(candidate_primary, candidate_total) == current_sign:
                continue
            if not self._is_selected_red_pair(group, candidate, all_groups, context=context):
                continue
            if candidate_primary.id in seen:
                continue
            seen.add(candidate_primary.id)
            summaries.append(
                {
                    "relatedInvoiceId": candidate_primary.id,
                    "invoiceNo": candidate_primary.digital_invoice_no or candidate_primary.invoice_no,
                    "invoiceDate": candidate_primary.invoice_date or "",
                    "buyerName": candidate_primary.buyer_name or candidate_primary.counterparty.name,
                    "totalWithTax": _money(candidate_total),
                    "relationType": "red_invoice" if _invoice_sign(candidate_primary, candidate_total) < 0 else "blue_invoice",
                    "reason": "同购方、价税合计绝对值一致、正负方向相反。",
                    "evidence": "同购方、价税合计绝对值一致、正负方向相反。",
                    "confidence": "auto_high",
                    "source": "auto",
                }
            )
        summaries.sort(key=lambda item: (item["invoiceDate"], item["relatedInvoiceId"]), reverse=True)
        primary_summary = summaries[0] if summaries else {}
        return {
            "primaryRelatedInvoiceId": primary_summary.get("relatedInvoiceId"),
            "relationCount": len(summaries),
            "hasMultiple": len(summaries) > 1,
            "detailMode": "none" if not summaries else "list" if len(summaries) > 1 else "single",
            "summaries": summaries,
        }

    def _is_selected_red_pair(
        self,
        current_group: dict[str, Any],
        candidate_group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> bool:
        current_primary: Invoice = current_group["primary"]
        candidate_primary: Invoice = candidate_group["primary"]
        current_total = sum((_invoice_total(line) for line in current_group["line_items"]), start=ZERO)
        candidate_total = sum((_invoice_total(line) for line in candidate_group["line_items"]), start=ZERO)
        if not _same_buyer(current_primary, candidate_primary):
            return False
        if not _within_cent(abs(current_total), abs(candidate_total)):
            return False
        if _invoice_sign(current_primary, current_total) > 0:
            positive_group = current_group
            negative_group = candidate_group
        else:
            positive_group = candidate_group
            negative_group = current_group
        selected_positive = self._best_positive_group_for_negative(negative_group, all_groups, context=context)
        return bool(selected_positive and selected_positive["identity_key"] == positive_group["identity_key"])

    def _best_positive_group_for_negative(
        self,
        negative_group: dict[str, Any],
        all_groups: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> dict[str, Any] | None:
        negative_primary: Invoice = negative_group["primary"]
        negative_total = sum((_invoice_total(line) for line in negative_group["line_items"]), start=ZERO)
        candidates = []
        for group in all_groups:
            primary: Invoice = group["primary"]
            total = sum((_invoice_total(line) for line in group["line_items"]), start=ZERO)
            if _invoice_sign(primary, total) <= 0:
                continue
            if not _same_buyer(primary, negative_primary):
                continue
            if not _within_cent(abs(total), abs(negative_total)):
                continue
            rank = self._red_pair_rank(group, negative_group, context=context)
            if rank[0] >= 3:
                continue
            candidates.append((rank, group))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0])
        return candidates[0][1]

    def _red_pair_rank(
        self,
        positive_group: dict[str, Any],
        negative_group: dict[str, Any],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> tuple[int, float, str]:
        positive_total = abs(sum((_invoice_total(line) for line in positive_group["line_items"]), start=ZERO))
        positive_banks = self._group_bank_summaries(positive_group, context=context)
        negative_banks = self._group_bank_summaries(negative_group, context=context)
        positive_inflow = self._bank_total(positive_banks, direction="inflow")
        negative_outflow = self._bank_total(negative_banks, direction="outflow")
        positive_full_inflow = _within_cent(positive_inflow, positive_total)
        if positive_full_inflow and negative_outflow > ZERO:
            priority = 0
        elif positive_inflow <= ZERO and negative_outflow <= ZERO:
            priority = 1
        elif positive_full_inflow:
            priority = 2
        else:
            priority = 3
        positive_date = _sortable_time(positive_group["primary"].invoice_date)
        negative_date = _sortable_time(negative_group["primary"].invoice_date)
        return (priority, abs(negative_date - positive_date), str(positive_group["identity_key"]))

    def _group_bank_summaries(self, group: dict[str, Any], *, context: DistributedInvoiceRelationContext) -> list[dict[str, Any]]:
        line_items = group["line_items"]
        invoice_ids = [line.id for line in line_items]
        relations = context.distributed_relations_for_row_ids(invoice_ids)
        return self._bank_relation_payload(group["primary"], line_items, relations, context=context)["summaries"]

    @staticmethod
    def _receipt_payload(collection_status: dict[str, Any], bank_payload: dict[str, Any]) -> dict[str, Any]:
        status_code = str(collection_status.get("code") or "")
        if status_code in RECEIPT_BLOCKED_STATUS_CODES:
            return {
                "status": "blocked",
                "label": "暂不出收据",
                "reason": "红冲/退款类记录暂不自动出收据。",
                "historyAvailable": False,
                "sourceAvailable": False,
                "previewAvailable": False,
                "relationCount": 0,
                "hasMultiple": False,
                "detailMode": "none",
            }
        inflow_count = sum(1 for summary in bank_payload.get("summaries", []) if summary.get("direction") == "inflow")
        if inflow_count <= 0:
            return {
                "status": "not_available",
                "label": "无可出收据流水",
                "reason": "未找到收入流水。",
                "historyAvailable": False,
                "sourceAvailable": False,
                "previewAvailable": False,
                "relationCount": 0,
                "hasMultiple": False,
                "detailMode": "none",
            }
        return {
            "status": "pending",
            "label": "待出收据",
            "reason": "可基于收入流水生成 Sheet7 预览并创建正式收据。",
            "historyAvailable": False,
            "sourceAvailable": False,
            "previewAvailable": True,
            "relationCount": 0,
            "hasMultiple": False,
            "detailMode": "none",
        }

    def apply_lifecycle_overlays_to_rows(self, rows: list[dict[str, Any]], *, tenant_id: str = "default") -> list[dict[str, Any]]:
        repository = self._lifecycle_repository
        overlay_loader = getattr(repository, "overlays_for_identity_keys", None)
        if not callable(overlay_loader) or not rows:
            return rows
        identity_keys = [
            str(row.get("invoiceIdentityKey") or "")
            for row in rows
            if str(row.get("invoiceIdentityKey") or "").strip()
        ]
        try:
            overlays = overlay_loader(identity_keys, tenant_id=tenant_id)
        except TypeError:
            overlays = overlay_loader(identity_keys)
        result: list[dict[str, Any]] = []
        for row in rows:
            identity_key = str(row.get("invoiceIdentityKey") or "")
            overlay = overlays.get(identity_key) if isinstance(overlays, dict) else None
            if not isinstance(overlay, dict):
                result.append(row)
                continue
            updated = deepcopy(row)
            updated["collectionStatus"] = self._status_overlay_service.apply_manual_override(
                dict(updated.get("collectionStatus") or {}),
                override=overlay.get("override") if isinstance(overlay.get("override"), dict) else None,
                reminder=overlay.get("reminder") if isinstance(overlay.get("reminder"), dict) else None,
            )
            updated["redInvoiceRelation"] = self._overlay_red_relations(
                dict(updated.get("redInvoiceRelation") or {}),
                list(overlay.get("redRelations") or []),
            )
            updated["receipt"] = self._overlay_receipt_payload(
                dict(updated.get("receipt") or {}),
                list(overlay.get("receipts") or []),
                updated.get("collectionStatus") if isinstance(updated.get("collectionStatus"), dict) else {},
            )
            result.append(updated)
        return result

    def summary_for_rows(self, rows: list[dict[str, Any]]) -> dict[str, Any]:
        return self._summary(rows)

    @staticmethod
    def _overlay_red_relations(payload: dict[str, Any], manual_relations: list[dict[str, Any]]) -> dict[str, Any]:
        if not manual_relations:
            return payload
        summaries = [dict(item) for item in list(payload.get("summaries") or []) if isinstance(item, dict)]
        seen = {
            (str(item.get("relatedInvoiceIdentityKey") or ""), str(item.get("relatedInvoiceId") or ""))
            for item in summaries
        }
        for relation in manual_relations:
            key = (str(relation.get("relatedInvoiceIdentityKey") or ""), str(relation.get("relatedInvoiceId") or ""))
            if key in seen:
                continue
            summaries.append(
                {
                    "relationId": relation.get("id"),
                    "relatedInvoiceIdentityKey": relation.get("relatedInvoiceIdentityKey"),
                    "relatedInvoiceId": relation.get("relatedInvoiceId"),
                    "invoiceNo": relation.get("relatedInvoiceNo") or relation.get("relatedInvoiceId"),
                    "invoiceDate": relation.get("relatedInvoiceDate") or "",
                    "buyerName": relation.get("buyerName") or "",
                    "totalWithTax": relation.get("relatedTotalWithTax") or "",
                    "relationType": relation.get("relationType") or "red_invoice",
                    "reason": relation.get("evidence") or "人工确认红蓝票关系。",
                    "evidence": relation.get("evidence") or "",
                    "confidence": relation.get("confidence") or "manual_confirmed",
                    "source": "manual",
                }
            )
            seen.add(key)
        payload["summaries"] = summaries
        payload["relationCount"] = len(summaries)
        payload["hasMultiple"] = len(summaries) > 1
        payload["detailMode"] = "none" if not summaries else "list" if len(summaries) > 1 else "single"
        if summaries and not payload.get("primaryRelatedInvoiceId"):
            payload["primaryRelatedInvoiceId"] = summaries[0].get("relatedInvoiceId")
        return payload

    @staticmethod
    def _overlay_receipt_payload(
        payload: dict[str, Any],
        receipts: list[dict[str, Any]],
        collection_status: dict[str, Any],
    ) -> dict[str, Any]:
        if not receipts:
            return payload
        active_receipts = [dict(item) for item in receipts if str(item.get("status") or "") == "issued"]
        latest = active_receipts[0] if active_receipts else dict(receipts[0])
        status = str(latest.get("status") or "issued")
        if status == "issued":
            payload.update(
                {
                    "status": "issued",
                    "label": "已出收据",
                    "reason": "已存在正式收据。",
                    "historyAvailable": True,
                    "sourceAvailable": True,
                    "previewAvailable": False,
                    "relationCount": len(receipts),
                    "hasMultiple": len(receipts) > 1,
                    "detailMode": "list" if len(receipts) > 1 else "single",
                    "latestReceipt": latest,
                    "summaries": receipts,
                }
            )
        elif str(collection_status.get("code") or "") in RED_REFUND_STATUS_CODES:
            payload["status"] = "blocked"
        else:
            payload.update({"historyAvailable": True, "sourceAvailable": True, "latestReceipt": latest, "summaries": receipts})
        return payload

    def _has_fully_matched_invoice_bank_relation(
        self,
        line_items: list[Invoice],
        relations: list[dict[str, Any]],
        *,
        context: DistributedInvoiceRelationContext,
    ) -> bool:
        invoice_total = abs(sum((_invoice_total(line) for line in line_items), start=ZERO))
        bank_map = context.bank_transactions_by_id()
        invoice_ids = {line.id for line in line_items}
        for relation in relations:
            if not self._relation_amount_check_is_matched(relation):
                continue
            typed_rows = self._typed_relation_rows(relation)
            if not any(row_type == "invoice" and row_id in invoice_ids for row_id, row_type in typed_rows):
                continue
            bank_ids = [row_id for row_id, row_type in typed_rows if row_type == "bank"]
            if any(_within_cent(_decimal(bank_map[bank_id].amount), invoice_total) for bank_id in bank_ids if bank_id in bank_map):
                return True
        return False

    def _parse_filters(self, filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if filters in (None, ""):
            return []
        if isinstance(filters, str):
            try:
                parsed = json.loads(unquote(filters))
            except json.JSONDecodeError as exc:
                raise OutputInvoiceCollectionError("invalid_filter_json", "filters must be a URL-encoded JSON array.") from exc
        else:
            parsed = filters
        if not isinstance(parsed, list):
            raise OutputInvoiceCollectionError("invalid_filter_json", "filters must be a JSON array.")
        normalized = []
        for item in parsed:
            if not isinstance(item, dict):
                raise OutputInvoiceCollectionError("invalid_filter_json", "each filter must be an object.")
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if field not in FILTER_CONFIG:
                raise OutputInvoiceCollectionError("invalid_filter_field", f"Unsupported filter field: {field}", details={"field": field})
            if operator not in FILTER_CONFIG[field]["operators"]:
                raise OutputInvoiceCollectionError(
                    "invalid_filter_operator",
                    f"Unsupported operator for {field}: {operator}",
                    details={"field": field, "operator": operator},
                )
            normalized.append(
                {"field": field, "operator": operator, "value": item.get("value"), "values": list(item.get("values") or [])}
            )
        return normalized

    def _parse_sort(self, sort_field: str | None, sort_direction: str | None) -> tuple[str, str]:
        field = str(sort_field or "invoice_date").strip() or "invoice_date"
        direction = str(sort_direction or "desc").strip().lower() or "desc"
        if field not in SORT_FIELDS:
            raise OutputInvoiceCollectionError("invalid_sort_field", f"Unsupported sort field: {field}", details={"field": field})
        if direction not in {"asc", "desc"}:
            raise OutputInvoiceCollectionError("invalid_sort_direction", "sort_direction must be asc or desc.")
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
                    raise OutputInvoiceCollectionError("invalid_filter_value", "between filter requires min/max object.")
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
        bank = row["bankTransactions"]
        collection = row["collectionStatus"]
        receipt = row["receipt"]
        values = {
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
            "receipt_status": receipt.get("status"),
        }
        return values.get(field)

    def _options_for_field(self, rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
        if FILTER_CONFIG[field]["mode"] in {"date", "money", "text"} and field not in {"collection_status", "receipt_status"}:
            return []
        counts: dict[str, int] = {}
        labels: dict[str, str] = {}
        for row in rows:
            value = self._field_value(row, field)
            if value in (None, ""):
                continue
            key = str(value)
            counts[key] = counts.get(key, 0) + 1
            if field == "collection_status":
                labels[key] = row["collectionStatus"]["label"]
            elif field == "receipt_status":
                labels[key] = row["receipt"]["label"]
            else:
                labels[key] = key
        return [{"value": value, "label": labels[value], "count": counts[value]} for value in sorted(counts)]

    @staticmethod
    def _summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "invoiceCount": len(rows),
            "totalWithTax": _money(sum((_decimal(row["invoice"]["totalWithTax"]) for row in rows), start=ZERO)),
            "collectedAmount": _money(sum((_decimal(row["collectionStatus"]["collectedAmount"]) for row in rows), start=ZERO)),
            "pendingAmount": _money(sum((_decimal(row["collectionStatus"]["pendingAmount"]) for row in rows), start=ZERO)),
            "pendingCollectionCount": sum(1 for row in rows if row["collectionStatus"]["code"] == "pending_collection"),
            "partialCollectionCount": sum(1 for row in rows if row["collectionStatus"]["code"] == "partial_collected"),
            "receiptPendingCount": sum(1 for row in rows if row["receipt"]["status"] == "pending"),
        }

    def _bank_transactions_by_id(self) -> dict[str, BankTransaction]:
        return {transaction.id: transaction for transaction in self._import_service.list_transactions(month="all")}

    @staticmethod
    def _bank_total(summaries: list[dict[str, Any]], *, direction: str) -> Decimal:
        return sum(
            (_decimal(summary.get("amount")) for summary in summaries if str(summary.get("direction") or "") == direction),
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

    @staticmethod
    def _relation_amount_check_is_matched(relation: dict[str, Any]) -> bool:
        amount_check = relation.get("amount_check")
        return isinstance(amount_check, dict) and amount_check.get("matched") is True

def _parse_positive_int(value: int | str | None, field: str, *, maximum: int | None = None) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise OutputInvoiceCollectionError("invalid_paging", f"{field} must be a positive integer.") from exc
    if number < 1:
        raise OutputInvoiceCollectionError("invalid_paging", f"{field} must be a positive integer.")
    if maximum is not None and number > maximum:
        raise OutputInvoiceCollectionError("invalid_paging", f"{field} must be <= {maximum}.")
    return number


def _collection_status(
    code: str,
    label: str,
    reason: str,
    matched_rule_id: str,
    *,
    collected_amount: Decimal,
    pending_amount: Decimal,
    severity: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "label": label,
        "reason": reason,
        "matchedRuleId": matched_rule_id,
        "severity": severity,
        "collectedAmount": _money(collected_amount),
        "pendingAmount": _money(pending_amount),
    }


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
    return "invoice"


def _invoice_sign(invoice: Invoice, total: Decimal) -> int:
    text = str(invoice.is_positive_invoice or "").strip().lower()
    if text in {"否", "false", "negative", "负数", "红字"}:
        return -1
    if total < ZERO:
        return -1
    return 1


def _same_buyer(left: Invoice, right: Invoice) -> bool:
    left_tax = str(left.buyer_tax_no or left.counterparty.tax_no or "").strip()
    right_tax = str(right.buyer_tax_no or right.counterparty.tax_no or "").strip()
    if left_tax and right_tax:
        return left_tax == right_tax
    return str(left.buyer_name or left.counterparty.name).strip() == str(right.buyer_name or right.counterparty.name).strip()


def _date_only(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text.split("T")[0].split(" ")[0]


def _date_parts(value: str) -> dict[str, str]:
    parts = _date_only(value).split("-")
    if len(parts) != 3:
        return {"year": "", "month": "", "day": ""}
    return {"year": parts[0], "month": parts[1], "day": parts[2]}


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _uppercase_rmb(value: Any) -> str:
    amount = abs(_decimal(value)).quantize(CENT)
    integer_text, fraction_text = f"{amount:.2f}".split(".")
    units = ["", "拾", "佰", "仟"]
    section_units = ["", "万", "亿", "兆"]
    digits = "零壹贰叁肆伍陆柒捌玖"

    def section_to_upper(section: int) -> str:
        result = ""
        zero_pending = False
        for index in range(4):
            digit = section % 10
            if digit == 0:
                if result:
                    zero_pending = True
            else:
                prefix = "零" if zero_pending else ""
                result = f"{digits[digit]}{units[index]}{prefix}{result}"
                zero_pending = False
            section //= 10
        return result

    integer = int(integer_text)
    if integer == 0:
        integer_upper = "零"
    else:
        sections = []
        section_index = 0
        need_zero = False
        while integer > 0:
            section = integer % 10000
            if section == 0:
                if sections:
                    need_zero = True
            else:
                section_text = section_to_upper(section) + section_units[section_index]
                if need_zero:
                    section_text = "零" + section_text
                    need_zero = False
                sections.insert(0, section_text)
            integer //= 10000
            section_index += 1
        integer_upper = "".join(sections)

    jiao = int(fraction_text[0])
    fen = int(fraction_text[1])
    if jiao == 0 and fen == 0:
        fraction_upper = "整"
    else:
        fraction_upper = ""
        if jiao:
            fraction_upper += f"{digits[jiao]}角"
        if fen:
            fraction_upper += f"{digits[fen]}分"
    return f"人民币{integer_upper}元{fraction_upper}"


def _serialize_dataclass(value: Any) -> dict[str, Any]:
    if is_dataclass(value):
        return asdict(value)
    return dict(value) if isinstance(value, dict) else {}

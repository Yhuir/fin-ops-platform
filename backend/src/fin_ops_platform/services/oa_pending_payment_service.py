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
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
    relation_status,
    summary_is_linked,
)
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusError,
    OAPaymentStatusRepository,
    PAY_STATUS_PAID,
)
from fin_ops_platform.services.oa_pending_payment_query_contract import (
    FILTER_CONFIG,
    SORT_FIELDS,
    VIEW_MODE_COMPLETED,
    VIEW_MODE_IN_PROGRESS,
    OaPendingPaymentError,
    parse_positive_int as _parse_positive_int,
)
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
SOURCE_VERSION = "oa-pending-payment:complete-relation-edge-proof-v6"
READ_MODEL_STATUS = "live_query"
VIEW_MODES = {VIEW_MODE_COMPLETED, VIEW_MODE_IN_PROGRESS}
OA_APPLICATION_TIME_FIELDS = (
    "审批完成时间",
    "申请时间",
    "申请日期",
    "提交时间",
    "创建时间",
    "单据日期",
    "日期",
    "applicationTime",
    "application_time",
    "applyTime",
    "apply_time",
    "createdAt",
    "created_at",
)


class OaPendingPaymentQueryService:
    """Read-only OA-primary query facade for pending payment reconciliation.

    Data ownership mirrors the refactored invoice relation pages:
    - OA rows come from the OA projection;
    - bank transactions and invoices come from normalized import facts;
    - completed OA relationship evidence comes from WorkbenchRelationReadFacade distribution;
    - in-progress OA-bank payment evidence comes from the OA pending payment relation source.
    """

    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        relation_facade: WorkbenchRelationReadFacade | None = None,
        pending_relation_service: Any | None = None,
        oa_projection: Any | None = None,
        in_progress_oa_projection: Any | None = None,
        payment_status_repository: OAPaymentStatusRepository | None = None,
        lifecycle_policy: Any | None = None,
        require_fresh_relations: bool = True,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._pending_relation_service = pending_relation_service
        self._oa_projection = oa_projection
        self._in_progress_oa_projection = in_progress_oa_projection or oa_projection
        self._payment_status_repository = payment_status_repository
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy()
        self._require_fresh_relations = require_fresh_relations

    def in_progress_oa_projection(self) -> Any | None:
        return self._in_progress_oa_projection

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
        view_mode: str | None = None,
    ) -> dict[str, Any]:
        page_number = _parse_positive_int(page, "page")
        page_limit = _parse_positive_int(page_size, "page_size", maximum=200)
        normalized_view_mode = self._parse_view_mode(view_mode)
        parsed_filters = self._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = self._parse_sort(sort_field, sort_direction)
        context = self._query_context(month_hint=month)
        payment_statuses_by_flow_id = self._payment_statuses_by_flow_id()
        rows = self._filtered_sorted_rows(
            context=context,
            keyword=keyword,
            month=month,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=parsed_filters,
            sort_field=normalized_sort_field,
            sort_direction=normalized_sort_direction,
            view_mode=normalized_view_mode,
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        view_counts = self._view_counts(
            context=context,
            keyword=keyword,
            month=month,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            filters=parsed_filters,
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        total = len(rows)
        paged_rows = rows[(page_number - 1) * page_limit : page_number * page_limit]
        summary = self._summary(rows)
        summary["viewCounts"] = view_counts
        return {
            "rows": paged_rows,
            "pagination": {"page": page_number, "pageSize": page_limit, "total": total},
            "summary": summary,
            "appliedFilters": {"filters": parsed_filters},
            "sort": {"field": normalized_sort_field, "direction": normalized_sort_direction},
            "viewMode": normalized_view_mode,
            "filterConfig": self._filter_config(),
            "read_model_status": READ_MODEL_STATUS,
            "readModelStatus": READ_MODEL_STATUS,
            "source_versions": self.source_versions(),
            "sourceVersions": self.source_versions(),
        }

    def row_by_id(self, row_id: str) -> dict[str, Any] | None:
        return self._row_by_id(row_id, context=self._query_context())

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        record = self._all_view_oa_records_by_id(month=None).get(str(oa_id))
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
        if normalized_kind not in {"oa", "bank", "invoice"}:
            raise OaPendingPaymentError("invalid_relation_kind", "kind must be oa, bank or invoice.")
        context = self._query_context()
        row = self._row_by_id(row_id, context=context)
        if row is None:
            raise OaPendingPaymentError("row_not_found", f"OA pending payment row not found: {row_id}", status_code=HTTPStatus.NOT_FOUND)
        relation_payload = {
            "oa": row["oa"],
            "bank": row["bankTransaction"],
            "invoice": row["invoice"],
        }[normalized_kind]
        title = {
            "oa": "OA关联明细",
            "bank": "支出流水关联明细",
            "invoice": "发票关联明细",
        }[normalized_kind]
        summaries = list(relation_payload.get("summaries") or [])
        return {
            "rowId": row["id"],
            "oaId": row["oa"]["id"],
            "kind": normalized_kind,
            "title": title,
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
        view_mode: str = VIEW_MODE_COMPLETED,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        rows = self._build_rows(
            month=month,
            context=context,
            view_mode=view_mode,
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        rows = [row for row in rows if self._row_matches_trade_date(row, date_from=trade_date_from, date_to=trade_date_to)]
        if keyword:
            needle = str(keyword).strip().lower()
            rows = [row for row in rows if needle in str(row.get("searchText") or "").lower()]
        rows = [row for row in rows if self._row_matches_filters(row, filters)]
        rows.sort(key=lambda row: self._sort_value(row, sort_field), reverse=sort_direction == "desc")
        return rows

    def _view_counts(
        self,
        *,
        context: DistributedInvoiceRelationContext,
        keyword: str | None,
        month: str | None,
        trade_date_from: str | None,
        trade_date_to: str | None,
        filters: list[dict[str, Any]],
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        counts: dict[str, int] = {}
        for view_mode in (VIEW_MODE_COMPLETED, VIEW_MODE_IN_PROGRESS):
            rows = self._filtered_sorted_rows(
                context=context,
                keyword=keyword,
                month=month,
                trade_date_from=trade_date_from,
                trade_date_to=trade_date_to,
                filters=filters,
                sort_field="bank_trade_time",
                sort_direction="desc",
                view_mode=view_mode,
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            )
            counts[view_mode] = self._unique_oa_count(rows)
        return counts

    @staticmethod
    def _unique_oa_count(rows: list[dict[str, Any]]) -> int:
        oa_ids: set[str] = set()
        for row in rows:
            oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
            for summary in list(oa.get("summaries") or []):
                if not isinstance(summary, dict):
                    continue
                oa_id = str(summary.get("oaId") or summary.get("id") or "").strip()
                if oa_id:
                    oa_ids.add(oa_id)
            fallback_id = str(oa.get("id") or "").strip()
            if fallback_id:
                oa_ids.add(fallback_id)
        return len(oa_ids)

    def _build_rows(
        self,
        *,
        month: str | None,
        context: DistributedInvoiceRelationContext,
        view_mode: str = VIEW_MODE_COMPLETED,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
        records: list[OAApplicationRecord] | None = None,
    ) -> list[dict[str, Any]]:
        records = list(records) if records is not None else self._oa_records(
            month=month,
            view_mode=view_mode,
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        record_ids = [record.id for record in records]
        context.preload_relation_rows(record_ids)
        context.preload_oa_records_from_relations(record_ids)
        if view_mode == VIEW_MODE_IN_PROGRESS:
            context.add_distributed_relations(self._pending_relations_for_row_ids(record_ids))
            context.preload_oa_records_from_relations(record_ids)
        oa_by_id = {record.id: record for record in records}
        bank_by_id = context.bank_transactions_by_id()
        invoices_by_id = self._input_invoices_by_id(context=context)
        rows = []
        emitted_relation_ids: set[str] = set()
        grouped_oa_ids: set[str] = set()
        for record in records:
            relations = context.distributed_relations_for_row_ids([record.id])
            for relation in relations:
                relation_id = _relation_row_identity(relation)
                if not relation_id or relation_id in emitted_relation_ids:
                    continue
                relation_records = self._relation_oa_records(
                    relation,
                    oa_by_id,
                    context=context,
                    view_mode=view_mode,
                    month=month,
                )
                if not relation_records or record.id not in {item.id for item in relation_records}:
                    continue
                row = self._relation_group_row(
                    relation=relation,
                    records=relation_records,
                    bank_by_id=bank_by_id,
                    invoices_by_id=invoices_by_id,
                    payment_statuses_by_flow_id=payment_statuses_by_flow_id,
                    scope_key=month,
                )
                rows.append(row)
                emitted_relation_ids.add(relation_id)
                grouped_oa_ids.update(item.id for item in relation_records)
        for record in records:
            if record.id in grouped_oa_ids:
                continue
            rows.append(
                self._single_oa_row(
                    record,
                    context=context,
                    bank_by_id=bank_by_id,
                    invoices_by_id=invoices_by_id,
                    payment_statuses_by_flow_id=payment_statuses_by_flow_id,
                )
            )
        return rows

    def _pending_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        reader = getattr(self._pending_relation_service, "active_relations_for_row_ids", None)
        if not callable(reader):
            return []
        return [relation for relation in list(reader(row_ids) or []) if isinstance(relation, dict)]

    def _single_oa_row(
        self,
        record: OAApplicationRecord,
        *,
        context: DistributedInvoiceRelationContext,
        bank_by_id: dict[str, BankTransaction],
        invoices_by_id: dict[str, Invoice],
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        relations = context.distributed_relations_for_row_ids([record.id])
        bank_payload = self._bank_relation_payload(record, relations=relations, bank_by_id=bank_by_id)
        invoice_payload = self._invoice_relation_payload(record, relations=relations, invoices_by_id=invoices_by_id)
        payment_status = self._payment_status_for_amount(record.amount, bank_payload)
        row = {
            "id": _row_id(record.id),
            "oa": self._oa_summary(record),
            "paymentStatus": payment_status,
            "oaPaymentWriteback": self._oa_payment_writeback_status(
                [record],
                payment_status,
                writeback_eligible=self._payment_writeback_eligible(record.amount, bank_payload),
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            ),
            "bankTransaction": bank_payload,
            "invoice": invoice_payload,
        }
        row["searchText"] = json.dumps(row, ensure_ascii=False, sort_keys=True)
        return row

    def _relation_group_row(
        self,
        *,
        relation: dict[str, Any],
        records: list[OAApplicationRecord],
        bank_by_id: dict[str, BankTransaction],
        invoices_by_id: dict[str, Invoice],
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
        scope_key: str | None = None,
    ) -> dict[str, Any]:
        oa_payload = self._oa_group_payload(records, relation)
        oa_amount = _parse_decimal(oa_payload.get("amount")) or ZERO
        relations = [relation]
        bank_payload = self._bank_relation_payload(None, relations=relations, bank_by_id=bank_by_id, oa_amount=oa_amount)
        invoice_payload = self._invoice_relation_payload(None, relations=relations, invoices_by_id=invoices_by_id, oa_amount=oa_amount)
        payment_status = self._payment_status_for_amount(oa_payload.get("amount"), bank_payload)
        row = {
            "id": _relation_row_id(
                _relation_row_identity(relation),
                scope_key=scope_key,
            ),
            "oa": oa_payload,
            "paymentStatus": payment_status,
            "oaPaymentWriteback": self._oa_payment_writeback_status(
                records,
                payment_status,
                writeback_eligible=self._payment_writeback_eligible(oa_payload.get("amount"), bank_payload),
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            ),
            "bankTransaction": bank_payload,
            "invoice": invoice_payload,
        }
        row["searchText"] = json.dumps(row, ensure_ascii=False, sort_keys=True)
        return row

    @staticmethod
    def _relation_oa_records(
        relation: dict[str, Any],
        oa_by_id: dict[str, OAApplicationRecord],
        *,
        context: DistributedInvoiceRelationContext,
        view_mode: str,
        month: str | None,
    ) -> list[OAApplicationRecord]:
        oa_ids: list[str] = []
        for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
            if row_type == "oa" and row_id in oa_by_id and row_id not in oa_ids:
                oa_ids.append(row_id)
            elif row_type == "oa" and row_id not in oa_by_id and row_id not in oa_ids:
                oa_ids.append(row_id)
        relation_records_by_id = dict(oa_by_id)
        relation_records_by_id.update(context.oa_records_by_id(oa_ids))
        normalized_month = str(month or "").strip()
        return [
            record
            for oa_id in oa_ids
            if (record := relation_records_by_id.get(oa_id)) is not None
            and OaPendingPaymentQueryService._record_matches_view_mode(record, view_mode)
            and (
                not normalized_month
                or normalized_month == "all"
                or str(record.month or "").startswith(normalized_month[:7])
            )
        ]

    @staticmethod
    def _oa_group_payload(records: list[OAApplicationRecord], relation: dict[str, Any]) -> dict[str, Any]:
        summaries = [OaPendingPaymentQueryService._oa_relation_summary(record, relation) for record in records]
        primary = summaries[0] if summaries else {}
        parsed_amounts = [_parse_decimal(summary.get("amount")) for summary in summaries]
        has_complete_amounts = len(parsed_amounts) == len(summaries) and all(amount is not None for amount in parsed_amounts)
        total = sum((amount or ZERO for amount in parsed_amounts), start=ZERO)
        relation_count = len(summaries)
        return {
            "id": primary.get("oaId", ""),
            "primaryOaId": primary.get("oaId", ""),
            "applicantName": primary.get("applicantName", ""),
            "applicationType": primary.get("applicationType", ""),
            "projectName": primary.get("projectName", ""),
            "applicationTime": primary.get("applicationTime", ""),
            "amount": _money(total) if has_complete_amounts else "",
            "detailAvailable": relation_count > 0,
            "month": primary.get("month", ""),
            "workflowNo": primary.get("workflowNo", ""),
            "reason": primary.get("reason", ""),
            "counterpartyName": primary.get("counterpartyName", ""),
            "workflowStatus": primary.get("workflowStatus", ""),
            "relationCount": relation_count,
            "hasMultiple": relation_count > 1,
            "detailMode": "none" if relation_count == 0 else "list" if relation_count > 1 else "single",
            "summaries": summaries,
        }

    @staticmethod
    def _oa_relation_summary(record: OAApplicationRecord, relation: dict[str, Any] | None = None) -> dict[str, Any]:
        summary = {
            "oaId": record.id,
            "applicantName": record.applicant,
            "applicationType": record.apply_type,
            "projectName": record.project_name_display or record.project_name,
            "applicationTime": _oa_application_time(record),
            "amount": _money(record.amount) if _parse_decimal(record.amount) is not None else "",
            "month": record.month,
            "workflowNo": record.case_id or "",
            "reason": record.reason,
            "counterpartyName": record.counterparty_name,
            "workflowStatus": _workflow_status(record),
        }
        if relation is not None:
            summary["relationCaseId"] = relation.get("case_id", "")
            summary["relationStatus"] = relation_status(relation)
            summary["relationSource"] = str(relation.get("relation_source") or "")
        return summary

    def _payment_status_for_amount(self, oa_amount_value: Any, bank_payload: dict[str, Any]) -> dict[str, str]:
        oa_amount = _parse_decimal(oa_amount_value)
        has_linked_payment_relation = (
            int(bank_payload.get("linkedRelationCount") or 0) > 0
            or int(bank_payload.get("missingBankRelationCount") or 0) > 0
            or int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0
        )
        return self._lifecycle_policy.evaluate_oa_payment(
            oa_amount=oa_amount,
            paid_total=_decimal(bank_payload.get("paidTotal")),
            has_bank=has_linked_payment_relation,
            has_missing_bank_relation=int(bank_payload.get("missingBankRelationCount") or 0) > 0,
            has_non_outflow_bank_relation=int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0,
        )

    def _oa_payment_writeback_status(
        self,
        records: list[OAApplicationRecord],
        payment_status: dict[str, str],
        *,
        writeback_eligible: bool = True,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if str(payment_status.get("code") or "") != "paid":
            return _oa_writeback_status("not_written", sync_status="not_required")
        if not writeback_eligible:
            return _oa_writeback_status("not_written", sync_status="not_required")
        if self._payment_status_repository is None:
            return _oa_writeback_status("not_written", sync_status="unavailable")
        flow_ids: list[str] = []
        try:
            for record in records:
                flow_id = self._payment_status_repository.resolve_flow_id(record)
                if not flow_id:
                    return _oa_writeback_status("not_written", sync_status="flow_id_missing")
                flow_ids.append(flow_id)
                if payment_statuses_by_flow_id is not None:
                    status_record = payment_statuses_by_flow_id.get(flow_id)
                else:
                    status_record = self._payment_status_repository.get_payment_status(flow_id)
                if status_record is None or status_record.pay_status != PAY_STATUS_PAID:
                    return _oa_writeback_status("not_written", flow_ids=flow_ids, sync_status="ready")
        except OAPaymentStatusError:
            return _oa_writeback_status("not_written", flow_ids=flow_ids, sync_status="unavailable")
        return _oa_writeback_status("written", flow_ids=flow_ids, sync_status="ready")

    @staticmethod
    def _payment_writeback_eligible(oa_amount_value: Any, bank_payload: dict[str, Any]) -> bool:
        oa_amount = _parse_decimal(oa_amount_value)
        if oa_amount is None:
            return False
        if int(bank_payload.get("linkedRelationCount") or 0) <= 0:
            return False
        if int(bank_payload.get("missingBankRelationCount") or 0) > 0:
            return False
        if int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0:
            return False
        return _within_cent(_decimal(bank_payload.get("paidTotal")), oa_amount)

    def _oa_records(
        self,
        *,
        month: str | None,
        view_mode: str = VIEW_MODE_COMPLETED,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> list[OAApplicationRecord]:
        records = list(
            self._oa_records_by_id(
                month=month,
                view_mode=view_mode,
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            ).values()
        )
        normalized_month = str(month or "").strip()
        if normalized_month and normalized_month != "all":
            records = [record for record in records if str(record.month or "").startswith(normalized_month[:7])]
        records = [record for record in records if self._record_matches_view_mode(record, view_mode)]
        records.sort(key=lambda record: (record.month or "", record.applicant or "", record.id))
        return records

    def _oa_records_by_id(
        self,
        *,
        month: str | None,
        view_mode: str = VIEW_MODE_COMPLETED,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> dict[str, OAApplicationRecord]:
        projection = self._projection_for_view_mode(view_mode)
        if projection is None:
            return {}
        normalized_month = str(month or "").strip()
        list_month = getattr(projection, "list_application_records", None)
        if normalized_month and normalized_month != "all" and callable(list_month):
            records = list_month(normalized_month)
        else:
            list_all = getattr(projection, "list_all_application_records", None)
            records = list_all() if callable(list_all) else []
        records = [record for record in records if isinstance(record, OAApplicationRecord)]
        if view_mode == VIEW_MODE_IN_PROGRESS and not bool(getattr(projection, "payment_admission_filtered", False)):
            records = self._filter_records_by_payment_status_admission(
                records,
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            )
        return {record.id: record for record in records if isinstance(record, OAApplicationRecord)}

    def _all_view_oa_records_by_id(self, *, month: str | None) -> dict[str, OAApplicationRecord]:
        records = self._oa_records_by_id(month=month, view_mode=VIEW_MODE_COMPLETED)
        for record_id, record in self._oa_records_by_id(month=month, view_mode=VIEW_MODE_IN_PROGRESS).items():
            records.setdefault(record_id, record)
        return records

    def _projection_for_view_mode(self, view_mode: str) -> Any | None:
        if view_mode == VIEW_MODE_IN_PROGRESS:
            return self._in_progress_oa_projection
        return self._oa_projection

    def _filter_records_by_payment_status_admission(
        self,
        records: list[OAApplicationRecord],
        *,
        payment_statuses_by_flow_id: dict[str, Any] | None = None,
    ) -> list[OAApplicationRecord]:
        if self._payment_status_repository is None:
            return records
        payment_statuses = payment_statuses_by_flow_id
        if payment_statuses is None:
            list_statuses = getattr(self._payment_status_repository, "list_payment_statuses", None)
            if not callable(list_statuses):
                return records
            try:
                payment_statuses = list_statuses()
            except OAPaymentStatusError:
                return []
        if not isinstance(payment_statuses, dict):
            return []
        admitted_flow_ids = {
            str(flow_id or "").strip()
            for flow_id in payment_statuses
            if str(flow_id or "").strip()
        }
        if not admitted_flow_ids:
            return []
        admitted_records: list[OAApplicationRecord] = []
        for record in records:
            try:
                flow_id = self._payment_status_repository.resolve_flow_id(record)
            except OAPaymentStatusError:
                continue
            if flow_id and flow_id in admitted_flow_ids:
                admitted_records.append(record)
        return admitted_records

    def _payment_statuses_by_flow_id(self) -> dict[str, Any] | None:
        repository = self._payment_status_repository
        if repository is None:
            return None
        list_statuses = getattr(repository, "list_payment_statuses", None)
        if not callable(list_statuses):
            return None
        try:
            payment_statuses = list_statuses()
        except OAPaymentStatusError:
            return None
        return dict(payment_statuses) if isinstance(payment_statuses, dict) else None

    def _input_invoices_by_id(self, *, context: DistributedInvoiceRelationContext | None = None) -> dict[str, Invoice]:
        if context is not None:
            invoices = context.list_invoices(month="all", invoice_type=InvoiceType.INPUT)
        else:
            invoices = self._import_service.list_invoices(month="all", invoice_type=InvoiceType.INPUT)
        return {
            invoice.id: invoice
            for invoice in invoices
        }

    @staticmethod
    def _oa_summary(record: OAApplicationRecord) -> dict[str, Any]:
        summary = OaPendingPaymentQueryService._oa_relation_summary(record)
        return {
            "id": summary["oaId"],
            "primaryOaId": summary["oaId"],
            "applicantName": summary["applicantName"],
            "applicationType": summary["applicationType"],
            "projectName": summary["projectName"],
            "applicationTime": summary["applicationTime"],
            "amount": summary["amount"],
            "detailAvailable": True,
            "month": summary["month"],
            "workflowNo": summary["workflowNo"],
            "reason": summary["reason"],
            "counterpartyName": summary["counterpartyName"],
            "workflowStatus": summary["workflowStatus"],
            "relationCount": 1,
            "hasMultiple": False,
            "detailMode": "single",
            "summaries": [summary],
        }

    def _bank_relation_payload(
        self,
        record: OAApplicationRecord | None,
        *,
        relations: list[dict[str, Any]],
        bank_by_id: dict[str, BankTransaction],
        oa_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        summaries = []
        seen: set[str] = set()
        seen_non_outflow_edges: set[tuple[str, str]] = set()
        non_outflow_relation_edges: list[dict[str, str]] = []
        missing_bank_relation_count = 0
        resolved_oa_amount = oa_amount if oa_amount is not None else (_parse_decimal(record.amount) if record is not None else None)
        resolved_oa_amount = resolved_oa_amount or ZERO
        for relation in relations:
            linked_relation = relation_status(relation) == "linked"
            for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
                if row_type not in {"bank", "bank_transaction"}:
                    continue
                bank = bank_by_id.get(row_id)
                if bank is None:
                    if linked_relation:
                        missing_bank_relation_count += 1
                    continue
                if _bank_direction(bank) != "outflow":
                    if linked_relation:
                        edge_key = (str(relation.get("case_id") or ""), bank.id)
                        if edge_key not in seen_non_outflow_edges:
                            seen_non_outflow_edges.add(edge_key)
                            non_outflow_relation_edges.append(
                                {
                                    "bankTransactionId": bank.id,
                                    "relationCaseId": edge_key[0],
                                    "relationStatus": relation_status(relation),
                                    "relationSource": str(relation.get("relation_source") or ""),
                                }
                            )
                    continue
                if bank.id not in seen:
                    seen.add(bank.id)
                    summaries.append(self._bank_summary(bank, resolved_oa_amount, relation))
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        linked_summaries = [summary for summary in public_summaries if summary_is_linked(summary)]
        paid_total = sum((_decimal(summary.get("amount")) for summary in linked_summaries), start=ZERO)
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
            "linkedRelationCount": len(linked_summaries),
            "missingBankRelationCount": missing_bank_relation_count,
            "nonOutflowBankRelationCount": len(non_outflow_relation_edges),
            "nonOutflowRelationEdges": non_outflow_relation_edges,
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
            "relationStatus": relation_status(relation),
            "relationSource": str(relation.get("relation_source") or ""),
            "_sort": (diff, -timestamp, bank.id),
        }

    def _invoice_relation_payload(
        self,
        record: OAApplicationRecord | None,
        *,
        relations: list[dict[str, Any]],
        invoices_by_id: dict[str, Invoice],
        oa_amount: Decimal | None = None,
    ) -> dict[str, Any]:
        summaries = []
        seen: set[str] = set()
        resolved_oa_amount = oa_amount if oa_amount is not None else (_parse_decimal(record.amount) if record is not None else None)
        resolved_oa_amount = resolved_oa_amount or ZERO
        for relation in relations:
            for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation):
                if row_type != "invoice":
                    continue
                invoice = invoices_by_id.get(row_id)
                if invoice is not None and invoice.id not in seen:
                    seen.add(invoice.id)
                    summaries.append(self._invoice_summary(invoice, resolved_oa_amount, relation))
        summaries.sort(key=lambda item: item["_sort"])
        public_summaries = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
        primary = public_summaries[0] if public_summaries else {}
        invoice_total = sum((_decimal(summary.get("totalWithTax")) for summary in public_summaries), start=ZERO)
        return {
            "primaryInvoiceId": primary.get("invoiceId"),
            "digitalInvoiceNo": primary.get("digitalInvoiceNo", ""),
            "sellerName": primary.get("sellerName", ""),
            "invoiceDate": primary.get("invoiceDate", ""),
            "totalWithTax": _money(invoice_total) if public_summaries else "",
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
            "relationStatus": relation_status(relation),
            "relationSource": str(relation.get("relation_source") or ""),
            "_sort": (abs(total - oa_amount), invoice.invoice_date or "", invoice.id),
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

    @staticmethod
    def _parse_view_mode(view_mode: str | None) -> str:
        normalized = str(view_mode or VIEW_MODE_COMPLETED).strip() or VIEW_MODE_COMPLETED
        if normalized not in VIEW_MODES:
            raise OaPendingPaymentError(
                "invalid_view_mode",
                "view_mode must be completed or in_progress.",
                details={"view_mode": normalized},
            )
        return normalized

    @staticmethod
    def _record_matches_view_mode(record: OAApplicationRecord, view_mode: str) -> bool:
        workflow_status = _workflow_status(record)
        if view_mode == VIEW_MODE_IN_PROGRESS:
            return workflow_status == VIEW_MODE_IN_PROGRESS
        return workflow_status in {"", VIEW_MODE_COMPLETED}

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
        for view_mode in (VIEW_MODE_COMPLETED, VIEW_MODE_IN_PROGRESS):
            for row in self._build_rows(month=None, context=context, view_mode=view_mode):
                if row["id"] == normalized_row_id:
                    return row
        return None


def _status(code: str, label: str, reason: str) -> dict[str, str]:
    severity = "success" if code == "paid" else "warning" if code == "unpaid" else "error"
    return {"code": code, "label": label, "reason": reason, "severity": severity}


def _oa_writeback_status(
    code: str,
    *,
    flow_ids: list[str] | None = None,
    sync_status: str = "ready",
) -> dict[str, Any]:
    normalized_code = "written" if code == "written" else "not_written"
    return {
        "code": normalized_code,
        "label": "已写回" if normalized_code == "written" else "未写回",
        "flowIds": list(flow_ids or []),
        "syncStatus": sync_status,
    }


def _row_id(oa_id: str) -> str:
    return "oa_pending_payment_row_" + sha1(str(oa_id).encode("utf-8")).hexdigest()[:16]


def _relation_row_identity(relation: dict[str, Any]) -> str:
    case_id = str(relation.get("case_id") or "").strip()
    if case_id:
        return case_id
    typed_rows = [
        f"{row_type}:{row_id}"
        for row_id, row_type in DistributedInvoiceRelationContext.typed_relation_rows(relation)
    ]
    return "|".join(typed_rows)


def _relation_row_id(identity: str, *, scope_key: str | None = None) -> str:
    normalized_scope_key = str(scope_key or "").strip()
    scoped_identity = (
        f"{identity}:{normalized_scope_key[:7]}"
        if normalized_scope_key and normalized_scope_key != "all"
        else str(identity)
    )
    return "oa_pending_payment_relation_" + sha1(scoped_identity.encode("utf-8")).hexdigest()[:16]


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


def _oa_application_time(record: OAApplicationRecord) -> str:
    detail_fields = record.detail_fields if isinstance(record.detail_fields, dict) else {}
    for field in OA_APPLICATION_TIME_FIELDS:
        text = _oa_time_text(detail_fields.get(field))
        if text:
            return text
    return ""


def _workflow_status(record: OAApplicationRecord) -> str:
    return str(getattr(record, "workflow_status", "") or "").strip()


def _oa_time_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "—", "None", "null"}:
        return ""
    normalized = text.replace("T", " ").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1].strip()
    if _looks_like_datetime(normalized):
        return normalized[:19]
    return normalized


def _looks_like_datetime(value: str) -> bool:
    return (
        len(value) >= 19
        and value[4] == "-"
        and value[7] == "-"
        and value[10] == " "
        and value[13] == ":"
        and value[16] == ":"
    )


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
    if kind == "oa":
        return [
            {
                "title": f"OA {index}",
                "fields": [
                    {"label": "申请人", "value": summary.get("applicantName")},
                    {"label": "类型", "value": summary.get("applicationType")},
                    {"label": "项目名称", "value": summary.get("projectName")},
                    {"label": "申请时间", "value": summary.get("applicationTime")},
                    {"label": "金额", "value": summary.get("amount")},
                    {"label": "月份", "value": summary.get("month")},
                    {"label": "事由", "value": summary.get("reason")},
                    {"label": "往来方", "value": summary.get("counterpartyName")},
                ],
            }
            for index, summary in enumerate(typed_summaries, start=1)
        ]
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

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from http import HTTPStatus
import json
from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType, ImportDecision, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


PENDING_INVOICE_RELATION_MODE = "pending_invoice_manual_invoice"
ATTACH_EXISTING_INVOICE_RELATION_MODE = "pending_invoice_attach_existing_invoice"
MANUAL_INVOICE_SOURCE_NAME = "pending_invoice_manual_entry"
MANUAL_INVOICE_SOURCE_TYPE = "manual_invoice_import"
EXPENSE_FILTERS = {"requires_invoice", "bank_statement_as_invoice", "no_invoice_required"}
VALID_FILTERS = {"all", *EXPENSE_FILTERS}
PENDING_INVOICE_FILTER_FIELDS: dict[str, set[str]] = {
    "trade_date": {"between"},
    "bank_name": {"in", "contains"},
    "account_name": {"in", "contains"},
    "counterparty_name": {"contains", "in"},
    "amount": {"between", "eq"},
    "summary_remark": {"contains"},
    "status_code": {"in"},
    "rule_group": {"in"},
    "seller_name": {"contains", "in"},
    "invoice_total": {"between", "eq"},
    "oa_applicant": {"contains", "in"},
    "project_name": {"contains", "in"},
}
PENDING_INVOICE_SORT_FIELDS = {
    "trade_date",
    "amount",
    "counterparty_name",
    "status_code",
    "seller_name",
    "invoice_total",
    "oa_applicant",
    "project_name",
}
INVOICE_CANDIDATE_SORT_FIELDS = {"issue_date", "total_with_tax", "seller_name", "amount_difference_abs"}
COMMAND_STATUSES = {
    "started",
    "invoice_created",
    "relation_created",
    "completed",
    "failed_recoverable",
    "failed_terminal",
}


class PendingInvoiceError(ValueError):
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


class PendingInvoiceQueryService:
    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        pair_relation_service: WorkbenchPairRelationService,
        category_service: BankTransactionCategoryService,
        app_settings_provider: Callable[[], dict[str, Any]],
        effective_category_provider: Any | None = None,
        oa_projection: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._pair_relation_service = pair_relation_service
        self._category_service = category_service
        self._app_settings_provider = app_settings_provider
        self._effective_category_provider = effective_category_provider
        self._oa_projection = oa_projection

    def clear_cache(self) -> None:
        return None

    def list_rows(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any]:
        normalized_direction = self._normalize_direction(direction)
        normalized_filter = self._normalize_filter(filter)
        if normalized_direction == "income" and normalized_filter in EXPENSE_FILTERS:
            raise PendingInvoiceError(
                "invalid_filter_for_income",
                "Income pending invoice rows do not support expense invoice tag filters.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        page_number = max(_optional_int(page, default=1), 1)
        page_limit = min(max(_optional_int(page_size, default=50), 1), 200)

        all_transactions = [
            transaction
            for transaction in self._import_service.list_transactions(month="all")
            if self._matches_date_range(transaction, date_from=date_from, date_to=date_to)
        ]
        transactions = [
            transaction
            for transaction in all_transactions
            if self._transaction_matches_direction(transaction, normalized_direction)
        ]
        categories = self._effective_categories(transactions)
        tag_groups = self._pending_invoice_tag_groups()
        rows = [
            self._row_payload(
                transaction,
                direction=normalized_direction,
                category=categories.get(transaction.id, {}),
                tag_groups=tag_groups,
            )
            for transaction in transactions
            if self._transaction_matches_filter(
                transaction,
                direction=normalized_direction,
                filter_name=normalized_filter,
                category=categories.get(transaction.id, {}),
                tag_groups=tag_groups,
            )
        ]
        if keyword:
            normalized_keyword = str(keyword).strip().lower()
            rows = [row for row in rows if normalized_keyword in str(row).lower()]
        rows = self._apply_filters(rows, filters)
        rows = self._apply_sort(rows, sort_field=sort_field, sort_direction=sort_direction)

        total = len(rows)
        start = (page_number - 1) * page_limit
        paged_rows = rows[start : start + page_limit]
        missing_invoice_rows = sum(1 for row in rows if not row["invoices"])
        create_invoice_available_rows = sum(1 for row in rows if row["can_create_invoice"])
        return {
            "direction": normalized_direction,
            "filter": normalized_filter,
            "rows": paged_rows,
            "pagination": {
                "page": page_number,
                "page_size": page_limit,
                "total": total,
            },
            "summary": {
                "total_rows": total,
                "missing_invoice_rows": missing_invoice_rows,
                "create_invoice_available_rows": create_invoice_available_rows,
                "source_summary": self._source_summary_for_transactions(
                    all_transactions,
                    direction=normalized_direction,
                ),
            },
            "bank_transaction_tags": self._app_settings_provider().get("bank_transaction_tags") or {},
            "bank_transaction_tags_version": int(
                (self._app_settings_provider().get("bank_transaction_tags") or {}).get("version") or 1
            ),
        }

    def _effective_categories(self, transactions: list[BankTransaction]) -> dict[str, dict[str, Any]]:
        if self._effective_category_provider is not None:
            bulk_get_for_rows = getattr(self._effective_category_provider, "bulk_get_for_rows", None)
            if callable(bulk_get_for_rows):
                return bulk_get_for_rows(transactions)
            bulk_get = getattr(self._effective_category_provider, "bulk_get", None)
            if callable(bulk_get):
                return bulk_get([transaction.id for transaction in transactions])
        return self._category_service.bulk_get([transaction.id for transaction in transactions])

    def row_for_transaction(self, transaction_id: str, *, direction: str) -> dict[str, Any]:
        normalized_direction = self._normalize_direction(direction)
        transaction = self._get_transaction(transaction_id)
        if not self._transaction_matches_direction(transaction, normalized_direction):
            raise PendingInvoiceError(
                "bank_transaction_not_found",
                f"Bank transaction not found in pending invoice rows: {transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        category = self._effective_categories([transaction]).get(transaction.id, {})
        return self._row_payload(
            transaction,
            direction=normalized_direction,
            category=category,
            tag_groups=self._pending_invoice_tag_groups(),
        )

    def normalize_row_payloads(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return [self._normalize_row_payload(row) for row in rows]

    def _normalize_row_payload(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(row)
        bank = payload.get("bank_transaction")
        if isinstance(bank, dict):
            self._apply_bank_identity(bank)
        return payload

    def _get_transaction(self, transaction_id: str) -> BankTransaction:
        try:
            return self._import_service.get_transaction(str(transaction_id or "").strip())
        except KeyError as exc:
            raise PendingInvoiceError(
                "bank_transaction_not_found",
                f"Bank transaction not found: {transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            ) from exc

    @staticmethod
    def _normalize_direction(direction: str) -> str:
        normalized = str(direction or "").strip()
        if normalized not in {"expense", "income"}:
            raise PendingInvoiceError("invalid_direction", "direction must be expense or income.")
        return normalized

    @staticmethod
    def _normalize_filter(filter_name: str | None) -> str:
        normalized = str(filter_name or "all").strip() or "all"
        if normalized not in VALID_FILTERS:
            raise PendingInvoiceError("invalid_filter", "filter must be all or a supported pending invoice group.")
        return normalized

    @staticmethod
    def _transaction_matches_direction(transaction: BankTransaction, direction: str) -> bool:
        expected = TransactionDirection.OUTFLOW if direction == "expense" else TransactionDirection.INFLOW
        return transaction.txn_direction == expected

    @classmethod
    def _source_summary_for_transactions(
        cls,
        transactions: list[BankTransaction],
        *,
        direction: str,
    ) -> dict[str, int]:
        expense_rows = sum(1 for transaction in transactions if cls._transaction_matches_direction(transaction, "expense"))
        income_rows = sum(1 for transaction in transactions if cls._transaction_matches_direction(transaction, "income"))
        total_rows = expense_rows + income_rows
        current_rows = expense_rows if direction == "expense" else income_rows
        return {
            "bank_transaction_rows": total_rows,
            "expense_rows": expense_rows,
            "income_rows": income_rows,
            "current_direction_rows": current_rows,
            "excluded_direction_rows": max(total_rows - current_rows, 0),
        }

    @staticmethod
    def _matches_date_range(
        transaction: BankTransaction,
        *,
        date_from: str | None,
        date_to: str | None,
    ) -> bool:
        txn_date = str(transaction.txn_date or transaction.trade_time or "")[:10]
        if date_from and txn_date < str(date_from):
            return False
        if date_to and txn_date > str(date_to):
            return False
        return True

    def _pending_invoice_tag_groups(self) -> dict[str, set[str]]:
        payload = self._app_settings_provider()
        groups = ((payload.get("pending_invoice_tag_groups") or {}).get("groups") or {})
        return {
            group_name: {
                str(code).strip()
                for code in list((groups.get(group_name) or {}).get("tag_codes") or [])
                if str(code).strip()
            }
            for group_name in EXPENSE_FILTERS
        }

    @staticmethod
    def _group_for_category(category_code: str | None, tag_groups: dict[str, set[str]]) -> str | None:
        if not category_code:
            return None
        for group_name in ("requires_invoice", "bank_statement_as_invoice", "no_invoice_required"):
            if category_code in tag_groups.get(group_name, set()):
                return group_name
        return None

    def _transaction_matches_filter(
        self,
        transaction: BankTransaction,
        *,
        direction: str,
        filter_name: str,
        category: dict[str, Any],
        tag_groups: dict[str, set[str]],
    ) -> bool:
        if direction == "income" or filter_name == "all":
            return True
        group = self._group_for_category(category.get("category_code"), tag_groups)
        return group == filter_name

    def _bank_account_mappings_by_last4(self) -> dict[str, dict[str, str]]:
        settings = self._app_settings_provider()
        mappings: dict[str, dict[str, str]] = {}
        for item in list(settings.get("bank_account_mappings") or []):
            if not isinstance(item, dict):
                continue
            last4 = self._account_last4(item.get("last4"))
            bank_name = str(item.get("bank_name") or "").strip()
            if not last4 or not bank_name:
                continue
            mappings[last4] = {
                "bank_name": bank_name,
                "short_name": str(item.get("short_name") or "").strip(),
            }
        return mappings

    @staticmethod
    def _account_last4(value: Any) -> str:
        digits = "".join(ch for ch in str(value or "") if ch.isdigit())
        return digits[-4:] if len(digits) >= 4 else digits

    def _apply_bank_identity(self, bank: dict[str, Any]) -> None:
        last4 = self._account_last4(bank.get("account_last4")) or self._account_last4(bank.get("account_no"))
        mapping = self._bank_account_mappings_by_last4().get(last4)
        raw_bank_name = str(bank.get("bank_name") or "").strip()
        if mapping is not None:
            bank["bank_name"] = mapping["bank_name"]
            bank["bank_short_name"] = mapping["short_name"] or mapping["bank_name"]
        else:
            bank["bank_name"] = raw_bank_name
            bank["bank_short_name"] = str(bank.get("bank_short_name") or "").strip()
        bank["account_last4"] = last4

    def _row_payload(
        self,
        transaction: BankTransaction,
        *,
        direction: str,
        category: dict[str, Any],
        tag_groups: dict[str, set[str]],
    ) -> dict[str, Any]:
        target_invoice_type = InvoiceType.INPUT if direction == "expense" else InvoiceType.OUTPUT
        invoice_map = {
            invoice.id: invoice
            for invoice in self._import_service.list_invoices(month="all", invoice_type=target_invoice_type)
        }
        relations = self._pair_relation_service.active_relations_for_row_ids([transaction.id])
        invoice_relations: list[tuple[dict[str, Any], Invoice]] = []
        for relation in relations:
            for row_id in list(relation.get("row_ids") or []):
                invoice = invoice_map.get(str(row_id))
                if invoice is not None and invoice.invoice_type == target_invoice_type:
                    invoice_relations.append((relation, invoice))
        invoice_relations.sort(key=lambda item: str(item[0].get("case_id") or ""))
        invoices = [self._invoice_payload(invoice, direction=direction) for _, invoice in invoice_relations]
        category_code = category.get("category_code")
        group = self._group_for_category(category_code, tag_groups)
        can_create_invoice = not invoices and not (direction == "expense" and group == "no_invoice_required")
        payment_summary = self._payment_summary_for_relations(invoice_relations)
        oa_payload = self._oa_payload_from_relations(relations)
        status_payload = self._status_payload(
            direction=direction,
            group=group,
            has_invoices=bool(invoices),
            payment_summary=payment_summary,
            matched_rule=self._matched_rule_payload(group=group, category=category),
        )
        input_invoices = {
            "primary": invoices[0] if invoices else None,
            "relation_count": len(invoices),
            "has_multiple": len(invoices) > 1,
            "summaries": invoices,
            "payment_summary": payment_summary,
        }
        trade_date = str(transaction.txn_date or transaction.trade_time or "")[:10]
        debit_amount = transaction.amount if transaction.txn_direction == TransactionDirection.OUTFLOW else Decimal("0.00")
        credit_amount = transaction.amount if transaction.txn_direction == TransactionDirection.INFLOW else Decimal("0.00")
        bank_identity = {
            "account_no": transaction.account_no,
            "bank_name": transaction.imported_bank_name or "",
            "account_name": transaction.account_name or "",
            "account_last4": transaction.imported_bank_last4 or self._account_last4(transaction.account_no),
        }
        self._apply_bank_identity(bank_identity)
        return {
            "id": transaction.id,
            "bank_transaction": {
                "id": transaction.id,
                "account_no": transaction.account_no,
                "counterparty_name": transaction.counterparty_name_raw,
                "counterparty_account_no": transaction.counterparty_account_no or "",
                "counterparty_bank_name": transaction.counterparty_bank_name or "",
                "trade_time": transaction.trade_time or transaction.txn_date,
                "booked_date": transaction.booked_date or transaction.txn_date or "",
                "trade_date": trade_date,
                "amount": _decimal_to_str(transaction.amount),
                "debit_amount": _decimal_to_str(debit_amount),
                "credit_amount": _decimal_to_str(credit_amount),
                "balance": _decimal_to_str(transaction.balance) if transaction.balance is not None else "",
                "currency": transaction.currency or "CNY",
                "bank_name": bank_identity["bank_name"],
                "bank_short_name": bank_identity["bank_short_name"],
                "account_name": transaction.account_name or "",
                "account_last4": bank_identity["account_last4"],
                "summary": transaction.summary or "",
                "remark": transaction.remark or "",
                "statement_serial_no": transaction.bank_serial_no or "",
                "enterprise_serial_no": transaction.enterprise_serial_no or "",
                "voucher_type": transaction.voucher_kind or "",
                "voucher_no": transaction.voucher_no or "",
                "effective_tag_code": category_code,
                "effective_tag_label": category.get("category_label"),
                "effective_tag_primary_label": category.get("category_primary_label"),
                "effective_tag_sub_label": category.get("category_sub_label"),
                "effective_tag_label_path": list(category.get("category_label_path") or []),
            },
            "invoice_acquisition_status": status_payload,
            "input_invoices": input_invoices,
            "oa": oa_payload,
            "invoices": invoices,
            "oa_applicant": self._oa_applicant_from_relations(relations),
            "can_create_invoice": can_create_invoice,
            "relation_case_ids": [str(relation.get("case_id")) for relation, _ in invoice_relations],
        }

    def _payment_summary_for_relations(self, invoice_relations: list[tuple[dict[str, Any], Invoice]]) -> dict[str, Any]:
        invoice_ids = [invoice.id for _, invoice in invoice_relations]
        invoice_total = sum((self._invoice_total(invoice) for _, invoice in invoice_relations), start=Decimal("0.00"))
        paid_transaction_ids: set[str] = set()
        for invoice_id in invoice_ids:
            for relation in self._pair_relation_service.active_relations_for_row_ids([invoice_id]):
                row_types = [str(item) for item in list(relation.get("row_types") or [])]
                row_ids = [str(item) for item in list(relation.get("row_ids") or [])]
                for row_id, row_type in zip(row_ids, row_types, strict=False):
                    if row_type == "bank":
                        paid_transaction_ids.add(row_id)
        paid_total = Decimal("0.00")
        for transaction_id in sorted(paid_transaction_ids):
            try:
                paid_total += self._import_service.get_transaction(transaction_id).amount
            except KeyError:
                continue
        remaining = invoice_total - paid_total
        if remaining < Decimal("0.00"):
            remaining = Decimal("0.00")
        return {
            "invoice_total": _decimal_to_str(invoice_total),
            "paid_total": _decimal_to_str(paid_total),
            "remaining_amount": _decimal_to_str(remaining),
            "difference_amount": _decimal_to_str(invoice_total - paid_total),
            "payment_transaction_count": len(paid_transaction_ids),
        }

    @staticmethod
    def _matched_rule_payload(*, group: str | None, category: dict[str, Any]) -> dict[str, Any] | None:
        if not group:
            return None
        return {
            "group": group,
            "tag_code": category.get("category_code"),
            "tag_label": category.get("category_label"),
            "tag_primary_label": category.get("category_primary_label"),
            "tag_sub_label": category.get("category_sub_label"),
            "tag_label_path": list(category.get("category_label_path") or []),
        }

    @staticmethod
    def _status_payload(
        *,
        direction: str,
        group: str | None,
        has_invoices: bool,
        payment_summary: dict[str, Any],
        matched_rule: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if direction != "expense":
            return {
                "code": "pending",
                "label": "待确认",
                "reason": "收入方向保留原有待找发票逻辑。",
                "severity": "default",
                "primary_action": None,
                "matched_rule": matched_rule,
            }
        invoice_total = _decimal_from_text(payment_summary.get("invoice_total"))
        paid_total = _decimal_from_text(payment_summary.get("paid_total"))
        if has_invoices and invoice_total > paid_total:
            return {
                "code": "invoice_not_fully_paid",
                "label": "未支付完已开票",
                "reason": "已有关联进项发票，但关联支付流水合计小于发票价税合计。",
                "severity": "warning",
                "primary_action": "view_relation",
                "matched_rule": matched_rule,
            }
        if has_invoices:
            return {
                "code": "paid_invoiced",
                "label": "已支付已开票",
                "reason": "支出流水已关联进项发票。",
                "severity": "success",
                "primary_action": "view_relation",
                "matched_rule": matched_rule,
            }
        if group == "no_invoice_required":
            return {
                "code": "no_invoice_required",
                "label": "无需开票",
                "reason": "流水分类命中无需开票规则。",
                "severity": "default",
                "primary_action": "view_rules",
                "matched_rule": matched_rule,
            }
        if group == "bank_statement_as_invoice":
            return {
                "code": "bank_statement_as_invoice",
                "label": "流水代替发票",
                "reason": "流水分类命中流水代替发票规则。",
                "severity": "info",
                "primary_action": "view_rules",
                "matched_rule": matched_rule,
            }
        return {
            "code": "paid_pending_invoice",
            "label": "已支付待开票",
            "reason": "支出流水未关联进项发票，也未命中免票或流水替票规则。",
            "severity": "error",
            "primary_action": "attach_or_create_invoice",
            "matched_rule": matched_rule,
        }

    @staticmethod
    def _invoice_payload(invoice: Invoice, *, direction: str) -> dict[str, Any]:
        return {
            "id": invoice.id,
            "invoice_no": invoice.invoice_no,
            "digital_invoice_no": invoice.digital_invoice_no,
            "issue_date": invoice.invoice_date,
            "total_with_tax": _decimal_to_str(invoice.total_with_tax if invoice.total_with_tax is not None else invoice.amount),
            "seller_name": invoice.seller_name,
            "buyer_name": invoice.buyer_name,
            "invoice_type": "input" if invoice.invoice_type == InvoiceType.INPUT else "output",
            "counterparty_display_name": invoice.seller_name if direction == "expense" else invoice.buyer_name,
        }

    @staticmethod
    def _invoice_total(invoice: Invoice) -> Decimal:
        return _invoice_total(invoice)

    def _oa_payload_from_relations(self, relations: list[dict[str, Any]]) -> dict[str, Any]:
        summaries: list[dict[str, Any]] = []
        seen_ids: set[str] = set()
        oa_ids = self._oa_ids_from_relations(relations)
        oa_records = self._oa_records_by_id(oa_ids)
        for relation in relations:
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            metadata = self._first_relation_metadata(relation)
            for row_id, row_type in zip(row_ids, row_types, strict=False):
                if row_type != "oa":
                    continue
                oa_id = row_id.strip()
                if not oa_id or oa_id in seen_ids:
                    continue
                seen_ids.add(oa_id)
                record = oa_records.get(oa_id)
                summaries.append(
                    {
                        "id": oa_id,
                        "applicant": record.applicant if record is not None else self._metadata_text(metadata, "oa_applicant", "applicant", "applicant_name") or "—",
                        "application_type": record.apply_type if record is not None else self._metadata_text(metadata, "application_type", "apply_type", "form_type"),
                        "project_name": (record.project_name_display or record.project_name) if record is not None else self._metadata_text(metadata, "project_name", "project", "projectName") or "",
                        "status": record.section if record is not None else self._metadata_text(metadata, "status", "flow_status", "section"),
                        "form_no": record.case_id or self._metadata_text(metadata, "form_no", "form_id", "oa_form_id") or "",
                        "detail_available": record is not None,
                        "relation_case_id": str(relation.get("case_id") or ""),
                    }
                )
        if not summaries:
            applicant = self._oa_applicant_from_relations(relations)
            if applicant != "—":
                summaries.append({"id": "", "applicant": applicant, "project_name": "", "form_no": "", "detail_available": False})
        return {
            "primary": summaries[0] if summaries else None,
            "relation_count": len(summaries),
            "has_multiple": len(summaries) > 1,
            "detail_available": any(bool(summary.get("detail_available")) for summary in summaries),
            "summaries": summaries,
        }

    @staticmethod
    def _oa_ids_from_relations(relations: list[dict[str, Any]]) -> list[str]:
        oa_ids: list[str] = []
        seen: set[str] = set()
        for relation in relations:
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            for row_id, row_type in zip(row_ids, row_types, strict=False):
                normalized = row_id.strip()
                if row_type == "oa" and normalized and normalized not in seen:
                    seen.add(normalized)
                    oa_ids.append(normalized)
        return oa_ids

    def _oa_records_by_id(self, oa_ids: list[str]) -> dict[str, OAApplicationRecord]:
        normalized_ids = [str(oa_id).strip() for oa_id in list(oa_ids or []) if str(oa_id).strip()]
        if not normalized_ids or self._oa_projection is None:
            return {}
        list_by_ids = getattr(self._oa_projection, "list_application_records_by_row_ids", None)
        records: list[Any]
        if callable(list_by_ids):
            records = list(list_by_ids(normalized_ids) or [])
        else:
            list_all = getattr(self._oa_projection, "list_all_application_records", None)
            records = list(list_all() or []) if callable(list_all) else []
        records_by_id = {
            record.id: record
            for record in records
            if isinstance(record, OAApplicationRecord)
        }
        return {
            oa_id: records_by_id[oa_id]
            for oa_id in normalized_ids
            if oa_id in records_by_id
        }

    @staticmethod
    def _first_relation_metadata(relation: dict[str, Any]) -> dict[str, Any]:
        merged: dict[str, Any] = {}
        for container_name in ("special_metadata", "evidence", "oa_exemption"):
            container = relation.get(container_name)
            if isinstance(container, dict):
                merged.update(container)
        return merged

    @staticmethod
    def _metadata_text(metadata: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = str(metadata.get(key) or "").strip()
            if value:
                return value
        return ""

    def _apply_filters(self, rows: list[dict[str, Any]], filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        filter_items = self._parse_filters(filters)
        if not filter_items:
            return rows
        return [row for row in rows if all(self._row_matches_filter_item(row, item) for item in filter_items)]

    @staticmethod
    def _parse_filters(filters: str | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if filters in (None, ""):
            return []
        if isinstance(filters, str):
            try:
                parsed = json.loads(filters)
            except json.JSONDecodeError as exc:
                raise PendingInvoiceError("invalid_filters", "filters must be a JSON array.") from exc
        else:
            parsed = filters
        if not isinstance(parsed, list):
            raise PendingInvoiceError("invalid_filters", "filters must be a JSON array.")
        result: list[dict[str, Any]] = []
        for item in parsed:
            if not isinstance(item, dict):
                raise PendingInvoiceError("invalid_filters", "Each filter must be an object.")
            field = str(item.get("field") or "").strip()
            operator = str(item.get("operator") or "").strip()
            if field not in PENDING_INVOICE_FILTER_FIELDS:
                raise PendingInvoiceError("invalid_filter_field", f"Unsupported filter field: {field}", details={"field": field})
            if operator not in PENDING_INVOICE_FILTER_FIELDS[field]:
                raise PendingInvoiceError(
                    "invalid_filter_operator",
                    f"Unsupported filter operator: {operator}",
                    details={"field": field, "operator": operator},
                )
            result.append({"field": field, "operator": operator, "value": item.get("value"), "values": item.get("values")})
        return result

    def _row_matches_filter_item(self, row: dict[str, Any], item: dict[str, Any]) -> bool:
        field = str(item["field"])
        operator = str(item["operator"])
        value = self._row_field_value(row, field)
        if operator == "contains":
            needle = str(item.get("value") or "").strip().lower()
            return not needle or needle in str(value or "").lower()
        if operator == "in":
            accepted = {str(candidate).strip().lower() for candidate in list(item.get("values") or []) if str(candidate).strip()}
            return not accepted or str(value or "").strip().lower() in accepted
        if operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            if field in {"amount", "invoice_total"}:
                parsed = _decimal_from_text(value)
                minimum = _decimal_or_none(bounds.get("min"))
                maximum = _decimal_or_none(bounds.get("max"))
                return (minimum is None or parsed >= minimum) and (maximum is None or parsed <= maximum)
            text_value = str(value or "")
            start = str(bounds.get("from") or "").strip()
            end = str(bounds.get("to") or "").strip()
            return (not start or text_value >= start) and (not end or text_value <= end)
        if operator == "eq":
            return _decimal_from_text(value) == _decimal_from_text(item.get("value"))
        return True

    def _apply_sort(
        self,
        rows: list[dict[str, Any]],
        *,
        sort_field: str | None,
        sort_direction: str | None,
    ) -> list[dict[str, Any]]:
        field = str(sort_field or "").strip()
        if not field:
            return rows
        if field not in PENDING_INVOICE_SORT_FIELDS:
            raise PendingInvoiceError("invalid_sort_field", f"Unsupported sort field: {field}", details={"field": field})
        direction = str(sort_direction or "asc").strip().lower() or "asc"
        if direction not in {"asc", "desc"}:
            raise PendingInvoiceError("invalid_sort_direction", "sort_direction must be asc or desc.")
        return sorted(rows, key=lambda row: self._sort_key(row, field), reverse=direction == "desc")

    def _sort_key(self, row: dict[str, Any], field: str) -> tuple[int, Any]:
        value = self._row_field_value(row, field)
        if field in {"amount", "invoice_total"}:
            return (0, _decimal_from_text(value))
        return (0, str(value or ""))

    @staticmethod
    def _row_field_value(row: dict[str, Any], field: str) -> Any:
        bank = row.get("bank_transaction") if isinstance(row.get("bank_transaction"), dict) else {}
        status = row.get("invoice_acquisition_status") if isinstance(row.get("invoice_acquisition_status"), dict) else {}
        invoices = row.get("input_invoices") if isinstance(row.get("input_invoices"), dict) else {}
        primary_invoice = invoices.get("primary") if isinstance(invoices.get("primary"), dict) else {}
        payment_summary = invoices.get("payment_summary") if isinstance(invoices.get("payment_summary"), dict) else {}
        oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        primary_oa = oa.get("primary") if isinstance(oa.get("primary"), dict) else {}
        mapping = {
            "trade_date": bank.get("trade_date") or str(bank.get("trade_time") or "")[:10],
            "bank_name": bank.get("bank_name"),
            "account_name": bank.get("account_name"),
            "counterparty_name": bank.get("counterparty_name"),
            "amount": bank.get("amount"),
            "summary_remark": " ".join(str(part or "") for part in (bank.get("summary"), bank.get("remark"))),
            "status_code": status.get("code"),
            "rule_group": (status.get("matched_rule") or {}).get("group") if isinstance(status.get("matched_rule"), dict) else None,
            "seller_name": primary_invoice.get("seller_name"),
            "invoice_total": payment_summary.get("invoice_total"),
            "oa_applicant": primary_oa.get("applicant") or row.get("oa_applicant"),
            "project_name": primary_oa.get("project_name"),
        }
        return mapping.get(field)

    def invoice_candidates(
        self,
        *,
        transaction_id: str,
        keyword: str | None = None,
        seller_name: str | None = None,
        issue_date_from: str | None = None,
        issue_date_to: str | None = None,
        amount_min: str | None = None,
        amount_max: str | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any]:
        transaction = self._get_transaction(transaction_id)
        if transaction.txn_direction != TransactionDirection.OUTFLOW:
            raise PendingInvoiceError("invalid_direction", "invoice candidates are only supported for expense rows.")
        field = str(sort_field or "").strip()
        if field and field not in INVOICE_CANDIDATE_SORT_FIELDS:
            raise PendingInvoiceError("invalid_sort_field", f"Unsupported candidate sort field: {field}", details={"field": field})
        direction = str(sort_direction or "asc").strip().lower() or "asc"
        if direction not in {"asc", "desc"}:
            raise PendingInvoiceError("invalid_sort_direction", "sort_direction must be asc or desc.")
        min_amount = _decimal_or_none(amount_min)
        max_amount = _decimal_or_none(amount_max)
        rows: list[dict[str, Any]] = []
        for invoice in self._import_service.list_invoices(invoice_type=InvoiceType.INPUT):
            invoice_total = self._invoice_total(invoice)
            if seller_name and str(seller_name).strip().lower() not in str(invoice.seller_name or "").lower():
                continue
            if issue_date_from and str(invoice.invoice_date or "") < str(issue_date_from):
                continue
            if issue_date_to and str(invoice.invoice_date or "") > str(issue_date_to):
                continue
            if min_amount is not None and invoice_total < min_amount:
                continue
            if max_amount is not None and invoice_total > max_amount:
                continue
            haystack = " ".join(str(part or "") for part in (invoice.invoice_no, invoice.digital_invoice_no, invoice.seller_name, invoice.remark)).lower()
            if keyword and str(keyword).strip().lower() not in haystack:
                continue
            paid_summary = self._payment_summary_for_relations([
                (relation, invoice)
                for relation in self._pair_relation_service.active_relations_for_row_ids([invoice.id])
                if invoice.id in {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            ])
            candidate_status = self._candidate_status(transaction.id, invoice.id)
            amount_difference = (invoice_total - transaction.amount).copy_abs()
            rows.append(
                {
                    "invoice_id": invoice.id,
                    "invoice_no": invoice.invoice_no,
                    "digital_invoice_no": invoice.digital_invoice_no,
                    "issue_date": invoice.invoice_date,
                    "seller_name": invoice.seller_name,
                    "seller_tax_no": invoice.seller_tax_no,
                    "buyer_name": invoice.buyer_name,
                    "total_with_tax": _decimal_to_str(invoice_total),
                    "paid_total": paid_summary["paid_total"],
                    "related_paid_total": paid_summary["paid_total"],
                    "remaining_amount": paid_summary["remaining_amount"],
                    "candidate_status": candidate_status,
                    "amount_difference_abs": _decimal_to_str(amount_difference),
                }
            )
        rows = self._sort_candidate_rows(rows, sort_field=field, sort_direction=direction)
        page_number = max(_optional_int(page, default=1), 1)
        page_limit = min(max(_optional_int(page_size, default=50), 1), 200)
        start = (page_number - 1) * page_limit
        return {
            "transaction_id": transaction.id,
            "rows": rows[start : start + page_limit],
            "pagination": {"page": page_number, "page_size": page_limit, "total": len(rows)},
        }

    def filter_options(
        self,
        *,
        direction: str,
        filter: str = "all",
        keyword: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload = self.list_rows(
            direction=direction,
            filter=filter,
            keyword=keyword,
            date_from=date_from,
            date_to=date_to,
            filters=filters,
            page=1,
            page_size=200,
        )
        rows = list(payload.get("rows") or [])
        fields = self._filter_option_fields()
        options: dict[str, list[dict[str, Any]]] = {}
        for field in PENDING_INVOICE_FILTER_FIELDS:
            counts: dict[str, int] = {}
            for row in rows:
                value = str(self._row_field_value(row, field) or "").strip()
                if value:
                    counts[value] = counts.get(value, 0) + 1
            options[field] = [
                {"value": value, "label": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:50]
            ]
        return {"direction": payload["direction"], "filter": payload["filter"], "fields": fields, "options": options}

    def filter_options_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        direction: str,
        filter: str,
    ) -> dict[str, Any]:
        fields = self._filter_option_fields()
        options: dict[str, list[dict[str, Any]]] = {}
        for field in PENDING_INVOICE_FILTER_FIELDS:
            counts: dict[str, int] = {}
            for row in rows:
                value = str(self._row_field_value(row, field) or "").strip()
                if value:
                    counts[value] = counts.get(value, 0) + 1
            options[field] = [
                {"value": value, "label": value, "count": count}
                for value, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))[:50]
            ]
        return {"direction": direction, "filter": filter, "fields": fields, "options": options}

    @staticmethod
    def _filter_option_fields() -> list[dict[str, Any]]:
        return [
            {"field": "trade_date", "label": "交易日期", "operators": ["between"]},
            {"field": "bank_name", "label": "银行", "operators": ["in", "contains"]},
            {"field": "account_name", "label": "账户", "operators": ["in", "contains"]},
            {"field": "counterparty_name", "label": "对方户名", "operators": ["contains", "in"]},
            {"field": "amount", "label": "金额", "operators": ["between", "eq"]},
            {"field": "summary_remark", "label": "摘要/备注", "operators": ["contains"]},
            {"field": "status_code", "label": "发票获取状态", "operators": ["in"]},
            {"field": "rule_group", "label": "规则组", "operators": ["in"]},
            {"field": "seller_name", "label": "销方", "operators": ["contains", "in"]},
            {"field": "invoice_total", "label": "发票金额", "operators": ["between", "eq"]},
            {"field": "oa_applicant", "label": "OA申请人", "operators": ["contains", "in"]},
            {"field": "project_name", "label": "项目", "operators": ["contains", "in"]},
        ]

    def relation_detail(self, *, transaction_id: str) -> dict[str, Any]:
        row = self.row_for_transaction(transaction_id, direction="expense")
        payment_summary = (
            row.get("input_invoices", {}).get("payment_summary")
            if isinstance(row.get("input_invoices"), dict)
            else {}
        )
        return {
            "transaction_summary": row.get("bank_transaction") or {},
            "related_invoices": list((row.get("input_invoices") or {}).get("summaries") or [])
            if isinstance(row.get("input_invoices"), dict)
            else list(row.get("invoices") or []),
            "invoice_summaries": list((row.get("input_invoices") or {}).get("summaries") or [])
            if isinstance(row.get("input_invoices"), dict)
            else list(row.get("invoices") or []),
            "payment_rows": self._payment_rows_for_transaction(transaction_id),
            "oa_summaries": list((row.get("oa") or {}).get("summaries") or []) if isinstance(row.get("oa"), dict) else [],
            "paid_total": payment_summary.get("paid_total", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "invoice_total": payment_summary.get("invoice_total", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "remaining_amount": payment_summary.get("remaining_amount", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "difference_amount": payment_summary.get("difference_amount", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "available_actions": ["attach_existing_invoice", "manual_invoice"],
            "relation_case_ids": list(row.get("relation_case_ids") or []),
        }

    def _payment_rows_for_transaction(self, transaction_id: str) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for relation in self._pair_relation_service.active_relations_for_row_ids([transaction_id]):
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            for row_id, row_type in zip(row_ids, row_types, strict=False):
                if row_type != "bank" or row_id in seen:
                    continue
                try:
                    transaction = self._import_service.get_transaction(row_id)
                except KeyError:
                    continue
                seen.add(row_id)
                rows.append(
                    {
                        "id": transaction.id,
                        "trade_time": transaction.trade_time or transaction.txn_date,
                        "counterparty_name": transaction.counterparty_name_raw,
                        "debit_amount": _decimal_to_str(transaction.amount),
                        "relation_case_id": str(relation.get("case_id") or ""),
                    }
                )
        return rows

    def bank_transaction_detail(self, bank_transaction_id: str) -> dict[str, Any]:
        transaction = self._get_transaction(bank_transaction_id)
        detail = {
            "id": transaction.id,
            "account_no": transaction.account_no,
            "counterparty_name": transaction.counterparty_name_raw,
            "counterparty_account_no": transaction.counterparty_account_no or "",
            "counterparty_bank_name": transaction.counterparty_bank_name or "",
            "trade_time": transaction.trade_time or "",
            "booked_date": transaction.booked_date or transaction.txn_date or "",
            "debit_amount": _decimal_to_str(transaction.amount if transaction.txn_direction == TransactionDirection.OUTFLOW else Decimal("0.00")),
            "credit_amount": _decimal_to_str(transaction.amount if transaction.txn_direction == TransactionDirection.INFLOW else Decimal("0.00")),
            "balance": _decimal_to_str(transaction.balance) if transaction.balance is not None else "",
            "currency": transaction.currency or "CNY",
            "bank_name": transaction.imported_bank_name or "",
            "account_name": transaction.account_name or "",
            "summary": transaction.summary or "",
            "remark": transaction.remark or "",
            "statement_serial_no": transaction.bank_serial_no or "",
            "enterprise_serial_no": transaction.enterprise_serial_no or "",
            "voucher_type": transaction.voucher_kind or "",
            "voucher_no": transaction.voucher_no or "",
        }
        return {
            "title": transaction.counterparty_name_raw or transaction.id,
            "subtitle": transaction.trade_time or transaction.txn_date or "",
            "detail_available": True,
            "sections": [{"title": "支出流水", "fields": _detail_fields(detail)}],
            "bank_transaction": detail,
        }

    def invoice_detail(self, invoice_id: str) -> dict[str, Any]:
        try:
            invoice = self._import_service.get_invoice(invoice_id)
        except KeyError as exc:
            raise PendingInvoiceError("invoice_not_found", f"Invoice detail not found: {invoice_id}", status_code=HTTPStatus.NOT_FOUND) from exc
        detail = self._invoice_payload(invoice, direction="expense")
        detail.update(
            {
                "invoice_code": invoice.invoice_code or "",
                "seller_tax_no": invoice.seller_tax_no or "",
                "buyer_tax_no": invoice.buyer_tax_no or "",
                "tax_amount": _decimal_to_str(invoice.tax_amount) if invoice.tax_amount is not None else "",
                "remark": invoice.remark or "",
            }
        )
        return {
            "title": detail.get("invoice_no") or detail.get("digital_invoice_no") or invoice.id,
            "subtitle": detail.get("seller_name") or "",
            "detail_available": True,
            "sections": [{"title": "进项发票", "fields": _detail_fields(detail)}],
            "invoice": detail,
        }

    def oa_detail(self, oa_id: str) -> dict[str, Any]:
        normalized_oa_id = str(oa_id or "").strip()
        active_relations = self._pair_relation_service.active_relations_for_row_ids([normalized_oa_id])
        records = self._oa_records_by_id([normalized_oa_id])
        record = records.get(normalized_oa_id)
        if record is not None:
            relation_case_id = str((active_relations[0] if active_relations else {}).get("case_id") or "")
            return self._oa_detail_from_record(record, relation_case_id=relation_case_id)
        for relation in active_relations:
            metadata = self._first_relation_metadata(relation)
            return {
                "title": normalized_oa_id,
                "subtitle": self._metadata_text(metadata, "project_name", "project", "projectName"),
                "oa_id": normalized_oa_id,
                "detail_available": False,
                "unavailable_reason": "OA 投影尚未同步，不能展示完整支付申请。",
                "relation_case_id": str(relation.get("case_id") or ""),
                "detail_fields": metadata,
                "sections": [],
            }
        return {
            "title": normalized_oa_id,
            "oa_id": normalized_oa_id,
            "detail_available": False,
            "unavailable_reason": "OA 投影尚未同步，不能展示完整支付申请。",
            "reason": "OA detail projection is unavailable.",
        }

    def _oa_detail_from_record(self, record: OAApplicationRecord, *, relation_case_id: str) -> dict[str, Any]:
        detail = {
            "oa_id": record.id,
            "applicant": record.applicant,
            "application_type": record.apply_type,
            "project_name": record.project_name_display or record.project_name,
            "workflow_no": record.case_id or "",
            "status": record.section,
            "amount": _decimal_to_str(_decimal_from_text(record.amount)),
            "month": record.month,
            "counterparty_name": record.counterparty_name,
            "reason": record.reason,
            "expense_type": record.expense_type or "",
            "expense_content": record.expense_content or record.reason,
            **{str(key): value for key, value in dict(record.detail_fields or {}).items() if value not in (None, "")},
        }
        return {
            "title": "打印选择",
            "subtitle": record.apply_type or "OA详情",
            "oa_id": record.id,
            "detail_available": True,
            "relation_case_id": relation_case_id,
            "detail_fields": detail,
            "oa_print_layout": self._oa_print_layout(record),
            "sections": [{"title": "OA 原始字段", "fields": _detail_fields(detail)}],
        }

    def _oa_print_layout(self, record: OAApplicationRecord) -> dict[str, Any]:
        detail_fields = dict(record.detail_fields or {})
        application_date = self._detail_text(detail_fields, "申请日期", "applicationDate", "ApplicationDate")
        payment_method = self._detail_text(detail_fields, "付款方式", "支付方式", "paymentMethod")
        invoice_kind = self._detail_text(detail_fields, "票据类型", "发票种类", "paymentProof")
        bank_name = self._detail_text(detail_fields, "开户行", "bank")
        payee_account = self._detail_text(detail_fields, "收款账号", "开户行账号", "payeeAccount")
        expense_type = record.expense_type or self._detail_text(detail_fields, "费用类型", "申请类型", "expenseType")
        amount_text = _decimal_to_str(_decimal_from_text(record.amount))
        fields = [
            {"label": "申请人", "value": record.applicant},
            {"label": "申请日期", "value": application_date},
            {"label": "申请类型", "value": expense_type},
            {"label": "支付方式", "value": payment_method},
            {"label": "发票种类", "value": invoice_kind},
            {"label": "项目名称", "value": record.project_name_display or record.project_name},
            {"label": "金额", "value": f"¥ {amount_text}元（大写：{_uppercase_rmb_without_currency(amount_text)}）"},
            {"label": "收款方", "value": record.counterparty_name},
            {"label": "开户行", "value": bank_name},
            {"label": "开户行账号", "value": payee_account},
            {"label": "申请事由", "value": record.reason},
            {"label": "电子签名", "value": self._detail_text(detail_fields, "电子签名", "signature") or record.applicant},
        ]
        return {
            "form_title": record.apply_type or "OA详情",
            "download_label": "打印下载",
            "fields": fields,
            "approvals": self._oa_approval_steps(record, application_date=application_date),
        }

    def _oa_approval_steps(self, record: OAApplicationRecord, *, application_date: str) -> list[dict[str, Any]]:
        detail_fields = dict(record.detail_fields or {})
        submitted_at = self._detail_text(detail_fields, "提交时间", "发起时间", "申请提交时间") or application_date
        steps = [
            {
                "title": record.apply_type or "支付申请",
                "lines": [line for line in (f"{record.applicant}发起流程申请", submitted_at, record.applicant) if line],
                "signature": record.applicant,
            }
        ]
        approval_rows = detail_fields.get("审批记录") or detail_fields.get("审批意见及评论") or detail_fields.get("approval_records")
        if isinstance(approval_rows, list):
            for row in approval_rows:
                if not isinstance(row, dict):
                    continue
                title = self._detail_text(row, "title", "节点", "步骤", "name") or "审批"
                opinion = self._detail_text(row, "opinion", "意见", "审批意见", "comment")
                acted_at = self._detail_text(row, "acted_at", "审批时间", "time", "created_at")
                actor = self._detail_text(row, "actor", "审批人", "user", "name")
                signature = self._detail_text(row, "signature", "签名") or actor
                steps.append(
                    {
                        "title": title,
                        "lines": [line for line in (opinion, acted_at, actor) if line],
                        "signature": signature,
                    }
                )
        return steps

    @staticmethod
    def _detail_text(values: dict[str, Any], *keys: str) -> str:
        for key in keys:
            value = values.get(key)
            if isinstance(value, (list, dict)):
                continue
            text = str(value or "").strip()
            if text:
                return text
        return ""

    def export_preview(self, **kwargs: Any) -> dict[str, Any]:
        rows = self._all_rows_for_export(**kwargs)
        return self.export_preview_for_rows(rows=rows, filters={key: value for key, value in kwargs.items() if value not in (None, "")})

    def export_preview_for_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        filters: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "file_name": f"待找发票-{datetime.now(UTC).date().isoformat()}.xlsx",
            "row_count": len(rows),
            "scope_label": "当前筛选",
            "columns": _pending_invoice_export_columns(),
            "sample_rows": [self._export_row(index, row) for index, row in enumerate(rows[:20], start=1)],
            "rows": [self._export_row(index, row) for index, row in enumerate(rows[:20], start=1)],
            "pagination": {"preview_count": min(len(rows), 20), "total": len(rows), "limit": 20},
            "filters": dict(filters or {}),
        }

    def export(self, **kwargs: Any) -> tuple[str, bytes]:
        rows = self._all_rows_for_export(**kwargs)
        return self.export_for_rows(rows=rows)

    def export_for_rows(self, *, rows: list[dict[str, Any]]) -> tuple[str, bytes]:
        from io import BytesIO

        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font

        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "待找发票"
        columns = _pending_invoice_export_columns()
        sheet.append(columns)
        for cell in sheet[1]:
            cell.font = Font(bold=True)
            cell.alignment = Alignment(horizontal="center")
        for index, row in enumerate(rows, start=1):
            export_row = self._export_row(index, row)
            sheet.append([export_row.get(column, "") for column in columns])
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            sheet.column_dimensions[column_cells[0].column_letter].width = min(max(max_length + 2, 12), 32)
        buffer = BytesIO()
        workbook.save(buffer)
        filename = f"待找发票-{datetime.now(UTC).date().isoformat()}.xlsx"
        return filename, buffer.getvalue()

    def _all_rows_for_export(self, **kwargs: Any) -> list[dict[str, Any]]:
        payload = self.list_rows(
            direction=str(kwargs.get("direction") or "expense"),
            filter=str(kwargs.get("filter") or "all"),
            date_from=kwargs.get("date_from"),
            date_to=kwargs.get("date_to"),
            keyword=kwargs.get("keyword"),
            filters=kwargs.get("filters"),
            sort_field=kwargs.get("sort_field"),
            sort_direction=kwargs.get("sort_direction"),
            page=1,
            page_size=200,
        )
        total = int((payload.get("pagination") or {}).get("total") or len(payload.get("rows") or []))
        rows = list(payload.get("rows") or [])
        page = 2
        while len(rows) < total:
            next_payload = self.list_rows(
                direction=str(kwargs.get("direction") or "expense"),
                filter=str(kwargs.get("filter") or "all"),
                date_from=kwargs.get("date_from"),
                date_to=kwargs.get("date_to"),
                keyword=kwargs.get("keyword"),
                filters=kwargs.get("filters"),
                sort_field=kwargs.get("sort_field"),
                sort_direction=kwargs.get("sort_direction"),
                page=page,
                page_size=200,
            )
            page_rows = list(next_payload.get("rows") or [])
            if not page_rows:
                break
            rows.extend(page_rows)
            page += 1
        return rows

    @staticmethod
    def _export_row(index: int, row: dict[str, Any]) -> dict[str, Any]:
        bank = row.get("bank_transaction") if isinstance(row.get("bank_transaction"), dict) else {}
        status = row.get("invoice_acquisition_status") if isinstance(row.get("invoice_acquisition_status"), dict) else {}
        invoices = row.get("input_invoices") if isinstance(row.get("input_invoices"), dict) else {}
        primary_invoice = invoices.get("primary") if isinstance(invoices.get("primary"), dict) else {}
        payment_summary = invoices.get("payment_summary") if isinstance(invoices.get("payment_summary"), dict) else {}
        oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        primary_oa = oa.get("primary") if isinstance(oa.get("primary"), dict) else {}
        return {
            "序号": index,
            "流水ID": row.get("id"),
            "交易日期": bank.get("trade_date") or str(bank.get("trade_time") or "")[:10],
            "对方户名": bank.get("counterparty_name"),
            "借方金额": bank.get("debit_amount"),
            "贷方金额": bank.get("credit_amount"),
            "银行": bank.get("bank_name"),
            "账号尾号": bank.get("account_last4"),
            "摘要": bank.get("summary"),
            "备注": bank.get("remark"),
            "状态": status.get("label"),
            "状态代码": status.get("code"),
            "发票号码": primary_invoice.get("invoice_no") or primary_invoice.get("digital_invoice_no"),
            "销方名称": primary_invoice.get("seller_name"),
            "价税合计": payment_summary.get("invoice_total") or primary_invoice.get("total_with_tax"),
            "已付合计": payment_summary.get("paid_total"),
            "剩余金额": payment_summary.get("remaining_amount"),
            "OA申请人": primary_oa.get("applicant") or row.get("oa_applicant"),
            "项目": primary_oa.get("project_name"),
        }

    def _candidate_status(self, transaction_id: str, invoice_id: str) -> str:
        expected = {transaction_id, invoice_id}
        for relation in self._pair_relation_service.active_relations_for_row_ids([invoice_id]):
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected.issubset(row_ids):
                return "already_related"
            if invoice_id in row_ids and not _relation_links_invoice_to_bank_payment(relation, invoice_id):
                return "conflict"
        return "available"

    @staticmethod
    def _sort_candidate_rows(
        rows: list[dict[str, Any]],
        *,
        sort_field: str,
        sort_direction: str,
    ) -> list[dict[str, Any]]:
        status_rank = {"available": 0, "already_related": 1, "conflict": 2}
        if not sort_field:
            return sorted(
                rows,
                key=lambda row: (
                    status_rank.get(str(row.get("candidate_status")), 99),
                    _decimal_from_text(row.get("amount_difference_abs")),
                    _reverse_date_key(row.get("issue_date")),
                    str(row.get("invoice_id") or ""),
                ),
            )
        reverse = sort_direction == "desc"
        if sort_field in {"total_with_tax", "amount_difference_abs"}:
            return sorted(rows, key=lambda row: _decimal_from_text(row.get(sort_field)), reverse=reverse)
        return sorted(rows, key=lambda row: str(row.get(sort_field) or ""), reverse=reverse)

    @staticmethod
    def _oa_applicant_from_relations(relations: list[dict[str, Any]]) -> str:
        for relation in relations:
            for container_name in ("special_metadata", "evidence", "oa_exemption"):
                container = relation.get(container_name)
                if not isinstance(container, dict):
                    continue
                for key in ("oa_applicant", "applicant", "applicant_name"):
                    value = str(container.get(key) or "").strip()
                    if value:
                        return value
        return "—"


class PendingInvoiceApplicationService:
    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        pair_relation_service: WorkbenchPairRelationService,
        command_store: dict[str, dict[str, Any]] | None = None,
        audit_recorder: Callable[[dict[str, Any]], None] | None = None,
        finalizer: Callable[[dict[str, Any]], None] | None = None,
        row_provider: Callable[[str, str], dict[str, Any]] | None = None,
        fault_injector: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._import_service = import_service
        self._pair_relation_service = pair_relation_service
        self._command_store = command_store if command_store is not None else {}
        self._audit_recorder = audit_recorder
        self._finalizer = finalizer
        self._row_provider = row_provider
        self._fault_injector = fault_injector
        self._previews: dict[str, dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._command_store)

    @property
    def command_store(self) -> dict[str, dict[str, Any]]:
        return self._command_store

    def preview_manual_invoice(self, payload: dict[str, Any]) -> dict[str, Any]:
        transaction = self._get_transaction(str(payload.get("bank_transaction_id") or ""))
        direction = self.direction_for_transaction(transaction)
        request_key = self.request_key_for_payload(payload, direction=direction)
        import_row = self.invoice_import_row(payload, request_key)
        preview = self._import_service.preview_import(
            batch_type=self.batch_type_for_direction(direction),
            source_name=MANUAL_INVOICE_SOURCE_NAME,
            imported_by=str(payload.get("actor_id") or payload.get("actor") or "pending_invoice_preview"),
            rows=[import_row],
        )
        row_result = preview.row_results[0]
        duplicate_status = "clear"
        if row_result.decision in (ImportDecision.DUPLICATE_SKIPPED, ImportDecision.SUSPECTED_DUPLICATE):
            duplicate_status = str(row_result.decision.value)
        elif row_result.decision == ImportDecision.ERROR:
            raise PendingInvoiceError(
                "invalid_invoice_payload",
                row_result.decision_reason or "Invalid invoice payload.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        preview_id = f"pending_invoice_preview_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:16]}"
        affected_months = self._affected_months_for_transaction(transaction)
        result = {
            "preview_id": preview_id,
            "request_key": request_key,
            "can_confirm": duplicate_status == "clear" or self._find_invoice_by_request_key(request_key) is not None,
            "target_invoice_type": "input" if direction == "expense" else "output",
            "bank_transaction_summary": {
                "id": transaction.id,
                "direction": direction,
                "counterparty_name": transaction.counterparty_name_raw,
                "trade_time": transaction.trade_time or transaction.txn_date,
                "amount": _decimal_to_str(transaction.amount),
            },
            "invoice_identity": {
                "source_unique_key": preview.normalized_rows[0].get("source_unique_key"),
                "data_fingerprint": preview.normalized_rows[0].get("data_fingerprint"),
            },
            "duplicate_check": {
                "status": duplicate_status,
                "matched_invoice_id": row_result.linked_object_id,
                "message": row_result.decision_reason or "",
            },
            "relation_impact": {
                "relation_mode": PENDING_INVOICE_RELATION_MODE,
                "affected_months": affected_months,
            },
            "warnings": [],
        }
        self._previews[preview_id] = {
            "request_key": request_key,
            "payload_fingerprint": self._payload_fingerprint(payload),
            "direction": direction,
        }
        return result

    def preview_attach_existing_invoice(self, *, transaction_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        transaction = self._get_transaction(transaction_id)
        direction = self.direction_for_transaction(transaction)
        if direction != "expense":
            raise PendingInvoiceError("invalid_direction", "Only expense rows can attach existing input invoices.")
        invoice = self._get_invoice(str(payload.get("invoice_id") or ""))
        if invoice.invoice_type != InvoiceType.INPUT:
            raise PendingInvoiceError("invalid_invoice_type", "Only input invoices can be attached to expense rows.")
        request_key = self.attach_existing_request_key(transaction_id=transaction.id, invoice_id=invoice.id)
        preview_id = f"pending_invoice_attach_preview_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:16]}"
        conflicts = self._attach_existing_conflicts(transaction_id=transaction.id, invoice_id=invoice.id)
        paid_total_before = self._paid_total_for_invoice(invoice.id)
        paid_total_after = paid_total_before + transaction.amount if not conflicts else paid_total_before
        invoice_total = _invoice_total(invoice)
        remaining_after = invoice_total - paid_total_after
        if remaining_after < Decimal("0.00"):
            remaining_after = Decimal("0.00")
        result = {
            "preview_id": preview_id,
            "request_key": request_key,
            "can_confirm": not conflicts,
            "transaction_summary": {
                "id": transaction.id,
                "counterparty_name": transaction.counterparty_name_raw,
                "trade_time": transaction.trade_time or transaction.txn_date,
                "debit_amount": _decimal_to_str(transaction.amount),
            },
            "invoice_summary": {
                "id": invoice.id,
                "invoice_no": invoice.invoice_no,
                "digital_invoice_no": invoice.digital_invoice_no,
                "issue_date": invoice.invoice_date,
                "seller_name": invoice.seller_name,
                "seller_tax_no": invoice.seller_tax_no,
                "total_with_tax": _decimal_to_str(invoice_total),
            },
            "payment_impact": {
                "paid_total_before": _decimal_to_str(paid_total_before),
                "paid_total_after": _decimal_to_str(paid_total_after),
                "invoice_total": _decimal_to_str(invoice_total),
                "remaining_amount_after": _decimal_to_str(remaining_after),
                "difference_amount_after": _decimal_to_str(invoice_total - paid_total_after),
            },
            "affected_months": self._affected_months_for_transaction(transaction),
            "warnings": [],
            "conflicts": conflicts,
            "expires_at": "",
        }
        self._previews[preview_id] = {
            "request_key": request_key,
            "transaction_id": transaction.id,
            "invoice_id": invoice.id,
            "direction": direction,
            "operation": "attach_existing_invoice",
        }
        return result

    def confirm_attach_existing_invoice(
        self,
        *,
        transaction_id: str,
        payload: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        preview_id = str(payload.get("preview_id") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()
        invoice_id = str(payload.get("invoice_id") or "").strip()
        if not preview_id or not request_id or not invoice_id:
            raise PendingInvoiceError("invalid_attach_existing_invoice_payload", "preview_id, invoice_id and request_id are required.")
        preview = self.preview_attach_existing_invoice(transaction_id=transaction_id, payload={"invoice_id": invoice_id})
        if preview["preview_id"] != preview_id:
            raise PendingInvoiceError("invalid_attach_existing_invoice_payload", "preview_id does not match the attach payload.")
        if not preview["can_confirm"]:
            raise PendingInvoiceError(
                "active_relation_conflict",
                "The invoice already has an active conflicting relation.",
                status_code=HTTPStatus.CONFLICT,
                details={"invoice_id": invoice_id, "conflicts": preview["conflicts"]},
            )
        request_key = str(preview["request_key"])
        command = self._command_store.get(request_id)
        if isinstance(command, dict) and command.get("status") == "completed":
            return deepcopy(command["result"])
        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "operation": "attach_existing_invoice",
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._command_store[request_id] = command
        elif command.get("request_key") != request_key:
            raise PendingInvoiceError(
                "invalid_attach_existing_invoice_payload",
                "request_id was already used for another attach-existing invoice payload.",
            )

        try:
            relation_case_id = str(command.get("relation_case_id") or "")
            if not relation_case_id:
                relation_case_id = self._create_attach_existing_relation(
                    transaction_id=transaction_id,
                    invoice_id=invoice_id,
                    request_key=request_key,
                    actor_id=actor_id,
                )
                command["invoice_id"] = invoice_id
                command["relation_case_id"] = relation_case_id
                self._mark_command(command, "relation_created")
                self._inject_fault("after_relation_created", command)
            affected_months = [str(month) for month in list(preview["affected_months"])]
            result = {
                "status": "completed",
                "request_id": request_id,
                "request_key": request_key,
                "transaction_id": transaction_id,
                "invoice_id": invoice_id,
                "relation_case_id": relation_case_id,
                "relation_mode": ATTACH_EXISTING_INVOICE_RELATION_MODE,
                "affected_transaction_ids": [transaction_id],
                "affected_invoice_ids": [invoice_id],
                "affected_months": affected_months,
            }
            if self._row_provider is not None:
                result["row"] = self._row_provider(transaction_id, "expense")
            self._record_attach_existing_audit(
                actor_id=actor_id,
                transaction_id=transaction_id,
                invoice_id=invoice_id,
                relation_case_id=relation_case_id,
                request_id=request_id,
                request_key=request_key,
                affected_months=affected_months,
            )
            self._finalize(
                {
                    "action": "pending_invoice_attach_existing_invoice_confirmed",
                    "source": "pending_invoice_attach_existing_invoice",
                    "entity_type": "pending_invoice_attach_existing_invoice",
                    "transaction_id": transaction_id,
                    "invoice_id": invoice_id,
                    "relation_case_id": relation_case_id,
                    "request_id": request_id,
                    "request_key": request_key,
                    "affected_months": affected_months,
                }
            )
            command["result"] = deepcopy(result)
            self._mark_command(command, "completed")
            return result
        except PendingInvoiceError:
            raise
        except Exception as exc:
            command["error"] = str(exc)
            command["last_successful_status"] = self._last_successful_status(command)
            self._mark_command(command, "failed_recoverable")
            raise

    def confirm_manual_invoice(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        preview_id = str(payload.get("preview_id") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()
        if not preview_id or not request_id:
            raise PendingInvoiceError("invalid_invoice_payload", "preview_id and request_id are required.")
        preview = self.preview_manual_invoice(payload)
        if preview["preview_id"] != preview_id:
            raise PendingInvoiceError("invalid_invoice_payload", "preview_id does not match the invoice payload.")
        request_key = str(preview["request_key"])
        direction = "expense" if preview["target_invoice_type"] == "input" else "income"
        transaction_id = str(payload.get("bank_transaction_id") or "").strip()
        affected_months = list(preview["relation_impact"]["affected_months"])
        command = self._command_store.get(request_id)
        if isinstance(command, dict) and command.get("status") == "completed":
            return deepcopy(command["result"])
        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._command_store[request_id] = command
        elif command.get("request_key") != request_key:
            raise PendingInvoiceError("invalid_invoice_payload", "request_id was already used for another invoice payload.")

        try:
            invoice_id = str(command.get("invoice_id") or "")
            if not invoice_id:
                orphan_invoice = self._find_invoice_by_request_key(request_key)
                if orphan_invoice is not None and not self._invoice_has_pending_relation(
                    orphan_invoice.id,
                    transaction_id=transaction_id,
                ):
                    invoice_id = orphan_invoice.id
                elif orphan_invoice is not None:
                    self._mark_command(command, "failed_terminal", error_code="duplicate_invoice")
                    raise PendingInvoiceError(
                        "duplicate_invoice",
                        "Invoice identity matched an existing pending invoice relation.",
                        status_code=HTTPStatus.CONFLICT,
                    )
                else:
                    if preview["duplicate_check"]["status"] != "clear":
                        self._mark_command(command, "failed_terminal", error_code="duplicate_invoice")
                        raise PendingInvoiceError(
                            "duplicate_invoice",
                            "Invoice identity matched an existing invoice.",
                            status_code=HTTPStatus.CONFLICT,
                        )
                    invoice_id = self._create_invoice(payload, request_key=request_key, direction=direction, actor_id=actor_id)
                command["invoice_id"] = invoice_id
                self._mark_command(command, "invoice_created")
                self._inject_fault("after_invoice_created", command)

            relation_case_id = str(command.get("relation_case_id") or "")
            if not relation_case_id:
                relation_case_id = self._create_relation(
                    transaction_id=transaction_id,
                    invoice_id=invoice_id,
                    request_key=request_key,
                    actor_id=actor_id,
                )
                command["relation_case_id"] = relation_case_id
                self._mark_command(command, "relation_created")
                self._inject_fault("after_relation_created", command)

            result = self._result_payload(
                transaction_id=transaction_id,
                invoice_id=invoice_id,
                relation_case_id=relation_case_id,
                affected_months=affected_months,
                direction=direction,
            )
            self._record_audit(
                actor_id=actor_id,
                transaction_id=transaction_id,
                invoice_id=invoice_id,
                relation_case_id=relation_case_id,
                request_id=request_id,
                request_key=request_key,
                affected_months=affected_months,
            )
            self._finalize(
                {
                    "transaction_id": transaction_id,
                    "invoice_id": invoice_id,
                    "relation_case_id": relation_case_id,
                    "request_id": request_id,
                    "request_key": request_key,
                    "affected_months": affected_months,
                }
            )
            command["result"] = deepcopy(result)
            self._mark_command(command, "completed")
            return result
        except PendingInvoiceError:
            raise
        except Exception as exc:
            command["error"] = str(exc)
            command["last_successful_status"] = self._last_successful_status(command)
            self._mark_command(command, "failed_recoverable")
            raise

    def batch_type_for_direction(self, direction: str) -> BatchType:
        return BatchType.INPUT_INVOICE if direction == "expense" else BatchType.OUTPUT_INVOICE

    def direction_for_transaction(self, transaction: BankTransaction) -> str:
        if transaction.txn_direction == TransactionDirection.OUTFLOW:
            return "expense"
        if transaction.txn_direction == TransactionDirection.INFLOW:
            return "income"
        raise PendingInvoiceError("invalid_direction", "Unsupported bank transaction direction.")

    def invoice_import_row(self, payload: dict[str, Any], request_key: str) -> dict[str, Any]:
        transaction = self._get_transaction(str(payload.get("bank_transaction_id") or ""))
        direction = self.direction_for_transaction(transaction)
        invoice_no = str(payload.get("invoice_no") or "").strip()
        digital_invoice_no = str(payload.get("digital_invoice_no") or "").strip()
        issue_date = str(payload.get("issue_date") or payload.get("invoice_date") or "").strip()
        total_with_tax = self._required_decimal(payload.get("total_with_tax"), "total_with_tax")
        seller_name = str(payload.get("seller_name") or "").strip()
        buyer_name = str(payload.get("buyer_name") or "").strip()
        if not (invoice_no or digital_invoice_no) or not issue_date:
            raise PendingInvoiceError("invalid_invoice_payload", "invoice_no or digital_invoice_no and issue_date are required.")
        if direction == "expense" and not seller_name:
            raise PendingInvoiceError("invalid_invoice_payload", "seller_name is required for expense manual invoices.")
        if direction == "income" and not buyer_name:
            raise PendingInvoiceError("invalid_invoice_payload", "buyer_name is required for income manual invoices.")
        tax_amount = self._optional_decimal(payload.get("tax_amount"))
        row = {
            "counterparty_name": seller_name if direction == "expense" else buyer_name,
            "invoice_code": str(payload.get("invoice_code") or "").strip(),
            "invoice_no": invoice_no,
            "digital_invoice_no": digital_invoice_no,
            "invoice_date": issue_date,
            "amount": _decimal_to_str(total_with_tax),
            "total_with_tax": _decimal_to_str(total_with_tax),
            "tax_amount": _decimal_to_str(tax_amount) if tax_amount is not None else None,
            "tax_rate": str(payload.get("tax_rate") or "").strip(),
            "seller_name": seller_name,
            "seller_tax_no": str(payload.get("seller_tax_no") or "").strip(),
            "buyer_name": buyer_name,
            "buyer_tax_no": str(payload.get("buyer_tax_no") or "").strip(),
            "remark": str(payload.get("remark") or "").strip(),
            "invoice_source": MANUAL_INVOICE_SOURCE_NAME,
            "pending_invoice_request_key": request_key,
            "pending_invoice_bank_transaction_id": transaction.id,
        }
        return {key: value for key, value in row.items() if value not in (None, "")}

    def request_key_for_payload(self, payload: dict[str, Any], *, direction: str) -> str:
        transaction_id = str(payload.get("bank_transaction_id") or "").strip()
        identity_payload = {
            "invoice_code": str(payload.get("invoice_code") or "").strip(),
            "invoice_no": str(payload.get("invoice_no") or "").strip(),
            "digital_invoice_no": str(payload.get("digital_invoice_no") or "").strip(),
            "issue_date": str(payload.get("issue_date") or payload.get("invoice_date") or "").strip(),
            "total_with_tax": _decimal_to_str(self._required_decimal(payload.get("total_with_tax"), "total_with_tax")),
            "seller_tax_no": str(payload.get("seller_tax_no") or "").strip(),
            "buyer_tax_no": str(payload.get("buyer_tax_no") or "").strip(),
            "seller_name": str(payload.get("seller_name") or "").strip(),
            "buyer_name": str(payload.get("buyer_name") or "").strip(),
        }
        digest = hashlib.sha1(str(sorted(identity_payload.items())).encode("utf-8")).hexdigest()[:20]
        return f"manual-pending-invoice:{transaction_id}:{direction}:{digest}"

    @staticmethod
    def attach_existing_request_key(*, transaction_id: str, invoice_id: str) -> str:
        return f"pending_invoice_attach_existing:{transaction_id}:{invoice_id}"

    def _get_transaction(self, transaction_id: str) -> BankTransaction:
        if not transaction_id:
            raise PendingInvoiceError("bank_transaction_not_found", "bank_transaction_id is required.", status_code=HTTPStatus.NOT_FOUND)
        try:
            return self._import_service.get_transaction(transaction_id)
        except KeyError as exc:
            raise PendingInvoiceError(
                "bank_transaction_not_found",
                f"Bank transaction not found: {transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            ) from exc

    def _get_invoice(self, invoice_id: str) -> Invoice:
        if not invoice_id:
            raise PendingInvoiceError("invoice_not_found", "invoice_id is required.", status_code=HTTPStatus.NOT_FOUND)
        try:
            return self._import_service.get_invoice(invoice_id)
        except KeyError as exc:
            raise PendingInvoiceError(
                "invoice_not_found",
                f"Invoice not found: {invoice_id}",
                status_code=HTTPStatus.NOT_FOUND,
            ) from exc

    def _create_invoice(self, payload: dict[str, Any], *, request_key: str, direction: str, actor_id: str) -> str:
        preview = self._import_service.preview_import(
            batch_type=self.batch_type_for_direction(direction),
            source_name=MANUAL_INVOICE_SOURCE_NAME,
            imported_by=actor_id,
            rows=[self.invoice_import_row(payload, request_key)],
        )
        row_result = preview.row_results[0]
        if row_result.decision in (ImportDecision.DUPLICATE_SKIPPED, ImportDecision.SUSPECTED_DUPLICATE):
            raise PendingInvoiceError("duplicate_invoice", "Invoice identity matched an existing invoice.", status_code=HTTPStatus.CONFLICT)
        if row_result.decision == ImportDecision.ERROR:
            raise PendingInvoiceError("invalid_invoice_payload", row_result.decision_reason or "Invalid invoice payload.")
        self._import_service.confirm_import(preview.id)
        linked_invoice_id = preview.row_results[0].linked_object_id
        if not linked_invoice_id:
            raise PendingInvoiceError("invalid_invoice_payload", "Invoice creation did not return an invoice id.")
        return str(linked_invoice_id)

    def _create_relation(self, *, transaction_id: str, invoice_id: str, request_key: str, actor_id: str) -> str:
        existing_relations = self._pair_relation_service.active_relations_for_row_ids([transaction_id, invoice_id])
        expected_rows = {transaction_id, invoice_id}
        for relation in existing_relations:
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected_rows.issubset(row_ids) and relation.get("relation_mode") == PENDING_INVOICE_RELATION_MODE:
                return str(relation.get("case_id"))
            if invoice_id in row_ids:
                raise PendingInvoiceError(
                    "relation_conflict",
                    "Invoice already has a conflicting active relation.",
                    status_code=HTTPStatus.CONFLICT,
                )
        case_id = self._relation_case_id(request_key)
        relation = self._pair_relation_service.create_active_relation(
            case_id=case_id,
            row_ids=[transaction_id, invoice_id],
            row_types=["bank", "invoice"],
            relation_mode=PENDING_INVOICE_RELATION_MODE,
            created_by=actor_id,
            special_metadata={
                "pending_invoice_request_key": request_key,
                "bank_transaction_id": transaction_id,
                "invoice_id": invoice_id,
            },
        )
        return str(relation["case_id"])

    def _create_attach_existing_relation(self, *, transaction_id: str, invoice_id: str, request_key: str, actor_id: str) -> str:
        expected_rows = {transaction_id, invoice_id}
        for relation in self._pair_relation_service.active_relations_for_row_ids([transaction_id, invoice_id]):
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected_rows.issubset(row_ids):
                return str(relation.get("case_id"))
            if invoice_id in row_ids and not _relation_links_invoice_to_bank_payment(relation, invoice_id):
                raise PendingInvoiceError(
                    "active_relation_conflict",
                    "The invoice already has an active conflicting relation.",
                    status_code=HTTPStatus.CONFLICT,
                    details={"invoice_id": invoice_id, "relation_case_id": str(relation.get("case_id") or "")},
                )
        case_id = f"case_attach_existing_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:20]}"
        relation = self._pair_relation_service.create_active_relation(
            case_id=case_id,
            row_ids=[transaction_id, invoice_id],
            row_types=["bank", "invoice"],
            relation_mode=ATTACH_EXISTING_INVOICE_RELATION_MODE,
            created_by=actor_id,
            special_metadata={
                "pending_invoice_request_key": request_key,
                "bank_transaction_id": transaction_id,
                "invoice_id": invoice_id,
                "source": "pending_invoice_attach_existing_invoice",
            },
        )
        return str(relation["case_id"])

    def _attach_existing_conflicts(self, *, transaction_id: str, invoice_id: str) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        expected_rows = {transaction_id, invoice_id}
        for relation in self._pair_relation_service.active_relations_for_row_ids([invoice_id]):
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected_rows.issubset(row_ids):
                continue
            if invoice_id in row_ids and not _relation_links_invoice_to_bank_payment(relation, invoice_id):
                conflicts.append(
                    {
                        "relation_case_id": str(relation.get("case_id") or ""),
                        "relation_mode": str(relation.get("relation_mode") or ""),
                        "row_ids": sorted(row_ids),
                    }
                )
        return conflicts

    def _paid_total_for_invoice(self, invoice_id: str) -> Decimal:
        transaction_ids: set[str] = set()
        for relation in self._pair_relation_service.active_relations_for_row_ids([invoice_id]):
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            for row_id, row_type in zip(row_ids, row_types, strict=False):
                if row_type == "bank":
                    transaction_ids.add(row_id)
        total = Decimal("0.00")
        for related_transaction_id in transaction_ids:
            try:
                total += self._import_service.get_transaction(related_transaction_id).amount
            except KeyError:
                continue
        return total.quantize(Decimal("0.01"))

    def _find_invoice_by_request_key(self, request_key: str) -> Invoice | None:
        for invoice in self._import_service.list_invoices():
            for link in list(getattr(invoice, "source_links", []) or []):
                if (
                    isinstance(link, dict)
                    and str(link.get("source_type") or "") == MANUAL_INVOICE_SOURCE_TYPE
                    and str(link.get("request_key") or "") == request_key
                ):
                    return invoice
        return None

    def _invoice_has_pending_relation(self, invoice_id: str, *, transaction_id: str) -> bool:
        expected_rows = {invoice_id, transaction_id}
        for relation in self._pair_relation_service.active_relations_for_row_ids([invoice_id, transaction_id]):
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected_rows.issubset(row_ids) and relation.get("relation_mode") == PENDING_INVOICE_RELATION_MODE:
                return True
        return False

    def _result_payload(
        self,
        *,
        transaction_id: str,
        invoice_id: str,
        relation_case_id: str,
        affected_months: list[str],
        direction: str,
    ) -> dict[str, Any]:
        result = {
            "invoice_id": invoice_id,
            "relation_case_id": relation_case_id,
            "affected_transaction_ids": [transaction_id],
            "affected_invoice_ids": [invoice_id],
            "affected_months": affected_months,
        }
        if self._row_provider is not None:
            result["row"] = self._row_provider(transaction_id, direction)
        return result

    def _record_audit(
        self,
        *,
        actor_id: str,
        transaction_id: str,
        invoice_id: str,
        relation_case_id: str,
        request_id: str,
        request_key: str,
        affected_months: list[str],
    ) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            {
                "actor_id": actor_id,
                "action": "pending_invoice_manual_invoice_confirmed",
                "transaction_id": transaction_id,
                "invoice_id": invoice_id,
                "relation_case_id": relation_case_id,
                "request_id": request_id,
                "request_key": request_key,
                "affected_months": list(affected_months),
            }
        )

    def _record_attach_existing_audit(
        self,
        *,
        actor_id: str,
        transaction_id: str,
        invoice_id: str,
        relation_case_id: str,
        request_id: str,
        request_key: str,
        affected_months: list[str],
    ) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            {
                "actor_id": actor_id,
                "action": "pending_invoice_attach_existing_invoice_confirmed",
                "source": "pending_invoice_attach_existing_invoice",
                "entity_type": "pending_invoice_attach_existing_invoice",
                "transaction_id": transaction_id,
                "invoice_id": invoice_id,
                "relation_case_id": relation_case_id,
                "request_id": request_id,
                "request_key": request_key,
                "affected_months": list(affected_months),
            }
        )

    def _finalize(self, event: dict[str, Any]) -> None:
        if self._finalizer is not None:
            self._finalizer(event)

    def _inject_fault(self, phase: str, command: dict[str, Any]) -> None:
        if self._fault_injector is not None:
            self._fault_injector(phase, command)

    @staticmethod
    def _mark_command(command: dict[str, Any], status: str, *, error_code: str | None = None) -> None:
        if status not in COMMAND_STATUSES:
            raise ValueError(f"unsupported pending invoice command status: {status}")
        command["status"] = status
        command["updated_at"] = _now()
        history = command.setdefault("status_history", [])
        if status not in history:
            history.append(status)
        if error_code:
            command["error_code"] = error_code

    @staticmethod
    def _last_successful_status(command: dict[str, Any]) -> str:
        for status in reversed(list(command.get("status_history") or [])):
            if status in {"relation_created", "invoice_created", "started"}:
                return status
        return "started"

    @staticmethod
    def _relation_case_id(request_key: str) -> str:
        return f"case_pending_invoice_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:20]}"

    @staticmethod
    def _payload_fingerprint(payload: dict[str, Any]) -> str:
        comparable = {key: value for key, value in payload.items() if key not in {"preview_id", "request_id"}}
        return hashlib.sha1(str(sorted(comparable.items())).encode("utf-8")).hexdigest()

    @staticmethod
    def _affected_months_for_transaction(transaction: BankTransaction) -> list[str]:
        month = str(transaction.trade_time or transaction.txn_date or "")[:7]
        return [month] if len(month) == 7 else []

    @staticmethod
    def _required_decimal(value: Any, field_name: str) -> Decimal:
        parsed = PendingInvoiceApplicationService._optional_decimal(value)
        if parsed is None:
            raise PendingInvoiceError("invalid_invoice_payload", f"{field_name} is required and must be a valid amount.")
        return parsed

    @staticmethod
    def _optional_decimal(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value)).quantize(Decimal("0.01"))
        except (InvalidOperation, ValueError) as exc:
            raise PendingInvoiceError("invalid_invoice_payload", "amount fields must be valid decimal values.") from exc


def _optional_int(value: int | str | None, *, default: int) -> int:
    try:
        return int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _decimal_or_none(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError) as exc:
        raise PendingInvoiceError("invalid_amount", "amount filters must be valid decimal values.") from exc


def _decimal_from_text(value: Any) -> Decimal:
    if value in (None, ""):
        return Decimal("0.00")
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _invoice_total(invoice: Invoice) -> Decimal:
    return Decimal(invoice.total_with_tax if invoice.total_with_tax is not None else invoice.amount).quantize(Decimal("0.01"))


def _relation_links_invoice_to_bank_payment(relation: dict[str, Any], invoice_id: str) -> bool:
    row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
    row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
    has_invoice = any(row_id == invoice_id and row_type == "invoice" for row_id, row_type in zip(row_ids, row_types, strict=False))
    has_bank = any(row_type == "bank" for row_type in row_types)
    return has_invoice and has_bank


def _decimal_to_str(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return str(Decimal(value).quantize(Decimal("0.01")))


def _uppercase_rmb_without_currency(value: Any) -> str:
    amount = abs(_decimal_from_text(value))
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
        sections: list[str] = []
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
    return f"{integer_upper}元{fraction_upper}"


def _reverse_date_key(value: Any) -> str:
    text_value = str(value or "")
    return "".join(chr(255 - ord(character)) for character in text_value)


def _pending_invoice_export_columns() -> list[str]:
    return [
        "序号",
        "流水ID",
        "交易日期",
        "对方户名",
        "借方金额",
        "贷方金额",
        "银行",
        "账号尾号",
        "摘要",
        "备注",
        "状态",
        "状态代码",
        "发票号码",
        "销方名称",
        "价税合计",
        "已付合计",
        "剩余金额",
        "OA申请人",
        "项目",
    ]


def _detail_fields(payload: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {"label": str(key), "value": "" if value is None else str(value)}
        for key, value in payload.items()
        if str(value or "").strip()
    ]


def _now() -> str:
    return datetime.now(UTC).isoformat()

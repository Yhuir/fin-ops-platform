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
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.pending_invoice_rules import (
    PENDING_INVOICE_CASH_INCOME_GROUP,
    PENDING_INVOICE_NO_INVOICE_GROUP,
    pending_invoice_effective_category_payload,
    pending_invoice_group_for_category,
    pending_invoice_tag_group_sets,
)
from fin_ops_platform.services.pending_invoice_status import (
    pending_invoice_available_actions,
    pending_invoice_status_payload,
)
from fin_ops_platform.services.pending_invoice_relation_identity import (
    infer_pending_invoice_relation_row_type,
    is_valid_pending_invoice_oa_row_id,
    pending_invoice_relation_identity,
)
from fin_ops_platform.services.read_model_write_targets import write_target_envelope
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_distribution_mapper import relation_dicts_from_distribution_payload
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


PENDING_INVOICE_RELATION_MODE = "pending_invoice_manual_invoice"
ATTACH_EXISTING_INVOICE_RELATION_MODE = "pending_invoice_attach_existing_invoice"
MANUAL_INVOICE_SOURCE_NAME = "pending_invoice_manual_entry"
MANUAL_INVOICE_SOURCE_TYPE = "manual_invoice_import"
EXPENSE_FILTERS = {"requires_invoice", "bank_statement_as_invoice", "no_invoice_required"}
INCOME_FILTERS = {"requires_invoice", "no_invoice_required", "cash_income"}
VALID_FILTERS = {"all", *EXPENSE_FILTERS, *INCOME_FILTERS}
PENDING_INVOICE_FILTER_FIELDS: dict[str, set[str]] = {
    "trade_date": {"between"},
    "bank_name": {"in", "contains"},
    "account_name": {"in", "contains"},
    "bank_account": {"in", "contains"},
    "counterparty_name": {"contains", "in"},
    "transaction_tag": {"contains", "in"},
    "direction": {"in"},
    "amount": {"between", "eq"},
    "summary_remark": {"contains"},
    "status_code": {"in"},
    "rule_group": {"in"},
    "seller_name": {"contains", "in"},
    "invoice_total": {"between", "eq"},
    "oa_applicant": {"contains", "in"},
    "oa_application_type": {"contains", "in"},
    "project_name": {"contains", "in"},
}
def _with_pending_invoice_write_targets(result: dict[str, Any]) -> dict[str, Any]:
    affected_months = result.get("affected_months")
    result.update(
        write_target_envelope(
            scope_keys=affected_months,
            targets=[],
        )
    )
    return result


INVOICE_CANDIDATE_SORT_FIELDS = {"issue_date", "total_with_tax", "seller_name", "amount_difference_abs"}
PENDING_INVOICE_EXPORT_ROW_LIMIT = 20000
BANK_RELATION_STATUS_UNLINKED = "unlinked"
BANK_RELATION_STATUS_LINKED = "linked"
BANK_RELATION_STATUS_ALREADY_SELECTED = "already_selected"
BANK_RELATION_STATUS_CONFLICT = "conflict"
COMMAND_STATUSES = {
    "started",
    "invoice_created",
    "relation_created",
    "completed",
    "failed_recoverable",
    "failed_terminal",
}
INCOME_STATUS_OVERRIDE_CODES = {
    "income_no_invoice_required",
    "cash_income",
}


def latest_income_status_override_from_commands(
    command_store: dict[str, dict[str, Any]] | None,
    transaction_id: str,
) -> dict[str, Any] | None:
    normalized_transaction_id = str(transaction_id or "").strip()
    latest: dict[str, Any] | None = None
    for command in dict(command_store or {}).values():
        if not isinstance(command, dict) or command.get("operation") != "income_status_override":
            continue
        if command.get("status") != "completed":
            continue
        overrides: list[dict[str, Any]] = []
        override = command.get("income_status_override")
        if isinstance(override, dict):
            overrides.append(override)
        batch_overrides = command.get("income_status_overrides")
        if isinstance(batch_overrides, list):
            overrides.extend(dict(item) for item in batch_overrides if isinstance(item, dict))
        for override_payload in overrides:
            if str(override_payload.get("transaction_id") or "") != normalized_transaction_id:
                continue
            if latest is None or str(override_payload.get("updated_at") or "") >= str(latest.get("updated_at") or ""):
                latest = dict(override_payload)
    return deepcopy(latest) if latest is not None else None


class InMemoryPendingInvoiceCommandRepository:
    def __init__(self, commands: dict[str, dict[str, Any]] | None = None) -> None:
        self._commands = commands if commands is not None else {}

    def get(self, request_id: str) -> dict[str, Any] | None:
        command = self._commands.get(str(request_id or "").strip())
        return command if isinstance(command, dict) else None

    def save(self, command: dict[str, Any]) -> None:
        request_id = str(command.get("request_id") or "").strip()
        if not request_id:
            raise PendingInvoiceError("invalid_command", "pending invoice command request_id is required.")
        self._commands[request_id] = command

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self._commands)

    def latest_income_status_override(self, transaction_id: str) -> dict[str, Any] | None:
        return latest_income_status_override_from_commands(self._commands, transaction_id)


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
        category_service: BankTransactionCategoryService,
        app_settings_provider: Callable[[], dict[str, Any]],
        effective_category_provider: Any | None = None,
        oa_projection: Any | None = None,
        income_status_override_provider: Callable[[str], dict[str, Any] | None] | None = None,
        relation_facade: Any | None = None,
        lifecycle_policy: Any | None = None,
    ) -> None:
        self._import_service = import_service
        self._category_service = category_service
        self._app_settings_provider = app_settings_provider
        self._effective_category_provider = effective_category_provider
        self._oa_projection = oa_projection
        self._income_status_override_provider = income_status_override_provider
        self._relation_facade = relation_facade
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy()

    def clear_cache(self) -> None:
        return None

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
            tag_groups=self._pending_invoice_tag_groups(direction=normalized_direction),
        )

    def normalize_row_payloads(
        self,
        rows: list[dict[str, Any]],
        *,
        settings_payload: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        bank_account_mappings = self._bank_account_mappings_by_last4(
            settings_payload=settings_payload,
        )
        return [self._normalize_row_payload(row, bank_account_mappings=bank_account_mappings) for row in rows]

    def _normalize_row_payload(
        self,
        row: dict[str, Any],
        *,
        bank_account_mappings: dict[str, dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        payload = deepcopy(row)
        bank = payload.get("bank_transaction")
        if isinstance(bank, dict):
            self._apply_bank_identity(bank, bank_account_mappings=bank_account_mappings)
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
        if normalized not in {"expense", "income", "all"}:
            raise PendingInvoiceError("invalid_direction", "direction must be expense, income or all.")
        return normalized

    @staticmethod
    def _normalize_filter(filter_name: str | None) -> str:
        normalized = str(filter_name or "all").strip() or "all"
        if normalized not in VALID_FILTERS:
            raise PendingInvoiceError("invalid_filter", "filter must be all or a supported pending invoice group.")
        return normalized

    @staticmethod
    def _transaction_matches_direction(transaction: BankTransaction, direction: str) -> bool:
        if direction == "all":
            return transaction.txn_direction in {TransactionDirection.OUTFLOW, TransactionDirection.INFLOW}
        expected = TransactionDirection.OUTFLOW if direction == "expense" else TransactionDirection.INFLOW
        return transaction.txn_direction == expected

    @staticmethod
    def direction_for_transaction(transaction: BankTransaction) -> str:
        if transaction.txn_direction == TransactionDirection.OUTFLOW:
            return "expense"
        if transaction.txn_direction == TransactionDirection.INFLOW:
            return "income"
        raise PendingInvoiceError("invalid_direction", "Unsupported bank transaction direction.")

    def _pending_invoice_tag_groups(self, *, direction: str) -> dict[str, set[str]]:
        return pending_invoice_tag_group_sets(self._app_settings_provider(), direction=direction)

    @staticmethod
    def _group_for_category(category_code: str | None, tag_groups: dict[str, set[str]], *, direction: str) -> str | None:
        return pending_invoice_group_for_category(category_code, tag_groups, direction=direction)

    def _bank_account_mappings_by_last4(
        self,
        *,
        settings_payload: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, str]]:
        settings = (
            settings_payload
            if isinstance(settings_payload, dict)
            else self._app_settings_provider()
        )
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

    def _apply_bank_identity(
        self,
        bank: dict[str, Any],
        *,
        bank_account_mappings: dict[str, dict[str, str]] | None = None,
    ) -> None:
        last4 = self._account_last4(bank.get("account_last4")) or self._account_last4(bank.get("account_no"))
        mappings = bank_account_mappings if bank_account_mappings is not None else self._bank_account_mappings_by_last4()
        mapping = mappings.get(last4)
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
        relation_row = self._relation_distribution_row(transaction.id, reason="pending_invoice_row_payload")
        invoices = self._invoice_payloads_from_distribution(relation_row, direction=direction) if relation_row is not None else []
        linked_invoices = [invoice for invoice in invoices if _distribution_item_is_linked(invoice)]
        effective_category = pending_invoice_effective_category_payload(category)
        category_code = effective_category.get("category_code")
        group = self._group_for_category(category_code, tag_groups, direction=direction)
        status_override = self._income_status_override(transaction.id) if direction == "income" else None
        can_create_invoice = (
            direction == "expense"
            and not linked_invoices
            and group != PENDING_INVOICE_NO_INVOICE_GROUP
        )
        payment_summary = (
            self._payment_summary_from_distribution(relation_row, linked_invoices)
            if relation_row is not None
            else self._empty_payment_summary(linked_invoices)
        )
        oa_summaries = self._oa_summaries_from_distribution(relation_row) if relation_row is not None else []
        oa_payload = self._oa_payload_from_summaries(oa_summaries)
        status_payload = self._lifecycle_policy.evaluate_pending_invoice_acquisition(
            direction=direction,
            group=group,
            has_invoices=bool(linked_invoices),
            payment_summary=payment_summary,
            matched_rule=self._matched_rule_payload(group=group, category=category),
            status_override=status_override,
        )
        available_actions = pending_invoice_available_actions(status_payload, can_create_invoice=can_create_invoice)
        input_invoices = {
            "primary": invoices[0] if invoices else None,
            "relation_count": len(invoices),
            "linked_relation_count": len(linked_invoices),
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
        bank_transaction = {
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
            "effective_tag_label": effective_category.get("category_label"),
            "effective_tag_primary_label": effective_category.get("category_primary_label"),
            "effective_tag_sub_label": effective_category.get("category_sub_label"),
            "effective_tag_label_path": list(effective_category.get("category_label_path") or []),
        }
        bank_transactions = self._bank_transactions_payload_from_distribution(
            relation_row,
            fallback=bank_transaction,
            direction=direction,
            paid_total=payment_summary.get("paid_total", "0.00") if isinstance(payment_summary, dict) else "0.00",
        )
        return {
            "id": transaction.id,
            "bank_transaction": bank_transaction,
            "bank_transactions": bank_transactions,
            "invoice_acquisition_status": status_payload,
            "input_invoices": input_invoices,
            "oa": oa_payload,
            "invoices": invoices,
            "oa_applicant": str((oa_payload.get("primary") or {}).get("applicant") or "—") if isinstance(oa_payload.get("primary"), dict) else "—",
            "can_create_invoice": can_create_invoice,
            "available_actions": available_actions,
            "relation_case_ids": self._invoice_relation_case_ids(invoices, relation_row),
        }

    @staticmethod
    def _multi_bank_relation_group_key(row: dict[str, Any]) -> str | None:
        bank_transactions = row.get("bank_transactions") if isinstance(row.get("bank_transactions"), dict) else {}
        summaries = list(bank_transactions.get("summaries") or []) if isinstance(bank_transactions, dict) else []
        if len(summaries) <= 1:
            return None
        for case_id in list(row.get("relation_case_ids") or []):
            normalized = str(case_id or "").strip()
            if normalized:
                return normalized
        return None

    def _payment_summary_for_relations(self, invoice_relations: list[tuple[dict[str, Any], Invoice]]) -> dict[str, Any]:
        invoice_ids = [invoice.id for _, invoice in invoice_relations]
        invoice_total = sum((self._invoice_total(invoice) for _, invoice in invoice_relations), start=Decimal("0.00"))
        paid_transaction_ids: set[str] = set()
        for invoice_id in invoice_ids:
            relation_row = self._relation_distribution_row(invoice_id, reason="pending_invoice_payment_summary")
            if relation_row is None:
                continue
            for item in list(relation_row.get("linked_bank_transactions") or []):
                if not isinstance(item, dict):
                    continue
                if not _distribution_item_is_linked(item):
                    continue
                transaction_id = str(item.get("id") or item.get("transaction_id") or "").strip()
                if transaction_id:
                    paid_transaction_ids.add(transaction_id)
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
    def _empty_payment_summary(invoices: list[dict[str, Any]]) -> dict[str, Any]:
        invoice_total = sum((_decimal_from_text(invoice.get("total_with_tax")) for invoice in invoices), start=Decimal("0.00"))
        return {
            "invoice_total": _decimal_to_str(invoice_total),
            "paid_total": "0.00",
            "remaining_amount": _decimal_to_str(invoice_total),
            "difference_amount": _decimal_to_str(invoice_total),
            "payment_transaction_count": 0,
        }

    def _relation_distribution_row(self, row_id: str, *, reason: str) -> dict[str, Any] | None:
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id or self._relation_facade is None:
            return None
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return None
        try:
            payload = reader([normalized_row_id], require_fresh=False, reason=reason)
        except TypeError:
            payload = reader([normalized_row_id])
        if not isinstance(payload, dict):
            return None
        groups_by_id = {
            str(group.get("group_id") or "").strip(): group
            for group in list(payload.get("groups") or [])
            if isinstance(group, dict) and str(group.get("group_id") or "").strip()
        }
        for row in list(payload.get("rows") or []):
            if isinstance(row, dict) and str(row.get("row_id") or "").strip() == normalized_row_id:
                group_ids = [str(group_id).strip() for group_id in list(row.get("group_ids") or []) if str(group_id).strip()]
                row = dict(row)
                row["_relation_groups"] = [groups_by_id[group_id] for group_id in group_ids if group_id in groups_by_id]
                return row
        return None

    @staticmethod
    def _relation_case_ids_from_distribution(row: dict[str, Any]) -> list[str]:
        relation_status = str(row.get("relation_status") or "linked").strip() or "linked"
        if relation_status != "linked":
            return []
        values: list[str] = []
        for value in list(row.get("group_ids") or []):
            text = str(value or "").strip()
            if text and text not in values:
                values.append(text)
        for key in ("linked_oa", "linked_bank_transactions", "linked_input_invoices", "linked_output_invoices"):
            for item in list(row.get(key) or []):
                if not isinstance(item, dict):
                    continue
                text = str(item.get("relation_case_id") or "").strip()
                if text and text not in values:
                    values.append(text)
        return values

    def _invoice_payloads_from_distribution(self, row: dict[str, Any], *, direction: str) -> list[dict[str, Any]]:
        key = "linked_input_invoices" if direction == "expense" else "linked_output_invoices"
        invoice_type = InvoiceType.INPUT if direction == "expense" else InvoiceType.OUTPUT
        payloads: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(row.get(key) or []):
            if not isinstance(item, dict):
                continue
            if not _distribution_item_is_linked(item):
                continue
            invoice_id = str(item.get("id") or item.get("invoice_id") or "").strip()
            if not invoice_id or invoice_id in seen:
                continue
            seen.add(invoice_id)
            try:
                invoice = self._import_service.get_invoice(invoice_id)
            except KeyError:
                invoice = None
            if invoice is not None:
                payload = self._invoice_payload(invoice, direction=direction)
            else:
                payload = {
                    "id": invoice_id,
                    "invoice_no": str(item.get("invoice_no") or ""),
                    "digital_invoice_no": str(item.get("digital_invoice_no") or ""),
                    "issue_date": str(item.get("issue_date") or item.get("invoice_date") or ""),
                    "total_with_tax": _decimal_to_str(_decimal_from_text(item.get("total_with_tax") or item.get("amount"))),
                    "seller_name": str(item.get("seller_name") or ""),
                    "buyer_name": str(item.get("buyer_name") or ""),
                    "invoice_type": "input" if invoice_type == InvoiceType.INPUT else "output",
                    "counterparty_display_name": str(
                        item.get("seller_name") if direction == "expense" else item.get("buyer_name") or ""
                    ),
                }
            relation_case_id = str(item.get("relation_case_id") or "").strip()
            if relation_case_id:
                payload["relation_case_id"] = relation_case_id
            relation_status = _distribution_item_relation_status(item)
            if relation_status:
                payload["relation_status"] = relation_status
            relation_source = str(item.get("relation_source") or item.get("relationSource") or "").strip()
            if relation_source:
                payload["relation_source"] = relation_source
            payloads.append(payload)
        return payloads

    @staticmethod
    def _oa_summaries_from_distribution(row: dict[str, Any]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(row.get("linked_oa") or []):
            if not isinstance(item, dict):
                continue
            if not _distribution_item_is_linked(item):
                continue
            oa_id = str(item.get("id") or item.get("oa_id") or "").strip()
            if not oa_id or oa_id in seen:
                continue
            seen.add(oa_id)
            summaries.append(
                {
                    "id": oa_id,
                    "applicant": str(item.get("applicant") or ""),
                    "application_type": str(item.get("application_type") or item.get("apply_type") or ""),
                    "project_name": str(item.get("project_name") or ""),
                    "status": str(item.get("status") or ""),
                    "form_no": str(item.get("form_no") or item.get("workflow_no") or ""),
                    "detail_available": bool(item.get("detail_available", True)),
                    "relation_case_id": str(item.get("relation_case_id") or ""),
                    "relation_status": _distribution_item_relation_status(item),
                    "relation_source": str(item.get("relation_source") or item.get("relationSource") or ""),
                }
            )
        if not summaries:
            for group in list(row.get("_relation_groups") or []):
                if not isinstance(group, dict) or not _distribution_group_is_linked(group):
                    continue
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
                metadata = payload.get("special_metadata") if isinstance(payload.get("special_metadata"), dict) else {}
                applicant = str(metadata.get("oa_applicant") or metadata.get("applicant") or metadata.get("applicant_name") or "").strip()
                if applicant:
                    summaries.append(
                        {
                            "id": "",
                            "applicant": applicant,
                            "application_type": str(metadata.get("application_type") or metadata.get("apply_type") or ""),
                            "project_name": str(metadata.get("project_name") or metadata.get("project") or ""),
                            "status": str(metadata.get("status") or ""),
                            "form_no": str(metadata.get("form_no") or ""),
                            "detail_available": False,
                            "relation_case_id": str(group.get("group_id") or ""),
                            "relation_status": _distribution_group_relation_status(group),
                            "relation_source": str(group.get("relation_source") or ""),
                        }
                    )
                    break
        return summaries

    def _payment_rows_from_distribution(self, row: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(row.get("linked_bank_transactions") or []):
            if not isinstance(item, dict):
                continue
            if not _distribution_item_is_linked(item):
                continue
            transaction_id = str(item.get("id") or item.get("transaction_id") or "").strip()
            if not transaction_id or transaction_id in seen:
                continue
            seen.add(transaction_id)
            try:
                transaction = self._import_service.get_transaction(transaction_id)
            except KeyError:
                transaction = None
            rows.append(
                {
                    "id": transaction_id,
                    "trade_time": (transaction.trade_time or transaction.txn_date) if transaction is not None else str(item.get("trade_time") or ""),
                    "counterparty_name": transaction.counterparty_name_raw if transaction is not None else str(item.get("counterparty_name") or ""),
                    "debit_amount": _decimal_to_str(transaction.amount) if transaction is not None else _decimal_to_str(_decimal_from_text(item.get("amount"))),
                    "relation_case_id": str(item.get("relation_case_id") or ""),
                    "relation_status": _distribution_item_relation_status(item),
                    "relation_source": str(item.get("relation_source") or item.get("relationSource") or ""),
                }
            )
        return rows

    def _bank_transactions_payload_from_distribution(
        self,
        row: dict[str, Any] | None,
        *,
        fallback: dict[str, Any],
        direction: str,
        paid_total: str,
    ) -> dict[str, Any]:
        summaries: list[dict[str, Any]] = []
        seen: set[str] = set()
        linked_count = 0
        if isinstance(row, dict):
            for item in list(row.get("linked_bank_transactions") or []):
                if not isinstance(item, dict):
                    continue
                if not _distribution_item_is_linked(item):
                    continue
                transaction_id = str(item.get("id") or item.get("transaction_id") or "").strip()
                if not transaction_id or transaction_id in seen:
                    continue
                seen.add(transaction_id)
                linked_count += 1
                try:
                    transaction = self._import_service.get_transaction(transaction_id)
                except KeyError:
                    transaction = None
                amount = transaction.amount if transaction is not None else _decimal_from_text(item.get("amount"))
                debit_amount = amount if direction == "expense" else Decimal("0.00")
                credit_amount = amount if direction == "income" else Decimal("0.00")
                summaries.append(
                    {
                        "id": transaction_id,
                        "trade_time": (transaction.trade_time or transaction.txn_date) if transaction is not None else str(item.get("trade_time") or ""),
                        "booked_date": (transaction.booked_date or transaction.txn_date or "") if transaction is not None else str(item.get("booked_date") or ""),
                        "counterparty_name": transaction.counterparty_name_raw if transaction is not None else str(item.get("counterparty_name") or ""),
                        "amount": _decimal_to_str(amount),
                        "debit_amount": _decimal_to_str(debit_amount),
                        "credit_amount": _decimal_to_str(credit_amount),
                        "bank_name": transaction.imported_bank_name if transaction is not None else str(item.get("bank_name") or ""),
                        "bank_short_name": transaction.imported_bank_name if transaction is not None else str(item.get("bank_short_name") or item.get("bank_name") or ""),
                        "account_last4": self._account_last4(transaction.imported_bank_last4 or transaction.account_no) if transaction is not None else self._account_last4(item.get("account_last4") or item.get("account_no")),
                        "summary": transaction.summary if transaction is not None else str(item.get("summary") or ""),
                        "remark": transaction.remark if transaction is not None else str(item.get("remark") or ""),
                        "relation_case_id": str(item.get("relation_case_id") or ""),
                        "relation_status": _distribution_item_relation_status(item),
                        "relation_source": str(item.get("relation_source") or item.get("relationSource") or ""),
                    }
                )
        if not summaries:
            summaries = [dict(fallback)]
            linked_count = 1
        return {
            "primary": summaries[0] if len(summaries) == 1 else None,
            "relation_count": len(summaries),
            "linked_relation_count": linked_count,
            "has_multiple": len(summaries) > 1,
            "detail_mode": "list" if len(summaries) > 1 else "single",
            "summaries": summaries,
            "payment_summary": {"paid_total": paid_total},
        }

    @staticmethod
    def _payment_summary_from_distribution(row: dict[str, Any], invoices: list[dict[str, Any]]) -> dict[str, Any]:
        invoice_total = sum((_decimal_from_text(invoice.get("total_with_tax")) for invoice in invoices), start=Decimal("0.00"))
        paid_transaction_ids: set[str] = set()
        paid_total = Decimal("0.00")
        for item in list(row.get("linked_bank_transactions") or []):
            if not isinstance(item, dict):
                continue
            if not _distribution_item_is_linked(item):
                continue
            transaction_id = str(item.get("id") or item.get("transaction_id") or "").strip()
            if transaction_id and transaction_id in paid_transaction_ids:
                continue
            if transaction_id:
                paid_transaction_ids.add(transaction_id)
            paid_total += _decimal_from_text(item.get("amount"))
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
        effective_category = pending_invoice_effective_category_payload(category)
        return {
            "group": group,
            "tag_code": effective_category.get("category_code"),
            "tag_label": effective_category.get("category_label"),
            "tag_primary_label": effective_category.get("category_primary_label"),
            "tag_sub_label": effective_category.get("category_sub_label"),
            "tag_label_path": list(effective_category.get("category_label_path") or []),
        }

    @staticmethod
    def _status_payload(
        *,
        direction: str,
        group: str | None,
        has_invoices: bool,
        payment_summary: dict[str, Any],
        matched_rule: dict[str, Any] | None,
        status_override: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return pending_invoice_status_payload(
            direction=direction,
            group=group,
            has_invoices=has_invoices,
            payment_summary=payment_summary,
            matched_rule=matched_rule,
            status_override=status_override,
        )

    def _income_status_override(self, transaction_id: str) -> dict[str, Any] | None:
        if self._income_status_override_provider is None:
            return None
        override = self._income_status_override_provider(transaction_id)
        return override if isinstance(override, dict) else None

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
        oa_ids = pending_invoice_relation_identity(relations).oa_row_ids
        oa_records = self._oa_records_by_id(oa_ids)
        for relation in relations:
            row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
            metadata = self._first_relation_metadata(relation)
            for index, row_id in enumerate(row_ids):
                row_type = row_types[index] if index < len(row_types) and row_types[index] else infer_pending_invoice_relation_row_type(row_id)
                if row_type != "oa":
                    continue
                oa_id = row_id.strip()
                if not is_valid_pending_invoice_oa_row_id(oa_id) or oa_id in seen_ids:
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
    def _oa_payload_from_summaries(summaries: list[dict[str, Any]]) -> dict[str, Any]:
        normalized = [dict(summary) for summary in list(summaries or []) if isinstance(summary, dict)]
        return {
            "primary": normalized[0] if normalized else None,
            "relation_count": len(normalized),
            "has_multiple": len(normalized) > 1,
            "detail_available": any(bool(summary.get("detail_available")) for summary in normalized),
            "summaries": normalized,
        }

    @staticmethod
    def _oa_ids_from_relations(relations: list[dict[str, Any]]) -> list[str]:
        return pending_invoice_relation_identity(relations).oa_row_ids

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

    @staticmethod
    def _row_field_value(row: dict[str, Any], field: str) -> Any:
        bank = row.get("bank_transaction") if isinstance(row.get("bank_transaction"), dict) else {}
        status = row.get("invoice_acquisition_status") if isinstance(row.get("invoice_acquisition_status"), dict) else {}
        invoices = row.get("input_invoices") if isinstance(row.get("input_invoices"), dict) else {}
        primary_invoice = invoices.get("primary") if isinstance(invoices.get("primary"), dict) else {}
        payment_summary = invoices.get("payment_summary") if isinstance(invoices.get("payment_summary"), dict) else {}
        oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        primary_oa = oa.get("primary") if isinstance(oa.get("primary"), dict) else {}
        tag_path = bank.get("effective_tag_label_path") if isinstance(bank.get("effective_tag_label_path"), list) else []
        transaction_tag = " / ".join(str(item).strip() for item in tag_path if str(item).strip()) or " / ".join(
            str(item or "").strip() for item in (bank.get("effective_tag_primary_label"), bank.get("effective_tag_sub_label")) if str(item or "").strip()
        ) or bank.get("effective_tag_label") or bank.get("effective_tag_code")
        bank_account = " ".join(
            str(item or "").strip()
            for item in (bank.get("bank_short_name") or bank.get("bank_name"), bank.get("account_last4"))
            if str(item or "").strip()
        )
        debit = _decimal_from_text(bank.get("debit_amount"))
        credit = _decimal_from_text(bank.get("credit_amount"))
        mapping = {
            "trade_date": bank.get("trade_date") or str(bank.get("trade_time") or "")[:10],
            "bank_name": bank.get("bank_name"),
            "account_name": bank.get("account_name"),
            "bank_account": bank_account,
            "counterparty_name": bank.get("counterparty_name"),
            "transaction_tag": transaction_tag,
            "direction": "income" if credit > 0 and debit <= 0 else "expense",
            "amount": bank.get("amount"),
            "summary_remark": " ".join(str(part or "") for part in (bank.get("summary"), bank.get("remark"))),
            "status_code": status.get("code"),
            "rule_group": (status.get("matched_rule") or {}).get("group") if isinstance(status.get("matched_rule"), dict) else None,
            "seller_name": primary_invoice.get("seller_name"),
            "invoice_total": payment_summary.get("invoice_total"),
            "oa_applicant": primary_oa.get("applicant") or row.get("oa_applicant"),
            "oa_application_type": primary_oa.get("application_type"),
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
            relation_row = self._relation_distribution_row(invoice.id, reason="pending_invoice_candidate_payment_summary")
            paid_summary = (
                self._payment_summary_from_distribution(relation_row, [self._invoice_payload(invoice, direction="expense")])
                if relation_row is not None
                else self._empty_payment_summary([self._invoice_payload(invoice, direction="expense")])
            )
            candidate_status = self._candidate_status(transaction.id, invoice.id)
            bank_relation = self._bank_relation_status_payload(
                relation_row,
                selected_transaction_ids=[transaction.id],
                candidate_status=candidate_status,
            )
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
                    **bank_relation,
                    "conflict_reason": "已有不兼容关系" if candidate_status == "conflict" else "",
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

    def invoice_candidates_batch(
        self,
        *,
        transaction_ids: list[str],
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
        normalized_transaction_ids = _normalize_id_list(transaction_ids, "transaction_ids")
        transactions = [self._get_transaction(transaction_id) for transaction_id in normalized_transaction_ids]
        if any(transaction.txn_direction != TransactionDirection.OUTFLOW for transaction in transactions):
            raise PendingInvoiceError("invalid_direction", "invoice candidates are only supported for expense rows.")
        selected_bank_total = sum((transaction.amount for transaction in transactions), Decimal("0.00")).quantize(Decimal("0.01"))
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
            relation_row = self._relation_distribution_row(invoice.id, reason="pending_invoice_batch_candidate_payment_summary")
            paid_summary = (
                self._payment_summary_from_distribution(relation_row, [self._invoice_payload(invoice, direction="expense")])
                if relation_row is not None
                else self._empty_payment_summary([self._invoice_payload(invoice, direction="expense")])
            )
            candidate_status = self._batch_candidate_status(normalized_transaction_ids, invoice.id)
            bank_relation = self._bank_relation_status_payload(
                relation_row,
                selected_transaction_ids=normalized_transaction_ids,
                candidate_status=candidate_status,
            )
            amount_difference = (invoice_total - selected_bank_total).copy_abs()
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
                    **bank_relation,
                    "conflict_reason": "已有不兼容关系" if candidate_status == "conflict" else "",
                    "amount_difference_abs": _decimal_to_str(amount_difference),
                }
            )
        rows = self._sort_candidate_rows(rows, sort_field=field, sort_direction=direction)
        page_number = max(_optional_int(page, default=1), 1)
        page_limit = min(max(_optional_int(page_size, default=50), 1), 200)
        start = (page_number - 1) * page_limit
        return {
            "transaction_ids": normalized_transaction_ids,
            "selection_summary": {
                "transaction_count": len(normalized_transaction_ids),
                "bank_total": _decimal_to_str(selected_bank_total),
            },
            "rows": rows[start : start + page_limit],
            "pagination": {"page": page_number, "page_size": page_limit, "total": len(rows)},
        }

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
            {"field": "bank_account", "label": "银行账户", "operators": ["in", "contains"]},
            {"field": "counterparty_name", "label": "对方户名", "operators": ["contains", "in"]},
            {"field": "transaction_tag", "label": "流水标签", "operators": ["contains", "in"]},
            {"field": "direction", "label": "收支", "operators": ["in"]},
            {"field": "amount", "label": "金额", "operators": ["between", "eq"]},
            {"field": "summary_remark", "label": "摘要/备注", "operators": ["contains"]},
            {"field": "status_code", "label": "发票获取状态", "operators": ["in"]},
            {"field": "rule_group", "label": "规则组", "operators": ["in"]},
            {"field": "seller_name", "label": "销方", "operators": ["contains", "in"]},
            {"field": "invoice_total", "label": "发票金额", "operators": ["between", "eq"]},
            {"field": "oa_applicant", "label": "OA申请人", "operators": ["contains", "in"]},
            {"field": "oa_application_type", "label": "OA类型", "operators": ["contains", "in"]},
            {"field": "project_name", "label": "项目", "operators": ["contains", "in"]},
        ]

    def relation_detail(self, *, transaction_id: str, direction: str = "expense", kind: str = "all") -> dict[str, Any]:
        normalized_direction = self._normalize_direction(direction)
        if normalized_direction == "all":
            normalized_direction = self.direction_for_transaction(self._get_transaction(transaction_id))
        row = self.row_for_transaction(transaction_id, direction=normalized_direction)
        payment_summary = (
            row.get("input_invoices", {}).get("payment_summary")
            if isinstance(row.get("input_invoices"), dict)
            else {}
        )
        payload = {
            "transaction_summary": row.get("bank_transaction") or {},
            "related_invoices": list((row.get("input_invoices") or {}).get("summaries") or [])
            if isinstance(row.get("input_invoices"), dict)
            else list(row.get("invoices") or []),
            "invoice_summaries": list((row.get("input_invoices") or {}).get("summaries") or [])
            if isinstance(row.get("input_invoices"), dict)
            else list(row.get("invoices") or []),
            "payment_rows": self._payment_rows_for_transaction(transaction_id),
            "oa_summaries": list((row.get("oa") or {}).get("summaries") or []) if isinstance(row.get("oa"), dict) else [],
            "related_oa": list((row.get("oa") or {}).get("summaries") or []) if isinstance(row.get("oa"), dict) else [],
            "paid_total": payment_summary.get("paid_total", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "invoice_total": payment_summary.get("invoice_total", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "remaining_amount": payment_summary.get("remaining_amount", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "difference_amount": payment_summary.get("difference_amount", "0.00") if isinstance(payment_summary, dict) else "0.00",
            "available_actions": [
                action
                for action in list(row.get("available_actions") or [])
                if action in {"attach_existing_invoice"}
            ],
            "relation_case_ids": list(row.get("relation_case_ids") or []),
        }
        relation_row = self._relation_distribution_row(transaction_id, reason="pending_invoice_relation_detail")
        if relation_row is None:
            return self._filter_relation_detail_payload(payload, kind=kind)
        invoices = self._invoice_payloads_from_distribution(relation_row, direction=normalized_direction)
        oa_summaries = self._oa_summaries_from_distribution(relation_row)
        payment_summary = self._payment_summary_from_distribution(relation_row, invoices)
        payment_rows = self._payment_rows_from_distribution(relation_row)
        payload.update(
            {
                "related_invoices": invoices,
                "invoice_summaries": invoices,
                "payment_rows": payment_rows,
                "related_oa": oa_summaries,
                "oa_summaries": oa_summaries,
                "paid_total": payment_summary["paid_total"],
                "invoice_total": payment_summary["invoice_total"],
                "remaining_amount": payment_summary["remaining_amount"],
                "difference_amount": payment_summary["difference_amount"],
                "relation_case_ids": self._invoice_relation_case_ids(invoices, relation_row),
            }
        )
        return self._filter_relation_detail_payload(payload, kind=kind)

    @staticmethod
    def _filter_relation_detail_payload(payload: dict[str, Any], *, kind: str) -> dict[str, Any]:
        normalized_kind = str(kind or "all").strip().lower() or "all"
        if normalized_kind == "all":
            return payload
        result = dict(payload)
        if normalized_kind != "invoice":
            result["related_invoices"] = []
            result["invoice_summaries"] = []
        if normalized_kind != "bank":
            result["payment_rows"] = []
        if normalized_kind != "oa":
            result["related_oa"] = []
            result["oa_summaries"] = []
        return result

    @staticmethod
    def _invoice_relation_case_ids(invoices: list[dict[str, Any]], relation_row: dict[str, Any] | None) -> list[str]:
        case_ids: list[str] = []
        for invoice in list(invoices or []):
            if not isinstance(invoice, dict):
                continue
            case_id = str(invoice.get("relation_case_id") or "").strip()
            if case_id and case_id not in case_ids:
                case_ids.append(case_id)
        if case_ids:
            return case_ids
        return PendingInvoiceQueryService._relation_case_ids_from_distribution(relation_row) if relation_row is not None else []

    def _payment_rows_for_transaction(self, transaction_id: str) -> list[dict[str, Any]]:
        relation_row = self._relation_distribution_row(transaction_id, reason="pending_invoice_payment_rows")
        return self._payment_rows_from_distribution(relation_row) if relation_row is not None else []

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
        if not is_valid_pending_invoice_oa_row_id(normalized_oa_id):
            raise PendingInvoiceError(
                "invalid_oa_detail_id",
                "OA detail requires a real OA row id.",
                status_code=HTTPStatus.BAD_REQUEST,
                details={"oa_id": normalized_oa_id},
            )
        relation_row = self._relation_distribution_row(normalized_oa_id, reason="pending_invoice_oa_detail")
        relation_case_ids = self._relation_case_ids_from_distribution(relation_row) if relation_row is not None else []
        records = self._oa_records_by_id([normalized_oa_id])
        record = records.get(normalized_oa_id)
        if record is not None:
            relation_case_id = relation_case_ids[0] if relation_case_ids else ""
            return self._oa_detail_from_record(record, relation_case_id=relation_case_id)
        if relation_row is not None:
            summaries = self._oa_summaries_from_distribution(relation_row)
            metadata = summaries[0] if summaries else {}
            return {
                "title": normalized_oa_id,
                "subtitle": self._metadata_text(metadata, "project_name"),
                "oa_id": normalized_oa_id,
                "detail_available": False,
                "unavailable_reason": "OA 投影尚未同步，不能展示完整支付申请。",
                "relation_case_id": relation_case_ids[0] if relation_case_ids else "",
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
            "oa": {
                "id": record.id,
                "applicant": record.applicant,
                "application_type": record.apply_type,
                "project_name": record.project_name_display or record.project_name,
                "relation_case_id": relation_case_id,
                "detail_available": True,
            },
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
        relation_row = self._relation_distribution_row(invoice_id, reason="pending_invoice_candidate_status")
        if relation_row is None:
            return "available"
        linked_bank_ids = {
            str(item.get("id") or item.get("transaction_id") or "").strip()
            for item in list(relation_row.get("linked_bank_transactions") or [])
            if isinstance(item, dict) and _distribution_item_is_linked(item)
        }
        if expected.issubset({invoice_id, *linked_bank_ids}):
            return "already_related"
        if not linked_bank_ids and self._distribution_row_has_attach_existing_linkable_group(relation_row, invoice_id):
            return "available"
        return "available" if linked_bank_ids else ("conflict" if _linked_group_ids_from_distribution_row(relation_row) else "available")

    def _batch_candidate_status(self, transaction_ids: list[str], invoice_id: str) -> str:
        statuses = [self._candidate_status(transaction_id, invoice_id) for transaction_id in transaction_ids]
        if any(status == "conflict" for status in statuses):
            return "conflict"
        if statuses and all(status == "already_related" for status in statuses):
            return "already_related"
        return "available"

    @staticmethod
    def _linked_bank_transaction_ids_from_distribution_row(relation_row: dict[str, Any] | None) -> set[str]:
        if relation_row is None:
            return set()
        return {
            str(item.get("id") or item.get("transaction_id") or "").strip()
            for item in list(relation_row.get("linked_bank_transactions") or [])
            if isinstance(item, dict)
            and _distribution_item_is_linked(item)
            and str(item.get("id") or item.get("transaction_id") or "").strip()
        }

    @staticmethod
    def _distribution_row_has_attach_existing_linkable_group(relation_row: dict[str, Any] | None, invoice_id: str) -> bool:
        if relation_row is None:
            return False
        for group in list(relation_row.get("_relation_groups") or []):
            if not isinstance(group, dict) or not _distribution_group_is_linked(group):
                continue
            payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
            row_ids = [str(row_id).strip() for row_id in list(payload.get("row_ids") or []) if str(row_id).strip()]
            row_types = [
                str(row_type).strip()
                for row_type in list(payload.get("row_types") or [])
                if str(row_type).strip()
            ]
            if not row_ids:
                row_ids = [
                    *[str(row_id).strip() for row_id in list(group.get("bank_transaction_ids") or []) if str(row_id).strip()],
                    *[str(row_id).strip() for row_id in list(group.get("input_invoice_ids") or []) if str(row_id).strip()],
                    *[str(row_id).strip() for row_id in list(group.get("output_invoice_ids") or []) if str(row_id).strip()],
                    *[str(row_id).strip() for row_id in list(group.get("oa_row_ids") or []) if str(row_id).strip()],
                ]
            row_type_set = {row_type for row_type in row_types if row_type}
            if invoice_id in row_ids and "invoice" in row_type_set and row_type_set.issubset({"bank", "invoice", "oa"}):
                return True
        return False

    def _bank_relation_status_payload(
        self,
        relation_row: dict[str, Any] | None,
        *,
        selected_transaction_ids: list[str],
        candidate_status: str,
    ) -> dict[str, Any]:
        linked_bank_ids = self._linked_bank_transaction_ids_from_distribution_row(relation_row)
        selected_ids = {str(transaction_id).strip() for transaction_id in list(selected_transaction_ids or []) if str(transaction_id).strip()}
        if candidate_status == "conflict":
            status = BANK_RELATION_STATUS_CONFLICT
        elif selected_ids and selected_ids.issubset(linked_bank_ids):
            status = BANK_RELATION_STATUS_ALREADY_SELECTED
        elif linked_bank_ids:
            status = BANK_RELATION_STATUS_LINKED
        else:
            status = BANK_RELATION_STATUS_UNLINKED
        return {
            "bank_relation_status": status,
            "linked_bank_transaction_count": len(linked_bank_ids),
        }

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
        command_store: dict[str, dict[str, Any]] | None = None,
        command_repository: Any | None = None,
        audit_recorder: Callable[[dict[str, Any]], None] | None = None,
        row_provider: Callable[[str, str], dict[str, Any]] | None = None,
        relation_facade: Any | None = None,
        relation_command_service: Any | None = None,
        fault_injector: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        self._import_service = import_service
        self._relation_facade = relation_facade
        self._relation_command_service = relation_command_service
        self._command_repository = command_repository or InMemoryPendingInvoiceCommandRepository(command_store)
        self._audit_recorder = audit_recorder
        self._row_provider = row_provider
        self._fault_injector = fault_injector
        self._previews: dict[str, dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        snapshot = getattr(self._command_repository, "snapshot", None)
        return dict(snapshot() or {}) if callable(snapshot) else {}

    @property
    def command_store(self) -> dict[str, dict[str, Any]]:
        return self.snapshot()

    def _get_command(self, request_id: str) -> dict[str, Any] | None:
        get = getattr(self._command_repository, "get", None)
        if not callable(get):
            return None
        command = get(request_id)
        return command if isinstance(command, dict) else None

    def _save_command(self, command: dict[str, Any]) -> None:
        save = getattr(self._command_repository, "save", None)
        if not callable(save):
            raise PendingInvoiceError("pending_invoice_command_repository_unavailable", "Pending invoice command repository is not configured.")
        save(command)

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
        command = self._get_command(request_id)
        if isinstance(command, dict) and command.get("status") == "completed":
            return _with_pending_invoice_write_targets(deepcopy(command["result"]))
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
            self._save_command(command)
        elif command.get("request_key") != request_key:
            raise PendingInvoiceError(
                "invalid_attach_existing_invoice_payload",
                "request_id was already used for another attach-existing invoice payload.",
            )

        try:
            relation_case_id = str(command.get("relation_case_id") or "")
            if not relation_case_id:
                self._assert_relation_write_precondition(
                    row_ids=[transaction_id, invoice_id],
                    month_scope="all",
                )
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
            result = _with_pending_invoice_write_targets(result)
            command["result"] = deepcopy(result)
            self._mark_command(command, "completed")
            return result
        except PendingInvoiceError as exc:
            self._mark_relation_precondition_error(command, exc)
            raise
        except Exception as exc:
            command["error"] = str(exc)
            command["last_successful_status"] = self._last_successful_status(command)
            self._mark_command(command, "failed_recoverable")
            raise

    def preview_attach_existing_invoices(self, *, payload: dict[str, Any]) -> dict[str, Any]:
        transaction_ids = _normalize_id_list(payload.get("transaction_ids"), "transaction_ids")
        invoice_ids = _normalize_id_list(payload.get("invoice_ids"), "invoice_ids")
        transactions = [self._get_transaction(transaction_id) for transaction_id in transaction_ids]
        invoices = [self._get_invoice(invoice_id) for invoice_id in invoice_ids]
        if any(self.direction_for_transaction(transaction) != "expense" for transaction in transactions):
            raise PendingInvoiceError("invalid_direction", "Only expense rows can attach existing input invoices.")
        if any(invoice.invoice_type != InvoiceType.INPUT for invoice in invoices):
            raise PendingInvoiceError("invalid_invoice_type", "Only input invoices can be attached to expense rows.")
        request_key = self.attach_existing_batch_request_key(transaction_ids=transaction_ids, invoice_ids=invoice_ids)
        preview_id = f"pending_invoice_attach_batch_preview_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:16]}"
        conflicts = self._attach_existing_batch_conflicts(transaction_ids=transaction_ids, invoice_ids=invoice_ids)
        selected_bank_total = sum((transaction.amount for transaction in transactions), Decimal("0.00")).quantize(Decimal("0.01"))
        selected_invoice_total = sum((_invoice_total(invoice) for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        paid_total_before = sum((self._paid_total_for_invoice(invoice.id) for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        paid_total_after = paid_total_before + selected_bank_total if not conflicts else paid_total_before
        remaining_after = selected_invoice_total - paid_total_after
        if remaining_after < Decimal("0.00"):
            remaining_after = Decimal("0.00")
        affected_months = sorted(
            {
                month
                for transaction in transactions
                for month in self._affected_months_for_transaction(transaction)
            }
        )
        result = {
            "preview_id": preview_id,
            "request_key": request_key,
            "can_confirm": not conflicts,
            "transaction_summaries": [
                {
                    "id": transaction.id,
                    "counterparty_name": transaction.counterparty_name_raw,
                    "trade_time": transaction.trade_time or transaction.txn_date,
                    "debit_amount": _decimal_to_str(transaction.amount),
                }
                for transaction in transactions
            ],
            "invoice_summaries": [
                {
                    "id": invoice.id,
                    "invoice_no": invoice.invoice_no,
                    "digital_invoice_no": invoice.digital_invoice_no,
                    "issue_date": invoice.invoice_date,
                    "seller_name": invoice.seller_name,
                    "seller_tax_no": invoice.seller_tax_no,
                    "total_with_tax": _decimal_to_str(_invoice_total(invoice)),
                }
                for invoice in invoices
            ],
            "selection_summary": {
                "transaction_count": len(transaction_ids),
                "invoice_count": len(invoice_ids),
                "bank_total": _decimal_to_str(selected_bank_total),
                "invoice_total": _decimal_to_str(selected_invoice_total),
                "difference_amount": _decimal_to_str(selected_invoice_total - selected_bank_total),
            },
            "payment_impact": {
                "paid_total_before": _decimal_to_str(paid_total_before),
                "paid_total_after": _decimal_to_str(paid_total_after),
                "invoice_total": _decimal_to_str(selected_invoice_total),
                "remaining_amount_after": _decimal_to_str(remaining_after),
                "difference_amount_after": _decimal_to_str(selected_invoice_total - paid_total_after),
            },
            "affected_months": affected_months,
            "warnings": [],
            "conflicts": conflicts,
            "expires_at": "",
        }
        self._previews[preview_id] = {
            "request_key": request_key,
            "transaction_ids": list(transaction_ids),
            "invoice_ids": list(invoice_ids),
            "direction": "expense",
            "operation": "attach_existing_invoices",
        }
        return result

    def confirm_attach_existing_invoices(self, *, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        preview_id = str(payload.get("preview_id") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()
        transaction_ids = _normalize_id_list(payload.get("transaction_ids"), "transaction_ids")
        invoice_ids = _normalize_id_list(payload.get("invoice_ids"), "invoice_ids")
        if not preview_id or not request_id:
            raise PendingInvoiceError("invalid_attach_existing_invoice_payload", "preview_id and request_id are required.")
        preview = self.preview_attach_existing_invoices(payload={"transaction_ids": transaction_ids, "invoice_ids": invoice_ids})
        if preview["preview_id"] != preview_id:
            raise PendingInvoiceError("invalid_attach_existing_invoice_payload", "preview_id does not match the attach payload.")
        if not preview["can_confirm"]:
            raise PendingInvoiceError(
                "active_relation_conflict",
                "One or more invoices already have an active conflicting relation.",
                status_code=HTTPStatus.CONFLICT,
                details={"invoice_ids": invoice_ids, "conflicts": preview["conflicts"]},
            )
        request_key = str(preview["request_key"])
        command = self._get_command(request_id)
        if isinstance(command, dict) and command.get("status") == "completed":
            return _with_pending_invoice_write_targets(deepcopy(command["result"]))
        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "operation": "attach_existing_invoices",
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._save_command(command)
        elif command.get("request_key") != request_key:
            raise PendingInvoiceError(
                "invalid_attach_existing_invoice_payload",
                "request_id was already used for another attach-existing invoice payload.",
            )

        try:
            relation_case_id = str(command.get("relation_case_id") or "")
            if not relation_case_id:
                self._assert_relation_write_precondition(
                    row_ids=[*transaction_ids, *invoice_ids],
                    month_scope="all",
                )
                relation_case_id = self._create_attach_existing_batch_relation(
                    transaction_ids=transaction_ids,
                    invoice_ids=invoice_ids,
                    request_key=request_key,
                    actor_id=actor_id,
                )
                command["transaction_ids"] = list(transaction_ids)
                command["invoice_ids"] = list(invoice_ids)
                command["relation_case_id"] = relation_case_id
                self._mark_command(command, "relation_created")
                self._inject_fault("after_relation_created", command)
            affected_months = [str(month) for month in list(preview["affected_months"])]
            result = {
                "status": "completed",
                "request_id": request_id,
                "request_key": request_key,
                "transaction_ids": transaction_ids,
                "invoice_ids": invoice_ids,
                "relation_case_id": relation_case_id,
                "relation_mode": ATTACH_EXISTING_INVOICE_RELATION_MODE,
                "affected_transaction_ids": transaction_ids,
                "affected_invoice_ids": invoice_ids,
                "affected_months": affected_months,
            }
            self._record_attach_existing_batch_audit(
                actor_id=actor_id,
                transaction_ids=transaction_ids,
                invoice_ids=invoice_ids,
                relation_case_id=relation_case_id,
                request_id=request_id,
                request_key=request_key,
                affected_months=affected_months,
            )
            result = _with_pending_invoice_write_targets(result)
            command["result"] = deepcopy(result)
            self._mark_command(command, "completed")
            return result
        except PendingInvoiceError as exc:
            self._mark_relation_precondition_error(command, exc)
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
        command = self._get_command(request_id)
        if isinstance(command, dict) and command.get("status") == "completed":
            return _with_pending_invoice_write_targets(deepcopy(command["result"]))
        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._save_command(command)
        elif command.get("request_key") != request_key:
            raise PendingInvoiceError("invalid_invoice_payload", "request_id was already used for another invoice payload.")

        try:
            invoice_id = str(command.get("invoice_id") or "")
            relation_case_id = str(command.get("relation_case_id") or "")
            if not relation_case_id:
                self._assert_relation_write_precondition(
                    row_ids=[transaction_id],
                    month_scope=affected_months[0] if len(affected_months) == 1 else "all",
                )
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
            result = _with_pending_invoice_write_targets(result)
            self._record_audit(
                actor_id=actor_id,
                transaction_id=transaction_id,
                invoice_id=invoice_id,
                relation_case_id=relation_case_id,
                request_id=request_id,
                request_key=request_key,
                affected_months=affected_months,
            )
            command["result"] = deepcopy(result)
            self._mark_command(command, "completed")
            return result
        except PendingInvoiceError as exc:
            self._mark_relation_precondition_error(command, exc)
            raise
        except Exception as exc:
            command["error"] = str(exc)
            command["last_successful_status"] = self._last_successful_status(command)
            self._mark_command(command, "failed_recoverable")
            raise

    def confirm_income_status_override(
        self,
        *,
        transaction_id: str,
        payload: dict[str, Any],
        actor_id: str,
    ) -> dict[str, Any]:
        request_id = str(payload.get("request_id") or "").strip()
        status_code = str(payload.get("status_code") or payload.get("code") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not request_id or status_code not in INCOME_STATUS_OVERRIDE_CODES:
            raise PendingInvoiceError(
                "invalid_income_status_override_payload",
                "request_id and a supported status_code are required.",
            )
        transaction = self._get_transaction(transaction_id)
        if self.direction_for_transaction(transaction) != "income":
            raise PendingInvoiceError("invalid_direction", "Only income rows can be manually marked.")
        request_key = f"pending_invoice_income_status:{transaction.id}:{status_code}"
        command = self._get_command(request_id)
        if isinstance(command, dict):
            if command.get("request_key") != request_key:
                raise PendingInvoiceError(
                    "invalid_income_status_override_payload",
                    "request_id was already used for another income status payload.",
                )
            if command.get("status") == "completed":
                return _with_pending_invoice_write_targets(deepcopy(command["result"]))
        current_row = self._row_provider(transaction.id, "income") if self._row_provider is not None else None
        if isinstance(current_row, dict):
            if not _row_can_mark_income_status(current_row):
                raise PendingInvoiceError(
                    "income_status_not_available",
                    "Selected income rows cannot be manually marked in their current state.",
                    status_code=HTTPStatus.CONFLICT,
                )
            if _row_has_linked_invoice(current_row):
                raise PendingInvoiceError(
                    "income_invoice_already_linked",
                    "Income rows that already have output invoices cannot be manually marked.",
                    status_code=HTTPStatus.CONFLICT,
                )
        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "operation": "income_status_override",
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._save_command(command)
        affected_months = self._affected_months_for_transaction(transaction)
        override = {
            "transaction_id": transaction.id,
            "status_code": status_code,
            "reason": reason,
            "actor_id": actor_id,
            "updated_at": _now(),
        }
        command["income_status_override"] = override
        result = {
            "status": "completed",
            "request_id": request_id,
            "request_key": request_key,
            "transaction_id": transaction.id,
            "status_code": status_code,
            "affected_transaction_ids": [transaction.id],
            "affected_months": affected_months,
        }
        if self._row_provider is not None:
            result["row"] = self._row_provider(transaction.id, "income")
        result = _with_pending_invoice_write_targets(result)
        command["result"] = deepcopy(result)
        self._mark_command(command, "completed")
        self._record_income_status_override_audit(
            actor_id=actor_id,
            transaction_id=transaction.id,
            request_id=request_id,
            request_key=request_key,
            status_code=status_code,
            affected_months=affected_months,
        )
        return result

    def confirm_income_status_overrides(self, *, payload: dict[str, Any], actor_id: str) -> dict[str, Any]:
        request_id = str(payload.get("request_id") or "").strip()
        status_code = str(payload.get("status_code") or payload.get("code") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        if not request_id or status_code not in INCOME_STATUS_OVERRIDE_CODES:
            raise PendingInvoiceError(
                "invalid_income_status_override_payload",
                "request_id and a supported status_code are required.",
            )
        raw_transaction_ids = _raw_id_list(payload.get("transaction_ids"), "transaction_ids")
        seen_transaction_ids: set[str] = set()
        transaction_ids: list[str] = []
        for transaction_id in raw_transaction_ids:
            if transaction_id in seen_transaction_ids:
                raise PendingInvoiceError(
                    "duplicate_income_status_transactions",
                    "transaction_ids must not include duplicate rows.",
                )
            seen_transaction_ids.add(transaction_id)
            transaction_ids.append(transaction_id)
        if not transaction_ids:
            raise PendingInvoiceError("invalid_id_list", "transaction_ids must include at least one id.")

        request_key = self.income_status_batch_request_key(transaction_ids=transaction_ids, status_code=status_code)
        command = self._get_command(request_id)
        if isinstance(command, dict):
            if command.get("request_key") != request_key:
                raise PendingInvoiceError(
                    "invalid_income_status_override_payload",
                    "request_id was already used for another income status payload.",
                )
            if command.get("status") == "completed":
                return _with_pending_invoice_write_targets(deepcopy(command["result"]))

        transactions = [self._get_transaction(transaction_id) for transaction_id in transaction_ids]
        for transaction in transactions:
            if self.direction_for_transaction(transaction) != "income":
                raise PendingInvoiceError("invalid_direction", "Only income rows can be manually marked.")
            current_row = self._row_provider(transaction.id, "income") if self._row_provider is not None else None
            if isinstance(current_row, dict):
                if not _row_can_mark_income_status(current_row):
                    raise PendingInvoiceError(
                        "income_status_not_available",
                        "Selected income rows cannot be manually marked in their current state.",
                        status_code=HTTPStatus.CONFLICT,
                    )
                if _row_has_linked_invoice(current_row):
                    raise PendingInvoiceError(
                        "income_invoice_already_linked",
                        "Income rows that already have output invoices cannot be manually marked.",
                        status_code=HTTPStatus.CONFLICT,
                    )

        if not isinstance(command, dict):
            command = {
                "request_id": request_id,
                "request_key": request_key,
                "operation": "income_status_override",
                "status": "started",
                "status_history": ["started"],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._save_command(command)

        updated_at = _now()
        affected_months = sorted(
            {
                month
                for transaction in transactions
                for month in self._affected_months_for_transaction(transaction)
            }
        )
        overrides = [
            {
                "transaction_id": transaction.id,
                "status_code": status_code,
                "reason": reason,
                "actor_id": actor_id,
                "updated_at": updated_at,
            }
            for transaction in transactions
        ]
        command["transaction_ids"] = list(transaction_ids)
        command["income_status_overrides"] = deepcopy(overrides)
        result = {
            "status": "completed",
            "request_id": request_id,
            "request_key": request_key,
            "transaction_ids": list(transaction_ids),
            "status_code": status_code,
            "affected_transaction_ids": list(transaction_ids),
            "affected_months": affected_months,
        }
        if self._row_provider is not None:
            result["rows"] = [self._row_provider(transaction.id, "income") for transaction in transactions]
        result = _with_pending_invoice_write_targets(result)
        command["result"] = deepcopy(result)
        self._mark_command(command, "completed")
        self._record_income_status_override_batch_audit(
            actor_id=actor_id,
            transaction_ids=transaction_ids,
            request_id=request_id,
            request_key=request_key,
            status_code=status_code,
            affected_months=affected_months,
        )
        return result

    def latest_income_status_override(self, transaction_id: str) -> dict[str, Any] | None:
        latest = getattr(self._command_repository, "latest_income_status_override", None)
        return latest(transaction_id) if callable(latest) else latest_income_status_override_from_commands(self.snapshot(), transaction_id)

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

    @staticmethod
    def attach_existing_batch_request_key(*, transaction_ids: list[str], invoice_ids: list[str]) -> str:
        payload = {
            "transaction_ids": sorted(str(transaction_id).strip() for transaction_id in transaction_ids if str(transaction_id).strip()),
            "invoice_ids": sorted(str(invoice_id).strip() for invoice_id in invoice_ids if str(invoice_id).strip()),
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return f"pending_invoice_attach_existing_batch:{digest}"

    @staticmethod
    def income_status_batch_request_key(*, transaction_ids: list[str], status_code: str) -> str:
        payload = {
            "transaction_ids": sorted(str(transaction_id).strip() for transaction_id in transaction_ids if str(transaction_id).strip()),
            "status_code": str(status_code or "").strip(),
        }
        digest = hashlib.sha1(json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()[:24]
        return f"pending_invoice_income_status_batch:{digest}"

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

    def _confirm_relation_via_command_service(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        relation_mode: str,
        actor_id: str,
        request_key: str,
        special_metadata: dict[str, Any],
        before_relations: list[dict[str, Any]] | None = None,
        month_scope: str = "all",
    ) -> str:
        relation_command_service = self._require_relation_command_service()
        try:
            result = relation_command_service.confirm_relation(
                case_id=case_id,
                row_ids=list(row_ids),
                row_types=list(row_types),
                relation_mode=relation_mode,
                actor_id=actor_id,
                month_scope=month_scope,
                special_metadata=dict(special_metadata),
                idempotency_key=request_key,
                before_relations=list(before_relations or []),
                replace_existing=True,
                history_operation_type="confirm_link",
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc
        relation = result.get("relation") if isinstance(result, dict) else {}
        if not isinstance(relation, dict):
            return str(case_id)
        return str(relation.get("case_id") or case_id)

    def _assert_relation_write_precondition(self, *, row_ids: list[str], month_scope: str) -> None:
        relation_command_service = self._require_relation_command_service()
        preflight = getattr(relation_command_service, "assert_write_precondition", None)
        if not callable(preflight):
            return
        try:
            preflight(
                row_ids=[
                    str(row_id).strip()
                    for row_id in list(row_ids or [])
                    if str(row_id).strip()
                ],
                month_scope=month_scope,
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise PendingInvoiceError(
                "pending_invoice_relation_command_unavailable",
                "Pending invoice relation writes require WorkbenchRelationCommandService.",
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        return self._relation_command_service

    @staticmethod
    def _command_error(exc: WorkbenchRelationCommandError) -> PendingInvoiceError:
        if exc.error_code == "workbench_relation_read_model_not_fresh":
            return PendingInvoiceError(
                "pending_invoice_relation_read_model_not_fresh",
                "关联台关系读模型不是 fresh，请刷新后再处理。",
                status_code=HTTPStatus.CONFLICT,
                details=dict(exc.payload),
            )
        if exc.error_code == "workbench_relation_active_row_conflict":
            return PendingInvoiceError(
                "active_relation_conflict",
                "The invoice already has an active conflicting relation.",
                status_code=HTTPStatus.CONFLICT,
                details=dict(exc.payload),
            )
        return PendingInvoiceError(exc.error_code, exc.message, details=dict(exc.payload))

    def _create_relation(self, *, transaction_id: str, invoice_id: str, request_key: str, actor_id: str) -> str:
        existing_relations = self._active_relation_dicts_for_row_ids(
            [transaction_id, invoice_id],
            reason="pending_invoice_manual_invoice_confirm",
        )
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
            if transaction_id in row_ids:
                existing_row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
                existing_row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
                resolved_row_types = [
                    existing_row_types[index]
                    if index < len(existing_row_types) and existing_row_types[index]
                    else _row_type_for_relation_row_id(row_id)
                    for index, row_id in enumerate(existing_row_ids)
                ]
                metadata = dict(relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {})
                metadata.update(
                    {
                        "pending_invoice_request_key": request_key,
                        "bank_transaction_id": transaction_id,
                        "invoice_id": invoice_id,
                    }
                )
                return self._confirm_relation_via_command_service(
                    case_id=str(relation.get("case_id") or ""),
                    row_ids=[*existing_row_ids, invoice_id],
                    row_types=[*resolved_row_types, "invoice"],
                    relation_mode=str(relation.get("relation_mode") or PENDING_INVOICE_RELATION_MODE),
                    actor_id=actor_id,
                    request_key=request_key,
                    special_metadata=metadata,
                    before_relations=[relation],
                    month_scope=str(relation.get("month_scope") or "all"),
                )
        case_id = self._relation_case_id(request_key)
        return self._confirm_relation_via_command_service(
            case_id=case_id,
            row_ids=[transaction_id, invoice_id],
            row_types=["bank", "invoice"],
            relation_mode=PENDING_INVOICE_RELATION_MODE,
            actor_id=actor_id,
            request_key=request_key,
            special_metadata={
                "pending_invoice_request_key": request_key,
                "bank_transaction_id": transaction_id,
                "invoice_id": invoice_id,
            },
        )

    def _create_attach_existing_relation(self, *, transaction_id: str, invoice_id: str, request_key: str, actor_id: str) -> str:
        expected_rows = {transaction_id, invoice_id}
        for relation in self._active_relation_dicts_for_row_ids(
            [transaction_id, invoice_id],
            reason="pending_invoice_attach_existing_confirm",
        ):
            row_ids = {str(row_id) for row_id in list(relation.get("row_ids") or [])}
            if expected_rows.issubset(row_ids):
                return str(relation.get("case_id"))
            if invoice_id in row_ids and _relation_can_absorb_attach_existing_invoice(relation, invoice_id):
                existing_row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
                existing_row_types = [
                    str(row_type).strip()
                    for row_type in list(relation.get("row_types") or [])
                ]
                resolved_row_types = [
                    existing_row_types[index]
                    if index < len(existing_row_types) and existing_row_types[index]
                    else _row_type_for_relation_row_id(row_id)
                    for index, row_id in enumerate(existing_row_ids)
                ]
                metadata = dict(relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {})
                metadata.update(
                    {
                        "pending_invoice_request_key": request_key,
                        "bank_transaction_id": transaction_id,
                        "invoice_id": invoice_id,
                        "source": "pending_invoice_attach_existing_invoice",
                    }
                )
                return self._confirm_relation_via_command_service(
                    case_id=str(relation.get("case_id") or ""),
                    row_ids=[*existing_row_ids, transaction_id],
                    row_types=[*resolved_row_types, "bank"],
                    relation_mode=str(relation.get("relation_mode") or ATTACH_EXISTING_INVOICE_RELATION_MODE),
                    actor_id=actor_id,
                    request_key=request_key,
                    special_metadata=metadata,
                    before_relations=[relation],
                    month_scope=str(relation.get("month_scope") or "all"),
                )
            if invoice_id in row_ids:
                raise PendingInvoiceError(
                    "active_relation_conflict",
                    "The invoice already has an active conflicting relation.",
                    status_code=HTTPStatus.CONFLICT,
                    details={"invoice_id": invoice_id, "relation_case_id": str(relation.get("case_id") or "")},
                )
        case_id = f"case_attach_existing_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:20]}"
        return self._confirm_relation_via_command_service(
            case_id=case_id,
            row_ids=[transaction_id, invoice_id],
            row_types=["bank", "invoice"],
            relation_mode=ATTACH_EXISTING_INVOICE_RELATION_MODE,
            actor_id=actor_id,
            request_key=request_key,
            special_metadata={
                "pending_invoice_request_key": request_key,
                "bank_transaction_id": transaction_id,
                "invoice_id": invoice_id,
                "source": "pending_invoice_attach_existing_invoice",
            },
        )

    def _create_attach_existing_batch_relation(
        self,
        *,
        transaction_ids: list[str],
        invoice_ids: list[str],
        request_key: str,
        actor_id: str,
    ) -> str:
        expected_rows = set(transaction_ids) | set(invoice_ids)
        existing_relations = self._active_relation_dicts_for_row_ids(
            [*transaction_ids, *invoice_ids],
            reason="pending_invoice_attach_existing_batch_confirm",
        )
        for relation in existing_relations:
            relation_row_ids = {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}
            if expected_rows.issubset(relation_row_ids):
                return str(relation.get("case_id") or "")
            for invoice_id in invoice_ids:
                if invoice_id in relation_row_ids and not _relation_can_absorb_attach_existing_invoice(relation, invoice_id):
                    raise PendingInvoiceError(
                        "active_relation_conflict",
                        "One or more invoices already have an active conflicting relation.",
                        status_code=HTTPStatus.CONFLICT,
                        details={"invoice_id": invoice_id, "relation_case_id": str(relation.get("case_id") or "")},
                    )
        combined_row_ids: list[str] = []
        combined_row_types: list[str] = []
        for relation in existing_relations:
            relation_row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
            relation_row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
            for index, row_id in enumerate(relation_row_ids):
                if row_id in combined_row_ids:
                    continue
                combined_row_ids.append(row_id)
                combined_row_types.append(
                    relation_row_types[index]
                    if index < len(relation_row_types) and relation_row_types[index]
                    else _row_type_for_relation_row_id(row_id)
                )
        for transaction_id in transaction_ids:
            if transaction_id not in combined_row_ids:
                combined_row_ids.append(transaction_id)
                combined_row_types.append("bank")
        for invoice_id in invoice_ids:
            if invoice_id not in combined_row_ids:
                combined_row_ids.append(invoice_id)
                combined_row_types.append("invoice")
        case_id = f"case_attach_existing_batch_{hashlib.sha1(request_key.encode('utf-8')).hexdigest()[:20]}"
        return self._confirm_relation_via_command_service(
            case_id=case_id,
            row_ids=combined_row_ids,
            row_types=combined_row_types,
            relation_mode=ATTACH_EXISTING_INVOICE_RELATION_MODE,
            actor_id=actor_id,
            request_key=request_key,
            special_metadata={
                "pending_invoice_request_key": request_key,
                "bank_transaction_ids": list(transaction_ids),
                "invoice_ids": list(invoice_ids),
                "source": "pending_invoice_attach_existing_invoice_batch",
            },
            before_relations=existing_relations,
            month_scope="all",
        )

    def _active_relation_dicts_for_row_ids(self, row_ids: list[str], *, reason: str) -> list[dict[str, Any]]:
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not normalized_row_ids:
            return []
        if self._relation_facade is None:
            return []
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return []
        try:
            payload = reader(normalized_row_ids, require_fresh=False, reason=reason)
        except TypeError:
            payload = reader(normalized_row_ids)
        return [
            relation
            for relation in relation_dicts_from_distribution_payload(payload if isinstance(payload, dict) else {})
            if _relation_dict_is_linked(relation)
        ]

    def _attach_existing_conflicts(self, *, transaction_id: str, invoice_id: str) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        relation_row = self._relation_distribution_row(invoice_id, reason="pending_invoice_attach_existing_conflicts")
        if relation_row is not None:
            linked_bank_ids = {
                str(item.get("id") or item.get("transaction_id") or "").strip()
                for item in list(relation_row.get("linked_bank_transactions") or [])
                if isinstance(item, dict)
                and _distribution_item_is_linked(item)
                and str(item.get("id") or item.get("transaction_id") or "").strip()
            }
            if transaction_id in linked_bank_ids:
                return []
            saw_existing_linkable_group = False
            for group in list(relation_row.get("_relation_groups") or []):
                if not isinstance(group, dict):
                    continue
                if not _distribution_group_is_linked(group):
                    continue
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
                row_ids = [str(row_id).strip() for row_id in list(payload.get("row_ids") or []) if str(row_id).strip()]
                if invoice_id not in row_ids:
                    row_ids = [
                        *[str(row_id).strip() for row_id in list(group.get("bank_transaction_ids") or []) if str(row_id).strip()],
                        *[str(row_id).strip() for row_id in list(group.get("input_invoice_ids") or []) if str(row_id).strip()],
                        *[str(row_id).strip() for row_id in list(group.get("output_invoice_ids") or []) if str(row_id).strip()],
                        *[str(row_id).strip() for row_id in list(group.get("oa_row_ids") or []) if str(row_id).strip()],
                    ]
                relation_mode = str(payload.get("relation_mode") or group.get("relation_source") or "")
                row_types = [
                    str(row_type).strip()
                    for row_type in list(payload.get("row_types") or [])
                    if str(row_type).strip()
                ]
                row_type_set = {row_type for row_type in row_types if row_type}
                if (
                    invoice_id in row_ids
                    and transaction_id not in row_ids
                    and "invoice" in row_type_set
                    and row_type_set.issubset({"bank", "invoice", "oa"})
                ):
                    saw_existing_linkable_group = True
                    continue
                if invoice_id in row_ids and transaction_id not in row_ids:
                    conflicts.append(
                        {
                            "relation_case_id": str(group.get("group_id") or payload.get("group_id") or ""),
                            "relation_mode": relation_mode,
                            "row_ids": sorted(set(row_ids)),
                        }
                    )
            if conflicts:
                return conflicts
            if saw_existing_linkable_group:
                return []
            group_ids = _linked_group_ids_from_distribution_row(relation_row)
            if linked_bank_ids or group_ids:
                return [
                    {
                        "relation_case_id": group_ids[0] if group_ids else "",
                        "relation_mode": "",
                        "row_ids": sorted({invoice_id, *linked_bank_ids}),
                    }
                ]
            return []
        return conflicts

    def _attach_existing_batch_conflicts(self, *, transaction_ids: list[str], invoice_ids: list[str]) -> list[dict[str, Any]]:
        conflicts: list[dict[str, Any]] = []
        seen: set[str] = set()
        for invoice_id in invoice_ids:
            for transaction_id in transaction_ids:
                for conflict in self._attach_existing_conflicts(transaction_id=transaction_id, invoice_id=invoice_id):
                    key = json.dumps(conflict, sort_keys=True, ensure_ascii=False)
                    if key in seen:
                        continue
                    seen.add(key)
                    conflicts.append(conflict)
        return conflicts

    def _paid_total_for_invoice(self, invoice_id: str) -> Decimal:
        relation_row = self._relation_distribution_row(invoice_id, reason="pending_invoice_attach_existing_paid_total")
        if relation_row is not None:
            paid_total = Decimal("0.00")
            seen_transaction_ids: set[str] = set()
            for item in list(relation_row.get("linked_bank_transactions") or []):
                if not isinstance(item, dict):
                    continue
                if not _distribution_item_is_linked(item):
                    continue
                transaction_id = str(item.get("id") or item.get("transaction_id") or "").strip()
                if transaction_id and transaction_id in seen_transaction_ids:
                    continue
                if transaction_id:
                    seen_transaction_ids.add(transaction_id)
                    try:
                        paid_total += self._import_service.get_transaction(transaction_id).amount
                        continue
                    except KeyError:
                        pass
                paid_total += _decimal_from_text(item.get("amount"))
            return paid_total.quantize(Decimal("0.01"))
        return Decimal("0.00")

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
        relation_row = self._relation_distribution_row(invoice_id, reason="pending_invoice_relation_exists")
        if relation_row is not None:
            linked_bank_ids = {
                str(item.get("id") or item.get("transaction_id") or "").strip()
                for item in list(relation_row.get("linked_bank_transactions") or [])
                if isinstance(item, dict) and _distribution_item_is_linked(item)
            }
            if transaction_id not in linked_bank_ids:
                return False
            for group in list(relation_row.get("_relation_groups") or []):
                if not isinstance(group, dict):
                    continue
                if not _distribution_group_is_linked(group):
                    continue
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
                relation_mode = str(payload.get("relation_mode") or "").strip()
                row_ids = {str(row_id).strip() for row_id in list(payload.get("row_ids") or []) if str(row_id).strip()}
                if {invoice_id, transaction_id}.issubset(row_ids) and relation_mode == PENDING_INVOICE_RELATION_MODE:
                    return True
            return False
        return False

    def _relation_distribution_row(self, row_id: str, *, reason: str) -> dict[str, Any] | None:
        normalized_row_id = str(row_id or "").strip()
        if not normalized_row_id or self._relation_facade is None:
            return None
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return None
        try:
            payload = reader([normalized_row_id], require_fresh=False, reason=reason)
        except TypeError:
            payload = reader([normalized_row_id])
        if not isinstance(payload, dict):
            return None
        groups_by_id = {
            str(group.get("group_id") or "").strip(): group
            for group in list(payload.get("groups") or [])
            if isinstance(group, dict) and str(group.get("group_id") or "").strip()
        }
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            if str(row.get("row_id") or "").strip() != normalized_row_id:
                continue
            group_ids = [str(group_id).strip() for group_id in list(row.get("group_ids") or []) if str(group_id).strip()]
            result = dict(row)
            result["_relation_groups"] = [groups_by_id[group_id] for group_id in group_ids if group_id in groups_by_id]
            return result
        return None

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
            self._overlay_command_invoice_on_row(
                result["row"],
                invoice_id=invoice_id,
                direction=direction,
                relation_case_id=relation_case_id,
            )
        return result

    def _overlay_command_invoice_on_row(
        self,
        row: dict[str, Any],
        *,
        invoice_id: str,
        direction: str,
        relation_case_id: str,
    ) -> None:
        """Keep the write response immediately useful while relation read models refresh asynchronously."""
        if not isinstance(row, dict):
            return
        try:
            invoice = self._import_service.get_invoice(invoice_id)
        except KeyError:
            return
        invoice_payload = PendingInvoiceQueryService._invoice_payload(invoice, direction=direction)
        invoice_payload["relation_case_id"] = relation_case_id
        existing = [item for item in list(row.get("invoices") or []) if isinstance(item, dict)]
        if not any(str(item.get("id") or "") == invoice_id for item in existing):
            existing.append(invoice_payload)
        row["invoices"] = existing
        invoice_group = row.get("input_invoices")
        if not isinstance(invoice_group, dict):
            invoice_group = {}
            row["input_invoices"] = invoice_group
        summaries = [item for item in list(invoice_group.get("summaries") or []) if isinstance(item, dict)]
        if not any(str(item.get("id") or "") == invoice_id for item in summaries):
            summaries.append(invoice_payload)
        invoice_group["summaries"] = summaries
        invoice_group["primary"] = summaries[0] if summaries else None
        invoice_group["relation_count"] = len(summaries)
        invoice_group["has_multiple"] = len(summaries) > 1
        invoice_group["payment_summary"] = PendingInvoiceQueryService._empty_payment_summary(summaries)
        relation_case_ids = [
            str(item).strip()
            for item in list(row.get("relation_case_ids") or [])
            if str(item).strip()
        ]
        if relation_case_id and relation_case_id not in relation_case_ids:
            relation_case_ids.append(relation_case_id)
        row["relation_case_ids"] = relation_case_ids

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

    def _record_attach_existing_batch_audit(
        self,
        *,
        actor_id: str,
        transaction_ids: list[str],
        invoice_ids: list[str],
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
                "action": "pending_invoice_attach_existing_invoice_batch_confirmed",
                "source": "pending_invoice_attach_existing_invoice",
                "entity_type": "pending_invoice_attach_existing_invoice",
                "transaction_ids": list(transaction_ids),
                "invoice_ids": list(invoice_ids),
                "relation_case_id": relation_case_id,
                "request_id": request_id,
                "request_key": request_key,
                "affected_months": list(affected_months),
            }
        )

    def _record_income_status_override_audit(
        self,
        *,
        actor_id: str,
        transaction_id: str,
        request_id: str,
        request_key: str,
        status_code: str,
        affected_months: list[str],
    ) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            {
                "actor_id": actor_id,
                "action": "pending_invoice_income_status_override_confirmed",
                "source": "pending_invoice_income_status_override",
                "entity_type": "pending_invoice_income_status_override",
                "transaction_id": transaction_id,
                "request_id": request_id,
                "request_key": request_key,
                "status_code": status_code,
                "affected_months": list(affected_months),
            }
        )

    def _record_income_status_override_batch_audit(
        self,
        *,
        actor_id: str,
        transaction_ids: list[str],
        request_id: str,
        request_key: str,
        status_code: str,
        affected_months: list[str],
    ) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            {
                "actor_id": actor_id,
                "action": "pending_invoice_income_status_override_batch_confirmed",
                "source": "pending_invoice_income_status_override",
                "entity_type": "pending_invoice_income_status_override",
                "transaction_ids": list(transaction_ids),
                "request_id": request_id,
                "request_key": request_key,
                "status_code": status_code,
                "affected_months": list(affected_months),
            }
        )

    def _inject_fault(self, phase: str, command: dict[str, Any]) -> None:
        if self._fault_injector is not None:
            self._fault_injector(phase, command)

    def _mark_relation_precondition_error(self, command: dict[str, Any], exc: PendingInvoiceError) -> None:
        if exc.error_code != "pending_invoice_relation_read_model_not_fresh":
            return
        command["error"] = str(exc)
        command["error_code"] = exc.error_code
        command["last_successful_status"] = self._last_successful_status(command)
        self._mark_command(command, "failed_recoverable")

    def _mark_command(self, command: dict[str, Any], status: str, *, error_code: str | None = None) -> None:
        if status not in COMMAND_STATUSES:
            raise ValueError(f"unsupported pending invoice command status: {status}")
        command["status"] = status
        command["updated_at"] = _now()
        history = command.setdefault("status_history", [])
        if status not in history:
            history.append(status)
        if error_code:
            command["error_code"] = error_code
        self._save_command(command)

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


def _normalize_id_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    else:
        try:
            raw_values = list(value or [])
        except TypeError as exc:
            raise PendingInvoiceError("invalid_id_list", f"{field_name} must be a list of ids.") from exc
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_value in raw_values:
        item = str(raw_value or "").strip()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    if not normalized:
        raise PendingInvoiceError("invalid_id_list", f"{field_name} must include at least one id.")
    return normalized


def _raw_id_list(value: Any, field_name: str) -> list[str]:
    if isinstance(value, str):
        raw_values = [value]
    else:
        try:
            raw_values = list(value or [])
        except TypeError as exc:
            raise PendingInvoiceError("invalid_id_list", f"{field_name} must be a list of ids.") from exc
    return [str(raw_value or "").strip() for raw_value in raw_values if str(raw_value or "").strip()]


def _row_has_linked_invoice(row: dict[str, Any]) -> bool:
    if row.get("invoices"):
        return True
    for key in ("output_invoices", "input_invoices"):
        invoice_payload = row.get(key)
        if not isinstance(invoice_payload, dict):
            continue
        if invoice_payload.get("primary") or invoice_payload.get("summaries"):
            return True
        try:
            if int(invoice_payload.get("relation_count") or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _row_can_mark_income_status(row: dict[str, Any]) -> bool:
    available_actions = row.get("available_actions")
    if isinstance(available_actions, list):
        return "mark_income_status" in {str(action) for action in available_actions}
    status_payload = row.get("invoice_acquisition_status")
    if isinstance(status_payload, dict) and "primary_action" in status_payload:
        return str(status_payload.get("primary_action") or "") == "mark_income_status"
    return True


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


def _relation_can_absorb_attach_existing_invoice(relation: dict[str, Any], invoice_id: str) -> bool:
    row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
    row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
    has_invoice = any(row_id == invoice_id and row_type == "invoice" for row_id, row_type in zip(row_ids, row_types, strict=False))
    return has_invoice and {row_type for row_type in row_types if row_type}.issubset({"bank", "invoice", "oa"})


def _distribution_item_relation_status(item: dict[str, Any] | None) -> str:
    if not isinstance(item, dict):
        return "linked"
    status = str(item.get("relation_status") or item.get("relationStatus") or "").strip()
    return status or "linked"


def _distribution_item_is_linked(item: dict[str, Any] | None) -> bool:
    return _distribution_item_relation_status(item) == "linked"


def _distribution_group_relation_status(group: dict[str, Any] | None) -> str:
    if not isinstance(group, dict):
        return "linked"
    payload = group.get("payload") if isinstance(group.get("payload"), dict) else {}
    status = str(payload.get("relation_status") or group.get("relation_status") or "").strip()
    return status or "linked"


def _distribution_group_is_linked(group: dict[str, Any] | None) -> bool:
    return _distribution_group_relation_status(group) == "linked"


def _linked_group_ids_from_distribution_row(row: dict[str, Any]) -> list[str]:
    linked_group_ids: list[str] = []
    for group in list(row.get("_relation_groups") or []):
        if not isinstance(group, dict) or not _distribution_group_is_linked(group):
            continue
        group_id = str(group.get("group_id") or "").strip()
        if group_id and group_id not in linked_group_ids:
            linked_group_ids.append(group_id)
    return linked_group_ids


def _relation_dict_is_linked(relation: dict[str, Any] | None) -> bool:
    if not isinstance(relation, dict):
        return False
    status = str(relation.get("relation_status") or relation.get("relationStatus") or "").strip()
    if not status and str(relation.get("status") or "").strip() == "active":
        status = "linked"
    return (status or "linked") == "linked"


def _row_type_for_relation_row_id(row_id: str) -> str:
    return row_type_for_workbench_row_id(row_id)


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

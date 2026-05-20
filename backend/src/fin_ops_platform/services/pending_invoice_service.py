from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
import hashlib
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.domain.enums import BatchType, ImportDecision, InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


PENDING_INVOICE_RELATION_MODE = "pending_invoice_manual_invoice"
MANUAL_INVOICE_SOURCE_NAME = "pending_invoice_manual_entry"
MANUAL_INVOICE_SOURCE_TYPE = "manual_invoice_import"
EXPENSE_FILTERS = {"requires_invoice", "bank_statement_as_invoice", "no_invoice_required"}
VALID_FILTERS = {"all", *EXPENSE_FILTERS}
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
    ) -> None:
        self._import_service = import_service
        self._pair_relation_service = pair_relation_service
        self._category_service = category_service
        self._app_settings_provider = app_settings_provider
        self._effective_category_provider = effective_category_provider

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

        transactions = [
            transaction
            for transaction in self._import_service.list_transactions()
            if self._transaction_matches_direction(transaction, normalized_direction)
            and self._matches_date_range(transaction, date_from=date_from, date_to=date_to)
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
        payload = self.list_rows(direction=direction, filter="all", page=1, page_size=200)
        for row in payload["rows"]:
            if row.get("id") == transaction_id:
                return row
        raise PendingInvoiceError(
            "bank_transaction_not_found",
            f"Bank transaction not found in pending invoice rows: {transaction_id}",
            status_code=HTTPStatus.NOT_FOUND,
        )

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

    def _row_payload(
        self,
        transaction: BankTransaction,
        *,
        direction: str,
        category: dict[str, Any],
        tag_groups: dict[str, set[str]],
    ) -> dict[str, Any]:
        target_invoice_type = InvoiceType.INPUT if direction == "expense" else InvoiceType.OUTPUT
        invoice_map = {invoice.id: invoice for invoice in self._import_service.list_invoices()}
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
        return {
            "id": transaction.id,
            "bank_transaction": {
                "id": transaction.id,
                "counterparty_name": transaction.counterparty_name_raw,
                "trade_time": transaction.trade_time or transaction.txn_date,
                "amount": _decimal_to_str(transaction.amount),
                "bank_name": transaction.imported_bank_name or "",
                "account_last4": transaction.imported_bank_last4 or str(transaction.account_no or "")[-4:],
                "effective_tag_code": category_code,
                "effective_tag_label": category.get("category_label"),
            },
            "invoices": invoices,
            "oa_applicant": self._oa_applicant_from_relations(relations),
            "can_create_invoice": can_create_invoice,
            "relation_case_ids": [str(relation.get("case_id")) for relation, _ in invoice_relations],
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


def _decimal_to_str(value: Decimal | None) -> str:
    if value is None:
        return "0.00"
    return str(Decimal(value).quantize(Decimal("0.01")))


def _now() -> str:
    return datetime.now(UTC).isoformat()

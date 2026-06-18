from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha1
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService, clean_string
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusError,
    OAPaymentStatusRepository,
    PAY_STATUS_PAID,
)
from fin_ops_platform.services.oa_pending_payment_service import (
    OaPendingPaymentError,
    VIEW_MODE_IN_PROGRESS,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


RefreshCallback = Callable[[str], object]


class OaPendingPaymentCommandService:
    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        oa_projection: Any,
        relation_command_service: Any | None,
        payment_status_repository: OAPaymentStatusRepository | None,
        lifecycle_policy: InvoiceLifecyclePolicy | None = None,
        enqueue_workbench_refresh: Callable[..., object] | None = None,
        enqueue_oa_pending_payment_refresh: Callable[..., object] | None = None,
    ) -> None:
        self._import_service = import_service
        self._oa_projection = oa_projection
        self._relation_command_service = relation_command_service
        self._payment_status_repository = payment_status_repository
        self._lifecycle_policy = lifecycle_policy or InvoiceLifecyclePolicy()
        self._enqueue_workbench_refresh = enqueue_workbench_refresh
        self._enqueue_oa_pending_payment_refresh = enqueue_oa_pending_payment_refresh

    def confirm_paid(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        oa_row_id = _payload_text(payload, "oa_row_id", "oaRowId")
        if not oa_row_id:
            raise OaPendingPaymentError("oa_row_id_required", "oa_row_id is required.")
        actor = clean_string(actor_id) or "system"
        bank_transaction_ids = _payload_list(payload, "bank_transaction_ids", "bankTransactionIds")
        single_bank_transaction_id = _payload_text(payload, "bank_transaction_id", "bankTransactionId")
        if single_bank_transaction_id and single_bank_transaction_id not in bank_transaction_ids:
            bank_transaction_ids.append(single_bank_transaction_id)
        note = _payload_text(payload, "note")
        idempotency_key = _payload_text(payload, "idempotency_key", "idempotencyKey") or None
        record = self._oa_record(oa_row_id)
        self._assert_in_progress(record)
        if self._payment_status_repository is None:
            raise OaPendingPaymentError(
                "oa_payment_status_repository_unavailable",
                "OA payment status writeback is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        if self._relation_command_service is None:
            raise OaPendingPaymentError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        flow_id = self._resolve_oa_flow_id(record)

        relation_result: dict[str, Any]
        if bank_transaction_ids:
            bank_transactions = [self._bank_transaction(bank_transaction_id) for bank_transaction_id in bank_transaction_ids]
            amount_check = self._assert_paid_by_banks(record, bank_transactions)
            active_relation = self._active_relation_for_oa_or_none(record.id)
            if active_relation is not None and _relation_contains_bank_ids(active_relation, bank_transaction_ids):
                relation_result = {
                    "status": "already_confirmed",
                    "relation": active_relation,
                    "affected_months": [record.month] if record.month else [],
                }
            else:
                relation_result = self._confirm_relation(
                    [record],
                    bank_transactions,
                    actor_id=actor,
                    note=note,
                    amount_check=amount_check,
                    idempotency_key=idempotency_key,
                    case_id=_payload_text(payload, "case_id", "caseId") or None,
                    history_operation_type="oa_pending_payment_confirm_paid",
                    history_note=note or "OA 待付款确认已支付",
                    source_action="confirm_paid",
                )
        else:
            active_relation = self._active_relation_for_oa(record.id)
            bank_transactions = self._bank_transactions_from_relation(active_relation)
            amount_check = self._assert_paid_by_banks(record, bank_transactions)
            relation_result = {
                "status": "already_confirmed",
                "relation": active_relation,
                "affected_months": [record.month] if record.month else [],
            }

        writeback = self._mark_oa_paid(flow_id)
        refresh = self._enqueue_refreshes(record)
        return {
            "success": True,
            "action": "oa_pending_payment_confirm_paid",
            "oaRowId": record.id,
            "bankTransactionIds": [transaction.id for transaction in bank_transactions],
            "paymentStatus": {
                "code": "paid",
                "label": "已支付",
                "reason": amount_check.get("reason", "支出流水合计等于OA金额"),
            },
            "oaPaymentWriteback": writeback,
            "relation": relation_result,
            "readModelRefresh": refresh,
        }

    def link_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        oa_row_ids = _payload_list(payload, "oa_row_ids", "oaRowIds")
        bank_transaction_ids = _payload_list(payload, "bank_transaction_ids", "bankTransactionIds")
        if not oa_row_ids:
            raise OaPendingPaymentError("oa_row_ids_required", "At least one OA row is required.")
        if not bank_transaction_ids:
            raise OaPendingPaymentError("bank_transaction_ids_required", "At least one bank transaction is required.")
        if self._relation_command_service is None:
            raise OaPendingPaymentError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        records = self._oa_records(oa_row_ids)
        if len(records) != len(set(oa_row_ids)):
            found_ids = {record.id for record in records}
            missing = [row_id for row_id in oa_row_ids if row_id not in found_ids]
            raise OaPendingPaymentError(
                "oa_not_found",
                "One or more OA rows were not found.",
                status_code=HTTPStatus.NOT_FOUND,
                details={"oa_row_ids": missing},
            )
        for record in records:
            self._assert_in_progress(record)
        bank_transactions = [self._bank_transaction(bank_transaction_id) for bank_transaction_id in bank_transaction_ids]
        non_outflow = [
            transaction.id
            for transaction in bank_transactions
            if _bank_direction(transaction) != "outflow"
        ]
        if non_outflow:
            raise OaPendingPaymentError(
                "bank_transaction_not_outflow",
                "Only outflow bank transactions can be linked to in-progress OA payments.",
                status_code=HTTPStatus.CONFLICT,
                details={"bank_transaction_ids": non_outflow},
            )
        amount_check = self._relation_amount_check(records, bank_transactions)
        relation_result = self._confirm_relation(
            records,
            bank_transactions,
            actor_id=clean_string(actor_id) or "system",
            note=_payload_text(payload, "note"),
            amount_check=amount_check,
            idempotency_key=_payload_text(payload, "idempotency_key", "idempotencyKey") or None,
            case_id=_payload_text(payload, "case_id", "caseId") or None,
            history_operation_type="oa_pending_payment_link_bank",
            history_note=_payload_text(payload, "note") or "OA 待付款关联支出流水",
            source_action="link_bank_transactions",
        )
        refresh = self._enqueue_refreshes_for_records(records)
        return {
            "success": True,
            "action": "oa_pending_payment_link_bank_transactions",
            "oaRowIds": [record.id for record in records],
            "bankTransactionIds": [transaction.id for transaction in bank_transactions],
            "relation": relation_result,
            "readModelRefresh": refresh,
        }

    def bank_transaction_candidates(self, query: dict[str, list[str]] | None = None) -> dict[str, Any]:
        query = query or {}
        status_filter = clean_string((query.get("relation_status") or query.get("relationStatus") or ["all"])[0]) or "all"
        keyword = clean_string((query.get("keyword") or [""])[0])
        page = _parse_positive_int((query.get("page") or [1])[0], "page")
        page_size = _parse_positive_int((query.get("page_size") or query.get("pageSize") or [100])[0], "page_size", maximum=200)
        transactions = [
            transaction
            for transaction in self._import_service.list_transactions(month="all")
            if _bank_direction(transaction) == "outflow"
        ]
        transaction_ids = [transaction.id for transaction in transactions]
        relation_map = self._relation_status_by_bank_id(transaction_ids)
        rows = [
            _bank_candidate_payload(transaction, relation_map.get(transaction.id))
            for transaction in transactions
        ]
        if keyword:
            rows = [row for row in rows if keyword in json_dumps(row)]
        if status_filter in {"unmatched", "matched", "linked_in_progress"}:
            rows = [row for row in rows if row.get("relationStatus") == status_filter]
        rows.sort(key=lambda row: (str(row.get("tradeTime") or ""), str(row.get("id") or "")), reverse=True)
        total = len(rows)
        paged = rows[(page - 1) * page_size : page * page_size]
        return {
            "rows": paged,
            "pagination": {"page": page, "pageSize": page_size, "total": total},
            "filters": {
                "relationStatus": status_filter,
                "keyword": keyword,
            },
        }

    def _oa_record(self, oa_row_id: str) -> OAApplicationRecord:
        loader = getattr(self._oa_projection, "list_application_records_by_row_ids", None)
        records: list[OAApplicationRecord] = []
        if callable(loader):
            records = [
                record
                for record in list(loader([oa_row_id]) or [])
                if isinstance(record, OAApplicationRecord)
            ]
        if not records:
            list_all = getattr(self._oa_projection, "list_all_application_records", None)
            if callable(list_all):
                records = [
                    record
                    for record in list(list_all() or [])
                    if isinstance(record, OAApplicationRecord) and record.id == oa_row_id
                ]
        if not records:
            raise OaPendingPaymentError(
                "oa_not_found",
                f"OA detail not found: {oa_row_id}",
                status_code=HTTPStatus.NOT_FOUND,
            )
        return records[0]

    def _oa_records(self, oa_row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = []
        for row_id in oa_row_ids:
            normalized = clean_string(row_id)
            if normalized and normalized not in wanted:
                wanted.append(normalized)
        loader = getattr(self._oa_projection, "list_application_records_by_row_ids", None)
        records: list[OAApplicationRecord] = []
        if callable(loader):
            records = [
                record
                for record in list(loader(wanted) or [])
                if isinstance(record, OAApplicationRecord)
            ]
        if len(records) < len(wanted):
            found_ids = {record.id for record in records}
            list_all = getattr(self._oa_projection, "list_all_application_records", None)
            if callable(list_all):
                records.extend(
                    record
                    for record in list(list_all() or [])
                    if isinstance(record, OAApplicationRecord)
                    and record.id in wanted
                    and record.id not in found_ids
                )
        record_by_id = {record.id: record for record in records}
        return [record_by_id[row_id] for row_id in wanted if row_id in record_by_id]

    @staticmethod
    def _assert_in_progress(record: OAApplicationRecord) -> None:
        workflow_status = clean_string(getattr(record, "workflow_status", "") or "")
        if workflow_status != VIEW_MODE_IN_PROGRESS:
            raise OaPendingPaymentError(
                "oa_workflow_status_not_in_progress",
                "Only in-progress OA rows can be confirmed paid from this view.",
                status_code=HTTPStatus.CONFLICT,
                details={"oa_row_id": record.id, "workflow_status": workflow_status},
            )

    def _bank_transaction(self, bank_transaction_id: str) -> BankTransaction:
        try:
            return self._import_service.get_transaction(bank_transaction_id)
        except KeyError as exc:
            raise OaPendingPaymentError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=HTTPStatus.NOT_FOUND,
            ) from exc

    def _active_relation_for_oa(self, oa_row_id: str) -> dict[str, Any]:
        relation = self._active_relation_for_oa_or_none(oa_row_id)
        if relation is None:
            raise OaPendingPaymentError(
                "bank_transaction_id_required",
                "bank_transaction_id is required when the OA row has no active bank relation.",
            )
        return relation

    def _active_relation_for_oa_or_none(self, oa_row_id: str) -> dict[str, Any] | None:
        active_relations_for_row_ids = getattr(self._relation_command_service, "active_relations_for_row_ids", None)
        if not callable(active_relations_for_row_ids):
            raise OaPendingPaymentError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service cannot read active relations.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        relations = [
            relation
                for relation in list(active_relations_for_row_ids([oa_row_id]) or [])
                if isinstance(relation, dict)
        ]
        if not relations:
            return None
        if len(relations) > 1:
            raise OaPendingPaymentError(
                "oa_multiple_active_relations",
                "OA row has multiple active relations and cannot be written back automatically.",
                status_code=HTTPStatus.CONFLICT,
                details={"oa_row_id": oa_row_id, "case_ids": [clean_string(item.get("case_id") or "") for item in relations]},
            )
        return relations[0]

    def _bank_transactions_from_relation(self, relation: dict[str, Any]) -> list[BankTransaction]:
        bank_ids = _relation_bank_ids(relation)
        if not bank_ids:
            raise OaPendingPaymentError(
                "active_relation_has_no_bank_transaction",
                "Active relation does not contain a bank transaction.",
                status_code=HTTPStatus.CONFLICT,
                details={"case_id": clean_string(relation.get("case_id") or "")},
            )
        return [self._bank_transaction(bank_id) for bank_id in bank_ids]

    def _assert_paid_by_banks(
        self,
        record: OAApplicationRecord,
        bank_transactions: list[BankTransaction],
    ) -> dict[str, Any]:
        oa_amount = _optional_decimal(record.amount)
        if oa_amount is None:
            raise OaPendingPaymentError(
                "oa_amount_invalid",
                "OA amount is missing or invalid.",
                status_code=HTTPStatus.CONFLICT,
                details={"oa_row_id": record.id, "amount": record.amount},
            )
        if not bank_transactions:
            raise OaPendingPaymentError(
                "bank_transaction_id_required",
                "At least one bank transaction is required.",
            )
        non_outflow = [
            transaction.id
            for transaction in bank_transactions
            if _bank_direction(transaction) != "outflow"
        ]
        paid_total = sum((abs(_decimal(transaction.amount)) for transaction in bank_transactions), start=Decimal("0"))
        status = self._lifecycle_policy.evaluate_oa_payment(
            oa_amount=oa_amount,
            paid_total=paid_total,
            has_bank=not non_outflow,
            has_non_outflow_bank_relation=bool(non_outflow),
        )
        if status.get("code") != "paid":
            raise OaPendingPaymentError(
                "oa_payment_status_not_paid",
                "Selected bank transaction cannot prove this OA has been paid.",
                status_code=HTTPStatus.CONFLICT,
                details={
                    "oa_row_id": record.id,
                    "bank_transaction_ids": [transaction.id for transaction in bank_transactions],
                    "payment_status": status,
                    "oa_amount": _money(oa_amount),
                    "paid_total": _money(paid_total),
                    "non_outflow_bank_transaction_ids": non_outflow,
                },
            )
        return {
            "matched": True,
            "oa_amount": _money(oa_amount),
            "bank_paid_total": _money(paid_total),
            "bank_transaction_count": len(bank_transactions),
            "reason": status.get("reason", "支出流水合计等于OA金额"),
            "source": "oa_pending_payment_confirm_paid",
        }

    def _relation_amount_check(
        self,
        records: list[OAApplicationRecord],
        bank_transactions: list[BankTransaction],
    ) -> dict[str, Any]:
        oa_total = sum((_decimal(record.amount) for record in records), start=Decimal("0"))
        bank_total = sum((abs(_decimal(transaction.amount)) for transaction in bank_transactions), start=Decimal("0"))
        return {
            "matched": oa_total == bank_total,
            "oa_amount": _money(oa_total),
            "bank_paid_total": _money(bank_total),
            "oa_count": len(records),
            "bank_transaction_count": len(bank_transactions),
            "reason": "支出流水合计等于OA金额" if oa_total == bank_total else "支出流水合计与OA金额不一致",
            "source": "oa_pending_payment_link_bank_transactions",
        }

    def _confirm_relation(
        self,
        records: list[OAApplicationRecord],
        bank_transactions: list[BankTransaction],
        *,
        actor_id: str,
        note: str,
        amount_check: dict[str, Any],
        idempotency_key: str | None,
        case_id: str | None,
        history_operation_type: str,
        history_note: str,
        source_action: str,
    ) -> dict[str, Any]:
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            raise OaPendingPaymentError(
                "workbench_relation_command_unavailable",
                "Workbench relation command service cannot confirm relations.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        if not records:
            raise OaPendingPaymentError("oa_row_ids_required", "At least one OA row is required.")
        bank_ids = [transaction.id for transaction in bank_transactions]
        oa_ids = [record.id for record in records]
        try:
            return dict(
                confirm_relation(
                    case_id=case_id or _confirm_paid_case_id(oa_ids, bank_ids),
                    row_ids=[*oa_ids, *bank_ids],
                    row_types=[*(["oa"] * len(oa_ids)), *(["bank"] * len(bank_ids))],
                    relation_mode="manual_confirmed",
                    actor_id=actor_id,
                    month_scope=_relation_month_scope(records),
                    note=note or None,
                    amount_check=amount_check,
                    special_metadata={
                        "origin": "oa_pending_payment_in_progress",
                        "source_action": source_action,
                    },
                    history_note=history_note,
                    idempotency_key=idempotency_key,
                    history_operation_type=history_operation_type,
                )
            )
        except WorkbenchRelationCommandError as exc:
            raise OaPendingPaymentError(
                exc.error_code,
                exc.message,
                status_code=HTTPStatus.CONFLICT,
                details=exc.payload,
            ) from exc

    def _resolve_oa_flow_id(self, record: OAApplicationRecord) -> str:
        assert self._payment_status_repository is not None
        try:
            flow_id = self._payment_status_repository.resolve_flow_id(record)
            if not flow_id:
                raise OaPendingPaymentError(
                    "oa_flow_id_not_found",
                    "Cannot resolve OA Flowable process id for payment status writeback.",
                    status_code=HTTPStatus.CONFLICT,
                    details={"oa_row_id": record.id},
                )
            return flow_id
        except OaPendingPaymentError:
            raise
        except OAPaymentStatusError as exc:
            raise OaPendingPaymentError(
                "oa_payment_status_writeback_unavailable",
                "OA payment status writeback is unavailable.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                details={"oa_row_id": record.id},
            ) from exc

    def _mark_oa_paid(self, flow_id: str) -> dict[str, Any]:
        assert self._payment_status_repository is not None
        try:
            status_record = self._payment_status_repository.mark_paid(flow_id)
        except OAPaymentStatusError as exc:
            raise OaPendingPaymentError(
                "oa_payment_status_writeback_unavailable",
                "OA payment status writeback failed.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                details={"flow_id": flow_id},
            ) from exc
        return {
            "code": "written" if status_record.pay_status == PAY_STATUS_PAID else "not_written",
            "label": "已写回" if status_record.pay_status == PAY_STATUS_PAID else "未写回",
            "flowId": status_record.flow_id,
        }

    def _enqueue_refreshes(self, record: OAApplicationRecord) -> dict[str, Any]:
        scope_keys = _refresh_scope_keys(record.month)
        metadata = {"oa_row_id": record.id, "reason": "oa_pending_payment_confirm_paid"}
        refreshed: list[str] = []
        for scope_key in scope_keys:
            if callable(self._enqueue_workbench_refresh):
                self._enqueue_workbench_refresh(
                    scope_key,
                    reason="oa_pending_payment_confirm_paid",
                    metadata=metadata,
                )
                refreshed.append(f"workbench:{scope_key}")
            if callable(self._enqueue_oa_pending_payment_refresh):
                self._enqueue_oa_pending_payment_refresh(
                    scope_key,
                    reason="oa_pending_payment_confirm_paid",
                    metadata=metadata,
                )
                refreshed.append(f"oa_pending_payment:{scope_key}")
        return {
            "scopeKeys": scope_keys,
            "targets": refreshed,
            "enqueued": bool(refreshed),
            "targetSeconds": 2,
        }

    def _enqueue_refreshes_for_records(self, records: list[OAApplicationRecord]) -> dict[str, Any]:
        scope_keys: list[str] = []
        for record in records:
            for scope_key in _refresh_scope_keys(record.month):
                if scope_key not in scope_keys:
                    scope_keys.append(scope_key)
        metadata = {"oa_row_ids": [record.id for record in records], "reason": "oa_pending_payment_link_bank_transactions"}
        refreshed: list[str] = []
        for scope_key in scope_keys:
            if callable(self._enqueue_workbench_refresh):
                self._enqueue_workbench_refresh(
                    scope_key,
                    reason="oa_pending_payment_link_bank_transactions",
                    metadata=metadata,
                )
                refreshed.append(f"workbench:{scope_key}")
            if callable(self._enqueue_oa_pending_payment_refresh):
                self._enqueue_oa_pending_payment_refresh(
                    scope_key,
                    reason="oa_pending_payment_link_bank_transactions",
                    metadata=metadata,
                )
                refreshed.append(f"oa_pending_payment:{scope_key}")
        return {
            "scopeKeys": scope_keys,
            "targets": refreshed,
            "enqueued": bool(refreshed),
            "targetSeconds": 2,
        }

    def _relation_status_by_bank_id(self, bank_transaction_ids: list[str]) -> dict[str, dict[str, Any]]:
        reader = getattr(self._relation_command_service, "active_relations_for_row_ids", None)
        if not callable(reader) or not bank_transaction_ids:
            return {}
        relations = [relation for relation in list(reader(bank_transaction_ids) or []) if isinstance(relation, dict)]
        oa_records = {record.id: record for record in self._oa_records(_relation_oa_ids(relations))}
        result: dict[str, dict[str, Any]] = {}
        for relation in relations:
            bank_ids = _relation_bank_ids(relation)
            oa_ids = _relation_oa_ids([relation])
            linked_in_progress = any(
                clean_string(getattr(oa_records.get(oa_id), "workflow_status", "") or "") == VIEW_MODE_IN_PROGRESS
                for oa_id in oa_ids
            )
            status = "linked_in_progress" if linked_in_progress else "matched"
            for bank_id in bank_ids:
                result[bank_id] = {
                    "status": status,
                    "caseId": clean_string(relation.get("case_id") or ""),
                    "oaRowIds": oa_ids,
                }
        return result


def _payload_text(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        text = clean_string(value or "")
        if text:
            return text
    return ""


def _payload_list(payload: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, list):
            for item in raw:
                text = clean_string(item or "")
                if text and text not in values:
                    values.append(text)
        else:
            text = clean_string(raw or "")
            if text and text not in values:
                values.append(text)
    return values


def _relation_bank_ids(relation: dict[str, Any]) -> list[str]:
    bank_ids: list[str] = []
    row_ids = list(relation.get("row_ids") or [])
    row_types = list(relation.get("row_types") or [])
    for index, row_id in enumerate(row_ids):
        row_type = clean_string(row_types[index] if index < len(row_types) else "")
        normalized_row_id = clean_string(row_id)
        if row_type == "bank" and normalized_row_id and normalized_row_id not in bank_ids:
            bank_ids.append(normalized_row_id)
    return bank_ids


def _relation_oa_ids(relations: list[dict[str, Any]]) -> list[str]:
    oa_ids: list[str] = []
    for relation in relations:
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        for index, row_id in enumerate(row_ids):
            row_type = clean_string(row_types[index] if index < len(row_types) else "")
            normalized_row_id = clean_string(row_id)
            if row_type == "oa" and normalized_row_id and normalized_row_id not in oa_ids:
                oa_ids.append(normalized_row_id)
    return oa_ids


def _relation_contains_bank_ids(relation: dict[str, Any], bank_transaction_ids: list[str]) -> bool:
    relation_bank_ids = set(_relation_bank_ids(relation))
    return all(bank_transaction_id in relation_bank_ids for bank_transaction_id in bank_transaction_ids)


def _confirm_paid_case_id(oa_row_ids: list[str], bank_transaction_ids: list[str]) -> str:
    digest = sha1("|".join([*oa_row_ids, *bank_transaction_ids]).encode("utf-8")).hexdigest()[:16]
    return f"OA-PAY-{digest}"


def _relation_month_scope(records: list[OAApplicationRecord]) -> str:
    months = []
    for record in records:
        month = clean_string(record.month or "")
        scope_key = month[:7] if len(month) >= 7 and month[4] == "-" else ""
        if scope_key and scope_key not in months:
            months.append(scope_key)
    return months[0] if len(months) == 1 else "all"


def _refresh_scope_keys(month: str | None) -> list[str]:
    normalized_month = clean_string(month or "")
    scope_keys = [normalized_month[:7]] if len(normalized_month) >= 7 and normalized_month[4] == "-" else []
    scope_keys.append("all")
    deduped: list[str] = []
    for scope_key in scope_keys:
        if scope_key and scope_key not in deduped:
            deduped.append(scope_key)
    return deduped


def _optional_decimal(value: Any) -> Decimal | None:
    text = clean_string(value or "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _parse_positive_int(value: Any, field_name: str, *, maximum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise OaPendingPaymentError(
            "invalid_paging",
            f"{field_name} must be a positive integer.",
            status_code=HTTPStatus.BAD_REQUEST,
            details={field_name: value},
        ) from exc
    if parsed < 1:
        raise OaPendingPaymentError(
            "invalid_paging",
            f"{field_name} must be a positive integer.",
            status_code=HTTPStatus.BAD_REQUEST,
            details={field_name: value},
        )
    if maximum is not None:
        return min(parsed, maximum)
    return parsed


def _decimal(value: Any) -> Decimal:
    parsed = _optional_decimal(value)
    return parsed if parsed is not None else Decimal("0")


def _money(value: Any) -> str:
    return f"{_decimal(value).quantize(Decimal('0.01'))}"


def _bank_direction(transaction: BankTransaction) -> str:
    raw_value = getattr(transaction.txn_direction, "value", transaction.txn_direction)
    value = clean_string(raw_value)
    if value == TransactionDirection.OUTFLOW.value or "outflow" in value:
        return "outflow"
    return "inflow"


def _bank_candidate_payload(transaction: BankTransaction, relation: dict[str, Any] | None) -> dict[str, Any]:
    status = str((relation or {}).get("status") or "unmatched")
    return {
        "id": transaction.id,
        "counterpartyName": clean_string(transaction.counterparty_name_raw or ""),
        "tradeTime": clean_string(transaction.trade_time or transaction.txn_date or ""),
        "amount": _money(abs(_decimal(transaction.amount))),
        "bankName": clean_string(getattr(transaction, "imported_bank_name", "") or ""),
        "accountNo": clean_string(transaction.account_no or ""),
        "accountLast4": clean_string(transaction.account_no or "")[-4:],
        "bankAccount": _bank_account_label(transaction),
        "direction": _bank_direction(transaction),
        "directionLabel": "支出",
        "summary": clean_string(getattr(transaction, "summary", "") or ""),
        "remark": clean_string(getattr(transaction, "remark", "") or ""),
        "relationStatus": status,
        "relationStatusLabel": {
            "unmatched": "未配对",
            "matched": "已配对",
            "linked_in_progress": "已关联进行中OA",
        }.get(status, "未配对"),
        "relationCaseId": clean_string((relation or {}).get("caseId") or ""),
        "linkedOaRowIds": list((relation or {}).get("oaRowIds") or []),
    }


def _bank_account_label(transaction: BankTransaction) -> str:
    bank_name = clean_string(getattr(transaction, "imported_bank_name", "") or "")
    last4 = clean_string(getattr(transaction, "imported_bank_last4", "") or "") or clean_string(transaction.account_no or "")[-4:]
    if bank_name and last4:
        return f"{bank_name} {last4}"
    return bank_name or last4


def json_dumps(payload: dict[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, sort_keys=True)

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from hashlib import sha1
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService, clean_string
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import (
    OAPaymentStatusError,
    OAPaymentStatusRepository,
    PAY_STATUS_PAID,
)
from fin_ops_platform.services.oa_pending_payment_query_contract import (
    OaPendingPaymentError,
    VIEW_MODE_IN_PROGRESS,
)
from fin_ops_platform.services.workbench_relation_command_service import (
    WorkbenchRelationCommandError,
)
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


class OaPendingPaymentCommandService:
    def __init__(
        self,
        *,
        import_service: ImportNormalizationService,
        oa_projection: Any,
        relation_command_service: Any | None,
        payment_status_repository: OAPaymentStatusRepository | None,
        payment_status_snapshot_writer: Any | None = None,
        bank_transaction_category_codes_for_row_ids: Callable[[list[str]], dict[str, str]] | None = None,
        bank_flow_rule_tag_rules_payload: Callable[[], dict[str, object]] | None = None,
    ) -> None:
        self._import_service = import_service
        self._oa_projection = oa_projection
        self._relation_command_service = relation_command_service
        self._payment_status_repository = payment_status_repository
        self._payment_status_snapshot_writer = payment_status_snapshot_writer
        self._bank_transaction_category_codes_for_row_ids = bank_transaction_category_codes_for_row_ids
        self._bank_flow_rule_tag_rules_payload = bank_flow_rule_tag_rules_payload

    def link_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        oa_row_ids = _payload_list(payload, "oa_row_ids", "oaRowIds")
        bank_transaction_ids = _payload_list(payload, "bank_transaction_ids", "bankTransactionIds")
        if not oa_row_ids:
            raise OaPendingPaymentError("oa_row_ids_required", "At least one OA row is required.")
        if not bank_transaction_ids:
            raise OaPendingPaymentError("bank_transaction_ids_required", "At least one bank transaction is required.")
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
        flow_ids = self._resolve_oa_flow_ids(records) if amount_check.get("matched") is True else []
        relation_result = self._confirm_formal_relation(
            records,
            bank_transactions,
            actor_id=clean_string(actor_id) or "system",
            note=_payload_text(payload, "note"),
            amount_check=amount_check,
            idempotency_key=_payload_text(payload, "idempotency_key", "idempotencyKey") or None,
            history_operation_type="oa_pending_payment_link_bank",
            history_note=_payload_text(payload, "note") or "OA 待付款关联支出流水",
        )
        writebacks = self._mark_oa_flow_ids_paid(flow_ids)
        if flow_ids:
            self._record_paid_statuses(records)
        return {
            "success": True,
            "action": "oa_pending_payment_link_bank_transactions",
            "oaRowIds": [record.id for record in records],
            "bankTransactionIds": [transaction.id for transaction in bank_transactions],
            "relation": relation_result,
            "autoWriteback": {
                "code": "written" if writebacks else "not_required",
                "label": "已写回" if writebacks else "未写回",
                "reason": amount_check.get("reason", ""),
                "matched": amount_check.get("matched") is True,
                "writebackCount": len(writebacks),
            },
            "oaPaymentWriteback": writebacks[0] if len(writebacks) == 1 else None,
            "oaPaymentWritebacks": writebacks,
        }

    def writeback_paid(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        if self._payment_status_repository is None:
            raise OaPendingPaymentError(
                "oa_payment_status_repository_unavailable",
                "OA payment status writeback is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        oa_row_ids = _payload_list(payload, "oa_row_ids", "oaRowIds")
        if not oa_row_ids:
            raise OaPendingPaymentError("oa_row_ids_required", "At least one OA row is required.")
        records = self._writeback_records(oa_row_ids)
        if len(records) != len(set(oa_row_ids)):
            found_ids = {record.id for record in records}
            missing = [row_id for row_id in oa_row_ids if row_id not in found_ids]
            raise OaPendingPaymentError(
                "oa_not_found",
                "One or more OA rows were not found.",
                status_code=HTTPStatus.NOT_FOUND,
                details={"oa_row_ids": missing},
            )
        writeback_items, eligible_records = self._writeback_paid_relations(records)
        self._record_paid_statuses(eligible_records)
        writebacks = [_public_writeback(item) for item in writeback_items]
        return {
            "success": True,
            "action": "oa_pending_payment_writeback_paid",
            "oaRowIds": [record.id for record in records],
            "writebackCount": len(writebacks),
            "oaPaymentWriteback": writebacks[0] if len(writebacks) == 1 else None,
            "oaPaymentWritebacks": writebacks,
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
        return self._records_from_projection(self._oa_projection, oa_row_ids)

    def _writeback_records(self, oa_row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted: list[str] = []
        for row_id in oa_row_ids:
            normalized = clean_string(row_id)
            if normalized and normalized not in wanted:
                wanted.append(normalized)
        records: list[OAApplicationRecord] = []
        seen: set[str] = set()
        for record in self._records_from_projection(self._oa_projection, wanted):
            if record.id in seen:
                continue
            seen.add(record.id)
            records.append(record)
        record_by_id = {record.id: record for record in records}
        return [record_by_id[row_id] for row_id in wanted if row_id in record_by_id]

    @staticmethod
    def _records_from_projection(projection: Any, oa_row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = []
        for row_id in oa_row_ids:
            normalized = clean_string(row_id)
            if normalized and normalized not in wanted:
                wanted.append(normalized)
        loader = getattr(projection, "list_application_records_by_row_ids", None)
        records: list[OAApplicationRecord] = []
        if callable(loader):
            records = [
                record
                for record in list(loader(wanted) or [])
                if isinstance(record, OAApplicationRecord)
            ]
        if len(records) < len(wanted):
            found_ids = {record.id for record in records}
            list_all = getattr(projection, "list_all_application_records", None)
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

    def _active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        active_relations_for_row_ids = getattr(
            self._relation_command_service,
            "active_relations_for_row_ids",
            None,
        )
        if not callable(active_relations_for_row_ids):
            return []
        return _dedupe_relations(active_relations_for_row_ids(row_ids) or [])

    def _bank_transactions_from_relation(self, relation: dict[str, Any]) -> list[BankTransaction]:
        bank_ids = _relation_bank_ids(relation)
        if not bank_ids:
            raise OaPendingPaymentError(
                "active_relation_has_no_bank_transaction",
                "Active relation does not contain a bank transaction.",
                status_code=HTTPStatus.CONFLICT,
                details={"case_id": clean_string(relation.get("case_id") or "")},
            )
        outflows: list[BankTransaction] = []
        for bank_id in bank_ids:
            transaction = self._bank_transaction(bank_id)
            if _bank_direction(transaction) == "outflow":
                outflows.append(transaction)
        if not outflows:
            raise OaPendingPaymentError(
                "active_relation_has_no_bank_transaction",
                "Active relation does not contain an outflow bank transaction.",
                status_code=HTTPStatus.CONFLICT,
                details={"case_id": clean_string(relation.get("case_id") or "")},
            )
        return outflows

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

    def _confirm_formal_relation(
        self,
        records: list[OAApplicationRecord],
        bank_transactions: list[BankTransaction],
        *,
        actor_id: str,
        note: str,
        amount_check: dict[str, Any],
        idempotency_key: str | None,
        history_operation_type: str,
        history_note: str,
    ) -> dict[str, Any]:
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            raise OaPendingPaymentError(
                "workbench_relation_command_service_unavailable",
                "Workbench relation command service is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        if not records:
            raise OaPendingPaymentError("oa_row_ids_required", "At least one OA row is required.")
        bank_ids = [transaction.id for transaction in bank_transactions]
        oa_ids = [record.id for record in records]
        active_relations = self._active_relations_for_row_ids([*oa_ids, *bank_ids])
        if len(active_relations) > 1:
            raise OaPendingPaymentError(
                "workbench_relation_active_row_conflict",
                "Selected OA and bank rows belong to different active Workbench relations.",
                status_code=HTTPStatus.CONFLICT,
                details={
                    "conflicting_case_ids": sorted(
                        clean_string(relation.get("case_id") or "")
                        for relation in active_relations
                        if clean_string(relation.get("case_id") or "")
                    )
                },
            )
        before_relation = active_relations[0] if active_relations else None
        member_types = {
            row_id: row_type
            for row_id, row_type in zip(
                _relation_text_list(before_relation or {}, "row_ids", "rowIds"),
                _relation_text_sequence(before_relation or {}, "row_types", "rowTypes"),
                strict=False,
            )
        }
        for oa_id in oa_ids:
            member_types[oa_id] = "oa"
        for bank_id in bank_ids:
            member_types[bank_id] = "bank"
        row_ids = list(member_types)
        row_types = [member_types[row_id] for row_id in row_ids]
        all_bank_ids = [row_id for row_id, row_type in member_types.items() if row_type == "bank"]
        category_codes = (
            self._bank_transaction_category_codes_for_row_ids(all_bank_ids)
            if self._bank_transaction_category_codes_for_row_ids
            else {}
        )
        requirements = build_bank_relation_requirement_metadata(
            tag_codes=[category_codes.get(bank_id, "") for bank_id in all_bank_ids],
            rules_payload=(
                self._bank_flow_rule_tag_rules_payload()
                if self._bank_flow_rule_tag_rules_payload
                else {}
            ),
        )
        existing_metadata = (
            dict(before_relation.get("special_metadata") or {})
            if isinstance(before_relation, dict)
            and isinstance(before_relation.get("special_metadata"), dict)
            else {}
        )
        special_metadata = {
            **existing_metadata,
            **requirements,
            "origin": "oa_pending_payment",
        }
        try:
            return dict(
                confirm_relation(
                    case_id=(
                        clean_string(before_relation.get("case_id") or "")
                        if isinstance(before_relation, dict)
                        else _pending_payment_relation_id(oa_ids, bank_ids)
                    ),
                    row_ids=row_ids,
                    row_types=row_types,
                    relation_mode=(
                        clean_string(before_relation.get("relation_mode") or "")
                        if isinstance(before_relation, dict)
                        else "manual_confirmed"
                    ) or "manual_confirmed",
                    actor_id=actor_id,
                    month_scope=(
                        clean_string(before_relation.get("month_scope") or "")
                        if isinstance(before_relation, dict)
                        else _relation_month_scope(records)
                    ) or _relation_month_scope(records),
                    note=note or None,
                    amount_check=amount_check,
                    special_metadata=special_metadata,
                    idempotency_key=idempotency_key,
                    before_relations=active_relations,
                    replace_existing=bool(active_relations),
                    history_operation_type=history_operation_type,
                    history_note=history_note,
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

    def _mark_oa_paid_if_needed(self, flow_id: str) -> dict[str, Any] | None:
        assert self._payment_status_repository is not None
        try:
            status_record = self._payment_status_repository.get_payment_status(flow_id)
        except OAPaymentStatusError as exc:
            raise OaPendingPaymentError(
                "oa_payment_status_writeback_unavailable",
                "OA payment status writeback is unavailable.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                details={"flow_id": flow_id},
            ) from exc
        if status_record is not None and status_record.pay_status == PAY_STATUS_PAID:
            return None
        return self._mark_oa_paid(flow_id)

    def _record_paid_statuses(self, records: list[OAApplicationRecord]) -> bool:
        if not records:
            return False
        writer = getattr(self._payment_status_snapshot_writer, "record_paid_statuses", None)
        if not callable(writer):
            raise OaPendingPaymentError(
                "oa_payment_status_snapshot_writer_unavailable",
                "OA payment status snapshot writer is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        try:
            result = writer(records=records)
        except (ValueError, RuntimeError) as exc:
            raise OaPendingPaymentError(
                "oa_payment_status_snapshot_write_failed",
                "OA payment status was written externally but the page snapshot update failed; retry is safe.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
                details={"oa_row_ids": [record.id for record in records]},
            ) from exc
        return bool(tuple(getattr(result, "oa_pending_payment_changed_scopes", ()) or ()))

    def _writeback_paid_relations(
        self,
        records: list[OAApplicationRecord],
    ) -> tuple[list[dict[str, Any]], list[OAApplicationRecord]]:
        if not records:
            return [], []
        records_by_id = {record.id: record for record in records}
        relations = self._active_relations_for_row_ids(list(records_by_id))
        writebacks: list[dict[str, Any]] = []
        eligible_records: list[OAApplicationRecord] = []
        matched_relation_found = False
        for relation in relations:
            relation_oa_ids = _relation_oa_ids([relation])
            if not relation_oa_ids:
                continue
            relation_records = self._writeback_records(relation_oa_ids)
            if not relation_records:
                continue
            bank_transactions = self._bank_transactions_from_relation(relation)
            amount_check = self._relation_amount_check(relation_records, bank_transactions)
            if amount_check.get("matched") is not True:
                continue
            matched_relation_found = True
            for record in relation_records:
                if record.id not in records_by_id:
                    continue
                eligible_records.append(record)
                flow_id = self._resolve_oa_flow_id(record)
                writeback = self._mark_oa_paid_if_needed(flow_id)
                if writeback is not None:
                    writebacks.append({"record": record, "writeback": writeback, "source": "existing_relation"})
        if not matched_relation_found:
            raise OaPendingPaymentError(
                "oa_payment_status_not_paid",
                "Only paid OA rows with an active outflow bank relation can be written back.",
                status_code=HTTPStatus.CONFLICT,
                details={"oa_row_ids": list(records_by_id)},
            )
        return writebacks, _dedupe_records(eligible_records)

    def _resolve_oa_flow_ids(self, records: list[OAApplicationRecord]) -> list[str]:
        return [self._resolve_oa_flow_id(record) for record in records]

    def _mark_oa_flow_ids_paid(self, flow_ids: list[str]) -> list[dict[str, Any]]:
        return [self._mark_oa_paid(flow_id) for flow_id in flow_ids]


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
    explicit_ids = _relation_text_list(
        relation,
        "bank_transaction_ids",
        "bankTransactionIds",
        "bank_row_ids",
        "bankRowIds",
    )
    if explicit_ids:
        return explicit_ids
    return _relation_typed_ids(relation, "bank")


def _relation_oa_ids(relations: list[dict[str, Any]]) -> list[str]:
    oa_ids: list[str] = []
    for relation in relations:
        relation_oa_ids = _relation_text_list(relation, "oa_row_ids", "oaRowIds")
        if not relation_oa_ids:
            relation_oa_ids = _relation_typed_ids(relation, "oa")
        for oa_id in relation_oa_ids:
            if oa_id not in oa_ids:
                oa_ids.append(oa_id)
    return oa_ids


def _relation_typed_ids(relation: dict[str, Any], expected_type: str) -> list[str]:
    ids: list[str] = []
    row_ids = _relation_text_list(relation, "row_ids", "rowIds")
    row_types = _relation_text_sequence(relation, "row_types", "rowTypes")
    for index, row_id in enumerate(row_ids):
        row_type = clean_string(row_types[index] if index < len(row_types) else "")
        if not row_type:
            row_type = row_type_for_workbench_row_id(row_id)
        if row_type == expected_type and row_id not in ids:
            ids.append(row_id)
    return ids


def _relation_text_sequence(relation: dict[str, Any], *keys: str) -> list[str]:
    for key in keys:
        raw_values = relation.get(key)
        if isinstance(raw_values, list):
            return [clean_string(raw_value or "") for raw_value in raw_values]
    return []


def _relation_text_list(relation: dict[str, Any], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        raw_values = relation.get(key)
        if not isinstance(raw_values, list):
            continue
        for raw_value in raw_values:
            normalized = clean_string(raw_value or "")
            if normalized and normalized not in values:
                values.append(normalized)
    return values


def _dedupe_relations(relations: Any) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for relation in relations:
        if not isinstance(relation, dict):
            continue
        key = clean_string(
            relation.get("case_id")
            or relation.get("caseId")
            or relation.get("relation_id")
            or relation.get("relationId")
            or ""
        ) or "|".join(
            f"{row_type}:{row_id}"
            for row_id, row_type in zip(_relation_text_list(relation, "row_ids", "rowIds"), _relation_text_list(relation, "row_types", "rowTypes"))
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(relation)
    return deduped


def _dedupe_records(records: list[OAApplicationRecord]) -> list[OAApplicationRecord]:
    deduped: list[OAApplicationRecord] = []
    seen: set[str] = set()
    for record in records:
        if record.id in seen:
            continue
        seen.add(record.id)
        deduped.append(record)
    return deduped


def _public_writeback(item: dict[str, Any]) -> dict[str, Any]:
    writeback = dict(item.get("writeback") or {})
    record = item.get("record")
    if isinstance(record, OAApplicationRecord):
        writeback["oaRowId"] = record.id
    if item.get("source"):
        writeback["source"] = item["source"]
    return writeback


def _pending_payment_relation_id(oa_row_ids: list[str], bank_transaction_ids: list[str]) -> str:
    digest = sha1(
        "|".join([*sorted(set(oa_row_ids)), *sorted(set(bank_transaction_ids))]).encode("utf-8")
    ).hexdigest()[:16]
    return f"OA-PAY-{digest}"


def _relation_month_scope(records: list[OAApplicationRecord]) -> str:
    months = []
    for record in records:
        month = clean_string(record.month or "")
        scope_key = month[:7] if len(month) >= 7 and month[4] == "-" else ""
        if scope_key and scope_key not in months:
            months.append(scope_key)
    return months[0] if len(months) == 1 else "all"


def _optional_decimal(value: Any) -> Decimal | None:
    text = clean_string(value or "")
    if not text:
        return None
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


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

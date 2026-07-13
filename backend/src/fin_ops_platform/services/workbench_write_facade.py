from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
import logging
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE
from fin_ops_platform.services.workbench_idempotency import (
    WorkbenchIdempotencyFailed,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)
from fin_ops_platform.services.no_oa_bank_batch_application_service import NoOaBankBatchPersistenceError
from fin_ops_platform.services.oa_attachment_invoice_linking import oa_row_source_ids
from fin_ops_platform.services.read_model_write_targets import write_target_envelope
from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationConflict
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_modes import workbench_relations_have_same_row_set
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id
from fin_ops_platform.services.workbench_stale_precondition import assert_workbench_stale_preconditions
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


LOGGER = logging.getLogger(__name__)
_IDEMPOTENCY_FROM_PAYLOAD = object()


class _WorkbenchWritePersistenceError(RuntimeError):
    pass


def _normalize_actor_id(actor_id: object, *, fallback: str = "system") -> str:
    normalized = str(actor_id or fallback).strip()
    return normalized or fallback


def _normalize_tenant_id(tenant_id: object, *, fallback: str = "default") -> str:
    normalized = str(tenant_id or fallback).strip()
    return normalized or fallback


@dataclass(frozen=True)
class WorkbenchWriteResult:
    status_code: HTTPStatus
    payload: dict[str, object]


@dataclass(frozen=True)
class _WorkbenchWritePreconditionCommand:
    action_name: str
    expected_versions: dict[str, object]
    payload: dict[str, object]


@dataclass(frozen=True)
class _WorkbenchConfirmLinkCommand:
    action_name: str
    month: str
    row_ids: list[str]
    case_id: str
    scope_keys: list[str]
    payload: dict[str, object]
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    expected_versions: dict[str, object] | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    refresh_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class _WorkbenchCancelLinkCommand:
    action_name: str
    month: str
    row_id: str
    affected_row_ids: list[str]
    case_id: str
    scope_keys: list[str]
    payload: dict[str, object]
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    expected_versions: dict[str, object] | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    refresh_metadata: dict[str, object] | None = None


@dataclass(frozen=True)
class _WorkbenchWithdrawLinkCommand:
    action_name: str
    month: str
    row_ids: list[str]
    case_id: str
    scope_keys: list[str]
    payload: dict[str, object]
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    expected_versions: dict[str, object] | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    refresh_metadata: dict[str, object] | None = None
    timing_emit: Callable[[str, float, str | None], None] | None = None


CASH_PASS_THROUGH_MODE = "cash_pass_through"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
PERSONAL_ADVANCE_REPAYMENT_MODE = "personal_advance_repayment_settlement"


class WorkbenchWriteRelationReadSnapshotPort:
    def __init__(self, pair_relation_service: Any) -> None:
        self._pair_relation_service = pair_relation_service

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        return self._pair_relation_service.active_relations_for_row_ids(row_ids)

    def active_relation_by_row_id(self, row_id: str) -> dict[str, object] | None:
        relation = self._pair_relation_service.get_active_relation_by_row_id(row_id)
        return relation if isinstance(relation, dict) else None

    def preview_withdraw_for_row_ids(self, row_ids: list[str]) -> dict[str, object]:
        return self._pair_relation_service.preview_withdraw_for_row_ids(row_ids)

    def snapshot(self) -> dict[str, object]:
        snapshot = self._pair_relation_service.snapshot()
        return snapshot if isinstance(snapshot, dict) else {}


class WorkbenchWriteRelationSpecialMetadataMutationPort:
    def __init__(self, pair_relation_service: Any) -> None:
        self._pair_relation_service = pair_relation_service

    def update_special_metadata_for_row_ids(
        self,
        row_ids: list[str],
        *,
        special_metadata: dict[str, object],
        updated_by: str,
        note: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        updated_relation, history = self._pair_relation_service.update_special_metadata_for_row_ids(
            row_ids,
            special_metadata=special_metadata,
            updated_by=updated_by,
            note=note,
        )
        return dict(updated_relation), dict(history)

    def clear_special_metadata_for_row_ids(
        self,
        row_ids: list[str],
        *,
        updated_by: str,
        note: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        updated_relation, history = self._pair_relation_service.clear_special_metadata_for_row_ids(
            row_ids,
            updated_by=updated_by,
            note=note,
        )
        return dict(updated_relation), dict(history)


class WorkbenchWriteFacade:
    def __init__(
        self,
        *,
        relation_read_snapshot_port: WorkbenchWriteRelationReadSnapshotPort,
        relation_special_metadata_mutation_port: WorkbenchWriteRelationSpecialMetadataMutationPort,
        exception_service: Any,
        exception_case_service: Any,
        override_service: Any,
        candidate_match_service: Any,
        next_case_id: Callable[[], str],
        normalize_row_ids: Callable[[list[object]], list[str]],
        resolved_row_types_for_row_ids: Callable[..., list[str]],
        can_confirm_link_row_types: Callable[..., bool],
        expand_confirm_link_row_ids_for_existing_context: Callable[..., list[str]],
        amount_check_for_row_ids: Callable[..., dict[str, object]],
        resolve_rows_for_amount_check: Callable[..., list[dict[str, object]]],
        merge_relation_snapshots: Callable[..., list[dict[str, object]]],
        synthetic_existing_case_relations: Callable[..., list[dict[str, object]]],
        month_scope_for_selected_row_ids: Callable[..., str],
        scope_keys_for_row_ids: Callable[..., set[str]],
        scope_keys_for_rows: Callable[..., list[str]],
        resolve_live_rows_direct: Callable[..., list[dict[str, object]]],
        resolve_live_row: Callable[..., dict[str, object]],
        relation_groups: Callable[..., list[dict[str, object]]],
        withdraw_rows_and_after_relations: Callable[..., tuple[list[dict[str, object]], list[dict[str, object]], list[str]]],
        amount_check_for_rows_by_type: Callable[[dict[str, list[dict[str, object]]]], dict[str, object]],
        transaction_amount_for_row_id: Callable[[str], object],
        build_workbench_payload: Callable[..., dict[str, object]],
        build_ignored_rows_payload: Callable[..., list[dict[str, object]]],
        save_exception_cases_snapshot: Callable[[], None],
        persist_pair_relations: Callable[..., None],
        save_overrides_snapshot: Callable[..., None],
        persist_candidate_matches_best_effort: Callable[..., None],
        restore_exception_write_snapshots: Callable[..., None],
        restore_exception_override_snapshots: Callable[..., None],
        restore_exception_pair_snapshots: Callable[..., None],
        schedule_pair_relation_persist: Callable[..., None],
        consume_reconciliation_decisions: Callable[..., int],
        restore_pair_relation_snapshot: Callable[..., None],
        execute_derived_data_lifecycle_event: Callable[..., None],
        schedule_read_model_persist: Callable[..., None],
        emit_action_timing: Callable[..., None],
        confirm_link_uow: Any | None = None,
        cancel_link_uow: Any | None = None,
        withdraw_link_uow: Any | None = None,
        persist_pair_relations_in_transaction: Callable[..., None] | None = None,
        consume_reconciliation_decisions_in_transaction: Callable[..., int] | None = None,
        bank_transaction_category_codes_for_row_ids: Callable[[list[str]], dict[str, str]] | None = None,
        bank_flow_rule_tag_rules_payload: Callable[[], dict[str, object]] | None = None,
        submit_internal_transfer_rows_from_workbench: Callable[..., dict[str, object]] | None = None,
        relation_command_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
        reconciliation_decision_store: Any | None = None,
    ) -> None:
        self._relation_read_snapshot_port = relation_read_snapshot_port
        self._relation_special_metadata_mutation_port = relation_special_metadata_mutation_port
        self._exception_service = exception_service
        self._exception_case_service = exception_case_service
        self._override_service = override_service
        self._candidate_match_service = candidate_match_service
        self._next_case_id = next_case_id
        self._normalize_row_ids = normalize_row_ids
        self._resolved_row_types_for_row_ids = resolved_row_types_for_row_ids
        self._can_confirm_link_row_types = can_confirm_link_row_types
        self._expand_confirm_link_row_ids_for_existing_context = expand_confirm_link_row_ids_for_existing_context
        self._amount_check_for_row_ids = amount_check_for_row_ids
        self._resolve_rows_for_amount_check = resolve_rows_for_amount_check
        self._merge_relation_snapshots = merge_relation_snapshots
        self._synthetic_existing_case_relations = synthetic_existing_case_relations
        self._month_scope_for_selected_row_ids = month_scope_for_selected_row_ids
        self._scope_keys_for_row_ids = scope_keys_for_row_ids
        self._scope_keys_for_rows = scope_keys_for_rows
        self._resolve_live_rows_direct = resolve_live_rows_direct
        self._resolve_live_row = resolve_live_row
        self._relation_groups = relation_groups
        self._withdraw_rows_and_after_relations = withdraw_rows_and_after_relations
        self._amount_check_for_rows_by_type = amount_check_for_rows_by_type
        self._transaction_amount_for_row_id = transaction_amount_for_row_id
        self._build_workbench_payload = build_workbench_payload
        self._build_ignored_rows_payload = build_ignored_rows_payload
        self._save_exception_cases_snapshot = save_exception_cases_snapshot
        self._persist_pair_relations = persist_pair_relations
        self._save_overrides_snapshot = save_overrides_snapshot
        self._persist_candidate_matches_best_effort = persist_candidate_matches_best_effort
        self._restore_exception_write_snapshots = restore_exception_write_snapshots
        self._restore_exception_override_snapshots = restore_exception_override_snapshots
        self._restore_exception_pair_snapshots = restore_exception_pair_snapshots
        self._schedule_pair_relation_persist = schedule_pair_relation_persist
        self._consume_reconciliation_decisions = consume_reconciliation_decisions
        self._restore_pair_relation_snapshot = restore_pair_relation_snapshot
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event
        self._schedule_read_model_persist = schedule_read_model_persist
        self._emit_action_timing = emit_action_timing
        self._confirm_link_uow = confirm_link_uow
        self._cancel_link_uow = cancel_link_uow
        self._withdraw_link_uow = withdraw_link_uow
        self._persist_pair_relations_in_transaction = persist_pair_relations_in_transaction
        self._consume_reconciliation_decisions_in_transaction = consume_reconciliation_decisions_in_transaction
        self._bank_transaction_category_codes_for_row_ids = bank_transaction_category_codes_for_row_ids
        self._bank_flow_rule_tag_rules_payload = bank_flow_rule_tag_rules_payload
        self._submit_internal_transfer_rows_from_workbench = submit_internal_transfer_rows_from_workbench
        self._relation_command_service = relation_command_service
        self._relation_command_service_factory = relation_command_service_factory
        self._reconciliation_decision_store = reconciliation_decision_store

    def preview_confirm_link(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(str(exc)) from exc

        requested_row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        if not self._can_confirm_link_row_types(row_ids=row_ids, row_types=requested_row_types, month=month):
            raise ValueError("confirm link requires rows from at least two panes.")
        row_ids = self._expand_confirm_link_row_ids_for_existing_context(row_ids, month=month)
        row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
        rows_by_type = self._rows_by_type(rows)
        amount_check = self._amount_check_for_rows_by_type(rows_by_type)
        before_relations = self._relation_read_snapshot_port.active_relations_for_row_ids(row_ids)
        active_relation_preview = self._already_active_relation_preview(
            before_relations=before_relations,
            selected_row_ids=row_ids,
            selected_rows=rows,
            amount_check=amount_check,
            month=month,
        )
        if active_relation_preview is not None:
            return active_relation_preview

        before_groups = self._relation_groups(before_relations, selected_rows=rows, ungrouped_selected_rows="separate")
        case_id = str(payload.get("case_id") or "preview:confirm")
        after_relation = {
            "case_id": case_id,
            "row_ids": row_ids,
            "row_types": row_types,
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            "amount_check": amount_check,
            "special_metadata": self._bank_transaction_paired_policy_metadata(
                row_ids=row_ids,
                row_types=row_types,
                selected_rows=rows,
                amount_check=amount_check,
            ),
        }
        after_groups = self._relation_groups([after_relation], selected_rows=rows)
        requires_note = bool(amount_check.get("requires_note"))
        return {
            "operation": "confirm_link",
            "operation_type": "confirm_link",
            "can_submit": True,
            "requires_note": requires_note,
            "message": "金额不一致，请填写备注。" if requires_note else "",
            "before": {"groups": before_groups},
            "after": {"groups": after_groups},
            "amount_summary": {
                "before": amount_check,
                "after": amount_check,
                **amount_check,
            },
        }

    def _already_active_relation_preview(
        self,
        *,
        before_relations: list[dict[str, object]],
        selected_row_ids: list[str],
        selected_rows: list[dict[str, object]],
        amount_check: dict[str, object],
        month: str,
    ) -> dict[str, object] | None:
        if not before_relations:
            return None
        if len(before_relations) > 1:
            return None
        active_relation = dict(before_relations[0])
        active_row_ids = {
            str(row_id).strip()
            for row_id in list(active_relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        selected_ids = {str(row_id).strip() for row_id in list(selected_row_ids or []) if str(row_id).strip()}
        if not selected_ids or selected_ids != active_row_ids:
            return None

        relation_command = self._relation_command_service_for()
        if relation_command is not None:
            try:
                preview = self._preview_withdraw_relation_via_command_service(
                    relation_command,
                    row_ids=sorted(active_row_ids),
                    month=month,
                )
            except WorkbenchRelationCommandError as exc:
                return self._blocked_confirm_preview_payload(
                    before_relations=before_relations,
                    selected_rows=selected_rows,
                    amount_check=amount_check,
                    message=str(exc) or "所选记录已确认关联，但撤回预览暂时不可用。",
                )
            result = self._withdraw_relation_preview_payload(preview, month=month)
            result["message"] = result.get("message") or "所选记录已确认关联，可在此撤回这组配对关系。"
            return result

        try:
            preview = self._relation_read_snapshot_port.preview_withdraw_for_row_ids(sorted(active_row_ids))
        except Exception:
            return self._blocked_confirm_preview_payload(
                before_relations=before_relations,
                selected_rows=selected_rows,
                amount_check=amount_check,
                message="所选记录已确认关联，但撤回预览暂时不可用。",
            )
        active_relation = dict(preview.get("active_relation") or active_relation)
        preview_payload = {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": f"withdraw_relation:{active_relation.get('case_id') or 'active'}",
            "can_submit": True,
            "requires_note": False,
            "message": "所选记录已确认关联，可在此撤回这组配对关系。",
            "active_relation": active_relation,
            "before_relations": [active_relation],
            "after_relations": list(preview.get("after_relations") or []),
            "submit_expected_versions": {
                str(active_relation.get("case_id") or ""): active_relation.get("version", 1)
            },
        }
        return self._withdraw_relation_preview_payload(preview_payload, month=month)

    def _blocked_confirm_preview_payload(
        self,
        *,
        before_relations: list[dict[str, object]],
        selected_rows: list[dict[str, object]],
        amount_check: dict[str, object],
        message: str,
    ) -> dict[str, object]:
        return {
            "operation": "confirm_link",
            "operation_type": "confirm_link",
            "can_submit": False,
            "requires_note": False,
            "message": message,
            "before": {
                "groups": self._relation_groups(
                    before_relations,
                    selected_rows=selected_rows,
                    ungrouped_selected_rows="separate",
                )
            },
            "after": {"groups": []},
            "amount_summary": {
                "before": amount_check,
                "after": amount_check,
                **amount_check,
            },
        }

    def confirm_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "confirm_link"
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            case_id = str(payload["case_id"]) if payload.get("case_id") is not None else None
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_request", "message": str(exc)},
            )

        try:
            selected_rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
            rows_by_type = self._rows_by_type(selected_rows)
            requested_row_types = self._row_types_from_rows(row_ids, selected_rows, month=month)
            amount_check = self._amount_check_for_rows_by_type(rows_by_type)
            if not self._can_confirm_link_resolved_selection(row_types=requested_row_types, amount_check=amount_check):
                return WorkbenchWriteResult(
                    HTTPStatus.BAD_REQUEST,
                    {
                        "error": "invalid_confirm_link_request",
                        "message": "confirm link requires rows from at least two panes.",
                    },
                )
            row_ids = self._expand_confirm_link_row_ids_for_existing_context(row_ids, month=month)
            if set(row_ids) != {str(row.get("id") or "") for row in selected_rows}:
                selected_rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=True)
                rows_by_type = self._rows_by_type(selected_rows)
                amount_check = self._amount_check_for_rows_by_type(rows_by_type)
            row_types = self._row_types_from_rows(row_ids, selected_rows, month=month)
        except KeyError as exc:
            row_id = str(exc.args[0] if exc.args else "").strip()
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "workbench_row_not_found",
                    "message": f"所选关联台记录不可用，请刷新后重试。{f' row_id={row_id}' if row_id else ''}",
                    "row_id": row_id,
                },
            )
        if amount_check.get("requires_note") and not note:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "workbench_pair_relation_note_required",
                    "message": "金额不一致或方向不确定，请填写备注。",
                    "amount_check": amount_check,
                },
            )

        resolve_rows_started_at = monotonic()
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="resolve_rows",
            started_at=resolve_rows_started_at,
            detail=f"rows={len(row_ids)}",
        )

        resolved_case_id = case_id or self._next_case_id()
        before_relations = self._relation_read_snapshot_port.active_relations_for_row_ids(row_ids)
        internal_transfer_status = self._bank_only_internal_transfer_confirm_status(
            row_ids=row_ids,
            row_types=row_types,
            selected_rows=selected_rows,
        )
        if internal_transfer_status == "mixed":
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "no_oa_bank_batch_selection_internal_transfer_conflict",
                    "message": "内部往来流水必须与对应内部往来流水一起提交。",
                },
            )
        if internal_transfer_status == "all":
            return self._confirm_internal_transfer_rows_via_no_oa_batch(
                row_ids=row_ids,
                month=month,
                actor_id=actor_id,
                note=note,
                amount_check=amount_check,
            )
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                selected_rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
        previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
        changed_scope_keys = self._operation_scope_keys_for_rows_and_row_ids(
            month=month,
            rows=selected_rows,
            row_ids=row_ids,
            month_scope=month,
        )
        changed_case_ids = [
            *[str(relation.get("case_id", "")) for relation in before_relations if str(relation.get("case_id", "")).strip()],
            resolved_case_id,
        ]
        if self._confirm_link_uow is not None:
            return self._confirm_link_with_uow(
                payload=payload,
                request_id=request_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                month=month,
                row_ids=row_ids,
                row_types=row_types,
                resolved_case_id=resolved_case_id,
                note=note,
                amount_check=amount_check,
                selected_rows=selected_rows,
                history_before_relations=history_before_relations,
                previous_pair_snapshot=previous_pair_snapshot,
                changed_scope_keys=changed_scope_keys,
                changed_case_ids=changed_case_ids,
            )

        relation_command = self._relation_command_service_for()
        if relation_command is not None:
            pair_relation_started_at = monotonic()
            try:
                command_result = self._confirm_relation_via_command_service(
                    relation_command,
                    payload=payload,
                    case_id=resolved_case_id,
                    row_ids=row_ids,
                    row_types=row_types,
                    actor_id=actor_id,
                    month=month,
                    note=note,
                    amount_check=amount_check,
                    history_before_relations=history_before_relations,
                    idempotency_key=self._idempotency_key_from_payload(payload),
                    selected_rows=selected_rows,
                )
            except WorkbenchRelationCommandError as exc:
                return self._relation_command_error_result(exc)
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={resolved_case_id}",
            )
            schedule_started_at = monotonic()
            try:
                self._schedule_pair_relation_persist(
                    changed_case_ids=list(command_result.get("changed_case_ids") or changed_case_ids),
                    request_id=request_id,
                    action_name=action_name,
                )
                self._consume_reconciliation_decisions(
                    row_ids=row_ids,
                    relation_id=resolved_case_id,
                )
            except Exception:
                self._restore_pair_relation_snapshot(
                    previous_pair_snapshot,
                    changed_case_ids=changed_case_ids,
                )
                return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
            self._invalidate_and_schedule_read_model(
                action_name=action_name,
                changed_scope_keys=changed_scope_keys,
                metadata={
                    "source": action_name,
                    "case_id": resolved_case_id,
                    **self._relation_refresh_metadata(
                        relation=dict(
                            command_result.get("relation")
                            or {
                                "case_id": resolved_case_id,
                                "row_ids": list(row_ids),
                                "row_types": list(row_types),
                                "month_scope": month,
                            }
                        ),
                        row_ids=row_ids,
                        month=month,
                    ),
                },
                include_all=False,
                request_id=request_id,
                schedule_started_at=schedule_started_at,
            )
            return WorkbenchWriteResult(
                HTTPStatus.OK,
                self._confirm_link_response_payload(
                    self._confirm_link_result_with_operation_projection(
                        {
                            "success": True,
                            "action": action_name,
                            "month": month,
                            "case_id": resolved_case_id,
                            "affected_row_ids": list(row_ids),
                            "affected_months": list(command_result.get("affected_months") or changed_scope_keys),
                            "affected_scope_keys": list(
                                command_result.get("read_model_scope_keys")
                                or command_result.get("affected_months")
                                or changed_scope_keys
                            ),
                            "amount_check": amount_check,
                            "message": f"已确认 {len(row_ids)} 条记录关联。",
                        },
                        case_id=resolved_case_id,
                        row_ids=row_ids,
                        row_types=row_types,
                        selected_rows=selected_rows,
                        month=month,
                        amount_check=amount_check,
                    )
                ),
            )

        return self._relation_command_unavailable_result()

    def _confirm_link_with_uow(
        self,
        *,
        payload: dict[str, object],
        request_id: str | None,
        actor_id: str | None,
        tenant_id: str | None,
        month: str,
        row_ids: list[str],
        row_types: list[str],
        resolved_case_id: str,
        note: str,
        amount_check: dict[str, object],
        selected_rows: list[dict[str, object]],
        history_before_relations: list[dict[str, object]],
        previous_pair_snapshot: dict[str, object],
        changed_scope_keys: list[str],
        changed_case_ids: list[str],
    ) -> WorkbenchWriteResult:
        action_name = "confirm_link"
        idempotency_key = str(
            payload.get("idempotency_key") or payload.get("request_idempotency_key") or ""
        ).strip() or None
        expected_versions = payload.get("expected_versions") if isinstance(payload.get("expected_versions"), dict) else {}
        relation_refresh_metadata = self._relation_refresh_metadata(
            relation={
                "case_id": resolved_case_id,
                "row_ids": list(row_ids),
                "row_types": list(row_types),
                "month_scope": month,
            },
            row_ids=row_ids,
            month=month,
        )
        command = _WorkbenchConfirmLinkCommand(
            action_name=action_name,
            month=month,
            row_ids=list(row_ids),
            case_id=resolved_case_id,
            scope_keys=list(changed_scope_keys),
            payload=dict(payload),
            idempotency_key=idempotency_key,
            expected_versions=dict(expected_versions),
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            refresh_metadata={
                "source": action_name,
                "case_id": resolved_case_id,
                **relation_refresh_metadata,
            },
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            if self._persist_pair_relations_in_transaction is None:
                raise _WorkbenchWritePersistenceError("confirm-link UoW requires transaction-bound pair relation persistence.")
            pair_relation_started_at = monotonic()
            relation_command = self._relation_command_service_for(repository=getattr(ctx, "pair_relations", None))
            if relation_command is None:
                raise _WorkbenchWritePersistenceError("workbench_relation_command_unavailable")
            self._confirm_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id=resolved_case_id,
                row_ids=row_ids,
                row_types=row_types,
                actor_id=actor_id,
                month=month,
                note=note,
                amount_check=amount_check,
                history_before_relations=history_before_relations,
                idempotency_key=None,
                selected_rows=selected_rows,
            )
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={resolved_case_id}",
            )
            if self._consume_reconciliation_decisions_in_transaction is not None:
                self._consume_reconciliation_decisions_in_transaction(
                    transaction=transaction,
                    row_ids=row_ids,
                    relation_id=resolved_case_id,
                )
            else:
                self._consume_reconciliation_decisions(
                    row_ids=row_ids,
                    relation_id=resolved_case_id,
                )
            return {
                "success": True,
                "action": action_name,
                "month": month,
                "case_id": resolved_case_id,
                "affected_row_ids": list(row_ids),
                "affected_months": list(changed_scope_keys),
                "affected_scope_keys": list(changed_scope_keys),
                "amount_check": amount_check,
                "message": f"已确认 {len(row_ids)} 条记录关联。",
            }

        try:
            result = self._confirm_link_uow.run(command, handler)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(exc.status_code), dict(conflict_payload["payload"]))
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except Exception:
            LOGGER.exception(
                "Workbench confirm-link UoW failed.",
                extra={
                    "workbench_write": {
                        "action": action_name,
                        "case_id": resolved_case_id,
                        "row_count": len(row_ids),
                        "scope_count": len(changed_scope_keys),
                        "request_id": request_id,
                    }
                },
            )
            self._restore_pair_relation_snapshot(
                previous_pair_snapshot,
                changed_case_ids=changed_case_ids,
            )
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            self._confirm_link_response_payload(
                self._confirm_link_result_with_operation_projection(
                    result,
                    case_id=resolved_case_id,
                    row_ids=row_ids,
                    row_types=row_types,
                    selected_rows=selected_rows,
                    month=month,
                    amount_check=amount_check,
                )
            ),
        )

    def _confirm_relation_via_command_service(
        self,
        relation_command: Any,
        *,
        payload: dict[str, object],
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        actor_id: str | None,
        month: str,
        note: str,
        amount_check: dict[str, object],
        history_before_relations: list[dict[str, object]],
        idempotency_key: str | None,
        selected_rows: list[dict[str, object]],
    ) -> dict[str, object]:
        confirm_relation = getattr(relation_command, "confirm_relation", None)
        if not callable(confirm_relation):
            raise _WorkbenchWritePersistenceError("relation command service must expose confirm_relation.")
        return confirm_relation(
            case_id=case_id,
            row_ids=list(row_ids),
            row_types=list(row_types),
            relation_mode="manual_confirmed",
            actor_id=_normalize_actor_id(actor_id),
            month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            note=note,
            amount_check=dict(amount_check or {}),
            special_metadata=self._bank_transaction_paired_policy_metadata(
                row_ids=row_ids,
                row_types=row_types,
                selected_rows=selected_rows,
                amount_check=amount_check,
            ),
            idempotency_key=idempotency_key,
            before_relations=list(history_before_relations),
            replace_existing=True,
            history_operation_type="confirm_link",
        )

    def _bank_only_internal_transfer_confirm_status(
        self,
        *,
        row_ids: list[str],
        row_types: list[str],
        selected_rows: list[dict[str, object]],
    ) -> str:
        if not row_ids or set(row_types) != {"bank"}:
            return "none"
        categories_by_row_id: dict[str, str] = {}
        if self._bank_transaction_category_codes_for_row_ids is not None:
            categories_by_row_id.update(self._bank_transaction_category_codes_for_row_ids(row_ids))
        for row in selected_rows:
            if not isinstance(row, dict) or str(row.get("type") or "") != "bank":
                continue
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if not row_id or categories_by_row_id.get(row_id):
                continue
            category_code = str(row.get("category_code") or row.get("effective_category_code") or "").strip()
            if category_code:
                categories_by_row_id[row_id] = category_code
        selected_codes = [str(categories_by_row_id.get(row_id) or "").strip() for row_id in row_ids]
        has_internal_transfer = any(code == "internal_transfer" for code in selected_codes)
        if not has_internal_transfer:
            return "none"
        return "all" if all(code == "internal_transfer" for code in selected_codes) else "mixed"

    def _confirm_internal_transfer_rows_via_no_oa_batch(
        self,
        *,
        row_ids: list[str],
        month: str,
        actor_id: str | None,
        note: str,
        amount_check: dict[str, object],
    ) -> WorkbenchWriteResult:
        if self._submit_internal_transfer_rows_from_workbench is None:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "no_oa_bank_batch_internal_transfer_submit_unavailable",
                    "message": "内部往来免OA提交入口不可用。",
                },
            )
        try:
            result = self._submit_internal_transfer_rows_from_workbench(
                row_ids=list(row_ids),
                actor=_normalize_actor_id(actor_id),
                note=note or None,
            )
        except ValueError as exc:
            error_code = str(exc).strip() or "invalid_no_oa_bank_batch_request"
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": error_code, "message": error_code},
            )
        except NoOaBankBatchPersistenceError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {
                    "error": exc.error_code,
                    "message": str(exc) or "免OA流水批次保存失败，请稍后重试。",
                },
            )
        batch = dict(result.get("batch") or {})
        relation = dict(result.get("pair_relation") or {})
        case_id = str(relation.get("case_id") or batch.get("relation_case_id") or batch.get("batch_id") or "").strip()
        affected_row_ids = [
            str(row_id).strip()
            for row_id in list(batch.get("row_ids") or row_ids)
            if str(row_id).strip()
        ]
        affected_months = [
            str(month_value).strip()
            for month_value in list(result.get("affected_months") or [month])
            if str(month_value).strip()
        ]
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_link",
                "month": month,
                "case_id": case_id,
                "affected_row_ids": affected_row_ids,
                "affected_months": affected_months,
                "affected_scope_keys": affected_months,
                "amount_check": amount_check,
                "message": f"已确认 {len(affected_row_ids)} 条记录关联。",
            },
        )

    @staticmethod
    def _confirm_link_response_payload(result: dict[str, object]) -> dict[str, object]:
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(result)
        return {
            "success": bool(result.get("success")),
            "action": "confirm_link",
            "month": str(result.get("month") or ""),
            "case_id": str(result.get("case_id") or ""),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "affected_months": list(result.get("affected_months") or []),
            "affected_scope_keys": affected_scope_keys,
            **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
            "amount_check": dict(result.get("amount_check") or {}),
            "operation_projection": dict(result.get("operation_projection") or {}),
            "message": str(result.get("message") or ""),
        }

    def _confirm_link_result_with_operation_projection(
        self,
        result: dict[str, object],
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        selected_rows: list[dict[str, object]],
        month: str,
        amount_check: dict[str, object],
    ) -> dict[str, object]:
        payload = dict(result)
        if isinstance(payload.get("operation_projection"), dict) and payload.get("operation_projection"):
            return payload
        payload["operation_projection"] = self._confirm_link_operation_projection(
            case_id=case_id,
            row_ids=row_ids,
            row_types=row_types,
            selected_rows=selected_rows,
            month=month,
            amount_check=amount_check,
        )
        return payload

    def _confirm_link_operation_projection(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        selected_rows: list[dict[str, object]],
        month: str,
        amount_check: dict[str, object],
    ) -> dict[str, object]:
        after_relation = {
            "case_id": case_id,
            "row_ids": list(row_ids),
            "row_types": list(row_types),
            "status": "active",
            "relation_mode": "manual_confirmed",
            "month_scope": self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            "amount_check": dict(amount_check or {}),
            "special_metadata": self._bank_transaction_paired_policy_metadata(
                row_ids=row_ids,
                row_types=row_types,
                selected_rows=selected_rows,
                amount_check=amount_check,
            ),
        }
        after_groups = self._relation_groups([after_relation], selected_rows=selected_rows)
        if self._confirm_link_projection_is_paired(
            row_types=row_types,
            amount_check=amount_check,
            special_metadata=after_relation["special_metadata"],
        ):
            paired_groups = after_groups
            open_groups: list[dict[str, object]] = []
        else:
            paired_groups = []
            open_groups = after_groups
        return {
            "after": {
                "paired_groups": paired_groups,
                "open_groups": open_groups,
            }
        }

    @staticmethod
    def _confirm_link_projection_is_paired(
        *,
        row_types: list[str],
        amount_check: dict[str, object],
        special_metadata: dict[str, object] | None = None,
    ) -> bool:
        normalized_types = {
            str(row_type or "").strip()
            for row_type in list(row_types or [])
            if str(row_type or "").strip()
        }
        if "bank" in normalized_types:
            metadata = special_metadata if isinstance(special_metadata, dict) else {}
            requires_oa = bool(metadata.get("requires_oa", True))
            requires_invoice = bool(metadata.get("requires_invoice", True))
            return (
                (not requires_oa or "oa" in normalized_types)
                and (not requires_invoice or "invoice" in normalized_types)
            )
        if {"oa", "bank", "invoice"}.issubset(normalized_types):
            return True
        external_etc_batch_id = str((amount_check or {}).get("external_etc_batch_id") or "").strip()
        return bool(external_etc_batch_id and {"oa", "bank"}.issubset(normalized_types))

    def _bank_transaction_paired_policy_metadata(
        self,
        *,
        row_ids: list[str],
        row_types: list[str],
        selected_rows: list[dict[str, object]],
        amount_check: dict[str, object] | None = None,
    ) -> dict[str, object]:
        bank_row_ids = self._bank_row_ids_from_relation(row_ids=row_ids, row_types=row_types)
        if not bank_row_ids:
            return {}
        payload = self._bank_flow_rule_tag_rules_payload() if self._bank_flow_rule_tag_rules_payload else {}
        requirements_by_tag_code = self._bank_flow_rule_requirements_by_tag_code(payload)
        category_codes = self._bank_category_codes_for_policy(bank_row_ids, selected_rows)
        requires_oa = False
        requires_invoice = False
        tag_codes: list[str] = []
        for row_id in bank_row_ids:
            tag_code = str(category_codes.get(row_id) or "").strip()
            if tag_code:
                tag_codes.append(tag_code)
            requirement = requirements_by_tag_code.get(tag_code)
            if isinstance(requirement, dict):
                row_requires_oa = bool(requirement.get("requires_oa"))
                row_requires_invoice = bool(requirement.get("requires_invoice"))
            elif self._is_etc_confirm_link_amount_check(amount_check) or self._selected_rows_include_etc_batch_oa(selected_rows):
                row_requires_oa = True
                row_requires_invoice = False
            else:
                row_requires_oa = True
                row_requires_invoice = True
            requires_oa = requires_oa or row_requires_oa
            requires_invoice = requires_invoice or row_requires_invoice
        metadata: dict[str, object] = {
            "paired_requirement_source": "bank_transaction_paired_policy",
            "paired_requirement_tag_codes": self._dedupe_ordered(tag_codes),
            "paired_requirement_version": self._positive_int((payload or {}).get("version"), default=1),
            "requires_oa": requires_oa,
            "requires_invoice": requires_invoice,
        }
        if len(metadata["paired_requirement_tag_codes"]) == 1:
            metadata["paired_requirement_tag_code"] = metadata["paired_requirement_tag_codes"][0]
        return metadata

    @staticmethod
    def _is_etc_confirm_link_amount_check(amount_check: dict[str, object] | None) -> bool:
        if not isinstance(amount_check, dict):
            return False
        return bool(str(amount_check.get("external_etc_batch_id") or amount_check.get("etc_batch_id") or "").strip())

    @staticmethod
    def _selected_rows_include_etc_batch_oa(selected_rows: list[dict[str, object]]) -> bool:
        for row in selected_rows:
            if not isinstance(row, dict) or str(row.get("type") or "").strip() != "oa":
                continue
            if str(row.get("source") or "").strip() == "etc_batch":
                return True
            if str(row.get("etc_batch_id") or row.get("etcBatchId") or "").strip():
                return True
        return False

    def _bank_category_codes_for_policy(
        self,
        bank_row_ids: list[str],
        selected_rows: list[dict[str, object]],
    ) -> dict[str, str]:
        categories_by_row_id: dict[str, str] = {}
        for row in selected_rows:
            if not isinstance(row, dict) or str(row.get("type") or "").strip() != "bank":
                continue
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if not row_id or categories_by_row_id.get(row_id):
                continue
            category_code = str(row.get("category_code") or row.get("effective_category_code") or "").strip()
            if category_code:
                categories_by_row_id[row_id] = category_code
        missing_row_ids = [row_id for row_id in bank_row_ids if row_id and row_id not in categories_by_row_id]
        if missing_row_ids and self._bank_transaction_category_codes_for_row_ids is not None:
            categories_by_row_id.update(self._bank_transaction_category_codes_for_row_ids(missing_row_ids))
        return categories_by_row_id

    @staticmethod
    def _bank_row_ids_from_relation(*, row_ids: list[str], row_types: list[str]) -> list[str]:
        normalized_row_ids = [str(row_id or "").strip() for row_id in list(row_ids or [])]
        normalized_row_types = [str(row_type or "").strip() for row_type in list(row_types or [])]
        if len(normalized_row_ids) == len(normalized_row_types):
            return [
                row_id
                for row_id, row_type in zip(normalized_row_ids, normalized_row_types)
                if row_id and row_type == "bank"
            ]
        return [
            row_id
            for row_id in normalized_row_ids
            if row_id and row_type_for_workbench_row_id(row_id) == "bank"
        ]

    @staticmethod
    def _bank_flow_rule_requirements_by_tag_code(payload: dict[str, object]) -> dict[str, dict[str, bool]]:
        requirements: dict[str, dict[str, bool]] = {}
        for item in list((payload or {}).get("rules") or []):
            if not isinstance(item, dict):
                continue
            tag_code = str(item.get("tag_code") or item.get("code") or "").strip()
            if tag_code:
                requirements[tag_code] = {
                    "requires_oa": bool(item.get("requires_oa")),
                    "requires_invoice": bool(item.get("requires_invoice")),
                }
        raw_requirements = (payload or {}).get("requirements_by_tag_code")
        if isinstance(raw_requirements, dict):
            for raw_code, item in raw_requirements.items():
                tag_code = str(raw_code or "").strip()
                if tag_code and isinstance(item, dict):
                    requirements[tag_code] = {
                        "requires_oa": bool(item.get("requires_oa")),
                        "requires_invoice": bool(item.get("requires_invoice")),
                    }
        return requirements

    @staticmethod
    def _positive_int(value: object, *, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    @staticmethod
    def _dedupe_ordered(values: list[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    @staticmethod
    def _operation_affected_scope_keys(result: dict[str, object]) -> list[str]:
        raw_scope_keys = (
            result.get("affected_scope_keys")
            or result.get("read_model_scope_keys")
            or result.get("affected_months")
            or result.get("changed_scopes")
            or []
        )
        return WorkbenchWriteFacade._normalize_operation_scope_keys(list(raw_scope_keys))

    @staticmethod
    def _normalize_operation_scope_keys(scope_keys: list[object]) -> list[str]:
        normalized: list[str] = []
        for scope_key in list(scope_keys):
            value = str(scope_key or "").strip()
            if not value or value == "all" or value in normalized:
                continue
            normalized.append(value)
        return normalized

    def _operation_scope_keys_for_rows_and_row_ids(
        self,
        *,
        month: str,
        rows: list[dict[str, object]],
        row_ids: list[str],
        month_scope: str | None = None,
    ) -> list[str]:
        return self._normalize_operation_scope_keys([
            *self._scope_keys_for_rows(month=month, rows=rows),
            *self._scope_keys_for_row_ids(month=month, row_ids=row_ids, month_scope=month_scope or ""),
        ])

    def _withdraw_changed_scope_keys(
        self,
        *,
        month: str,
        active_relation: dict[str, object],
        preview: dict[str, object],
        affected_row_ids: list[str],
    ) -> list[str]:
        changed_scope_keys = self._normalize_operation_scope_keys(
            list(preview.get("affected_months") or preview.get("read_model_scope_keys") or [])
        )
        if changed_scope_keys:
            return changed_scope_keys

        month_scope = str(active_relation.get("month_scope") or "")
        changed_scope_keys = self._operation_scope_keys_for_rows_and_row_ids(
            month=month,
            rows=[],
            row_ids=affected_row_ids,
            month_scope=month_scope,
        )
        if changed_scope_keys:
            return changed_scope_keys

        try:
            alias_map = self._withdraw_selected_row_alias_map(affected_row_ids, month=month)
            before_relations = [
                self._canonicalize_withdraw_relation(dict(relation), alias_map=alias_map)
                for relation in list(preview.get("before_relations") or [])
                if isinstance(relation, dict)
            ]
            canonical_active_relation = before_relations[0] if before_relations else self._canonicalize_withdraw_relation(
                active_relation,
                alias_map=alias_map,
            )
            canonical_after_relations = [
                self._canonicalize_withdraw_relation(dict(relation), alias_map=alias_map)
                for relation in list(preview.get("after_relations") or [])
                if isinstance(relation, dict)
            ]
            rows, _synthetic_after_relations, _affected_row_ids = self._withdraw_rows_and_after_relations(
                active_relation=canonical_active_relation,
                after_relations=canonical_after_relations,
                month=month,
            )
        except (TypeError, ValueError, IndexError, KeyError):
            return []
        return self._operation_scope_keys_for_rows_and_row_ids(
            month=month,
            rows=rows,
            row_ids=affected_row_ids,
            month_scope=month_scope,
        )

    @staticmethod
    def _operation_freshness_targets(scope_keys: list[str]) -> list[dict[str, str]]:
        return [
            {"read_model_key": read_model_key, "scope_key": scope_key}
            for scope_key in scope_keys
            for read_model_key in ("workbench", "workbench_relation")
        ]

    @staticmethod
    def _operation_write_target_envelope(scope_keys: list[str]) -> dict[str, object]:
        return write_target_envelope(
            scope_keys=scope_keys,
            targets=WorkbenchWriteFacade._operation_freshness_targets(scope_keys),
        )

    def _relation_command_service_for(self, *, repository: Any | None = None) -> Any | None:
        if self._relation_command_service_factory is not None:
            try:
                return self._relation_command_service_factory(repository=repository)
            except TypeError:
                return self._relation_command_service_factory(repository)
        return self._relation_command_service

    @staticmethod
    def _relation_command_unavailable_result() -> WorkbenchWriteResult:
        return WorkbenchWriteResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "workbench_relation_command_unavailable",
                "message": "Workbench relation command service is not configured.",
            },
        )

    @staticmethod
    def _relation_command_error_result(exc: WorkbenchRelationCommandError) -> WorkbenchWriteResult:
        if exc.error_code == "workbench_relation_preview_conflict":
            return WorkbenchWriteFacade._relation_preview_conflict_result(exc)
        conflict_errors = {
            "workbench_relation_active_row_conflict",
            "workbench_relation_idempotency_conflict",
            "workbench_relation_multiple_groups_selected",
            "workbench_relation_read_model_not_fresh",
        }
        unavailable_errors = {
            "workbench_relation_command_unavailable",
            "workbench_relation_read_model_unavailable",
            "workbench_relation_repository_unavailable",
        }
        status_code = HTTPStatus.BAD_REQUEST
        if exc.error_code in conflict_errors:
            status_code = HTTPStatus.CONFLICT
        if exc.error_code in unavailable_errors:
            status_code = HTTPStatus.SERVICE_UNAVAILABLE
        payload: dict[str, object] = {"error": exc.error_code, "message": exc.message}
        payload.update(exc.payload)
        return WorkbenchWriteResult(status_code, payload)

    @staticmethod
    def _relation_preview_conflict_result(exc: WorkbenchRelationCommandError) -> WorkbenchWriteResult:
        reason = str(exc.payload.get("reason") or "stale_relation_identity").strip() or "stale_relation_identity"
        expected: dict[str, object] = {}
        actual: dict[str, object] = {}
        expected_versions = exc.payload.get("expected_versions")
        current_expected_versions = exc.payload.get("current_expected_versions")
        if isinstance(expected_versions, dict):
            expected.update(expected_versions)
        if isinstance(current_expected_versions, dict):
            actual.update(current_expected_versions)
        preview_id = str(exc.payload.get("preview_id") or "").strip()
        current_preview_id = str(exc.payload.get("current_preview_id") or "").strip()
        if preview_id:
            expected["preview_id"] = preview_id
        if current_preview_id:
            actual["preview_id"] = current_preview_id
        conflict = WorkbenchWriteConflict(
            action="withdraw_link",
            reason=reason,
            expected=expected,
            actual=actual,
            message=f"409 workbench_write_conflict: {reason}",
        )
        response = conflict.to_response_payload()
        return WorkbenchWriteResult(HTTPStatus.CONFLICT, dict(response["payload"]))

    def cancel_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "cancel_link"
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            _comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_link_request", "message": str(exc)},
            )

        replayed = self._cancel_link_replay_if_committed(
            payload=payload,
            month=month,
            row_id=row_id,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        if replayed is not None:
            return replayed

        resolve_rows_started_at = monotonic()
        active_relation = self._relation_read_snapshot_port.active_relation_by_row_id(row_id)
        if not isinstance(active_relation, dict):
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_pair_relation_not_found", "message": row_id},
            )
        conflict = self._cancel_link_stale_conflict(payload, active_relation)
        if conflict is not None:
            conflict_payload = conflict.to_response_payload()
            return WorkbenchWriteResult(
                HTTPStatus(conflict.status_code),
                dict(conflict_payload["payload"]),
            )
        affected_row_ids = self._normalize_row_ids(list(active_relation.get("row_ids") or []))
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="resolve_rows",
            started_at=resolve_rows_started_at,
            detail=f"rows={len(affected_row_ids)}",
        )
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=affected_row_ids,
                month_scope=str(active_relation.get("month_scope") or ""),
            )
        )
        changed_case_ids = [str(active_relation.get("case_id") or "")]
        if self._cancel_link_uow is not None:
            return self._cancel_link_with_uow(
                payload=payload,
                request_id=request_id,
                actor_id=actor_id,
                tenant_id=tenant_id,
                month=month,
                row_id=row_id,
                active_relation=active_relation,
                affected_row_ids=affected_row_ids,
                changed_scope_keys=changed_scope_keys,
                changed_case_ids=changed_case_ids,
            )

        relation_command = self._relation_command_service_for()
        if relation_command is not None:
            previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
            pair_relation_started_at = monotonic()
            try:
                command_result = self._cancel_relation_via_command_service(
                    relation_command,
                    payload=payload,
                    case_id=str(active_relation.get("case_id") or ""),
                    actor_id=actor_id,
                    reason=_comment,
                    idempotency_key=self._idempotency_key_from_payload(payload),
                )
            except WorkbenchRelationCommandError as exc:
                return self._relation_command_error_result(exc)
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"row_id={row_id}",
            )
            schedule_started_at = monotonic()
            try:
                self._schedule_pair_relation_persist(
                    changed_case_ids=list(command_result.get("changed_case_ids") or changed_case_ids),
                    request_id=request_id,
                    action_name=action_name,
                )
                self._invalidate_and_schedule_read_model(
                    action_name=action_name,
                    changed_scope_keys=changed_scope_keys,
                    metadata={
                        "source": action_name,
                        "case_id": str(active_relation.get("case_id") or ""),
                        **self._relation_refresh_metadata(
                            relation=active_relation,
                            row_ids=affected_row_ids,
                            month=month,
                        ),
                    },
                    request_id=request_id,
                    schedule_started_at=schedule_started_at,
                )
            except Exception:
                self._restore_pair_relation_snapshot(
                    previous_pair_snapshot,
                    changed_case_ids=changed_case_ids,
                )
                return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
            return WorkbenchWriteResult(
                HTTPStatus.OK,
                self._cancel_link_response_payload(
                    {
                        "success": True,
                        "action": action_name,
                        "month": month,
                        "case_id": str(active_relation.get("case_id") or ""),
                        "affected_row_ids": affected_row_ids,
                        "affected_months": list(command_result.get("affected_months") or changed_scope_keys),
                        "message": "已取消关联并回退为待处理。",
                    }
                ),
            )

        return self._relation_command_unavailable_result()

    def _cancel_link_replay_if_committed(
        self,
        *,
        payload: dict[str, object],
        month: str,
        row_id: str,
        actor_id: str | None,
        tenant_id: str | None,
    ) -> WorkbenchWriteResult | None:
        if self._cancel_link_uow is None:
            return None
        command = _WorkbenchCancelLinkCommand(
            action_name="cancel_link",
            month=month,
            row_id=row_id,
            affected_row_ids=[],
            case_id="",
            scope_keys=[],
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
        )
        replay_committed = getattr(self._cancel_link_uow, "replay_committed", None)
        if not callable(replay_committed):
            return None
        try:
            result = replay_committed(command)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        if result is None:
            return None
        return WorkbenchWriteResult(HTTPStatus.OK, self._cancel_link_response_payload(result))

    def _cancel_link_with_uow(
        self,
        *,
        payload: dict[str, object],
        request_id: str | None,
        actor_id: str | None,
        tenant_id: str | None,
        month: str,
        row_id: str,
        active_relation: dict[str, object],
        affected_row_ids: list[str],
        changed_scope_keys: list[str],
        changed_case_ids: list[str],
    ) -> WorkbenchWriteResult:
        action_name = "cancel_link"
        previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
        command = _WorkbenchCancelLinkCommand(
            action_name=action_name,
            month=month,
            row_id=row_id,
            affected_row_ids=list(affected_row_ids),
            case_id=str(active_relation.get("case_id") or ""),
            scope_keys=list(changed_scope_keys),
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            refresh_metadata={
                "source": action_name,
                "case_id": str(active_relation.get("case_id") or ""),
                **self._relation_refresh_metadata(
                    relation=active_relation,
                    row_ids=affected_row_ids,
                    month=month,
                ),
            },
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            relation_command = self._relation_command_service_for(repository=getattr(ctx, "pair_relations", None))
            if relation_command is None:
                raise _WorkbenchWritePersistenceError("workbench_relation_command_unavailable")
            pair_relation_started_at = monotonic()
            self._cancel_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id=str(active_relation.get("case_id") or ""),
                actor_id=actor_id,
                reason=str(payload.get("comment") or "") if payload.get("comment") is not None else None,
                idempotency_key=None,
            )
            cancelled_relation = active_relation
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"row_id={row_id}",
            )
            if not isinstance(cancelled_relation, dict):
                raise _WorkbenchWritePersistenceError("cancel-link relation disappeared during UoW handler.")
            return {
                "success": True,
                "action": action_name,
                "month": month,
                "case_id": str(active_relation.get("case_id") or ""),
                "affected_row_ids": list(affected_row_ids),
                "affected_months": list(changed_scope_keys),
                "affected_scope_keys": list(changed_scope_keys),
                "message": "已取消关联并回退为待处理。",
            }

        try:
            result = self._cancel_link_uow.run(command, handler)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(exc.status_code), dict(conflict_payload["payload"]))
        except Exception:
            self._restore_pair_relation_snapshot(
                previous_pair_snapshot,
                changed_case_ids=changed_case_ids,
            )
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(HTTPStatus.OK, self._cancel_link_response_payload(result))

    def _cancel_relation_via_command_service(
        self,
        relation_command: Any,
        *,
        payload: dict[str, object],
        case_id: str,
        actor_id: str | None,
        reason: str | None,
        idempotency_key: str | None,
    ) -> dict[str, object]:
        _ = payload
        cancel_relation = getattr(relation_command, "cancel_relation", None)
        if not callable(cancel_relation):
            raise _WorkbenchWritePersistenceError("relation command service must expose cancel_relation.")
        return cancel_relation(
            case_id=case_id,
            actor_id=_normalize_actor_id(actor_id),
            reason=reason,
            idempotency_key=idempotency_key,
            history_operation_type="cancel_link",
        )

    @staticmethod
    def _cancel_link_response_payload(result: dict[str, object]) -> dict[str, object]:
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(result)
        return {
            "success": bool(result.get("success")),
            "action": "cancel_link",
            "month": str(result.get("month") or ""),
            "case_id": str(result.get("case_id") or ""),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "affected_months": list(result.get("affected_months") or []),
            "affected_scope_keys": affected_scope_keys,
            **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
            "message": str(result.get("message") or ""),
        }

    @staticmethod
    def _idempotency_key_from_payload(payload: dict[str, object]) -> str | None:
        return str(payload.get("idempotency_key") or payload.get("request_idempotency_key") or "").strip() or None

    def _cancel_link_stale_conflict(
        self,
        payload: dict[str, object],
        active_relation: dict[str, object],
    ) -> WorkbenchWriteConflict | None:
        expected_versions = payload.get("expected_versions")
        if not isinstance(expected_versions, dict) or not expected_versions:
            return None
        try:
            assert_workbench_stale_preconditions(
                _WorkbenchWritePreconditionCommand(
                    action_name="cancel_link",
                    expected_versions=dict(expected_versions),
                    payload={
                        "current_relation_case_id": str(active_relation.get("case_id") or ""),
                        "current_relation_version": active_relation.get("version"),
                    },
                )
            )
        except WorkbenchWriteConflict as exc:
            return exc
        return None

    def _ignore_row_stale_conflict(
        self,
        payload: dict[str, object],
        row: dict[str, object],
    ) -> WorkbenchWriteConflict | None:
        expected_versions = payload.get("expected_versions")
        if not isinstance(expected_versions, dict) or not expected_versions:
            return None
        row_id = str(row.get("id") or "")
        active_relation = self._relation_read_snapshot_port.active_relation_by_row_id(row_id)
        current_row_status = "confirmed" if isinstance(active_relation, dict) else "open"
        try:
            assert_workbench_stale_preconditions(
                _WorkbenchWritePreconditionCommand(
                    action_name="ignore_row",
                    expected_versions=dict(expected_versions),
                    payload={"current_row_status": current_row_status},
                )
            )
        except WorkbenchWriteConflict as exc:
            return exc
        return None

    def _cash_special_stale_conflict(
        self,
        *,
        action_name: str,
        payload: dict[str, object],
        relation: dict[str, object],
    ) -> WorkbenchWriteConflict | None:
        expected_versions = payload.get("expected_versions")
        if not isinstance(expected_versions, dict) or not expected_versions:
            return None
        try:
            assert_workbench_stale_preconditions(
                _WorkbenchWritePreconditionCommand(
                    action_name=action_name,
                    expected_versions=dict(expected_versions),
                    payload={
                        "current_relation_case_id": str(relation.get("case_id") or ""),
                        "current_relation_version": relation.get("version"),
                    },
                )
            )
        except WorkbenchWriteConflict as exc:
            return exc
        return None

    def preview_withdraw_link(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._withdraw_row_ids(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_preview_request", "message": str(exc)},
            )

        relation_command = self._relation_command_service_for()
        if relation_command is None:
            return self._relation_command_unavailable_result()
        try:
            preview_relation = self._preview_withdraw_relation_via_command_service(
                relation_command,
                row_ids=row_ids,
                month=month,
            )
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        except (TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_preview_request", "message": str(exc)},
            )
        return WorkbenchWriteResult(HTTPStatus.OK, self._withdraw_relation_preview_payload(preview_relation, month=month))

    def withdraw_link(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
        actor_id: str | None = None,
        tenant_id: str | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "withdraw_link"
        try:
            month = str(payload["month"])
            row_ids = self._withdraw_row_ids(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_request", "message": str(exc)},
            )

        operation_type = str(payload.get("operation_type") or "withdraw_relation").strip()
        if operation_type != "withdraw_relation":
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_withdraw_link_request",
                    "message": f"Unsupported withdraw operation_type: {operation_type or '<empty>'}.",
                },
            )

        replayed = self._withdraw_link_replay_if_committed(
            payload=payload,
            month=month,
            row_ids=row_ids,
            actor_id=actor_id,
            tenant_id=tenant_id,
        )
        if replayed is not None:
            return replayed

        relation_command = self._relation_command_service_for()
        if relation_command is None:
            return self._relation_command_unavailable_result()
        if self._withdraw_link_uow is not None:
            try:
                alias_started_at = monotonic()
                row_id_aliases = self._withdraw_selected_row_alias_map(row_ids, month=month)
                self._emit_timing_if_requested(
                    request_id=request_id,
                    action_name="withdraw_link",
                    phase="withdraw_alias_map",
                    started_at=alias_started_at,
                    detail=f"row_count={len(row_ids)}",
                )
                return self._withdraw_link_with_uow_from_row_ids(
                    payload=payload,
                    request_id=request_id,
                    actor_id=actor_id,
                    tenant_id=tenant_id,
                    month=month,
                    row_ids=row_ids,
                    note=note,
                    row_id_aliases=row_id_aliases,
                )
            except WorkbenchRelationCommandError as exc:
                return self._relation_command_error_result(exc)
            except _WorkbenchWritePersistenceError as exc:
                return self._persistence_unavailable_result(str(exc))
            except (TypeError, ValueError, KeyError) as exc:
                return WorkbenchWriteResult(
                    HTTPStatus.BAD_REQUEST,
                    {"error": "invalid_withdraw_link_request", "message": str(exc)},
                )
        try:
            row_id_aliases = self._withdraw_selected_row_alias_map(row_ids, month=month)
            preview = self._preview_withdraw_relation_via_command_service(
                relation_command,
                row_ids=row_ids,
                month=month,
                row_id_aliases=row_id_aliases,
            )
            active_relation = dict(preview.get("active_relation") or {})
            case_id = str(active_relation.get("case_id") or "").strip()
            if not case_id:
                raise ValueError("active relation case_id is required.")
            operation_projection: dict[str, object] = {}
            previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
            result = self._withdraw_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id=case_id,
                actor_id=actor_id,
                reason=note,
                row_id_aliases=row_id_aliases,
            )
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        except (TypeError, ValueError, KeyError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_request", "message": str(exc)},
            )
        changed_case_ids = list(result.get("changed_case_ids") or [case_id])
        affected_row_ids = self._canonicalize_withdraw_row_ids(
            list(result.get("affected_row_ids") or row_ids),
            selected_row_ids=row_ids,
            month=month,
            alias_map=row_id_aliases,
        )
        restored_relations = self._canonicalize_withdraw_relations(
            list(result.get("restored_relations") or []),
            selected_row_ids=row_ids,
            month=month,
            alias_map=row_id_aliases,
        )
        restored_relations = self._withdraw_restored_relations_excluding_active(
            restored_relations,
            active_relation=self._canonical_withdraw_active_relation(
                preview=preview,
                active_relation=active_relation,
                alias_map=row_id_aliases,
            ),
        )
        changed_scope_keys = self._withdraw_changed_scope_keys(
            month=month,
            active_relation=active_relation,
            preview={
                **preview,
                "affected_months": result.get("affected_months") or result.get("read_model_scope_keys") or [],
            },
            affected_row_ids=affected_row_ids,
        )
        schedule_started_at = monotonic()
        try:
            self._schedule_pair_relation_persist(
                changed_case_ids=changed_case_ids,
                request_id=request_id,
                action_name=action_name,
            )
            self._invalidate_and_schedule_read_model(
                action_name=action_name,
                changed_scope_keys=changed_scope_keys,
                metadata={
                    "source": action_name,
                    "case_id": case_id,
                    **self._relation_refresh_metadata(
                        relation=active_relation,
                        row_ids=affected_row_ids,
                        month=month,
                    ),
                },
                include_all=False,
                request_id=request_id,
                schedule_started_at=schedule_started_at,
            )
        except Exception:
            self._restore_pair_relation_snapshot(
                previous_pair_snapshot,
                changed_case_ids=changed_case_ids,
            )
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "operation": "withdraw_link",
                "action": "withdraw_link",
                "month": month,
                "case_id": case_id,
                "changed_scopes": changed_scope_keys,
                "affected_months": changed_scope_keys,
                "affected_scope_keys": changed_scope_keys,
                "affected_row_ids": affected_row_ids,
                "restored_relations": restored_relations,
                "operation_projection": operation_projection,
                "message": "已撤回 1 组关联。",
            },
        )

    def _withdraw_link_replay_if_committed(
        self,
        *,
        payload: dict[str, object],
        month: str,
        row_ids: list[str],
        actor_id: str | None,
        tenant_id: str | None,
    ) -> WorkbenchWriteResult | None:
        if self._withdraw_link_uow is None:
            return None
        command = _WorkbenchWithdrawLinkCommand(
            action_name="withdraw_link",
            month=month,
            row_ids=list(row_ids),
            case_id="",
            scope_keys=[],
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
        )
        replay_committed = getattr(self._withdraw_link_uow, "replay_committed", None)
        if not callable(replay_committed):
            return None
        try:
            result = replay_committed(command)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        if result is None:
            return None
        return WorkbenchWriteResult(HTTPStatus.OK, self._withdraw_link_response_payload(result))

    def _withdraw_link_with_uow(
        self,
        *,
        payload: dict[str, object],
        request_id: str | None,
        actor_id: str | None,
        tenant_id: str | None,
        month: str,
        row_ids: list[str],
        active_relation: dict[str, object],
        case_id: str,
        preview: dict[str, object],
        note: str,
        row_id_aliases: dict[str, str] | None = None,
        operation_projection: dict[str, object] | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "withdraw_link"
        affected_row_ids = list(preview.get("affected_row_ids") or active_relation.get("row_ids") or row_ids)
        changed_scope_keys = self._withdraw_changed_scope_keys(
            month=month,
            active_relation=active_relation,
            preview=preview,
            affected_row_ids=affected_row_ids,
        )
        relation_refresh_metadata = self._relation_refresh_metadata(
            relation=active_relation,
            row_ids=affected_row_ids,
            month=month,
        )
        command = _WorkbenchWithdrawLinkCommand(
            action_name=action_name,
            month=month,
            row_ids=list(row_ids),
            case_id=case_id,
            scope_keys=list(changed_scope_keys),
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            refresh_metadata={
                "source": action_name,
                "case_id": case_id,
                **relation_refresh_metadata,
            },
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            relation_command = self._relation_command_service_for(repository=getattr(ctx, "pair_relations", None))
            if relation_command is None:
                raise _WorkbenchWritePersistenceError("workbench_relation_command_unavailable")
            pair_relation_started_at = monotonic()
            result = self._withdraw_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id=case_id,
                actor_id=actor_id,
                reason=note,
                idempotency_key=None,
                row_id_aliases=row_id_aliases,
            )
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={case_id}",
            )
            canonical_affected_row_ids = self._canonicalize_withdraw_row_ids(
                list(result.get("affected_row_ids") or affected_row_ids),
                selected_row_ids=row_ids,
                month=month,
                alias_map=row_id_aliases,
            )
            canonical_restored_relations = self._canonicalize_withdraw_relations(
                list(result.get("restored_relations") or []),
                selected_row_ids=row_ids,
                month=month,
                alias_map=row_id_aliases,
            )
            canonical_restored_relations = self._withdraw_restored_relations_excluding_active(
                canonical_restored_relations,
                active_relation=self._canonical_withdraw_active_relation(
                    preview=preview,
                    active_relation=active_relation,
                    alias_map=row_id_aliases or {},
                ),
            )
            return {
                "success": True,
                "operation": action_name,
                "action": action_name,
                "month": month,
                "case_id": case_id,
                "changed_scopes": list(result.get("affected_months") or changed_scope_keys),
                "affected_months": list(result.get("affected_months") or changed_scope_keys),
                "affected_scope_keys": list(result.get("affected_months") or changed_scope_keys),
                "affected_row_ids": canonical_affected_row_ids,
                "restored_relations": canonical_restored_relations,
                "operation_projection": dict(operation_projection or {}),
                "message": "已撤回 1 组关联。",
            }

        try:
            result = self._withdraw_link_uow.run(command, handler)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(exc.status_code), dict(conflict_payload["payload"]))
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except Exception:
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(HTTPStatus.OK, self._withdraw_link_response_payload(result))

    def _withdraw_link_with_uow_from_row_ids(
        self,
        *,
        payload: dict[str, object],
        request_id: str | None,
        actor_id: str | None,
        tenant_id: str | None,
        month: str,
        row_ids: list[str],
        note: str,
        row_id_aliases: dict[str, str] | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "withdraw_link"
        def emit_phase_timing(phase: str, started_at: float, detail: str | None = None) -> None:
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase=phase,
                started_at=started_at,
                detail=detail,
            )

        command = _WorkbenchWithdrawLinkCommand(
            action_name=action_name,
            month=month,
            row_ids=list(row_ids),
            case_id="",
            scope_keys=[],
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            refresh_metadata={"source": action_name},
            timing_emit=emit_phase_timing,
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            relation_command = self._relation_command_service_for(repository=getattr(ctx, "pair_relations", None))
            if relation_command is None:
                raise _WorkbenchWritePersistenceError("workbench_relation_command_unavailable")
            pair_relation_started_at = monotonic()
            result = self._withdraw_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id="",
                actor_id=actor_id,
                reason=note,
                idempotency_key=None,
                row_id_aliases=row_id_aliases,
                row_ids=row_ids,
            )
            before_relation = dict(result.get("before_relation") or result.get("relation") or {})
            case_id = str(result.get("case_id") or before_relation.get("case_id") or "").strip()
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={case_id}",
            )
            postprocess_started_at = monotonic()
            affected_row_ids = self._canonicalize_withdraw_row_ids(
                list(result.get("affected_row_ids") or before_relation.get("row_ids") or row_ids),
                selected_row_ids=row_ids,
                month=month,
                alias_map=row_id_aliases,
            )
            restored_relations = self._canonicalize_withdraw_relations(
                list(result.get("restored_relations") or []),
                selected_row_ids=row_ids,
                month=month,
                alias_map=row_id_aliases,
            )
            if before_relation:
                restored_relations = self._withdraw_restored_relations_excluding_active(
                    restored_relations,
                    active_relation=self._canonicalize_withdraw_relation(
                        before_relation,
                        alias_map=row_id_aliases or {},
                    ),
                )
            changed_scope_keys = self._normalize_operation_scope_keys(
                list(result.get("affected_months") or result.get("read_model_scope_keys") or [])
            )
            if not changed_scope_keys:
                changed_scope_keys = self._withdraw_changed_scope_keys(
                    month=month,
                    active_relation=before_relation,
                    preview={
                        "affected_months": result.get("affected_months") or [],
                        "read_model_scope_keys": result.get("read_model_scope_keys") or [],
                    },
                    affected_row_ids=affected_row_ids,
                )
            metadata_started_at = monotonic()
            refresh_metadata = {
                "source": action_name,
                "case_id": case_id,
                **self._relation_refresh_metadata(
                    relation=before_relation,
                    row_ids=affected_row_ids,
                    month=month,
                    resolve_rows=False,
                ),
            }
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="relation_refresh_metadata",
                started_at=metadata_started_at,
                detail=f"scope_count={len(changed_scope_keys)}",
            )
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="withdraw_postprocess",
                started_at=postprocess_started_at,
                detail=f"scope_count={len(changed_scope_keys)}",
            )
            return {
                "success": True,
                "operation": action_name,
                "action": action_name,
                "month": month,
                "case_id": case_id,
                "changed_scopes": changed_scope_keys,
                "affected_months": changed_scope_keys,
                "affected_scope_keys": changed_scope_keys,
                "affected_row_ids": affected_row_ids,
                "restored_relations": restored_relations,
                "operation_projection": {},
                "refresh_metadata": refresh_metadata,
                "message": "已撤回 1 组关联。",
            }

        try:
            result = self._withdraw_link_uow.run(command, handler)
        except WorkbenchIdempotencyKeyConflict as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyInProgress as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchIdempotencyFailed as exc:
            return WorkbenchWriteResult(HTTPStatus.CONFLICT, exc.to_response_payload())
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(exc.status_code), dict(conflict_payload["payload"]))
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except Exception:
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(HTTPStatus.OK, self._withdraw_link_response_payload(result))

    @staticmethod
    def _withdraw_link_response_payload(result: dict[str, object]) -> dict[str, object]:
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(result)
        return {
            "success": bool(result.get("success")),
            "operation": "withdraw_link",
            "action": "withdraw_link",
            "month": str(result.get("month") or ""),
            "case_id": str(result.get("case_id") or ""),
            "changed_scopes": list(result.get("changed_scopes") or result.get("affected_months") or []),
            "affected_months": list(result.get("affected_months") or result.get("changed_scopes") or []),
            "affected_scope_keys": affected_scope_keys,
            **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "restored_relations": list(result.get("restored_relations") or []),
            "operation_projection": dict(result.get("operation_projection") or {}),
            "message": str(result.get("message") or "已撤回 1 组关联。"),
        }

    def _withdraw_link_operation_projection(
        self,
        *,
        preview: dict[str, object],
        month: str,
        alias_map: dict[str, str] | None = None,
    ) -> dict[str, object]:
        preview_payload = self._withdraw_relation_preview_payload(preview, month=month, alias_map=alias_map)
        after = dict(preview_payload.get("after") or {})
        return {
            "after": {
                "paired_groups": [],
                "open_groups": list(after.get("groups") or []),
            }
        }

    def _preview_withdraw_relation_via_command_service(
        self,
        relation_command: Any,
        *,
        row_ids: list[str],
        month: str,
        row_id_aliases: dict[str, str] | None = None,
    ) -> dict[str, object]:
        preview_withdraw_relation = getattr(relation_command, "preview_withdraw_relation", None)
        if not callable(preview_withdraw_relation):
            raise _WorkbenchWritePersistenceError("relation command service must expose preview_withdraw_relation.")
        preview = dict(
            preview_withdraw_relation(
                row_ids=list(row_ids),
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
                row_id_aliases=row_id_aliases
                if row_id_aliases is not None
                else self._withdraw_selected_row_alias_map(row_ids, month=month),
            )
            or {}
        )
        preview["selected_row_ids"] = list(row_ids)
        return preview

    def _withdraw_relation_via_command_service(
        self,
        relation_command: Any,
        *,
        payload: dict[str, object],
        case_id: str,
        actor_id: str | None,
        reason: str | None,
        idempotency_key: str | None | object = _IDEMPOTENCY_FROM_PAYLOAD,
        row_id_aliases: dict[str, str] | None = None,
        row_ids: list[str] | None = None,
    ) -> dict[str, object]:
        withdraw_relation = getattr(relation_command, "withdraw_relation", None)
        if not callable(withdraw_relation):
            raise _WorkbenchWritePersistenceError("relation command service must expose withdraw_relation.")
        resolved_idempotency_key = (
            self._idempotency_key_from_payload(payload)
            if idempotency_key is _IDEMPOTENCY_FROM_PAYLOAD
            else idempotency_key
        )
        return dict(
            withdraw_relation(
                case_id=case_id,
                actor_id=_normalize_actor_id(actor_id),
                row_ids=list(row_ids or []),
                reason=reason,
                idempotency_key=resolved_idempotency_key,
                history_operation_type="withdraw_link",
                preview_id=str(payload.get("preview_id") or "").strip() or None,
                operation_type=str(payload.get("operation_type") or "withdraw_relation").strip(),
                expected_versions=dict(payload.get("expected_versions") or {})
                if isinstance(payload.get("expected_versions"), dict)
                else None,
                row_id_aliases=row_id_aliases,
            )
            or {}
        )

    def _withdraw_relation_preview_payload(
        self,
        preview: dict[str, object],
        *,
        month: str,
        alias_map: dict[str, str] | None = None,
    ) -> dict[str, object]:
        can_submit = bool(preview.get("can_submit", True))
        selected_row_ids = [
            str(row_id)
            for row_id in list(preview.get("selected_row_ids") or [])
            if str(row_id).strip()
        ]
        selected_alias_map = alias_map if alias_map is not None else self._withdraw_selected_row_alias_map(
            selected_row_ids,
            month=month,
        )
        before_relations = [
            dict(relation)
            for relation in list(preview.get("before_relations") or [])
            if isinstance(relation, dict)
        ]
        if not before_relations:
            active_identity = dict(preview.get("active_relation") or {})
            before_relations = [active_identity] if active_identity else []
        after_relations = [
            dict(relation)
            for relation in list(preview.get("after_relations") or [])
            if isinstance(relation, dict)
        ]
        before_relations = self._canonicalize_withdraw_relations(
            before_relations,
            selected_row_ids=selected_row_ids,
            month=month,
            alias_map=selected_alias_map,
        )
        after_relations = self._canonicalize_withdraw_relations(
            after_relations,
            selected_row_ids=selected_row_ids,
            month=month,
            alias_map=selected_alias_map,
        )
        active_relation = before_relations[0] if before_relations else {}
        if can_submit:
            after_relations = self._withdraw_restored_relations_excluding_active(
                after_relations,
                active_relation=active_relation,
            )
        rows, _synthetic_after_relations, _affected_row_ids = self._withdraw_rows_and_after_relations(
            active_relation=active_relation,
            after_relations=after_relations,
            month=month,
        )
        before_groups = self._relation_groups(before_relations, selected_rows=rows)
        after_groups = self._relation_groups(
            after_relations,
            selected_rows=rows,
            ungrouped_selected_rows="individual",
        )
        amount_check = self._amount_check_for_withdraw_preview(
            active_relation=active_relation,
            rows=rows,
        )
        return {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": str(preview.get("preview_id") or ""),
            "can_submit": can_submit,
            "requires_note": bool(preview.get("requires_note")),
            "message": str(preview.get("message") or ""),
            "before": {"groups": before_groups},
            "after": {"groups": after_groups},
            "amount_summary": {
                "before": amount_check,
                "after": amount_check,
                **amount_check,
            },
            "restored_relations": after_relations,
            "active_relation": self._canonicalize_withdraw_relation(
                dict(preview.get("active_relation") or {}),
                alias_map=selected_alias_map,
            ),
            "submit_expected_versions": dict(preview.get("submit_expected_versions") or {}),
        }

    def _canonicalize_withdraw_relations(
        self,
        relations: list[object],
        *,
        selected_row_ids: list[str],
        month: str,
        alias_map: dict[str, str] | None = None,
    ) -> list[dict[str, object]]:
        resolved_alias_map = alias_map if alias_map is not None else self._withdraw_selected_row_alias_map(
            selected_row_ids,
            month=month,
        )
        return [
            self._canonicalize_withdraw_relation(dict(relation), alias_map=resolved_alias_map)
            for relation in list(relations or [])
            if isinstance(relation, dict)
        ]

    def _canonical_withdraw_active_relation(
        self,
        *,
        preview: dict[str, object],
        active_relation: dict[str, object],
        alias_map: dict[str, str],
    ) -> dict[str, object]:
        before_relations = [
            dict(relation)
            for relation in list(preview.get("before_relations") or [])
            if isinstance(relation, dict)
        ]
        relation = before_relations[0] if before_relations else active_relation
        return self._canonicalize_withdraw_relation(dict(relation or {}), alias_map=alias_map)

    @staticmethod
    def _withdraw_restored_relations_excluding_active(
        relations: list[dict[str, object]],
        *,
        active_relation: dict[str, object],
    ) -> list[dict[str, object]]:
        if not active_relation:
            return [dict(relation) for relation in list(relations or [])]
        return [
            dict(relation)
            for relation in list(relations or [])
            if (
                not workbench_relations_have_same_row_set(relation, active_relation)
                or WorkbenchWriteFacade._relation_contains_immutable_oa_attachment_binding(relation)
            )
        ]

    @staticmethod
    def _relation_contains_immutable_oa_attachment_binding(relation: dict[str, object]) -> bool:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            return False
        return (
            special_metadata.get("immutable_oa_attachment_binding") is True
            or special_metadata.get("contains_immutable_oa_attachment_binding") is True
        )

    def _canonicalize_withdraw_row_ids(
        self,
        row_ids: list[object],
        *,
        selected_row_ids: list[str],
        month: str,
        alias_map: dict[str, str] | None = None,
    ) -> list[str]:
        resolved_alias_map = alias_map if alias_map is not None else self._withdraw_selected_row_alias_map(
            selected_row_ids,
            month=month,
        )
        normalized: list[str] = []
        for row_id in list(row_ids or []):
            value = str(row_id or "").strip()
            if not value:
                continue
            canonical = resolved_alias_map.get(value, value)
            if canonical not in normalized:
                normalized.append(canonical)
        return normalized

    def _withdraw_selected_row_alias_map(self, selected_row_ids: list[str], *, month: str) -> dict[str, str]:
        normalized_selected_row_ids = [
            str(row_id or "").strip()
            for row_id in list(selected_row_ids or [])
            if str(row_id or "").strip()
        ]
        alias_map = {row_id: row_id for row_id in normalized_selected_row_ids}
        if not normalized_selected_row_ids:
            return alias_map
        if all(row_type_for_workbench_row_id(row_id, unknown="") != "oa" for row_id in normalized_selected_row_ids):
            return alias_map
        try:
            selected_rows = self._resolve_live_rows_direct(normalized_selected_row_ids, month_hint=month)
        except Exception:
            return alias_map
        for row in list(selected_rows or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if not row_id:
                continue
            alias_map[row_id] = row_id
            if str(row.get("type") or "").strip() != "oa":
                continue
            for source_id in oa_row_source_ids(row):
                alias = str(source_id or "").strip()
                if alias:
                    alias_map.setdefault(alias, row_id)
        return alias_map

    @staticmethod
    def _canonicalize_withdraw_relation(
        relation: dict[str, object],
        *,
        alias_map: dict[str, str],
    ) -> dict[str, object]:
        if not relation or not alias_map:
            return dict(relation or {})
        normalized = dict(relation)
        raw_row_ids = list(normalized.get("row_ids") or [])
        if not raw_row_ids:
            return normalized
        raw_row_types = list(normalized.get("row_types") or [])
        row_ids: list[str] = []
        row_types: list[object] = []
        for index, raw_row_id in enumerate(raw_row_ids):
            value = str(raw_row_id or "").strip()
            if not value:
                continue
            canonical = alias_map.get(value, value)
            if canonical in row_ids:
                continue
            row_ids.append(canonical)
            if index < len(raw_row_types):
                row_types.append(raw_row_types[index])
        normalized["row_ids"] = row_ids
        if raw_row_types:
            normalized["row_types"] = row_types
        return normalized

    def confirm_cash_pass_through(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._cash_special_row_ids(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids)
            conflict = self._cash_special_stale_conflict(
                action_name="confirm_cash_pass_through",
                payload=payload,
                relation=relation,
            )
            if conflict is not None:
                conflict_payload = conflict.to_response_payload()
                return WorkbenchWriteResult(HTTPStatus(conflict.status_code), dict(conflict_payload["payload"]))
            self._validate_cash_pass_through_relation(relation)
            cash_amount = self._cash_special_cash_amount(payload, relation)
            special_metadata = {
                "special_type": CASH_PASS_THROUGH_MODE,
                "cash_amount": cash_amount,
                "ticket_cost_amount": "0.00",
                "cost_policy": "exclude_all",
                "note": note,
                "created_by": "system",
                "updated_by": "system",
            }
            updated_relation, _history = self._relation_special_metadata_mutation_port.update_special_metadata_for_row_ids(
                row_ids,
                special_metadata=special_metadata,
                updated_by="system",
                note=note,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cash_pass_through_request", "message": str(exc)},
            )
        affected_scope_keys = self._after_cash_special_relation_update(
            month=month,
            relation=updated_relation,
            request_id=request_id,
            action_name="confirm_cash_pass_through",
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_cash_pass_through",
                "month": month,
                "case_id": str(updated_relation.get("case_id") or ""),
                "affected_row_ids": list(updated_relation.get("row_ids") or []),
                "affected_months": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "special_metadata": dict(updated_relation.get("special_metadata") or {}),
                "message": "已确认现金往来过账。",
            },
        )

    def confirm_cash_ticket_purchase(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._cash_special_row_ids(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids)
            conflict = self._cash_special_stale_conflict(
                action_name="confirm_cash_ticket_purchase",
                payload=payload,
                relation=relation,
            )
            if conflict is not None:
                conflict_payload = conflict.to_response_payload()
                return WorkbenchWriteResult(HTTPStatus(conflict.status_code), dict(conflict_payload["payload"]))
            self._validate_cash_ticket_purchase_relation(relation)
            ticket_cost_amount = self._required_non_negative_amount(payload.get("ticket_cost_amount"), "ticket_cost_amount")
            cash_amount = self._required_non_negative_amount(payload.get("cash_amount"), "cash_amount")
            project_id = str(payload.get("project_id") or "").strip()
            project_name = str(payload.get("project_name") or "").strip()
            if Decimal(ticket_cost_amount) > Decimal("0.00") and not (project_id or project_name):
                raise ValueError("project_id or project_name is required when ticket_cost_amount is greater than 0.")
            special_metadata = {
                "special_type": CASH_TICKET_PURCHASE_MODE,
                "cash_amount": cash_amount,
                "ticket_cost_amount": ticket_cost_amount,
                "project_id": project_id,
                "project_name": project_name,
                "cost_policy": "include_ticket_cost_only",
                "note": note,
                "created_by": "system",
                "updated_by": "system",
            }
            updated_relation, _history = self._relation_special_metadata_mutation_port.update_special_metadata_for_row_ids(
                row_ids,
                special_metadata=special_metadata,
                updated_by="system",
                note=note,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cash_ticket_purchase_request", "message": str(exc)},
            )
        affected_scope_keys = self._after_cash_special_relation_update(
            month=month,
            relation=updated_relation,
            request_id=request_id,
            action_name="confirm_cash_ticket_purchase",
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_cash_ticket_purchase",
                "month": month,
                "case_id": str(updated_relation.get("case_id") or ""),
                "affected_row_ids": list(updated_relation.get("row_ids") or []),
                "affected_months": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "special_metadata": dict(updated_relation.get("special_metadata") or {}),
                "message": "已确认现金往来买票情况。",
            },
        )

    def cancel_cash_special(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._cash_special_row_ids(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids)
            conflict = self._cash_special_stale_conflict(
                action_name="cancel_cash_special",
                payload=payload,
                relation=relation,
            )
            if conflict is not None:
                conflict_payload = conflict.to_response_payload()
                return WorkbenchWriteResult(HTTPStatus(conflict.status_code), dict(conflict_payload["payload"]))
            updated_relation, _history = self._relation_special_metadata_mutation_port.clear_special_metadata_for_row_ids(
                row_ids,
                updated_by="system",
                note=note,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_cash_special_request", "message": str(exc)},
            )
        affected_scope_keys = self._after_cash_special_relation_update(
            month=month,
            relation=updated_relation,
            request_id=request_id,
            action_name="cancel_cash_special",
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_cash_special",
                "month": month,
                "case_id": str(updated_relation.get("case_id") or ""),
                "affected_row_ids": list(updated_relation.get("row_ids") or []),
                "affected_months": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "special_metadata": dict(updated_relation.get("special_metadata") or {}),
                "message": "已取消现金往来特殊处理。",
            },
        )

    def update_bank_exception(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            relation_code = str(payload["relation_code"])
            relation_label = str(payload["relation_label"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_update_bank_exception_request", "message": str(exc)},
            )

        try:
            rows = self._resolve_live_rows_direct([row_id], month_hint=month)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )
        row = rows[0]
        if row.get("type") != "bank":
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_update_bank_exception_request", "message": "update_bank_exception only supports bank rows."},
            )
        return self._legacy_exception_result(
            month=month,
            row_ids=[row_id],
            action_name="update_bank_exception",
            invalid_error_code="invalid_update_bank_exception_request",
            legacy_payload={
                "note": comment or relation_label,
                "legacy_relation_code": relation_code,
                "legacy_relation_label": relation_label,
            },
            response_message="已更新银行异常分类。",
        )

    def oa_bank_exception(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            exception_code = str(payload["exception_code"])
            exception_label = str(payload["exception_label"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": str(exc)},
            )

        try:
            rows = self._resolve_live_rows_direct(row_ids, month_hint=month)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        if not rows:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": "row_ids is required."},
            )
        if any(str(row.get("type")) == "invoice" for row in rows):
            return self._oa_bank_exception_with_invoice(
                month=month,
                row_ids=row_ids,
                exception_code=exception_code,
                exception_label=exception_label,
                comment=comment,
            )

        return self._legacy_exception_result(
            month=month,
            row_ids=row_ids,
            action_name="oa_bank_exception",
            invalid_error_code="invalid_oa_bank_exception_request",
            legacy_payload={
                "note": comment or exception_label,
                "legacy_exception_code": exception_code,
                "legacy_exception_label": exception_label,
            },
            response_message=f"已对 {len(rows)} 条记录执行 OA/流水异常处理。",
        )

    def confirm_personal_advance_repayment(
        self,
        payload: dict[str, object],
        *,
        request_id: str | None = None,
    ) -> WorkbenchWriteResult:
        action_name = "confirm_personal_advance_repayment"
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_personal_advance_repayment_request", "message": str(exc)},
            )

        try:
            rows = self._resolve_live_rows_direct(row_ids, month_hint=month)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        amount_summary = self._personal_advance_repayment_amount_summary(rows)
        validation_message = self._personal_advance_repayment_validation_message(rows, amount_summary)
        if validation_message:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_personal_advance_repayment_request",
                    "message": validation_message,
                    "amount_summary": amount_summary,
                },
            )

        changed_scope_keys = self._scope_keys_for_rows(month=month, rows=rows)
        before_relations = self._relation_read_snapshot_port.active_relations_for_row_ids(row_ids)
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
        relation_command = self._relation_command_service_for()
        if relation_command is None:
            return self._relation_command_unavailable_result()
        previous_exception_snapshot = self._exception_case_service.snapshot()
        previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
        try:
            exception_case = self._exception_case_service.create_settlement_case(
                rows=rows,
                exception_code=PERSONAL_ADVANCE_REPAYMENT_MODE,
                exception_label="还清个人暂借款",
                category="oa_bank_settlement",
                comment=note or None,
                scope_months=[scope for scope in changed_scope_keys if SEARCH_MONTH_RE.match(scope)],
            )
            case_id = f"CASE-{str(exception_case['id'])}"
            amount_check = {
                "status": "matched",
                "direction": PERSONAL_ADVANCE_REPAYMENT_MODE,
                **amount_summary,
            }
            confirm_relation = getattr(relation_command, "confirm_relation", None)
            if not callable(confirm_relation):
                raise _WorkbenchWritePersistenceError("relation command service must expose confirm_relation.")
            command_result = confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=[str(row.get("type") or "") for row in rows],
                relation_mode=PERSONAL_ADVANCE_REPAYMENT_MODE,
                actor_id="system",
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
                note=note,
                amount_check=amount_check,
                special_metadata={
                    "special_type": PERSONAL_ADVANCE_REPAYMENT_MODE,
                    "cost_policy": "exclude_all",
                    "note": note,
                },
                before_relations=history_before_relations,
                replace_existing=True,
                history_operation_type=action_name,
            )
            relation = dict(command_result.get("relation") or {})
            self._save_exception_cases_snapshot()
        except WorkbenchRelationCommandError as exc:
            self._restore_exception_pair_snapshots(
                previous_exception_snapshot=previous_exception_snapshot,
                previous_pair_snapshot=previous_pair_snapshot,
            )
            return self._relation_command_error_result(exc)
        except Exception as exc:
            self._restore_exception_pair_snapshots(
                previous_exception_snapshot=previous_exception_snapshot,
                previous_pair_snapshot=previous_pair_snapshot,
            )
            if exc.__class__.__name__ == "StatePersistenceError":
                return self._persistence_unavailable_result(str(exc))
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_personal_advance_repayment_request", "message": str(exc)},
            )

        self._schedule_pair_relation_persist(
            changed_case_ids=[
                *[str(before_relation.get("case_id") or "") for before_relation in before_relations],
                str(relation.get("case_id") or ""),
            ],
            request_id=request_id,
            action_name=action_name,
        )
        self._invalidate_and_schedule_read_model(
            action_name=action_name,
            changed_scope_keys=changed_scope_keys,
            metadata={"source": action_name},
            request_id=request_id,
            schedule_started_at=monotonic(),
        )
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(
            {"affected_scope_keys": changed_scope_keys}
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": action_name,
                "month": month,
                "case_id": str(relation.get("case_id") or ""),
                "exception_case_id": str(exception_case["id"]),
                "affected_row_ids": row_ids,
                "affected_months": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "amount_summary": amount_summary,
                "message": "已确认还清个人暂借款。",
            },
        )

    def apply_exception(
        self,
        payload: dict[str, object],
        *,
        actor: str,
        request_id: str | None = None,
        action_name: str = "exception_apply",
        invalid_error_code: str = "invalid_workbench_exception_apply_request",
    ) -> WorkbenchWriteResult:
        try:
            result = self._apply_exception_payload(
                payload,
                actor=actor,
                request_id=request_id,
                action_name=action_name,
            )
        except WorkbenchRelationCommandError as exc:
            return self._relation_command_error_result(exc)
        except WorkbenchExceptionApplicationConflict as exc:
            return WorkbenchWriteResult(
                HTTPStatus.CONFLICT,
                {"error": exc.code, "message": str(exc), **({"payload": exc.payload} if exc.payload else {})},
            )
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        except (TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": invalid_error_code, "message": str(exc)},
            )
        return WorkbenchWriteResult(HTTPStatus.OK, result)

    def mark_exception(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            exception_code = str(payload["exception_code"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_mark_exception_request", "message": str(exc)},
            )

        return self._legacy_exception_result(
            month=month,
            row_ids=[row_id],
            action_name="mark_exception",
            invalid_error_code="invalid_mark_exception_request",
            legacy_payload={
                "note": comment or "",
                "legacy_exception_code": exception_code,
                "legacy_exception_label": comment or exception_code,
            },
            response_message="已标记异常。",
        )

    def cancel_exception(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._normalize_row_ids(list(payload["row_ids"]))
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_exception_request", "message": str(exc)},
            )

        if not row_ids:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_exception_request", "message": "row_ids is required."},
            )

        try:
            rows = self._resolve_live_rows_direct(row_ids, month_hint=month)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )

        try:
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=rows)

            def mutation() -> tuple[list[str], list[dict[str, object]]]:
                cancelled_cases = self._exception_case_service.cancel_exception_cases(
                    rows=rows,
                    comment=comment,
                )
                updated = self._override_service.cancel_exception(rows=rows, comment=comment)
                return [str(case["id"]) for case in cancelled_cases], updated

            exception_case_ids, updated_rows = self._persist_exception_and_override_change(
                changed_row_ids=row_ids,
                mutation=mutation,
                changed_scope_keys=changed_scope_keys,
                action_name="cancel_exception",
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(
            {"affected_scope_keys": changed_scope_keys}
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_exception",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
                "affected_scope_keys": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "updated_rows": updated_rows,
                "exception_case_ids": exception_case_ids,
                "message": f"已取消 {len(updated_rows)} 条记录的异常处理。",
            },
        )

    def _oa_bank_exception_with_invoice(
        self,
        *,
        month: str,
        row_ids: list[str],
        exception_code: str,
        exception_label: str,
        comment: str | None,
    ) -> WorkbenchWriteResult:
        try:
            preview = self._exception_service.preview({"month": month, "row_ids": row_ids})
            result = self._apply_exception_payload(
                {
                    "month": month,
                    "row_ids": row_ids,
                    "scenario_code": str(preview["scenario"]["scenario_code"]),
                    "action_code": "manual_review",
                    "payload": {
                        "note": comment or exception_label,
                        "legacy_exception_code": exception_code,
                        "legacy_exception_label": exception_label,
                    },
                },
                actor="system",
                action_name="oa_bank_exception",
            )
        except WorkbenchExceptionApplicationConflict as exc:
            return WorkbenchWriteResult(
                HTTPStatus.CONFLICT,
                {"error": exc.code, "message": str(exc), **({"payload": exc.payload} if exc.payload else {})},
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_oa_bank_exception_request", "message": str(exc)},
            )

        case_payload = result["case"]
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(result)
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "oa_bank_exception",
                "month": month,
                "affected_row_ids": list(result.get("affected_row_ids") or row_ids),
                "affected_scope_keys": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "updated_rows": list(result.get("updated_rows") or []),
                "exception_case_id": str(case_payload.get("id") or ""),
                "exception_case_ids": [str(case_payload.get("id") or "")],
                "message": f"已对 {len(row_ids)} 条记录执行 OA/流水异常处理。",
            },
        )

    def ignore_row(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
            comment = str(payload["comment"]) if payload.get("comment") is not None else None
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ignore_row_request", "message": str(exc)},
            )

        grouped_payload = self._build_workbench_payload(month)
        try:
            row = self._resolve_live_row(grouped_payload, row_id)
        except KeyError:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        if row.get("type") != "invoice":
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_ignore_row_request", "message": "ignore_row only supports invoice rows."},
            )
        conflict = self._ignore_row_stale_conflict(payload, row)
        if conflict is not None:
            conflict_payload = conflict.to_response_payload()
            return WorkbenchWriteResult(
                HTTPStatus(conflict.status_code),
                dict(conflict_payload["payload"]),
            )
        try:
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=[row])

            def mutation() -> tuple[str, dict[str, object]]:
                exception_case = self._exception_case_service.ignore_row(row, comment=comment)
                updated = self._override_service.ignore_row(
                    row=row,
                    comment=comment,
                    exception_case_id=str(exception_case["id"]),
                )
                return str(exception_case["id"]), updated

            exception_case_id, updated_row = self._persist_exception_and_override_change(
                changed_row_ids=[row_id],
                mutation=mutation,
                changed_scope_keys=changed_scope_keys,
                action_name="ignore_row",
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(
            {"affected_scope_keys": changed_scope_keys}
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "ignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "affected_scope_keys": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "updated_rows": [updated_row],
                "exception_case_id": exception_case_id,
                "exception_case_ids": [exception_case_id],
                "message": "已忽略 1 条记录。",
            },
        )

    def unignore_row(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_id = str(payload["row_id"])
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_unignore_row_request", "message": str(exc)},
            )

        ignored_rows = {
            str(row["id"]): row
            for row in self._build_ignored_rows_payload(month)
        }
        row = ignored_rows.get(row_id)
        if row is None:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": row_id},
            )
        try:
            changed_scope_keys = self._scope_keys_for_rows(month=month, rows=[row])

            def mutation() -> tuple[list[str], dict[str, object]]:
                unignored_case = self._exception_case_service.unignore_row(row)
                updated = self._override_service.unignore_row(row=row)
                return ([str(unignored_case["id"])] if isinstance(unignored_case, dict) else []), updated

            exception_case_ids, updated_row = self._persist_exception_and_override_change(
                changed_row_ids=[row_id],
                mutation=mutation,
                changed_scope_keys=changed_scope_keys,
                action_name="unignore_row",
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(
            {"affected_scope_keys": changed_scope_keys}
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "unignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
                "affected_scope_keys": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "updated_rows": [updated_row],
                "exception_case_ids": exception_case_ids,
                "message": "已撤回忽略 1 条记录。",
            },
        )

    def _withdraw_row_ids(self, payload: dict[str, object]) -> list[str]:
        raw_row_ids = payload.get("row_ids")
        if raw_row_ids is None and payload.get("row_id") is not None:
            raw_row_ids = [payload.get("row_id")]
        return self._normalize_row_ids(list(raw_row_ids or []))

    def _amount_check_for_withdraw_preview(
        self,
        *,
        active_relation: dict[str, object],
        rows: list[dict[str, object]],
    ) -> dict[str, object]:
        relation_amount_check = active_relation.get("amount_check")
        if isinstance(relation_amount_check, dict) and any(
            relation_amount_check.get(key) is not None
            for key in ("oa_total", "bank_total", "invoice_total")
        ):
            return dict(relation_amount_check)
        return self._amount_check_for_rows_by_type(self._rows_by_type(rows))

    def _cash_special_row_ids(self, payload: dict[str, object]) -> list[str]:
        raw_row_ids = payload.get("row_ids")
        if raw_row_ids is None and payload.get("row_id") is not None:
            raw_row_ids = [payload.get("row_id")]
        return self._normalize_row_ids(list(raw_row_ids or []))

    def _active_relation_for_cash_special(self, row_ids: list[str]) -> dict[str, object]:
        if not row_ids:
            raise ValueError("row_ids is required.")
        relation = self._relation_read_snapshot_port.active_relations_for_row_ids(row_ids)
        if not relation:
            raise KeyError("workbench_pair_relation_not_found")
        return relation[0]

    @staticmethod
    def _validate_cash_pass_through_relation(relation: dict[str, object]) -> None:
        row_types = {str(row_type).strip() for row_type in list(relation.get("row_types") or []) if str(row_type).strip()}
        if not {"oa", "bank"}.issubset(row_types):
            raise ValueError("cash_pass_through requires a relation containing OA and bank rows.")
        if "invoice" in row_types:
            raise ValueError("cash_pass_through requires an OA and bank relation without invoice rows.")

    @staticmethod
    def _validate_cash_ticket_purchase_relation(relation: dict[str, object]) -> None:
        row_types = {str(row_type).strip() for row_type in list(relation.get("row_types") or []) if str(row_type).strip()}
        if not {"oa", "bank", "invoice"}.issubset(row_types):
            raise ValueError("cash_ticket_purchase requires a relation containing OA, bank, and invoice rows.")

    def _cash_special_cash_amount(self, payload: dict[str, object], relation: dict[str, object]) -> str:
        if payload.get("cash_amount") is not None:
            return self._required_non_negative_amount(payload.get("cash_amount"), "cash_amount")
        bank_amounts: list[Decimal] = []
        for row_id, row_type in zip(list(relation.get("row_ids") or []), list(relation.get("row_types") or [])):
            if str(row_type) != "bank":
                continue
            try:
                transaction_amount = self._transaction_amount_for_row_id(str(row_id))
            except KeyError:
                continue
            amount = self._decimal_from_value(transaction_amount)
            if amount is not None:
                bank_amounts.append(amount)
        if len(bank_amounts) == 1:
            return f"{bank_amounts[0].quantize(Decimal('0.01')):.2f}"
        return "0.00"

    @staticmethod
    def _required_non_negative_amount(value: object, field_name: str) -> str:
        if value is None:
            raise ValueError(f"{field_name} is required.")
        try:
            amount = Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
        except Exception as exc:
            raise ValueError(f"{field_name} must be a valid amount.") from exc
        if amount < Decimal("0.00"):
            raise ValueError(f"{field_name} must be greater than or equal to 0.")
        return f"{amount:.2f}"

    def _after_cash_special_relation_update(
        self,
        *,
        month: str,
        relation: dict[str, object],
        request_id: str | None,
        action_name: str,
    ) -> list[str]:
        row_ids = self._normalize_row_ids(list(relation.get("row_ids") or []))
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=row_ids,
                month_scope=str(relation.get("month_scope") or ""),
            )
        )
        self._schedule_pair_relation_persist(
            changed_case_ids=[str(relation.get("case_id") or "")],
            request_id=request_id,
            action_name=action_name,
        )
        self._invalidate_and_schedule_read_model(
            action_name=action_name,
            changed_scope_keys=changed_scope_keys,
            metadata={"source": action_name, "case_id": str(relation.get("case_id") or "")},
            request_id=request_id,
            schedule_started_at=monotonic(),
        )
        return WorkbenchWriteFacade._operation_affected_scope_keys(
            {"affected_scope_keys": changed_scope_keys}
        )

    @staticmethod
    def _rows_by_type(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        rows_by_type: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type", ""))
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type

    def _row_types_from_rows(
        self,
        row_ids: list[str],
        rows: list[dict[str, object]],
        *,
        month: str,
    ) -> list[str]:
        rows_by_id = {str(row.get("id") or ""): row for row in rows}
        row_types = [str(rows_by_id.get(row_id, {}).get("type") or "unknown") for row_id in row_ids]
        if "unknown" not in row_types:
            return row_types
        fallback_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        return [fallback_types[index] if row_type == "unknown" and index < len(fallback_types) else row_type for index, row_type in enumerate(row_types)]

    @staticmethod
    def _can_confirm_link_resolved_selection(
        *,
        row_types: list[str],
        amount_check: dict[str, object],
    ) -> bool:
        known_types = {str(row_type).strip() for row_type in row_types if str(row_type).strip() and row_type != "unknown"}
        if len(known_types) >= 2:
            return True
        return known_types == {"bank"} and str(amount_check.get("status") or "") == "matched" and not amount_check.get("requires_note")

    def _personal_advance_repayment_amount_summary(self, rows: list[dict[str, object]]) -> dict[str, str]:
        oa_total = Decimal("0.00")
        bank_debit_total = Decimal("0.00")
        bank_credit_total = Decimal("0.00")
        for row in rows:
            row_type = str(row.get("type") or "")
            if row_type == "oa":
                amount = (
                    self._decimal_from_value(row.get("amount"))
                    or self._decimal_from_value(row.get("reimbursement_amount"))
                    or self._decimal_from_value(row.get("payment_amount"))
                    or self._decimal_from_value(row.get("apply_amount"))
                    or Decimal("0.00")
                )
                oa_total += amount
            elif row_type == "bank":
                debit_amount = self._decimal_from_value(row.get("debit_amount"))
                credit_amount = self._decimal_from_value(row.get("credit_amount"))
                if debit_amount is not None and debit_amount > 0:
                    bank_debit_total += debit_amount
                if credit_amount is not None and credit_amount > 0:
                    bank_credit_total += credit_amount
        return {
            "oa_total": self._plain_money(oa_total),
            "bank_debit_total": self._plain_money(bank_debit_total),
            "bank_credit_total": self._plain_money(bank_credit_total),
            "bank_net_total": self._plain_money(bank_credit_total - bank_debit_total),
        }

    def _personal_advance_repayment_validation_message(
        self,
        rows: list[dict[str, object]],
        amount_summary: dict[str, str],
    ) -> str | None:
        rows_by_type = self._rows_by_type(rows)
        unsupported_row_types = sorted(
            {
                str(row.get("type") or "")
                for row in rows
                if str(row.get("type") or "") not in {"oa", "bank", "invoice"}
            }
        )
        if unsupported_row_types:
            return f"personal advance repayment only supports OA and bank rows: {unsupported_row_types[0]}."
        if rows_by_type["invoice"]:
            return "personal advance repayment does not support invoice rows."
        if not rows_by_type["oa"]:
            return "personal advance repayment requires at least one OA row."

        has_bank_debit = False
        has_bank_credit = False
        for row in rows_by_type["bank"]:
            debit_amount = self._decimal_from_value(row.get("debit_amount"))
            credit_amount = self._decimal_from_value(row.get("credit_amount"))
            has_bank_debit = has_bank_debit or bool(debit_amount is not None and debit_amount > 0)
            has_bank_credit = has_bank_credit or bool(credit_amount is not None and credit_amount > 0)
        if not has_bank_debit:
            return "personal advance repayment requires at least one bank debit row."
        if not has_bank_credit:
            return "personal advance repayment requires at least one bank credit row."

        oa_total = Decimal(amount_summary["oa_total"])
        bank_debit_total = Decimal(amount_summary["bank_debit_total"])
        bank_credit_total = Decimal(amount_summary["bank_credit_total"])
        if oa_total != bank_debit_total or bank_credit_total != bank_debit_total:
            return "personal advance repayment amounts do not close."
        return None

    @staticmethod
    def _decimal_from_value(value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
        except Exception:
            return None

    @staticmethod
    def _plain_money(value: Decimal) -> str:
        return f"{value.quantize(Decimal('0.01')):.2f}"

    def _legacy_exception_result(
        self,
        *,
        month: str,
        row_ids: list[str],
        action_name: str,
        invalid_error_code: str,
        legacy_payload: dict[str, object],
        response_message: str,
    ) -> WorkbenchWriteResult:
        try:
            normalized_row_ids = self._normalize_row_ids(row_ids)
            scenario_code = self._legacy_replay_scenario_code(
                month=month,
                row_ids=normalized_row_ids,
                legacy_payload=legacy_payload,
            )
            preview = None
            if not scenario_code:
                preview = self._exception_service.preview({"month": month, "row_ids": normalized_row_ids})
                scenario_code = str(preview["scenario"]["scenario_code"])
            result = self._apply_exception_payload(
                {
                    "month": month,
                    "row_ids": normalized_row_ids,
                    "scenario_code": scenario_code,
                    "action_code": "manual_review",
                    "payload": legacy_payload,
                },
                actor="system",
                action_name=action_name,
            )
        except WorkbenchExceptionApplicationConflict as exc:
            return WorkbenchWriteResult(
                HTTPStatus.CONFLICT,
                {"error": exc.code, "message": str(exc), **({"payload": exc.payload} if exc.payload else {})},
            )
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_row_not_found", "message": str(exc)},
            )
        except _WorkbenchWritePersistenceError as exc:
            return self._persistence_unavailable_result(str(exc))
        except (TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": invalid_error_code, "message": str(exc)},
            )

        case_payload = result.get("case") if isinstance(result.get("case"), dict) else {}
        case_id = str(case_payload.get("id") or "")
        updated_rows = list(result.get("updated_rows") or [])
        affected_row_ids = [
            str(row_id)
            for row_id in list(result.get("affected_row_ids") or normalized_row_ids)
            if str(row_id).strip()
        ]
        affected_scope_keys = WorkbenchWriteFacade._operation_affected_scope_keys(result)
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": action_name,
                "month": month,
                "affected_row_ids": affected_row_ids,
                "affected_scope_keys": affected_scope_keys,
                **WorkbenchWriteFacade._operation_write_target_envelope(affected_scope_keys),
                "updated_rows": updated_rows,
                "exception_case_id": case_id,
                "exception_case_ids": [case_id] if case_id else [],
                "message": response_message,
            },
        )

    def _legacy_replay_scenario_code(
        self,
        *,
        month: str,
        row_ids: list[str],
        legacy_payload: dict[str, object],
    ) -> str:
        identity_key = next(
            (
                key
                for key in ("legacy_relation_code", "legacy_exception_code")
                if str(legacy_payload.get(key) or "").strip()
            ),
            "",
        )
        if not identity_key:
            return ""
        existing_cases = self._exception_case_service.preview_existing_case_conflicts(row_ids)
        if len(existing_cases) != 1:
            return ""
        existing_case = existing_cases[0]
        existing_row_ids = [str(row_id) for row_id in list(existing_case.get("row_ids") or [])]
        if set(existing_row_ids) != set(row_ids) or len(existing_row_ids) != len(row_ids):
            return ""
        scope_months = {str(scope) for scope in list(existing_case.get("scope_months") or [])}
        if month not in scope_months:
            return ""
        resolution = existing_case.get("resolution") if isinstance(existing_case.get("resolution"), dict) else {}
        if str(resolution.get("action_code") or "") != "manual_review":
            return ""
        if str(resolution.get(identity_key) or "") != str(legacy_payload.get(identity_key) or ""):
            return ""
        return str(existing_case.get("scenario_code") or "")

    def _apply_exception_payload(
        self,
        payload: dict[str, object],
        *,
        actor: str,
        request_id: str | None = None,
        action_name: str = "exception_apply",
    ) -> dict[str, object]:
        previous_exception_snapshot = self._exception_case_service.snapshot()
        previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
        previous_candidate_snapshot = self._candidate_match_service.snapshot()
        previous_override_snapshot = self._override_service.snapshot()
        try:
            result = self._exception_service.apply(payload, actor=actor)
        except WorkbenchRelationCommandError:
            self._restore_exception_write_snapshots(
                previous_exception_snapshot=previous_exception_snapshot,
                previous_pair_snapshot=previous_pair_snapshot,
                previous_candidate_snapshot=previous_candidate_snapshot,
                previous_override_snapshot=previous_override_snapshot,
            )
            raise
        row_ids = [
            str(row_id)
            for row_id in list(result.get("affected_row_ids") or [])
            if str(row_id).strip()
        ]
        month = str(payload.get("month") or "")
        rows = self._resolve_live_rows_direct(row_ids, month_hint=month) if row_ids else []
        relation = result.get("pair_relation")
        case_payload = result.get("case")
        if isinstance(case_payload, dict):
            if isinstance(relation, dict):
                updated_rows = self._override_service.apply_relation_projection(
                    relation,
                    rows,
                    case_payload=case_payload,
                    candidate_evidence=list(result.get("candidate_evidence") or []),
                )
            else:
                updated_rows = self._override_service.apply_exception_projection(
                    case_payload,
                    rows,
                    candidate_evidence=list(result.get("candidate_evidence") or []),
                )
            result["updated_rows"] = updated_rows
        try:
            self._save_exception_cases_snapshot()
            if isinstance(relation, dict):
                self._persist_pair_relations(
                    changed_case_ids=[str(relation.get("case_id") or "")],
                )
            self._save_overrides_snapshot(changed_row_ids=row_ids)
            self._persist_candidate_matches_best_effort(operation=action_name)
        except Exception as exc:
            self._restore_exception_write_snapshots(
                previous_exception_snapshot=previous_exception_snapshot,
                previous_pair_snapshot=previous_pair_snapshot,
                previous_candidate_snapshot=previous_candidate_snapshot,
                previous_override_snapshot=previous_override_snapshot,
            )
            raise _WorkbenchWritePersistenceError("工作台状态暂时无法保存，请稍后重试。") from exc

        changed_scope_keys = self._normalize_operation_scope_keys(list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=row_ids,
                month_scope=str(relation.get("month_scope") or "") if isinstance(relation, dict) else month,
            )
        ))
        result["affected_scope_keys"] = list(changed_scope_keys)
        result.update(self._operation_write_target_envelope(changed_scope_keys))
        self._execute_derived_data_lifecycle_event(
            "exception_case_changed",
            scope_keys=changed_scope_keys,
            metadata={"source": action_name, "reason": action_name},
        )
        if isinstance(relation, dict):
            self._schedule_pair_relation_persist(
                changed_case_ids=[str(relation.get("case_id") or "")],
                request_id=request_id,
                action_name=action_name,
            )
        self._schedule_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            request_id=request_id,
            action_name=action_name,
        )
        return result

    def _persist_exception_and_override_change(
        self,
        *,
        changed_row_ids: list[str],
        mutation: Callable[[], object],
        changed_scope_keys: list[str] | None = None,
        request_id: str | None = None,
        action_name: str | None = None,
    ) -> object:
        previous_exception_snapshot = self._exception_case_service.snapshot()
        previous_override_snapshot = self._override_service.snapshot()
        result = mutation()
        try:
            self._save_exception_cases_snapshot()
            self._save_overrides_snapshot(changed_row_ids=changed_row_ids)
        except Exception as exc:
            self._restore_exception_override_snapshots(
                previous_exception_snapshot=previous_exception_snapshot,
                previous_override_snapshot=previous_override_snapshot,
            )
            raise _WorkbenchWritePersistenceError("工作台状态暂时无法保存，请稍后重试。") from exc
        if changed_scope_keys is not None:
            self._execute_derived_data_lifecycle_event(
                "exception_case_changed",
                scope_keys=changed_scope_keys,
                metadata={"source": action_name or "workbench_exception_change"},
            )
            self._schedule_read_model_persist(
                changed_scope_keys=changed_scope_keys,
                request_id=request_id,
                action_name=action_name,
            )
        return result

    def _relation_refresh_metadata(
        self,
        *,
        relation: dict[str, object],
        row_ids: list[str],
        month: str,
        resolve_rows: bool = True,
    ) -> dict[str, object]:
        rows: list[dict[str, object]] = []
        row_types = self._relation_row_types(relation=relation, rows=[])
        if resolve_rows and ("invoice" in row_types or not row_types):
            try:
                resolved_row_ids = [str(row_id) for row_id in list(row_ids or []) if str(row_id).strip()]
                rows = self._resolve_live_rows_direct(resolved_row_ids, month_hint=month) if resolved_row_ids else []
            except Exception:
                rows = []
        downstream_scope_types = self._relation_downstream_scope_types(relation=relation, rows=rows)
        invoice_usage_scope_types = sorted(
            downstream_scope_types & {"input_invoice_usage", "output_invoice_collection", "oa_pending_payment"}
        )
        pending_invoice_scope_keys = self._relation_pending_invoice_scope_keys(
            relation=relation,
            rows=rows,
            month=month,
        )
        metadata: dict[str, object] = {
            "downstream_scope_types": sorted(downstream_scope_types),
            "invoice_usage_scope_types": invoice_usage_scope_types,
        }
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if normalized_row_ids:
            metadata["row_ids"] = list(dict.fromkeys(normalized_row_ids))
        case_id = str(relation.get("case_id") or "").strip()
        if case_id:
            metadata["case_ids"] = [case_id]
        if pending_invoice_scope_keys:
            metadata["pending_invoice_scope_keys"] = pending_invoice_scope_keys
        return metadata

    def _relation_downstream_scope_types(
        self,
        *,
        relation: dict[str, object],
        rows: list[dict[str, object]],
    ) -> set[str]:
        row_types = self._relation_row_types(relation=relation, rows=rows)
        unknown_row_types = not row_types
        has_bank = "bank" in row_types or unknown_row_types
        has_invoice = "invoice" in row_types or unknown_row_types
        has_oa = "oa" in row_types
        scope_types: set[str] = {"search", "workbench_relation"}
        if has_bank:
            scope_types.update({"bank_detail", "pending_invoice"})
        if has_invoice or has_oa or unknown_row_types:
            scope_types.add("invoice_lifecycle")
        if has_invoice:
            scope_types.update({"input_invoice_usage", "output_invoice_collection"})
        if has_oa:
            scope_types.add("oa_pending_payment")
        if has_bank or has_invoice or has_oa or unknown_row_types:
            scope_types.add("cost_statistics")
        return scope_types

    def _relation_pending_invoice_scope_keys(
        self,
        *,
        relation: dict[str, object],
        rows: list[dict[str, object]],
        month: str | None = None,
    ) -> list[str]:
        row_types = self._relation_row_types(relation=relation, rows=rows)
        if row_types and "bank" not in row_types:
            return []
        directions = self._bank_directions(rows)
        if not directions:
            directions = {"expense", "income"}
        scope_keys: list[str] = []
        month_suffix = f":{month}" if month and SEARCH_MONTH_RE.match(str(month)) else ""
        if "expense" in directions:
            scope_keys.append(f"expense:all{month_suffix}")
        if "income" in directions:
            scope_keys.append(f"income:all{month_suffix}")
        return list(dict.fromkeys(scope_keys))

    @staticmethod
    def _relation_row_types(*, relation: dict[str, object], rows: list[dict[str, object]]) -> set[str]:
        row_types = {
            str(row_type).strip()
            for row_type in list(relation.get("row_types") or [])
            if str(row_type).strip()
        }
        if row_types:
            return row_types
        row_types.update(
            str(row.get("type") or "").strip()
            for row in list(rows or [])
            if str(row.get("type") or "").strip()
        )
        if row_types:
            return row_types
        return {
            row_type_for_workbench_row_id(row_id, unknown="")
            for row_id in list(relation.get("row_ids") or [])
            if row_type_for_workbench_row_id(row_id, unknown="")
        }

    def _bank_directions(self, rows: list[dict[str, object]]) -> set[str]:
        directions: set[str] = set()
        for row in list(rows or []):
            if str(row.get("type") or "") != "bank":
                continue
            raw_direction = str(row.get("txn_direction") or row.get("direction") or "").strip().lower()
            if raw_direction in {"outflow", "debit", "expense"} or "支" in raw_direction or "付" in raw_direction:
                directions.add("expense")
            if raw_direction in {"inflow", "credit", "income"} or "收" in raw_direction or "入" in raw_direction:
                directions.add("income")
            debit_amount = self._decimal_from_value(row.get("debit_amount"))
            credit_amount = self._decimal_from_value(row.get("credit_amount"))
            if debit_amount is not None and debit_amount > 0:
                directions.add("expense")
            if credit_amount is not None and credit_amount > 0:
                directions.add("income")
        return directions

    def _invalidate_and_schedule_read_model(
        self,
        *,
        action_name: str,
        changed_scope_keys: list[str],
        metadata: dict[str, object],
        include_all: bool = True,
        request_id: str | None,
        schedule_started_at: float,
    ) -> None:
        invalidate_started_at = monotonic()
        self._execute_derived_data_lifecycle_event(
            "pair_relation_changed",
            scope_keys=changed_scope_keys,
            include_all=include_all,
            metadata={**dict(metadata), "action_name": action_name},
        )
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="invalidate_read_model_scopes",
            started_at=invalidate_started_at,
            detail=",".join(changed_scope_keys),
        )
        self._schedule_read_model_persist(
            changed_scope_keys=changed_scope_keys,
            request_id=request_id,
            action_name=action_name,
        )
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="schedule_background_persist",
            started_at=schedule_started_at,
        )

    def _emit_timing_if_requested(
        self,
        *,
        request_id: str | None,
        action_name: str,
        phase: str,
        started_at: float,
        detail: str | None = None,
    ) -> None:
        if request_id is None:
            return
        kwargs: dict[str, object] = {
            "request_id": request_id,
            "action_name": action_name,
            "phase": phase,
            "duration_ms": self._duration_ms(started_at),
        }
        if detail is not None:
            kwargs["detail"] = detail
        self._emit_action_timing(**kwargs)

    @staticmethod
    def _duration_ms(started_at: float) -> float:
        return round((monotonic() - started_at) * 1000, 3)

    @staticmethod
    def _persistence_unavailable_result(message: str) -> WorkbenchWriteResult:
        return WorkbenchWriteResult(
            HTTPStatus.SERVICE_UNAVAILABLE,
            {
                "error": "workbench_state_persistence_unavailable",
                "message": message,
            },
        )

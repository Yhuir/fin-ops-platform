from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE
from fin_ops_platform.services.workbench_idempotency import (
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)
from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationConflict
from fin_ops_platform.services.workbench_stale_precondition import assert_workbench_stale_preconditions
from fin_ops_platform.services.workbench_write_conflict import WorkbenchWriteConflict


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


CASH_PASS_THROUGH_MODE = "cash_pass_through"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
PERSONAL_ADVANCE_REPAYMENT_MODE = "personal_advance_repayment_settlement"


class WorkbenchWriteFacade:
    def __init__(
        self,
        *,
        pair_relation_service: Any,
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
        persist_pair_relations_in_transaction: Callable[..., None] | None = None,
        consume_reconciliation_decisions_in_transaction: Callable[..., int] | None = None,
    ) -> None:
        self._pair_relation_service = pair_relation_service
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
        self._persist_pair_relations_in_transaction = persist_pair_relations_in_transaction
        self._consume_reconciliation_decisions_in_transaction = consume_reconciliation_decisions_in_transaction

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

        requested_row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        if not self._can_confirm_link_row_types(row_ids=row_ids, row_types=requested_row_types, month=month):
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_confirm_link_request",
                    "message": "confirm link requires rows from at least two panes.",
                },
            )
        row_ids = self._expand_confirm_link_row_ids_for_existing_context(row_ids, month=month)
        row_types = self._resolved_row_types_for_row_ids(row_ids, month=month)
        amount_check = self._amount_check_for_row_ids(row_ids, month=month, allow_direct=False)
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
        before_relations = self._pair_relation_service.active_relations_for_row_ids(row_ids)
        selected_rows = self._resolve_rows_for_amount_check(row_ids, month=month, allow_direct=False)
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                selected_rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
        previous_pair_snapshot = self._pair_relation_service.snapshot()
        changed_scope_keys = list(self._scope_keys_for_row_ids(month=month, row_ids=row_ids))
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
                history_before_relations=history_before_relations,
                previous_pair_snapshot=previous_pair_snapshot,
                changed_scope_keys=changed_scope_keys,
                changed_case_ids=changed_case_ids,
            )

        pair_relation_started_at = monotonic()
        self._pair_relation_service.replace_with_confirmed_relation(
            case_id=resolved_case_id,
            row_ids=row_ids,
            row_types=row_types,
            relation_mode="manual_confirmed",
            created_by="system",
            month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            note=note,
            amount_check=amount_check,
            before_relations=history_before_relations,
        )
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
                changed_case_ids=changed_case_ids,
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
            metadata={"source": action_name, "case_id": resolved_case_id},
            request_id=request_id,
            schedule_started_at=schedule_started_at,
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "confirm_link",
                "month": month,
                "case_id": resolved_case_id,
                "affected_row_ids": row_ids,
                "affected_months": changed_scope_keys,
                "amount_check": amount_check,
                "message": f"已确认 {len(row_ids)} 条记录关联。",
            },
        )

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
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            if self._persist_pair_relations_in_transaction is None:
                raise _WorkbenchWritePersistenceError("confirm-link UoW requires transaction-bound pair relation persistence.")
            pair_relation_started_at = monotonic()
            self._pair_relation_service.replace_with_confirmed_relation(
                case_id=resolved_case_id,
                row_ids=row_ids,
                row_types=row_types,
                relation_mode="manual_confirmed",
                created_by="system",
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
                note=note,
                amount_check=amount_check,
                before_relations=history_before_relations,
            )
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={resolved_case_id}",
            )
            self._persist_pair_relations_in_transaction(
                transaction=transaction,
                changed_case_ids=changed_case_ids,
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
        except WorkbenchWriteConflict as exc:
            conflict_payload = exc.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(exc.status_code), dict(conflict_payload["payload"]))
        except Exception:
            self._restore_pair_relation_snapshot(
                previous_pair_snapshot,
                changed_case_ids=changed_case_ids,
            )
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(HTTPStatus.OK, self._confirm_link_response_payload(result))

    @staticmethod
    def _confirm_link_response_payload(result: dict[str, object]) -> dict[str, object]:
        return {
            "success": bool(result.get("success")),
            "action": "confirm_link",
            "month": str(result.get("month") or ""),
            "case_id": str(result.get("case_id") or ""),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "affected_months": list(result.get("affected_months") or []),
            "amount_check": dict(result.get("amount_check") or {}),
            "message": str(result.get("message") or ""),
        }

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
        active_relation = self._pair_relation_service.get_active_relation_by_row_id(row_id)
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

        pair_relation_started_at = monotonic()
        cancelled_relation = self._pair_relation_service.cancel_relation_for_row_id(row_id)
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="pair_relation_update",
            started_at=pair_relation_started_at,
            detail=f"row_id={row_id}",
        )
        changed_case_ids = []
        if isinstance(cancelled_relation, dict):
            changed_case_ids.append(str(cancelled_relation.get("case_id", "")))
        schedule_started_at = monotonic()
        self._schedule_pair_relation_persist(
            changed_case_ids=changed_case_ids,
            request_id=request_id,
            action_name=action_name,
        )
        self._invalidate_and_schedule_read_model(
            action_name=action_name,
            changed_scope_keys=changed_scope_keys,
            metadata={"source": action_name, "case_id": str(active_relation.get("case_id") or "")},
            request_id=request_id,
            schedule_started_at=schedule_started_at,
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_link",
                "month": month,
                "case_id": str(active_relation.get("case_id") or ""),
                "affected_row_ids": affected_row_ids,
                "affected_months": changed_scope_keys,
                "message": "已取消关联并回退为待处理。",
            },
        )

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
        previous_pair_snapshot = self._pair_relation_service.snapshot()
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
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            if self._persist_pair_relations_in_transaction is None:
                raise _WorkbenchWritePersistenceError("cancel-link UoW requires transaction-bound pair relation persistence.")
            pair_relation_started_at = monotonic()
            cancelled_relation = self._pair_relation_service.cancel_relation_for_row_id(row_id)
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"row_id={row_id}",
            )
            if not isinstance(cancelled_relation, dict):
                raise _WorkbenchWritePersistenceError("cancel-link relation disappeared during UoW handler.")
            self._persist_pair_relations_in_transaction(
                transaction=transaction,
                changed_case_ids=changed_case_ids,
            )
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

    @staticmethod
    def _cancel_link_response_payload(result: dict[str, object]) -> dict[str, object]:
        return {
            "success": bool(result.get("success")),
            "action": "cancel_link",
            "month": str(result.get("month") or ""),
            "case_id": str(result.get("case_id") or ""),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "affected_months": list(result.get("affected_months") or []),
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
        active_relation = self._pair_relation_service.get_active_relation_by_row_id(row_id)
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

    def _withdraw_link_stale_conflict(
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
                    action_name="withdraw_link",
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

    def preview_withdraw_link(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids = self._withdraw_row_ids(payload)
            preview = self._pair_relation_service.preview_withdraw_for_row_ids(row_ids)
            active_relation = preview["active_relation"]
            rows, after_relations, _affected_row_ids = self._withdraw_rows_and_after_relations(
                active_relation=active_relation,
                after_relations=list(preview.get("after_relations") or []),
                month=month,
            )
            before_groups = self._relation_groups([active_relation], selected_rows=rows)
            after_groups = self._relation_groups(
                after_relations,
                selected_rows=rows,
                ungrouped_selected_rows="separate",
            )
            amount_check = self._amount_check_for_withdraw_preview(
                active_relation=active_relation,
                rows=rows,
            )
            active_relation_identity = self._withdraw_preview_active_relation_identity(active_relation)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history", "message": str(exc)},
            )
        except (TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_preview_request", "message": str(exc)},
            )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "operation": "withdraw_link",
                "can_submit": True,
                "requires_note": False,
                "message": "",
                "before": {"groups": before_groups},
                "after": {"groups": after_groups},
                "amount_summary": {
                    "before": amount_check,
                    "after": amount_check,
                    **amount_check,
                },
                "restored_relations": after_relations,
                "active_relation": active_relation_identity,
                "submit_expected_versions": {
                    f"relation:{active_relation_identity['case_id']}": active_relation_identity["version"],
                },
            },
        )

    @staticmethod
    def _withdraw_preview_active_relation_identity(active_relation: dict[str, object]) -> dict[str, object]:
        case_id = str(active_relation.get("case_id") or "").strip()
        if not case_id:
            raise ValueError("active relation case_id is required for withdraw preview.")
        version = active_relation.get("version")
        if type(version) is int:
            resolved_version = version
        elif isinstance(version, str) and version.strip().isdigit():
            resolved_version = int(version.strip())
        else:
            # Compatibility bridge: current in-memory relation facts do not yet
            # expose a durable facts-level version. This preview-only token gives
            # the frontend a stable submit contract; real stale rejection remains
            # a later UoW/facts precondition slice.
            resolved_version = 1
        return {"case_id": case_id, "version": resolved_version}

    def withdraw_link(self, payload: dict[str, object], *, request_id: str | None = None) -> WorkbenchWriteResult:
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

        try:
            preview = self._pair_relation_service.preview_withdraw_for_row_ids(row_ids)
        except KeyError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": str(exc).strip("'") or "workbench_pair_relation_no_withdraw_history", "message": str(exc)},
            )

        active_relation = preview["active_relation"]
        conflict = self._withdraw_link_stale_conflict(payload, active_relation)
        if conflict is not None:
            conflict_payload = conflict.to_response_payload()
            return WorkbenchWriteResult(HTTPStatus(conflict.status_code), dict(conflict_payload["payload"]))
        _rows, after_relations, affected_row_ids = self._withdraw_rows_and_after_relations(
            active_relation=active_relation,
            after_relations=list(preview.get("after_relations") or []),
            month=month,
        )
        restored_relations, _history = self._pair_relation_service.withdraw_latest_for_row_ids(
            row_ids,
            created_by="system",
            note=note,
            fallback_after_relations=after_relations,
        )
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=affected_row_ids,
                month_scope=str(active_relation.get("month_scope") or ""),
            )
        )
        changed_case_ids = [
            str(active_relation.get("case_id") or ""),
            *[str(relation.get("case_id") or "") for relation in restored_relations],
        ]
        schedule_started_at = monotonic()
        self._schedule_pair_relation_persist(
            changed_case_ids=changed_case_ids,
            request_id=request_id,
            action_name=action_name,
        )
        self._invalidate_and_schedule_read_model(
            action_name=action_name,
            changed_scope_keys=changed_scope_keys,
            metadata={"source": action_name, "case_id": str(active_relation.get("case_id") or "")},
            request_id=request_id,
            schedule_started_at=schedule_started_at,
        )
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "operation": "withdraw_link",
                "action": "withdraw_link",
                "month": month,
                "changed_scopes": changed_scope_keys,
                "affected_months": changed_scope_keys,
                "affected_row_ids": affected_row_ids,
                "restored_relations": restored_relations,
            },
        )

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
            updated_relation, _history = self._pair_relation_service.update_special_metadata_for_row_ids(
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
        self._after_cash_special_relation_update(
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
            updated_relation, _history = self._pair_relation_service.update_special_metadata_for_row_ids(
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
        self._after_cash_special_relation_update(
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
            updated_relation, _history = self._pair_relation_service.clear_special_metadata_for_row_ids(
                row_ids,
                updated_by="system",
                note=note,
            )
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_cancel_cash_special_request", "message": str(exc)},
            )
        self._after_cash_special_relation_update(
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
        before_relations = self._pair_relation_service.active_relations_for_row_ids(row_ids)
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
        previous_exception_snapshot = self._exception_case_service.snapshot()
        previous_pair_snapshot = self._pair_relation_service.snapshot()
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
            relation, _history = self._pair_relation_service.replace_with_confirmed_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=[str(row.get("type") or "") for row in rows],
                relation_mode=PERSONAL_ADVANCE_REPAYMENT_MODE,
                created_by="system",
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
                note=note,
                amount_check=amount_check,
                special_metadata={
                    "special_type": PERSONAL_ADVANCE_REPAYMENT_MODE,
                    "cost_policy": "exclude_all",
                    "note": note,
                },
                before_relations=history_before_relations,
            )
            self._save_exception_cases_snapshot()
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": action_name,
                "month": month,
                "case_id": str(relation.get("case_id") or ""),
                "exception_case_id": str(exception_case["id"]),
                "affected_row_ids": row_ids,
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "cancel_exception",
                "month": month,
                "affected_row_ids": [row["id"] for row in updated_rows],
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "oa_bank_exception",
                "month": month,
                "affected_row_ids": list(result.get("affected_row_ids") or row_ids),
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "ignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": "unignore_row",
                "month": month,
                "affected_row_ids": [updated_row["id"]],
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
        relation = self._pair_relation_service.active_relations_for_row_ids(row_ids)
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
    ) -> None:
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

    @staticmethod
    def _rows_by_type(rows: list[dict[str, object]]) -> dict[str, list[dict[str, object]]]:
        rows_by_type: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        for row in rows:
            row_type = str(row.get("type", ""))
            if row_type in rows_by_type:
                rows_by_type[row_type].append(row)
        return rows_by_type

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
            preview = self._exception_service.preview({"month": month, "row_ids": normalized_row_ids})
            result = self._apply_exception_payload(
                {
                    "month": month,
                    "row_ids": normalized_row_ids,
                    "scenario_code": str(preview["scenario"]["scenario_code"]),
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
                "success": True,
                "action": action_name,
                "month": month,
                "affected_row_ids": affected_row_ids,
                "updated_rows": updated_rows,
                "exception_case_id": case_id,
                "exception_case_ids": [case_id] if case_id else [],
                "message": response_message,
            },
        )

    def _apply_exception_payload(
        self,
        payload: dict[str, object],
        *,
        actor: str,
        request_id: str | None = None,
        action_name: str = "exception_apply",
    ) -> dict[str, object]:
        previous_exception_snapshot = self._exception_case_service.snapshot()
        previous_pair_snapshot = self._pair_relation_service.snapshot()
        previous_candidate_snapshot = self._candidate_match_service.snapshot()
        previous_override_snapshot = self._override_service.snapshot()
        result = self._exception_service.apply(payload, actor=actor)
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

        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=row_ids,
                month_scope=str(relation.get("month_scope") or "") if isinstance(relation, dict) else month,
            )
        )
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

    def _invalidate_and_schedule_read_model(
        self,
        *,
        action_name: str,
        changed_scope_keys: list[str],
        metadata: dict[str, object],
        request_id: str | None,
        schedule_started_at: float,
    ) -> None:
        invalidate_started_at = monotonic()
        self._execute_derived_data_lifecycle_event(
            "pair_relation_changed",
            scope_keys=changed_scope_keys,
            metadata=metadata,
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

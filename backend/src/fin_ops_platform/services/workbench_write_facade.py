from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable


@dataclass(frozen=True)
class WorkbenchWriteResult:
    status_code: HTTPStatus
    payload: dict[str, object]


class WorkbenchWriteFacade:
    def __init__(
        self,
        *,
        pair_relation_service: Any,
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
        schedule_pair_relation_persist: Callable[..., None],
        consume_reconciliation_decisions: Callable[..., int],
        restore_pair_relation_snapshot: Callable[..., None],
        execute_derived_data_lifecycle_event: Callable[..., None],
        schedule_read_model_persist: Callable[..., None],
        emit_action_timing: Callable[..., None],
    ) -> None:
        self._pair_relation_service = pair_relation_service
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
        self._schedule_pair_relation_persist = schedule_pair_relation_persist
        self._consume_reconciliation_decisions = consume_reconciliation_decisions
        self._restore_pair_relation_snapshot = restore_pair_relation_snapshot
        self._execute_derived_data_lifecycle_event = execute_derived_data_lifecycle_event
        self._schedule_read_model_persist = schedule_read_model_persist
        self._emit_action_timing = emit_action_timing

    def confirm_link(self, payload: dict[str, object], *, request_id: str | None = None) -> WorkbenchWriteResult:
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
        changed_scope_keys = list(self._scope_keys_for_row_ids(month=month, row_ids=row_ids))
        changed_case_ids = [
            *[str(relation.get("case_id", "")) for relation in before_relations if str(relation.get("case_id", "")).strip()],
            resolved_case_id,
        ]
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

    def cancel_link(self, payload: dict[str, object], *, request_id: str | None = None) -> WorkbenchWriteResult:
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

        resolve_rows_started_at = monotonic()
        active_relation = self._pair_relation_service.get_active_relation_by_row_id(row_id)
        if not isinstance(active_relation, dict):
            return WorkbenchWriteResult(
                HTTPStatus.NOT_FOUND,
                {"error": "workbench_pair_relation_not_found", "message": row_id},
            )
        affected_row_ids = self._normalize_row_ids(list(active_relation.get("row_ids") or []))
        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="resolve_rows",
            started_at=resolve_rows_started_at,
            detail=f"rows={len(affected_row_ids)}",
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
        changed_scope_keys = list(
            self._scope_keys_for_row_ids(
                month=month,
                row_ids=affected_row_ids,
                month_scope=str(active_relation.get("month_scope") or ""),
            )
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

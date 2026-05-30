from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.services.workbench_exception_application_service import WorkbenchExceptionApplicationConflict


class _WorkbenchWritePersistenceError(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkbenchWriteResult:
    status_code: HTTPStatus
    payload: dict[str, object]


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
        build_workbench_payload: Callable[..., dict[str, object]],
        build_ignored_rows_payload: Callable[..., list[dict[str, object]]],
        save_exception_cases_snapshot: Callable[[], None],
        persist_pair_relations: Callable[..., None],
        save_overrides_snapshot: Callable[..., None],
        persist_candidate_matches_best_effort: Callable[..., None],
        restore_exception_write_snapshots: Callable[..., None],
        restore_exception_override_snapshots: Callable[..., None],
        schedule_pair_relation_persist: Callable[..., None],
        consume_reconciliation_decisions: Callable[..., int],
        restore_pair_relation_snapshot: Callable[..., None],
        execute_derived_data_lifecycle_event: Callable[..., None],
        schedule_read_model_persist: Callable[..., None],
        emit_action_timing: Callable[..., None],
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
        self._build_workbench_payload = build_workbench_payload
        self._build_ignored_rows_payload = build_ignored_rows_payload
        self._save_exception_cases_snapshot = save_exception_cases_snapshot
        self._persist_pair_relations = persist_pair_relations
        self._save_overrides_snapshot = save_overrides_snapshot
        self._persist_candidate_matches_best_effort = persist_candidate_matches_best_effort
        self._restore_exception_write_snapshots = restore_exception_write_snapshots
        self._restore_exception_override_snapshots = restore_exception_override_snapshots
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

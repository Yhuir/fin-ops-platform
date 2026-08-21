from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from http import HTTPStatus
import logging
import re
from time import monotonic
from typing import Any, Callable

MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
from fin_ops_platform.services.workbench_idempotency import (
    WorkbenchIdempotencyFailed,
    WorkbenchIdempotencyInProgress,
    WorkbenchIdempotencyKeyConflict,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import oa_row_source_ids
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_modes import workbench_relations_have_same_row_set
from fin_ops_platform.services.workbench_relation_requirements import (
    build_bank_relation_requirement_metadata,
)
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
    row_types: list[str]
    case_id: str
    scope_keys: list[str]
    payload: dict[str, object]
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    expected_versions: dict[str, object] | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    timing_emit: Callable[[str, float, str | None], None] | None = None


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


@dataclass(frozen=True)
class _WorkbenchWithdrawLinkCommand:
    action_name: str
    month: str
    row_ids: list[str]
    row_types: list[str]
    case_id: str
    scope_keys: list[str]
    payload: dict[str, object]
    idempotency_key: str | None = None
    request_fingerprint: str | None = None
    expected_versions: dict[str, object] | None = None
    tenant_id: str = "default"
    actor_id: str = "system"
    timing_emit: Callable[[str, float, str | None], None] | None = None


CASH_PASS_THROUGH_MODE = "cash_pass_through"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
PERSONAL_ADVANCE_REPAYMENT_MODE = "personal_advance_repayment_settlement"


class WorkbenchWriteRelationReadSnapshotPort:
    def __init__(self, pair_relation_service: Any) -> None:
        self._pair_relation_service = pair_relation_service

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        return self._pair_relation_service.active_relations_for_row_ids(row_ids)

    def active_relations_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
    ) -> list[dict[str, object]]:
        reader = getattr(self._pair_relation_service, "active_relations_for_typed_rows", None)
        if not callable(reader):
            raise RuntimeError("Typed Workbench relation lookup is required.")
        return list(reader(row_ids, row_types) or [])

    def active_relation_by_row_id(self, row_id: str) -> dict[str, object] | None:
        relation = self._pair_relation_service.get_active_relation_by_row_id(row_id)
        return relation if isinstance(relation, dict) else None

    def active_relation_by_typed_row(
        self,
        row_id: str,
        row_type: str,
    ) -> dict[str, object] | None:
        relations = self.active_relations_for_typed_rows([row_id], [row_type])
        return relations[0] if len(relations) == 1 else None

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

    def update_special_metadata_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        special_metadata: dict[str, object],
        updated_by: str,
        note: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        mutation = getattr(
            self._pair_relation_service,
            "update_special_metadata_for_typed_rows",
            None,
        )
        if not callable(mutation):
            raise RuntimeError("Typed Workbench special-metadata mutation is required.")
        updated_relation, history = mutation(
            row_ids,
            row_types,
            special_metadata=special_metadata,
            updated_by=updated_by,
            note=note,
        )
        return dict(updated_relation), dict(history)

    def clear_special_metadata_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        updated_by: str,
        note: str | None = None,
    ) -> tuple[dict[str, object], dict[str, object]]:
        mutation = getattr(
            self._pair_relation_service,
            "clear_special_metadata_for_typed_rows",
            None,
        )
        if not callable(mutation):
            raise RuntimeError("Typed Workbench special-metadata mutation is required.")
        updated_relation, history = mutation(
            row_ids,
            row_types,
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
        exception_case_service: Any,
        next_case_id: Callable[[], str],
        normalize_row_ids: Callable[[list[object]], list[str]],
        relation_preview_selection: Callable[..., Any],
        resolve_rows_for_amount_check: Callable[..., list[dict[str, object]]],
        merge_relation_snapshots: Callable[..., list[dict[str, object]]],
        synthetic_existing_case_relations: Callable[..., list[dict[str, object]]],
        month_scope_for_selected_row_ids: Callable[..., str],
        scope_keys_for_row_ids: Callable[..., set[str]],
        scope_keys_for_rows: Callable[..., list[str]],
        resolve_live_rows_direct: Callable[..., list[dict[str, object]]],
        relation_groups: Callable[..., list[dict[str, object]]],
        withdraw_rows_and_after_relations: Callable[..., tuple[list[dict[str, object]], list[dict[str, object]], list[str]]],
        amount_check_for_rows_by_type: Callable[[dict[str, list[dict[str, object]]]], dict[str, object]],
        transaction_amount_for_row_id: Callable[[str], object],
        save_exception_cases_snapshot: Callable[[], None],
        persist_pair_relations: Callable[..., None],
        restore_exception_pair_snapshots: Callable[..., None],
        schedule_pair_relation_persist: Callable[..., None],
        restore_pair_relation_snapshot: Callable[..., None],
        emit_action_timing: Callable[..., None],
        confirm_link_uow: Any | None = None,
        cancel_link_uow: Any | None = None,
        withdraw_link_uow: Any | None = None,
        persist_pair_relations_in_transaction: Callable[..., None] | None = None,
        bank_transaction_category_codes_for_row_ids: Callable[[list[str]], dict[str, str]] | None = None,
        bank_flow_rule_tag_rules_payload: Callable[[], dict[str, object]] | None = None,
        relation_command_service: Any | None = None,
        relation_command_service_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._relation_read_snapshot_port = relation_read_snapshot_port
        self._relation_special_metadata_mutation_port = relation_special_metadata_mutation_port
        self._exception_case_service = exception_case_service
        self._next_case_id = next_case_id
        self._normalize_row_ids = normalize_row_ids
        self._relation_preview_selection = relation_preview_selection
        self._resolve_rows_for_amount_check = resolve_rows_for_amount_check
        self._merge_relation_snapshots = merge_relation_snapshots
        self._synthetic_existing_case_relations = synthetic_existing_case_relations
        self._month_scope_for_selected_row_ids = month_scope_for_selected_row_ids
        self._scope_keys_for_row_ids = scope_keys_for_row_ids
        self._scope_keys_for_rows = scope_keys_for_rows
        self._resolve_live_rows_direct = resolve_live_rows_direct
        self._relation_groups = relation_groups
        self._withdraw_rows_and_after_relations = withdraw_rows_and_after_relations
        self._amount_check_for_rows_by_type = amount_check_for_rows_by_type
        self._transaction_amount_for_row_id = transaction_amount_for_row_id
        self._save_exception_cases_snapshot = save_exception_cases_snapshot
        self._persist_pair_relations = persist_pair_relations
        self._restore_exception_pair_snapshots = restore_exception_pair_snapshots
        self._schedule_pair_relation_persist = schedule_pair_relation_persist
        self._restore_pair_relation_snapshot = restore_pair_relation_snapshot
        self._emit_action_timing = emit_action_timing
        self._confirm_link_uow = confirm_link_uow
        self._cancel_link_uow = cancel_link_uow
        self._withdraw_link_uow = withdraw_link_uow
        self._persist_pair_relations_in_transaction = persist_pair_relations_in_transaction
        self._bank_transaction_category_codes_for_row_ids = bank_transaction_category_codes_for_row_ids
        self._bank_flow_rule_tag_rules_payload = bank_flow_rule_tag_rules_payload
        self._relation_command_service = relation_command_service
        self._relation_command_service_factory = relation_command_service_factory

    def preview_confirm_link(self, payload: dict[str, object]) -> WorkbenchWriteResult:
        try:
            month = str(payload["month"])
            row_ids, requested_row_types = self._typed_selection_from_payload(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_confirm_link_preview_request",
                    "message": str(exc),
                },
            )

        before_relations = self._relation_read_snapshot_port.active_relations_for_typed_rows(
            row_ids,
            requested_row_types,
        )
        is_active_selection, withdraw_preview, blocked_message = self._active_relation_withdraw_preview(
            before_relations=before_relations,
            selected_row_ids=row_ids,
            selected_row_types=requested_row_types,
            month=month,
        )
        selection_result = self._relation_preview_selection(
            month,
            row_ids=row_ids,
            row_types=requested_row_types,
        )
        if selection_result.status_code != HTTPStatus.OK:
            return WorkbenchWriteResult(
                HTTPStatus(selection_result.status_code),
                dict(selection_result.payload),
            )
        selection = dict(selection_result.payload)
        selected_rows = [
            dict(row)
            for row in list(selection.get("selected_rows") or [])
            if isinstance(row, dict)
        ]
        try:
            self._assert_canonical_typed_selection(
                row_ids,
                requested_row_types,
                selected_rows,
                minimum_rows=2,
            )
        except (KeyError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_confirm_link_preview_request",
                    "message": str(exc),
                },
            )
        rows = selected_rows
        row_types = requested_row_types
        rows_by_type = self._rows_by_type(rows)
        amount_check = self._amount_check_for_rows_by_type(rows_by_type)
        if is_active_selection:
            if blocked_message:
                return WorkbenchWriteResult(
                    HTTPStatus.OK,
                    self._blocked_confirm_preview_payload(
                        before_relations=before_relations,
                        selected_rows=rows,
                        amount_check=amount_check,
                        message=blocked_message,
                    ),
                )
            assert withdraw_preview is not None
            preview_payload = self._withdraw_relation_preview_payload(
                withdraw_preview,
                month=month,
                alias_map=self._withdraw_alias_map_from_rows(rows),
                selected_rows=rows,
            )
            preview_payload["message"] = (
                preview_payload.get("message")
                or "所选记录已确认关联，可在此撤回这组配对关系。"
            )
            return WorkbenchWriteResult(HTTPStatus.OK, preview_payload)

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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            {
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
            },
        )

    def _active_relation_withdraw_preview(
        self,
        *,
        before_relations: list[dict[str, object]],
        selected_row_ids: list[str],
        selected_row_types: list[str],
        month: str,
    ) -> tuple[bool, dict[str, object] | None, str | None]:
        if not before_relations:
            return False, None, None
        if len(before_relations) > 1:
            return False, None, None
        active_relation = dict(before_relations[0])
        active_row_ids = [str(row_id).strip() for row_id in list(active_relation.get("row_ids") or [])]
        active_row_types = [str(row_type).strip() for row_type in list(active_relation.get("row_types") or [])]
        if len(active_row_ids) != len(active_row_types):
            return True, None, "所选关系成员类型已损坏，请联系管理员。"
        selected_identities = list(zip(selected_row_types, selected_row_ids, strict=True))
        active_identities = list(zip(active_row_types, active_row_ids, strict=True))
        if not selected_identities or set(selected_identities) != set(active_identities):
            return False, None, None

        relation_command = self._relation_command_service_for()
        if relation_command is not None:
            try:
                preview = self._preview_withdraw_relation_via_command_service(
                    relation_command,
                    row_ids=selected_row_ids,
                    row_types=selected_row_types,
                    month=month,
                )
            except WorkbenchRelationCommandError as exc:
                return (
                    True,
                    None,
                    str(exc) or "所选记录已确认关联，但撤回预览暂时不可用。",
                )
            return True, preview, None

        try:
            preview = self._relation_read_snapshot_port.preview_withdraw_for_row_ids(selected_row_ids)
        except Exception:
            return True, None, "所选记录已确认关联，但撤回预览暂时不可用。"
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
        return True, preview_payload, None

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
            row_ids, row_types = self._typed_selection_from_payload(payload)
            case_id = str(payload["case_id"]) if payload.get("case_id") is not None else None
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_request", "message": str(exc)},
            )

        resolve_rows_started_at = monotonic()
        try:
            selected_rows = self._resolve_rows_for_amount_check(
                row_ids,
                row_types=row_types,
                month=month,
            )
            self._assert_canonical_typed_selection(
                row_ids,
                row_types,
                selected_rows,
                minimum_rows=2,
            )
            rows_by_type = self._rows_by_type(selected_rows)
            amount_check = self._amount_check_for_rows_by_type(rows_by_type)
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
        except ValueError as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_confirm_link_request", "message": str(exc)},
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

        self._emit_timing_if_requested(
            request_id=request_id,
            action_name=action_name,
            phase="resolve_rows",
            started_at=resolve_rows_started_at,
            detail=f"rows={len(row_ids)}",
        )

        resolved_case_id = case_id or self._next_case_id()
        paired_policy_metadata = self._bank_transaction_paired_policy_metadata(
            row_ids=row_ids,
            row_types=row_types,
            selected_rows=selected_rows,
            amount_check=amount_check,
        )
        before_relations = self._relation_read_snapshot_port.active_relations_for_typed_rows(
            row_ids,
            row_types,
        )
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(
                selected_rows,
                existing_relations=before_relations,
                month_scope=self._month_scope_for_selected_row_ids(month=month, row_ids=row_ids),
            ),
        )
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
                changed_scope_keys=changed_scope_keys,
                paired_policy_metadata=paired_policy_metadata,
            )

        previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
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
                    paired_policy_metadata=paired_policy_metadata,
                    request_id=request_id,
                    tenant_id=tenant_id,
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
            try:
                self._schedule_pair_relation_persist(
                    changed_case_ids=list(command_result.get("changed_case_ids") or changed_case_ids),
                    request_id=request_id,
                    action_name=action_name,
                )
            except Exception:
                self._restore_pair_relation_snapshot(
                    previous_pair_snapshot,
                    changed_case_ids=changed_case_ids,
                )
                return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
            return WorkbenchWriteResult(
                HTTPStatus.OK,
                self._confirm_link_response_payload(
                    {
                        "success": True,
                        "action": action_name,
                        "month": month,
                        "case_id": resolved_case_id,
                        "affected_row_ids": list(row_ids),
                        "affected_months": list(command_result.get("affected_months") or changed_scope_keys),
                        "affected_scope_keys": list(
                            command_result.get("affected_months") or changed_scope_keys
                        ),
                        "amount_check": amount_check,
                        "message": f"已确认 {len(row_ids)} 条记录关联。",
                    }
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
        changed_scope_keys: list[str],
        paired_policy_metadata: dict[str, object],
    ) -> WorkbenchWriteResult:
        action_name = "confirm_link"
        failure_phase = "uow_enter"
        def emit_phase_timing(phase: str, started_at: float, detail: str | None = None) -> None:
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase=phase,
                started_at=started_at,
                detail=detail,
            )

        idempotency_key = str(
            payload.get("idempotency_key") or payload.get("request_idempotency_key") or ""
        ).strip() or None
        expected_versions = payload.get("expected_versions") if isinstance(payload.get("expected_versions"), dict) else {}
        command = _WorkbenchConfirmLinkCommand(
            action_name=action_name,
            month=month,
            row_ids=list(row_ids),
            row_types=list(row_types),
            case_id=resolved_case_id,
            scope_keys=list(changed_scope_keys),
            payload=dict(payload),
            idempotency_key=idempotency_key,
            expected_versions=dict(expected_versions),
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            timing_emit=emit_phase_timing,
        )

        def handler(ctx: object) -> dict[str, object]:
            nonlocal failure_phase
            failure_phase = "transaction_context"
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            if self._persist_pair_relations_in_transaction is None:
                raise _WorkbenchWritePersistenceError("confirm-link UoW requires transaction-bound pair relation persistence.")
            canonical_query = getattr(ctx, "canonical_query", None)
            validate_selection = getattr(
                canonical_query,
                "validate_workbench_relation_selection_in_current_transaction",
                None,
            )
            if not callable(validate_selection):
                raise _WorkbenchWritePersistenceError(
                    "confirm-link UoW requires transaction-bound canonical selection validation."
                )
            canonical_selection = validate_selection(
                scope_key=month,
                row_ids=row_ids,
                row_types=row_types,
            )
            failure_phase = "canonical_selection"
            canonical_identities = [
                (
                    str(item.get("pane") or ""),
                    str(item.get("row_id") or ""),
                )
                for item in canonical_selection
                if isinstance(item, dict)
            ]
            expected_identities = list(zip(row_types, row_ids, strict=True))
            if canonical_identities != expected_identities:
                raise WorkbenchWriteConflict(
                    action=action_name,
                    reason="canonical_selection_changed",
                    expected={"row_ids": row_ids, "row_types": row_types},
                    actual={
                        "row_ids": [row_id for _row_type, row_id in canonical_identities],
                        "row_types": [row_type for row_type, _row_id in canonical_identities],
                    },
                )
            external_etc_batch_ids = list(
                dict.fromkeys(
                    str(item.get("external_etc_batch_id") or "").strip()
                    for item in canonical_selection
                    if isinstance(item, dict)
                    and str(item.get("external_etc_batch_id") or "").strip()
                )
            )
            if len(external_etc_batch_ids) > 1:
                raise WorkbenchWriteConflict(
                    action=action_name,
                    reason="multiple_etc_batches_selected",
                    expected={"external_etc_batch_count": 1},
                    actual={"external_etc_batch_ids": external_etc_batch_ids},
                )
            transaction_metadata = dict(paired_policy_metadata)
            if external_etc_batch_ids:
                transaction_metadata["external_etc_batch_id"] = external_etc_batch_ids[0]
            pair_relation_started_at = monotonic()
            failure_phase = "relation_command"
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
                paired_policy_metadata=transaction_metadata,
                request_id=request_id,
                tenant_id=tenant_id,
            )
            failure_phase = "handler_result"
            self._emit_timing_if_requested(
                request_id=request_id,
                action_name=action_name,
                phase="pair_relation_update",
                started_at=pair_relation_started_at,
                detail=f"case_id={resolved_case_id}",
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
            failure_phase = "completed"
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
                "Workbench confirm-link UoW failed at phase=%s.",
                failure_phase,
                extra={
                    "workbench_write": {
                        "action": action_name,
                        "phase": failure_phase,
                        "case_id": resolved_case_id,
                        "row_count": len(row_ids),
                        "scope_count": len(changed_scope_keys),
                        "request_id": request_id,
                    }
                },
            )
            return self._persistence_unavailable_result("工作台关联关系暂时无法保存，请稍后重试。")
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            self._confirm_link_response_payload(result),
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
        paired_policy_metadata: dict[str, object],
        request_id: str | None,
        tenant_id: str | None,
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
            special_metadata=dict(paired_policy_metadata or {}),
            idempotency_key=idempotency_key,
            before_relations=list(history_before_relations),
            replace_existing=True,
            history_operation_type="confirm_link",
            request_id=request_id,
            tenant_id=tenant_id,
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
            **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
            "amount_check": dict(result.get("amount_check") or {}),
            "outbox_event_ids": list(result.get("outbox_event_ids") or []),
            "message": str(result.get("message") or ""),
        }

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
        category_codes = self._bank_category_codes_for_policy(bank_row_ids, selected_rows)
        metadata = build_bank_relation_requirement_metadata(
            tag_codes=(str(category_codes.get(row_id) or "") for row_id in bank_row_ids),
            rules_payload=payload,
        )
        if self._is_etc_confirm_link_amount_check(amount_check) or self._selected_rows_include_etc_batch_oa(selected_rows):
            metadata["requires_oa"] = True
            metadata["requires_invoice"] = False
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
            list(preview.get("affected_months") or [])
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
    def _affected_scope_envelope(scope_keys: list[str]) -> dict[str, object]:
        return {"affected_scope_keys": list(dict.fromkeys(scope_keys))}

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
            "workbench_relation_canonical_member_missing",
            "workbench_relation_idempotency_conflict",
            "workbench_relation_immutable_oa_attachment_binding",
            "workbench_relation_multiple_groups_selected",
            "workbench_relation_restore_conflict",
        }
        unavailable_errors = {
            "workbench_relation_command_unavailable",
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
            row_type = str(payload["row_type"]).strip().lower()
            if row_type not in {"oa", "bank", "invoice"}:
                raise ValueError("row_type must be oa, bank, or invoice.")
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
        active_relation = self._relation_read_snapshot_port.active_relation_by_typed_row(
            row_id,
            row_type,
        )
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
            try:
                self._schedule_pair_relation_persist(
                    changed_case_ids=list(command_result.get("changed_case_ids") or changed_case_ids),
                    request_id=request_id,
                    action_name=action_name,
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
            **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
            "outbox_event_ids": list(result.get("outbox_event_ids") or []),
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
            row_ids, row_types = self._typed_selection_from_payload(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_withdraw_link_preview_request", "message": str(exc)},
            )

        relation_command = self._relation_command_service_for()
        if relation_command is None:
            return self._relation_command_unavailable_result()
        selection_result = self._relation_preview_selection(
            month,
            row_ids=row_ids,
            row_types=row_types,
        )
        if selection_result.status_code != HTTPStatus.OK:
            return WorkbenchWriteResult(
                HTTPStatus(selection_result.status_code),
                dict(selection_result.payload),
            )
        selected_rows = [
            dict(row)
            for row in list(selection_result.payload.get("rows") or [])
            if isinstance(row, dict)
        ]
        row_id_aliases = self._withdraw_alias_map_from_rows(selected_rows)
        try:
            preview_relation = self._preview_withdraw_relation_via_command_service(
                relation_command,
                row_ids=row_ids,
                row_types=row_types,
                month=month,
                row_id_aliases=row_id_aliases,
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
        return WorkbenchWriteResult(
            HTTPStatus.OK,
            self._withdraw_relation_preview_payload(
                preview_relation,
                month=month,
                alias_map=row_id_aliases,
                selected_rows=selected_rows,
            ),
        )

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
            row_ids, row_types = self._typed_selection_from_payload(payload)
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
            row_types=row_types,
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
                    row_types=row_types,
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
                row_types=row_types,
                month=month,
                row_id_aliases=row_id_aliases,
            )
            active_relation = dict(preview.get("active_relation") or {})
            case_id = str(active_relation.get("case_id") or "").strip()
            if not case_id:
                raise ValueError("active relation case_id is required.")
            previous_pair_snapshot = self._relation_read_snapshot_port.snapshot()
            result = self._withdraw_relation_via_command_service(
                relation_command,
                payload=payload,
                case_id=case_id,
                actor_id=actor_id,
                reason=note,
                row_id_aliases=row_id_aliases,
                row_ids=row_ids,
                row_types=row_types,
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
                "affected_months": result.get("affected_months") or [],
            },
            affected_row_ids=affected_row_ids,
        )
        try:
            self._schedule_pair_relation_persist(
                changed_case_ids=changed_case_ids,
                request_id=request_id,
                action_name=action_name,
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
                "message": "已撤回 1 组关联。",
            },
        )

    def _withdraw_link_replay_if_committed(
        self,
        *,
        payload: dict[str, object],
        month: str,
        row_ids: list[str],
        row_types: list[str],
        actor_id: str | None,
        tenant_id: str | None,
    ) -> WorkbenchWriteResult | None:
        if self._withdraw_link_uow is None:
            return None
        command = _WorkbenchWithdrawLinkCommand(
            action_name="withdraw_link",
            month=month,
            row_ids=list(row_ids),
            row_types=list(row_types),
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

    def _withdraw_link_with_uow_from_row_ids(
        self,
        *,
        payload: dict[str, object],
        request_id: str | None,
        actor_id: str | None,
        tenant_id: str | None,
        month: str,
        row_ids: list[str],
        row_types: list[str],
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
            row_types=list(row_types),
            case_id="",
            scope_keys=[],
            payload=dict(payload),
            idempotency_key=self._idempotency_key_from_payload(payload),
            expected_versions=dict(payload.get("expected_versions") or {})
            if isinstance(payload.get("expected_versions"), dict)
            else {},
            tenant_id=_normalize_tenant_id(tenant_id),
            actor_id=_normalize_actor_id(actor_id),
            timing_emit=emit_phase_timing,
        )

        def handler(ctx: object) -> dict[str, object]:
            transaction = getattr(ctx, "transaction", None)
            if transaction is None:
                raise _WorkbenchWritePersistenceError("Workbench UoW context is missing transaction.")
            relation_command = self._relation_command_service_for(repository=getattr(ctx, "pair_relations", None))
            if relation_command is None:
                raise _WorkbenchWritePersistenceError("workbench_relation_command_unavailable")
            canonical_query = getattr(ctx, "canonical_query", None)
            validate_selection = getattr(
                canonical_query,
                "validate_workbench_relation_selection_in_current_transaction",
                None,
            )
            if not callable(validate_selection):
                raise _WorkbenchWritePersistenceError(
                    "withdraw-link UoW requires transaction-bound canonical selection validation."
                )
            canonical_selection = validate_selection(
                scope_key=month,
                row_ids=row_ids,
                row_types=row_types,
            )
            canonical_identities = [
                (str(item.get("pane") or ""), str(item.get("row_id") or ""))
                for item in canonical_selection
                if isinstance(item, dict)
            ]
            expected_identities = list(zip(row_types, row_ids, strict=True))
            if canonical_identities != expected_identities:
                raise WorkbenchWriteConflict(
                    action=action_name,
                    reason="canonical_selection_changed",
                    expected={"row_ids": row_ids, "row_types": row_types},
                    actual={
                        "row_ids": [row_id for _row_type, row_id in canonical_identities],
                        "row_types": [row_type for row_type, _row_id in canonical_identities],
                    },
                )
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
                row_types=row_types,
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
                list(result.get("affected_months") or [])
            )
            if not changed_scope_keys:
                changed_scope_keys = self._withdraw_changed_scope_keys(
                    month=month,
                    active_relation=before_relation,
                    preview={"affected_months": result.get("affected_months") or []},
                    affected_row_ids=affected_row_ids,
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
            **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
            "affected_row_ids": list(result.get("affected_row_ids") or []),
            "restored_relations": list(result.get("restored_relations") or []),
            "outbox_event_ids": list(result.get("outbox_event_ids") or []),
            "message": str(result.get("message") or "已撤回 1 组关联。"),
        }

    def _preview_withdraw_relation_via_command_service(
        self,
        relation_command: Any,
        *,
        row_ids: list[str],
        row_types: list[str],
        month: str,
        row_id_aliases: dict[str, str] | None = None,
    ) -> dict[str, object]:
        preview_withdraw_relation = getattr(relation_command, "preview_withdraw_relation", None)
        if not callable(preview_withdraw_relation):
            raise _WorkbenchWritePersistenceError("relation command service must expose preview_withdraw_relation.")
        preview = dict(
            preview_withdraw_relation(
                row_ids=list(row_ids),
                row_types=list(row_types),
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
        row_types: list[str] | None = None,
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
                row_ids=None if row_ids is None else list(row_ids),
                row_types=None if row_types is None else list(row_types),
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
        selected_rows: list[dict[str, object]],
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
        rows = [dict(row) for row in selected_rows]
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

    @staticmethod
    def _relation_row_ids(relations: list[object]) -> list[str]:
        return list(
            dict.fromkeys(
                str(row_id).strip()
                for relation in list(relations or [])
                if isinstance(relation, dict)
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            )
        )

    @classmethod
    def _withdraw_preview_row_ids(cls, preview: dict[str, object] | None) -> list[str]:
        if not isinstance(preview, dict):
            return []
        relations = [
            *list(preview.get("before_relations") or []),
            *list(preview.get("after_relations") or []),
        ]
        active_relation = preview.get("active_relation")
        if isinstance(active_relation, dict):
            relations.append(active_relation)
        return list(
            dict.fromkeys(
                [
                    *[
                        str(row_id).strip()
                        for row_id in list(preview.get("selected_row_ids") or [])
                        if str(row_id).strip()
                    ],
                    *cls._relation_row_ids(relations),
                ]
            )
        )

    @staticmethod
    def _withdraw_alias_map_from_rows(
        rows: list[dict[str, object]],
    ) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for row in rows:
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
            row_ids, row_types = self._cash_special_typed_rows(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids, row_types)
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
            updated_relation, _history = self._relation_special_metadata_mutation_port.update_special_metadata_for_typed_rows(
                row_ids,
                row_types,
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
                **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
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
            row_ids, row_types = self._cash_special_typed_rows(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids, row_types)
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
            updated_relation, _history = self._relation_special_metadata_mutation_port.update_special_metadata_for_typed_rows(
                row_ids,
                row_types,
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
                **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
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
            row_ids, row_types = self._cash_special_typed_rows(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
            relation = self._active_relation_for_cash_special(row_ids, row_types)
            conflict = self._cash_special_stale_conflict(
                action_name="cancel_cash_special",
                payload=payload,
                relation=relation,
            )
            if conflict is not None:
                conflict_payload = conflict.to_response_payload()
                return WorkbenchWriteResult(HTTPStatus(conflict.status_code), dict(conflict_payload["payload"]))
            updated_relation, _history = self._relation_special_metadata_mutation_port.clear_special_metadata_for_typed_rows(
                row_ids,
                row_types,
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
                **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
                "special_metadata": dict(updated_relation.get("special_metadata") or {}),
                "message": "已取消现金往来特殊处理。",
            },
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
            row_ids, row_types = self._typed_selection_from_payload(payload)
            note = str(payload.get("note") or payload.get("comment") or "").strip()
        except (KeyError, TypeError, ValueError) as exc:
            return WorkbenchWriteResult(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_personal_advance_repayment_request", "message": str(exc)},
            )

        try:
            rows = self._resolve_live_rows_direct(
                row_ids,
                row_types=row_types,
                month_hint=month,
            )
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
        before_relations = self._relation_read_snapshot_port.active_relations_for_typed_rows(
            row_ids,
            row_types,
        )
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
                scope_months=[scope for scope in changed_scope_keys if MONTH_SCOPE_RE.match(scope)],
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
                row_types=row_types,
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
                **WorkbenchWriteFacade._affected_scope_envelope(affected_scope_keys),
                "amount_summary": amount_summary,
                "message": "已确认还清个人暂借款。",
            },
        )

    @staticmethod
    def _typed_selection_from_payload(
        payload: dict[str, object],
    ) -> tuple[list[str], list[str]]:
        raw_row_ids = payload.get("row_ids")
        raw_row_types = payload.get("row_types")
        if not isinstance(raw_row_ids, list) or not isinstance(raw_row_types, list):
            raise ValueError("row_ids and row_types are required arrays.")
        row_ids = [str(value or "").strip() for value in raw_row_ids]
        row_types = [str(value or "").strip().lower() for value in raw_row_types]
        if not row_ids or len(row_ids) != len(row_types):
            raise ValueError("row_ids and row_types must be non-empty aligned arrays.")
        if any(not row_id for row_id in row_ids):
            raise ValueError("row_ids must contain non-empty identifiers.")
        aliases = {
            "oa_application": "oa",
            "bank_transaction": "bank",
            "invoice_record": "invoice",
        }
        row_types = [aliases.get(row_type, row_type) for row_type in row_types]
        if any(row_type not in {"oa", "bank", "invoice"} for row_type in row_types):
            raise ValueError("row_types contains an unsupported canonical row type.")
        identities = list(zip(row_types, row_ids, strict=True))
        if len(set(identities)) != len(identities):
            raise ValueError("Workbench selection contains a duplicate typed row.")
        return row_ids, row_types

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
        row_ids, _row_types = self._typed_selection_from_payload(payload)
        return row_ids

    def _cash_special_typed_rows(
        self,
        payload: dict[str, object],
    ) -> tuple[list[str], list[str]]:
        return self._typed_selection_from_payload(payload)

    def _active_relation_for_cash_special(
        self,
        row_ids: list[str],
        row_types: list[str],
    ) -> dict[str, object]:
        if not row_ids:
            raise ValueError("row_ids is required.")
        relations = self._relation_read_snapshot_port.active_relations_for_typed_rows(
            row_ids,
            row_types,
        )
        if len(relations) != 1:
            raise KeyError("workbench_pair_relation_not_found")
        relation = relations[0]
        requested = set(zip(row_types, row_ids, strict=True))
        members = set(
            zip(
                [str(value).strip().lower() for value in list(relation.get("row_types") or [])],
                [str(value).strip() for value in list(relation.get("row_ids") or [])],
                strict=True,
            )
        )
        if requested != members or len(row_ids) != len(members):
            raise ValueError("cash special update requires the complete typed relation selection.")
        return relation

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

    @staticmethod
    def _canonical_row_types(
        row_ids: list[str],
        rows: list[dict[str, object]],
    ) -> list[str]:
        rows_by_id: dict[str, dict[str, object]] = {}
        for row in rows:
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if row_id:
                rows_by_id[row_id] = row
        row_types: list[str] = []
        for row_id in row_ids:
            row = rows_by_id.get(row_id)
            if row is None:
                raise KeyError(row_id)
            row_type = str(row.get("type") or "").strip()
            if row_type not in {"oa", "bank", "invoice"}:
                raise ValueError(f"unsupported canonical row type for confirm link: {row_type or '<empty>'}.")
            row_types.append(row_type)
        return row_types

    @classmethod
    def _canonical_confirm_link_row_types(
        cls,
        row_ids: list[str],
        rows: list[dict[str, object]],
    ) -> list[str]:
        if len(row_ids) < 2:
            raise ValueError("confirm link requires at least two distinct canonical rows.")
        return cls._canonical_row_types(row_ids, rows)

    @staticmethod
    def _assert_canonical_typed_selection(
        row_ids: list[str],
        row_types: list[str],
        rows: list[dict[str, object]],
        *,
        minimum_rows: int = 1,
    ) -> None:
        if len(row_ids) < minimum_rows:
            raise ValueError(
                f"confirm link requires at least {minimum_rows} distinct canonical rows."
            )
        if len(row_ids) != len(row_types) or len(rows) != len(row_ids):
            raise ValueError("canonical Workbench selection changed.")
        expected = list(zip(row_types, row_ids, strict=True))
        actual = [
            (
                str(row.get("type") or "").strip(),
                str(row.get("id") or row.get("row_id") or "").strip(),
            )
            for row in rows
        ]
        if actual != expected:
            raise ValueError("row_types do not match canonical Workbench rows.")

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

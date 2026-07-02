from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re
from threading import RLock
from typing import Any, Callable, Iterable

from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_relation_distribution_mapper import relation_dicts_from_distribution_payload
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


BATCH_ACCOUNTING_SOURCE = "batch_accounting"
BATCH_ACCOUNTING_COUNTERPARTY_NAME = "批量账务集中处理"
BATCH_ACCOUNTING_RELATION_REPAIR_ACTOR = "batch_accounting_relation_repair"

_READ_MODEL_STATUS_PRIORITY = {
    "fresh": 0,
    "refreshing": 1,
    "stale": 2,
    "failed": 3,
    "missing": 4,
    "schema_mismatch": 5,
    "unavailable": 6,
}


class BatchAccountingError(ValueError):
    def __init__(self, code: str, message: str | None = None, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.payload = payload or {}


@dataclass
class _RelationReadModelStatus:
    status: str = "fresh"
    stale_reasons: list[str] | None = None
    read_model_scope_keys: list[str] | None = None
    refresh_enqueued: bool = False

    def record(self, payload: dict[str, Any] | None) -> None:
        if not isinstance(payload, dict):
            return
        status = str(payload.get("status") or payload.get("read_model_status") or "fresh").strip() or "fresh"
        refresh_enqueued = bool(payload.get("refresh_enqueued") or payload.get("refreshEnqueued"))
        stale_reasons = payload.get("stale_reasons") or payload.get("read_model_stale_reasons") or payload.get("readModelStaleReasons")
        if _READ_MODEL_STATUS_PRIORITY.get(status, -1) > _READ_MODEL_STATUS_PRIORITY.get(self.status, -1):
            self.status = status
        self.refresh_enqueued = self.refresh_enqueued or refresh_enqueued
        self.stale_reasons = _append_unique_strings(
            self.stale_reasons or [],
            stale_reasons,
        )
        if status != "fresh" or refresh_enqueued or bool(stale_reasons):
            self.read_model_scope_keys = _append_unique_strings(
                self.read_model_scope_keys or [],
                payload.get("read_model_scope_keys") or payload.get("readModelScopeKeys"),
            )

    def as_payload(self) -> dict[str, Any]:
        return {
            "read_model_status": self.status,
            "read_model_stale_reasons": list(self.stale_reasons or []),
            "read_model_scope_keys": list(self.read_model_scope_keys or []),
            "refresh_enqueued": self.refresh_enqueued,
        }


def _append_unique_strings(existing: list[str], values: Any) -> list[str]:
    result = list(existing)
    seen = set(result)
    if isinstance(values, str):
        iterable: Iterable[Any] = [values]
    elif isinstance(values, Iterable):
        iterable = values
    else:
        iterable = []
    for value in iterable:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


@dataclass
class _WorkbenchContext:
    rows_by_id: dict[str, dict[str, Any]]
    groups: list[dict[str, Any]]
    bank_rows: list[dict[str, Any]]
    open_oa_rows: list[dict[str, Any]]
    invoice_ids_by_oa_id: dict[str, list[str]]
    linked_row_ids: set[str]
    bank_linked_row_ids: set[str]
    eligible_bank_rows: list[dict[str, Any]]
    eligible_oa_rows: list[dict[str, Any]]
    relation_read_model_status: _RelationReadModelStatus


class BatchAccountingService:
    def __init__(
        self,
        *,
        grouped_workbench_loader: Callable[[str], dict[str, Any]],
        batch_workbench_loader: Callable[..., dict[str, Any] | None] | None = None,
        batch_submit_workbench_loader: Callable[..., dict[str, Any] | None] | None = None,
        batch_submitted_workbench_loader: Callable[..., dict[str, Any] | None] | None = None,
        case_id_provider: Callable[[str], str] | None = None,
        relation_facade: Any | None = None,
        relation_command_service: Any | None = None,
    ) -> None:
        self._grouped_workbench_loader = grouped_workbench_loader
        self._batch_workbench_loader = batch_workbench_loader
        self._batch_submit_workbench_loader = batch_submit_workbench_loader
        self._batch_submitted_workbench_loader = batch_submitted_workbench_loader
        self._case_id_provider = case_id_provider or self._default_case_id_for_bank_row
        self._relation_facade = relation_facade
        self._relation_command_service = relation_command_service
        self._mutation_lock = RLock()

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联写入服务不可用，请稍后重试。",
            )
        return self._relation_command_service

    def _active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        command_service = self._require_relation_command_service()
        active_relations = getattr(command_service, "active_relations_for_row_ids", None)
        if not callable(active_relations):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联读取服务不可用，请稍后重试。",
            )
        return [
            deepcopy(relation)
            for relation in list(active_relations(list(row_ids or [])) or [])
            if isinstance(relation, dict)
        ]

    def _active_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        relations = self._active_relations_for_row_ids([row_id])
        return deepcopy(relations[0]) if relations else None

    def _active_bank_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        for relation in self._active_relations_for_row_ids([row_id]):
            if self._relation_has_bank_row(relation):
                return deepcopy(relation)
        return None

    def _active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        command_service = self._require_relation_command_service()
        get_relation = getattr(command_service, "get_active_relation_by_case_id", None)
        if not callable(get_relation):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联读取服务不可用，请稍后重试。",
            )
        try:
            relation = get_relation(case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return None
            raise BatchAccountingError(exc.error_code, exc.message, payload=exc.payload) from exc
        return deepcopy(relation) if isinstance(relation, dict) else None

    def _active_relations(self) -> list[dict[str, Any]]:
        command_service = self._require_relation_command_service()
        list_active = getattr(command_service, "list_active_relations", None)
        if not callable(list_active):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联读取服务不可用，请稍后重试。",
            )
        return [
            deepcopy(relation)
            for relation in list(list_active() or [])
            if isinstance(relation, dict)
        ]

    def _relation_history(self) -> list[dict[str, Any]]:
        command_service = self._require_relation_command_service()
        list_history = getattr(command_service, "list_history", None)
        if not callable(list_history):
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联历史读取服务不可用，请稍后重试。",
            )
        return [
            deepcopy(history)
            for history in list(list_history() or [])
            if isinstance(history, dict)
        ]

    def build_payload(
        self,
        *,
        year: str | None = None,
        bank_year: str | None = None,
        bucket: str,
        page: int | str | None = None,
        page_size: int | str | None = None,
        bank_page: int | str | None = None,
        bank_page_size: int | str | None = None,
        oa_page: int | str | None = None,
        oa_page_size: int | str | None = None,
    ) -> dict[str, Any]:
        fallback_year = str(year or "").strip()
        resolved_bank_year = self._validate_year(bank_year or fallback_year)
        if bucket not in {"unsubmitted", "submitted"}:
            raise BatchAccountingError("invalid_batch_accounting_bucket", "bucket must be unsubmitted or submitted.")
        bank_pagination = self._pagination_from_values(
            page=bank_page if bank_page is not None else page,
            page_size=bank_page_size if bank_page_size is not None else page_size,
            requested=any(value is not None for value in (page, page_size, bank_page, bank_page_size)),
        )
        oa_pagination = self._pagination_from_values(
            page=oa_page if oa_page is not None else page,
            page_size=oa_page_size if oa_page_size is not None else page_size,
            requested=any(value is not None for value in (page, page_size, oa_page, oa_page_size)),
        )
        if bucket == "submitted":
            context = self._build_submitted_list_context(bank_year=resolved_bank_year)
            submitted_relations = self._submitted_relations(resolved_bank_year, context)
            bank_rows, relations_by_bank_row_id = self._submitted_payload(submitted_relations, context)
            oa_rows: list[dict[str, Any]] = []
            submitted_count = len(submitted_relations)
        else:
            context = self._build_list_context(bank_year=resolved_bank_year)
            submitted_count = self._submitted_relation_count(resolved_bank_year, context)
            bank_rows = [self._bank_row_payload(row) for row in context.eligible_bank_rows]
            oa_rows = [self._oa_row_payload(row, context.invoice_ids_by_oa_id.get(str(row.get("id")), [])) for row in context.eligible_oa_rows]
            relations_by_bank_row_id = {}
        visible_bank_rows = self._page_items(bank_rows, bank_pagination)
        visible_oa_rows = self._page_items(oa_rows, oa_pagination)
        if bank_pagination is not None:
            visible_bank_row_ids = {str(row.get("id") or "") for row in visible_bank_rows}
            relations_by_bank_row_id = {
                bank_row_id: relation_payload
                for bank_row_id, relation_payload in relations_by_bank_row_id.items()
                if str(bank_row_id) in visible_bank_row_ids
            }
        return {
            "summary": {
                "unsubmitted_count": len(context.eligible_bank_rows),
                "submitted_count": submitted_count,
                "bank_year": resolved_bank_year,
            },
            "bank_rows": visible_bank_rows,
            "oa_rows": visible_oa_rows,
            "relations_by_bank_row_id": relations_by_bank_row_id,
            **self._pagination_payload(
                bank_rows=bank_rows,
                oa_rows=oa_rows,
                bank_pagination=bank_pagination,
                oa_pagination=oa_pagination,
            ),
            **context.relation_read_model_status.as_payload(),
        }

    @classmethod
    def _pagination_from_values(
        cls,
        *,
        page: int | str | None,
        page_size: int | str | None,
        requested: bool,
    ) -> dict[str, int] | None:
        if not requested:
            return None
        return {
            "page": cls._positive_int(page if page is not None else 1, "page"),
            "page_size": cls._positive_int(page_size if page_size is not None else 100, "page_size", maximum=200),
        }

    @staticmethod
    def _positive_int(value: object, field: str, *, maximum: int | None = None) -> int:
        try:
            number = int(value if value not in (None, "") else 1)
        except (TypeError, ValueError) as exc:
            raise BatchAccountingError("invalid_paging", f"{field} must be a positive integer.") from exc
        if number < 1:
            raise BatchAccountingError("invalid_paging", f"{field} must be a positive integer.")
        if maximum is not None and number > maximum:
            raise BatchAccountingError("invalid_paging", f"{field} must be <= {maximum}.")
        return number

    @staticmethod
    def _page_items(items: list[dict[str, Any]], pagination: dict[str, int] | None) -> list[dict[str, Any]]:
        if pagination is None:
            return items
        start = (pagination["page"] - 1) * pagination["page_size"]
        return items[start : start + pagination["page_size"]]

    @staticmethod
    def _pagination_payload(
        *,
        bank_rows: list[dict[str, Any]],
        oa_rows: list[dict[str, Any]],
        bank_pagination: dict[str, int] | None,
        oa_pagination: dict[str, int] | None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {}
        pagination: dict[str, object] = {}
        if bank_pagination is not None:
            page_size = bank_pagination["page_size"]
            pagination["bank_rows"] = {
                "page": bank_pagination["page"],
                "page_size": page_size,
                "pageSize": page_size,
                "total": len(bank_rows),
            }
        if oa_pagination is not None:
            page_size = oa_pagination["page_size"]
            pagination["oa_rows"] = {
                "page": oa_pagination["page"],
                "page_size": page_size,
                "pageSize": page_size,
                "total": len(oa_rows),
            }
        if pagination:
            payload["pagination"] = pagination
        return payload

    def submit(
        self,
        *,
        year: str | None = None,
        bank_year: str | None = None,
        bank_row_id: str,
        oa_row_ids: list[str],
        actor: str,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        with self._mutation_lock:
            return self._submit_unlocked(
                year=year,
                bank_year=bank_year,
                bank_row_id=bank_row_id,
                oa_row_ids=oa_row_ids,
                actor=actor,
                note=note,
                expected_version=expected_version,
            )

    def _submit_unlocked(
        self,
        *,
        year: str | None = None,
        bank_year: str | None = None,
        bank_row_id: str,
        oa_row_ids: list[str],
        actor: str,
        note: str | None = None,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        fallback_year = str(year or "").strip()
        resolved_bank_year = self._validate_year(bank_year or fallback_year)
        normalized_bank_row_id = self._required_id(bank_row_id, "bank_row_id")
        normalized_oa_row_ids = self._normalize_ids(oa_row_ids)
        context = self._build_submit_context(
            bank_year=resolved_bank_year,
            bank_row_id=normalized_bank_row_id,
            oa_row_ids=normalized_oa_row_ids,
        )
        bank_row = context.rows_by_id.get(normalized_bank_row_id)
        if not isinstance(bank_row, dict) or not self._is_batch_bank_row(bank_row, resolved_bank_year, require_unlinked=False):
            raise BatchAccountingError("invalid_batch_accounting_bank_row", "银行流水不符合批量账务提交条件。")
        if expected_version is not None:
            row_version = self._optional_int(bank_row.get("version"))
            if row_version is not None and row_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "银行流水版本已变化，请刷新后重试。")

        eligible_oa_by_id = {
            str(row.get("id")): row
            for row in context.open_oa_rows
            if self._is_eligible_oa_row_for_submission(row, linked_row_ids=set())
        }
        selected_oa_rows: list[dict[str, Any]] = []
        for oa_row_id in normalized_oa_row_ids:
            oa_row = eligible_oa_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict):
                raise BatchAccountingError("invalid_batch_accounting_oa_row", "OA 单据不符合批量账务提交条件。")
            selected_oa_rows.append(oa_row)

        bank_amount = self._bank_expense_amount(bank_row)
        oa_amount = sum((self._money(row.get("amount")) or Decimal("0.00") for row in selected_oa_rows), Decimal("0.00"))
        amount_check = self._batch_amount_check(bank_amount=bank_amount, oa_amount=oa_amount)
        submit_note = str(note or "").strip()
        if amount_check["status"] == "mismatch" and not submit_note:
            raise BatchAccountingError(
                "batch_accounting_note_required",
                "银行流水金额与所选 OA 金额合计不一致，请填写差额说明。",
                payload={"amount_check": amount_check},
            )
        relation_note = submit_note if amount_check["status"] == "mismatch" else "日常报销批量账务管理提交"

        invoice_row_ids = self._linked_invoice_row_ids(normalized_oa_row_ids, context)
        selected_oa_years = self._selected_oa_years(selected_oa_rows)
        row_ids = self._dedupe([normalized_bank_row_id, *normalized_oa_row_ids, *invoice_row_ids])
        rows = [context.rows_by_id.get(row_id, {"id": row_id, "type": self._row_type_for_row_id(row_id)}) for row_id in row_ids]
        row_types = [self._row_type(row, row_id) for row, row_id in zip(rows, row_ids, strict=False)]
        month_scope = self._month_scope(rows)
        before_relations = self._active_relations_for_row_ids(row_ids)
        if any(normalized_bank_row_id in self._relation_row_id_set(relation) for relation in before_relations):
            raise BatchAccountingError("batch_accounting_bank_row_already_linked", "银行流水已有关联关系，请刷新后重试。")
        for oa_row_id in normalized_oa_row_ids:
            if any(
                oa_row_id in self._relation_row_id_set(relation) and self._relation_has_bank_row(relation)
                for relation in before_relations
            ):
                raise BatchAccountingError("invalid_batch_accounting_oa_row", "OA 单据已有关联流水，请刷新后重试。")
        history_before_relations = self._merge_relation_snapshots(
            before_relations,
            self._synthetic_existing_case_relations(rows, existing_relations=before_relations, month_scope=month_scope),
        )
        special_metadata = {
            "source": BATCH_ACCOUNTING_SOURCE,
            "bank_row_id": normalized_bank_row_id,
            "oa_row_ids": normalized_oa_row_ids,
            "invoice_row_ids": invoice_row_ids,
            "year": resolved_bank_year,
            "bank_year": resolved_bank_year,
            "oa_years": selected_oa_years,
            "created_by": actor,
        }
        case_id = self._case_id_provider(normalized_bank_row_id)
        if self._relation_command_service is None:
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联写入服务不可用，请稍后重试。",
                payload={"case_id": case_id, "row_ids": row_ids},
            )
        try:
            command_result = self._relation_command_service.confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=row_types,
                relation_mode=BATCH_ACCOUNTING_SOURCE,
                actor_id=actor,
                month_scope=month_scope,
                note=relation_note,
                amount_check=amount_check,
                special_metadata=special_metadata,
                before_relations=history_before_relations,
                replace_existing=True,
                history_operation_type="confirm_link",
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc
        relation = dict(command_result.get("relation") or {})
        changed_case_ids = self._dedupe([str(case_id) for case_id in list(command_result.get("changed_case_ids") or [])])
        return {
            "success": True,
            "action": "submit_batch_accounting",
            "relation_id": str(relation.get("case_id") or ""),
            "pair_relation": relation,
            "affected_row_ids": row_ids,
            "changed_case_ids": changed_case_ids,
            "month_scope": str(relation.get("month_scope") or "all"),
            "amount_check": amount_check,
            "message": f"已关联批量账务流水与 {len(normalized_oa_row_ids)} 项 OA。",
        }

    def repair_legacy_case_id_collisions(
        self,
        *,
        actor: str = BATCH_ACCOUNTING_RELATION_REPAIR_ACTOR,
    ) -> dict[str, Any]:
        latest_relations_by_bank_row_id: dict[str, dict[str, Any]] = {}
        for history in self._relation_history():
            if not isinstance(history, dict):
                continue
            for relation in list(history.get("before_relations") or []):
                bank_row_id = self._batch_relation_bank_row_id(relation)
                if bank_row_id:
                    latest_relations_by_bank_row_id.pop(bank_row_id, None)
            for relation in list(history.get("after_relations") or []):
                bank_row_id = self._batch_relation_bank_row_id(relation)
                if bank_row_id:
                    latest_relations_by_bank_row_id[bank_row_id] = deepcopy(relation)

        if not latest_relations_by_bank_row_id:
            return {"changed": False, "changed_case_ids": [], "affected_row_ids": [], "affected_months": []}

        active_row_ids = {
            str(row_id).strip()
            for relation in self._active_relations()
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        repaired_case_ids: list[str] = []
        affected_row_ids: list[str] = []
        affected_months: list[str] = []
        repaired_at = datetime.now(UTC).isoformat()
        repair_note = "修复批量账务关系号复用导致的关联丢失"

        for bank_row_id, relation in sorted(latest_relations_by_bank_row_id.items()):
            if bank_row_id in active_row_ids:
                continue
            target_case_id = self._case_id_provider(bank_row_id)
            existing_target_relation = self._active_relation_by_case_id(target_case_id)
            if isinstance(existing_target_relation, dict):
                continue
            row_ids = self._dedupe(str(row_id) for row_id in list(relation.get("row_ids") or []))
            if not row_ids:
                continue
            row_types = [
                str(row_type).strip()
                for row_type in list(relation.get("row_types") or [])
                if str(row_type).strip()
            ]
            if len(row_types) != len(row_ids):
                row_types = [self._row_type_for_row_id(row_id) for row_id in row_ids]
            metadata = deepcopy(relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {})
            legacy_case_id = str(relation.get("case_id") or "").strip()
            metadata.update(
                {
                    "source": BATCH_ACCOUNTING_SOURCE,
                    "bank_row_id": bank_row_id,
                    "legacy_case_id": legacy_case_id,
                    "repair_source": "batch_accounting_case_id_collision",
                    "repaired_at": repaired_at,
                }
            )
            if self._relation_command_service is None:
                raise BatchAccountingError(
                    "batch_accounting_relation_command_unavailable",
                    "批量账务关联写入服务不可用，请稍后重试。",
                    payload={"case_id": target_case_id, "row_ids": row_ids},
                )
            try:
                command_result = self._relation_command_service.confirm_relation(
                    case_id=target_case_id,
                    row_ids=row_ids,
                    row_types=row_types,
                    relation_mode=str(relation.get("relation_mode") or "manual_confirmed"),
                    actor_id=actor,
                    month_scope=str(relation.get("month_scope") or "all"),
                    note=repair_note,
                    amount_check=deepcopy(relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {}),
                    special_metadata=metadata,
                    exception_case_id=str(relation.get("exception_case_id") or ""),
                    rule_version=str(relation.get("rule_version") or ""),
                    evidence=deepcopy(relation.get("evidence") if isinstance(relation.get("evidence"), dict) else {}),
                    oa_exemption=deepcopy(relation.get("oa_exemption") if isinstance(relation.get("oa_exemption"), dict) else None),
                    display_tags=[
                        str(tag).strip()
                        for tag in list(relation.get("display_tags") or [])
                        if str(tag).strip()
                    ],
                    occurred_at=repaired_at,
                    history_operation_type="repair_batch_accounting_relation_id_collision",
                )
            except WorkbenchRelationCommandError as exc:
                raise self._command_error(exc) from exc
            repaired_relation = dict(command_result.get("relation") or {})
            repaired_case_ids.extend(
                str(case_id)
                for case_id in list(command_result.get("changed_case_ids") or [target_case_id])
                if str(case_id).strip()
            )
            affected_row_ids.extend(row_ids)
            month_scope = str(repaired_relation.get("month_scope") or "").strip()
            if month_scope:
                affected_months.append(month_scope)

        changed_case_ids = self._dedupe(repaired_case_ids)
        return {
            "changed": bool(changed_case_ids),
            "changed_case_ids": changed_case_ids,
            "affected_row_ids": self._dedupe(affected_row_ids),
            "affected_months": self._dedupe(affected_months),
        }

    def withdraw(
        self,
        *,
        relation_id: str,
        actor: str,
        reason: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        with self._mutation_lock:
            return self._withdraw_unlocked(
                relation_id=relation_id,
                actor=actor,
                reason=reason,
                expected_version=expected_version,
            )

    def _withdraw_unlocked(
        self,
        *,
        relation_id: str,
        actor: str,
        reason: str,
        expected_version: int | None = None,
    ) -> dict[str, Any]:
        normalized_relation_id = self._required_id(relation_id, "relation_id")
        note = str(reason or "").strip()
        if not note:
            raise BatchAccountingError("batch_accounting_withdraw_reason_required", "撤回原因不能为空。")
        active_relation = self._active_relation_by_case_id(normalized_relation_id)
        if not self._is_batch_accounting_relation(active_relation):
            raise BatchAccountingError("batch_accounting_relation_not_found", "批量账务关联不存在或不可撤回。")
        if expected_version is not None:
            relation_version = self._optional_int(active_relation.get("version") if isinstance(active_relation, dict) else None)
            if relation_version is not None and relation_version != expected_version:
                raise BatchAccountingError("batch_accounting_version_conflict", "关联版本已变化，请刷新后重试。")
        row_ids = self._normalize_ids(list(active_relation.get("row_ids") or []))
        if self._relation_command_service is None:
            raise BatchAccountingError(
                "batch_accounting_relation_command_unavailable",
                "批量账务关联写入服务不可用，请稍后重试。",
                payload={"case_id": normalized_relation_id, "row_ids": row_ids},
            )
        try:
            command_result = self._relation_command_service.withdraw_relation(
                case_id=normalized_relation_id,
                actor_id=actor,
                reason=note,
                history_operation_type="withdraw_link",
            )
        except WorkbenchRelationCommandError as exc:
            raise self._command_error(exc) from exc
        restored_relations = list(command_result.get("restored_relations") or [])
        affected_row_ids = self._dedupe(list(command_result.get("affected_row_ids") or row_ids))
        changed_case_ids = self._dedupe(
            [str(case_id) for case_id in list(command_result.get("changed_case_ids") or [])]
        )
        return {
            "success": True,
            "action": "withdraw_batch_accounting",
            "relation_id": normalized_relation_id,
            "affected_row_ids": affected_row_ids,
            "restored_relations": restored_relations,
            "changed_case_ids": changed_case_ids,
            "month_scope": str(active_relation.get("month_scope") or "all"),
            "message": "已撤回批量账务关联。",
        }

    def _build_list_context(self, *, bank_year: str) -> _WorkbenchContext:
        return self._context_with_candidate_relation_distribution(
            self._build_workbench_row_context(bank_year=bank_year),
            bank_year=bank_year,
        )

    def _build_submitted_list_context(self, *, bank_year: str) -> _WorkbenchContext:
        return self._build_workbench_row_context(
            bank_year=bank_year,
            payload_loader=self._batch_submitted_workbench_loader,
        )

    def _build_submit_context(
        self,
        *,
        bank_year: str,
        bank_row_id: str,
        oa_row_ids: list[str],
    ) -> _WorkbenchContext:
        if self._batch_submit_workbench_loader is not None:
            return self._build_workbench_row_context(
                bank_year=bank_year,
                payload_loader=lambda *, bank_year: self._batch_submit_workbench_loader(
                    bank_year=bank_year,
                    bank_row_id=bank_row_id,
                    oa_row_ids=list(oa_row_ids),
                ),
            )
        return self._build_workbench_row_context(bank_year=bank_year)

    def _build_workbench_row_context(
        self,
        *,
        bank_year: str,
        payload_loader: Callable[..., dict[str, Any] | None] | None = None,
    ) -> _WorkbenchContext:
        payload = None
        resolved_loader = payload_loader or self._batch_workbench_loader
        if resolved_loader is not None:
            payload = resolved_loader(bank_year=bank_year)
        if not isinstance(payload, dict):
            payload = self._grouped_workbench_loader("all")
        groups = self._groups_from_payload(payload)
        rows_by_id: dict[str, dict[str, Any]] = {}
        bank_rows: list[dict[str, Any]] = []
        open_oa_rows: list[dict[str, Any]] = []
        invoice_ids_by_oa_id: dict[str, list[str]] = {}
        seen_bank_row_ids: set[str] = set()
        seen_open_oa_row_ids: set[str] = set()
        seen_invoice_row_ids: set[str] = set()
        relation_read_model_status = _RelationReadModelStatus()
        for group in groups:
            section = str(group.get("_section") or "")
            for row in list(group.get("bank_rows") or []):
                if not isinstance(row, dict):
                    continue
                bank_row = self._annotated_row(row, group, section)
                bank_row_id = str(bank_row.get("id") or "").strip()
                if not bank_row_id or bank_row_id in seen_bank_row_ids:
                    continue
                seen_bank_row_ids.add(bank_row_id)
                rows_by_id.setdefault(bank_row_id, bank_row)
                bank_rows.append(bank_row)
            group_oa_rows = [
                self._annotated_row(row, group, section)
                for row in list(group.get("oa_rows") or [])
                if isinstance(row, dict)
            ]
            unique_group_oa_rows: list[dict[str, Any]] = []
            for row in group_oa_rows:
                row_id = str(row.get("id") or "").strip()
                if not row_id:
                    continue
                rows_by_id.setdefault(row_id, row)
                unique_group_oa_rows.append(row)
                if section == "open":
                    if row_id in seen_open_oa_row_ids:
                        continue
                    seen_open_oa_row_ids.add(row_id)
                    open_oa_rows.append(row)
            invoice_rows = [
                self._annotated_row(row, group, section)
                for row in list(group.get("invoice_rows") or [])
                if isinstance(row, dict)
            ]
            unique_invoice_rows: list[dict[str, Any]] = []
            for row in invoice_rows:
                row_id = str(row.get("id") or "").strip()
                if not row_id or row_id in seen_invoice_row_ids:
                    continue
                seen_invoice_row_ids.add(row_id)
                rows_by_id.setdefault(row_id, row)
                unique_invoice_rows.append(row)
            if section == "open":
                self._index_group_invoice_links(unique_group_oa_rows, unique_invoice_rows, invoice_ids_by_oa_id)
        return _WorkbenchContext(
            rows_by_id=rows_by_id,
            groups=groups,
            bank_rows=bank_rows,
            open_oa_rows=open_oa_rows,
            invoice_ids_by_oa_id=invoice_ids_by_oa_id,
            linked_row_ids=set(),
            bank_linked_row_ids=set(),
            eligible_bank_rows=[],
            eligible_oa_rows=[],
            relation_read_model_status=relation_read_model_status,
        )

    def _context_with_candidate_relation_distribution(
        self,
        context: _WorkbenchContext,
        *,
        bank_year: str,
    ) -> _WorkbenchContext:
        candidate_bank_rows = [
            row
            for row in context.bank_rows
            if self._is_batch_bank_row(
                row,
                bank_year,
                require_unlinked=False,
            )
        ]
        candidate_oa_rows = [
            row
            for row in context.open_oa_rows
            if self._is_eligible_oa_row(row, linked_row_ids=set())
        ]
        linked_row_ids, bank_linked_row_ids = self._relation_distribution_row_id_sets(
            [*candidate_bank_rows, *candidate_oa_rows],
            read_model_status=context.relation_read_model_status,
        )
        eligible_bank_rows = [
            row
            for row in candidate_bank_rows
            if self._is_batch_bank_row(
                row,
                bank_year,
                require_unlinked=True,
                linked_row_ids=linked_row_ids,
            )
        ]
        eligible_oa_rows = [
            row
            for row in candidate_oa_rows
            if self._is_eligible_oa_row(row, linked_row_ids=bank_linked_row_ids)
        ]
        return replace(
            context,
            linked_row_ids=linked_row_ids,
            bank_linked_row_ids=bank_linked_row_ids,
            eligible_bank_rows=eligible_bank_rows,
            eligible_oa_rows=eligible_oa_rows,
        )

    def _submitted_relation_count(self, year: str, context: _WorkbenchContext) -> int:
        if context.relation_read_model_status.status != "fresh":
            return 0
        if self._relation_facade is None:
            return 0
        counter = getattr(self._relation_facade, "count_batch_accounting_relations_by_year", None)
        if not callable(counter):
            context.relation_read_model_status.record(
                {
                    "status": "unavailable",
                    "read_model_scope_keys": self._month_scope_keys_for_year(year),
                    "stale_reasons": ["batch_accounting_relation_count_unavailable"],
                }
            )
            return 0
        try:
            payload = counter(
                year,
                require_fresh=True,
                reason="batch_accounting_submitted_relation_count",
            )
        except TypeError:
            payload = counter(year)
        context.relation_read_model_status.record(payload if isinstance(payload, dict) else None)
        if not isinstance(payload, dict):
            return 0
        return self._optional_int(payload.get("submitted_count")) or 0

    @staticmethod
    def _groups_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        for section in ("open", "paired"):
            section_payload = payload.get(section)
            if not isinstance(section_payload, dict):
                continue
            for group in list(section_payload.get("groups") or []):
                if isinstance(group, dict):
                    groups.append({**group, "_section": section})
        return groups

    @staticmethod
    def _annotated_row(row: dict[str, Any], group: dict[str, Any], section: str) -> dict[str, Any]:
        result = deepcopy(row)
        result["_section"] = section
        result["_group_id"] = str(group.get("group_id") or "")
        group_case_id = str(group.get("case_id") or "").strip()
        if not group_case_id and str(group.get("group_id") or "").startswith("case:"):
            group_case_id = str(group.get("group_id"))[5:]
        result["_group_case_id"] = group_case_id
        return result

    def _index_group_invoice_links(
        self,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        invoice_ids_by_oa_id: dict[str, list[str]],
    ) -> None:
        oa_ids = [str(row.get("id") or "").strip() for row in oa_rows if str(row.get("id") or "").strip()]
        for invoice_row in invoice_rows:
            if not self._is_oa_attachment_invoice(invoice_row):
                continue
            invoice_id = str(invoice_row.get("id") or "").strip()
            if not invoice_id:
                continue
            linked_oa_id = self._invoice_source_oa_id(invoice_row, oa_ids)
            if linked_oa_id:
                invoice_ids_by_oa_id.setdefault(linked_oa_id, []).append(invoice_id)

    def _is_batch_bank_row(
        self,
        row: dict[str, Any],
        year: str,
        *,
        require_unlinked: bool,
        linked_row_ids: set[str] | None = None,
    ) -> bool:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            return False
        if str(row.get("type") or "bank") != "bank" and self._row_type_for_row_id(row_id) != "bank":
            return False
        if self._clean_text(row.get("counterparty_name")) != BATCH_ACCOUNTING_COUNTERPARTY_NAME:
            return False
        if not self._row_year_matches(row, year, keys=("trade_time", "pay_receive_time", "txn_date", "transaction_date", "date")):
            return False
        if self._bank_expense_amount(row) <= Decimal("0.00"):
            return False
        if require_unlinked and row_id in (linked_row_ids or set()):
            return False
        return True

    def _is_eligible_oa_row(
        self,
        row: dict[str, Any],
        *,
        linked_row_ids: set[str] | None = None,
    ) -> bool:
        return self._is_eligible_oa_row_for_submission(row, linked_row_ids=linked_row_ids)

    def _is_eligible_oa_row_for_submission(
        self,
        row: dict[str, Any],
        *,
        linked_row_ids: set[str] | None = None,
    ) -> bool:
        row_id = str(row.get("id") or "").strip()
        if not row_id:
            return False
        if row_id in (linked_row_ids or set()):
            return False
        if str(row.get("type") or "oa") != "oa" and self._row_type_for_row_id(row_id) != "oa":
            return False
        if ":item:" in row_id or str(row.get("row_kind") or "").strip() in {"schedule_detail", "detail"}:
            return False
        if not self._contains_daily_reimbursement(row):
            return False
        return True

    def _linked_distribution_row_ids(
        self,
        rows: list[dict[str, Any]],
        *,
        read_model_status: _RelationReadModelStatus,
    ) -> set[str]:
        linked_row_ids, _bank_linked_row_ids = self._relation_distribution_row_id_sets(
            rows,
            read_model_status=read_model_status,
        )
        return linked_row_ids

    def _relation_distribution_row_id_sets(
        self,
        rows: list[dict[str, Any]],
        *,
        read_model_status: _RelationReadModelStatus,
    ) -> tuple[set[str], set[str]]:
        row_ids = self._dedupe(
            str(row.get("id") or "").strip()
            for row in list(rows or [])
            if isinstance(row, dict) and str(row.get("id") or "").strip()
        )
        if not row_ids or self._relation_facade is None:
            return set(), set()
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return set(), set()
        scope_keys_hint = self._scope_keys_for_rows(rows)
        try:
            payload = reader(
                row_ids,
                require_fresh=True,
                reason="batch_accounting_unsubmitted_relations",
                scope_keys_hint=scope_keys_hint,
            )
        except TypeError:
            payload = reader(row_ids)
        read_model_status.record(payload if isinstance(payload, dict) else None)
        if not isinstance(payload, dict):
            return set(), set()
        linked: set[str] = set()
        bank_linked: set[str] = set()
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id") or "").strip()
            if not row_id:
                continue
            group_ids = [str(group_id).strip() for group_id in list(row.get("group_ids") or []) if str(group_id).strip()]
            relation_status = str(row.get("relation_status") or "").strip()
            if group_ids or relation_status in {"linked", "partial", "conflict", "stale_source"}:
                linked.add(row_id)
            if self._distribution_row_has_linked_bank_transaction(row):
                bank_linked.add(row_id)
        for relation in relation_dicts_from_distribution_payload(payload):
            if not self._relation_has_bank_row(relation):
                continue
            for row_id in list(relation.get("row_ids") or []):
                normalized_row_id = str(row_id or "").strip()
                if normalized_row_id:
                    bank_linked.add(normalized_row_id)
        return linked, bank_linked

    def _submitted_relations(self, year: str, context: _WorkbenchContext) -> list[dict[str, Any]]:
        if self._relation_facade is None:
            return []
        list_by_year = getattr(self._relation_facade, "list_batch_accounting_relations_by_year", None)
        if callable(list_by_year):
            try:
                payload = list_by_year(
                    year,
                    require_fresh=True,
                    reason="batch_accounting_submitted_relations",
                )
            except TypeError:
                payload = list_by_year(year)
            context.relation_read_model_status.record(payload if isinstance(payload, dict) else None)
            if not isinstance(payload, dict):
                return []
            return [
                relation
                for relation in relation_dicts_from_distribution_payload(payload)
                if self._is_batch_accounting_relation(relation)
            ]
        list_by_month = getattr(self._relation_facade, "list_by_month", None)
        if not callable(list_by_month):
            return []
        relations: list[dict[str, Any]] = []
        seen_case_ids: set[str] = set()
        for month in self._month_scope_keys_for_year(year):
            try:
                payload = list_by_month(
                    month,
                    row_types=["bank_transaction"],
                    require_fresh=True,
                    reason="batch_accounting_submitted_relations",
                )
            except TypeError:
                payload = list_by_month(month)
            context.relation_read_model_status.record(payload if isinstance(payload, dict) else None)
            for relation in relation_dicts_from_distribution_payload(payload):
                case_id = str(relation.get("case_id") or "").strip()
                if not case_id or case_id in seen_case_ids or not self._is_batch_accounting_relation(relation):
                    continue
                metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
                bank_row_id = str(metadata.get("bank_row_id") or "").strip() or self._bank_row_id_for_relation(relation)
                bank_row = context.rows_by_id.get(bank_row_id)
                if str(metadata.get("year") or metadata.get("bank_year") or "").strip() == year or (
                    isinstance(bank_row, dict) and self._row_year_matches(bank_row, year, keys=("trade_time", "pay_receive_time", "txn_date"))
                ):
                    relations.append(relation)
                    seen_case_ids.add(case_id)
        return relations

    @staticmethod
    def _month_scope_keys_for_year(year: str) -> list[str]:
        normalized_year = str(year or "").strip()
        if re.fullmatch(r"\d{4}", normalized_year):
            return [f"{normalized_year}-{month:02d}" for month in range(1, 13)]
        return ["all"]

    def _submitted_payload(
        self,
        relations: list[dict[str, Any]],
        context: _WorkbenchContext,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        bank_rows: list[dict[str, Any]] = []
        relations_by_bank_row_id: dict[str, Any] = {}
        bank_row_ids = [self._bank_row_id_for_relation(relation) for relation in relations]
        distribution_rows = self._distribution_rows_by_bank_id(
            bank_row_ids,
            read_model_status=context.relation_read_model_status,
        )
        for relation in relations:
            metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
            bank_row_id = self._bank_row_id_for_relation(relation)
            if not bank_row_id:
                continue
            bank_row = context.rows_by_id.get(bank_row_id, {"id": bank_row_id, "type": "bank"})
            bank_payload = self._bank_row_payload(bank_row, relation_id=str(relation.get("case_id") or ""))
            bank_rows.append(bank_payload)
            oa_row_ids = [str(row_id) for row_id in list(metadata.get("oa_row_ids") or []) if str(row_id).strip()]
            invoice_row_ids = [str(row_id) for row_id in list(metadata.get("invoice_row_ids") or []) if str(row_id).strip()]
            distribution_row = distribution_rows.get(bank_row_id)
            if distribution_row is not None:
                oa_rows = self._oa_rows_from_distribution(distribution_row, context)
                invoice_rows = self._invoice_rows_from_distribution(distribution_row, context)
            else:
                oa_rows = [self._oa_row_payload(context.rows_by_id.get(row_id, {"id": row_id, "type": "oa"}), []) for row_id in oa_row_ids]
                invoice_rows = [
                    deepcopy(context.rows_by_id.get(row_id, {"id": row_id, "type": "invoice"}))
                    for row_id in invoice_row_ids
                ]
            relations_by_bank_row_id[bank_row_id] = {
                "relation_id": str(relation.get("case_id") or ""),
                "relation": deepcopy(relation),
                "oa_rows": oa_rows,
                "invoice_rows": invoice_rows,
                "metadata": deepcopy(metadata),
            }
        return bank_rows, relations_by_bank_row_id

    def _bank_row_id_for_relation(self, relation: dict[str, Any]) -> str:
        metadata = relation.get("special_metadata") if isinstance(relation.get("special_metadata"), dict) else {}
        bank_row_id = str(metadata.get("bank_row_id") or "").strip()
        if bank_row_id:
            return bank_row_id
        return next(
            (str(row_id) for row_id in list(relation.get("row_ids") or []) if self._row_type_for_row_id(str(row_id)) == "bank"),
            "",
        )

    def _distribution_rows_by_bank_id(
        self,
        bank_row_ids: list[str],
        *,
        read_model_status: _RelationReadModelStatus,
    ) -> dict[str, dict[str, Any]]:
        normalized_ids = []
        seen: set[str] = set()
        for row_id in bank_row_ids:
            text = str(row_id or "").strip()
            if text and text not in seen:
                seen.add(text)
                normalized_ids.append(text)
        if not normalized_ids or self._relation_facade is None:
            return {}
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            return {}
        try:
            payload = reader(normalized_ids, require_fresh=True, reason="batch_accounting_submitted_relations")
        except TypeError:
            payload = reader(normalized_ids)
        read_model_status.record(payload if isinstance(payload, dict) else None)
        if not isinstance(payload, dict):
            return {}
        rows: dict[str, dict[str, Any]] = {}
        for row in list(payload.get("rows") or []):
            if not isinstance(row, dict):
                continue
            row_id = str(row.get("row_id") or "").strip()
            if row_id:
                rows[row_id] = row
        return rows

    def _oa_rows_from_distribution(self, row: dict[str, Any], context: _WorkbenchContext) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        seen: set[str] = set()
        for item in list(row.get("linked_oa") or []):
            if not isinstance(item, dict):
                continue
            row_id = str(item.get("id") or item.get("oa_id") or "").strip()
            if not row_id or row_id in seen:
                continue
            seen.add(row_id)
            source = dict(context.rows_by_id.get(row_id, {"id": row_id, "type": "oa"}))
            source.update({key: value for key, value in item.items() if value not in (None, "")})
            payloads.append(self._oa_row_payload(source, []))
        return payloads

    def _invoice_rows_from_distribution(self, row: dict[str, Any], context: _WorkbenchContext) -> list[dict[str, Any]]:
        payloads: list[dict[str, Any]] = []
        seen: set[str] = set()
        for key in ("linked_input_invoices", "linked_output_invoices"):
            for item in list(row.get(key) or []):
                if not isinstance(item, dict):
                    continue
                row_id = str(item.get("id") or item.get("invoice_id") or "").strip()
                if not row_id or row_id in seen:
                    continue
                seen.add(row_id)
                source = dict(context.rows_by_id.get(row_id, {"id": row_id, "type": "invoice"}))
                source.update({item_key: value for item_key, value in item.items() if value not in (None, "")})
                payloads.append(source)
        return payloads

    def _bank_row_payload(self, row: dict[str, Any], *, relation_id: str = "") -> dict[str, Any]:
        amount = self._bank_expense_amount(row)
        bank_name, account_last4 = self._bank_account_parts(row)
        return {
            "id": str(row.get("id") or ""),
            "trade_time": str(row.get("trade_time") or row.get("pay_receive_time") or row.get("txn_date") or ""),
            "counterparty_name": self._clean_text(row.get("counterparty_name")),
            "direction": "expense",
            "direction_label": "支出",
            "amount": self._format_amount(amount),
            "bank_name": bank_name,
            "account_last4": account_last4,
            "relation_id": relation_id,
            "version": self._optional_int(row.get("version")) or 1,
        }

    def _oa_row_payload(self, row: dict[str, Any], linked_invoice_row_ids: list[str]) -> dict[str, Any]:
        return {
            "id": str(row.get("id") or ""),
            "applicant": self._first_text(row, ("applicant", "applicant_name", "apply_user", "userName"), ("申请人",)),
            "apply_time": self._first_text(
                row,
                ("apply_time", "application_time", "application_date", "date", "created_at"),
                ("申请日期", "单据日期", "日期"),
            ),
            "project_name": self._first_text(row, ("project_name", "project"), ("项目名称", "项目")),
            "amount": self._format_amount(self._money(row.get("amount")) or Decimal("0.00")),
            "reason": self._first_text(row, ("reason", "remark"), ("申请事由", "报销事由", "事由", "备注")),
            "apply_type": str(row.get("apply_type") or ""),
            "expense_type": str(row.get("expense_type") or ""),
            "linked_invoice_row_ids": list(linked_invoice_row_ids),
        }

    def _synthetic_existing_case_relations(
        self,
        rows: Iterable[dict[str, Any]],
        *,
        existing_relations: list[dict[str, Any]],
        month_scope: str,
    ) -> list[dict[str, Any]]:
        covered_row_ids = {
            str(row_id).strip()
            for relation in existing_relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        rows_by_case_id: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            row_id = str(row.get("id") or "").strip()
            case_id = str(row.get("case_id") or row.get("_group_case_id") or "").strip()
            if not row_id or not case_id or row_id in covered_row_ids:
                continue
            rows_by_case_id.setdefault(case_id, []).append(row)
        relations: list[dict[str, Any]] = []
        for case_id, case_rows in rows_by_case_id.items():
            if len(case_rows) < 2:
                continue
            relations.append(
                {
                    "case_id": case_id,
                    "row_ids": [str(row.get("id") or "").strip() for row in case_rows],
                    "row_types": [self._row_type(row, str(row.get("id") or "")) for row in case_rows],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": month_scope,
                }
            )
        return relations

    @staticmethod
    def _merge_relation_snapshots(
        primary_relations: list[dict[str, Any]],
        secondary_relations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        merged: dict[str, dict[str, Any]] = {}
        for relation in [*primary_relations, *secondary_relations]:
            case_id = str(relation.get("case_id") or "").strip()
            if case_id:
                merged[case_id] = relation
        return list(merged.values())

    @staticmethod
    def _relation_row_id_set(relation: dict[str, Any]) -> set[str]:
        return {str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()}

    def _linked_invoice_row_ids(self, oa_row_ids: list[str], context: _WorkbenchContext) -> list[str]:
        invoice_row_ids: list[str] = []
        for oa_row_id in oa_row_ids:
            invoice_row_ids.extend(context.invoice_ids_by_oa_id.get(oa_row_id, []))
        return self._dedupe(invoice_row_ids)

    @staticmethod
    def _command_error(exc: WorkbenchRelationCommandError) -> BatchAccountingError:
        if exc.error_code == "workbench_relation_read_model_not_fresh":
            return BatchAccountingError(
                "batch_accounting_read_model_not_fresh",
                "关联台关系读模型不是 fresh，请刷新后再处理。",
                payload=dict(exc.payload),
            )
        if exc.error_code == "workbench_relation_active_row_conflict":
            return BatchAccountingError(
                "batch_accounting_relation_conflict",
                "所选流水或 OA 已有关联关系，请刷新后重试。",
                payload=dict(exc.payload),
            )
        if exc.error_code == "workbench_relation_not_found":
            return BatchAccountingError(
                "batch_accounting_relation_not_found",
                "批量账务关联不存在或不可撤回。",
                payload=dict(exc.payload),
            )
        return BatchAccountingError(exc.error_code, exc.message, payload=dict(exc.payload))

    @classmethod
    def _scope_keys_for_rows(cls, rows: Iterable[dict[str, Any]]) -> list[str]:
        return cls._dedupe(
            month
            for row in list(rows or [])
            if isinstance(row, dict)
            for month in [cls._row_month(row)]
            if month is not None
        )

    @staticmethod
    def _is_batch_accounting_relation(relation: dict[str, Any] | None) -> bool:
        if not isinstance(relation, dict):
            return False
        metadata = relation.get("special_metadata")
        return relation.get("status") == "active" and isinstance(metadata, dict) and metadata.get("source") == BATCH_ACCOUNTING_SOURCE

    @staticmethod
    def _validate_year(year: str) -> str:
        resolved_year = str(year or "").strip()
        if not re.fullmatch(r"20\d{2}", resolved_year):
            raise BatchAccountingError("invalid_batch_accounting_year", "year must be a four-digit year.")
        return resolved_year

    @staticmethod
    def _required_id(value: str, field_name: str) -> str:
        resolved = str(value or "").strip()
        if not resolved:
            raise BatchAccountingError("invalid_batch_accounting_request", f"{field_name} is required.")
        return resolved

    @classmethod
    def _normalize_ids(cls, values: list[Any]) -> list[str]:
        ids = cls._dedupe([str(value or "").strip() for value in values])
        if not ids:
            raise BatchAccountingError("invalid_batch_accounting_request", "at least one OA row is required.")
        return ids

    @staticmethod
    def _dedupe(values: Iterable[str]) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = str(value or "").strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            result.append(normalized)
        return result

    @staticmethod
    def _default_case_id_for_bank_row(bank_row_id: str) -> str:
        safe_bank_row_id = re.sub(r"[^A-Za-z0-9_-]+", "-", str(bank_row_id or "").strip()).strip("-")
        if not safe_bank_row_id:
            raise BatchAccountingError("invalid_batch_accounting_bank_row", "银行流水 ID 不能为空。")
        return f"CASE-BATCH-{safe_bank_row_id[:96]}"

    @classmethod
    def _batch_relation_bank_row_id(cls, relation: Any) -> str:
        if not isinstance(relation, dict):
            return ""
        metadata = relation.get("special_metadata")
        if not isinstance(metadata, dict) or metadata.get("source") != BATCH_ACCOUNTING_SOURCE:
            return ""
        relation_row_ids = [cls._clean_text(row_id) for row_id in list(relation.get("row_ids") or []) if cls._clean_text(row_id)]
        relation_bank_row_ids = [
            row_id
            for row_id in relation_row_ids
            if cls._row_type_for_row_id(row_id) == "bank"
        ]
        bank_row_id = cls._clean_text(metadata.get("bank_row_id"))
        if bank_row_id and bank_row_id in relation_row_ids:
            return bank_row_id
        if len(relation_bank_row_ids) == 1:
            return relation_bank_row_ids[0]
        return ""

    @classmethod
    def _relation_has_bank_row(cls, relation: Any) -> bool:
        if not isinstance(relation, dict):
            return False
        row_ids = [cls._clean_text(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [cls._clean_text(row_type) for row_type in list(relation.get("row_types") or [])]
        for index, row_id in enumerate(row_ids):
            row_type = row_types[index] if index < len(row_types) else cls._row_type_for_row_id(row_id)
            if row_type in {"bank", "bank_transaction"} or cls._row_type_for_row_id(row_id) == "bank":
                return True
        return False

    @classmethod
    def _distribution_row_has_linked_bank_transaction(cls, row: dict[str, Any]) -> bool:
        for item in list(row.get("linked_bank_transactions") or []):
            if isinstance(item, dict):
                bank_row_id = cls._clean_text(item.get("id") or item.get("transaction_id") or item.get("row_id"))
            else:
                bank_row_id = cls._clean_text(item)
            if bank_row_id:
                return True
        return False

    @staticmethod
    def _clean_text(value: Any) -> str:
        return str(value or "").strip()

    @classmethod
    def _first_text(
        cls,
        row: dict[str, Any],
        keys: tuple[str, ...],
        nested_keys: tuple[str, ...] = (),
    ) -> str:
        for key in keys:
            value = cls._clean_text(row.get(key))
            if value:
                return value
        for nested_field in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_field)
            if not isinstance(nested, dict):
                continue
            for key in nested_keys:
                value = cls._clean_text(nested.get(key))
                if value:
                    return value
        return ""

    @classmethod
    def _contains_daily_reimbursement(cls, row: dict[str, Any]) -> bool:
        return "日常报销" in cls._clean_text(row.get("apply_type")) or "日常报销" in cls._clean_text(row.get("expense_type"))

    @classmethod
    def _row_year_matches(
        cls,
        row: dict[str, Any],
        year: str,
        *,
        keys: tuple[str, ...],
        nested_date_keys: tuple[str, ...] = (),
    ) -> bool:
        values: list[Any] = [row.get(key) for key in keys]
        for nested_key in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_key)
            if isinstance(nested, dict):
                values.extend(nested.get(key) for key in nested_date_keys)
        return any(str(value or "").strip().startswith(year) for value in values)

    @classmethod
    def _bank_expense_amount(cls, row: dict[str, Any]) -> Decimal:
        debit = cls._money(row.get("debit_amount"))
        if debit is not None and debit > Decimal("0.00"):
            return debit
        direction = cls._clean_text(row.get("direction") or row.get("txn_direction") or row.get("direction_code")).lower()
        amount = cls._money(row.get("amount")) or cls._money(row.get("signed_amount")) or Decimal("0.00")
        if direction in {"expense", "outflow", "支出"}:
            return abs(amount)
        signed_amount = cls._money(row.get("signed_amount"))
        if signed_amount is not None and signed_amount < Decimal("0.00"):
            return abs(signed_amount)
        return Decimal("0.00")

    @staticmethod
    def _money(value: Any) -> Decimal | None:
        if value in (None, ""):
            return None
        try:
            return Decimal(str(value).replace(",", "")).copy_abs()
        except (InvalidOperation, ValueError):
            return None

    @staticmethod
    def _quantize(value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    @classmethod
    def _format_amount(cls, value: Decimal) -> str:
        return f"{cls._quantize(value):.2f}"

    def _batch_amount_check(self, *, bank_amount: Decimal, oa_amount: Decimal) -> dict[str, Any]:
        amount_delta = self._quantize(bank_amount) - self._quantize(oa_amount)
        status = "matched" if amount_delta == Decimal("0.00") else "mismatch"
        return {
            "status": status,
            "direction": "expense",
            "bank_amount": self._format_amount(bank_amount),
            "oa_amount": self._format_amount(oa_amount),
            "amount_delta": self._format_amount(amount_delta),
            "requires_note": status == "mismatch",
        }

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _bank_account_parts(cls, row: dict[str, Any]) -> tuple[str, str]:
        label = cls._clean_text(row.get("payment_account_label") or row.get("account_label"))
        bank_name = cls._clean_text(row.get("bank_name") or row.get("selected_bank_name") or row.get("imported_bank_name"))
        account_last4 = cls._clean_text(row.get("account_last4") or row.get("selected_bank_last4") or row.get("imported_bank_last4"))
        if label:
            parts = label.split()
            if not bank_name and parts:
                bank_name = parts[0].replace("基本户", "").replace("一般户", "")
            if not account_last4:
                digit_groups = re.findall(r"\d{4,}", label)
                if digit_groups:
                    account_last4 = digit_groups[-1][-4:]
        return bank_name, account_last4

    @classmethod
    def _is_oa_attachment_invoice(cls, row: dict[str, Any]) -> bool:
        return cls._clean_text(row.get("source_kind")) == "oa_attachment_invoice" or cls._clean_text(row.get("id")).startswith("oa-att-inv-")

    @classmethod
    def _invoice_source_oa_id(cls, invoice_row: dict[str, Any], oa_ids: list[str]) -> str | None:
        for key in ("derived_from_oa_id", "source_oa_id", "oa_row_id"):
            value = cls._clean_text(invoice_row.get(key))
            if value in oa_ids:
                return value
        invoice_id = cls._clean_text(invoice_row.get("id"))
        prefix = "oa-att-inv-"
        if invoice_id.startswith(prefix):
            tail = invoice_id[len(prefix):]
            for oa_id in sorted(oa_ids, key=len, reverse=True):
                if tail == oa_id or tail.startswith(f"{oa_id}-"):
                    return oa_id
        if len(oa_ids) == 1:
            return oa_ids[0]
        return None

    @classmethod
    def _row_type(cls, row: dict[str, Any], row_id: str) -> str:
        return str(row.get("type") or cls._row_type_for_row_id(row_id) or "unknown")

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        return row_type_for_workbench_row_id(row_id)

    @classmethod
    def _month_scope(cls, rows: Iterable[dict[str, Any]]) -> str:
        months = {
            month
            for row in rows
            for month in [cls._row_month(row)]
            if month is not None
        }
        if len(months) == 1:
            return next(iter(months))
        return "all"

    @classmethod
    def _row_month(cls, row: dict[str, Any]) -> str | None:
        for key in (
            "trade_time",
            "pay_receive_time",
            "txn_date",
            "apply_time",
            "application_time",
            "application_date",
            "issue_date",
        ):
            value = str(row.get(key) or "").strip()
            if re.match(r"20\d{2}-\d{2}", value):
                return value[:7]
        for nested_key in ("summary_fields", "detail_fields", "_summary_fields", "_detail_fields"):
            nested = row.get(nested_key)
            if not isinstance(nested, dict):
                continue
            for key in ("申请日期", "单据日期", "日期"):
                value = str(nested.get(key) or "").strip()
                if re.match(r"20\d{2}-\d{2}", value):
                    return value[:7]
        return None

    @classmethod
    def _row_year(cls, row: dict[str, Any]) -> str | None:
        month = cls._row_month(row)
        if month and re.fullmatch(r"20\d{2}-\d{2}", month):
            return month[:4]
        return None

    @classmethod
    def _selected_oa_years(cls, rows: Iterable[dict[str, Any]]) -> list[str]:
        return sorted(
            {
                year
                for row in rows
                for year in [cls._row_year(row)]
                if year is not None
            }
        )

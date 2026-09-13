from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.app_settings_service import AppSettingsService
from fin_ops_platform.services.cost_statistics_allocation_scope import merge_source_decision
from fin_ops_platform.services.cost_statistics_canonical_repository import (
    PostgresCostStatisticsCanonicalRepository,
)
from fin_ops_platform.services.cost_statistics_manual_items import allocation_targets, validate_manual_items
from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from fin_ops_platform.services.cost_statistics_source_allocation import (
    SourceAllocationError,
    complete_source_task,
    suggest_source_allocations,
    validate_source_allocations,
)
from fin_ops_platform.services.postgres_repositories.cost_statistics_manual_allocation import (
    PostgresCostStatisticsManualAllocationRepository,
)
from fin_ops_platform.services.postgres_repositories.operations_audit import (
    PostgresOperationsAuditRepository,
)

MONEY_PATTERN = re.compile(r"^(?:0|[1-9]\d{0,14})\.\d{2}$")


class CostStatisticsManualAllocationValidationError(ValueError):
    error_code = "invalid_cost_statistics_manual_allocation"


class CostStatisticsManualAllocationConflictError(ValueError):
    error_code = "cost_statistics_manual_allocation_conflict"


class CostStatisticsManualAllocationService:
    """List and atomically save explicit allocations for complex relations."""

    def __init__(
        self,
        *,
        canonical_repository: Any,
        allocation_repository: Any,
        write_connection: Any | None = None,
    ) -> None:
        if not callable(
            getattr(canonical_repository, "load_manual_allocation_task_snapshot", None)
        ):
            raise ValueError(
                "Cost statistics manual allocation service requires a task snapshot repository."
            )
        self._canonical_repository = canonical_repository
        self._allocation_repository = allocation_repository
        self._write_connection = write_connection

    def list_tasks(
        self,
        *,
        cursor: str | None,
        page_size: int,
        status: str,
        query: str | None,
        can_save: bool,
    ) -> dict[str, Any]:
        normalized_size = max(1, min(int(page_size), 50))
        normalized_cursor = str(cursor or "").strip()
        normalized_status = str(status or "pending").strip()
        if normalized_status not in {"pending", "allocated"}:
            raise CostStatisticsManualAllocationValidationError(
                "status must be pending or allocated"
            )
        normalized_query = " ".join(str(query or "").split()).casefold()
        if len(normalized_query) > 200:
            raise CostStatisticsManualAllocationValidationError(
                "query must not exceed 200 characters"
            )
        policy = CostStatisticsPolicy(
            self._canonical_repository.load_manual_allocation_task_snapshot()
        )
        all_tasks = sorted(
            (
                {**task, "can_save": can_save}
                for task in policy.manual_allocation_tasks
                if task["in_project_cost_scope"]
            ),
            key=lambda task: str(task.get("relation_case_id") or ""),
        )
        counts = {
            "pending": sum(
                1 for task in all_tasks if task.get("status") in {"pending", "stale"}
            ),
            "allocated": sum(
                1 for task in all_tasks if task.get("status") == "allocated"
            ),
        }
        tasks = [
            task
            for task in all_tasks
            if (
                task.get("status") == "allocated"
                if normalized_status == "allocated"
                else task.get("status") in {"pending", "stale"}
            )
            and (
                not normalized_query
                or normalized_query in _task_search_text(task)
            )
        ]
        row_count = len(tasks)
        after_cursor = [
            task
            for task in tasks
            if not normalized_cursor
            or str(task.get("relation_case_id") or "") > normalized_cursor
        ]
        page = after_cursor[: normalized_size + 1]
        has_more = len(page) > normalized_size
        page = page[:normalized_size]
        return {
            "items": [_task_summary(task) for task in page],
            "row_count": row_count,
            "counts": counts,
            "next_cursor": (
                str(page[-1]["relation_case_id"])
                if has_more and page
                else None
            ),
        }

    def get_task(self, relation_case_id: str, *, can_save: bool) -> dict[str, Any]:
        snapshot = self._canonical_repository.load_relation_snapshot(relation_case_id)
        task = next((task for task in CostStatisticsPolicy(snapshot).manual_allocation_tasks
                     if task["relation_case_id"] == relation_case_id), None)
        if task is None:
            raise KeyError(relation_case_id)
        group = next(group for group in snapshot["cost_groups"]
                     if group["group_id"] == relation_case_id)
        return {**task, "can_save": can_save,
                "manual_options": AppSettingsService.cost_manual_options_from_settings(snapshot["settings"], snapshot["manual_projects"]),
                "suggested_source_allocations": suggest_source_allocations(task, group["bank_rows"], group["source_relation_groups"]),
                "relation_display_groups": _relation_display_groups(task, group)}

    def save(
        self,
        relation_case_id: str,
        payload: dict[str, Any],
        *,
        actor: dict[str, str],
        request_id: str = "",
    ) -> dict[str, Any]:
        normalized_case_id = str(relation_case_id or "").strip()
        if not normalized_case_id:
            raise CostStatisticsManualAllocationValidationError(
                "relation_case_id is required"
            )
        if self._write_connection is None:
            return self._save_in_context(
                normalized_case_id,
                payload,
                actor=actor,
                request_id=request_id,
                canonical_repository=self._canonical_repository,
                allocation_repository=self._allocation_repository,
                audit_repository=None,
                for_update=False,
            )
        from psycopg.errors import DeadlockDetected, LockNotAvailable, SerializationFailure

        try:
            with self._write_connection.transaction() as transaction:
                return self._save_in_context(
                    normalized_case_id,
                    payload,
                    actor=actor,
                    request_id=request_id,
                    canonical_repository=PostgresCostStatisticsCanonicalRepository(
                        transaction,
                        transaction_bound=True,
                    ),
                    allocation_repository=PostgresCostStatisticsManualAllocationRepository(
                        transaction
                    ),
                    audit_repository=PostgresOperationsAuditRepository(transaction),
                    for_update=True,
                )
        except (DeadlockDetected, LockNotAvailable, SerializationFailure) as exc:
            raise CostStatisticsManualAllocationConflictError(
                "关联或来源正在更新，请保留草稿并刷新后重试。"
            ) from exc

    @staticmethod
    def _save_in_context(
        relation_case_id: str,
        payload: dict[str, Any],
        *,
        actor: dict[str, str],
        request_id: str,
        canonical_repository: Any,
        allocation_repository: Any,
        audit_repository: Any | None,
        for_update: bool,
    ) -> dict[str, Any]:
        allowed_fields = {
            "relation_case_id",
            "expected_version",
            "scope_version",
            "source_fingerprint",
            "allocations",
            "manual_items",
            "source_allocations",
            "non_cost_amount",
            "non_cost_reason",
        }
        unknown_fields = set(payload) - allowed_fields
        if unknown_fields:
            raise CostStatisticsManualAllocationValidationError(
                "manual allocation payload contains unsupported fields"
            )
        body_case_id_value = payload.get("relation_case_id")
        if not isinstance(body_case_id_value, str) or not body_case_id_value.strip():
            raise CostStatisticsManualAllocationValidationError(
                "relation_case_id is required"
            )
        body_case_id = body_case_id_value.strip()
        if body_case_id != relation_case_id:
            raise CostStatisticsManualAllocationValidationError(
                "relation_case_id must match the request path"
            )
        try:
            snapshot = canonical_repository.load_relation_snapshot(
                relation_case_id,
                for_update=for_update,
            )
        except KeyError as exc:
            raise CostStatisticsManualAllocationConflictError(
                "关联关系不存在或已撤回，请刷新后重试。"
            ) from exc
        tasks = CostStatisticsPolicy(snapshot).manual_allocation_tasks
        task = next(
            (
                candidate
                for candidate in tasks
                if candidate.get("relation_case_id") == relation_case_id
            ),
            None,
        )
        if task is None:
            raise CostStatisticsManualAllocationConflictError(
                "该关联关系当前不属于人工分配范围，请刷新后重试。"
            )
        if type(payload.get("scope_version")) is not int or payload["scope_version"] < 1:
            raise CostStatisticsManualAllocationValidationError("scope_version 必须是正整数。")
        if payload["scope_version"] != task["scope_version"]:
            raise CostStatisticsManualAllocationConflictError("项目成本范围已变化，请重新加载后保存。")
        if not task["in_project_cost_scope"] or "scope_refund_required" in task["pending_reasons"]:
            raise CostStatisticsManualAllocationValidationError("当前范围没有可分配来源，或退款来源尚未确认。")
        source_fingerprint = str(payload.get("source_fingerprint") or "").strip()
        if source_fingerprint != task["source_fingerprint"]:
            raise CostStatisticsManualAllocationConflictError(
                "关联关系或金额来源已变化，请刷新后重新填写。"
            )
        expected_version = _required_version(payload.get("expected_version"))
        if expected_version != int(task.get("version") or 0):
            raise CostStatisticsManualAllocationConflictError(
                "人工分配版本已变化，请刷新后重试。"
            )
        previous = snapshot["manual_allocations"].get(relation_case_id)
        if "manual_items" not in payload and previous and previous.get("manual_items"):
            raise CostStatisticsManualAllocationConflictError("分配包含人工成本，请刷新页面后再保存。")
        options = AppSettingsService.cost_manual_options_from_settings(snapshot["settings"], snapshot["manual_projects"])
        try:
            manual_items = validate_manual_items(payload.get("manual_items", []), options, task["manual_items"])
        except ValueError as exc:
            raise CostStatisticsManualAllocationValidationError(str(exc)) from exc
        task = {**task, "manual_items": manual_items}
        allocations = _validate_allocations(
            payload.get("allocations"),
            units=allocation_targets(task),
        )
        non_cost_amount = _optional_money(payload.get("non_cost_amount"))
        non_cost_reason = _non_cost_reason(payload.get("non_cost_reason"))
        if non_cost_amount > Decimal("0.00") and not non_cost_reason:
            raise CostStatisticsManualAllocationValidationError(
                "填写不计入成本金额时必须填写原因。"
            )
        if non_cost_amount == Decimal("0.00") and non_cost_reason:
            raise CostStatisticsManualAllocationValidationError(
                "不计入成本金额为 0.00 时不得填写原因。"
            )
        allocated_total = sum(
            (Decimal(line["amount"]) for line in allocations),
            start=Decimal("0.00"),
        )
        net_outflow_total = Decimal(str(task["net_outflow_total"]))
        if allocated_total + non_cost_amount != net_outflow_total:
            raise CostStatisticsManualAllocationValidationError(
                "分配金额合计与不计入成本金额之和必须等于净支出。"
            )
        try:
            source_allocations = validate_source_allocations(
                task, allocations, non_cost_amount, payload.get("source_allocations")
            )
        except SourceAllocationError as exc:
            error = CostStatisticsManualAllocationValidationError(str(exc))
            error.field_error = {"path": exc.path, "code": exc.code, "message": str(exc)}
            raise error from exc
        actor_id = str(actor.get("id") or "").strip()
        if not actor_id:
            raise CostStatisticsManualAllocationValidationError(
                "operator identity is required"
            )
        previous = snapshot["manual_allocations"].get(relation_case_id)
        if (previous and previous["source_fingerprint"] == source_fingerprint
                and previous["source_allocations"] is None
                and Decimal(previous["gross_outflow_total"]) != Decimal(task["gross_outflow_total"])):
            raise CostStatisticsManualAllocationValidationError("历史分配缺少逐笔来源，请先在完整范围确认来源。")
        # Preserve all canonical unit identities, including units hidden by current scope.
        valid_previous = previous if previous and previous["source_fingerprint"] == source_fingerprint else None
        selected = {e["transaction_id"] for e in task["bank_events"] if e["event_kind"] == "outflow"}
        outside_ids = {line["unit_id"] for line in valid_previous["source_allocations"]["cost_lines"] if line["bank_transaction_id"] not in selected} if valid_previous and valid_previous["source_allocations"] else set()
        retained_manual = [item for item in valid_previous.get("manual_items", []) if item["unit_id"] in outside_ids] if valid_previous else []
        if {i["unit_id"] for i in retained_manual} & {i["unit_id"] for i in manual_items}:
            raise CostStatisticsManualAllocationValidationError("人工成本不能跨当前范围修改来源。")
        stored_manual = retained_manual + manual_items
        oa_ids = [line["unit_id"] for line in valid_previous["allocations"] if not line["unit_id"].startswith("manual:")] if valid_previous else [u["unit_id"] for u in task["units"]]
        all_units = [{"unit_id": id} for id in oa_ids] + stored_manual
        merged = merge_source_decision({**task, "non_cost_reason": non_cost_reason}, previous, source_allocations, all_units)
        merged["non_cost_reason"] = _non_cost_reason(merged["non_cost_reason"])
        stored_refund = sum((Decimal(line["amount"]) for line in merged["source_allocations"]["refund_links"]), Decimal("0.00"))
        stored_net = sum((Decimal(line["amount"]) for line in merged["allocations"]), Decimal(merged["non_cost_amount"]))
        saved = allocation_repository.save(
            relation_case_id=relation_case_id,
            relation_version=int(task["relation_version"]),
            source_fingerprint=source_fingerprint,
            oa_total=str(previous["oa_total"] if previous and previous["source_fingerprint"] == source_fingerprint else task["oa_total"]),
            gross_outflow_total=f"{stored_net + stored_refund:.2f}",
            wrong_payment_refund_total=f"{stored_refund:.2f}",
            net_outflow_total=f"{stored_net:.2f}",
            allocations=merged["allocations"],
            source_allocations=merged["source_allocations"],
            manual_items=stored_manual,
            non_cost_amount=merged["non_cost_amount"],
            non_cost_reason=merged["non_cost_reason"],
            expected_version=expected_version,
            actor_id=actor_id,
        )
        if saved is None:
            raise CostStatisticsManualAllocationConflictError(
                "人工分配版本已变化，请刷新后重试。"
            )
        if audit_repository is not None:
            audit_repository.append_operation_event(
                {
                    "event_type": "operation.completed",
                    "object_type": "cost_statistics_manual_allocation",
                    "object_id": relation_case_id,
                    "actor_id": actor_id,
                    "actor_name": str(actor.get("name") or ""),
                    "actor_account": str(actor.get("account") or ""),
                    "scope": "all",
                    "action": "cost_statistics.manual_allocation.save",
                    "page_key": "cost-statistics",
                    "operation_location": "成本统计/配对归集/待分配",
                    "outcome": "success",
                    "request_id": request_id or None,
                    "payload": {
                        "relation_case_id": relation_case_id,
                        "source_fingerprint": source_fingerprint,
                        "version": int(saved["version"]),
                        "net_outflow_total": str(task["net_outflow_total"]),
                        "allocations": allocations,
                        "manual_items": manual_items,
                        "source_allocations": source_allocations,
                        "non_cost_amount": f"{non_cost_amount:.2f}",
                        "non_cost_reason": non_cost_reason,
                    },
                }
            )
        group = next(g for g in snapshot["cost_groups"] if g["group_id"] == relation_case_id)
        return complete_source_task({
            **task,
            "status": "allocated",
            "manual_options": options,
            "relation_display_groups": _relation_display_groups(task, group),
            "allocations": allocations,
            "non_cost_amount": f"{non_cost_amount:.2f}",
            "non_cost_reason": non_cost_reason,
            "version": int(saved["version"]),
            "updated_by": actor_id,
            "updated_at": str(saved.get("updated_at") or ""),
            "can_save": True,
        }, source_allocations)


def _required_version(value: Any) -> int:
    if isinstance(value, bool):
        raise CostStatisticsManualAllocationValidationError(
            "expected_version must be a nonnegative integer"
        )
    try:
        version = int(value)
    except (TypeError, ValueError) as exc:
        raise CostStatisticsManualAllocationValidationError(
            "expected_version must be a nonnegative integer"
        ) from exc
    if version < 0 or str(value).strip() != str(version):
        raise CostStatisticsManualAllocationValidationError(
            "expected_version must be a nonnegative integer"
        )
    return version


def _validate_allocations(
    value: Any,
    *,
    units: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise CostStatisticsManualAllocationValidationError(
            "allocations must be an array"
        )
    expected_unit_ids = [str(unit.get("unit_id") or "") for unit in units]
    if len(value) != len(expected_unit_ids):
        raise CostStatisticsManualAllocationValidationError(
            "必须填写当前关联关系中的全部分配单元。"
        )
    amounts: dict[str, Decimal] = {}
    for line in value:
        if not isinstance(line, dict):
            raise CostStatisticsManualAllocationValidationError(
                "allocation lines must be objects"
            )
        if set(line) != {"unit_id", "amount"}:
            raise CostStatisticsManualAllocationValidationError(
                "allocation lines only accept unit_id and amount"
            )
        unit_id = str(line.get("unit_id") or "").strip()
        amount_text = str(line.get("amount") or "").strip()
        if (
            not unit_id
            or unit_id in amounts
            or not MONEY_PATTERN.fullmatch(amount_text)
        ):
            raise CostStatisticsManualAllocationValidationError(
                "每个分配单元必须且只能填写一次非负两位小数金额。"
            )
        try:
            amounts[unit_id] = Decimal(amount_text)
        except InvalidOperation as exc:
            raise CostStatisticsManualAllocationValidationError(
                "分配金额格式无效。"
            ) from exc
    if set(amounts) != set(expected_unit_ids):
        raise CostStatisticsManualAllocationValidationError(
            "提交的分配单元与当前关联关系不一致。"
        )
    return [
        {
            "unit_id": unit_id,
            "amount": f"{amounts[unit_id]:.2f}",
        }
        for unit_id in expected_unit_ids
    ]


def _optional_money(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    amount_text = str(value).strip()
    if not MONEY_PATTERN.fullmatch(amount_text):
        raise CostStatisticsManualAllocationValidationError(
            "不计入成本金额必须是非负两位小数。"
        )
    try:
        return Decimal(amount_text)
    except InvalidOperation as exc:
        raise CostStatisticsManualAllocationValidationError(
            "不计入成本金额格式无效。"
        ) from exc


def _non_cost_reason(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise CostStatisticsManualAllocationValidationError(
            "不计入成本原因必须是字符串。"
        )
    reason = " ".join(value.split())
    if len(reason) > 500:
        raise CostStatisticsManualAllocationValidationError(
            "不计入成本原因不得超过 500 个字符。"
        )
    return reason


def _task_search_text(task: dict[str, Any]) -> str:
    visible_values: list[str] = [
        str(task.get("status") or ""),
        str(task.get("oa_total") or ""),
        str(task.get("gross_outflow_total") or ""),
        str(task.get("wrong_payment_refund_total") or ""),
        str(task.get("net_outflow_total") or ""),
        str(task.get("non_cost_amount") or ""),
        str(task.get("non_cost_reason") or ""),
        str(task.get("updated_by") or ""),
        str(task.get("updated_at") or ""),
    ]
    for unit in allocation_targets(task):
        if isinstance(unit, dict):
            visible_values.extend(
                str(unit.get(key) or "")
                for key in (
                    "project_name",
                    "expense_type",
                    "expense_content",
                    "oa_applicant",
                    "oa_original_amount",
                )
            )
    for event in list(task.get("bank_events") or []):
        if isinstance(event, dict):
            visible_values.extend(
                str(event.get(key) or "")
                for key in (
                    "amount",
                    "trade_time",
                    "counterparty_name",
                    "summary",
                )
            )
            visible_values.extend(
                str(value) for value in list(event.get("tags") or [])
            )
    return " ".join(visible_values).casefold()


def _task_summary(task: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in task.items()
        if key not in {"units", "bank_events", "allocations", "source_allocations", "suggested_source_allocations", "manual_items", "manual_options"}
    } | {
        "project_names": list(dict.fromkeys(unit["project_name"] for unit in allocation_targets(task))),
        "unit_count": len(task["units"]),
        "bank_event_count": len(task["bank_events"]),
    }


def _relation_display_groups(task: dict[str, Any], group: dict[str, Any]) -> list[dict[str, Any]]:
    """Clip current relation blocks to Cost scope without regrouping their members."""
    banks = {row["transaction_id"] for row in task["bank_events"]}
    result = []
    for block in group["relation_display_groups"]:
        oa_ids = set(block["oa_row_ids"])
        units = [u["unit_id"] for u in task["units"] if u["oa_id"] in oa_ids]
        sources = [id for id in block["bank_row_ids"] if id in banks]
        if units or sources:
            result.append({"unit_ids": units, "bank_transaction_ids": sources,
                           "sources_excluded": bool(block["bank_row_ids"]) and not sources})
    return result

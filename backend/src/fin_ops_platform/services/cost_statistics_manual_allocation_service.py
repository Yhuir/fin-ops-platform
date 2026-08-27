from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.cost_statistics_canonical_repository import (
    PostgresCostStatisticsCanonicalRepository,
)
from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
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
        normalized_size = max(1, min(int(page_size), 100))
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
            "items": page,
            "row_count": row_count,
            "counts": counts,
            "next_cursor": (
                str(page[-1]["relation_case_id"])
                if has_more and page
                else None
            ),
        }

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
        allocations = _validate_allocations(
            payload.get("allocations"),
            units=list(task.get("units") or []),
            sources=list(task.get("sources") or []),
        )
        actor_id = str(actor.get("id") or "").strip()
        if not actor_id:
            raise CostStatisticsManualAllocationValidationError(
                "operator identity is required"
            )
        saved = allocation_repository.save(
            relation_case_id=relation_case_id,
            relation_version=int(task["relation_version"]),
            source_fingerprint=source_fingerprint,
            oa_allocation_total=str(task["oa_allocation_total"]),
            bank_outflow_total=str(task["bank_outflow_total"]),
            paid_wrong_refund_total=str(task["paid_wrong_refund_total"]),
            net_cash_cost=str(task["net_cash_cost"]),
            allocations=allocations,
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
                        "net_cash_cost": str(task["net_cash_cost"]),
                        "allocations": allocations,
                    },
                }
            )
        return {
            **task,
            "status": "allocated",
            "allocations": allocations,
            "version": int(saved["version"]),
            "updated_by": actor_id,
            "updated_at": str(saved.get("updated_at") or ""),
            "can_save": True,
        }


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
    sources: list[dict[str, Any]],
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise CostStatisticsManualAllocationValidationError(
            "allocations must be an array"
        )
    expected_unit_ids = [str(unit.get("unit_id") or "") for unit in units]
    expected_sources = [
        (
            str(source.get("source_kind") or ""),
            str(source.get("source_id") or ""),
            Decimal(str(source.get("amount") or "0.00")),
        )
        for source in sources
    ]
    expected_keys = {
        (unit_id, source_kind, source_id)
        for unit_id in expected_unit_ids
        for source_kind, source_id, _amount in expected_sources
    }
    if len(value) != len(expected_keys):
        raise CostStatisticsManualAllocationValidationError(
            "必须填写当前关联关系中的全部子付款项和流水来源。"
        )
    amounts: dict[tuple[str, str, str], Decimal] = {}
    for line in value:
        if not isinstance(line, dict):
            raise CostStatisticsManualAllocationValidationError(
                "allocation lines must be objects"
            )
        unit_id = str(line.get("unit_id") or "").strip()
        source_kind = str(line.get("source_kind") or "").strip()
        source_id = str(line.get("source_id") or "").strip()
        key = (unit_id, source_kind, source_id)
        amount_text = str(line.get("amount") or "").strip()
        if (
            not all(key)
            or key in amounts
            or not MONEY_PATTERN.fullmatch(amount_text)
        ):
            raise CostStatisticsManualAllocationValidationError(
                "每个子付款项和流水来源必须且只能填写一次非负两位小数金额。"
            )
        try:
            amounts[key] = Decimal(amount_text)
        except InvalidOperation as exc:
            raise CostStatisticsManualAllocationValidationError(
                "分配金额格式无效。"
            ) from exc
    if set(amounts) != expected_keys:
        raise CostStatisticsManualAllocationValidationError(
            "提交的子付款项或流水来源与当前关联关系不一致。"
        )
    for source_kind, source_id, source_amount in expected_sources:
        source_allocated = sum(
            (
                amounts[(unit_id, source_kind, source_id)]
                for unit_id in expected_unit_ids
            ),
            start=Decimal("0.00"),
        )
        if source_allocated != source_amount:
            raise CostStatisticsManualAllocationValidationError(
                "每条流水的分配合计必须等于该流水金额。"
            )
    for unit_id in expected_unit_ids:
        unit_net = sum(
            (
                -amounts[(unit_id, source_kind, source_id)]
                if source_kind == "paid_wrong_refund"
                else amounts[(unit_id, source_kind, source_id)]
                for source_kind, source_id, _amount in expected_sources
            ),
            start=Decimal("0.00"),
        )
        if unit_net < Decimal("0.00"):
            raise CostStatisticsManualAllocationValidationError(
                "单个子付款项分配后的净成本不能为负数。"
            )
    return [
        {
            "unit_id": unit_id,
            "source_kind": source_kind,
            "source_id": source_id,
            "amount": f"{amounts[(unit_id, source_kind, source_id)]:.2f}",
        }
        for unit_id in expected_unit_ids
        for source_kind, source_id, _amount in expected_sources
    ]


def _task_search_text(task: dict[str, Any]) -> str:
    visible_values: list[str] = [
        str(task.get("status") or ""),
        str(task.get("oa_allocation_total") or ""),
        str(task.get("bank_outflow_total") or ""),
        str(task.get("paid_wrong_refund_total") or ""),
        str(task.get("net_cash_cost") or ""),
        str(task.get("updated_by") or ""),
        str(task.get("updated_at") or ""),
    ]
    for unit in list(task.get("units") or []):
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
    for source in list(task.get("sources") or []):
        if isinstance(source, dict):
            visible_values.extend(
                str(source.get(key) or "")
                for key in (
                    "amount",
                    "trade_time",
                    "counterparty_name",
                    "payment_account_label",
                    "remark",
                )
            )
    return " ".join(visible_values).casefold()

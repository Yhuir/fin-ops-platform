from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
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


MONEY_PATTERN = re.compile(r"^(?:0|[1-9]\d*)\.\d{2}$")


class CostStatisticsManualAllocationValidationError(ValueError):
    error_code = "invalid_cost_statistics_manual_allocation"


class CostStatisticsManualAllocationConflictError(ValueError):
    error_code = "cost_statistics_manual_allocation_conflict"


class CostStatisticsManualAllocationService:
    """List and atomically save explicit allocations for mismatched relations."""

    def __init__(
        self,
        *,
        canonical_repository: Any,
        allocation_repository: Any,
        write_connection: Any | None = None,
    ) -> None:
        self._canonical_repository = canonical_repository
        self._allocation_repository = allocation_repository
        self._write_connection = write_connection

    def list_tasks(
        self,
        *,
        cursor: str | None,
        page_size: int,
        can_save: bool,
    ) -> dict[str, Any]:
        normalized_size = max(1, min(int(page_size), 100))
        normalized_cursor = str(cursor or "").strip()
        policy = CostStatisticsPolicy(
            self._canonical_repository.load_snapshot(
                view="project",
                include_statistics=True,
            )
        )
        tasks = [
            {**task, "can_save": can_save}
            for task in policy.manual_allocation_tasks
            if not normalized_cursor
            or str(task.get("relation_case_id") or "") > normalized_cursor
        ]
        page = tasks[: normalized_size + 1]
        has_more = len(page) > normalized_size
        page = page[:normalized_size]
        return {
            "items": page,
            "row_count": len(tasks),
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
                "该关联关系当前金额一致，不需要人工分配。"
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
            net_cash_cost=str(task["net_cash_cost"]),
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
    net_cash_cost: str,
) -> list[dict[str, str]]:
    if not isinstance(value, list):
        raise CostStatisticsManualAllocationValidationError(
            "allocations must be an array"
        )
    expected_ids = [str(unit.get("unit_id") or "") for unit in units]
    if len(value) != len(expected_ids):
        raise CostStatisticsManualAllocationValidationError(
            "必须填写当前关联关系中的全部 OA 项目。"
        )
    amounts: dict[str, Decimal] = {}
    for line in value:
        if not isinstance(line, dict):
            raise CostStatisticsManualAllocationValidationError(
                "allocation lines must be objects"
            )
        unit_id = str(line.get("unit_id") or "").strip()
        amount_text = str(line.get("amount") or "").strip()
        if not unit_id or unit_id in amounts or not MONEY_PATTERN.fullmatch(amount_text):
            raise CostStatisticsManualAllocationValidationError(
                "每个 OA 项目必须且只能填写一次非负两位小数金额。"
            )
        try:
            amounts[unit_id] = Decimal(amount_text)
        except InvalidOperation as exc:
            raise CostStatisticsManualAllocationValidationError(
                "分配金额格式无效。"
            ) from exc
    if set(amounts) != set(expected_ids):
        raise CostStatisticsManualAllocationValidationError(
            "提交的 OA 项目与当前关联关系不一致。"
        )
    if sum(amounts.values(), start=Decimal("0.00")) != Decimal(net_cash_cost):
        raise CostStatisticsManualAllocationValidationError(
            "各项目分配金额合计必须等于流水净支出。"
        )
    return [
        {"unit_id": unit_id, "amount": f"{amounts[unit_id]:.2f}"}
        for unit_id in expected_ids
    ]

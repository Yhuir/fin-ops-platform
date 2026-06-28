from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.scope_keys import normalized_scope_keys


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class TaxOffsetPlanConflictError(ValueError):
    def __init__(self, message: str, *, payload: dict[str, Any]) -> None:
        super().__init__(message)
        self.payload = payload


class InMemoryTaxOffsetPlanRepository:
    def __init__(self, snapshot: dict[str, Any] | None = None) -> None:
        plans = snapshot.get("plans") if isinstance(snapshot, dict) else {}
        self._plans: dict[str, dict[str, Any]] = {
            str(plan_id): deepcopy(plan)
            for plan_id, plan in dict(plans if isinstance(plans, dict) else {}).items()
            if isinstance(plan, dict)
        }
        self._idempotency_index: dict[str, str] = {}
        for plan_id, plan in self._plans.items():
            key = str(plan.get("idempotency_key") or "").strip()
            if key:
                self._idempotency_index[key] = plan_id

    def save_tax_offset_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        idempotency_key = str(plan.get("idempotency_key") or "").strip()
        if idempotency_key and idempotency_key in self._idempotency_index:
            return deepcopy(self._plans[self._idempotency_index[idempotency_key]])
        plan_id = str(plan.get("id") or "").strip()
        if not plan_id:
            raise ValueError("plan id is required.")
        stored = deepcopy(plan)
        self._plans[plan_id] = stored
        if idempotency_key:
            self._idempotency_index[idempotency_key] = plan_id
        return deepcopy(stored)

    def snapshot(self) -> dict[str, Any]:
        return {"plans": deepcopy(self._plans)}


class TaxOffsetPlanService:
    def __init__(
        self,
        *,
        query_service: Any,
        plan_repository: Any,
        id_provider: Callable[[], str] | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._query_service = query_service
        self._plan_repository = plan_repository
        self._id_provider = id_provider or (lambda: f"tax-offset-plan-{uuid4().hex}")
        self._clock = clock or (lambda: datetime.now(UTC))

    def save_plan(self, *, actor_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        month = self._normalize_month(payload.get("month"))
        selected_output_ids = self._string_list(payload.get("selected_output_ids"), "selected_output_ids")
        selected_input_ids = self._string_list(payload.get("selected_input_ids"), "selected_input_ids")
        expected_source_versions = payload.get("expected_source_versions")
        if expected_source_versions is not None and not isinstance(expected_source_versions, dict):
            raise ValueError("expected_source_versions must be an object.")

        month_payload, _cache_hit = self._query_service.get_month_payload(month)
        source_versions = dict(month_payload.get("source_versions") if isinstance(month_payload.get("source_versions"), dict) else {})
        if source_versions and isinstance(expected_source_versions, dict) and expected_source_versions != source_versions:
            raise TaxOffsetPlanConflictError(
                "Tax offset source versions changed.",
                payload={
                    "error": "tax_offset_source_version_conflict",
                    "message": "税金抵扣数据来源版本已变化，请刷新页面后重新保存。",
                    "source_versions": source_versions,
                    "expected_source_versions": expected_source_versions,
                },
            )

        calculation, status_code = self._query_service.calculate(
            {
                "month": month,
                "selected_output_ids": selected_output_ids,
                "selected_input_ids": selected_input_ids,
            }
        )
        if status_code != 200:
            raise TaxOffsetPlanConflictError(
                "Tax offset calculation did not finish on a fresh read model.",
                payload={
                    "error": "tax_offset_calculation_not_ready",
                    "message": "税金抵扣试算尚未完成，请稍后重试。",
                    **dict(calculation),
                },
            )

        now = self._clock().isoformat()
        plan = {
            "id": self._id_provider(),
            "month": month,
            "selected_output_ids": selected_output_ids,
            "selected_input_ids": selected_input_ids,
            "summary": deepcopy(calculation.get("summary") if isinstance(calculation.get("summary"), dict) else {}),
            "source_versions": source_versions,
            "idempotency_key": str(payload.get("idempotency_key") or "").strip(),
            "actor_id": str(actor_id or "").strip() or "system",
            "created_at": now,
            "updated_at": now,
            "audit": {
                "operation": "tax_offset_plan_save",
                "expected_source_versions": deepcopy(expected_source_versions if isinstance(expected_source_versions, dict) else {}),
            },
        }
        saved_plan = self._plan_repository.save_tax_offset_plan(plan)
        return {
            "status": "saved",
            "plan": saved_plan,
            "affected_scope_keys": normalized_scope_keys([month], fallback=month),
        }

    @staticmethod
    def _normalize_month(value: Any) -> str:
        month = str(value or "").strip()
        if not month:
            raise ValueError("month is required.")
        if not MONTH_RE.match(month):
            raise ValueError("month must be YYYY-MM.")
        return month

    @staticmethod
    def _string_list(value: Any, field_name: str) -> list[str]:
        if not isinstance(value, list):
            raise ValueError(f"{field_name} must be an array.")
        result: list[str] = []
        for item in value:
            text = str(item or "").strip()
            if text and text not in result:
                result.append(text)
        return result

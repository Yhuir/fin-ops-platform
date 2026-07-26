from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from typing import Any, Callable
from uuid import uuid4

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
        expected_snapshot_version = str(payload.get("expected_canonical_snapshot_version") or "").strip()

        month_payload = self._query_service.get_month_payload(month)
        canonical_snapshot_version = str(month_payload.get("canonical_snapshot_version") or "").strip()
        if not expected_snapshot_version or expected_snapshot_version != canonical_snapshot_version:
            raise TaxOffsetPlanConflictError(
                "Tax offset canonical facts changed.",
                payload={
                    "error": "tax_offset_canonical_version_conflict",
                    "message": "税金抵扣数据已变化，请刷新页面后重新保存。",
                    "month": month,
                    "canonical_snapshot_version": canonical_snapshot_version,
                    "expected_canonical_snapshot_version": expected_snapshot_version or None,
                },
            )

        calculation = self._query_service.calculate_from_month_payload(
            {
                "month": month,
                "selected_output_ids": selected_output_ids,
                "selected_input_ids": selected_input_ids,
            },
            month_payload=month_payload,
        )

        now = self._clock().isoformat()
        plan = {
            "id": self._id_provider(),
            "month": month,
            "selected_output_ids": selected_output_ids,
            "selected_input_ids": selected_input_ids,
            "summary": deepcopy(calculation.get("summary") if isinstance(calculation.get("summary"), dict) else {}),
            "canonical_snapshot_version": canonical_snapshot_version,
            "idempotency_key": str(payload.get("idempotency_key") or "").strip(),
            "actor_id": str(actor_id or "").strip() or "system",
            "created_at": now,
            "updated_at": now,
            "audit": {
                "operation": "tax_offset_plan_save",
                "expected_canonical_snapshot_version": expected_snapshot_version,
            },
        }
        saved_plan = self._plan_repository.save_tax_offset_plan(plan)
        return {
            "status": "saved",
            "plan": saved_plan,
            "affected_scope_keys": [month],
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

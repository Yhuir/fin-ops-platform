from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from typing import Any, Callable
from uuid import uuid4

from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.read_model_write_targets import write_target_envelope


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
        expected_scope_key = str(payload.get("expected_read_model_scope_key") or "").strip()
        expected_source_versions = payload.get("expected_source_versions")
        if expected_source_versions is not None and not isinstance(expected_source_versions, dict):
            raise ValueError("expected_source_versions must be an object.")

        month_payload, _cache_hit = self._query_service.get_month_payload(month)
        read_model_status = str(month_payload.get("read_model_status") or "fresh")
        read_model_scope_key = str(month_payload.get("read_model_scope_key") or month).strip() or month
        source_versions = dict(month_payload.get("source_versions") if isinstance(month_payload.get("source_versions"), dict) else {})
        if read_model_status != "fresh":
            raise TaxOffsetPlanConflictError(
                "Tax offset read model is not fresh.",
                payload={
                    "error": "tax_offset_read_model_not_fresh",
                    "message": "税金抵扣读模型尚未刷新完成，请刷新后再保存计划。",
                    "read_model_status": read_model_status,
                    "read_model_scope_key": read_model_scope_key,
                    "read_model_stale_reasons": list(month_payload.get("read_model_stale_reasons") or []),
                },
            )
        if expected_scope_key and expected_scope_key != read_model_scope_key:
            raise TaxOffsetPlanConflictError(
                "Tax offset read model scope changed.",
                payload={
                    "error": "tax_offset_read_model_version_conflict",
                    "message": "税金抵扣读模型范围已变化，请刷新页面后重新保存。",
                    "read_model_scope_key": read_model_scope_key,
                    "expected_read_model_scope_key": expected_scope_key,
                },
            )
        try:
            expected_versions = require_expected_source_versions(
                expected_source_versions if isinstance(expected_source_versions, dict) else {},
                context="tax_offset_plan_expected_read_model",
            )
        except ValueError as exc:
            raise TaxOffsetPlanConflictError(
                "Tax offset read model source versions are missing.",
                payload={
                    "error": "tax_offset_read_model_version_conflict",
                    "message": "税金抵扣数据来源版本缺失，请刷新页面后重新保存。",
                    "read_model_scope_key": read_model_scope_key,
                    "source_versions": source_versions,
                    "expected_source_versions": expected_source_versions,
                },
            ) from exc
        mismatch_reasons = source_version_mismatch_reasons(
            expected=expected_versions,
            actual=source_versions,
        )
        if mismatch_reasons:
            raise TaxOffsetPlanConflictError(
                "Tax offset read model source versions changed.",
                payload={
                    "error": "tax_offset_read_model_version_conflict",
                    "message": "税金抵扣数据来源版本已变化，请刷新页面后重新保存。",
                    "read_model_scope_key": read_model_scope_key,
                    "read_model_stale_reasons": mismatch_reasons,
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
            "read_model_scope_key": read_model_scope_key,
            "source_versions": source_versions,
            "idempotency_key": str(payload.get("idempotency_key") or "").strip(),
            "actor_id": str(actor_id or "").strip() or "system",
            "created_at": now,
            "updated_at": now,
            "audit": {
                "operation": "tax_offset_plan_save",
                "expected_read_model_scope_key": expected_scope_key,
                "expected_source_versions": deepcopy(expected_source_versions if isinstance(expected_source_versions, dict) else {}),
            },
        }
        saved_plan = self._plan_repository.save_tax_offset_plan(plan)
        return {
            "status": "saved",
            "plan": saved_plan,
            **write_target_envelope(
                scope_keys=[read_model_scope_key],
                targets=[],
                fallback_scope_key=month,
            ),
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

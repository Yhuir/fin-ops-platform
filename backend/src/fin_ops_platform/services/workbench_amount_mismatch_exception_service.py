from __future__ import annotations

from typing import Any

from fin_ops_platform.services.workbench_read_model_version import (
    WorkbenchReadModelVersionConflictError,
)


class WorkbenchAmountMismatchConflict(ValueError):
    pass


class WorkbenchAmountMismatchExceptionService:
    def __init__(self, *, group_repository: Any, decision_repository: Any) -> None:
        self._group_repository = group_repository
        self._decision_repository = decision_repository

    def set_ignored(
        self,
        payload: dict[str, object],
        *,
        actor_id: str,
        ignored: bool,
    ) -> dict[str, object]:
        scope_key = str(payload.get("month") or "").strip()
        zone = str(payload.get("zone") or "").strip()
        group_id = str(payload.get("group_id") or "").strip()
        fingerprint = str(payload.get("fingerprint") or "").strip().lower()
        expected_version = str(payload.get("expected_read_model_version") or "").strip()
        if zone not in {"paired", "unpaired"}:
            raise ValueError("zone must be paired or unpaired.")
        if not scope_key or not group_id or not fingerprint or not expected_version:
            raise ValueError("month, group_id, fingerprint and expected_read_model_version are required.")
        group = self._group_repository.get_workbench_group_detail(
            scope_key=scope_key,
            zone=zone,
            group_id=group_id,
            expected_read_model_version=expected_version,
        )
        if not isinstance(group, dict):
            raise WorkbenchAmountMismatchConflict("金额异常关系组已变化，请刷新后重试。")
        anomaly = group.get("oa_invoice_anomaly")
        if not isinstance(anomaly, dict) or str(anomaly.get("fingerprint") or "") != fingerprint:
            raise WorkbenchAmountMismatchConflict("金额异常已变化或已消失，请刷新后重试。")
        group_scope = str(
            group.get("source_scope_key")
            or group.get("scope_month")
            or group.get("month")
            or group.get("scope_key")
            or scope_key
        ).strip()
        decision_scope_key = group_scope[:7] if len(group_scope) >= 7 else scope_key
        if decision_scope_key == "all":
            raise WorkbenchAmountMismatchConflict("金额异常缺少所属月份，请刷新后重试。")
        result = self._decision_repository.set_workbench_amount_mismatch_decision(
            fingerprint=fingerprint,
            group_id=group_id,
            scope_key=decision_scope_key,
            actor_id=actor_id,
            ignored=ignored,
        )
        return {
            **result,
            "affected_scope_keys": [decision_scope_key],
            "read_model_version": expected_version,
        }


__all__ = [
    "WorkbenchAmountMismatchConflict",
    "WorkbenchAmountMismatchExceptionService",
]

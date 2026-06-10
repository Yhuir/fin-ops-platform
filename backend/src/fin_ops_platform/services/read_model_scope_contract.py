from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.read_model_scope_policy import (
    DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ReadModelScopeError,
    ReadModelScopePolicyRegistry,
)


class ReadModelScopeContractRepository(Protocol):
    def list_cost_statistics_dirty_scopes(self) -> list[dict[str, Any]]: ...
    def list_cost_statistics_outbox_events(self) -> list[dict[str, Any]]: ...
    def list_cost_statistics_readiness(self) -> list[dict[str, Any]]: ...
    def delete_dirty_scope(self, row_id: str) -> int: ...
    def delete_outbox_event(self, row_id: str) -> int: ...
    def delete_readiness(self, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> int: ...


@dataclass(frozen=True)
class ReadModelScopeContractViolation:
    location: str
    kind: str
    scope_key: str
    normalized_scope_keys: list[str]
    row: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "kind": self.kind,
            "scope_key": self.scope_key,
            "normalized_scope_keys": list(self.normalized_scope_keys),
            "row": dict(self.row),
        }


class ReadModelScopeContractService:
    def __init__(
        self,
        repository: ReadModelScopeContractRepository,
        *,
        scope_policy_registry: ReadModelScopePolicyRegistry = DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY,
    ) -> None:
        self._repository = repository
        self._scope_policy_registry = scope_policy_registry

    def check_cost_statistics_contract(self) -> dict[str, Any]:
        violations = self._cost_statistics_violations()
        return self._report(violations, cleanup=None, replacement_enqueue=None)

    def repair_cost_statistics_contract(
        self,
        *,
        apply: bool,
        refresh_gateway: ReadModelRefreshGateway | None = None,
        enqueue_replacements: bool = True,
        reason: str = "read_model_scope_contract_repair",
    ) -> dict[str, Any]:
        violations = self._cost_statistics_violations()
        cleanup = {"applied": apply, "deleted": _empty_location_counts()}
        replacement_enqueue = {"enabled": bool(apply and enqueue_replacements), "enqueued_scope_keys": [], "enqueued_count": 0}
        if apply:
            cleanup["deleted"] = self._delete_violations(violations)
            replacement_scope_keys = _replacement_scope_keys(violations)
            if enqueue_replacements and replacement_scope_keys:
                if refresh_gateway is None or not refresh_gateway.can_enqueue():
                    raise RuntimeError("refresh_gateway is required when enqueue_replacements is enabled.")
                enqueued_scope_keys = refresh_gateway.enqueue_many(
                    "cost_statistics",
                    replacement_scope_keys,
                    reason=reason,
                )
                replacement_enqueue = {
                    "enabled": True,
                    "enqueued_scope_keys": enqueued_scope_keys,
                    "enqueued_count": len(enqueued_scope_keys),
                }
        return self._report(violations, cleanup=cleanup, replacement_enqueue=replacement_enqueue)

    def _cost_statistics_violations(self) -> list[ReadModelScopeContractViolation]:
        violations: list[ReadModelScopeContractViolation] = []
        for location, rows in (
            ("job.read_model_dirty_scopes", self._repository.list_cost_statistics_dirty_scopes()),
            ("job.outbox_events", self._repository.list_cost_statistics_outbox_events()),
            ("read_model.app_status_readiness", self._repository.list_cost_statistics_readiness()),
        ):
            for row in rows:
                violation = self._violation_for_row(location, row)
                if violation is not None:
                    violations.append(violation)
        return violations

    def _violation_for_row(self, location: str, row: dict[str, Any]) -> ReadModelScopeContractViolation | None:
        raw_scope_key = str(row.get("scope_key") or "")
        scope_key = raw_scope_key.strip()
        try:
            normalized_scope_keys = self._scope_policy_registry.normalize_and_validate("cost_statistics", [scope_key])
        except ReadModelScopeError:
            return ReadModelScopeContractViolation(
                location=location,
                kind="invalid",
                scope_key=scope_key,
                normalized_scope_keys=[],
                row=dict(row),
            )
        if raw_scope_key == scope_key and normalized_scope_keys == [scope_key]:
            return None
        return ReadModelScopeContractViolation(
            location=location,
            kind="legacy",
            scope_key=scope_key,
            normalized_scope_keys=normalized_scope_keys,
            row=dict(row),
        )

    def _delete_violations(self, violations: list[ReadModelScopeContractViolation]) -> dict[str, int]:
        deleted = _empty_location_counts()
        for violation in violations:
            row = violation.row
            if violation.location == "job.read_model_dirty_scopes":
                deleted[violation.location] += self._repository.delete_dirty_scope(str(row.get("id") or ""))
            elif violation.location == "job.outbox_events":
                deleted[violation.location] += self._repository.delete_outbox_event(str(row.get("id") or ""))
            elif violation.location == "read_model.app_status_readiness":
                deleted[violation.location] += self._repository.delete_readiness(
                    tenant_id=str(row.get("tenant_id") or "default"),
                    read_model_key=str(row.get("read_model_key") or "cost_statistics"),
                    scope_type=str(row.get("scope_type") or "cost_statistics"),
                    scope_key=str(row.get("scope_key") or ""),
                )
        return deleted

    @staticmethod
    def _report(
        violations: list[ReadModelScopeContractViolation],
        *,
        cleanup: dict[str, Any] | None,
        replacement_enqueue: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary: dict[str, dict[str, int]] = {}
        for violation in violations:
            location_summary = summary.setdefault(violation.location, {"legacy": 0, "invalid": 0, "total": 0})
            location_summary[violation.kind] += 1
            location_summary["total"] += 1
        report = {
            "action": "read_model_scope_contract_check",
            "ok": not violations,
            "violation_count": len(violations),
            "summary": summary,
            "replacement_scope_keys": _replacement_scope_keys(violations),
            "violations": [violation.to_dict() for violation in violations],
        }
        if cleanup is not None:
            report["cleanup"] = cleanup
        if replacement_enqueue is not None:
            report["replacement_enqueue"] = replacement_enqueue
        return report


def _replacement_scope_keys(violations: list[ReadModelScopeContractViolation]) -> list[str]:
    scope_keys: list[str] = []
    for violation in violations:
        for scope_key in violation.normalized_scope_keys:
            if scope_key not in scope_keys:
                scope_keys.append(scope_key)
    return scope_keys


def _empty_location_counts() -> dict[str, int]:
    return {
        "job.read_model_dirty_scopes": 0,
        "job.outbox_events": 0,
        "read_model.app_status_readiness": 0,
    }

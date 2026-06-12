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
    def list_read_model_outbox_failures(self) -> list[dict[str, Any]]: ...
    def delete_dirty_scope(self, row_id: str) -> int: ...
    def delete_outbox_event(self, row_id: str) -> int: ...
    def delete_readiness(self, *, tenant_id: str, read_model_key: str, scope_type: str, scope_key: str) -> int: ...
    def record_repair_audit(self, event: dict[str, Any]) -> str: ...


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
        outbox_failures = self._read_model_outbox_failures(violations)
        return self._report(violations, outbox_failures=outbox_failures, cleanup=None, replacement_enqueue=None)

    def repair_cost_statistics_contract(
        self,
        *,
        apply: bool,
        refresh_gateway: ReadModelRefreshGateway | None = None,
        enqueue_replacements: bool = True,
        reason: str = "read_model_scope_contract_repair",
    ) -> dict[str, Any]:
        violations = self._cost_statistics_violations()
        outbox_failures = self._read_model_outbox_failures(violations)
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
        report = self._report(violations, outbox_failures=outbox_failures, cleanup=cleanup, replacement_enqueue=replacement_enqueue)
        if apply and violations:
            report["repair_audit"] = self._record_repair_audit(report=report, reason=reason)
        return report

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

    def _read_model_outbox_failures(
        self,
        violations: list[ReadModelScopeContractViolation],
    ) -> list[dict[str, Any]]:
        list_failures = getattr(self._repository, "list_read_model_outbox_failures", None)
        if not callable(list_failures):
            return []
        legacy_outbox_ids = {
            str(violation.row.get("id") or "")
            for violation in violations
            if violation.location == "job.outbox_events"
        }
        failures: list[dict[str, Any]] = []
        for row in list_failures():
            row_id = str(row.get("id") or "")
            if row_id and row_id in legacy_outbox_ids:
                continue
            if str(row.get("event_type") or "") == "cost_statistics.read_model.refresh":
                if self._violation_for_row("job.outbox_events", row) is not None:
                    continue
            failures.append(dict(row))
        return failures

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
        outbox_failures: list[dict[str, Any]],
        cleanup: dict[str, Any] | None,
        replacement_enqueue: dict[str, Any] | None,
    ) -> dict[str, Any]:
        summary: dict[str, dict[str, int]] = {}
        for violation in violations:
            location_summary = summary.setdefault(violation.location, {"legacy": 0, "invalid": 0, "total": 0})
            location_summary[violation.kind] += 1
            location_summary["total"] += 1
        repair_manifest = _repair_manifest(violations, outbox_failures)
        current_uncovered_count = repair_manifest["summary"]["current_uncovered_outbox_failures"]
        covered_historical_count = repair_manifest["summary"]["covered_historical_outbox_failures"]
        report = {
            "action": "read_model_scope_contract_check",
            "ok": not violations and current_uncovered_count == 0 and covered_historical_count == 0,
            "violation_count": len(violations),
            "covered_historical_outbox_failure_count": covered_historical_count,
            "current_uncovered_outbox_failure_count": current_uncovered_count,
            "summary": summary,
            "replacement_scope_keys": _replacement_scope_keys(violations),
            "repair_manifest": repair_manifest,
            "rollback": {
                "strategy": "restore deleted rows from repair_manifest.items[].row and inspect replacement enqueue events before replay.",
                "manifest_item_count": len(repair_manifest["items"]),
            },
            "violations": [violation.to_dict() for violation in violations],
        }
        if cleanup is not None:
            report["cleanup"] = cleanup
        if replacement_enqueue is not None:
            report["replacement_enqueue"] = replacement_enqueue
        if cleanup is not None:
            report["repair_audit"] = {"enabled": bool(cleanup.get("applied")), "recorded": False, "event_id": ""}
        return report

    def _record_repair_audit(self, *, report: dict[str, Any], reason: str) -> dict[str, Any]:
        record_audit = getattr(self._repository, "record_repair_audit", None)
        if not callable(record_audit):
            return {"enabled": True, "recorded": False, "event_id": "", "reason": "repository_does_not_support_audit"}
        event = {
            "event_type": "read_model_scope_contract_repair",
            "object_type": "read_model_runtime_repair",
            "object_id": "cost_statistics",
            "reason": reason,
            "payload": {
                "reason": reason,
                "repair_manifest": report.get("repair_manifest") or {},
                "cleanup": report.get("cleanup") or {},
                "replacement_enqueue": report.get("replacement_enqueue") or {},
                "rollback": report.get("rollback") or {},
            },
        }
        event_id = record_audit(event)
        return {"enabled": True, "recorded": True, "event_id": event_id}


def _replacement_scope_keys(violations: list[ReadModelScopeContractViolation]) -> list[str]:
    scope_keys: list[str] = []
    for violation in violations:
        for scope_key in violation.normalized_scope_keys:
            if scope_key not in scope_keys:
                scope_keys.append(scope_key)
    return scope_keys


def _repair_manifest(
    violations: list[ReadModelScopeContractViolation],
    outbox_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    summary = _empty_manifest_summary()
    for violation in violations:
        item = _manifest_item_from_violation(violation)
        summary[item["category"]] += 1
        items.append(item)
    for row in outbox_failures:
        item = _manifest_item_from_outbox_failure(row)
        summary[item["category"]] += 1
        items.append(item)
    return {
        "summary": summary,
        "items": items,
    }


def _manifest_item_from_violation(violation: ReadModelScopeContractViolation) -> dict[str, Any]:
    row = dict(violation.row)
    category = _cost_statistics_violation_category(violation)
    return {
        "category": category,
        "location": violation.location,
        "row_id": str(row.get("id") or ""),
        "tenant_id": str(row.get("tenant_id") or "default"),
        "scope_type": str(row.get("scope_type") or "cost_statistics"),
        "scope_key": violation.scope_key,
        "event_type": str(row.get("event_type") or ("cost_statistics.read_model.refresh" if violation.location == "job.outbox_events" else "")),
        "status": str(row.get("status") or ""),
        "last_error": str(row.get("last_error") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "covered_by": [f"scope_policy:{scope_key}" for scope_key in violation.normalized_scope_keys],
        "normalized_scope_keys": list(violation.normalized_scope_keys),
        "proposed_action": _proposed_action_for_violation(violation),
        "rollback_hint": f"restore {violation.location} row from repair_manifest item row before rerun",
        "row": row,
    }


def _manifest_item_from_outbox_failure(row: dict[str, Any]) -> dict[str, Any]:
    covered_by = _outbox_failure_covered_by(row)
    covered = bool(covered_by)
    return {
        "category": "covered_historical_outbox_failures" if covered else "current_uncovered_outbox_failures",
        "location": "job.outbox_events",
        "row_id": str(row.get("id") or ""),
        "tenant_id": str(row.get("tenant_id") or "default"),
        "scope_type": str(row.get("scope_type") or ""),
        "scope_key": str(row.get("scope_key") or ""),
        "event_type": str(row.get("event_type") or ""),
        "status": str(row.get("status") or ""),
        "last_error": str(row.get("last_error") or ""),
        "updated_at": str(row.get("updated_at") or ""),
        "covered_by": covered_by,
        "normalized_scope_keys": [],
        "proposed_action": (
            "operator_resolve_historical_outbox_failure"
            if covered
            else "retain_current_blocker_investigate_or_requeue"
        ),
        "rollback_hint": (
            "restore outbox row from repair manifest if operator resolution is reverted"
            if covered
            else "no repair applied; investigate worker/readiness before requeue"
        ),
        "row": dict(row),
    }


def _cost_statistics_violation_category(violation: ReadModelScopeContractViolation) -> str:
    kind = "legacy" if violation.kind == "legacy" else "invalid"
    if violation.location == "job.read_model_dirty_scopes":
        suffix = "dirty_scopes"
    elif violation.location == "job.outbox_events":
        suffix = "outbox_events"
    else:
        suffix = "readiness_rows"
    return f"cost_statistics_{kind}_{suffix}"


def _proposed_action_for_violation(violation: ReadModelScopeContractViolation) -> str:
    if violation.normalized_scope_keys:
        if violation.location == "read_model.app_status_readiness":
            return "delete_readiness_and_enqueue_replacement"
        return "delete_runtime_row_and_enqueue_replacement"
    if violation.location == "read_model.app_status_readiness":
        return "delete_invalid_readiness_no_replacement"
    return "delete_invalid_runtime_row_no_replacement"


def _outbox_failure_covered_by(row: dict[str, Any]) -> list[str]:
    covered_by: list[str] = []
    if _truthy(row.get("covered_by_later_done")):
        covered_by.append("later_done")
    if _truthy(row.get("covered_by_later_readiness")):
        covered_by.append("fresh_readiness")
    return covered_by


def _truthy(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"1", "t", "true", "yes", "y"}


def _empty_manifest_summary() -> dict[str, int]:
    return {
        "cost_statistics_legacy_dirty_scopes": 0,
        "cost_statistics_legacy_outbox_events": 0,
        "cost_statistics_legacy_readiness_rows": 0,
        "cost_statistics_invalid_dirty_scopes": 0,
        "cost_statistics_invalid_outbox_events": 0,
        "cost_statistics_invalid_readiness_rows": 0,
        "covered_historical_outbox_failures": 0,
        "current_uncovered_outbox_failures": 0,
    }


def _empty_location_counts() -> dict[str, int]:
    return {
        "job.read_model_dirty_scopes": 0,
        "job.outbox_events": 0,
        "read_model.app_status_readiness": 0,
    }

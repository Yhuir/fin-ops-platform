"""Explicit retirement of redundant cost decisions; caller owns the transaction."""
from __future__ import annotations

from typing import Any

from fin_ops_platform.services.cost_statistics_decision_equivalence import automatic_equivalence_reason, automatic_task


class CostStatisticsAutomaticMigrationService:
    def __init__(self, *, canonical_repository: Any, allocation_repository: Any, audit_repository: Any) -> None:
        self._canonical = canonical_repository
        self._allocations = allocation_repository
        self._audit = audit_repository

    def restore(self, *, case_id: str, expected_version: int, actor_id: str) -> dict[str, Any]:
        """Restore a retained equivalent decision only at its exact current revision."""
        if not actor_id.strip() or expected_version < 1:
            raise ValueError("operator and positive expected version are required")
        snapshot = self._canonical.load_relation_snapshot(case_id, for_update=True)
        record = snapshot["manual_allocations"].get(case_id)
        if record is None or record["decision_mode"] != "automatic" or record["version"] != expected_version:
            raise ValueError(f"decision changed: {case_id}")
        reason = automatic_equivalence_reason(record, automatic_task(snapshot, case_id))
        if reason:
            raise ValueError(f"cannot restore changed facts: {reason}")
        fields = {key: record[key] for key in (
            "relation_case_id", "relation_version", "source_fingerprint", "oa_total", "gross_outflow_total",
            "wrong_payment_refund_total", "net_outflow_total", "allocations", "source_allocations",
            "manual_items", "oa_amount_locks", "oa_cost_tag_overrides", "non_cost_amount", "non_cost_reason")}
        saved = self._allocations.save(**fields, decision_mode="manual", expected_version=expected_version, actor_id=actor_id)
        if saved is None:
            raise ValueError(f"decision changed: {case_id}")
        self._audit.append_operation_event({
            "event_type": "operation.completed", "object_type": "cost_statistics_manual_allocation",
            "object_id": case_id, "actor_id": actor_id, "scope": "all", "outcome": "success",
            "action": "cost_statistics.manual_allocation.restore_automatic_retirement",
            "page_key": "cost-statistics", "operation_location": "成本统计/自动分配迁移恢复",
            "payload": {"before": record, "after": saved},
        })
        return {"relation_case_id": case_id, "decision_mode": saved["decision_mode"], "version": saved["version"]}

    def run(self, *, apply: bool = False, actor_id: str = "") -> dict[str, Any]:
        if apply and not actor_id.strip():
            raise ValueError("operator is required")
        results = []
        for candidate in self._allocations.list_decision_candidates():
            case_id = candidate["relation_case_id"]
            reason = ""
            if candidate["relation_status"] != "active":
                reason = "inactive_relation"
            else:
                try:
                    snapshot = self._canonical.load_relation_snapshot(case_id, for_update=apply)
                except KeyError:
                    reason = "missing_relation_facts"
                else:
                    record = snapshot["manual_allocations"].get(case_id)
                    if record is None or record["decision_mode"] != "manual" or record["version"] != candidate["version"]:
                        raise ValueError(f"decision changed: {case_id}")
                    reason = automatic_equivalence_reason(record, automatic_task(snapshot, case_id))
                    if not reason and apply:
                        saved = self._allocations.retire_to_automatic(
                            relation_case_id=case_id, expected_version=record["version"], actor_id=actor_id)
                        if saved is None:
                            raise ValueError(f"decision changed: {case_id}")
                        self._audit.append_operation_event({
                            "event_type": "operation.completed", "object_type": "cost_statistics_manual_allocation",
                            "object_id": case_id, "actor_id": actor_id, "scope": "all",
                            "action": "cost_statistics.manual_allocation.retire_automatic",
                            "page_key": "cost-statistics", "operation_location": "成本统计/自动分配迁移",
                            "outcome": "success", "payload": {"before": record, "after": saved},
                        })
            results.append({"relation_case_id": case_id, "version": candidate["version"],
                            "eligible": not reason, "reason": reason, "changed": apply and not reason})
        return {"applied": apply, "scanned": len(results),
                "eligible_count": sum(row["eligible"] for row in results),
                "changed_count": sum(row["changed"] for row in results), "items": results}

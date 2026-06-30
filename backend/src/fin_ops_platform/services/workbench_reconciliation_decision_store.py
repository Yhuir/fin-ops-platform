from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_EXPIRED,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PROPOSED,
    DECISION_STATUS_SUPPRESSED,
    WorkbenchDecision,
)


ACTIVE_DECISION_STATUSES = {
    DECISION_STATUS_PROPOSED,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_OPEN,
}


class WorkbenchReconciliationDecisionStore:
    def __init__(self, repository: Any | None = None, *, tenant_id: str = "default") -> None:
        self._repository = repository
        self._tenant_id = str(tenant_id or "default")
        self._decisions_by_key: dict[str, dict[str, Any]] = {}

    def upsert_decisions(self, decisions: list[WorkbenchDecision]) -> None:
        if self._repository is not None:
            self._repository.upsert_workbench_reconciliation_decisions(
                tenant_id=self._tenant_id,
                decisions=[decision.to_dict() for decision in decisions],
            )
            return
        for decision in decisions:
            payload = decision.to_dict()
            payload["tenant_id"] = self._tenant_id
            payload.setdefault("consumed_by_relation_id", None)
            payload.setdefault("suppressed_by_exception_case_id", None)
            decision_key = str(payload["decision_key"])
            existing = self._decisions_by_key.get(decision_key)
            if isinstance(existing, dict) and existing.get("decision_status") == DECISION_STATUS_SUPPRESSED:
                payload["decision_status"] = DECISION_STATUS_SUPPRESSED
                payload["suppressed_by_exception_case_id"] = existing.get("suppressed_by_exception_case_id")
            self._decisions_by_key[decision_key] = payload

    def list_decisions(self, scope_month: str, *, statuses: set[str] | None = None) -> list[dict[str, object]]:
        if self._repository is not None:
            return self._repository.list_workbench_reconciliation_decisions(
                tenant_id=self._tenant_id,
                scope_month=scope_month,
                statuses=statuses,
            )
        status_filter = set(statuses or [])
        rows = [
            deepcopy(decision)
            for decision in self._decisions_by_key.values()
            if decision.get("scope_month") == scope_month
            and (not status_filter or decision.get("decision_status") in status_filter)
        ]
        return sorted(rows, key=lambda item: str(item.get("decision_key") or ""))

    def consume_by_row_ids(self, row_ids: list[str], *, relation_id: str) -> int:
        if self._repository is not None:
            return int(
                self._repository.consume_workbench_reconciliation_decisions_by_row_ids(
                    tenant_id=self._tenant_id,
                    row_ids=row_ids,
                    relation_id=relation_id,
                )
                or 0
            )
        return self._mark_by_row_ids(
            row_ids,
            status=DECISION_STATUS_CONSUMED,
            metadata_key="consumed_by_relation_id",
            metadata_value=relation_id,
        )

    def suppress_by_row_ids(self, row_ids: list[str], *, exception_case_id: str) -> int:
        if self._repository is not None:
            return int(
                self._repository.suppress_workbench_reconciliation_decisions_by_row_ids(
                    tenant_id=self._tenant_id,
                    row_ids=row_ids,
                    exception_case_id=exception_case_id,
                )
                or 0
            )
        return self._mark_by_row_ids(
            row_ids,
            status=DECISION_STATUS_SUPPRESSED,
            metadata_key="suppressed_by_exception_case_id",
            metadata_value=exception_case_id,
        )

    def expire_stale(self, scope_months: list[str], *, source_versions: dict[str, object]) -> int:
        if self._repository is not None:
            return int(
                self._repository.expire_stale_workbench_reconciliation_decisions(
                    tenant_id=self._tenant_id,
                    scope_months=scope_months,
                    source_versions=source_versions,
                )
                or 0
            )
        scope_filter = {str(month) for month in scope_months}
        expired = 0
        for decision in self._decisions_by_key.values():
            if decision.get("scope_month") not in scope_filter:
                continue
            if decision.get("decision_status") not in ACTIVE_DECISION_STATUSES:
                continue
            if _source_versions_match(decision.get("source_versions"), source_versions):
                continue
            decision["decision_status"] = DECISION_STATUS_EXPIRED
            expired += 1
        return expired

    def expire_missing_for_scope(self, scope_month: str, *, active_decision_keys: set[str]) -> int:
        if self._repository is not None:
            return int(
                self._repository.expire_missing_workbench_reconciliation_decisions(
                    tenant_id=self._tenant_id,
                    scope_month=scope_month,
                    active_decision_keys=sorted(active_decision_keys),
                )
                or 0
            )
        expired = 0
        for decision in self._decisions_by_key.values():
            if decision.get("scope_month") != scope_month:
                continue
            if decision.get("decision_status") not in ACTIVE_DECISION_STATUSES:
                continue
            if str(decision.get("decision_key") or "") in active_decision_keys:
                continue
            decision["decision_status"] = DECISION_STATUS_EXPIRED
            expired += 1
        return expired

    def _mark_by_row_ids(
        self,
        row_ids: list[str],
        *,
        status: str,
        metadata_key: str,
        metadata_value: str,
    ) -> int:
        row_filter = {str(row_id) for row_id in row_ids if str(row_id or "").strip()}
        if not row_filter:
            return 0
        changed = 0
        for decision in self._decisions_by_key.values():
            if decision.get("decision_status") not in ACTIVE_DECISION_STATUSES:
                continue
            if not row_filter.intersection(str(row_id) for row_id in decision.get("row_ids") or []):
                continue
            decision["decision_status"] = status
            decision[metadata_key] = metadata_value
            changed += 1
        return changed


def _source_versions_match(existing: object, current: dict[str, object]) -> bool:
    if not isinstance(existing, dict):
        return not current
    for key, value in current.items():
        if existing.get(key) != value:
            return False
    return True

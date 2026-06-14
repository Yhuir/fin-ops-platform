from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any

from fin_ops_platform.services.workbench_free_matching_engine import WorkbenchFreeMatchingEngine
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    MATCH_DOMAIN_FREE,
    MATCH_DOMAIN_SPECIAL,
    WorkbenchDecision,
    expand_scope_month_window,
)
from fin_ops_platform.services.workbench_special_reconciliation_adapter import (
    WorkbenchSpecialReconciliationAdapter,
)
from fin_ops_platform.services.workbench_row_identity import row_type_for_workbench_row_id


ACTIVE_RELATION_STATUS = "active"


class WorkbenchReconciliationEngine:
    def __init__(
        self,
        *,
        decision_store: WorkbenchReconciliationDecisionStore,
        pair_relation_service: WorkbenchPairRelationService,
        free_engine: WorkbenchFreeMatchingEngine | None = None,
        special_adapter: Any | None = None,
    ) -> None:
        self._decision_store = decision_store
        self._pair_relation_service = pair_relation_service
        self._free_engine = free_engine or WorkbenchFreeMatchingEngine()
        self._special_adapter = special_adapter or WorkbenchSpecialReconciliationAdapter()

    def run_scope(
        self,
        scope_month: str,
        *,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
        settings: dict[str, Any] | None = None,
        source_versions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        normalized_scope_month = str(scope_month or "").strip()
        resolved_source_versions = dict(source_versions or {})
        held_row_ids, extendable_payment_row_ids = self._active_pair_relation_row_ids(normalized_scope_month)
        if not invoice_rows:
            extendable_payment_row_ids = set()
        strict_held_row_ids = held_row_ids.difference(extendable_payment_row_ids)
        scoped_held_row_ids = self._row_ids_in_rows((oa_rows, bank_rows, invoice_rows), held_row_ids)
        filtered_oa_rows = self._exclude_row_ids(oa_rows, strict_held_row_ids)
        filtered_bank_rows = self._exclude_row_ids(bank_rows, strict_held_row_ids)
        filtered_invoice_rows = self._exclude_row_ids(invoice_rows, held_row_ids)

        expired_count = self._decision_store.expire_stale(
            [normalized_scope_month],
            source_versions=resolved_source_versions,
        )
        special_result = self._special_adapter.generate_decisions(
            normalized_scope_month,
            filtered_oa_rows,
            filtered_bank_rows,
            filtered_invoice_rows,
            settings=dict(settings or {}),
            source_versions=resolved_source_versions,
        )
        special_decisions = [
            decision
            for decision in list(getattr(special_result, "decisions", ()) or ())
            if isinstance(decision, WorkbenchDecision) and decision.scope_month == normalized_scope_month
        ]
        claimed_by_special = {
            str(row_id or "").strip()
            for row_id in getattr(special_result, "claimed_row_ids", set())
            if str(row_id or "").strip()
        }
        free_decisions = [
            decision
            for decision in self._free_engine.generate_decisions(
                normalized_scope_month,
                self._exclude_row_ids(filtered_oa_rows, claimed_by_special),
                self._exclude_row_ids(filtered_bank_rows, claimed_by_special),
                self._exclude_row_ids(filtered_invoice_rows, claimed_by_special),
                source_versions=resolved_source_versions,
            )
            if not set(decision.row_ids).issubset(held_row_ids)
        ]
        decisions = [
            decision
            for decision in [*special_decisions, *free_decisions]
            if decision.scope_month == normalized_scope_month
        ]
        missing_expired_count = self._decision_store.expire_missing_for_scope(
            normalized_scope_month,
            active_decision_keys={decision.decision_key for decision in decisions},
        )
        self._decision_store.upsert_decisions(decisions)
        return self._summary(
            scope_month=normalized_scope_month,
            decisions=decisions,
            expired_count=expired_count + missing_expired_count,
            suppressed_by_pair_relation_count=len(scoped_held_row_ids),
            duration_ms=self._duration_ms(started_at),
        )

    def _active_pair_relation_row_ids(self, scope_month: str) -> tuple[set[str], set[str]]:
        list_active_relations = getattr(self._pair_relation_service, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("pair_relation_service must provide list_active_relations().")
        window_months = set(expand_scope_month_window(scope_month))
        held: set[str] = set()
        extendable_payment_rows: set[str] = set()
        for relation in list_active_relations():
            if not isinstance(relation, dict):
                raise ValueError("pair_relation_service returned a non-dict active relation.")
            if str(relation.get("status") or ACTIVE_RELATION_STATUS) != ACTIVE_RELATION_STATUS:
                continue
            month_scope = self._relation_month_scope(relation)
            if month_scope != "all" and month_scope not in window_months:
                continue
            row_ids = [str(row_id or "").strip() for row_id in list(relation.get("row_ids") or [])]
            row_types = [str(row_type or "").strip() for row_type in list(relation.get("row_types") or [])]
            typed_row_ids: list[tuple[str, str]] = []
            for index, row_id in enumerate(row_ids):
                normalized_row_id = str(row_id or "").strip()
                if normalized_row_id:
                    held.add(normalized_row_id)
                    row_type = row_types[index] if index < len(row_types) and row_types[index] else self._row_type_for_row_id(normalized_row_id)
                    typed_row_ids.append((normalized_row_id, row_type))
            relation_types = {row_type for _, row_type in typed_row_ids}
            if month_scope in {"all", scope_month} and {"oa", "bank"}.issubset(relation_types) and "invoice" not in relation_types:
                extendable_payment_rows.update(
                    row_id for row_id, row_type in typed_row_ids if row_type in {"oa", "bank"}
                )
        return held, extendable_payment_rows

    @staticmethod
    def _relation_month_scope(relation: dict[str, Any]) -> str:
        month_scope = str(relation.get("month_scope") or "all").strip()
        if month_scope == "all":
            return "all"
        return month_scope[:7] if len(month_scope) >= 7 else month_scope

    @staticmethod
    def _row_type_for_row_id(row_id: str) -> str:
        return row_type_for_workbench_row_id(row_id, unknown="")

    @classmethod
    def _exclude_row_ids(cls, rows: list[dict[str, Any]], row_ids: set[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return [deepcopy(row) for row in rows]
        filtered: list[dict[str, Any]] = []
        for row in rows:
            row_id = cls._row_id(row)
            if not row_id:
                raise ValueError("workbench row requires id or row_id.")
            if row_id not in row_ids:
                filtered.append(deepcopy(row))
        return filtered

    @classmethod
    def _row_ids_in_rows(cls, row_groups: tuple[list[dict[str, Any]], ...], row_ids: set[str]) -> set[str]:
        if not row_ids:
            return set()
        scoped: set[str] = set()
        for rows in row_groups:
            for row in rows:
                row_id = cls._row_id(row)
                if row_id in row_ids:
                    scoped.add(row_id)
        return scoped

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "").strip()

    @staticmethod
    def _summary(
        *,
        scope_month: str,
        decisions: list[WorkbenchDecision],
        expired_count: int,
        suppressed_by_pair_relation_count: int,
        duration_ms: int,
    ) -> dict[str, Any]:
        paired_count = sum(1 for decision in decisions if decision.decision_status == DECISION_STATUS_PAIRED)
        open_count = sum(1 for decision in decisions if decision.decision_status == DECISION_STATUS_OPEN)
        free_count = sum(1 for decision in decisions if decision.match_domain == MATCH_DOMAIN_FREE)
        special_count = sum(1 for decision in decisions if decision.match_domain == MATCH_DOMAIN_SPECIAL)
        return {
            "scope_month": scope_month,
            "decision_count": len(decisions),
            "paired_count": paired_count,
            "open_count": open_count,
            "free_decision_count": free_count,
            "special_decision_count": special_count,
            "expired_decision_count": int(expired_count or 0),
            "suppressed_by_pair_relation_count": int(suppressed_by_pair_relation_count or 0),
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))

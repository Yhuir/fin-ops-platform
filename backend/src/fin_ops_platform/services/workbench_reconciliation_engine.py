from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from decimal import Decimal
from time import perf_counter
from typing import Any

from fin_ops_platform.services.workbench_free_matching_engine import WorkbenchFreeMatchingEngine
from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_PAIRED,
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
AUTO_COMPLETABLE_RELATION_MODES = frozenset({"manual_confirmed"})
THREE_PANE_ROW_TYPES = frozenset({"oa", "bank", "invoice"})
AUTO_COMPLETION_ACTOR = "system:workbench-relation-auto-completion"
AUTO_COMPLETION_HISTORY_OPERATION = "auto_complete_three_way_relation"
AUTO_PAIR_ACTOR = "system:workbench-relation-auto-pair"
AUTO_PAIR_HISTORY_OPERATION = "auto_create_relation_from_decision"


class WorkbenchMatchingRelationReadPort:
    def __init__(self, relation_reader: Any) -> None:
        self._relation_reader = relation_reader

    def list_active_relations(self) -> list[dict[str, Any]]:
        list_active_relations = getattr(self._relation_reader, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("relation_reader must provide list_active_relations().")
        relations = list(list_active_relations() or [])
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
        return [dict(relation) for relation in relations]

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        active_relations_for_row_ids = getattr(self._relation_reader, "active_relations_for_row_ids", None)
        if not callable(active_relations_for_row_ids):
            raise ValueError("relation_reader must provide active_relations_for_row_ids(...).")
        relations = list(active_relations_for_row_ids(list(row_ids or [])) or [])
        for relation in relations:
            if not isinstance(relation, dict):
                raise ValueError("relation_reader returned a non-dict active relation.")
        return [dict(relation) for relation in relations]

    def has_withdrawn_relation_for_row_ids(self, row_ids: list[str]) -> bool:
        target = {
            str(row_id or "").strip()
            for row_id in list(row_ids or [])
            if str(row_id or "").strip()
        }
        if not target:
            return False
        checker = getattr(self._relation_reader, "has_withdrawn_relation_for_row_ids", None)
        if callable(checker):
            return bool(checker(list(target)))
        list_history = getattr(self._relation_reader, "list_history", None)
        if not callable(list_history):
            return False
        for history in list(list_history() or []):
            if not isinstance(history, dict):
                continue
            if str(history.get("operation_type") or "") != "withdraw_link":
                continue
            for relation in list(history.get("before_relations") or []):
                if not isinstance(relation, dict):
                    continue
                relation_row_ids = {
                    str(row_id or "").strip()
                    for row_id in list(relation.get("row_ids") or [])
                    if str(row_id or "").strip()
                }
                if relation_row_ids == target:
                    return True
        return False


class WorkbenchReconciliationEngine:
    def __init__(
        self,
        *,
        decision_store: WorkbenchReconciliationDecisionStore,
        relation_read_port: WorkbenchMatchingRelationReadPort,
        free_engine: WorkbenchFreeMatchingEngine | None = None,
        special_adapter: Any | None = None,
        relation_command_service: Any | None = None,
    ) -> None:
        self._decision_store = decision_store
        self._relation_read_port = relation_read_port
        self._free_engine = free_engine or WorkbenchFreeMatchingEngine()
        self._special_adapter = special_adapter or WorkbenchSpecialReconciliationAdapter()
        self._relation_command_service = relation_command_service
        self._amount_check_service = WorkbenchAmountCheckService()

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
        held_row_ids, extendable_relation_row_ids = self._active_pair_relation_row_ids(normalized_scope_month)
        if not invoice_rows:
            extendable_relation_row_ids = {
                row_id
                for row_id in extendable_relation_row_ids
                if self._row_type_for_row_id(row_id) == "invoice"
            }
        strict_held_row_ids = held_row_ids.difference(extendable_relation_row_ids)
        scoped_held_row_ids = self._row_ids_in_rows((oa_rows, bank_rows, invoice_rows), held_row_ids)
        filtered_oa_rows = self._exclude_row_ids(oa_rows, strict_held_row_ids)
        filtered_bank_rows = self._exclude_row_ids(bank_rows, strict_held_row_ids)
        filtered_invoice_rows = self._exclude_row_ids(invoice_rows, strict_held_row_ids)

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
        auto_created_relation_count = self._auto_create_paired_relations(
            decisions,
            rows_by_id=self._rows_by_id((oa_rows, bank_rows, invoice_rows)),
            scope_month=normalized_scope_month,
        )
        auto_completed_relation_count = self._auto_complete_two_pane_relations(
            decisions,
            rows_by_id=self._rows_by_id((oa_rows, bank_rows, invoice_rows)),
            scope_month=normalized_scope_month,
        )
        return self._summary(
            scope_month=normalized_scope_month,
            decisions=decisions,
            expired_count=expired_count + missing_expired_count,
            suppressed_by_pair_relation_count=len(scoped_held_row_ids),
            auto_created_relation_count=auto_created_relation_count,
            auto_completed_relation_count=auto_completed_relation_count,
            duration_ms=self._duration_ms(started_at),
        )

    def _active_pair_relation_row_ids(self, scope_month: str) -> tuple[set[str], set[str]]:
        window_months = set(expand_scope_month_window(scope_month))
        held: set[str] = set()
        extendable_relation_rows: set[str] = set()
        for relation in self._relation_read_port.list_active_relations():
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
            if self._relation_can_participate_in_three_way_completion(
                relation,
                relation_types=relation_types,
                month_scope=month_scope,
                scope_month=scope_month,
            ):
                extendable_relation_rows.update(row_id for row_id, _row_type in typed_row_ids)
        return held, extendable_relation_rows

    def _auto_complete_two_pane_relations(
        self,
        decisions: list[WorkbenchDecision],
        *,
        rows_by_id: dict[str, dict[str, Any]],
        scope_month: str,
    ) -> int:
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            return 0
        completed = 0
        for decision in sorted(decisions, key=lambda item: item.decision_key):
            if not self._decision_can_complete_relation(decision):
                continue
            row_ids = list(decision.row_ids)
            decision_row_ids = set(row_ids)
            if any(row_id not in rows_by_id for row_id in row_ids):
                continue
            active_relations = self._relation_read_port.active_relations_for_row_ids(row_ids)
            if len(active_relations) != 1:
                continue
            relation = active_relations[0]
            if not self._relation_matches_completion_decision(relation, decision_row_ids):
                continue

            rows_by_type = self._decision_rows_by_type(decision, rows_by_id)
            amount_check = self._amount_check_service.check(rows_by_type)
            if str(amount_check.get("status") or "") != "matched":
                continue

            case_id = str(relation.get("case_id") or "").strip()
            if not case_id:
                continue
            confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=self._decision_row_types(decision),
                relation_mode=str(relation.get("relation_mode") or "manual_confirmed").strip(),
                actor_id=AUTO_COMPLETION_ACTOR,
                month_scope=str(relation.get("month_scope") or scope_month or "all").strip(),
                note="自动补齐第三栏并升级为三栏关系",
                amount_check=amount_check,
                special_metadata=self._auto_completion_metadata(relation, decision),
                evidence=self._plain_value(decision.evidence or {}),
                rule_version=str(decision.rule_version or ""),
                relation_created_by=AUTO_COMPLETION_ACTOR,
                history_note="自动补齐第三栏",
                idempotency_key=self._auto_completion_idempotency_key(case_id, decision.decision_key),
                before_relations=[deepcopy(relation)],
                replace_existing=True,
                history_operation_type=AUTO_COMPLETION_HISTORY_OPERATION,
            )
            self._decision_store.consume_by_row_ids(row_ids, relation_id=case_id)
            completed += 1
        return completed

    def _auto_create_paired_relations(
        self,
        decisions: list[WorkbenchDecision],
        *,
        rows_by_id: dict[str, dict[str, Any]],
        scope_month: str,
    ) -> int:
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            return 0
        created = 0
        for decision in sorted(decisions, key=lambda item: item.decision_key):
            if not self._decision_can_create_relation(decision):
                continue
            row_ids = list(decision.row_ids)
            if any(row_id not in rows_by_id for row_id in row_ids):
                continue
            if self._relation_read_port.active_relations_for_row_ids(row_ids):
                continue
            if self._relation_read_port.has_withdrawn_relation_for_row_ids(row_ids):
                continue

            rows_by_type = self._decision_rows_by_type(decision, rows_by_id)
            amount_check = self._amount_check_service.check(rows_by_type)
            if str(amount_check.get("status") or "") != "matched":
                continue
            case_id = str(decision.decision_key or "").strip()
            if not case_id:
                continue
            confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=self._decision_row_types(decision),
                relation_mode="manual_confirmed",
                actor_id=AUTO_PAIR_ACTOR,
                month_scope=scope_month or str(decision.scope_month or "all").strip(),
                note="系统自动配对",
                amount_check=amount_check,
                special_metadata=self._auto_pair_metadata(decision),
                evidence=self._plain_value(decision.evidence or {}),
                rule_version=str(decision.rule_version or ""),
                relation_created_by=AUTO_PAIR_ACTOR,
                history_note="系统自动配对",
                idempotency_key=self._auto_pair_idempotency_key(decision.decision_key),
                history_operation_type=AUTO_PAIR_HISTORY_OPERATION,
            )
            self._decision_store.consume_by_row_ids(row_ids, relation_id=case_id)
            created += 1
        return created

    @classmethod
    def _decision_can_create_relation(cls, decision: WorkbenchDecision) -> bool:
        row_types = cls._decision_row_types_set(decision)
        return (
            decision.decision_status == DECISION_STATUS_PAIRED
            and decision.display_state == DISPLAY_STATE_PAIRED
            and decision.match_domain == MATCH_DOMAIN_FREE
            and len(decision.row_ids) >= 2
            and bool(row_types)
            and row_types.issubset(THREE_PANE_ROW_TYPES)
        )

    @classmethod
    def _decision_can_complete_relation(cls, decision: WorkbenchDecision) -> bool:
        return (
            decision.decision_status == DECISION_STATUS_PAIRED
            and decision.display_state == DISPLAY_STATE_PAIRED
            and decision.match_domain == MATCH_DOMAIN_FREE
            and decision.match_shape == "oa_bank_invoice"
            and cls._decision_row_types_set(decision) == THREE_PANE_ROW_TYPES
            and len(decision.row_ids) >= 3
        )

    @classmethod
    def _relation_matches_completion_decision(
        cls,
        relation: dict[str, Any],
        decision_row_ids: set[str],
    ) -> bool:
        if str(relation.get("status") or ACTIVE_RELATION_STATUS) != ACTIVE_RELATION_STATUS:
            return False
        if str(relation.get("relation_mode") or "").strip() not in AUTO_COMPLETABLE_RELATION_MODES:
            return False
        relation_row_ids = set(cls._relation_row_ids(relation))
        if not relation_row_ids or not relation_row_ids < decision_row_ids:
            return False
        relation_types = cls._relation_row_types(relation)
        return len(relation_types) == 2 and relation_types.issubset(THREE_PANE_ROW_TYPES)

    @staticmethod
    def _relation_can_participate_in_three_way_completion(
        relation: dict[str, Any],
        *,
        relation_types: set[str],
        month_scope: str,
        scope_month: str,
    ) -> bool:
        if month_scope not in {"all", scope_month}:
            return False
        if str(relation.get("relation_mode") or "").strip() not in AUTO_COMPLETABLE_RELATION_MODES:
            return False
        return len(relation_types) == 2 and relation_types.issubset(THREE_PANE_ROW_TYPES)

    @classmethod
    def _auto_completion_metadata(cls, relation: dict[str, Any], decision: WorkbenchDecision) -> dict[str, Any]:
        metadata = deepcopy(relation.get("special_metadata") or {})
        metadata["auto_completion"] = {
            "decision_key": decision.decision_key,
            "decision_id": decision.decision_id,
            "completed_from_row_ids": cls._relation_row_ids(relation),
            "completed_from_row_types": sorted(cls._relation_row_types(relation)),
            "operation": AUTO_COMPLETION_HISTORY_OPERATION,
        }
        return metadata

    @staticmethod
    def _auto_completion_idempotency_key(case_id: str, decision_key: str) -> str:
        return f"workbench:auto-complete-three-way:{case_id}:{decision_key}"

    @staticmethod
    def _auto_pair_metadata(decision: WorkbenchDecision) -> dict[str, Any]:
        return {
            "auto_pair": {
                "decision_key": decision.decision_key,
                "decision_id": decision.decision_id,
                "match_shape": decision.match_shape,
                "rule_code": decision.rule_code,
                "operation": AUTO_PAIR_HISTORY_OPERATION,
            }
        }

    @staticmethod
    def _auto_pair_idempotency_key(decision_key: str) -> str:
        return f"workbench:auto-pair:{decision_key}"

    @classmethod
    def _decision_rows_by_type(
        cls,
        decision: WorkbenchDecision,
        rows_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        rows_by_type: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        for row_id, row_type in zip(decision.row_ids, cls._decision_row_types(decision)):
            if row_type in rows_by_type:
                rows_by_type[row_type].append(deepcopy(rows_by_id[row_id]))
        return rows_by_type

    @classmethod
    def _decision_row_types(cls, decision: WorkbenchDecision) -> list[str]:
        row_types: list[str] = []
        for row_id in decision.row_ids:
            if row_id in decision.oa_row_ids:
                row_types.append("oa")
            elif row_id in decision.bank_row_ids:
                row_types.append("bank")
            elif row_id in decision.invoice_row_ids:
                row_types.append("invoice")
            else:
                row_types.append(cls._row_type_for_row_id(row_id))
        return row_types

    @classmethod
    def _decision_row_types_set(cls, decision: WorkbenchDecision) -> set[str]:
        return {row_type for row_type in cls._decision_row_types(decision) if row_type}

    @classmethod
    def _relation_row_ids(cls, relation: dict[str, Any]) -> list[str]:
        return [row_id for row_id in (str(row_id or "").strip() for row_id in relation.get("row_ids") or []) if row_id]

    @classmethod
    def _relation_row_types(cls, relation: dict[str, Any]) -> set[str]:
        row_ids = cls._relation_row_ids(relation)
        raw_row_types = [str(row_type or "").strip() for row_type in relation.get("row_types") or []]
        row_types: set[str] = set()
        for index, row_id in enumerate(row_ids):
            row_type = raw_row_types[index] if index < len(raw_row_types) and raw_row_types[index] else cls._row_type_for_row_id(row_id)
            if row_type:
                row_types.add(row_type)
        return row_types

    @classmethod
    def _rows_by_id(cls, row_groups: tuple[list[dict[str, Any]], ...]) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for group in row_groups:
            for row in group:
                row_id = cls._row_id(row)
                if row_id:
                    rows[row_id] = deepcopy(row)
        return rows

    @classmethod
    def _plain_value(cls, value: Any) -> Any:
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, Mapping):
            return {str(key): cls._plain_value(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._plain_value(item) for item in value]
        return deepcopy(value)

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
        auto_created_relation_count: int,
        auto_completed_relation_count: int,
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
            "auto_created_relation_count": int(auto_created_relation_count or 0),
            "auto_completed_relation_count": int(auto_completed_relation_count or 0),
            "duration_ms": duration_ms,
        }

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))

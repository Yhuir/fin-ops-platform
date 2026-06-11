from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.no_oa_managed_rule_policy import (
    NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
    NO_OA_LEGACY_RELATION_MIGRATION_VERSION,
    no_oa_batch_type_for_legacy_relation_mode,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class NoOaLegacyRelationMigrationService:
    def __init__(self, *, pair_relation_service: WorkbenchPairRelationService) -> None:
        self._pair_relation_service = pair_relation_service

    def batch_type_for_relation(self, relation: dict[str, Any]) -> str:
        return no_oa_batch_type_for_legacy_relation_mode(str(relation.get("relation_mode") or ""))

    def active_legacy_relations(self, active_relations: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relations: list[dict[str, Any]] = []
        for relation in list(active_relations or []):
            if not isinstance(relation, dict):
                continue
            if str(relation.get("status") or "active") != "active":
                continue
            if not self.batch_type_for_relation(relation):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id:
                continue
            current_relation = self._pair_relation_service.get_active_relation_by_case_id(case_id)
            if current_relation is None:
                continue
            relations.append(deepcopy(current_relation))
        return relations

    def current_active_relation(self, case_id: str) -> dict[str, Any] | None:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            return None
        current_relation = self._pair_relation_service.get_active_relation_by_case_id(resolved_case_id)
        return deepcopy(current_relation) if isinstance(current_relation, dict) else None

    def migrate_relation_to_no_oa(
        self,
        *,
        legacy_relation: dict[str, Any],
        no_oa_relation_case_id: str,
        row_ids: list[str],
        month_scope: str,
        created_at: str,
        special_metadata: dict[str, Any],
        evidence: dict[str, Any],
        display_tags: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        return self.migrate_relations_to_no_oa(
            legacy_relations=[legacy_relation],
            no_oa_relation_case_id=no_oa_relation_case_id,
            row_ids=row_ids,
            month_scope=month_scope,
            created_at=created_at,
            special_metadata=special_metadata,
            evidence=evidence,
            display_tags=display_tags,
        )

    def migrate_relations_to_no_oa(
        self,
        *,
        legacy_relations: list[dict[str, Any]],
        no_oa_relation_case_id: str,
        row_ids: list[str],
        month_scope: str,
        created_at: str,
        special_metadata: dict[str, Any],
        evidence: dict[str, Any],
        display_tags: list[str],
    ) -> tuple[dict[str, Any], list[str]]:
        resolved_legacy_relations = [
            relation for relation in list(legacy_relations or []) if isinstance(relation, dict)
        ]
        legacy_case_ids = [
            str(relation.get("case_id") or "").strip()
            for relation in resolved_legacy_relations
            if str(relation.get("case_id") or "").strip()
        ]
        first_legacy_relation = resolved_legacy_relations[0] if resolved_legacy_relations else {}
        changed_case_ids: list[str] = []
        existing_relation = self._pair_relation_service.get_active_relation_by_case_id(no_oa_relation_case_id)
        if not self._is_matching_no_oa_relation(existing_relation, no_oa_relation_case_id, row_ids, special_metadata):
            for legacy_case_id in legacy_case_ids:
                cancelled = self._pair_relation_service.cancel_relation(legacy_case_id, cancelled_at=created_at)
                if cancelled is not None:
                    changed_case_ids.append(legacy_case_id)
            relation = self._pair_relation_service.create_active_relation(
                case_id=no_oa_relation_case_id,
                row_ids=row_ids,
                row_types=["bank" for _ in row_ids],
                relation_mode="no_oa_bank_batch",
                created_by=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                month_scope=month_scope or str(first_legacy_relation.get("month_scope") or "all"),
                created_at=created_at,
                note="历史工资/内部往来款自动配对迁移为免OA批次",
                special_metadata=deepcopy(special_metadata),
                evidence=deepcopy(evidence),
                display_tags=display_tags,
            )
            changed_case_ids.append(no_oa_relation_case_id)
            return relation, changed_case_ids

        for legacy_case_id in legacy_case_ids:
            cancelled = self._pair_relation_service.cancel_relation(legacy_case_id, cancelled_at=created_at)
            if cancelled is not None:
                changed_case_ids.append(legacy_case_id)
        return deepcopy(existing_relation), changed_case_ids

    @staticmethod
    def legacy_metadata(legacy_relation: dict[str, Any], *, migrated_at: str) -> dict[str, Any]:
        legacy_case_id = str(legacy_relation.get("case_id") or "").strip()
        legacy_relation_id = str(
            legacy_relation.get("relation_id")
            or legacy_relation.get("id")
            or legacy_relation.get("_id")
            or legacy_case_id
        ).strip()
        return {
            "legacy_relation_mode": str(legacy_relation.get("relation_mode") or "").strip(),
            "legacy_case_id": legacy_case_id,
            "legacy_relation_id": legacy_relation_id,
            "migration_version": NO_OA_LEGACY_RELATION_MIGRATION_VERSION,
            "migration_source": NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
            "migrated_at": migrated_at,
        }

    @staticmethod
    def _is_matching_no_oa_relation(
        relation: dict[str, Any] | None,
        case_id: str,
        row_ids: list[str],
        special_metadata: dict[str, Any],
    ) -> bool:
        if not isinstance(relation, dict):
            return False
        if str(relation.get("case_id") or "").strip() != case_id:
            return False
        if str(relation.get("relation_mode") or "").strip() != "no_oa_bank_batch":
            return False
        if sorted(str(row_id) for row_id in list(relation.get("row_ids") or [])) != sorted(row_ids):
            return False
        relation_metadata = relation.get("special_metadata")
        if not isinstance(relation_metadata, dict):
            return False
        return (
            str(relation_metadata.get("source_batch_id") or "").strip()
            == str(special_metadata.get("source_batch_id") or "").strip()
        )

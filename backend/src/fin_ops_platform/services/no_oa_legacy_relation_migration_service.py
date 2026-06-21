from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.no_oa_managed_rule_policy import (
    NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
    NO_OA_LEGACY_RELATION_MIGRATION_VERSION,
    no_oa_batch_type_for_legacy_relation_mode,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class NoOaLegacyRelationMigrationService:
    def __init__(self, *, relation_command_service: Any | None = None) -> None:
        self._relation_command_service = relation_command_service

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
            relations.append(deepcopy(relation))
        return relations

    def migrate_relation_to_no_oa(
        self,
        *,
        legacy_relation: dict[str, Any],
        existing_relation: dict[str, Any] | None = None,
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
            existing_relation=existing_relation,
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
        existing_relation: dict[str, Any] | None = None,
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
        if not self._is_matching_no_oa_relation(existing_relation, no_oa_relation_case_id, row_ids, special_metadata):
            for legacy_case_id in legacy_case_ids:
                changed_case_ids.extend(
                    self._cancel_relation(
                        legacy_case_id,
                        occurred_at=created_at,
                        reason="历史工资/内部往来款自动配对迁移为免OA批次",
                        history_operation_type="no_oa_legacy_relation_migration_cancel",
                    )
                )
            relation, changed_ids = self._confirm_relation(
                case_id=no_oa_relation_case_id,
                row_ids=row_ids,
                row_types=["bank" for _ in row_ids],
                relation_mode="no_oa_bank_batch",
                actor_id=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                month_scope=month_scope or str(first_legacy_relation.get("month_scope") or "all"),
                occurred_at=created_at,
                note="历史工资/内部往来款自动配对迁移为免OA批次",
                special_metadata=deepcopy(special_metadata),
                evidence=deepcopy(evidence),
                display_tags=display_tags,
                history_operation_type="no_oa_legacy_relation_migration",
            )
            changed_case_ids.extend(changed_ids)
            return relation, changed_case_ids

        for legacy_case_id in legacy_case_ids:
            changed_case_ids.extend(
                self._cancel_relation(
                    legacy_case_id,
                    occurred_at=created_at,
                    reason="历史工资/内部往来款自动配对迁移为免OA批次",
                    history_operation_type="no_oa_legacy_relation_migration_cancel",
                )
            )
        return deepcopy(existing_relation), changed_case_ids

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise ValueError("no_oa_relation_command_unavailable")
        return self._relation_command_service

    def _confirm_relation(self, **kwargs: Any) -> tuple[dict[str, Any], list[str]]:
        command_service = self._require_relation_command_service()
        try:
            result = command_service.confirm_relation(**kwargs)
        except WorkbenchRelationCommandError as exc:
            raise ValueError(exc.error_code) from exc
        relation = result.get("relation") if isinstance(result, dict) else None
        raw_changed_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
        changed_case_ids = [
            str(case_id).strip()
            for case_id in list(raw_changed_case_ids or [])
            if str(case_id).strip()
        ]
        return deepcopy(relation) if isinstance(relation, dict) else {}, changed_case_ids

    def _cancel_relation(
        self,
        case_id: str,
        *,
        occurred_at: str,
        reason: str,
        history_operation_type: str,
    ) -> list[str]:
        command_service = self._require_relation_command_service()
        try:
            result = command_service.cancel_relation(
                case_id=case_id,
                actor_id=NO_OA_LEGACY_RELATION_MIGRATION_SOURCE,
                reason=reason,
                occurred_at=occurred_at,
                history_operation_type=history_operation_type,
            )
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return []
            raise ValueError(exc.error_code) from exc
        raw_changed_case_ids = result.get("changed_case_ids") if isinstance(result, dict) else []
        return [
            str(changed_case_id).strip()
            for changed_case_id in list(raw_changed_case_ids or [])
            if str(changed_case_id).strip()
        ]

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

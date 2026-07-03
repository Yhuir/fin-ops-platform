from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
import json
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_modes import VALID_WORKBENCH_RELATION_MODES

FRESH_WORKBENCH_RELATION_STATUS = "fresh"


class WorkbenchRelationCommandError(Exception):
    def __init__(
        self,
        error_code: str,
        message: str,
        *,
        payload: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.payload = dict(payload or {})


class _InMemoryIdempotencyStore:
    def __init__(self) -> None:
        self._records: dict[str, dict[str, Any]] = {}

    def get(self, key: str) -> dict[str, Any] | None:
        record = self._records.get(key)
        return deepcopy(record) if isinstance(record, dict) else None

    def save(self, key: str, record: dict[str, Any]) -> None:
        self._records[key] = deepcopy(record)


class CallbackWorkbenchRelationRepository:
    def __init__(self, *, load_snapshot: Any, save_snapshot: Any) -> None:
        self._load_snapshot = load_snapshot
        self._save_snapshot = save_snapshot

    def load_workbench_pair_relations(self) -> dict[str, Any]:
        snapshot = self._load_snapshot()
        return deepcopy(snapshot) if isinstance(snapshot, dict) else {}

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        return WorkbenchPairRelationService.from_snapshot(
            self.load_workbench_pair_relations()
        ).snapshot_for_row_ids(list(row_ids or []), case_ids=list(case_ids or []))

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        self._save_snapshot(
            deepcopy(snapshot),
            changed_case_ids=[
                str(case_id)
                for case_id in list(changed_case_ids or [])
                if str(case_id).strip()
            ],
        )


class WorkbenchRelationCommandService:
    def __init__(
        self,
        *,
        relation_repository: Any,
        relation_facade: Any | None = None,
        idempotency_store: Any | None = None,
        require_fresh_relations: bool = False,
    ) -> None:
        self._relation_repository = relation_repository
        self._relation_facade = relation_facade
        self._idempotency_store = idempotency_store or _InMemoryIdempotencyStore()
        self._require_fresh_relations = bool(require_fresh_relations)

    def confirm_relation(
        self,
        *,
        case_id: str,
        row_ids: list[str],
        row_types: list[str],
        relation_mode: str,
        actor_id: str,
        month_scope: str = "all",
        note: str | None = None,
        amount_check: dict[str, Any] | None = None,
        special_metadata: dict[str, Any] | None = None,
        evidence: dict[str, Any] | None = None,
        oa_exemption: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
        exception_case_id: str | None = None,
        rule_version: str | None = None,
        occurred_at: str | None = None,
        relation_created_by: str | None = None,
        history_note: str | None = None,
        idempotency_key: str | None = None,
        before_relations: list[dict[str, Any]] | None = None,
        replace_existing: bool = False,
        history_operation_type: str = "confirm_relation",
    ) -> dict[str, Any]:
        mode = self._validated_relation_mode(relation_mode)
        fingerprint = self._request_fingerprint(
            "confirm_relation",
            {
                "case_id": case_id,
                "row_ids": list(row_ids or []),
                "row_types": list(row_types or []),
                "relation_mode": mode,
                "actor_id": actor_id,
                "month_scope": month_scope,
                "note": note,
                "amount_check": amount_check,
                "special_metadata": special_metadata,
                "evidence": evidence,
                "oa_exemption": oa_exemption,
                "display_tags": display_tags,
                "exception_case_id": exception_case_id,
                "rule_version": rule_version,
                "relation_created_by": relation_created_by,
                "history_note": history_note,
                "before_relations": before_relations,
                "replace_existing": replace_existing,
                "history_operation_type": history_operation_type,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        freshness = self._assert_relation_read_model_fresh(
            row_ids=list(row_ids or []),
            month_scope=month_scope,
        )
        pair_service = self._pair_service_for_row_ids(list(row_ids or []), case_ids=[case_id])
        active_relations = pair_service.active_relations_for_row_ids(list(row_ids or []))
        if not replace_existing:
            conflicts = [
                relation
                for relation in active_relations
                if str(relation.get("case_id") or "").strip() != str(case_id or "").strip()
            ]
        else:
            conflicts = []
        if conflicts:
            raise WorkbenchRelationCommandError(
                "workbench_relation_active_row_conflict",
                "One or more rows are already active in another workbench relation.",
                payload={
                    "conflicting_case_ids": [
                        str(relation.get("case_id") or "")
                        for relation in conflicts
                        if str(relation.get("case_id") or "")
                    ],
                    "row_ids": [str(row_id) for row_id in list(row_ids or [])],
                },
            )

        if replace_existing:
            relation, history = pair_service.replace_with_confirmed_relation(
                case_id=case_id,
                row_ids=list(row_ids or []),
                row_types=list(row_types or []),
                relation_mode=mode,
                created_by=relation_created_by or actor_id,
                month_scope=month_scope,
                created_at=occurred_at,
                note=note,
                amount_check=amount_check,
                special_metadata=special_metadata,
                operation_type=history_operation_type,
                history_created_by=actor_id,
                history_note=history_note,
                exception_case_id=exception_case_id,
                rule_version=rule_version,
                evidence=evidence,
                oa_exemption=oa_exemption,
                display_tags=display_tags,
                before_relations=before_relations,
            )
        else:
            relation = pair_service.create_active_relation(
                case_id=case_id,
                row_ids=list(row_ids or []),
                row_types=list(row_types or []),
                relation_mode=mode,
                created_by=relation_created_by or actor_id,
                month_scope=month_scope,
                created_at=occurred_at,
                note=note,
                amount_check=amount_check,
                special_metadata=special_metadata,
                exception_case_id=exception_case_id,
                rule_version=rule_version,
                evidence=evidence,
                oa_exemption=oa_exemption,
                display_tags=display_tags,
            )
            history = pair_service.record_history(
                operation_type=history_operation_type,
                before_relations=[],
                after_relations=[relation],
                affected_row_ids=list(relation.get("row_ids") or []),
                created_by=actor_id,
                note=history_note if history_note is not None else note,
                amount_check=amount_check,
                created_at=occurred_at,
            )
        changed_case_ids = self._changed_case_ids(
            [
                *active_relations,
                *list(before_relations or []),
                relation,
            ]
        )
        self._save_changed_cases(pair_service, changed_case_ids)
        result = self._command_result(
            status="confirmed",
            relation=relation,
            history=history,
            changed_case_ids=changed_case_ids,
            affected_months=self._affected_months(month_scope),
            freshness=freshness,
            idempotent_replay=False,
        )
        self._save_idempotency_result(idempotency_key, fingerprint, result)
        return result

    def cancel_relation(
        self,
        *,
        case_id: str,
        actor_id: str,
        reason: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "cancel_relation",
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        fingerprint = self._request_fingerprint(
            "cancel_relation",
            {
                "case_id": resolved_case_id,
                "actor_id": actor_id,
                "reason": reason,
                "history_operation_type": history_operation_type,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        pair_service = self._pair_service_for_case_ids([resolved_case_id])
        before_relation = pair_service.get_active_relation_by_case_id(resolved_case_id)
        if not isinstance(before_relation, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
        freshness = self._assert_relation_read_model_fresh(
            row_ids=list(before_relation.get("row_ids") or []),
            month_scope=str(before_relation.get("month_scope") or "all"),
        )
        cancelled = pair_service.cancel_relation(resolved_case_id, cancelled_at=occurred_at)
        if not isinstance(cancelled, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
        history = pair_service.record_history(
            operation_type=history_operation_type,
            before_relations=[before_relation],
            after_relations=[],
            affected_row_ids=list(before_relation.get("row_ids") or []),
            created_by=actor_id,
            note=reason,
            amount_check=dict(before_relation.get("amount_check") or {}),
            created_at=occurred_at,
        )
        changed_case_ids = [resolved_case_id]
        self._save_changed_cases(pair_service, changed_case_ids)
        result = self._command_result(
            status="cancelled",
            relation=cancelled,
            history=history,
            changed_case_ids=changed_case_ids,
            affected_months=self._affected_months(str(before_relation.get("month_scope") or "all")),
            freshness=freshness,
            idempotent_replay=False,
        )
        self._save_idempotency_result(idempotency_key, fingerprint, result)
        return result

    def cancel_by_case_id(self, **kwargs: Any) -> dict[str, Any]:
        return self.cancel_relation(**kwargs)

    def cancel_relations_for_row_ids(
        self,
        *,
        row_ids: list[str],
        actor_id: str,
        reason: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "cancel_active_relation",
    ) -> dict[str, Any]:
        normalized_row_ids = [
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        fingerprint = self._request_fingerprint(
            "cancel_relations_for_row_ids",
            {
                "row_ids": normalized_row_ids,
                "actor_id": actor_id,
                "reason": reason,
                "history_operation_type": history_operation_type,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        pair_service = self._pair_service_for_row_ids(normalized_row_ids)
        before_relations = pair_service.active_relations_for_row_ids(normalized_row_ids)
        freshness = self._assert_relation_read_model_fresh(
            row_ids=normalized_row_ids,
            month_scope=self._combined_month_scope(before_relations),
        )
        if not before_relations:
            result = {
                "status": "noop",
                "relations": [],
                "history": None,
                "changed_case_ids": [],
                "affected_months": [],
                **self._success_freshness_payload(freshness, fallback_months=[]),
                "idempotent_replay": False,
            }
            self._save_idempotency_result(idempotency_key, fingerprint, result)
            return result

        cancelled_relations, history = pair_service.cancel_active_relations_for_row_ids(
            normalized_row_ids,
            created_by=actor_id,
            note=reason,
            created_at=occurred_at,
            operation_type=history_operation_type,
        )
        changed_case_ids = self._changed_case_ids([*before_relations, *cancelled_relations])
        self._save_changed_cases(pair_service, changed_case_ids)
        affected_months = self._affected_months_for_relations(before_relations)
        result = {
            "status": "cancelled",
            "relations": deepcopy(cancelled_relations),
            "history": deepcopy(history),
            "changed_case_ids": changed_case_ids,
            "affected_months": affected_months,
            **self._success_freshness_payload(freshness, fallback_months=affected_months),
            "idempotent_replay": False,
        }
        self._save_idempotency_result(idempotency_key, fingerprint, result)
        return result

    def update_relation_metadata_for_case_id(
        self,
        *,
        case_id: str,
        relation_mode: str | None = None,
        amount_check: dict[str, Any] | None = None,
        special_metadata: dict[str, Any] | None = None,
        display_tags: list[str] | None = None,
        actor_id: str,
        note: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "update_pair_relation_metadata",
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        normalized_relation_mode = (
            self._validated_relation_mode(relation_mode)
            if str(relation_mode or "").strip()
            else None
        )
        fingerprint = self._request_fingerprint(
            "update_relation_metadata_for_case_id",
            {
                "case_id": resolved_case_id,
                "relation_mode": normalized_relation_mode,
                "amount_check": amount_check,
                "special_metadata": special_metadata,
                "display_tags": display_tags,
                "actor_id": actor_id,
                "note": note,
                "history_operation_type": history_operation_type,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        pair_service = self._pair_service_for_case_ids([resolved_case_id])
        before_relation = pair_service.get_active_relation_by_case_id(resolved_case_id)
        if not isinstance(before_relation, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
        freshness = self._assert_relation_read_model_fresh(
            row_ids=list(before_relation.get("row_ids") or []),
            month_scope=str(before_relation.get("month_scope") or "all"),
        )
        relation, history = pair_service.update_relation_metadata_for_case_id(
            resolved_case_id,
            relation_mode=normalized_relation_mode,
            amount_check=amount_check,
            special_metadata=special_metadata,
            display_tags=display_tags,
            updated_by=actor_id,
            note=note,
            updated_at=occurred_at,
            operation_type=history_operation_type,
        )
        changed_case_ids = [resolved_case_id]
        self._save_changed_cases(pair_service, changed_case_ids)
        result = self._command_result(
            status="updated",
            relation=relation,
            history=history,
            changed_case_ids=changed_case_ids,
            affected_months=self._affected_months(str(relation.get("month_scope") or "all")),
            freshness=freshness,
            idempotent_replay=False,
        )
        self._save_idempotency_result(idempotency_key, fingerprint, result)
        return result

    def assert_write_precondition(
        self,
        *,
        row_ids: list[str],
        month_scope: str = "all",
    ) -> dict[str, Any]:
        return self._assert_relation_read_model_fresh(
            row_ids=list(row_ids or []),
            month_scope=month_scope,
        )

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        return self._pair_service_for_row_ids(list(row_ids or [])).active_relations_for_row_ids(list(row_ids or []))

    def list_active_relations(self) -> list[dict[str, Any]]:
        return self._pair_service().list_active_relations()

    def get_active_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        relation = self._pair_service_for_row_ids([str(row_id or "")]).get_active_relation_by_row_id(str(row_id or ""))
        return deepcopy(relation) if isinstance(relation, dict) else None

    def list_history(self) -> list[dict[str, Any]]:
        return self._pair_service().list_history()

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        relation = self._pair_service_for_case_ids([resolved_case_id]).get_active_relation_by_case_id(resolved_case_id)
        if not isinstance(relation, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
        return deepcopy(relation)

    def preview_withdraw_relation(
        self,
        *,
        row_ids: list[str],
        month_scope: str = "all",
    ) -> dict[str, Any]:
        pair_service = self._pair_service_for_row_ids(list(row_ids or []))
        return self._preview_withdraw_relation_from_pair_service(
            pair_service,
            row_ids=list(row_ids or []),
            month_scope=month_scope,
        )

    def _preview_withdraw_relation_from_pair_service(
        self,
        pair_service: WorkbenchPairRelationService,
        *,
        row_ids: list[str],
        month_scope: str = "all",
        freshness: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        active_relations = pair_service.active_relations_for_row_ids(list(row_ids or []))
        if not active_relations:
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"row_ids": [str(row_id) for row_id in list(row_ids or [])]},
            )
        if len(active_relations) > 1:
            raise WorkbenchRelationCommandError(
                "workbench_relation_multiple_groups_selected",
                "Only one workbench relation group can be withdrawn at a time.",
                payload={
                    "case_ids": [
                        str(relation.get("case_id") or "")
                        for relation in active_relations
                        if str(relation.get("case_id") or "").strip()
                    ],
                },
            )
        active_relation = active_relations[0]
        active_row_ids = [
            str(row_id)
            for row_id in list(active_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        resolved_month_scope = str(active_relation.get("month_scope") or month_scope or "all")
        resolved_freshness = freshness or self._assert_relation_read_model_fresh(
            row_ids=active_row_ids,
            month_scope=resolved_month_scope,
        )
        try:
            preview = pair_service.preview_withdraw_for_row_ids(active_row_ids)
        except KeyError as exc:
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"row_ids": active_row_ids},
            ) from exc
        active_relation = deepcopy(preview["active_relation"])
        after_relations = [
            deepcopy(relation)
            for relation in list(preview.get("after_relations") or [])
            if isinstance(relation, dict)
        ]
        expected_versions = self._withdraw_expected_versions(active_relation)
        preview_id = self._withdraw_preview_id(
            operation_type="withdraw_relation",
            active_relation=active_relation,
            after_relations=after_relations,
        )
        return {
            "operation": "withdraw_link",
            "operation_type": "withdraw_relation",
            "preview_id": preview_id,
            "can_submit": True,
            "requires_note": False,
            "message": "",
            "active_relation": self._relation_identity(active_relation),
            "before_relations": [deepcopy(active_relation)],
            "after_relations": after_relations,
            "submit_expected_versions": expected_versions,
            "read_model_status": str(resolved_freshness.get("status") or resolved_freshness.get("read_model_status") or FRESH_WORKBENCH_RELATION_STATUS),
            "read_model_scope_keys": list(resolved_freshness.get("read_model_scope_keys") or self._affected_months(resolved_month_scope)),
            "read_model_stale_reasons": list(resolved_freshness.get("stale_reasons") or resolved_freshness.get("read_model_stale_reasons") or []),
            "refresh_enqueued": bool(resolved_freshness.get("refresh_enqueued")),
        }

    def withdraw_relation(
        self,
        *,
        case_id: str,
        actor_id: str,
        reason: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "withdraw_link",
        preview_id: str | None = None,
        operation_type: str | None = None,
        expected_versions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        resolved_operation_type = str(operation_type or "withdraw_relation").strip()
        if resolved_operation_type != "withdraw_relation":
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation submit operation_type does not match the preview.",
                payload={"operation_type": resolved_operation_type},
            )
        fingerprint = self._request_fingerprint(
            "withdraw_relation",
            {
                "case_id": resolved_case_id,
                "actor_id": actor_id,
                "reason": reason,
                "history_operation_type": history_operation_type,
                "preview_id": preview_id,
                "operation_type": resolved_operation_type,
                "expected_versions": expected_versions,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        pair_service = self._pair_service_for_case_ids([resolved_case_id])
        before_relation = pair_service.get_active_relation_by_case_id(resolved_case_id)
        if not isinstance(before_relation, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
        before_row_ids = [
            str(row_id)
            for row_id in list(before_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        before_month_scope = str(before_relation.get("month_scope") or "all")
        freshness = self._assert_relation_read_model_fresh(
            row_ids=before_row_ids,
            month_scope=before_month_scope,
        )
        current_preview = self._preview_withdraw_relation_from_pair_service(
            pair_service,
            row_ids=before_row_ids,
            month_scope=before_month_scope,
            freshness=freshness,
        )
        self._assert_withdraw_preview_lock(
            preview=current_preview,
            preview_id=preview_id,
            expected_versions=expected_versions,
        )
        restored_relations, history = pair_service.withdraw_latest_for_row_ids(
            before_row_ids,
            created_by=actor_id,
            note=reason,
            created_at=occurred_at,
        )
        if history_operation_type != "withdraw_link":
            history = pair_service.record_history(
                operation_type=history_operation_type,
                before_relations=[before_relation],
                after_relations=restored_relations,
                affected_row_ids=[
                    str(row_id)
                    for relation in [before_relation, *restored_relations]
                    for row_id in list(relation.get("row_ids") or [])
                    if str(row_id).strip()
                ],
                created_by=actor_id,
                note=reason,
                amount_check=dict(before_relation.get("amount_check") or {}),
                created_at=occurred_at,
            )
        snapshot = pair_service.snapshot_case_ids(
            self._changed_case_ids([before_relation, *restored_relations])
        )
        relation = deepcopy(snapshot.get("pair_relations", {}).get(resolved_case_id, before_relation))
        changed_case_ids = self._changed_case_ids([relation, *restored_relations])
        self._save_changed_cases(pair_service, changed_case_ids)
        affected_row_ids = [
            str(row_id)
            for relation_item in [before_relation, *restored_relations]
            for row_id in list(relation_item.get("row_ids") or [])
            if str(row_id).strip()
        ]
        result = {
            **self._command_result(
                status="withdrawn",
                relation=relation,
                history=history,
                changed_case_ids=changed_case_ids,
                affected_months=self._affected_months(str(before_relation.get("month_scope") or "all")),
                freshness=freshness,
                idempotent_replay=False,
            ),
            "restored_relations": deepcopy(restored_relations),
            "affected_row_ids": list(dict.fromkeys(affected_row_ids)),
        }
        self._save_idempotency_result(idempotency_key, fingerprint, result)
        return result

    @classmethod
    def _relation_identity(cls, relation: dict[str, Any]) -> dict[str, Any]:
        case_id = str(relation.get("case_id") or "").strip()
        if not case_id:
            raise WorkbenchRelationCommandError(
                "workbench_relation_invalid_identity",
                "Workbench relation case_id is required.",
            )
        return {"case_id": case_id, "version": cls._relation_version(relation)}

    @classmethod
    def _withdraw_expected_versions(cls, active_relation: dict[str, Any]) -> dict[str, Any]:
        identity = cls._relation_identity(active_relation)
        return {f"relation:{identity['case_id']}": identity["version"]}

    @classmethod
    def _withdraw_preview_id(
        cls,
        *,
        operation_type: str,
        active_relation: dict[str, Any],
        after_relations: list[dict[str, Any]],
    ) -> str:
        payload = {
            "operation_type": operation_type,
            "active_relation": cls._relation_identity(active_relation),
            "active_row_ids": [
                str(row_id)
                for row_id in list(active_relation.get("row_ids") or [])
                if str(row_id).strip()
            ],
            "after_relations": [
                cls._relation_identity(relation)
                for relation in list(after_relations or [])
                if isinstance(relation, dict)
            ],
        }
        digest = sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
        ).hexdigest()[:24]
        return f"{operation_type}:{digest}"

    @staticmethod
    def _relation_version(relation: dict[str, Any]) -> int:
        version = relation.get("version")
        if type(version) is int:
            return version
        if isinstance(version, str) and version.strip().isdigit():
            return int(version.strip())
        return 1

    @staticmethod
    def _assert_withdraw_preview_lock(
        *,
        preview: dict[str, Any],
        preview_id: str | None,
        expected_versions: dict[str, Any] | None,
    ) -> None:
        resolved_preview_id = str(preview_id or "").strip()
        current_preview_id = str(preview.get("preview_id") or "").strip()
        if resolved_preview_id and resolved_preview_id != current_preview_id:
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation preview is stale.",
                payload={
                    "reason": "stale_preview_id",
                    "preview_id": resolved_preview_id,
                    "current_preview_id": current_preview_id,
                },
            )
        if isinstance(expected_versions, dict) and expected_versions:
            current_expected = dict(preview.get("submit_expected_versions") or {})
            if dict(expected_versions) != current_expected:
                raise WorkbenchRelationCommandError(
                    "workbench_relation_preview_conflict",
                    "Withdraw relation expected_versions do not match the current relation state.",
                    payload={
                        "reason": "stale_relation_identity",
                        "expected_versions": dict(expected_versions),
                        "current_expected_versions": current_expected,
                    },
                )

    def _pair_service(self) -> WorkbenchPairRelationService:
        loader = getattr(self._relation_repository, "load_workbench_pair_relations", None)
        if not callable(loader):
            raise WorkbenchRelationCommandError(
                "workbench_relation_repository_unavailable",
                "Workbench relation repository does not expose load_workbench_pair_relations.",
            )
        return WorkbenchPairRelationService.from_snapshot(loader())

    def _pair_service_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> WorkbenchPairRelationService:
        normalized_row_ids = [
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        normalized_case_ids = [
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        ]
        loader = getattr(self._relation_repository, "load_workbench_pair_relations_for_row_ids", None)
        if callable(loader):
            return WorkbenchPairRelationService.from_snapshot(
                loader(normalized_row_ids, case_ids=normalized_case_ids)
            )
        return self._pair_service()

    def _pair_service_for_case_ids(self, case_ids: list[str]) -> WorkbenchPairRelationService:
        return self._pair_service_for_row_ids([], case_ids=case_ids)

    def _save_changed_cases(self, pair_service: WorkbenchPairRelationService, changed_case_ids: list[str]) -> None:
        saver = getattr(self._relation_repository, "save_workbench_pair_relations", None)
        if not callable(saver):
            raise WorkbenchRelationCommandError(
                "workbench_relation_repository_unavailable",
                "Workbench relation repository does not expose save_workbench_pair_relations.",
            )
        changed_ids = {str(case_id).strip() for case_id in list(changed_case_ids or []) if str(case_id).strip()}
        saver(pair_service.snapshot_case_ids(sorted(changed_ids)), changed_case_ids=changed_ids)

    @staticmethod
    def _changed_case_ids(relations: list[dict[str, Any]]) -> list[str]:
        changed: list[str] = []
        seen: set[str] = set()
        for relation in list(relations or []):
            if not isinstance(relation, dict):
                continue
            case_id = str(relation.get("case_id") or "").strip()
            if not case_id or case_id in seen:
                continue
            seen.add(case_id)
            changed.append(case_id)
        return changed

    def _combined_month_scope(self, relations: list[dict[str, Any]]) -> str:
        months = self._affected_months_for_relations(relations)
        return months[0] if len(months) == 1 else "all"

    def _affected_months_for_relations(self, relations: list[dict[str, Any]]) -> list[str]:
        months: list[str] = []
        for relation in list(relations or []):
            months.extend(self._affected_months(str(relation.get("month_scope") or "all")))
        return list(dict.fromkeys(months))

    def _assert_relation_read_model_fresh(
        self,
        *,
        row_ids: list[str],
        month_scope: str,
    ) -> dict[str, Any]:
        if not self._require_fresh_relations:
            return {
                "status": FRESH_WORKBENCH_RELATION_STATUS,
                "read_model_scope_keys": self._affected_months(month_scope),
                "stale_reasons": [],
                "refresh_enqueued": False,
            }
        if self._relation_facade is None:
            raise WorkbenchRelationCommandError(
                "workbench_relation_read_model_unavailable",
                "Workbench relation read facade is not configured.",
                payload={
                    "read_model_status": "unavailable",
                    "read_model_stale_reasons": ["relation_facade_unavailable"],
                    "read_model_scope_keys": self._affected_months(month_scope),
                    "refresh_enqueued": False,
                },
            )
        reader = getattr(self._relation_facade, "get_by_row_ids", None)
        if not callable(reader):
            raise WorkbenchRelationCommandError(
                "workbench_relation_read_model_unavailable",
                "Workbench relation read facade does not expose get_by_row_ids.",
                payload={
                    "read_model_status": "unavailable",
                    "read_model_stale_reasons": ["relation_facade_get_by_row_ids_unavailable"],
                    "read_model_scope_keys": self._affected_months(month_scope),
                    "refresh_enqueued": False,
                },
            )
        payload = reader(
            [str(row_id) for row_id in list(row_ids or [])],
            require_fresh=True,
            reason="workbench_relation_write_precondition",
            month_hint=month_scope,
            scope_keys_hint=self._affected_months(month_scope),
        )
        if not isinstance(payload, dict):
            payload = {"status": "unavailable"}
        status = str(payload.get("status") or payload.get("read_model_status") or "missing")
        if status != FRESH_WORKBENCH_RELATION_STATUS:
            raise WorkbenchRelationCommandError(
                "workbench_relation_read_model_not_fresh",
                "Workbench relation read model is not fresh. Refresh and retry the mutation.",
                payload=self._freshness_error_payload(payload, fallback_month_scope=month_scope),
            )
        return payload

    def _freshness_error_payload(self, payload: dict[str, Any], *, fallback_month_scope: str) -> dict[str, Any]:
        status = str(payload.get("status") or payload.get("read_model_status") or "missing")
        stale_reasons = payload.get("stale_reasons")
        if not isinstance(stale_reasons, list):
            stale_reasons = payload.get("read_model_stale_reasons")
        scope_keys = payload.get("read_model_scope_keys")
        if not isinstance(scope_keys, list):
            scope_keys = self._affected_months(fallback_month_scope)
        return {
            "read_model_status": status,
            "read_model_stale_reasons": [
                str(reason)
                for reason in list(stale_reasons or [])
                if str(reason).strip()
            ],
            "read_model_scope_keys": [
                str(scope_key)
                for scope_key in list(scope_keys or [])
                if str(scope_key).strip()
            ],
            "refresh_enqueued": bool(payload.get("refresh_enqueued")),
        }

    def _validated_relation_mode(self, relation_mode: str) -> str:
        mode = str(relation_mode or "").strip()
        if mode not in VALID_WORKBENCH_RELATION_MODES:
            raise WorkbenchRelationCommandError(
                "invalid_workbench_relation_mode",
                f"Unsupported workbench relation mode: {mode or '<empty>'}.",
                payload={"relation_mode": mode},
            )
        return mode

    def _command_result(
        self,
        *,
        status: str,
        relation: dict[str, Any],
        history: dict[str, Any],
        changed_case_ids: list[str],
        affected_months: list[str],
        freshness: dict[str, Any],
        idempotent_replay: bool,
    ) -> dict[str, Any]:
        freshness_payload = self._success_freshness_payload(freshness, fallback_months=affected_months)
        return {
            "status": status,
            "relation": deepcopy(relation),
            "history": deepcopy(history),
            "changed_case_ids": [
                str(case_id)
                for case_id in list(changed_case_ids or [])
                if str(case_id).strip()
            ],
            "affected_months": list(affected_months or []),
            "version": int(relation.get("version") or 1),
            "read_model_status": freshness_payload["read_model_status"],
            "read_model_stale_reasons": freshness_payload["read_model_stale_reasons"],
            "read_model_scope_keys": freshness_payload["read_model_scope_keys"],
            "refresh_enqueued": freshness_payload["refresh_enqueued"],
            "idempotent_replay": idempotent_replay,
        }

    def _success_freshness_payload(self, payload: dict[str, Any], *, fallback_months: list[str]) -> dict[str, Any]:
        scope_keys = payload.get("read_model_scope_keys")
        if not isinstance(scope_keys, list):
            scope_keys = fallback_months
        stale_reasons = payload.get("stale_reasons")
        if not isinstance(stale_reasons, list):
            stale_reasons = payload.get("read_model_stale_reasons")
        return {
            "read_model_status": str(payload.get("status") or payload.get("read_model_status") or FRESH_WORKBENCH_RELATION_STATUS),
            "read_model_stale_reasons": [
                str(reason)
                for reason in list(stale_reasons or [])
                if str(reason).strip()
            ],
            "read_model_scope_keys": [
                str(scope_key)
                for scope_key in list(scope_keys or [])
                if str(scope_key).strip()
            ],
            "refresh_enqueued": bool(payload.get("refresh_enqueued")),
        }

    def _idempotency_replay(self, idempotency_key: str | None, fingerprint: str) -> dict[str, Any] | None:
        key = str(idempotency_key or "").strip()
        if not key:
            return None
        existing = self._idempotency_get(key)
        if not isinstance(existing, dict):
            return None
        if str(existing.get("fingerprint") or "") != fingerprint:
            raise WorkbenchRelationCommandError(
                "workbench_relation_idempotency_conflict",
                "Idempotency key was already used for a different workbench relation command.",
                payload={"idempotency_key": key},
            )
        result = deepcopy(existing.get("result") if isinstance(existing.get("result"), dict) else {})
        if not result:
            return None
        result["idempotent_replay"] = True
        return result

    def _save_idempotency_result(self, idempotency_key: str | None, fingerprint: str, result: dict[str, Any]) -> None:
        key = str(idempotency_key or "").strip()
        if not key:
            return
        self._idempotency_save(key, {"fingerprint": fingerprint, "result": deepcopy(result)})

    def _idempotency_get(self, key: str) -> dict[str, Any] | None:
        getter = getattr(self._idempotency_store, "get", None)
        if callable(getter):
            result = getter(key)
            return deepcopy(result) if isinstance(result, dict) else None
        if isinstance(self._idempotency_store, dict):
            result = self._idempotency_store.get(key)
            return deepcopy(result) if isinstance(result, dict) else None
        return None

    def _idempotency_save(self, key: str, record: dict[str, Any]) -> None:
        saver = getattr(self._idempotency_store, "save", None)
        if callable(saver):
            saver(key, deepcopy(record))
            return
        if isinstance(self._idempotency_store, dict):
            self._idempotency_store[key] = deepcopy(record)

    @staticmethod
    def _request_fingerprint(action: str, payload: dict[str, Any]) -> str:
        return json.dumps(
            {
                "action": action,
                "payload": payload,
            },
            sort_keys=True,
            default=str,
            ensure_ascii=True,
        )

    @staticmethod
    def _affected_months(month_scope: str) -> list[str]:
        normalized = str(month_scope or "").strip()
        if not normalized or normalized == "all":
            return []
        return [normalized[:7]]

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from fin_ops_platform.services.workbench_etc_batch_link import (
    relation_external_etc_batch_id,
    relation_external_etc_batch_ids,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_modes import VALID_WORKBENCH_RELATION_MODES

FRESH_WORKBENCH_RELATION_STATUS = "fresh"
IMMUTABLE_OA_ATTACHMENT_BINDING_MESSAGE = "无法撤回：OA 附件发票必须和来源 OA 保持绑定。"


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


def _oa_attachment_binding_pairs(metadata: dict[str, Any] | None) -> set[tuple[str, str]]:
    pairs: set[tuple[str, str]] = set()
    if not isinstance(metadata, dict):
        return pairs
    for binding in list(metadata.get("oa_attachment_bindings") or []):
        if not isinstance(binding, dict):
            continue
        parent_oa_row_id = str(binding.get("parent_oa_row_id") or "").strip()
        for invoice_row_id in list(binding.get("invoice_row_ids") or []):
            normalized_invoice_row_id = str(invoice_row_id or "").strip()
            if parent_oa_row_id and normalized_invoice_row_id:
                pairs.add((parent_oa_row_id, normalized_invoice_row_id))
    return pairs


def _formal_oa_attachment_metadata(
    *,
    row_ids: list[str],
    row_types: list[str],
    bindings: set[tuple[str, str]],
) -> dict[str, Any]:
    if not bindings:
        return {}
    typed_members = dict(zip(row_ids, row_types, strict=False))
    invalid = [
        (parent_oa_row_id, invoice_row_id)
        for parent_oa_row_id, invoice_row_id in sorted(bindings)
        if typed_members.get(parent_oa_row_id) != "oa"
        or typed_members.get(invoice_row_id) != "invoice"
    ]
    if invalid:
        raise WorkbenchRelationCommandError(
            "invalid_formal_relation_plan",
            "Formal OA attachment bindings must reference typed members of the same plan.",
            payload={"invalid_oa_attachment_bindings": invalid},
        )

    invoice_ids_by_parent: dict[str, list[str]] = {}
    for parent_oa_row_id, invoice_row_id in sorted(bindings):
        invoice_ids_by_parent.setdefault(parent_oa_row_id, []).append(invoice_row_id)
    normalized_bindings = [
        {
            "parent_oa_row_id": parent_oa_row_id,
            "invoice_row_ids": invoice_ids_by_parent[parent_oa_row_id],
        }
        for parent_oa_row_id in sorted(invoice_ids_by_parent)
    ]
    metadata: dict[str, Any] = {
        "contains_immutable_oa_attachment_binding": True,
        "oa_attachment_bindings": normalized_bindings,
    }
    if len(normalized_bindings) == 1:
        binding = normalized_bindings[0]
        binding_row_ids = {
            str(binding["parent_oa_row_id"]),
            *[str(item) for item in binding["invoice_row_ids"]],
        }
        if set(row_ids) == binding_row_ids:
            metadata.update(
                {
                    "source": "oa_attachment_invoice",
                    "immutable_oa_attachment_binding": True,
                    "parent_oa_row_id": binding["parent_oa_row_id"],
                }
            )
    return metadata


@dataclass(frozen=True, slots=True)
class WorkbenchRelationConfirmPreparation:
    owner_token: object
    row_ids: tuple[str, ...]
    row_types: tuple[str, ...]
    tenant_id: str
    month_scope: str
    freshness: dict[str, Any]
    pair_service: WorkbenchPairRelationService
    active_relations: tuple[dict[str, Any], ...]


@dataclass(frozen=True, slots=True)
class WorkbenchRelationWithdrawPreparation:
    owner_token: object
    case_id: str
    pair_service: WorkbenchPairRelationService
    before_relation: dict[str, Any]
    freshness: dict[str, Any]
    current_preview: dict[str, Any]
    row_id_aliases: dict[str, str]


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

    def load_active_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        service = WorkbenchPairRelationService.from_snapshot(self.load_workbench_pair_relations())
        normalized_row_ids = {
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        }
        normalized_case_ids = {
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        }
        relations = {
            str(relation.get("case_id") or "").strip(): relation
            for relation in service.list_active_relations()
            if str(relation.get("case_id") or "").strip() in normalized_case_ids
            or normalized_row_ids.intersection(
                str(row_id).strip()
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            )
        }
        return {"pair_relations": deepcopy(relations)}

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

    def load_active_workbench_pair_relations_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        service = WorkbenchPairRelationService.from_snapshot(self.load_workbench_pair_relations())
        requested = set(zip(row_types, row_ids, strict=True))
        normalized_case_ids = {
            str(case_id).strip()
            for case_id in list(case_ids or [])
            if str(case_id).strip()
        }
        relations: dict[str, dict[str, Any]] = {}
        for relation in service.list_active_relations():
            case_id = str(relation.get("case_id") or "").strip()
            members = set(
                zip(
                    [str(value).strip() for value in list(relation.get("row_types") or [])],
                    [str(value).strip() for value in list(relation.get("row_ids") or [])],
                    strict=True,
                )
            )
            if case_id in normalized_case_ids or requested.intersection(members):
                relations[case_id] = relation
        return {"pair_relations": deepcopy(relations)}

    def save_workbench_pair_relation_delta(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: set[str] | list[str] | None = None,
    ) -> None:
        normalized_case_ids = [
            str(case_id).strip()
            for case_id in list(changed_case_ids or [])
            if str(case_id).strip()
        ]
        service = WorkbenchPairRelationService.from_snapshot(self.load_workbench_pair_relations())
        service.apply_snapshot_delta(
            snapshot,
            changed_case_ids=normalized_case_ids,
            replace_history=False,
        )
        self._save_snapshot(
            service.snapshot(),
            changed_case_ids=normalized_case_ids,
        )

    @staticmethod
    def acquire_relation_member_locks(
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> list[str]:
        _ = case_ids
        normalized_types = [str(item).strip() for item in list(row_types or [])]
        return sorted(
            f"{normalized_types[index] if index < len(normalized_types) else 'unknown'}:{row_id}"
            for index, row_id in enumerate(str(item).strip() for item in list(row_ids or []))
            if row_id
        )


class WorkbenchRelationCommandService:
    def __init__(
        self,
        *,
        relation_repository: Any,
        etc_batch_link_repository: Any | None = None,
        relation_facade: Any | None = None,
        idempotency_store: Any | None = None,
        require_fresh_relations: bool = False,
        tenant_id: str | None = None,
    ) -> None:
        self._relation_repository = relation_repository
        self._etc_batch_link_repository = etc_batch_link_repository
        self._relation_facade = relation_facade
        self._idempotency_store = idempotency_store or _InMemoryIdempotencyStore()
        self._require_fresh_relations = bool(require_fresh_relations)
        self._tenant_id = str(tenant_id or "").strip()
        self._confirm_preparation_owner = object()
        self._withdraw_preparation_owner = object()

    def prepare_confirm_relation(
        self,
        *,
        row_ids: list[str],
        row_types: list[str],
        month_scope: str = "all",
        scope_keys_hint: list[str] | None = None,
        tenant_id: str | None = None,
    ) -> WorkbenchRelationConfirmPreparation:
        normalized_row_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        normalized_row_types = [str(row_type).strip() for row_type in list(row_types or [])]
        freshness = self._assert_relation_read_model_fresh(
            row_ids=normalized_row_ids,
            month_scope=month_scope,
            scope_keys_hint=scope_keys_hint,
        )
        self._assert_canonical_relation_members_available(
            normalized_row_ids,
            row_types=normalized_row_types,
            tenant_id=tenant_id,
        )
        self._acquire_relation_member_locks(
            normalized_row_ids,
            row_types=normalized_row_types,
        )
        pair_service = self._active_pair_service_for_typed_rows(
            normalized_row_ids,
            normalized_row_types,
        )
        active_relations = pair_service.active_relations_for_typed_rows(
            normalized_row_ids,
            normalized_row_types,
        )
        return WorkbenchRelationConfirmPreparation(
            owner_token=self._confirm_preparation_owner,
            row_ids=tuple(normalized_row_ids),
            row_types=tuple(normalized_row_types),
            tenant_id=self._canonical_tenant_id(tenant_id),
            month_scope=str(month_scope or "all").strip() or "all",
            freshness=deepcopy(freshness),
            pair_service=pair_service,
            active_relations=tuple(deepcopy(active_relations)),
        )

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
        preparation: WorkbenchRelationConfirmPreparation | None = None,
        request_id: str | None = None,
        tenant_id: str | None = None,
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
                "tenant_id": self._canonical_tenant_id(tenant_id),
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        if preparation is None:
            freshness = self._assert_relation_read_model_fresh(
                row_ids=list(row_ids or []),
                month_scope=month_scope,
            )
            self._assert_canonical_relation_members_available(
                list(row_ids or []),
                row_types=list(row_types or []),
                tenant_id=tenant_id,
            )
            self._acquire_relation_member_locks(
                list(row_ids or []),
                row_types=list(row_types or []),
                case_ids=[case_id],
            )
            pair_service = self._active_pair_service_for_typed_rows(
                list(row_ids or []),
                list(row_types or []),
                case_ids=[case_id],
            )
        else:
            requested_row_ids = list(row_ids or [])
            requested_row_types = list(row_types or [])
            self._validate_confirm_preparation(
                preparation,
                row_ids=requested_row_ids,
                row_types=requested_row_types,
                month_scope=month_scope,
                tenant_id=tenant_id,
            )
            freshness = deepcopy(preparation.freshness)
            pair_service = preparation.pair_service
            prepared_members = set(zip(preparation.row_ids, preparation.row_types, strict=False))
            additional_row_ids: list[str] = []
            additional_row_types: list[str] = []
            for index, row_id in enumerate(requested_row_ids):
                row_type = str(requested_row_types[index] if index < len(requested_row_types) else "").strip()
                member = (str(row_id).strip(), row_type)
                if member in prepared_members:
                    continue
                additional_row_ids.append(member[0])
                additional_row_types.append(member[1])
            self._assert_canonical_relation_members_available(
                additional_row_ids,
                row_types=additional_row_types,
                tenant_id=tenant_id,
            )
            self._acquire_relation_member_locks(
                additional_row_ids,
                row_types=additional_row_types,
                case_ids=[case_id],
            )
        active_relations = pair_service.active_relations_for_typed_rows(
            list(row_ids or []),
            list(row_types or []),
        )
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
        if request_id:
            history = {
                **history,
                "request_id": str(request_id or "").strip(),
            }
        changed_case_ids = self._changed_case_ids(
            [
                *active_relations,
                *list(before_relations or []),
                relation,
            ]
        )
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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

    def prepare_withdraw_relation(
        self,
        *,
        case_id: str,
        row_id_aliases: dict[str, str] | None = None,
    ) -> WorkbenchRelationWithdrawPreparation:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id},
            )
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
        pair_service, before_relation, current_preview = self._lock_and_revalidate_withdraw_topology(
            pair_service=pair_service,
            before_relation=before_relation,
            freshness=freshness,
            row_id_aliases=row_id_aliases,
        )
        return WorkbenchRelationWithdrawPreparation(
            owner_token=self._withdraw_preparation_owner,
            case_id=resolved_case_id,
            pair_service=pair_service,
            before_relation=deepcopy(before_relation),
            freshness=deepcopy(freshness),
            current_preview=deepcopy(current_preview),
            row_id_aliases=dict(row_id_aliases or {}),
        )

    def confirm_formal_relation_plans(
        self,
        plans: list[Any],
        *,
        actor_id: str,
        etc_batch_links: list[dict[str, Any]] | None = None,
        paired_requirements_by_case_id: dict[str, dict[str, object]] | None = None,
        tenant_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_plans = [plan for plan in list(plans or []) if plan is not None]
        normalized_links = self._normalize_etc_batch_links(etc_batch_links or [])
        if not normalized_plans:
            return {
                "status": "noop",
                "relations": [],
                "histories": [],
                "changed_case_ids": [],
                "affected_months": [],
                "enriched_relation_count": 0,
            }
        row_ids = [
            str(row_id)
            for plan in normalized_plans
            for row_id in tuple(getattr(plan, "row_ids", ()) or ())
        ]
        row_types = [
            str(row_type)
            for plan in normalized_plans
            for row_type in tuple(getattr(plan, "row_types", ()) or ())
        ]
        case_ids = [str(getattr(plan, "case_id", "") or "") for plan in normalized_plans]
        if len(row_ids) != len(row_types) or any(not item for item in (*row_ids, *row_types, *case_ids)):
            raise WorkbenchRelationCommandError(
                "invalid_formal_relation_plan",
                "Formal relation plans require aligned row ids, row types and case ids.",
            )
        links_by_case = {str(link["case_id"]): link for link in normalized_links}
        requirements_by_case = {
            str(case_id): dict(metadata)
            for case_id, metadata in dict(paired_requirements_by_case_id or {}).items()
        }
        if set(links_by_case) - set(case_ids):
            raise WorkbenchRelationCommandError(
                "etc_batch_link_plan_mismatch",
                "ETC batch link targets must belong to the formal relation plan batch.",
            )
        if set(requirements_by_case) - set(case_ids):
            raise WorkbenchRelationCommandError(
                "paired_requirement_plan_mismatch",
                "Paired requirements must belong to the formal relation plan batch.",
            )
        self._assert_canonical_relation_members_available(
            row_ids,
            row_types=row_types,
            tenant_id=tenant_id,
        )
        self._acquire_relation_member_locks(row_ids, row_types=row_types, case_ids=case_ids)
        self._validate_etc_batch_links(normalized_links)
        pair_service = self._pair_service_for_row_ids(row_ids, case_ids=case_ids)
        relations: list[dict[str, Any]] = []
        histories: list[dict[str, Any]] = []
        changed_case_ids: set[str] = set()
        affected_months: set[str] = set()
        for plan in sorted(normalized_plans, key=lambda item: str(getattr(item, "relation_fingerprint", ""))):
            plan_row_ids = [str(item) for item in tuple(getattr(plan, "row_ids", ()) or ())]
            plan_row_types = [str(item) for item in tuple(getattr(plan, "row_types", ()) or ())]
            case_id = str(getattr(plan, "case_id", "") or "")
            target_case_id = str(getattr(plan, "target_case_id", "") or "")
            active_relations = pair_service.active_relations_for_row_ids(plan_row_ids)
            conflicts = [
                relation
                for relation in active_relations
                if str(relation.get("case_id") or "") != target_case_id
            ]
            if conflicts:
                raise WorkbenchRelationCommandError(
                    "workbench_relation_active_row_conflict",
                    "One or more formal plan members are already active in another Workbench relation.",
                    payload={
                        "case_id": case_id,
                        "conflicting_case_ids": sorted(
                            str(relation.get("case_id") or "")
                            for relation in conflicts
                            if str(relation.get("case_id") or "")
                        ),
                    },
                )
            scope_keys = [
                str(item)
                for item in tuple(getattr(plan, "scope_keys", ()) or ())
                if str(item) and str(item) != "all"
            ]
            month_scope = scope_keys[0] if len(scope_keys) == 1 else "all"
            amount_minor = int(getattr(plan, "amount_minor", 0) or 0)
            amount_check = {
                "status": "matched" if amount_minor else "explicit_reference",
                "amount_minor": amount_minor,
                "currency": str(getattr(plan, "currency", "CNY") or "CNY"),
            }
            evidence = dict(tuple(getattr(plan, "evidence_summary", ()) or ()))
            relation_mode = str(getattr(plan, "relation_mode", "manual_confirmed") or "").strip()
            if relation_mode not in VALID_WORKBENCH_RELATION_MODES:
                raise WorkbenchRelationCommandError(
                    "invalid_formal_relation_mode",
                    "Formal relation plan uses an unsupported relation mode.",
                    payload={"case_id": case_id, "relation_mode": relation_mode},
                )
            attachment_bindings = {
                (str(parent_oa_row_id), str(invoice_row_id))
                for parent_oa_row_id, invoice_row_id in tuple(
                    getattr(plan, "oa_attachment_bindings", ()) or ()
                )
                if str(parent_oa_row_id).strip() and str(invoice_row_id).strip()
            }
            special_metadata = {
                "formal_relation": {
                    "origin": "system_deterministic",
                    "relation_fingerprint": str(getattr(plan, "relation_fingerprint", "") or ""),
                    "batch_hash": str(getattr(plan, "batch_hash", "") or ""),
                    "rule_code": str(getattr(plan, "rule_code", "") or ""),
                    "rule_version": str(getattr(plan, "rule_version", "") or ""),
                }
            }
            if relation_mode == "output_invoice_reversal":
                special_metadata["output_invoice_reversal"] = {
                    "blue_invoice_identity": evidence.get("blue_invoice_identity", ""),
                    "red_invoice_identity": evidence.get("red_invoice_identity", ""),
                    "match_rule": "seller_buyer_currency_gross_net_tax_rate_exact",
                }
            special_metadata.update(
                _formal_oa_attachment_metadata(
                    row_ids=plan_row_ids,
                    row_types=plan_row_types,
                    bindings=attachment_bindings,
                )
            )
            special_metadata.update(requirements_by_case.get(case_id, {}))
            etc_batch_link = links_by_case.get(case_id)
            if etc_batch_link is not None:
                if (str(etc_batch_link["oa_row_id"]), "oa") not in set(
                    zip(plan_row_ids, plan_row_types, strict=False)
                ):
                    raise WorkbenchRelationCommandError(
                        "etc_batch_link_oa_relation_mismatch",
                        "The exact ETC OA row is not a typed OA member of the formal relation plan.",
                        payload={"case_id": case_id, "oa_row_id": etc_batch_link["oa_row_id"]},
                    )
                special_metadata["etc_batch_link"] = self._desired_etc_batch_link(etc_batch_link)
            if target_case_id:
                before_relation = pair_service.get_active_relation_by_case_id(target_case_id)
                if not isinstance(before_relation, dict):
                    raise WorkbenchRelationCommandError(
                        "workbench_relation_extension_target_missing",
                        "The active relation targeted by an explicit reference extension no longer exists.",
                        payload={"case_id": target_case_id},
                    )
                if not set(before_relation.get("row_ids") or []).issubset(plan_row_ids):
                    raise WorkbenchRelationCommandError(
                        "workbench_relation_extension_members_changed",
                        "The active relation targeted by an explicit reference extension changed members.",
                        payload={"case_id": target_case_id},
                    )
                before_metadata = (
                    before_relation.get("special_metadata")
                    if isinstance(before_relation.get("special_metadata"), dict)
                    else {}
                )
                attachment_bindings.update(
                    _oa_attachment_binding_pairs(before_metadata)
                )
                special_metadata.update(
                    _formal_oa_attachment_metadata(
                        row_ids=plan_row_ids,
                        row_types=plan_row_types,
                        bindings=attachment_bindings,
                    )
                )
                relation, history = pair_service.replace_with_confirmed_relation(
                    case_id=target_case_id,
                    row_ids=plan_row_ids,
                    row_types=plan_row_types,
                    relation_mode=relation_mode,
                    created_by=actor_id,
                    month_scope=month_scope,
                    note="系统确定性配对扩展",
                    amount_check=amount_check,
                    special_metadata=special_metadata,
                    operation_type="confirm_link",
                    history_created_by=actor_id,
                    history_note="系统确定性配对扩展",
                    rule_version=str(getattr(plan, "rule_version", "") or ""),
                    evidence=evidence,
                    before_relations=[before_relation],
                )
            else:
                relation = pair_service.create_active_relation(
                    case_id=case_id,
                    row_ids=plan_row_ids,
                    row_types=plan_row_types,
                    relation_mode=relation_mode,
                    created_by=actor_id,
                    month_scope=month_scope,
                    note="系统确定性配对",
                    amount_check=amount_check,
                    special_metadata=special_metadata,
                    rule_version=str(getattr(plan, "rule_version", "") or ""),
                    evidence=evidence,
                )
                history = pair_service.record_history(
                    operation_type="confirm_link",
                    before_relations=[],
                    after_relations=[relation],
                    affected_row_ids=plan_row_ids,
                    created_by=actor_id,
                    note="系统确定性配对",
                    amount_check=amount_check,
                )
            relations.append(relation)
            histories.append(history)
            changed_case_ids.add(case_id)
            affected_months.update(scope_keys)
        self._save_changed_cases(
            pair_service,
            sorted(changed_case_ids),
            history_events=histories,
        )
        return {
            "status": "confirmed",
            "relations": relations,
            "histories": histories,
            "changed_case_ids": sorted(changed_case_ids),
            "affected_months": sorted(affected_months),
            "enriched_relation_count": len(normalized_links),
        }

    def enrich_etc_batch_links(
        self,
        links: list[dict[str, Any]],
        *,
        actor_id: str,
    ) -> dict[str, Any]:
        normalized = self._normalize_etc_batch_links(links)
        if not normalized:
            return {
                "status": "noop",
                "relations": [],
                "histories": [],
                "changed_case_ids": [],
                "affected_months": [],
                "updated_count": 0,
            }

        ordered_case_ids = sorted(str(item["case_id"]) for item in normalized)
        self._acquire_relation_member_locks([], case_ids=ordered_case_ids)
        self._validate_etc_batch_links(normalized)
        pair_service = self._pair_service_for_case_ids(ordered_case_ids)
        relations: list[dict[str, Any]] = []
        histories: list[dict[str, Any]] = []
        affected_months: set[str] = set()
        for item in sorted(normalized, key=lambda value: str(value["case_id"])):
            case_id = str(item["case_id"])
            active_relation = pair_service.get_active_relation_by_case_id(case_id)
            if not isinstance(active_relation, dict):
                raise WorkbenchRelationCommandError(
                    "workbench_relation_not_found",
                    "Workbench relation is not active or does not exist.",
                    payload={"case_id": case_id},
                )
            typed_members = set(
                zip(
                    (str(row_id).strip() for row_id in list(active_relation.get("row_ids") or [])),
                    (str(row_type).strip() for row_type in list(active_relation.get("row_types") or [])),
                    strict=False,
                )
            )
            if (str(item["oa_row_id"]), "oa") not in typed_members:
                raise WorkbenchRelationCommandError(
                    "etc_batch_link_oa_relation_mismatch",
                    "The exact ETC OA row does not belong to the target Workbench relation.",
                    payload={"case_id": case_id, "oa_row_id": item["oa_row_id"]},
                )
            current_external_batch_id = relation_external_etc_batch_id(active_relation)
            current_external_batch_ids = relation_external_etc_batch_ids(active_relation)
            if len(current_external_batch_ids) > 1:
                raise WorkbenchRelationCommandError(
                    "etc_batch_link_marker_conflict",
                    "The Workbench relation contains conflicting ETC batch owner markers.",
                    payload={"case_id": case_id, "external_etc_batch_ids": sorted(current_external_batch_ids)},
                )
            if current_external_batch_id and current_external_batch_id != item["external_etc_batch_id"]:
                raise WorkbenchRelationCommandError(
                    "etc_batch_link_owner_conflict",
                    "The Workbench relation already belongs to another ETC batch.",
                    payload={
                        "case_id": case_id,
                        "current_external_etc_batch_id": current_external_batch_id,
                        "requested_external_etc_batch_id": item["external_etc_batch_id"],
                    },
                )
            desired_link = self._desired_etc_batch_link(item)
            current_metadata = active_relation.get("special_metadata")
            current_link = (
                current_metadata.get("etc_batch_link")
                if isinstance(current_metadata, dict)
                else None
            )
            if current_link == desired_link:
                continue
            relation, history = pair_service.update_relation_metadata_for_case_id(
                case_id,
                special_metadata={"etc_batch_link": desired_link},
                display_tags=["ETC发票已关联"],
                updated_by=actor_id,
                note="系统按 OA 精确 ETC 批次标识补全正式关系归属。",
                operation_type="link_etc_business_batch",
            )
            relations.append(relation)
            histories.append(history)
            affected_months.update(
                scope
                for scope in list(item.get("scope_keys") or [])
                if scope != "all"
            )
        changed_case_ids = [str(relation.get("case_id") or "") for relation in relations]
        if changed_case_ids:
            self._save_changed_cases(
                pair_service,
                changed_case_ids,
                history_events=histories,
            )
        return {
            "status": "updated" if relations else "noop",
            "relations": relations,
            "histories": histories,
            "changed_case_ids": changed_case_ids,
            "affected_months": sorted(affected_months),
            "updated_count": len(relations),
        }

    @staticmethod
    def _normalize_etc_batch_links(links: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        case_ids: set[str] = set()
        external_batch_ids: set[str] = set()
        for raw in list(links or []):
            if not isinstance(raw, dict):
                raise WorkbenchRelationCommandError(
                    "invalid_etc_batch_link",
                    "ETC batch link enrichment entries must be objects.",
                )
            case_id = str(raw.get("case_id") or "").strip()
            external_batch_id = str(raw.get("external_etc_batch_id") or "").strip()
            business_batch_id = str(raw.get("business_batch_id") or "").strip()
            oa_row_id = str(raw.get("oa_row_id") or "").strip()
            if not case_id or not external_batch_id or not business_batch_id or not oa_row_id:
                raise WorkbenchRelationCommandError(
                    "invalid_etc_batch_link",
                    "ETC batch link enrichment requires case, OA row, business batch and external batch ids.",
                )
            if case_id in case_ids or external_batch_id in external_batch_ids:
                raise WorkbenchRelationCommandError(
                    "ambiguous_etc_batch_link",
                    "One ETC batch and one Workbench relation must have exactly one enrichment owner.",
                    payload={"case_id": case_id, "external_etc_batch_id": external_batch_id},
                )
            case_ids.add(case_id)
            external_batch_ids.add(external_batch_id)
            normalized.append(
                {
                    "case_id": case_id,
                    "oa_row_id": oa_row_id,
                    "business_batch_id": business_batch_id,
                    "external_etc_batch_id": external_batch_id,
                    "submission_batch_id": str(raw.get("submission_batch_id") or "").strip(),
                    "invoice_count": int(raw.get("invoice_count") or 0),
                    "total_amount": str(raw.get("total_amount") or "0"),
                    "scope_keys": [
                        str(scope).strip()
                        for scope in list(raw.get("scope_keys") or [])
                        if str(scope).strip()
                    ],
                }
            )
        return normalized

    def _validate_etc_batch_links(self, links: list[dict[str, Any]]) -> None:
        if not links:
            return
        validator = getattr(self._etc_batch_link_repository, "validate_etc_batch_links", None)
        if not callable(validator):
            raise WorkbenchRelationCommandError(
                "etc_batch_link_validation_unavailable",
                "ETC batch link enrichment requires the transactional canonical validation boundary.",
            )
        validation = validator(links)
        if not isinstance(validation, dict) or not bool(validation.get("valid")):
            raise WorkbenchRelationCommandError(
                "etc_batch_link_validation_conflict",
                "The canonical OA, ETC batch, or active relation owner changed before enrichment.",
                payload={"issues": list((validation or {}).get("issues") or [])},
            )

    @staticmethod
    def _desired_etc_batch_link(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "source": "workbench_deterministic_etc_enrichment",
            "external_etc_batch_id": item["external_etc_batch_id"],
            "business_batch_id": item["business_batch_id"],
            "submission_batch_id": item["submission_batch_id"],
            "oa_row_id": item["oa_row_id"],
            "invoice_count": item["invoice_count"],
            "total_amount": item["total_amount"],
        }

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

        self._acquire_relation_member_locks([], case_ids=[resolved_case_id])
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
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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

        self._acquire_relation_member_locks(normalized_row_ids)
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
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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

    def remove_rows_from_active_relations(
        self,
        *,
        row_ids: list[str],
        actor_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Remove unavailable canonical facts without leaving a half-valid active relation."""

        removed_row_ids = {
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        }
        if not removed_row_ids:
            return {"changed_case_ids": [], "affected_months": []}
        self._acquire_relation_member_locks(sorted(removed_row_ids))
        pair_service = self._pair_service_for_row_ids(sorted(removed_row_ids))
        before_relations = pair_service.active_relations_for_row_ids(sorted(removed_row_ids))
        histories: list[dict[str, Any]] = []
        changed_case_ids: list[str] = []
        for before in before_relations:
            case_id = str(before.get("case_id") or "").strip()
            metadata = before.get("special_metadata")
            binding_parents = {
                str(binding.get("parent_oa_row_id") or "").strip()
                for binding in list((metadata or {}).get("oa_attachment_bindings") or [])
                if isinstance(binding, dict)
            }
            members = [
                (str(row_id).strip(), str(row_type).strip())
                for row_id, row_type in zip(
                    list(before.get("row_ids") or []),
                    list(before.get("row_types") or []),
                    strict=False,
                )
                if str(row_id).strip() and str(row_id).strip() not in removed_row_ids
            ]
            if len(members) >= 2 and not binding_parents.intersection(removed_row_ids):
                _, history = pair_service.replace_with_confirmed_relation(
                    case_id=case_id,
                    row_ids=[row_id for row_id, _ in members],
                    row_types=[row_type for _, row_type in members],
                    relation_mode=str(before.get("relation_mode") or "manual_confirmed"),
                    created_by=str(before.get("created_by") or actor_id),
                    month_scope=str(before.get("month_scope") or "all"),
                    note=str(before.get("note") or "") or None,
                    amount_check=(
                        dict(before.get("amount_check") or {})
                        if isinstance(before.get("amount_check"), dict)
                        else None
                    ),
                    special_metadata=(dict(metadata) if isinstance(metadata, dict) else None),
                    before_relations=[before],
                    operation_type="remove_unavailable_oa_fact",
                    history_created_by=actor_id,
                    history_note=reason,
                )
            else:
                pair_service.cancel_relation(case_id)
                history = pair_service.record_history(
                    operation_type="cancel_relation_for_unavailable_oa_fact",
                    before_relations=[before],
                    after_relations=[],
                    affected_row_ids=list(before.get("row_ids") or []),
                    created_by=actor_id,
                    note=reason,
                    amount_check=(
                        dict(before.get("amount_check") or {})
                        if isinstance(before.get("amount_check"), dict)
                        else None
                    ),
                )
            histories.append(history)
            changed_case_ids.append(case_id)
        if changed_case_ids:
            self._save_changed_cases(
                pair_service,
                changed_case_ids,
                history_events=histories,
            )
        return {
            "changed_case_ids": changed_case_ids,
            "affected_months": self._affected_months_for_relations(before_relations),
        }

    def cancel_relations_by_case_ids(
        self,
        *,
        case_ids: list[str],
        actor_id: str,
        reason: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "cancel_relations",
    ) -> dict[str, Any]:
        normalized_case_ids = list(
            dict.fromkeys(
                str(case_id).strip()
                for case_id in list(case_ids or [])
                if str(case_id).strip()
            )
        )
        fingerprint = self._request_fingerprint(
            "cancel_relations_by_case_ids",
            {
                "case_ids": normalized_case_ids,
                "actor_id": actor_id,
                "reason": reason,
                "history_operation_type": history_operation_type,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay
        if not normalized_case_ids:
            return {
                "status": "noop",
                "relations": [],
                "history": None,
                "changed_case_ids": [],
                "affected_months": [],
                "idempotent_replay": False,
            }

        self._acquire_relation_member_locks([], case_ids=normalized_case_ids)
        pair_service = self._pair_service_for_case_ids(normalized_case_ids)
        before_relations = [
            relation
            for case_id in normalized_case_ids
            for relation in [pair_service.get_active_relation_by_case_id(case_id)]
            if isinstance(relation, dict)
        ]
        all_row_ids = list(
            dict.fromkeys(
                str(row_id).strip()
                for relation in before_relations
                for row_id in list(relation.get("row_ids") or [])
                if str(row_id).strip()
            )
        )
        freshness = self._assert_relation_read_model_fresh(
            row_ids=all_row_ids,
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

        cancelled_relations = [
            cancelled
            for relation in before_relations
            for cancelled in [pair_service.cancel_relation(str(relation.get("case_id") or ""), cancelled_at=occurred_at)]
            if isinstance(cancelled, dict)
        ]
        history = pair_service.record_history(
            operation_type=history_operation_type,
            before_relations=before_relations,
            after_relations=[],
            affected_row_ids=all_row_ids,
            created_by=actor_id,
            note=reason,
            created_at=occurred_at,
        )
        changed_case_ids = self._changed_case_ids(before_relations)
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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
        replace_special_metadata: bool = False,
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
                "replace_special_metadata": bool(replace_special_metadata),
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
            replace_special_metadata=replace_special_metadata,
            display_tags=display_tags,
            updated_by=actor_id,
            note=note,
            updated_at=occurred_at,
            operation_type=history_operation_type,
        )
        changed_case_ids = [resolved_case_id]
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any]:
        return self._assert_relation_read_model_fresh(
            row_ids=list(row_ids or []),
            month_scope=month_scope,
            scope_keys_hint=scope_keys_hint,
        )

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        normalized_row_ids = list(row_ids or [])
        return self._active_pair_service_for_row_ids(
            normalized_row_ids
        ).active_relations_for_row_ids(normalized_row_ids)

    def active_relations_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
    ) -> list[dict[str, Any]]:
        if len(row_ids) != len(row_types):
            raise ValueError("row_types must align with row_ids.")
        pair_service = self._active_pair_service_for_typed_rows(
            list(row_ids or []),
            list(row_types or []),
        )
        return list(
            pair_service.active_relations_for_typed_rows(
                list(row_ids or []),
                list(row_types or []),
            )
            or []
        )

    def list_active_relations(self) -> list[dict[str, Any]]:
        return self._pair_service().list_active_relations()

    def get_active_relation_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        relation = self._pair_service_for_row_ids([str(row_id or "")]).get_active_relation_by_row_id(str(row_id or ""))
        return deepcopy(relation) if isinstance(relation, dict) else None

    def list_history(self) -> list[dict[str, Any]]:
        return self._pair_service().list_history()

    def get_active_relation_by_case_id(self, case_id: str) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        loader = getattr(self._relation_repository, "load_active_workbench_pair_relation_by_case_id", None)
        relation = (
            loader(resolved_case_id)
            if callable(loader)
            else self._pair_service_for_case_ids([resolved_case_id]).get_active_relation_by_case_id(resolved_case_id)
        )
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
        row_types: list[str] | None = None,
        month_scope: str = "all",
        row_id_aliases: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        pair_service = self._pair_service_for_row_ids(list(row_ids or []))
        return self._preview_withdraw_relation_from_pair_service(
            pair_service,
            row_ids=list(row_ids or []),
            row_types=None if row_types is None else list(row_types),
            month_scope=month_scope,
            row_id_aliases=row_id_aliases,
        )

    def _preview_withdraw_relation_from_pair_service(
        self,
        pair_service: WorkbenchPairRelationService,
        *,
        row_ids: list[str],
        row_types: list[str] | None = None,
        month_scope: str = "all",
        freshness: dict[str, Any] | None = None,
        row_id_aliases: dict[str, str] | None = None,
        active_relation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(active_relation, dict):
            if row_types is not None:
                active_relations = pair_service.active_relations_for_typed_rows(
                    list(row_ids or []),
                    list(row_types or []),
                )
            else:
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
        self._assert_exact_withdraw_selection(
            row_ids,
            row_types=row_types,
            active_relation=active_relation,
            row_id_aliases=row_id_aliases,
        )
        active_row_ids = [
            str(row_id)
            for row_id in list(active_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        resolved_month_scope = str(active_relation.get("month_scope") or month_scope or "all")
        if pair_service.is_immutable_oa_attachment_binding_relation(
            active_relation,
            row_id_aliases=row_id_aliases,
        ):
            expected_versions = self._withdraw_expected_versions(active_relation)
            after_relations = [deepcopy(active_relation)]
            preview_id = self._withdraw_preview_id(
                operation_type="withdraw_relation",
                active_relation=active_relation,
                after_relations=after_relations,
                confirm_history=None,
            )
            return {
                "operation": "withdraw_link",
                "operation_type": "withdraw_relation",
                "preview_id": preview_id,
                "can_submit": False,
                "requires_note": False,
                "message": IMMUTABLE_OA_ATTACHMENT_BINDING_MESSAGE,
                "active_relation": self._relation_identity(active_relation),
                "before_relations": [deepcopy(active_relation)],
                "after_relations": after_relations,
                "submit_expected_versions": expected_versions,
            }
        resolved_freshness = freshness or self._assert_relation_read_model_fresh(
            row_ids=active_row_ids,
            month_scope=resolved_month_scope,
        )
        try:
            preview = pair_service.preview_withdraw_for_active_relation(
                active_relation,
                row_id_aliases=row_id_aliases,
            )
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
            confirm_history=(
                dict(preview.get("confirm_history") or {})
                if isinstance(preview.get("confirm_history"), dict)
                else None
            ),
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
        }

    def withdraw_relation(
        self,
        *,
        case_id: str,
        actor_id: str,
        row_ids: list[str] | None = None,
        row_types: list[str] | None = None,
        reason: str | None = None,
        occurred_at: str | None = None,
        idempotency_key: str | None = None,
        history_operation_type: str = "withdraw_link",
        preview_id: str | None = None,
        operation_type: str | None = None,
        expected_versions: dict[str, Any] | None = None,
        row_id_aliases: dict[str, str] | None = None,
        preparation: WorkbenchRelationWithdrawPreparation | None = None,
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        resolved_operation_type = str(operation_type or "withdraw_relation").strip()
        if resolved_operation_type != "withdraw_relation":
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation submit operation_type does not match the preview.",
                payload={"operation_type": resolved_operation_type},
            )
        selected_row_ids = [
            str(row_id).strip()
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        selected_row_types = [str(row_type).strip() for row_type in list(row_types or [])]
        if row_types is not None and len(selected_row_ids) != len(selected_row_types):
            raise ValueError("row_types must align with row_ids.")
        fingerprint = self._request_fingerprint(
            "withdraw_relation",
            {
                "case_id": resolved_case_id,
                "row_ids": selected_row_ids,
                "row_types": selected_row_types,
                "actor_id": actor_id,
                "reason": reason,
                "history_operation_type": history_operation_type,
                "preview_id": preview_id,
                "operation_type": resolved_operation_type,
                "expected_versions": expected_versions,
                "row_id_aliases": row_id_aliases,
            },
        )
        replay = self._idempotency_replay(idempotency_key, fingerprint)
        if replay is not None:
            return replay

        if preparation is not None:
            self._validate_withdraw_preparation(
                preparation,
                case_id=resolved_case_id,
                row_ids=selected_row_ids,
                row_id_aliases=row_id_aliases,
            )
            resolved_case_id = preparation.case_id
            pair_service = preparation.pair_service
            before_relation = deepcopy(preparation.before_relation)
            freshness = deepcopy(preparation.freshness)
            current_preview = deepcopy(preparation.current_preview)
        else:
            if resolved_case_id:
                pair_service = self._pair_service_for_case_ids([resolved_case_id])
                before_relation = pair_service.get_active_relation_by_case_id(resolved_case_id)
            else:
                pair_service = self._pair_service_for_row_ids(selected_row_ids)
                if row_types is not None:
                    active_relations = pair_service.active_relations_for_typed_rows(
                        selected_row_ids,
                        selected_row_types,
                    )
                else:
                    active_relations = pair_service.active_relations_for_row_ids(selected_row_ids)
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
                before_relation = active_relations[0] if active_relations else None
                resolved_case_id = str((before_relation or {}).get("case_id") or "").strip()
        if not isinstance(before_relation, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_not_found",
                "Workbench relation is not active or does not exist.",
                payload={"case_id": resolved_case_id, "row_ids": selected_row_ids},
            )
        before_row_ids = [
            str(row_id)
            for row_id in list(before_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        if row_ids is not None:
            self._assert_exact_withdraw_selection(
                selected_row_ids,
                row_types=selected_row_types if row_types is not None else None,
                active_relation=before_relation,
                row_id_aliases=row_id_aliases,
            )
        before_month_scope = str(before_relation.get("month_scope") or "all")
        if pair_service.is_immutable_oa_attachment_binding_relation(
            before_relation,
            row_id_aliases=row_id_aliases,
        ):
            raise WorkbenchRelationCommandError(
                "workbench_relation_immutable_oa_attachment_binding",
                IMMUTABLE_OA_ATTACHMENT_BINDING_MESSAGE,
                payload={"case_id": resolved_case_id, "row_ids": before_row_ids},
            )
        if preparation is None:
            freshness = self._assert_relation_read_model_fresh(
                row_ids=before_row_ids,
                month_scope=before_month_scope,
            )
            pair_service, before_relation, current_preview = self._lock_and_revalidate_withdraw_topology(
                pair_service=pair_service,
                before_relation=before_relation,
                freshness=freshness,
                row_id_aliases=row_id_aliases,
            )
        before_row_ids = [
            str(row_id)
            for row_id in list(before_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        self._assert_withdraw_preview_lock(
            preview=current_preview,
            preview_id=preview_id,
            expected_versions=expected_versions,
        )
        restored_relations, history = pair_service.withdraw_latest_for_active_relation(
            before_relation,
            created_by=actor_id,
            note=reason,
            created_at=occurred_at,
            row_id_aliases=row_id_aliases,
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
            self._changed_case_ids([before_relation, *restored_relations]),
            include_history=False,
        )
        relation = deepcopy(snapshot.get("pair_relations", {}).get(resolved_case_id, before_relation))
        changed_case_ids = self._changed_case_ids([relation, *restored_relations])
        self._save_changed_cases(pair_service, changed_case_ids, history_events=[history])
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
            "before_relation": deepcopy(before_relation),
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
        confirm_history: dict[str, Any] | None = None,
    ) -> str:
        payload = {
            "operation_type": operation_type,
            "active_relation": cls._relation_topology_identity(active_relation),
            "after_relations": sorted(
                [
                    cls._relation_topology_identity(relation)
                    for relation in list(after_relations or [])
                    if isinstance(relation, dict)
                ],
                key=lambda relation: str(relation.get("case_id") or ""),
            ),
            "confirm_history": (
                {
                    "operation_id": str(confirm_history.get("operation_id") or ""),
                    "operation_type": str(confirm_history.get("operation_type") or ""),
                    "created_at": str(confirm_history.get("created_at") or ""),
                }
                if isinstance(confirm_history, dict)
                else None
            ),
        }
        digest = sha256(
            json.dumps(payload, sort_keys=True, default=str, ensure_ascii=True).encode("utf-8")
        ).hexdigest()[:24]
        return f"{operation_type}:{digest}"

    @classmethod
    def _relation_topology_identity(cls, relation: dict[str, Any]) -> dict[str, Any]:
        identity = cls._relation_identity(relation)
        row_ids = list(relation.get("row_ids") or [])
        row_types = list(relation.get("row_types") or [])
        return {
            **identity,
            "status": str(relation.get("status") or ""),
            "members": sorted(
                [
                    {
                        "row_id": str(row_id).strip(),
                        "row_type": str(row_types[index] if index < len(row_types) else "").strip(),
                    }
                    for index, row_id in enumerate(row_ids)
                    if str(row_id).strip()
                ],
                key=lambda member: (member["row_type"], member["row_id"]),
            ),
        }

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

    def _validate_confirm_preparation(
        self,
        preparation: WorkbenchRelationConfirmPreparation,
        *,
        row_ids: list[str],
        row_types: list[str],
        month_scope: str,
        tenant_id: str | None,
    ) -> None:
        normalized_month_scope = str(month_scope or "all").strip() or "all"
        prepared_members = set(zip(preparation.row_ids, preparation.row_types, strict=False))
        requested_members = {
            (
                str(row_id).strip(),
                str(row_types[index] if index < len(row_types) else "").strip(),
            )
            for index, row_id in enumerate(list(row_ids or []))
            if str(row_id).strip()
        }
        allowed_members = set(prepared_members)
        for relation in preparation.active_relations:
            relation_row_ids = list(relation.get("row_ids") or [])
            relation_row_types = list(relation.get("row_types") or [])
            allowed_members.update(
                (
                    str(row_id).strip(),
                    str(relation_row_types[index] if index < len(relation_row_types) else "").strip(),
                )
                for index, row_id in enumerate(relation_row_ids)
                if str(row_id).strip()
            )
        if (
            preparation.owner_token is not self._confirm_preparation_owner
            or preparation.tenant_id != self._canonical_tenant_id(tenant_id)
            or preparation.month_scope != normalized_month_scope
            or not prepared_members.issubset(requested_members)
            or not requested_members.issubset(allowed_members)
        ):
            raise WorkbenchRelationCommandError(
                "workbench_relation_preparation_conflict",
                "Prepared workbench relation context does not match the confirm command.",
                payload={
                    "month_scope": normalized_month_scope,
                    "prepared_month_scope": preparation.month_scope,
                    "row_ids": [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()],
                    "prepared_row_ids": list(preparation.row_ids),
                },
            )

    def _validate_withdraw_preparation(
        self,
        preparation: WorkbenchRelationWithdrawPreparation,
        *,
        case_id: str,
        row_ids: list[str],
        row_id_aliases: dict[str, str] | None,
    ) -> None:
        prepared_row_ids = [
            str(row_id).strip()
            for row_id in list(preparation.before_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        if (
            preparation.owner_token is not self._withdraw_preparation_owner
            or preparation.case_id != str(case_id or "").strip()
            or (row_ids and set(row_ids) != set(prepared_row_ids))
            or preparation.row_id_aliases != dict(row_id_aliases or {})
        ):
            raise WorkbenchRelationCommandError(
                "workbench_relation_preparation_conflict",
                "Prepared workbench relation context does not match the withdraw command.",
                payload={
                    "case_id": str(case_id or "").strip(),
                    "prepared_case_id": preparation.case_id,
                    "row_ids": list(row_ids),
                    "prepared_row_ids": prepared_row_ids,
                },
            )

    @staticmethod
    def _canonical_withdraw_row_id(
        row_id: str,
        *,
        row_id_aliases: dict[str, str] | None,
    ) -> str:
        value = str(row_id).strip()
        if not value or not row_id_aliases:
            return value
        seen = {value}
        current = value
        while True:
            candidate = str(row_id_aliases.get(current, current)).strip()
            if not candidate or candidate == current or candidate in seen:
                return current
            seen.add(candidate)
            current = candidate

    @classmethod
    def _assert_exact_withdraw_selection(
        cls,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        active_relation: dict[str, Any],
        row_id_aliases: dict[str, str] | None,
    ) -> None:
        requested_ids = [
            cls._canonical_withdraw_row_id(
                str(row_id),
                row_id_aliases=row_id_aliases,
            )
            for row_id in list(row_ids or [])
            if str(row_id).strip()
        ]
        current_ids = [
            cls._canonical_withdraw_row_id(
                str(row_id),
                row_id_aliases=row_id_aliases,
            )
            for row_id in list(active_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        if row_types is not None:
            normalized_types = [str(row_type).strip() for row_type in row_types]
            current_types = [
                str(row_type).strip()
                for row_type in list(active_relation.get("row_types") or [])
            ]
            if len(requested_ids) != len(normalized_types) or len(current_ids) != len(current_types):
                raise WorkbenchRelationCommandError(
                    "workbench_relation_exact_selection_required",
                    "Withdraw relation requires aligned typed members.",
                )
            requested: set[Any] = set(zip(normalized_types, requested_ids, strict=True))
            current: set[Any] = set(zip(current_types, current_ids, strict=True))
        else:
            requested = set(requested_ids)
            current = set(current_ids)
        if requested != current:
            raise WorkbenchRelationCommandError(
                "workbench_relation_exact_selection_required",
                "Withdraw relation requires the complete active relation member set.",
                payload={
                    "case_id": str(active_relation.get("case_id") or ""),
                    "requested_row_ids": sorted(requested),
                    "current_row_ids": sorted(current),
                },
            )

    def _lock_and_revalidate_withdraw_topology(
        self,
        *,
        pair_service: WorkbenchPairRelationService,
        before_relation: dict[str, Any],
        freshness: dict[str, Any],
        row_id_aliases: dict[str, str] | None,
    ) -> tuple[WorkbenchPairRelationService, dict[str, Any], dict[str, Any]]:
        before_case_id = str(before_relation.get("case_id") or "").strip()
        before_row_ids = [
            str(row_id).strip()
            for row_id in list(before_relation.get("row_ids") or [])
            if str(row_id).strip()
        ]
        provisional = pair_service.preview_withdraw_for_active_relation(
            before_relation,
            row_id_aliases=row_id_aliases,
        )
        provisional_after = [
            deepcopy(relation)
            for relation in list(provisional.get("after_relations") or [])
            if isinstance(relation, dict)
        ]
        restored_row_ids, restored_row_types = self._canonical_relation_members(
            provisional_after,
            row_id_aliases=row_id_aliases,
        )
        restored_case_ids = self._changed_case_ids(provisional_after)
        before_row_types = [
            str(row_type).strip()
            for row_type in list(before_relation.get("row_types") or [])
        ]
        lock_row_ids, lock_row_types = self._merge_relation_members(
            before_row_ids,
            before_row_types,
            restored_row_ids,
            restored_row_types,
        )
        lock_case_ids = list(dict.fromkeys([before_case_id, *restored_case_ids]))
        self._acquire_relation_member_locks(
            lock_row_ids,
            row_types=lock_row_types,
            case_ids=lock_case_ids,
        )
        locked_pair_service = self._pair_service_for_row_ids(
            list(dict.fromkeys([*before_row_ids, *restored_row_ids])),
            case_ids=lock_case_ids,
        )
        locked_before = locked_pair_service.get_active_relation_by_case_id(before_case_id)
        if not isinstance(locked_before, dict):
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation topology changed while acquiring locks.",
                payload={"reason": "active_relation_changed", "case_id": before_case_id},
            )
        if self._relation_topology_identity(locked_before) != self._relation_topology_identity(
            before_relation
        ):
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation topology changed while acquiring locks.",
                payload={"reason": "active_relation_changed", "case_id": before_case_id},
            )
        locked_preview = self._preview_withdraw_relation_from_pair_service(
            locked_pair_service,
            row_ids=list(locked_before.get("row_ids") or []),
            month_scope=str(locked_before.get("month_scope") or "all"),
            freshness=freshness,
            row_id_aliases=row_id_aliases,
            active_relation=locked_before,
        )
        locked_after = [
            deepcopy(relation)
            for relation in list(locked_preview.get("after_relations") or [])
            if isinstance(relation, dict)
        ]
        provisional_after_topology = sorted(
            [self._relation_topology_identity(relation) for relation in provisional_after],
            key=lambda relation: str(relation.get("case_id") or ""),
        )
        locked_after_topology = sorted(
            [self._relation_topology_identity(relation) for relation in locked_after],
            key=lambda relation: str(relation.get("case_id") or ""),
        )
        if locked_after_topology != provisional_after_topology:
            raise WorkbenchRelationCommandError(
                "workbench_relation_preview_conflict",
                "Withdraw relation topology changed while acquiring locks.",
                payload={"reason": "restored_topology_changed", "case_id": before_case_id},
            )
        locked_row_ids, locked_row_types = self._canonical_relation_members(
            locked_after,
            row_id_aliases=row_id_aliases,
        )
        if locked_row_ids:
            self._assert_canonical_relation_members_available(
                locked_row_ids,
                row_types=locked_row_types,
            )
        try:
            locked_pair_service.assert_restored_relations_available(
                active_relation=locked_before,
                restored_relations=locked_after,
                row_id_aliases=row_id_aliases,
            )
        except ValueError as exc:
            raise WorkbenchRelationCommandError(
                "workbench_relation_restore_conflict",
                "Previous Workbench relation topology can no longer be restored safely.",
                payload={"reason": str(exc)},
            ) from exc
        return locked_pair_service, deepcopy(locked_before), locked_preview

    @staticmethod
    def _merge_relation_members(
        first_row_ids: list[str],
        first_row_types: list[str],
        second_row_ids: list[str],
        second_row_types: list[str],
    ) -> tuple[list[str], list[str]]:
        entries: dict[tuple[str, str], None] = {}
        for row_ids, row_types in (
            (list(first_row_ids or []), list(first_row_types or [])),
            (list(second_row_ids or []), list(second_row_types or [])),
        ):
            for index, row_id in enumerate(row_ids):
                normalized_row_id = str(row_id).strip()
                normalized_row_type = str(
                    row_types[index] if index < len(row_types) else ""
                ).strip()
                if not normalized_row_id or not normalized_row_type:
                    continue
                entries[(normalized_row_type, normalized_row_id)] = None
        ordered_entries = sorted(entries)
        return (
            [row_id for _, row_id in ordered_entries],
            [row_type for row_type, _ in ordered_entries],
        )

    @classmethod
    def _canonical_relation_members(
        cls,
        relations: list[dict[str, Any]],
        *,
        row_id_aliases: dict[str, str] | None,
    ) -> tuple[list[str], list[str]]:
        row_ids: list[str] = []
        row_types: list[str] = []
        seen: set[str] = set()
        for relation in list(relations or []):
            relation_row_ids = list(relation.get("row_ids") or [])
            relation_row_types = list(relation.get("row_types") or [])
            for index, row_id in enumerate(relation_row_ids):
                resolved_row_id = cls._canonical_withdraw_row_id(
                    str(row_id),
                    row_id_aliases=row_id_aliases,
                )
                if not resolved_row_id or resolved_row_id in seen:
                    continue
                resolved_row_type = str(
                    relation_row_types[index] if index < len(relation_row_types) else ""
                ).strip()
                if resolved_row_type not in {"oa", "bank", "invoice"}:
                    raise WorkbenchRelationCommandError(
                        "workbench_relation_restore_conflict",
                        "Previous Workbench relation contains an invalid member type.",
                        payload={
                            "reason": "invalid_restored_member_type",
                            "row_id": resolved_row_id,
                            "row_type": resolved_row_type,
                        },
                    )
                seen.add(resolved_row_id)
                row_ids.append(resolved_row_id)
                row_types.append(resolved_row_type)
        return row_ids, row_types

    def _acquire_relation_member_locks(
        self,
        row_ids: list[str],
        *,
        row_types: list[str] | None = None,
        case_ids: list[str] | None = None,
    ) -> list[str]:
        acquire = getattr(self._relation_repository, "acquire_relation_member_locks", None)
        if not callable(acquire):
            return []
        return list(
            acquire(
                list(row_ids or []),
                row_types=list(row_types or []),
                case_ids=list(case_ids or []),
            )
            or []
        )

    def _assert_canonical_relation_members_available(
        self,
        row_ids: list[str],
        *,
        row_types: list[str],
        tenant_id: str | None = None,
    ) -> None:
        lock = getattr(self._relation_repository, "lock_canonical_relation_members", None)
        if not callable(lock):
            return
        missing_member_keys = sorted(
            str(item).strip()
            for item in list(
                lock(
                    list(row_ids or []),
                    row_types=list(row_types or []),
                    tenant_id=self._canonical_tenant_id(tenant_id),
                )
                or []
            )
            if str(item).strip()
        )
        if missing_member_keys:
            raise WorkbenchRelationCommandError(
                "workbench_relation_canonical_member_missing",
                "One or more Workbench relation members no longer exist in canonical facts.",
                payload={"missing_member_keys": missing_member_keys},
            )

    def _canonical_tenant_id(self, tenant_id: str | None) -> str:
        return str(tenant_id or self._tenant_id or "").strip()

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

    def _active_pair_service_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> WorkbenchPairRelationService:
        loader = getattr(
            self._relation_repository,
            "load_active_workbench_pair_relations_for_row_ids",
            None,
        )
        if not callable(loader):
            raise WorkbenchRelationCommandError(
                "workbench_relation_repository_unavailable",
                "Workbench relation repository does not expose active relation overlap reads.",
            )
        return WorkbenchPairRelationService.from_snapshot(
            loader(list(row_ids or []), case_ids=list(case_ids or []))
        )

    def _active_pair_service_for_typed_rows(
        self,
        row_ids: list[str],
        row_types: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> WorkbenchPairRelationService:
        if len(row_ids) != len(row_types):
            raise ValueError("row_types must align with row_ids.")
        loader = getattr(
            self._relation_repository,
            "load_active_workbench_pair_relations_for_typed_rows",
            None,
        )
        if not callable(loader):
            raise WorkbenchRelationCommandError(
                "workbench_relation_repository_unavailable",
                "Workbench relation repository does not expose typed active relation overlap reads.",
            )
        return WorkbenchPairRelationService.from_snapshot(
            loader(
                list(row_ids or []),
                list(row_types or []),
                case_ids=list(case_ids or []),
            )
        )

    def _save_changed_cases(
        self,
        pair_service: WorkbenchPairRelationService,
        changed_case_ids: list[str],
        *,
        history_events: list[dict[str, Any]],
    ) -> None:
        saver = getattr(self._relation_repository, "save_workbench_pair_relation_delta", None)
        if not callable(saver):
            raise WorkbenchRelationCommandError(
                "workbench_relation_repository_unavailable",
                "Workbench relation repository does not expose changed-case delta persistence.",
            )
        changed_ids = {str(case_id).strip() for case_id in list(changed_case_ids or []) if str(case_id).strip()}
        snapshot = pair_service.snapshot_case_ids(sorted(changed_ids), include_history=False)
        snapshot["pair_relation_history"] = [
            deepcopy(history)
            for history in list(history_events or [])
            if isinstance(history, dict)
        ]
        saver(snapshot, changed_case_ids=changed_ids)

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
        scope_keys_hint: list[str] | None = None,
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
        normalized_scope_keys = list(
            dict.fromkeys(
                str(scope_key).strip()
                for scope_key in list(scope_keys_hint or [])
                if str(scope_key).strip()
            )
        )
        payload = reader(
            [str(row_id) for row_id in list(row_ids or [])],
            require_fresh=True,
            reason="workbench_relation_write_precondition",
            month_hint=month_scope,
            scope_keys_hint=normalized_scope_keys or self._affected_months(month_scope),
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

from __future__ import annotations

from copy import deepcopy
from typing import Any

from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.postgres_repositories.common import text, text_list
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_relation import (
    OaPendingPaymentRelationRepositoryError,
)
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


class OaPendingPaymentRelationPromotionService:
    def __init__(
        self,
        *,
        pending_relation_service: Any,
        relation_command_service: Any,
    ) -> None:
        self._pending_relation_service = pending_relation_service
        self._relation_command_service = relation_command_service

    def promote_completed_records(
        self,
        records: list[OAApplicationRecord],
        *,
        actor_id: str = "oa_projection_sync",
    ) -> dict[str, Any]:
        completed_records = [
            record
            for record in list(records or [])
            if isinstance(record, OAApplicationRecord) and text(getattr(record, "id", ""))
        ]
        completed_ids = _dedupe_text(getattr(record, "id", "") for record in completed_records)
        if not completed_ids:
            return _empty_result()
        completed_id_set = set(completed_ids)
        month_by_oa_id = {
            text(record.id): text(getattr(record, "month", "")) or "all"
            for record in completed_records
            if text(record.id)
        }
        active_loader = getattr(self._pending_relation_service, "active_relations_for_row_ids", None)
        if not callable(active_loader):
            raise OaPendingPaymentRelationRepositoryError(
                "pending_relation_active_loader_unavailable",
                "Pending payment relation service cannot load active relations.",
            )
        mark_promoted = getattr(self._pending_relation_service, "mark_relation_promoted", None)
        if not callable(mark_promoted):
            raise OaPendingPaymentRelationRepositoryError(
                "pending_relation_promotion_writer_unavailable",
                "Pending payment relation service cannot mark promoted relations.",
            )

        relations = list(active_loader(completed_ids) or [])
        result = _empty_result()
        seen_relation_ids: set[str] = set()
        for relation in relations:
            if not isinstance(relation, dict):
                continue
            relation_id = text(relation.get("relation_id") or relation.get("relationId") or relation.get("case_id"))
            if not relation_id or relation_id in seen_relation_ids:
                continue
            seen_relation_ids.add(relation_id)
            oa_ids = text_list(relation.get("oa_row_ids")) or text_list(relation.get("oaRowIds"))
            bank_ids = text_list(relation.get("bank_transaction_ids")) or text_list(relation.get("bankTransactionIds"))
            if not oa_ids or not bank_ids:
                result["skipped_count"] += 1
                continue
            if not set(oa_ids).issubset(completed_id_set):
                result["skipped_count"] += 1
                continue
            workbench_case_id = _workbench_case_id(relation, relation_id)
            month_scope = _relation_month_scope(relation, oa_ids=oa_ids, month_by_oa_id=month_by_oa_id)
            try:
                confirm_result = self._relation_command_service.confirm_relation(
                    case_id=workbench_case_id,
                    row_ids=[*oa_ids, *bank_ids],
                    row_types=[*(["oa"] * len(oa_ids)), *(["bank"] * len(bank_ids))],
                    relation_mode=_promotion_relation_mode(relation),
                    actor_id=actor_id,
                    month_scope=month_scope,
                    note=text(relation.get("note")),
                    amount_check=deepcopy(relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else {}),
                    special_metadata=_promotion_metadata(relation, relation_id=relation_id),
                    evidence={"pending_payment_relation": _promotion_evidence(relation)},
                    relation_created_by=actor_id,
                    history_note="Promoted from OA pending payment in-progress relation after OA completion.",
                    idempotency_key=f"oa-pending-payment-promotion:{relation_id}:{workbench_case_id}",
                    history_operation_type="oa_pending_payment_promote_completed",
                )
                promoted = mark_promoted(
                    relation_id=relation_id,
                    workbench_case_id=workbench_case_id,
                    actor_id=actor_id,
                )
            except (OaPendingPaymentRelationRepositoryError, WorkbenchRelationCommandError) as exc:
                result["error_count"] += 1
                result["errors"].append(
                    {
                        "relation_id": relation_id,
                        "workbench_case_id": workbench_case_id,
                        "error_code": text(getattr(exc, "error_code", "")) or exc.__class__.__name__,
                        "message": text(getattr(exc, "message", "")) or str(exc),
                        "payload": deepcopy(getattr(exc, "payload", {}) or {}),
                    }
                )
                continue
            result["promoted_count"] += 1
            result["promotions"].append(
                {
                    "relation_id": relation_id,
                    "workbench_case_id": workbench_case_id,
                    "confirm_result": deepcopy(confirm_result if isinstance(confirm_result, dict) else {}),
                    "promoted": deepcopy(promoted if isinstance(promoted, dict) else {}),
                }
            )
            for month in text_list((promoted or {}).get("affected_months")) or [month_scope]:
                if month and month not in result["affected_months"]:
                    result["affected_months"].append(month)
        result["affected_months"] = sorted(result["affected_months"])
        return result


def _empty_result() -> dict[str, Any]:
    return {
        "promoted_count": 0,
        "skipped_count": 0,
        "error_count": 0,
        "promotions": [],
        "errors": [],
        "affected_months": [],
    }


def _workbench_case_id(relation: dict[str, Any], relation_id: str) -> str:
    return (
        text(relation.get("migrated_from_workbench_case_id"))
        or text(relation.get("migratedFromWorkbenchCaseId"))
        or text(relation.get("promoted_workbench_case_id"))
        or text(relation.get("promotedWorkbenchCaseId"))
        or relation_id
    )


def _relation_month_scope(
    relation: dict[str, Any],
    *,
    oa_ids: list[str],
    month_by_oa_id: dict[str, str],
) -> str:
    month = text(relation.get("month_scope") or relation.get("monthScope"))
    if month and month != "all":
        return month[:7]
    for oa_id in oa_ids:
        record_month = text(month_by_oa_id.get(oa_id))
        if record_month:
            return record_month[:7]
    return "all"


def _promotion_relation_mode(relation: dict[str, Any]) -> str:
    source_action = text(relation.get("source_action") or relation.get("sourceAction"))
    if source_action == "auto_reconcile_bank_transactions":
        return "normal_match"
    return "manual_confirmed"


def _promotion_metadata(relation: dict[str, Any], *, relation_id: str) -> dict[str, Any]:
    source_action = text(relation.get("source_action") or relation.get("sourceAction"))
    return {
        "origin": "oa_pending_payment_promotion",
        "source": "oa_pending_payment_bank_relations",
        "pending_relation_id": relation_id,
        "source_action": source_action,
    }


def _promotion_evidence(relation: dict[str, Any]) -> dict[str, Any]:
    return {
        "relation_id": text(relation.get("relation_id") or relation.get("relationId") or relation.get("case_id")),
        "oa_row_ids": text_list(relation.get("oa_row_ids")) or text_list(relation.get("oaRowIds")),
        "bank_transaction_ids": text_list(relation.get("bank_transaction_ids")) or text_list(relation.get("bankTransactionIds")),
        "source_action": text(relation.get("source_action") or relation.get("sourceAction")),
    }


def _dedupe_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in list(values or []):
        normalized = text(value)
        if normalized and normalized not in result:
            result.append(normalized)
    return result

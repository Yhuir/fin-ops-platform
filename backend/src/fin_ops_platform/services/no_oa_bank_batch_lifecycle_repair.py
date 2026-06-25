from __future__ import annotations

from collections import Counter
from copy import deepcopy
from typing import Any

from fin_ops_platform.services.no_oa_bank_batch_service import NoOaBankBatchService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


PUBLIC_NO_OA_BANK_BATCH_STATUSES = frozenset({"draft", "submitted", "withdrawn"})


def build_public_no_oa_bank_batch_snapshot(
    no_oa_snapshot: dict[str, Any] | None,
    *,
    pair_relation_snapshot: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    original_snapshot = deepcopy(no_oa_snapshot) if isinstance(no_oa_snapshot, dict) else {}
    original_batches = original_snapshot.get("batches") if isinstance(original_snapshot.get("batches"), dict) else {}
    source_snapshot = deepcopy(original_snapshot)
    source_snapshot = _normalize_cancelled_submitted_batches(
        source_snapshot,
        pair_relation_snapshot=pair_relation_snapshot,
    )
    pair_service = WorkbenchPairRelationService.from_snapshot(pair_relation_snapshot)
    batch_service = NoOaBankBatchService.from_snapshot(
        source_snapshot,
        pair_relation_service=pair_service,
    )
    public_snapshot = batch_service.public_snapshot()
    public_batches = public_snapshot.get("batches") if isinstance(public_snapshot.get("batches"), dict) else {}
    source_batch_ids = {str(batch_id) for batch_id in original_batches}
    public_batch_ids = {str(batch_id) for batch_id in public_batches}

    removed_batch_ids = sorted(source_batch_ids - public_batch_ids)
    normalized_batch_ids = sorted(
        batch_id
        for batch_id in source_batch_ids.intersection(public_batch_ids)
        if _raw_status(original_batches.get(batch_id)) != _raw_status(public_batches.get(batch_id))
        or _raw_bucket(original_batches.get(batch_id)) != _raw_bucket(public_batches.get(batch_id))
    )
    removed_status_counts = Counter(
        _raw_status(original_batches.get(batch_id)) or "unknown"
        for batch_id in removed_batch_ids
    )
    normalized_status_counts = Counter(
        f"{_raw_status(original_batches.get(batch_id)) or 'unknown'}->{_raw_status(public_batches.get(batch_id)) or 'unknown'}"
        for batch_id in normalized_batch_ids
    )
    report = {
        "before_count": len(source_batch_ids),
        "after_count": len(public_batch_ids),
        "removed_count": len(removed_batch_ids),
        "normalized_count": len(normalized_batch_ids),
        "removed_status_counts": dict(sorted(removed_status_counts.items())),
        "normalized_status_counts": dict(sorted(normalized_status_counts.items())),
        "removed_batch_ids": removed_batch_ids,
        "normalized_batch_ids": normalized_batch_ids,
    }
    return public_snapshot, report


def _normalize_cancelled_submitted_batches(
    source_snapshot: dict[str, Any],
    *,
    pair_relation_snapshot: dict[str, Any] | None,
) -> dict[str, Any]:
    batches = source_snapshot.get("batches") if isinstance(source_snapshot.get("batches"), dict) else {}
    if not batches:
        return source_snapshot
    relations = _relations_by_case_id(pair_relation_snapshot)
    if not relations:
        return source_snapshot

    normalized_snapshot = deepcopy(source_snapshot)
    normalized_batches = normalized_snapshot.get("batches") if isinstance(normalized_snapshot.get("batches"), dict) else {}
    for batch_id, batch in list(normalized_batches.items()):
        if not isinstance(batch, dict):
            continue
        if _raw_status(batch) != "submitted":
            continue
        relation_case_id = str(batch.get("relation_case_id") or batch.get("batch_id") or batch_id or "").strip()
        relation = relations.get(relation_case_id)
        if not _is_cancelled_no_oa_relation(relation):
            continue
        withdrawn_at = str(
            relation.get("withdrawn_at")
            or relation.get("updated_at")
            or batch.get("withdrawn_at")
            or batch.get("updated_at")
            or ""
        )
        withdrawn_by = str(
            relation.get("withdrawn_by")
            or relation.get("updated_by")
            or batch.get("withdrawn_by")
            or "system:no_oa_lifecycle_repair"
        )
        normalized = deepcopy(batch)
        normalized.update(
            {
                "status": "withdrawn",
                "status_bucket": "withdrawn",
                "can_submit": False,
                "can_withdraw": False,
                "withdrawn_at": withdrawn_at,
                "withdrawn_by": withdrawn_by,
                "withdraw_reason": str(batch.get("withdraw_reason") or "relation_cancelled"),
            }
        )
        normalized_batches[str(batch_id)] = normalized
    return normalized_snapshot


def _relations_by_case_id(pair_relation_snapshot: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not isinstance(pair_relation_snapshot, dict):
        return {}
    raw_relations = pair_relation_snapshot.get("pair_relations")
    if not isinstance(raw_relations, dict):
        return {}
    relations: dict[str, dict[str, Any]] = {}
    for fallback_case_id, relation in raw_relations.items():
        if not isinstance(relation, dict):
            continue
        case_id = str(relation.get("case_id") or fallback_case_id or "").strip()
        if case_id:
            relations[case_id] = relation
    return relations


def _is_cancelled_no_oa_relation(relation: object) -> bool:
    if not isinstance(relation, dict):
        return False
    if str(relation.get("status") or "").strip() != "cancelled":
        return False
    if str(relation.get("relation_mode") or "").strip() == "no_oa_bank_batch":
        return True
    special_metadata = relation.get("special_metadata")
    return (
        isinstance(special_metadata, dict)
        and str(special_metadata.get("relation_mode") or special_metadata.get("source") or "").strip()
        == "no_oa_bank_batch"
    )


def _raw_status(batch: object) -> str:
    if not isinstance(batch, dict):
        return ""
    return str(batch.get("status") or "").strip()


def _raw_bucket(batch: object) -> str:
    if not isinstance(batch, dict):
        return ""
    return str(batch.get("status_bucket") or batch.get("statusBucket") or "").strip()

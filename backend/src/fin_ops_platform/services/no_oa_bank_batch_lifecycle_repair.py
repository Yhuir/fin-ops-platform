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
    source_snapshot = deepcopy(no_oa_snapshot) if isinstance(no_oa_snapshot, dict) else {}
    source_batches = source_snapshot.get("batches") if isinstance(source_snapshot.get("batches"), dict) else {}
    pair_service = WorkbenchPairRelationService.from_snapshot(pair_relation_snapshot)
    batch_service = NoOaBankBatchService.from_snapshot(
        source_snapshot,
        pair_relation_service=pair_service,
    )
    public_snapshot = batch_service.public_snapshot()
    public_batches = public_snapshot.get("batches") if isinstance(public_snapshot.get("batches"), dict) else {}
    source_batch_ids = {str(batch_id) for batch_id in source_batches}
    public_batch_ids = {str(batch_id) for batch_id in public_batches}

    removed_batch_ids = sorted(source_batch_ids - public_batch_ids)
    normalized_batch_ids = sorted(
        batch_id
        for batch_id in source_batch_ids.intersection(public_batch_ids)
        if _raw_status(source_batches.get(batch_id)) != _raw_status(public_batches.get(batch_id))
        or _raw_bucket(source_batches.get(batch_id)) != _raw_bucket(public_batches.get(batch_id))
    )
    removed_status_counts = Counter(
        _raw_status(source_batches.get(batch_id)) or "unknown"
        for batch_id in removed_batch_ids
    )
    normalized_status_counts = Counter(
        f"{_raw_status(source_batches.get(batch_id)) or 'unknown'}->{_raw_status(public_batches.get(batch_id)) or 'unknown'}"
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


def _raw_status(batch: object) -> str:
    if not isinstance(batch, dict):
        return ""
    return str(batch.get("status") or "").strip()


def _raw_bucket(batch: object) -> str:
    if not isinstance(batch, dict):
        return ""
    return str(batch.get("status_bucket") or batch.get("statusBucket") or "").strip()

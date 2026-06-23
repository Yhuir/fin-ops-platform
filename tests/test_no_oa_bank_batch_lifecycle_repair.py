from __future__ import annotations

from fin_ops_platform.services.no_oa_bank_batch_lifecycle_repair import (
    build_public_no_oa_bank_batch_snapshot,
)


def test_public_lifecycle_repair_removes_unsubmitted_exception_batches() -> None:
    snapshot = {
        "schema_version": 1,
        "batches": {
            "batch-draft": {
                "batch_id": "batch-draft",
                "batch_type": "fee",
                "status": "draft",
                "status_bucket": "unsubmitted",
                "row_ids": ["bank-1"],
                "row_count": 1,
                "total_amount": "1.00",
                "version": 1,
            },
            "batch-conflict": {
                "batch_id": "batch-conflict",
                "batch_type": "internal_transfer",
                "status": "conflict",
                "status_bucket": "unsubmitted",
                "row_ids": ["bank-2"],
                "row_count": 1,
                "total_amount": "2.00",
                "version": 1,
            },
            "batch-stale": {
                "batch_id": "batch-stale",
                "batch_type": "fee",
                "status": "stale",
                "status_bucket": "unsubmitted",
                "row_ids": ["bank-3"],
                "row_count": 1,
                "total_amount": "3.00",
                "version": 2,
            },
            "batch-withdrawn": {
                "batch_id": "batch-withdrawn",
                "batch_type": "fee",
                "status": "withdrawn",
                "status_bucket": "withdrawn",
                "row_ids": ["bank-4"],
                "row_count": 1,
                "total_amount": "4.00",
                "version": 3,
            },
        },
        "audit_log": [{"operation": "submit", "batch_id": "batch-stale"}],
    }

    public_snapshot, report = build_public_no_oa_bank_batch_snapshot(snapshot)

    assert sorted(public_snapshot["batches"]) == ["batch-draft", "batch-withdrawn"]
    assert public_snapshot["audit_log"][0]["operation"] == "submit"
    assert public_snapshot["audit_log"][0]["batch_id"] == "batch-stale"
    assert report["before_count"] == 4
    assert report["after_count"] == 2
    assert report["removed_status_counts"] == {"conflict": 1, "stale": 1}
    assert report["removed_batch_ids"] == ["batch-conflict", "batch-stale"]


def test_public_lifecycle_repair_keeps_relation_backed_stale_as_submitted() -> None:
    snapshot = {
        "batches": {
            "batch-stale-active": {
                "batch_id": "batch-stale-active",
                "batch_type": "fee",
                "status": "stale",
                "status_bucket": "unsubmitted",
                "relation_case_id": "batch-stale-active",
                "row_ids": ["bank-1"],
                "row_count": 1,
                "total_amount": "1.00",
                "version": 4,
            }
        }
    }
    pair_relation_snapshot = {
        "pair_relations": {
            "batch-stale-active": {
                "case_id": "batch-stale-active",
                "row_ids": ["bank-1"],
                "row_types": ["bank"],
                "status": "active",
                "relation_mode": "no_oa_bank_batch",
                "month_scope": "2026-03",
                "created_by": "finance-user",
                "special_metadata": {
                    "source": "no_oa_bank_batch",
                    "source_batch_id": "batch-stale-active",
                },
            }
        }
    }

    public_snapshot, report = build_public_no_oa_bank_batch_snapshot(
        snapshot,
        pair_relation_snapshot=pair_relation_snapshot,
    )

    public_batch = public_snapshot["batches"]["batch-stale-active"]
    assert public_batch["status"] == "submitted"
    assert public_batch["status_bucket"] == "submitted"
    assert public_batch["can_withdraw"] is True
    assert report["removed_count"] == 0
    assert report["normalized_status_counts"] == {"stale->submitted": 1}


def test_public_lifecycle_repair_normalizes_legacy_unsubmitted_to_draft() -> None:
    snapshot = {
        "batches": {
            "batch-legacy-unsubmitted": {
                "batch_id": "batch-legacy-unsubmitted",
                "batch_type": "internal_transfer",
                "status": "unsubmitted",
                "status_bucket": "unsubmitted",
                "row_ids": ["bank-1", "bank-2"],
                "row_count": 2,
                "total_amount": "500.00",
                "can_submit": False,
                "version": 2,
            }
        }
    }

    public_snapshot, report = build_public_no_oa_bank_batch_snapshot(snapshot)

    public_batch = public_snapshot["batches"]["batch-legacy-unsubmitted"]
    assert public_batch["status"] == "draft"
    assert public_batch["status_bucket"] == "unsubmitted"
    assert public_batch["can_submit"] is True
    assert report["removed_count"] == 0
    assert report["normalized_status_counts"] == {"unsubmitted->draft": 1}

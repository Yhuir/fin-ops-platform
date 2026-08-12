from __future__ import annotations

from copy import deepcopy

import pytest

from fin_ops_platform.services.invoice_header_fact_repair_service import (
    INVOICE_HEADER_REPAIR_FACTS,
    INVOICE_HEADER_REPAIR_SOURCE_SHA256,
    build_invoice_header_fact_repair_plan,
    public_invoice_header_fact_repair_report,
)


def _snapshot() -> list[dict[str, object]]:
    return [
        {
            "invoice_id": f"invoice-{index}",
            "invoice_type": "input_invoice",
            "digital_invoice_no": fact["digital_invoice_no"],
            "invoice_month": "2026-06",
            "amount": "1.00",
            "signed_amount": "1.00",
            "tax_amount": "0.13",
            "total_with_tax": "1.13",
            "tax_rate": "13%",
            "raw_payload": {
                "normalized_payload": {
                    "amount": "1.00",
                    "tax_rate": "13%",
                    "taxable_item_name": "第一条商品明细",
                }
            },
        }
        for index, fact in enumerate(INVOICE_HEADER_REPAIR_FACTS, start=1)
    ]


def test_build_invoice_header_fact_repair_plan_is_exact_and_recoverable() -> None:
    plan = build_invoice_header_fact_repair_plan(
        _snapshot(),
        source_sha256=INVOICE_HEADER_REPAIR_SOURCE_SHA256,
        expected_target_count=11,
    )

    assert plan["target_count"] == 11
    assert plan["update_count"] == 11
    assert plan["affected_months"] == ["2026-06"]
    assert len(plan["rollback_manifest"]["restore_invoices"]) == 11
    first = plan["updates"][0]
    assert first["raw_payload"]["normalized_payload"]["source_sheet_name"] == "发票基础信息"
    assert first["raw_payload"]["normalized_payload"]["source_workbook_sha256"] == INVOICE_HEADER_REPAIR_SOURCE_SHA256
    assert first["tax_rate"] == ""
    assert first["raw_payload"]["normalized_payload"]["tax_rate"] is None
    assert first["raw_payload"]["normalized_payload"]["taxable_item_name"] is None


def test_invoice_header_fact_repair_rejects_wrong_hash_missing_and_duplicate_targets() -> None:
    with pytest.raises(ValueError, match="SHA-256"):
        build_invoice_header_fact_repair_plan(
            _snapshot(), source_sha256="wrong", expected_target_count=11
        )
    with pytest.raises(ValueError, match="resolve every"):
        build_invoice_header_fact_repair_plan(
            _snapshot()[:-1],
            source_sha256=INVOICE_HEADER_REPAIR_SOURCE_SHA256,
            expected_target_count=11,
        )
    duplicate = _snapshot()
    duplicate[-1] = deepcopy(duplicate[0])
    with pytest.raises(ValueError, match="exactly once"):
        build_invoice_header_fact_repair_plan(
            duplicate,
            source_sha256=INVOICE_HEADER_REPAIR_SOURCE_SHA256,
            expected_target_count=11,
        )


def test_invoice_header_fact_repair_is_idempotent_after_values_match() -> None:
    snapshot = _snapshot()
    initial_plan = build_invoice_header_fact_repair_plan(
        snapshot,
        source_sha256=INVOICE_HEADER_REPAIR_SOURCE_SHA256,
        expected_target_count=11,
    )
    updates_by_number = {
        update["digital_invoice_no"]: update for update in initial_plan["updates"]
    }
    for row in snapshot:
        update = updates_by_number[str(row["digital_invoice_no"])]
        row.update(
            {
                "amount": update["amount"],
                "signed_amount": update["signed_amount"],
                "tax_amount": update["tax_amount"],
                "total_with_tax": update["total_with_tax"],
                "tax_rate": "",
                "raw_payload": deepcopy(update["raw_payload"]),
            }
        )

    plan = build_invoice_header_fact_repair_plan(
        snapshot,
        source_sha256=INVOICE_HEADER_REPAIR_SOURCE_SHA256,
        expected_target_count=11,
    )
    report = public_invoice_header_fact_repair_report(
        plan,
        mode="dry_run",
        written=False,
    )

    assert plan["update_count"] == 0
    assert plan["source_fingerprint"] == initial_plan["source_fingerprint"]
    assert report["target_count"] == 11
    assert report["authorized_write_scope"] == [
        "app.invoices",
        "job.outbox_events",
        "job.read_model_dirty_scopes",
        "ops.operation_events",
    ]

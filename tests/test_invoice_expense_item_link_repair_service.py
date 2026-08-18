from __future__ import annotations

import pytest

from fin_ops_platform.services.invoice_expense_item_link_repair_service import (
    build_invoice_expense_item_link_repair_plan,
    public_invoice_expense_item_link_repair_report,
)


def _snapshot() -> list[dict[str, object]]:
    return [
        {
            "invoice_id": "invoice-1",
            "digital_invoice_no": "26537000000000000001",
            "total_with_tax": "859.57",
            "source_links": [{"source_type": "manual_invoice_import"}],
        },
        {
            "invoice_id": "invoice-2",
            "digital_invoice_no": "26537000000000000002",
            "total_with_tax": "1178.45",
            "source_links": [],
        },
    ]


def _plan(snapshot: list[dict[str, object]] | None = None) -> dict[str, object]:
    return build_invoice_expense_item_link_repair_plan(
        snapshot if snapshot is not None else _snapshot(),
        invoice_ids=["invoice-1", "invoice-2"],
        case_id="CASE-AUTO-0102",
        oa_row_id="oa-exp-1992",
        expense_item_id="oa-exp-1992:item:0:cceb2198c025",
        expected_total="2038.02",
    )


def test_build_invoice_expense_item_link_repair_plan_is_exact_and_auditable() -> None:
    plan = _plan()

    assert plan["target_count"] == 2
    assert plan["target_total"] == "2038.02"
    assert plan["update_count"] == 2
    assert len(plan["source_fingerprint"]) == 64
    added_link = plan["updates"][0]["source_links"][-1]
    assert added_link == {
        "source_type": "oa_expense_item_invoice",
        "source_workbench_row_id": "oa-exp-1992",
        "derived_from_oa_id": "oa-exp-1992",
        "source_expense_item_id": "oa-exp-1992:item:0:cceb2198c025",
        "source_relation_case_id": "CASE-AUTO-0102",
        "entry_method": "historical_repair",
    }
    report = public_invoice_expense_item_link_repair_report(
        plan,
        mode="dry_run",
        written=False,
    )
    assert report["authorized_write_scope"] == ["app.invoices", "ops.operation_events"]
    assert report["rollback_manifest"]["restore_invoice_source_links"][0][
        "source_links"
    ] == [{"source_type": "manual_invoice_import"}]


def test_build_invoice_expense_item_link_repair_plan_rejects_wrong_total() -> None:
    with pytest.raises(ValueError, match="authorized total"):
        build_invoice_expense_item_link_repair_plan(
            _snapshot(),
            invoice_ids=["invoice-1", "invoice-2"],
            case_id="CASE-AUTO-0102",
            oa_row_id="oa-exp-1992",
            expense_item_id="oa-exp-1992:item:0:cceb2198c025",
            expected_total="2038.03",
        )


def test_build_invoice_expense_item_link_repair_plan_rejects_conflicting_link() -> None:
    snapshot = _snapshot()
    snapshot[0]["source_links"] = [
        {
            "source_type": "oa_expense_item_invoice",
            "derived_from_oa_id": "oa-other",
            "source_expense_item_id": "oa-other:item:0",
        }
    ]

    with pytest.raises(ValueError, match="conflicting"):
        _plan(snapshot)


def test_build_invoice_expense_item_link_repair_plan_is_idempotent() -> None:
    first_plan = _plan()
    snapshot = _snapshot()
    for row in snapshot:
        update = next(
            item for item in first_plan["updates"] if item["invoice_id"] == row["invoice_id"]
        )
        row["source_links"] = update["source_links"]

    assert _plan(snapshot)["update_count"] == 0

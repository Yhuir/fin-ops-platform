from decimal import Decimal

import pytest

from fin_ops_platform.services.bank_split_relation_scope import bank_split_comparison_rows


def banks():
    return [
        {"id": "principal", "amount": "1000000.00", "txn_direction": "outflow", "is_split": True, "turnover_role": "external_turnover"},
        {"id": "interest", "amount": "1497.22", "txn_direction": "outflow", "is_split": True},
    ]


@pytest.mark.parametrize(("target", "ids"), [("1497.22", ["interest"]), ("1000000", ["principal"]), ("1001497.22", ["principal", "interest"]), ("100", ["principal", "interest"])])
def test_only_unique_complete_purpose_bucket_is_selected(target, ids):
    rows = banks()
    assert [row["id"] for row in bank_split_comparison_rows(rows, target=Decimal(target))] == ids
    assert len(rows) == 2


def test_duplicate_amounts_and_mixed_directions_do_not_invent_ownership():
    rows = banks()
    rows[0]["amount"] = "1497.22"
    assert bank_split_comparison_rows(rows, target=Decimal("1497.22")) == rows
    rows = banks()
    rows[0]["txn_direction"] = "inflow"
    assert bank_split_comparison_rows(rows, target=Decimal("1497.22")) == rows


def test_unsplit_and_missing_document_totals_keep_existing_behavior():
    rows = banks()
    for row in rows:
        row["is_split"] = False
    assert bank_split_comparison_rows(rows, target=Decimal("1497.22")) == rows
    assert bank_split_comparison_rows(banks(), target=None) == banks()


def test_mixed_unsplit_principal_cannot_be_hidden_in_other_purpose_bucket():
    rows = banks() + [{"id": "old-principal", "amount": "500.00", "txn_direction": "outflow", "is_split": False, "turnover_role": "external_turnover"}]
    assert bank_split_comparison_rows(rows, target=Decimal("1000000.00")) == rows


def test_unknown_oa_amount_preserves_the_full_comparison_evidence():
    from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
    rows = banks()
    for row in rows:
        row["type"] = "bank"
    result = WorkbenchAmountCheckService().check({"bank": rows, "oa": [
        {"type": "oa", "amount": "1497.22", "apply_type": "支付申请"},
        {"type": "oa", "amount": None, "apply_type": "支付申请"},
    ], "invoice": []})
    assert result["bank_total"] == "1001497.22"

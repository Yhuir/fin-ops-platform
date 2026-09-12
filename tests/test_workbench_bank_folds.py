from copy import deepcopy

import pytest
from fin_ops_platform.services.workbench_bank_folds import apply_bank_folds
from fin_ops_platform.services.workbench_display_subgroups import apply_display_subgroups
from test_workbench_display_subgroups import event, group, relation, row


def fixture(count=4, kind="oa"):
    banks = [dict(row("bank", f"b{i}", "10.01"), category_code="interest", currency="CNY",
                  payment_account_label="bank A", counterparty_name="party", trade_time="2026-05-01") for i in range(count)]
    g = group([*([row(kind, "owner", "40.04")] if kind else []), *banks])
    g["group_id"] = "case:merged"
    return g


@pytest.mark.parametrize("count", [0, 1, 3, 4, 9])
@pytest.mark.parametrize("kind", ["oa", "invoice", None])
def test_threshold_preserves_canonical_members_with_or_without_owner(count, kind):
    g = fixture(count, kind)
    original = deepcopy(g)
    apply_bank_folds([g])
    folds = g.pop("bank_folds", [])
    assert g == original
    assert len(folds) == (1 if count >= 4 else 0)
    if folds:
        assert folds[0]["member_ids"] == [r["id"] for r in g["bank_rows"]]
        assert folds[0]["summary_row"]["amount"] == f"{count * 1001 / 100:.2f}"
        assert folds[0]["summary_row"]["available_actions"] == []
        assert folds[0]["summary_row"]["special_metadata"] == {}


@pytest.mark.parametrize("field,value", [("category_code", "other"), ("category_code", ""),
                                        ("currency", "USD"), ("txn_direction", "inflow")])
@pytest.mark.parametrize("kind", ["oa", None])
def test_mixed_or_missing_classification_never_folds(field, value, kind):
    g = fixture(kind=kind)
    g["bank_rows"][0][field] = value
    apply_bank_folds([g])
    assert "bank_folds" not in g


def test_four_plus_one_remains_two_areas_even_if_old_batch_crosses_them():
    g = fixture(5)
    other = row("oa", "other", "10.01")
    g["oa_rows"].append(other)
    g["formal_member_ids"].append("other")
    g["formal_member_types"].append("oa")
    rows = [*g["oa_rows"], *g["bank_rows"]]
    g["bank_batches"] = [{"member_ids": [r["id"] for r in g["bank_rows"]]}]
    history = [event(relation("merged", rows), [relation("old", [g["oa_rows"][0], *g["bank_rows"][:4]])])]
    apply_display_subgroups([g], history)
    apply_bank_folds([g])
    assert len(g["display_subgroups"]) == 2
    assert len(g["bank_folds"]) == 1
    assert g["bank_folds"][0]["member_ids"] == ["b0", "b1", "b2", "b3"]


def test_summary_does_not_impersonate_first_account_or_date_and_direction_is_exact():
    g = fixture()
    g["bank_rows"][1].update(payment_account_label="bank B", counterparty_name="another", trade_time="2026-05-02")
    for r in g["bank_rows"]:
        r["txn_direction"] = "inflow"
    apply_bank_folds([g])
    summary = g["bank_folds"][0]["summary_row"]
    assert summary["payment_account_label"] == "多个账户"
    assert summary["counterparty_name"] == "多个对方"
    assert summary["trade_time"] == ""
    assert summary["credit_amount"] == "40.04"
    assert summary["debit_amount"] == ""


def test_unresolved_shared_area_stays_unfolded():
    g = fixture()
    g["display_subgroups"] = [{"resolved": False, "oa_row_ids": ["owner"], "bank_row_ids": ["b0", "b1", "b2", "b3"]}]
    apply_bank_folds([g])
    assert "bank_folds" not in g


def test_unrelated_bank_rows_never_fold_and_formal_groups_never_merge():
    g = fixture(kind=None)
    g["formal_member_ids"] = []
    apply_bank_folds([g])
    assert "bank_folds" not in g
    groups = [fixture(3, kind=None), fixture(3, kind=None)]
    groups[1]["group_id"] = "case:other"
    apply_bank_folds(groups)
    assert not any(g.get("bank_folds") for g in groups)

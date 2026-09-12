from copy import deepcopy

import pytest
from fin_ops_platform.services.workbench_display_subgroups import apply_display_subgroups
from fin_ops_platform.services.workbench_relation_alignment_service import WorkbenchRelationAlignmentService


def row(kind, id, amount):
    return {"id": id, "type": kind, "amount": str(amount), "txn_direction": "outflow"}


def relation(case, rows):
    return {"case_id": case, "row_ids": [r["id"] for r in rows], "row_types": [r["type"] for r in rows]}


def group(rows, case="merged"):
    return {
        "case_id": case,
        "formal_member_ids": [r["id"] for r in rows],
        "formal_member_types": [r["type"] for r in rows],
        **{f"{kind}_rows": [r for r in rows if r["type"] == kind] for kind in ("oa", "bank", "invoice")},
    }


def event(after, before):
    return {"operation_type": "confirm_link", "after_relations": [after], "before_relations": before}


def test_repeated_amounts_follow_historical_subgroups_without_changing_facts():
    oa = [row("oa", f"o{i}", 199) for i in range(3)]
    banks = [row("bank", f"b{i}", amount) for i, amount in enumerate([164, 35] * 3)]
    rows = oa + banks + [row("invoice", "invoice", 620)]
    g = group(rows)
    original = deepcopy(g)
    history = [
        event(relation("merged", rows), [relation("old0", [oa[0], *banks[:2]]), relation("old1", [oa[1], *banks[2:4]])])
    ]
    apply_display_subgroups([g], history)
    assert g.pop("display_subgroups") == [
        {"oa_row_ids": [f"o{i}"], "bank_row_ids": [f"b{i * 2}", f"b{i * 2 + 1}"]} for i in range(3)
    ]
    assert g == original


def test_nested_merge_uses_exact_members_and_preserves_many_to_one():
    a, b, c, d = [row("oa", f"o{i}", amount) for i, amount in enumerate([10, 20, 40, 50])]
    x, y = row("bank", "x", 30), row("bank", "y", 90)
    old = relation("reused", [a, b, x])
    middle = relation("reused", [a, b, x, c, d, y])
    rows = [a, b, c, d, x, y, row("invoice", "i", 120)]
    g = group(rows)
    history = [event(middle, [old]), event(relation("merged", rows), [middle])]
    apply_display_subgroups([g], history)
    assert g["display_subgroups"] == [
        {"oa_row_ids": ["o0", "o1"], "bank_row_ids": ["x"]},
        {"oa_row_ids": ["o2", "o3"], "bank_row_ids": ["y"]},
    ]
    # After withdrawal the middle snapshot cannot use the later merged event.
    restored = group([a, b, c, d, x, y], "reused")
    apply_display_subgroups([restored], history)
    assert restored["display_subgroups"] == g["display_subgroups"]


def test_ambiguous_many_to_many_stays_shared_and_batch_is_not_split():
    rows = [row("oa", "a", 100), row("oa", "b", 100), row("bank", "x", 40), row("bank", "y", 60)]
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [{"oa_row_ids": ["a", "b"], "bank_row_ids": ["x", "y"]}]
    g["bank_batches"] = [{"member_ids": ["x", "y"]}]
    history = [event(relation("merged", rows), [relation("a", [rows[0], rows[2]]), relation("b", [rows[1], rows[3]])])]
    apply_display_subgroups([g], history)
    assert len(g["display_subgroups"]) == 1


def test_typed_identity_does_not_drop_bank_with_same_id_as_oa():
    rows = [row("oa", "same", 100), row("oa", "other", 200), row("bank", "same", 100), row("bank", "b", 200)]
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [
        {"oa_row_ids": ["same"], "bank_row_ids": ["same"]},
        {"oa_row_ids": ["other"], "bank_row_ids": ["b"]},
    ]


@pytest.mark.parametrize(
    "oa_amounts,bank_amounts,expected",
    [
        ([100, 100], [40, 60], {}),
        ([100, 200], [100, 100, 200], {"o1": ["b2"]}),
        ([100, 200], [100, 40, 60, 200], {"o0": ["b0"], "o1": ["b3"]}),
    ],
)
def test_alignment_never_uses_same_subset_for_duplicate_oa_or_overallocates(oa_amounts, bank_amounts, expected):
    rows = [row("oa", f"o{i}", a) for i, a in enumerate(oa_amounts)] + [
        row("bank", f"b{i}", a) for i, a in enumerate(bank_amounts)
    ]
    result = WorkbenchRelationAlignmentService().align_relation(
        rows_by_id={r["id"]: r for r in rows}, relation=relation("c", rows)
    )
    assert {link["oa_row_id"]: link["bank_row_ids"] for link in result["links"]} == expected


def test_empty_and_expense_item_groups_are_not_repartitioned():
    g = group([row("oa", "a", 1), row("oa", "b", 2), row("bank", "c", 3)])
    g["oa_rows"][0]["expense_items"] = [{"id": "item"}]
    original = deepcopy(g)
    apply_display_subgroups([], [])
    apply_display_subgroups([g], [])
    assert g == original

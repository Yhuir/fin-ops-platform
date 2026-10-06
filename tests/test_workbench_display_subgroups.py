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


def installment_rows():
    return [
        {**row("oa", "prepay", 8000), "application_date": "2026-08-14", "reason": "合同16000元，预付款50%", "counterparty_name": "测试设备有限公司"},
        {**row("oa", "final", 8000), "application_date": "2026-08-24", "reason": "设备配件，50%尾款", "counterparty_name": "测试设备有限公司"},
        {**row("bank", "bank-prepay", 8000), "trade_time": "2026-08-14 10:17:33", "remark": "货款", "counterparty_name": "测试设备有限公司"},
        {**row("bank", "bank-final", 8000), "trade_time": "2026-08-24 11:25:34", "remark": "货款（50%尾款）", "counterparty_name": "测试设备有限公司"},
        row("invoice", "shared-invoice", 16000),
    ]


@pytest.mark.parametrize("reverse", [False, True])
def test_installments_realign_overallocated_history_and_keep_shared_invoice(reverse):
    rows = installment_rows()
    old = relation("old", [rows[0], *rows[2:]])
    if reverse:
        rows.reverse()
    g = group(rows)
    before = deepcopy(g)
    history = [event(relation("merged", rows), [old])]
    apply_display_subgroups([g], history)
    assert {tuple(part["oa_row_ids"]): part["bank_row_ids"] for part in g.pop("display_subgroups")} == {
        ("prepay",): ["bank-prepay"], ("final",): ["bank-final"],
    }
    assert g == before


def test_installments_without_history_use_the_same_alignment():
    rows = installment_rows()
    result = WorkbenchRelationAlignmentService().align_relation(
        rows_by_id={r["id"]: r for r in rows}, relation=relation("c", rows),
    )
    assert {r["oa_row_id"]: r["bank_row_ids"] for r in result["links"]} == {
        "prepay": ["bank-prepay"], "final": ["bank-final"],
    }
    assert result["unresolved_row_ids"] == []


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
        {"resolved": True, "oa_row_ids": [f"o{i}"], "bank_row_ids": [f"b{i * 2}", f"b{i * 2 + 1}"]} for i in range(3)
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
        {"resolved": True, "oa_row_ids": ["o0", "o1"], "bank_row_ids": ["x"]},
        {"resolved": True, "oa_row_ids": ["o2", "o3"], "bank_row_ids": ["y"]},
    ]
    # After withdrawal the middle snapshot cannot use the later merged event.
    restored = group([a, b, c, d, x, y], "reused")
    apply_display_subgroups([restored], history)
    assert restored["display_subgroups"] == g["display_subgroups"]


def test_ambiguous_many_to_many_stays_shared_and_batch_cannot_override_alignment():
    rows = [row("oa", "a", 100), row("oa", "b", 100), row("bank", "x", 40), row("bank", "y", 60)]
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [{"resolved": False, "oa_row_ids": ["a", "b"], "bank_row_ids": ["x", "y"]}]
    g["bank_batches"] = [{"member_ids": ["x", "y"]}]
    history = [event(relation("merged", rows), [relation("a", [rows[0], rows[2]]), relation("b", [rows[1], rows[3]])])]
    apply_display_subgroups([g], history)
    # Historical membership alone does not prove two partial-payment owners.
    assert g["display_subgroups"] == [{"resolved": False, "oa_row_ids": ["a", "b"], "bank_row_ids": ["x", "y"]}]


def test_typed_identity_does_not_drop_bank_with_same_id_as_oa():
    rows = [row("oa", "same", 100), row("oa", "other", 200), row("bank", "same", 100), row("bank", "b", 200)]
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [
        {"resolved": True, "oa_row_ids": ["same"], "bank_row_ids": ["same"]},
        {"resolved": True, "oa_row_ids": ["other"], "bank_row_ids": ["b"]},
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


@pytest.mark.parametrize("value,expected", [("预付款50%", "advance"), ("50%尾款", "final"), ("预付款50%，尾款50%", ""), ("尚未支付尾款", ""), ("货款", "")])
def test_only_unambiguous_payment_phase_is_evidence(value, expected):
    from fin_ops_platform.services.workbench_relation_alignment_service import payment_phase
    assert payment_phase(value) == expected


def test_duplicate_same_day_without_phase_stays_unresolved():
    rows = installment_rows()[:4]
    for r in rows:
        r.update(application_date="2026-08-24", trade_time="2026-08-24 11:25:34", reason="货款", remark="货款")
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [{"resolved": False, "oa_row_ids": ["prepay", "final"], "bank_row_ids": ["bank-prepay", "bank-final"]}]


def test_balanced_but_contradicted_historical_pair_is_rechecked():
    rows = installment_rows()
    history = [event(relation("merged", rows), [relation("wrong", [rows[0], rows[3]])])]
    g = group(rows)
    apply_display_subgroups([g], history)
    assert g["display_subgroups"] == [
        {"resolved": True, "oa_row_ids": ["prepay"], "bank_row_ids": ["bank-prepay"]},
        {"resolved": True, "oa_row_ids": ["final"], "bank_row_ids": ["bank-final"]},
    ]



def test_explicit_partial_bank_source_is_not_replaced_by_equal_amount_guess():
    rows = [row("oa", "a", 100), row("oa", "b", 40), {**row("bank", "x", 40), "detail_fields": {"source_oa_row_id": "a"}}]
    g = group(rows)
    apply_display_subgroups([g], [])
    assert g["display_subgroups"] == [
        {"resolved": True, "oa_row_ids": ["a"], "bank_row_ids": ["x"]},
        {"resolved": False, "oa_row_ids": ["b"], "bank_row_ids": []},
    ]


def test_derived_display_source_is_not_promoted_to_explicit_bank_binding():
    rows = installment_rows()
    for bank in rows[2:4]:
        bank["source_oa_id"] = "prepay"
        bank["source_oa_row_id"] = "prepay"
    g = group(rows)
    apply_display_subgroups([g], [])
    assert [s["bank_row_ids"] for s in g["display_subgroups"]] == [["bank-prepay"], ["bank-final"]]


def test_payment_evidence_search_is_bounded_and_never_returns_partial_choices():
    from datetime import date
    from decimal import Decimal

    from fin_ops_platform.services.workbench_relation_alignment_service import PaymentEvidence, evidenced_payment_pairs
    oa = [PaymentEvidence(str(i), Decimal(1), payee="相同收款方", day=date(2026, 8, 1)) for i in range(150)]
    banks = [PaymentEvidence(str(i), Decimal(1), payee="相同收款方", day=date(2026, 8, 1)) for i in range(150)]
    result = evidenced_payment_pairs(oa, banks)
    assert result.resource_limited and result.pairs == {}


def test_invoice_scopes_preserve_merged_relations_without_inventing_equal_amount_owners():
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    equipment = installment_rows()
    etc = [row("oa", "etc-oa", "1711.33"), row("bank", "etc-bank", "1711.33"), row("invoice", "etc-invoice", "1711.33")]
    rows = [*etc, *equipment]
    g = group(rows)
    original = deepcopy(g)
    previous = [relation("equipment", equipment), relation("etc", etc)]
    history = [event(relation("merged", rows), previous)]
    apply_display_subgroups([g], history)
    apply_invoice_display_scopes([g], history)
    assert g["invoice_display_scopes"] == [
        {"oa_row_ids": ["etc-oa"], "bank_row_ids": ["etc-bank"], "invoice_row_ids": ["etc-invoice"]},
        {"oa_row_ids": ["prepay", "final"], "bank_row_ids": ["bank-prepay", "bank-final"], "invoice_row_ids": ["shared-invoice"]},
    ]
    g.pop("invoice_display_scopes")
    g.pop("display_subgroups")
    assert g == original
    unproven = group(rows)
    apply_invoice_display_scopes([unproven], [])
    assert "invoice_display_scopes" not in unproven


def test_invoice_scopes_reject_overallocated_history_and_stale_members():
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    rows = installment_rows()
    invalid = relation("old", [rows[0], *rows[2:]])
    g = group(rows)
    apply_invoice_display_scopes([g], [event(relation("merged", rows), [invalid])])
    assert "invoice_display_scopes" not in g
    stale = relation("merged", rows[:-1])
    apply_invoice_display_scopes([g], [event(stale, [invalid])])
    assert "invoice_display_scopes" not in g


@pytest.mark.parametrize("conflict", ["invoice_source", "bank_source", "overlap", "unknown_amount"])
def test_invoice_scopes_do_not_publish_conflicting_coverage(conflict):
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    a = [row("oa", "oa-a", 100), row("bank", "bank-a", 100), row("invoice", "invoice-a", 100)]
    b = [row("oa", "oa-b", 100), row("bank", "bank-b", 100), row("invoice", "invoice-b", 100)]
    if conflict == "invoice_source":
        a[2]["source_oa_id"] = "oa-b"
    elif conflict == "bank_source":
        a[1]["detail_fields"] = {"source_oa_row_id": "oa-b"}
    elif conflict == "unknown_amount":
        a[0]["amount"] = None
    before = [relation("a", a), relation("b", b)]
    if conflict == "overlap":
        before.append(relation("duplicate", a))
    g = group(a + b)
    apply_invoice_display_scopes([g], [], before_relations=before)
    assert "invoice_display_scopes" not in g


def test_invoice_scope_keeps_complete_parent_when_older_history_overallocated_one_oa():
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    equipment = installment_rows()
    etc = [row("oa", "etc-oa", "1711.33"), row("bank", "etc-bank", "1711.33"), row("invoice", "etc-invoice", "1711.33")]
    old = relation("equipment", [equipment[0], *equipment[2:]])
    complete = relation("equipment", equipment)
    history = [event(complete, [old])]
    previous = [complete, relation("etc", etc)]
    preview = group(equipment + etc)
    apply_invoice_display_scopes([preview], history, before_relations=previous)
    assert preview["invoice_display_scopes"][0]["oa_row_ids"] == ["prepay", "final"]
    assert preview["invoice_display_scopes"][0]["invoice_row_ids"] == ["shared-invoice"]
    published = group(equipment + etc)
    apply_invoice_display_scopes([published], history + [event(relation("merged", equipment + etc), previous)])
    assert published["invoice_display_scopes"] == preview["invoice_display_scopes"]


def test_late_shared_invoice_does_not_belong_to_other_newly_added_oa():
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    may = row('oa', 'may', '2329.32')
    june = row('oa', 'june', '4426.11')
    banks = [row('bank', 'may-bank', '2329.32'), row('bank', 'june-bank', '4426.11')]
    invoice = row('invoice', 'shared', '6755.43')
    rows = [may, june, *banks, invoice]
    previous = [relation('may-batch', [banks[0]]), relation('june-linked', [june, banks[1]])]
    history = [event(relation('merged', rows), previous)]
    published = group(rows)
    apply_invoice_display_scopes([published], history)
    assert 'invoice_display_scopes' not in published
    preview = group(rows)
    apply_invoice_display_scopes([preview], [], before_relations=previous)
    assert preview == published


def test_late_shared_invoice_remains_shared_inside_subsequent_unrelated_merge():
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    a = [row('oa', 'may', 20), row('oa', 'june', 40), row('bank', 'b', 60), row('invoice', 'i', 60)]
    other = [row('oa', 'other', 90), row('bank', 'other-bank', 90), row('invoice', 'other-invoice', 90)]
    inner = relation('inner', a)
    history = [event(inner, [relation('old', a[:3])]), event(relation('merged', a + other), [inner, relation('other', other)])]
    g = group(a + other)
    apply_invoice_display_scopes([g], history)
    assert g['invoice_display_scopes'] == [
        {'oa_row_ids': ['may', 'june'], 'bank_row_ids': ['b'], 'invoice_row_ids': ['i']},
        {'oa_row_ids': ['other'], 'bank_row_ids': ['other-bank'], 'invoice_row_ids': ['other-invoice']},
    ]


def interest_batches():
    amounts = [
        ['47.33', '268.33', '828.33', '427.78', '38.89', '236.44', '202.22', '280.00'],
        ['917.08', '61.14', '916.22', '361.67', '602.78', '120.56', '482.22', '964.44'],
    ]
    oa = [row('oa', 'may', '2329.32'), row('oa', 'june', '4426.11')]
    banks = [[{**row('bank', f'b{month}-{i}', value), 'display_batch_id': f'batch-{month}',
               'currency': 'CNY', 'counterparty_name': '贷款账户'} for i, value in enumerate(values)]
             for month, values in enumerate(amounts)]
    rows = [*oa, *banks[1], *banks[0], row('invoice', 'shared', '6755.43')]
    previous = [relation('old-june', [oa[1], *banks[1]]), relation('may-batch', banks[0])]
    return rows, previous


@pytest.mark.parametrize('reverse', [False, True])
def test_confirmed_eight_payment_batches_align_despite_display_name_variants(reverse):
    from fin_ops_platform.services.workbench_bank_folds import apply_bank_folds
    from fin_ops_platform.services.workbench_display_subgroups import apply_invoice_display_scopes

    rows, previous = interest_batches()
    rows[0]['counterparty_name'] = '贷款帐户'
    rows[1]['counterparty_name'] = '银行'
    if reverse:
        rows.reverse()
    g = group(rows)
    g['group_id'] = 'case:merged'
    original = deepcopy(g)
    history = [event(relation('merged', rows), previous)]
    for _ in range(2):
        apply_display_subgroups([g], history)
        apply_invoice_display_scopes([g], history)
        apply_bank_folds([g])
        assert {tuple(p['oa_row_ids']): set(p['bank_row_ids']) for p in g['display_subgroups']} == {
            ('may',): {f'b0-{i}' for i in range(8)}, ('june',): {f'b1-{i}' for i in range(8)},
        }
        assert all(p['resolved'] for p in g['display_subgroups'])
        assert len(g['bank_folds']) == 2
        assert 'invoice_display_scopes' not in g
        assert {k: v for k, v in g.items() if k not in {'display_subgroups', 'bank_folds'}} == original
    preview = deepcopy(original)
    apply_display_subgroups([preview], [], before_relations=previous)
    assert preview['display_subgroups'] == g['display_subgroups']


def test_unique_whole_batches_align_without_subset_search_or_history(monkeypatch):
    rows, _ = interest_batches()
    for r in rows:
        r.pop('counterparty_name', None)
    def reject_subset(**kwargs):
        raise AssertionError('Intact matching batches must not run bank subset search')
    monkeypatch.setattr(WorkbenchRelationAlignmentService, '_unique_subset_matches', reject_subset)
    g = group(rows)
    apply_display_subgroups([g], [])
    assert [p['resolved'] for p in g['display_subgroups']] == [True, True]


@pytest.mark.parametrize('conflict', ['currency', 'direction', 'account', 'owner', 'payee', 'duplicate'])
def test_batch_alignment_does_not_override_conflicts_or_ambiguity(conflict):
    rows, _ = interest_batches()
    for r in rows:
        r.pop('counterparty_name', None)
    banks = [r for r in rows if r['type'] == 'bank' and r['display_batch_id'] == 'batch-1']
    if conflict == 'currency':
        banks[0]['currency'] = 'USD'
    elif conflict == 'direction':
        banks[0]['txn_direction'] = 'inflow'
    elif conflict == 'account':
        rows[1]['detail_fields'] = {'收款账号': '111'}
        banks[0]['detail_fields'] = {'counterparty_account_no': '222'}
    elif conflict == 'owner':
        banks[0]['detail_fields'] = {'source_oa_row_id': 'may'}
    elif conflict == 'payee':
        rows[1]['counterparty_name'] = '另一家公司'
        banks[0]['counterparty_name'] = '实际收款方'
    else:
        rows.append(row('oa', 'duplicate-june', '4426.11'))
    g = group(rows)
    apply_display_subgroups([g], [])
    assert not any(p['resolved'] and p['oa_row_ids'] == ['june'] and len(p['bank_row_ids']) == 8
                   for p in g['display_subgroups'])


def test_historical_batch_still_rejects_account_conflict():
    rows, previous = interest_batches()
    rows[1]['detail_fields'] = {'收款账号': '111'}
    rows[2]['detail_fields'] = {'counterparty_account_no': '222'}
    g = group(rows)
    apply_display_subgroups([g], [event(relation('merged', rows), previous)])
    assert not any(p['resolved'] and p['oa_row_ids'] == ['june'] for p in g['display_subgroups'])


def test_partial_batch_never_imports_members_from_another_relation():
    rows, _ = interest_batches()
    # Only current relation members are available, even if provenance is shared.
    removed = rows.pop(2)
    g = group(rows)
    original = deepcopy(g)
    apply_display_subgroups([g], [])
    assert all(removed['id'] not in p['bank_row_ids'] for p in g['display_subgroups'])
    assert not any(p['resolved'] and p['oa_row_ids'] == ['june'] for p in g['display_subgroups'])
    assert {k: v for k, v in g.items() if k != 'display_subgroups'} == original


def test_same_total_batches_do_not_pick_first_candidate():
    oa = [row('oa', 'a', 100), row('oa', 'b', 200)]
    banks = [{**row('bank', f'{batch}-{i}', value), 'display_batch_id': batch}
             for batch in ['first', 'second'] for i, value in enumerate([10, 20, 70])]
    g = group([*oa, *banks])
    apply_display_subgroups([g], [])
    assert not any(p['resolved'] and p['oa_row_ids'] == ['a'] for p in g['display_subgroups'])


def test_large_batches_use_whole_totals_without_combinatorial_search(monkeypatch):
    oa = [row('oa', 'a', 500), row('oa', 'b', 1000)]
    banks = [{**row('bank', f'{batch}-{i}', value), 'display_batch_id': batch}
             for batch, value in [('first', 1), ('second', 2)] for i in range(500)]
    def reject_subset(**kwargs):
        raise AssertionError('Whole batch lookup must not enumerate subsets')
    monkeypatch.setattr(WorkbenchRelationAlignmentService, '_unique_subset_matches', reject_subset)
    g = group([*oa, *banks])
    apply_display_subgroups([g], [])
    assert [(p['oa_row_ids'], len(p['bank_row_ids']), p['resolved']) for p in g['display_subgroups']] == [
        (['a'], 500, True), (['b'], 500, True),
    ]

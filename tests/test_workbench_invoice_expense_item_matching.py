from copy import deepcopy

import pytest
from fin_ops_platform.services.workbench_invoice_expense_item_matching import plan_invoice_expense_assignments


def oa(amount="34", owner="oa-1", item="item-1"):
    return {"id": owner, "expense_items": [{"id": item, "amount": amount}], "currency": "CNY"}


def invoice(amount="34", key="inv-1", **fields):
    return {"id": key, "invoice_type": "input", "total_with_tax": amount, "currency": "CNY",
            "source_links": [{"source_type": "manual_invoice_import"}], **fields}


def test_unique_34_invoice_is_assigned_with_or_without_supporting_document():
    row = oa()
    for documents in ([], [{"id": "document"}]):
        row["expense_items"][0]["supporting_documents"] = documents
        assert plan_invoice_expense_assignments([row], [invoice()]) == {"inv-1": [("oa-1", "item-1")]}


def test_multi_oa_437_regression_preserves_six_existing_links():
    rows = [oa(), oa("351", "oa-2", "item-2"), oa("52", "oa-3", "item-3")]
    invoices = [invoice()]
    for index, (amount, owner, item) in enumerate([
        ("241", "oa-2", "item-2"), ("110", "oa-2", "item-2"),
        ("25.2", "oa-3", "item-3"), (".8", "oa-3", "item-3"),
        ("25.2", "oa-3", "item-3"), (".8", "oa-3", "item-3"),
    ]):
        invoices.append(invoice(amount, f"existing-{index}", source_links=[{
            "source_type": "oa_expense_item_invoice", "derived_from_oa_id": owner,
            "source_expense_item_id": item,
        }]))
    before = deepcopy(invoices)
    for ordered in (invoices, list(reversed(invoices))):
        assert plan_invoice_expense_assignments(rows, ordered) == {"inv-1": [("oa-1", "item-1")]}
    assert invoices == before


def test_duplicate_amounts_are_not_broken_by_order():
    assert plan_invoice_expense_assignments([oa(), oa(owner="oa-2", item="item-2")], [invoice()]) == {}
    assert plan_invoice_expense_assignments([oa()], [invoice(), invoice(key="inv-2")]) == {}


def test_only_whole_remainder_can_fill_one_item():
    assert plan_invoice_expense_assignments([oa()], [invoice("20"), invoice("14", "inv-2")]) == {
        "inv-1": [("oa-1", "item-1")], "inv-2": [("oa-1", "item-1")],
    }
    assert plan_invoice_expense_assignments([oa()], [invoice("20"), invoice("14", "inv-2"), invoice("5", "inv-3")]) == {}


@pytest.mark.parametrize("amount", [None, "", "invalid", "NaN", "Infinity", "-34", "0", "34.001"])
def test_invalid_or_nonpositive_money_is_not_assigned(amount):
    assert plan_invoice_expense_assignments([oa()], [invoice(amount)]) == {}


@pytest.mark.parametrize("fields", [
    {"currency": "USD"}, {"invoice_type": "output"}, {"source_kind": "etc_invoice_summary"},
    {"etc_invoice_id": "etc-1"},
    {"source_links": [{"source_type": "oa_expense_item_invoice", "source_expense_item_id": "old"}]},
    {"source_links": [{"source_type": "oa_attachment_invoice", "derived_from_oa_id": "different-oa"}]},
])
def test_other_owner_special_type_or_currency_is_not_overwritten(fields):
    assert plan_invoice_expense_assignments([oa()], [invoice(**fields)]) == {}


def test_partially_covered_item_uses_unique_residual_amount():
    existing = invoice("10", "old", source_links=[{
        "source_type": "oa_expense_item_invoice", "derived_from_oa_id": "oa-1", "source_expense_item_id": "item-1",
    }])
    assert plan_invoice_expense_assignments([oa()], [existing, invoice("24")]) == {"inv-1": [("oa-1", "item-1")]}


def owned_invoice(amount, key, targets=("item-1",), **fields):
    return invoice(amount, key, source_links=[{
        "source_type": "oa_attachment_invoice", "derived_from_oa_id": "oa-1", "source_expense_item_id": target,
    } for target in targets], **fields)


def test_71_partial_three_tickets_preserves_separate_25_item_and_is_idempotent():
    row = oa("71")
    row["expense_items"].append({"id": "item-25", "amount": "25"})
    rows = [owned_invoice("23", "first"), owned_invoice("25", "separate", ("item-25",)),
            invoice("23", "second"), invoice("25", "third")]
    before = deepcopy(rows)
    expected = {"second": [("oa-1", "item-1")], "third": [("oa-1", "item-1")]}
    for ordered in (rows, list(reversed(rows)), [*rows, rows[0]]):
        assert plan_invoice_expense_assignments([row], ordered) == expected
    assert rows == before
    assert plan_invoice_expense_assignments([row], [rows[0], rows[1], owned_invoice("23", "second"), owned_invoice("25", "third")]) == {}


@pytest.mark.parametrize("amount", ["71", "72", "0", "NaN", "-23"])
def test_closed_overpaid_or_invalid_owned_amount_does_not_take_more(amount):
    assert plan_invoice_expense_assignments([oa("71")], [owned_invoice(amount, "owned"), invoice("48")]) == {}


def test_shared_invoice_has_no_invented_per_item_allocation():
    row = oa("71")
    row["expense_items"].append({"id": "item-2", "amount": "71"})
    assert plan_invoice_expense_assignments([row], [owned_invoice("23", "shared", ("item-1", "item-2")), invoice("48")]) == {}


def test_partial_remainder_ambiguity_currency_and_extra_tickets_are_not_guessed():
    partial = owned_invoice("23", "owned")
    assert plan_invoice_expense_assignments([oa("71"), oa("48", "other", "other-item")], [partial, invoice("48")]) == {}
    assert plan_invoice_expense_assignments([oa("71")], [partial, invoice("48", currency="USD")]) == {}
    assert plan_invoice_expense_assignments([oa("71")], [partial, invoice("23", "a"), invoice("25", "b"), invoice("1", "extra")]) == {}


def test_empty_inputs():
    assert plan_invoice_expense_assignments([], [invoice()]) == {}
    assert plan_invoice_expense_assignments([oa()], []) == {}


def test_formally_covered_item_cannot_take_another_same_amount_invoice():
    owned = invoice(key="owned", source_links=[{
        "source_type": "oa_expense_item_invoice", "derived_from_oa_id": "oa-1",
        "source_expense_item_id": "item-1",
    }])
    assert plan_invoice_expense_assignments([oa()], [owned, invoice()]) == {}


def test_large_same_amount_bucket_stays_ambiguous():
    rows = [oa(owner=f"oa-{index}", item=f"item-{index}") for index in range(1000)]
    invoices = [invoice(key=f"invoice-{index}") for index in range(1000)]
    assert plan_invoice_expense_assignments(rows, invoices) == {}

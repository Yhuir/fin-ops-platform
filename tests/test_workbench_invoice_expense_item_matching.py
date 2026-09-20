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


def test_partially_covered_item_does_not_use_residual_amount():
    existing = invoice("10", "old", source_links=[{
        "source_type": "oa_expense_item_invoice", "derived_from_oa_id": "oa-1", "source_expense_item_id": "item-1",
    }])
    assert plan_invoice_expense_assignments([oa()], [existing, invoice("24")]) == {}


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

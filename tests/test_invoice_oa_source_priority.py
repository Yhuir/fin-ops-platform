from copy import deepcopy

import pytest
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_expense_item_links import (
    effective_invoice_source_links,
    effective_invoice_source_tags,
    replace_explicit_expense_item_links,
)
from fin_ops_platform.services.oa_attachment_invoice_linking import canonical_oa_expense_item_ids
from fin_ops_platform.services.postgres_repositories.invoice_import_page_audit import _canonical_invoice_issues
from fin_ops_platform.services.workbench_invoice_expense_item_assignment_service import (
    WorkbenchInvoiceExpenseItemAssignmentError,
)
from fin_ops_platform.services.workbench_invoice_expense_item_matching import plan_invoice_expense_assignments

from tests.test_audit_invoice_import_page import FakeConnection
from tests.test_oa_attachment_invoice_promotion_service import _attachment, _invoice

OA_LINK = {
    "source_type": "oa_attachment_invoice", "derived_from_oa_id": "oa-1",
    "source_expense_item_id": "oa-1:item:0", "source_attachment_key": "attachment-1",
}
MANUAL_LINK = {"source_type": "manual_invoice_import", "batch_id": "batch-1"}
WRONG_LINK = {
    "source_type": "oa_expense_item_invoice", "derived_from_oa_id": "oa-2",
    "source_expense_item_id": "oa-2:item:0",
}


def test_oa_replaces_manual_ownership_without_removing_independent_etc_sources():
    etc = {"source_type": "etc_invoice_import", "source_id": "etc-1"}
    links = [MANUAL_LINK, WRONG_LINK, OA_LINK, etc]
    before = deepcopy(links)
    assert effective_invoice_source_links(links) == [OA_LINK, etc]
    assert effective_invoice_source_links(effective_invoice_source_links(links)) == [OA_LINK, etc]
    assert effective_invoice_source_tags(["人工导入", "OA附件", "ETC"], links) == ["OA附件", "ETC"]
    assert links == before


def test_attachment_owner_wins_over_stored_wrong_manual_assignment():
    row = {"id": "oa-1", "expense_items": [{"id": "oa-1:item:0"}]}
    assert canonical_oa_expense_item_ids(oa_row=row, invoice_row={"source_links": [WRONG_LINK, OA_LINK]}) == ["oa-1:item:0"]
    with pytest.raises(ValueError, match="不能人工更改"):
        replace_explicit_expense_item_links([OA_LINK], case_id="CASE-1", targets=[("oa-2", "item-b")], entry_method="manual")


@pytest.mark.parametrize("correction", [False, True])
def test_assignment_api_domain_rejects_both_initial_and_correction_for_oa_invoice(correction):
    from tests.test_workbench_invoice_expense_item_assignment_service import (
        WorkbenchInvoiceExpenseItemAssignmentServiceTests,
    )
    fixture = WorkbenchInvoiceExpenseItemAssignmentServiceTests()
    service, invoices, _, audit = fixture._fixture(source_links=[OA_LINK])
    request = fixture._payload()
    if correction:
        request.update(previous_targets=[{"oa_row_id": "oa-1", "expense_item_id": "oa-1:item:0"}])
    with pytest.raises(WorkbenchInvoiceExpenseItemAssignmentError) as caught:
        service.assign(request, actor_id="user", tenant_id="default", request_id="immutable")
    assert caught.value.code == "invoice_oa_source_immutable"
    assert not invoices.updates
    assert not audit.events


def test_unresolved_oa_attachment_never_enters_amount_inference():
    rows = [{"id": "oa-1", "expense_items": [{"id": "oa-1:item:0", "amount": "34"}]}]
    invoice = {"id": "invoice-1", "invoice_type": "input", "total_with_tax": "34", "source_links": [
        {"source_type": "oa_attachment_invoice", "derived_from_oa_id": "oa-1"},
    ]}
    assert plan_invoice_expense_assignments(rows, [invoice]) == {}


def test_oa_promotion_takes_over_existing_invoice_and_is_idempotent():
    payload = _attachment("26539150014000401220", "145.00", "oa-1:item:0", "ticket.pdf")
    invoice = _invoice(payload)
    invoice.source_links = [MANUAL_LINK, WRONG_LINK]
    invoice.tags = ["人工导入"]
    invoice.source_batch_id = "batch-1"
    invoice.oa_form_id = "oa-2"
    service = ImportNormalizationService(existing_invoices=[invoice])
    updated = service.upsert_oa_attachment_invoice(payload, oa_row_id="oa-1", source_workbench_row_id="oa-1")
    assert updated.id == invoice.id
    assert {link["source_type"] for link in updated.source_links} == {"oa_attachment_invoice"}
    assert updated.source_batch_id == "batch-1"
    assert updated.oa_form_id == "oa-1"
    assert "人工导入" not in updated.tags
    before = deepcopy(updated)
    service.upsert_oa_attachment_invoice(payload, oa_row_id="oa-1", source_workbench_row_id="oa-1")
    assert updated == before


def test_import_audit_uses_historical_rows_after_oa_takes_over():
    data = FakeConnection()
    invoice = data.invoices[0]
    invoice["source_links"] = [OA_LINK]
    invoice["raw_payload"]["normalized_payload"]["source_links"] = [OA_LINK]
    issues = _canonical_invoice_issues(data.batches, data.rows, data.invoices, known_batch_ids={"batch-1"})
    assert not issues
    data.rows[0]["source_unique_key"] = "wrong-invoice"
    issues = _canonical_invoice_issues(data.batches, data.rows, data.invoices, known_batch_ids={"batch-1"})
    assert "invoice_import_row_identity_mismatch" in {issue.code for issue in issues}


def test_oa_source_moves_invoice_from_wrong_group_and_settles_before_bank_ambiguity():
    from dataclasses import replace

    from fin_ops_platform.services.workbench_free_matching_engine import (
        ActiveFormalRelationAnchor,
        FormalRelationFactBatch,
        FormalRelationReference,
        WorkbenchFreeMatchingEngine,
    )

    from tests.test_workbench_free_matching_engine import fact
    invoice = replace(fact("invoice", "invoice-1", 14500, references=(
        FormalRelationReference("attachment_source", "source:oa-new", "oa", "oa-new"),
    )), has_oa_attachment_source=True)
    invoice2 = replace(invoice, canonical_object_identity="invoice-2", row_id="invoice-2")
    facts = (fact("oa", "oa-old", 14500), fact("bank", "bank-old", 14500),
             fact("oa", "oa-new", 29000), invoice, invoice2)
    batch = FormalRelationFactBatch(facts=facts, active_relations=(
        ActiveFormalRelationAnchor("CASE-OLD", (("oa", "oa-old"), ("bank", "bank-old"), invoice.member_key)),
    ))
    result = WorkbenchFreeMatchingEngine().plan_relations(batch)
    assert result.source_reassignments == (("invoice-1", "CASE-OLD"),)
    owned = [plan for plan in result.plans if "oa-new" in plan.row_ids]
    assert len(owned) == 1
    assert set(owned[0].row_ids) == {"oa-new", "invoice-1", "invoice-2"}
    assert set(owned[0].oa_attachment_bindings) == {("oa-new", "invoice-1"), ("oa-new", "invoice-2")}


def test_repeating_same_source_target_adds_no_manual_edge():
    payload = _attachment("26539150014000401220", "145.00", "oa-1:item:0", "ticket.pdf")
    invoice = _invoice(payload)
    invoice.source_links = [OA_LINK]
    service = ImportNormalizationService(existing_invoices=[invoice])
    before = deepcopy(invoice)
    service.attach_source_links_to_invoices([invoice.id], source_links=[{
        "source_type": "oa_expense_item_invoice", "derived_from_oa_id": "oa-1", "source_expense_item_id": "oa-1:item:0",
    }], oa_form_id="oa-1")
    assert invoice == before

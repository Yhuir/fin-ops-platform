from __future__ import annotations

import unittest
from decimal import Decimal
from types import SimpleNamespace

from fin_ops_platform.domain.enums import BatchType, DifferenceReason
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.pending_invoice_service import (
    PendingInvoiceApplicationService,
    PendingInvoiceError,
    PendingInvoiceQueryService,
)
from fin_ops_platform.services.pending_invoice_status import pending_invoice_status_payload
from fin_ops_platform.services.project_costing import ProjectCostingService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


class InvoiceMissingAmountBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.imports = ImportNormalizationService()
        self.audit = AuditTrailService()
        self.matching = MatchingEngineService(self.imports)
        self.reconciliation = ManualReconciliationService(self.imports, self.matching, self.audit)
        self.ledgers = LedgerReminderService(self.imports, self.audit)

    def _import(self, kind: BatchType, row: dict[str, str]) -> str:
        preview = self.imports.preview_import(
            batch_type=kind, source_name="source-values.json", imported_by="reviewer", rows=[row],
        )
        self.imports.confirm_import(preview.id)
        return preview.row_results[0].linked_object_id

    def _invoice(self, number: str, *, kind: BatchType = BatchType.INPUT_INVOICE):
        invoice_id = self._import(kind, {
            "invoice_code": "SOURCE", "invoice_no": number, "counterparty_name": "Source Vendor", "amount": "100.00",
            "tax_amount": "13.00", "total_with_tax": "113.00", "invoice_date": "2026-10-01",
            "invoice_status_from_source": "valid",
        })
        return self.imports.get_invoice(invoice_id)

    def _bank(self, *, income: bool = False):
        bank_id = self._import(BatchType.BANK_TRANSACTION, {
            "account_no": "1234", "txn_date": "2026-10-01", "counterparty_name": "Source Vendor",
            "debit_amount": "" if income else "60.00", "credit_amount": "60.00" if income else "",
            "bank_serial_no": "BANK-SOURCE-1",
        })
        return self.imports.get_transaction(bank_id)

    def test_automatic_matching_excludes_missing_net_without_substituting_gross(self) -> None:
        missing = self._invoice("MISSING")
        missing.amount = missing.signed_amount = None
        known = self._invoice("KNOWN")
        run = self.matching.run(triggered_by="reviewer")
        self.assertEqual(run.invoice_count, 1)
        self.assertEqual({value for item in run.results for value in item.invoice_ids}, {known.id})
        self.assertIsNone(missing.amount)
        self.assertEqual(missing.total_with_tax, Decimal("113.00"))

    def test_manual_commands_reject_missing_net_before_writing_relations_or_balances(self) -> None:
        invoice = self._invoice("MISSING", kind=BatchType.OUTPUT_INVOICE)
        invoice.amount = invoice.signed_amount = None
        bank = self._bank(income=True)
        payable = self._invoice("PAYABLE")
        common = {"actor_id": "reviewer", "invoice_ids": [invoice.id], "transaction_ids": [bank.id]}
        actions = [
            lambda: self.reconciliation.confirm_manual_reconciliation(**common),
            lambda: self.reconciliation.confirm_difference_reconciliation(**common, difference_reason=DifferenceReason.ROUNDING),
            lambda: self.reconciliation.record_exception(**common, biz_side="receivable", exception_code="SO-A"),
            lambda: self.reconciliation.record_offline_reconciliation(**common, biz_side="receivable", amount="60", payment_method="cash", occurred_on="2026-10-01"),
            lambda: self.reconciliation.record_offset_reconciliation(actor_id="reviewer", receivable_invoice_ids=[invoice.id], payable_invoice_ids=[payable.id], reason="offset"),
        ]
        audit_before = len(self.audit.list_entries())
        for index, action in enumerate(actions):
            with self.subTest(action=index), self.assertRaisesRegex(ValueError, "has no source amount"):
                action()
            self.assertEqual(self.reconciliation.list_cases(), [])
            self.assertEqual(invoice.written_off_amount, Decimal("0"))
            self.assertEqual(bank.written_off_amount, Decimal("0"))
            self.assertEqual(len(self.audit.list_entries()), audit_before)

    def test_project_summary_marks_only_affected_side_unknown(self) -> None:
        service = ProjectCostingService(
            self.imports, self.reconciliation, self.ledgers,
            IntegrationHubService(self.imports, self.audit), self.audit,
        )
        project = service.create_project(actor_id="reviewer", project_code="P1", project_name="Project")
        invoice = self._invoice("MISSING")
        invoice.amount = invoice.signed_amount = None
        service.assign_project(actor_id="reviewer", object_type="invoice", object_id=invoice.id, project_id=project.id)
        known = self._invoice("KNOWN")
        service.assign_project(actor_id="reviewer", object_type="invoice", object_id=known.id, project_id=project.id)
        summary = service.list_project_summaries()[0]
        self.assertIsNone(summary.expense_amount)
        self.assertEqual(summary.income_amount, Decimal("0"))
        self.assertEqual(summary.invoice_count, 2)
        self.assertIsNone(service.build_project_hub()["totals"]["expense_amount"])

    def test_ledger_recalculation_does_not_overwrite_existing_balance_when_source_disappears(self) -> None:
        invoice = self._invoice("PARTIAL", kind=BatchType.OUTPUT_INVOICE)
        bank = self._bank(income=True)
        case = self.reconciliation.confirm_manual_reconciliation(
            actor_id="reviewer", invoice_ids=[invoice.id], transaction_ids=[bank.id],
        )
        ledger = self.ledgers.sync_from_case(case)[0]
        before_lines = [(line.object_id, line.applied_amount) for line in case.lines]
        invoice.amount = invoice.signed_amount = None
        with self.assertRaisesRegex(ValueError, "follow-up balance cannot be recalculated"):
            self.ledgers.sync_from_case(case)
        self.assertEqual(self.ledgers.get_ledger(ledger.id).open_amount, Decimal("40.00"))
        self.assertEqual([(line.object_id, line.applied_amount) for line in case.lines], before_lines)

    def test_pending_candidates_keep_missing_gross_visible_but_reject_amount_based_attachment(self) -> None:
        invoice = self._invoice("MISSING-GROSS")
        invoice.total_with_tax = None
        bank = self._bank()
        bank_reader = lambda ids: [self.imports.get_transaction(value) for value in ids]
        query = PendingInvoiceQueryService(
            import_service=self.imports, bank_units_by_ids=bank_reader,
            category_service=SimpleNamespace(bulk_get=lambda ids: {}), app_settings_provider=lambda: {},
        )
        rows = query.invoice_candidates(transaction_id=bank.id)["rows"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["total_with_tax"], "")
        self.assertEqual(rows[0]["remaining_amount"], "")
        self.assertEqual(rows[0]["candidate_status"], "conflict")
        self.assertEqual(rows[0]["conflict_reason"], "发票原件未提供价税合计")
        application = PendingInvoiceApplicationService(import_service=self.imports, bank_units_by_ids=bank_reader)
        with self.assertRaises(PendingInvoiceError) as raised:
            application.preview_attach_existing_invoice(transaction_id=bank.id, payload={"invoice_id": invoice.id})
        self.assertEqual(raised.exception.error_code, "invoice_total_missing")
        self.assertEqual(application.command_store, {})
        invoice.total_with_tax = Decimal("113.00")
        invoice.amount = invoice.signed_amount = None
        self.assertEqual(query.invoice_candidates(transaction_id=bank.id)["rows"][0]["total_with_tax"], "113.00")
        preview = application.preview_attach_existing_invoice(transaction_id=bank.id, payload={"invoice_id": invoice.id})
        self.assertTrue(preview["can_confirm"])
        self.assertEqual(preview["payment_impact"]["remaining_amount_after"], "53.00")

    def test_unknown_invoice_summary_keeps_actual_paid_amount_and_never_claims_settled(self) -> None:
        summary = PendingInvoiceQueryService._payment_summary_from_relation_context(
            {"linked_bank_transactions": [{"id": "bank-1", "amount": "60.00"}]},
            [{"total_with_tax": "100.00"}, {"total_with_tax": ""}],
        )
        self.assertEqual(summary["invoice_total"], "")
        self.assertEqual(summary["remaining_amount"], "")
        self.assertEqual(summary["paid_total"], "60.00")
        status = pending_invoice_status_payload(
            direction="expense", group=None, has_invoices=True, payment_summary=summary, matched_rule=None,
        )
        self.assertEqual(status["code"], "invoice_amount_missing")
        self.assertEqual(status["primary_action"], "view_relation")

    def test_pending_service_detail_uses_all_actual_lines_and_source_tax_text(self) -> None:
        invoice = self._invoice("ACTUAL-LINES")
        invoice.total_with_tax = None
        invoice.tax_amount = None
        invoice.tax_amount_text = "*"
        invoice.source_line_items = [
            {"taxable_item_name": "第一项", "amount": "40.00", "tax_amount_text": "*", "tax_rate": "免税"},
            {"taxable_item_name": "第二项", "amount": "60.00", "tax_amount": "0.00", "tax_rate": "0%"},
        ]
        query = PendingInvoiceQueryService(
            import_service=self.imports, bank_units_by_ids=lambda ids: [],
            category_service=SimpleNamespace(bulk_get=lambda ids: {}), app_settings_provider=lambda: {},
        )
        detail = query.invoice_detail(invoice.id)
        sections = detail["sections"]
        lines = [section for section in sections if section["title"].startswith("货物或应税劳务明细")]
        self.assertEqual([section["title"] for section in lines], ["货物或应税劳务明细 1", "货物或应税劳务明细 2"])
        money = next(section for section in sections if section["title"] == "金额与税额")
        self.assertIn({"label": "税额", "value": "*"}, money["fields"])
        self.assertIn({"label": "价税合计", "value": "—"}, money["fields"])
        self.assertIn({"label": "税额", "value": "*"}, lines[0]["fields"])
        self.assertIn({"label": "税额", "value": "0.00"}, lines[1]["fields"])
        self.assertIsNone(detail["invoice"]["total_with_tax"])


if __name__ == "__main__":
    unittest.main()

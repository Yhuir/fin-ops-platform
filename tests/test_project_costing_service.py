from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.integrations import IntegrationHubService
from fin_ops_platform.services.ledgers import LedgerReminderService
from fin_ops_platform.services.matching import MatchingEngineService
from fin_ops_platform.services.reconciliation import ManualReconciliationService


class ProjectCostingServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.import_service = ImportNormalizationService()
        self.audit_service = AuditTrailService()
        self.integration_service = IntegrationHubService(self.import_service, self.audit_service)
        self.matching_service = MatchingEngineService(self.import_service)
        self.reconciliation_service = ManualReconciliationService(
            self.import_service,
            self.matching_service,
            self.audit_service,
        )
        self.ledger_service = LedgerReminderService(
            self.import_service,
            self.audit_service,
        )

        from fin_ops_platform.services.project_costing import ProjectCostingService

        self.project_service = ProjectCostingService(
            self.import_service,
            self.reconciliation_service,
            self.ledger_service,
            self.integration_service,
            self.audit_service,
        )

    def test_manual_assignment_overrides_oa_and_existing_project_fields(self) -> None:
        self.integration_service.sync(scope="all", triggered_by="user_finance_01")
        invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "088001",
                    "invoice_no": "PROJ-PRIORITY-001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        invoice = self.import_service.get_invoice(invoice_ids[0])
        invoice.project_id = "proj_existing_001"
        invoice.oa_form_id = "OA-AF-001"

        project = self.project_service.create_project(
            actor_id="user_finance_01",
            project_code="PJT-MAN-001",
            project_name="人工指定项目",
        )
        assignment = self.project_service.assign_project(
            actor_id="user_finance_01",
            object_type="invoice",
            object_id=invoice.id,
            project_id=project.id,
            note="manual override",
        )

        effective_project = self.project_service.resolve_project_for_object("invoice", invoice.id)

        self.assertEqual(assignment.project_id, project.id)
        self.assertEqual(effective_project.id, project.id)
        self.assertEqual(self.audit_service.list_entries()[-1].action, "project_assignment_recorded")

    def test_project_summary_aggregates_income_expense_reconciled_and_open_amounts(self) -> None:
        project = self.project_service.create_project(
            actor_id="user_finance_01",
            project_code="PJT-SUM-001",
            project_name="归集测试项目",
        )
        output_invoice_ids = self._confirm(
            BatchType.OUTPUT_INVOICE,
            [
                {
                    "invoice_code": "088002",
                    "invoice_no": "PROJ-OUT-001",
                    "counterparty_name": "Project Client",
                    "amount": "100.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        input_invoice_ids = self._confirm(
            BatchType.INPUT_INVOICE,
            [
                {
                    "invoice_code": "088003",
                    "invoice_no": "PROJ-IN-001",
                    "counterparty_name": "Project Vendor",
                    "amount": "60.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        transaction_ids = self._confirm(
            BatchType.BANK_TRANSACTION,
            [
                {
                    "account_no": "62228888",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Project Client",
                    "debit_amount": "",
                    "credit_amount": "60.00",
                    "bank_serial_no": "PROJ-BANK-001",
                    "summary": "partial receipt",
                }
            ],
        )

        for invoice_id in [*output_invoice_ids, *input_invoice_ids]:
            self.project_service.assign_project(
                actor_id="user_finance_01",
                object_type="invoice",
                object_id=invoice_id,
                project_id=project.id,
            )
        self.project_service.assign_project(
            actor_id="user_finance_01",
            object_type="bank_transaction",
            object_id=transaction_ids[0],
            project_id=project.id,
        )

        case = self.reconciliation_service.confirm_manual_reconciliation(
            actor_id="user_finance_01",
            invoice_ids=output_invoice_ids,
            transaction_ids=transaction_ids,
            remark="project partial settlement",
        )
        ledgers = self.ledger_service.sync_from_case(case)

        summary = self.project_service.get_project_detail(project.id)["summary"]

        self.assertEqual(summary.income_amount, Decimal("100.00"))
        self.assertEqual(summary.expense_amount, Decimal("60.00"))
        self.assertEqual(summary.reconciled_amount, Decimal("60.00"))
        self.assertEqual(summary.open_ledger_amount, Decimal("40.00"))
        self.assertEqual(ledgers[0].source_case_id, case.id)

    def _confirm(self, batch_type: BatchType, rows: list[dict[str, str]]) -> list[str]:
        preview = self.import_service.preview_import(
            batch_type=batch_type,
            source_name=f"{batch_type.value}.json",
            imported_by="user_finance_01",
            rows=rows,
        )
        self.import_service.confirm_import(preview.id)
        if batch_type == BatchType.BANK_TRANSACTION:
            return [transaction.id for transaction in self.import_service.list_transactions()][-len(rows):]
        return [invoice.id for invoice in self.import_service.list_invoices()][-len(rows):]


if __name__ == "__main__":
    unittest.main()

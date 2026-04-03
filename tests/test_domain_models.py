from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import (
    DifferenceReason,
    IntegrationObjectType,
    IntegrationSource,
    IntegrationSyncStatus,
    InvoiceStatus,
    InvoiceType,
    ImportDecision,
    LedgerStatus,
    LedgerType,
    MatchingConfidence,
    MatchingResultType,
    ReconciliationCaseStatus,
    ReconciliationCaseType,
    ReminderStatus,
    TransactionDirection,
)
from fin_ops_platform.domain.models import (
    BankTransaction,
    Counterparty,
    ExceptionHandlingRecord,
    FollowUpLedger,
    IntegrationMapping,
    IntegrationSyncIssue,
    IntegrationSyncRun,
    ImportedBatch,
    ImportedBatchRowResult,
    Invoice,
    MatchingResult,
    MatchingRun,
    OfflineReconciliationRecord,
    OADocument,
    OffsetNote,
    ProjectAssignmentRecord,
    ProjectMaster,
    ProjectSummary,
    Reminder,
    ReconciliationCase,
    ReconciliationLine,
)


class DomainModelTests(unittest.TestCase):
    def test_invoice_tracks_outstanding_amount_and_project_metadata(self) -> None:
        counterparty = Counterparty(
            id="cp_001",
            name="Acme Supplies",
            normalized_name="acme supplies",
            counterparty_type="vendor",
            oa_external_id="OA-CP-001",
        )
        invoice = Invoice(
            id="inv_001",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="OUT-001",
            counterparty=counterparty,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            written_off_amount=Decimal("30.00"),
            project_id="proj_001",
            status=InvoiceStatus.PARTIALLY_RECONCILED,
        )

        self.assertEqual(invoice.outstanding_amount, Decimal("70.00"))
        self.assertEqual(invoice.project_id, "proj_001")
        self.assertEqual(invoice.counterparty.oa_external_id, "OA-CP-001")

    def test_reconciliation_case_sums_lines_and_flags_follow_up_when_difference_exists(self) -> None:
        case = ReconciliationCase(
            id="rc_001",
            case_type=ReconciliationCaseType.MANUAL,
            biz_side="receivable",
            counterparty_id="cp_001",
            total_amount=Decimal("100.00"),
            difference_amount=Decimal("1.00"),
            lines=[
                ReconciliationLine(
                    id="line_001",
                    reconciliation_case_id="rc_001",
                    object_type="invoice",
                    object_id="inv_001",
                    applied_amount=Decimal("60.00"),
                ),
                ReconciliationLine(
                    id="line_002",
                    reconciliation_case_id="rc_001",
                    object_type="bank_txn",
                    object_id="txn_001",
                    applied_amount=Decimal("39.00"),
                ),
            ],
        )

        self.assertEqual(case.applied_amount_total, Decimal("99.00"))
        self.assertTrue(case.requires_follow_up)

    def test_follow_up_ledger_carries_project_scope_for_future_costing(self) -> None:
        ledger = FollowUpLedger(
            id="ledger_001",
            ledger_type=LedgerType.PAYMENT_COLLECTION,
            source_object_type="invoice",
            source_object_id="inv_001",
            counterparty_id="cp_001",
            project_id="proj_001",
            open_amount=Decimal("70.00"),
            expected_date="2026-03-31",
            owner_id="user_finance_01",
            source_case_id="rc_001",
            status=LedgerStatus.OPEN,
        )

        self.assertEqual(ledger.project_id, "proj_001")
        self.assertEqual(ledger.open_amount, Decimal("70.00"))
        self.assertEqual(ledger.source_case_id, "rc_001")

    def test_bank_transaction_preserves_direction_and_remaining_amount(self) -> None:
        txn = BankTransaction(
            id="txn_001",
            account_no="62220001",
            txn_direction=TransactionDirection.INFLOW,
            counterparty_name_raw="Acme Supplies Ltd.",
            amount=Decimal("88.00"),
            signed_amount=Decimal("88.00"),
            written_off_amount=Decimal("20.00"),
        )

        self.assertEqual(txn.outstanding_amount, Decimal("68.00"))
        self.assertEqual(txn.txn_direction, TransactionDirection.INFLOW)

    def test_import_tracking_models_keep_unique_key_fingerprint_and_row_decision(self) -> None:
        batch = ImportedBatch(
            id="batch_001",
            batch_type="output_invoice",
            source_name="output-demo.json",
            imported_by="user_finance_01",
            row_count=5,
            success_count=2,
            error_count=1,
            duplicate_count=1,
            suspected_duplicate_count=1,
            updated_count=1,
            status="pending",
        )
        row = ImportedBatchRowResult(
            id="row_001",
            batch_id=batch.id,
            row_no=4,
            source_record_type="invoice",
            source_unique_key="033001:9001",
            data_fingerprint="fp_001",
            decision=ImportDecision.SUSPECTED_DUPLICATE,
            decision_reason="Fingerprint matched an existing invoice without official unique key.",
            linked_object_type="invoice",
            linked_object_id="inv_existing",
            raw_payload={"invoice_no": "9001"},
        )
        counterparty = Counterparty(
            id="cp_001",
            name="Acme Supplies",
            normalized_name="acme supplies",
            counterparty_type="vendor",
        )
        invoice = Invoice(
            id="inv_001",
            invoice_type=InvoiceType.OUTPUT,
            invoice_no="OUT-001",
            counterparty=counterparty,
            amount=Decimal("100.00"),
            signed_amount=Decimal("100.00"),
            source_unique_key="033001:9001",
            data_fingerprint="fp_001",
        )
        txn = BankTransaction(
            id="txn_001",
            account_no="62220001",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="Acme Supplies Ltd.",
            amount=Decimal("88.00"),
            signed_amount=Decimal("-88.00"),
            source_unique_key="SERIAL-001",
            data_fingerprint="fp_txn_001",
        )

        self.assertEqual(batch.duplicate_count, 1)
        self.assertEqual(batch.updated_count, 1)
        self.assertEqual(row.decision, ImportDecision.SUSPECTED_DUPLICATE)
        self.assertEqual(invoice.source_unique_key, "033001:9001")
        self.assertEqual(txn.data_fingerprint, "fp_txn_001")

    def test_integration_sync_models_track_external_mapping_and_retry_counts(self) -> None:
        project = ProjectMaster(
            id="proj_oa_001",
            project_code="PJT-001",
            project_name="华东改造项目",
            project_status="active",
            oa_external_id="OA-PROJ-001",
            department_name="交付中心",
            owner_name="张三",
        )
        document = OADocument(
            id="oa_doc_001",
            document_type="payment_request",
            oa_external_id="OA-PR-001",
            form_no="FKSQ-202603-001",
            title="供应商付款申请",
            applicant_name="李四",
            amount=Decimal("300.00"),
            counterparty_name="Acme Supplies",
            project_external_id="OA-PROJ-001",
            project_name="华东改造项目",
            form_status="approved",
            submitted_at="2026-03-26T10:00:00+00:00",
        )
        mapping = IntegrationMapping(
            id="map_001",
            source_system=IntegrationSource.OA,
            object_type=IntegrationObjectType.COUNTERPARTY,
            external_id="OA-CP-001",
            internal_object_type="counterparty",
            internal_object_id="cp_001",
            display_name="Acme Supplies",
            sync_status=IntegrationSyncStatus.SUCCEEDED,
        )
        run = IntegrationSyncRun(
            id="sync_001",
            source_system=IntegrationSource.OA,
            scope="all",
            triggered_by="user_finance_01",
            status=IntegrationSyncStatus.PARTIAL,
            pulled_count=5,
            success_count=4,
            failed_count=1,
            retry_of_run_id="sync_000",
            issues=[
                IntegrationSyncIssue(
                    id="issue_001",
                    run_id="sync_001",
                    object_type=IntegrationObjectType.EXPENSE_CLAIM,
                    external_id="OA-CL-009",
                    title="缺少申请人",
                    reason="applicant_name is required",
                )
            ],
        )

        self.assertEqual(project.oa_external_id, "OA-PROJ-001")
        self.assertEqual(document.project_external_id, "OA-PROJ-001")
        self.assertEqual(mapping.internal_object_id, "cp_001")
        self.assertEqual(run.issue_count, 1)
        self.assertEqual(run.retry_of_run_id, "sync_000")

    def test_project_assignment_and_summary_models_keep_traceable_costing_fields(self) -> None:
        assignment = ProjectAssignmentRecord(
            id="assign_001",
            object_type="invoice",
            object_id="inv_001",
            project_id="proj_001",
            source="manual",
            assigned_by="user_finance_01",
            note="finance override",
        )
        summary = ProjectSummary(
            project_id="proj_001",
            project_code="PJT-001",
            project_name="华东改造项目",
            income_amount=Decimal("100.00"),
            expense_amount=Decimal("60.00"),
            reconciled_amount=Decimal("80.00"),
            open_ledger_amount=Decimal("20.00"),
            invoice_count=2,
            transaction_count=1,
            case_count=1,
            ledger_count=1,
        )

        self.assertEqual(assignment.source, "manual")
        self.assertEqual(assignment.project_id, "proj_001")
        self.assertEqual(summary.project_name, "华东改造项目")
        self.assertEqual(summary.open_ledger_amount, Decimal("20.00"))
        self.assertEqual(summary.invoice_count, 2)

    def test_matching_run_tracks_result_counts_by_type(self) -> None:
        run = MatchingRun(
            id="match_run_001",
            triggered_by="user_finance_01",
            invoice_count=3,
            transaction_count=2,
            results=[
                MatchingResult(
                    id="match_result_001",
                    run_id="match_run_001",
                    result_type=MatchingResultType.AUTOMATIC_MATCH,
                    confidence=MatchingConfidence.HIGH,
                    rule_code="exact_one_to_one",
                    explanation="Exact one-to-one match.",
                    invoice_ids=["inv_001"],
                    transaction_ids=["txn_001"],
                    amount=Decimal("100.00"),
                ),
                MatchingResult(
                    id="match_result_002",
                    run_id="match_run_001",
                    result_type=MatchingResultType.SUGGESTED_MATCH,
                    confidence=MatchingConfidence.MEDIUM,
                    rule_code="many_invoices_one_txn",
                    explanation="Two invoices sum to one transaction.",
                    invoice_ids=["inv_002", "inv_003"],
                    transaction_ids=["txn_002"],
                    amount=Decimal("120.00"),
                ),
            ],
        )

        self.assertEqual(run.result_count, 2)
        self.assertEqual(run.automatic_count, 1)
        self.assertEqual(run.suggested_count, 1)
        self.assertEqual(run.manual_review_count, 0)

    def test_manual_reconciliation_records_keep_exception_and_offline_traceability_fields(self) -> None:
        case = ReconciliationCase(
            id="rc_002",
            case_type=ReconciliationCaseType.DIFFERENCE,
            biz_side="payable",
            counterparty_id="cp_002",
            total_amount=Decimal("80.00"),
            status=ReconciliationCaseStatus.FOLLOW_UP_REQUIRED,
            source_result_id="match_result_001",
            difference_reason=DifferenceReason.FEE,
            difference_note="bank fee retained by payee bank",
            exception_code="PI-B",
            resolution_type="create_follow_up_ledger",
            remark="supplier invoice missing",
            related_oa_ids=["OA-202603-066"],
        )
        exception_record = ExceptionHandlingRecord(
            id="exc_001",
            reconciliation_case_id=case.id,
            biz_side="payable",
            exception_code="PI-B",
            exception_title="供应商漏开发票",
            source_invoice_ids=["inv_001"],
            source_bank_txn_ids=["txn_001"],
            resolution_action="create_follow_up_ledger",
            follow_up_ledger_type="invoice_collection",
            note="wait for supplier invoice",
            created_by="user_finance_01",
        )
        offline_record = OfflineReconciliationRecord(
            id="offline_001",
            reconciliation_case_id="rc_003",
            payment_method="cash",
            amount=Decimal("50.00"),
            occurred_on="2026-03-29",
            note="cash settlement",
            created_by="user_finance_01",
        )

        self.assertEqual(case.source_result_id, "match_result_001")
        self.assertEqual(case.exception_code, "PI-B")
        self.assertEqual(case.difference_reason, DifferenceReason.FEE)
        self.assertEqual(case.difference_note, "bank fee retained by payee bank")
        self.assertEqual(case.related_oa_ids, ["OA-202603-066"])
        self.assertEqual(exception_record.follow_up_ledger_type, "invoice_collection")
        self.assertEqual(offline_record.payment_method, "cash")

    def test_offset_note_keeps_cross_side_amounts_and_operator_traceability(self) -> None:
        offset_note = OffsetNote(
            id="offset_001",
            counterparty_id="cp_003",
            receivable_amount=Decimal("120.00"),
            payable_amount=Decimal("90.00"),
            offset_amount=Decimal("90.00"),
            reason="same_counterparty_setoff",
            note="march internal offset",
            created_by="user_finance_01",
        )

        self.assertEqual(offset_note.offset_amount, Decimal("90.00"))
        self.assertEqual(offset_note.reason, "same_counterparty_setoff")
        self.assertEqual(offset_note.created_by, "user_finance_01")

    def test_reminder_model_keeps_delivery_state_for_repeatable_scheduler_runs(self) -> None:
        reminder = Reminder(
            id="rem_001",
            ledger_id="ledger_001",
            remind_at="2026-03-30",
            channel="in_app",
            status=ReminderStatus.PENDING,
            sent_result=None,
        )

        self.assertEqual(reminder.ledger_id, "ledger_001")
        self.assertEqual(reminder.status, ReminderStatus.PENDING)


if __name__ == "__main__":
    unittest.main()

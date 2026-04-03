from __future__ import annotations

from dataclasses import asdict
from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.enums import (
    BatchStatus,
    BatchType,
    ImportDecision,
    InvoiceStatus,
    InvoiceType,
    LedgerStatus,
    LedgerType,
    ReconciliationCaseType,
    TransactionDirection,
)
from fin_ops_platform.domain.models import (
    BankTransaction,
    Counterparty,
    FollowUpLedger,
    ImportedBatch,
    ImportedBatchRowResult,
    Invoice,
    ReconciliationCase,
    ReconciliationLine,
)


def build_demo_seed() -> dict[str, Any]:
    counterparty = Counterparty(
        id="cp_demo_001",
        name="Acme Supplies",
        normalized_name="acme supplies",
        counterparty_type="customer_vendor",
        oa_external_id="OA-CP-001",
    )
    invoice = Invoice(
        id="inv_demo_001",
        invoice_type=InvoiceType.OUTPUT,
        invoice_no="OUT-202603-001",
        invoice_code="033001",
        counterparty=counterparty,
        amount=Decimal("100.00"),
        signed_amount=Decimal("100.00"),
        written_off_amount=Decimal("30.00"),
        source_unique_key="033001:OUT-202603-001",
        data_fingerprint="invoice:acme supplies:2026-03-21:100.00",
        invoice_status_from_source="valid",
        invoice_date="2026-03-21",
        project_id="proj_demo_001",
        status=InvoiceStatus.PARTIALLY_RECONCILED,
    )
    transaction = BankTransaction(
        id="txn_demo_001",
        account_no="62220001",
        txn_direction=TransactionDirection.INFLOW,
        counterparty_name_raw="Acme Supplies Ltd.",
        amount=Decimal("30.00"),
        signed_amount=Decimal("30.00"),
        bank_serial_no="SERIAL-DEMO-001",
        source_unique_key="SERIAL-DEMO-001",
        data_fingerprint="bank:62220001:acme supplies ltd.:2026-03-22:inflow:30.00",
        txn_date="2026-03-22",
        project_id="proj_demo_001",
    )
    case = ReconciliationCase(
        id="rc_demo_001",
        case_type=ReconciliationCaseType.MANUAL,
        biz_side="receivable",
        counterparty_id=counterparty.id,
        total_amount=Decimal("30.00"),
        lines=[
            ReconciliationLine(
                id="line_demo_001",
                reconciliation_case_id="rc_demo_001",
                object_type="invoice",
                object_id=invoice.id,
                applied_amount=Decimal("30.00"),
                side_role="debit",
            ),
            ReconciliationLine(
                id="line_demo_002",
                reconciliation_case_id="rc_demo_001",
                object_type="bank_txn",
                object_id=transaction.id,
                applied_amount=Decimal("30.00"),
                side_role="credit",
            ),
        ],
        project_id="proj_demo_001",
        approval_form_id="OA-FORM-001",
    )
    ledger = FollowUpLedger(
        id="ledger_demo_001",
        ledger_type=LedgerType.PAYMENT_COLLECTION,
        source_object_type="invoice",
        source_object_id=invoice.id,
        counterparty_id=counterparty.id,
        project_id="proj_demo_001",
        open_amount=Decimal("70.00"),
        expected_date="2026-03-31",
        owner_id="user_finance_01",
        status=LedgerStatus.OPEN,
    )
    batch = ImportedBatch(
        id="batch_demo_001",
        batch_type=BatchType.OUTPUT_INVOICE,
        source_name="demo-output-invoices.xlsx",
        imported_by="user_finance_01",
        row_count=1,
        success_count=1,
        error_count=0,
        duplicate_count=0,
        suspected_duplicate_count=0,
        updated_count=0,
        status=BatchStatus.COMPLETED,
    )
    batch_row = ImportedBatchRowResult(
        id="batch_row_demo_001",
        batch_id=batch.id,
        row_no=1,
        source_record_type="invoice",
        source_unique_key=invoice.source_unique_key,
        data_fingerprint=invoice.data_fingerprint,
        decision=ImportDecision.CREATED,
        decision_reason="Demo invoice imported successfully.",
        linked_object_type="invoice",
        linked_object_id=invoice.id,
        raw_payload={
            "invoice_code": invoice.invoice_code,
            "invoice_no": invoice.invoice_no,
            "counterparty_name": counterparty.name,
            "amount": "100.00",
        },
    )
    return {
        "counterparties": [asdict(counterparty)],
        "invoices": [serialize_invoice(invoice)],
        "bank_transactions": [asdict(transaction)],
        "reconciliation_cases": [serialize_case(case)],
        "follow_up_ledgers": [asdict(ledger)],
        "imported_batches": [asdict(batch)],
        "imported_batch_row_results": [asdict(batch_row)],
    }


def serialize_invoice(invoice: Invoice) -> dict[str, Any]:
    payload = asdict(invoice)
    payload["counterparty"] = asdict(invoice.counterparty)
    return payload


def serialize_case(case: ReconciliationCase) -> dict[str, Any]:
    payload = asdict(case)
    payload["created_at"] = case.created_at.isoformat()
    return payload

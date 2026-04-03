from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from .enums import (
    BatchStatus,
    BatchType,
    DifferenceReason,
    IntegrationObjectType,
    IntegrationSource,
    IntegrationSyncStatus,
    ImportDecision,
    InvoiceStatus,
    InvoiceType,
    LedgerStatus,
    LedgerType,
    MatchingConfidence,
    MatchingResultType,
    ReconciliationCaseStatus,
    ReconciliationCaseType,
    ReminderStatus,
    TransactionDirection,
    TransactionStatus,
)


ZERO = Decimal("0.00")


@dataclass(slots=True)
class Counterparty:
    id: str
    name: str
    normalized_name: str
    counterparty_type: str
    tax_no: str | None = None
    oa_external_id: str | None = None


@dataclass(slots=True)
class Invoice:
    id: str
    invoice_type: InvoiceType
    invoice_no: str
    counterparty: Counterparty
    amount: Decimal
    signed_amount: Decimal
    invoice_code: str | None = None
    digital_invoice_no: str | None = None
    source_unique_key: str | None = None
    data_fingerprint: str | None = None
    written_off_amount: Decimal = ZERO
    currency: str = "CNY"
    invoice_date: str | None = None
    invoice_status_from_source: str | None = None
    seller_tax_no: str | None = None
    seller_name: str | None = None
    buyer_tax_no: str | None = None
    buyer_name: str | None = None
    tax_rate: str | None = None
    tax_amount: Decimal | None = None
    total_with_tax: Decimal | None = None
    tax_classification_code: str | None = None
    specific_business_type: str | None = None
    taxable_item_name: str | None = None
    specification_model: str | None = None
    unit: str | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    invoice_source: str | None = None
    invoice_kind: str | None = None
    is_positive_invoice: str | None = None
    risk_level: str | None = None
    issuer: str | None = None
    remark: str | None = None
    project_id: str | None = None
    department_id: str | None = None
    source_batch_id: str | None = None
    oa_form_id: str | None = None
    status: InvoiceStatus = InvoiceStatus.PENDING

    @property
    def outstanding_amount(self) -> Decimal:
        return self.amount - self.written_off_amount


@dataclass(slots=True)
class BankTransaction:
    id: str
    account_no: str
    txn_direction: TransactionDirection
    counterparty_name_raw: str
    amount: Decimal
    signed_amount: Decimal
    bank_serial_no: str | None = None
    source_unique_key: str | None = None
    data_fingerprint: str | None = None
    written_off_amount: Decimal = ZERO
    txn_date: str | None = None
    trade_time: str | None = None
    pay_receive_time: str | None = None
    counterparty_id: str | None = None
    project_id: str | None = None
    source_batch_id: str | None = None
    account_name: str | None = None
    balance: Decimal | None = None
    currency: str | None = None
    counterparty_account_no: str | None = None
    counterparty_bank_name: str | None = None
    booked_date: str | None = None
    summary: str | None = None
    remark: str | None = None
    account_detail_no: str | None = None
    enterprise_serial_no: str | None = None
    voucher_kind: str | None = None
    voucher_no: str | None = None
    status: TransactionStatus = TransactionStatus.PENDING

    @property
    def outstanding_amount(self) -> Decimal:
        return self.amount - self.written_off_amount


@dataclass(slots=True)
class ReconciliationLine:
    id: str
    reconciliation_case_id: str
    object_type: str
    object_id: str
    applied_amount: Decimal
    side_role: str = "note"


@dataclass(slots=True)
class ReconciliationCase:
    id: str
    case_type: ReconciliationCaseType
    biz_side: str
    counterparty_id: str
    total_amount: Decimal
    difference_amount: Decimal = ZERO
    difference_reason: DifferenceReason | str | None = None
    difference_note: str | None = None
    created_by: str | None = None
    approved_by: str | None = None
    approval_form_id: str | None = None
    source_result_id: str | None = None
    exception_code: str | None = None
    resolution_type: str | None = None
    remark: str | None = None
    related_oa_ids: list[str] = field(default_factory=list)
    project_id: str | None = None
    status: ReconciliationCaseStatus = ReconciliationCaseStatus.CONFIRMED
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    lines: list[ReconciliationLine] = field(default_factory=list)

    @property
    def applied_amount_total(self) -> Decimal:
        return sum((line.applied_amount for line in self.lines), start=ZERO)

    @property
    def requires_follow_up(self) -> bool:
        return self.difference_amount != ZERO or self.applied_amount_total != self.total_amount


@dataclass(slots=True)
class FollowUpLedger:
    id: str
    ledger_type: LedgerType
    source_object_type: str
    source_object_id: str
    counterparty_id: str
    open_amount: Decimal
    expected_date: str
    owner_id: str
    status: LedgerStatus = LedgerStatus.OPEN
    source_case_id: str | None = None
    project_id: str | None = None
    latest_note: str | None = None
    last_reminded_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ImportedBatch:
    id: str
    batch_type: BatchType
    source_name: str
    imported_by: str
    row_count: int
    success_count: int
    error_count: int
    status: BatchStatus
    duplicate_count: int = 0
    suspected_duplicate_count: int = 0
    updated_count: int = 0
    imported_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ImportedBatchRowResult:
    id: str
    batch_id: str
    row_no: int
    source_record_type: str
    source_unique_key: str | None
    data_fingerprint: str | None
    decision: ImportDecision
    decision_reason: str
    linked_object_type: str | None = None
    linked_object_id: str | None = None
    raw_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class MatchingResult:
    id: str
    run_id: str
    result_type: MatchingResultType
    confidence: MatchingConfidence
    rule_code: str
    explanation: str
    invoice_ids: list[str] = field(default_factory=list)
    transaction_ids: list[str] = field(default_factory=list)
    amount: Decimal = ZERO
    difference_amount: Decimal = ZERO
    counterparty_name: str | None = None


@dataclass(slots=True)
class MatchingRun:
    id: str
    triggered_by: str
    invoice_count: int
    transaction_count: int
    executed_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    results: list[MatchingResult] = field(default_factory=list)

    @property
    def result_count(self) -> int:
        return len(self.results)

    @property
    def automatic_count(self) -> int:
        return sum(1 for result in self.results if result.result_type == MatchingResultType.AUTOMATIC_MATCH)

    @property
    def suggested_count(self) -> int:
        return sum(1 for result in self.results if result.result_type == MatchingResultType.SUGGESTED_MATCH)

    @property
    def manual_review_count(self) -> int:
        return sum(1 for result in self.results if result.result_type == MatchingResultType.MANUAL_REVIEW)


@dataclass(slots=True)
class ExceptionHandlingRecord:
    id: str
    reconciliation_case_id: str
    biz_side: str
    exception_code: str
    exception_title: str
    source_invoice_ids: list[str] = field(default_factory=list)
    source_bank_txn_ids: list[str] = field(default_factory=list)
    resolution_action: str | None = None
    follow_up_ledger_type: str | None = None
    note: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class OfflineReconciliationRecord:
    id: str
    reconciliation_case_id: str
    payment_method: str
    amount: Decimal
    occurred_on: str
    note: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class OffsetNote:
    id: str
    counterparty_id: str
    receivable_amount: Decimal
    payable_amount: Decimal
    offset_amount: Decimal
    reason: str
    note: str | None = None
    created_by: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class Reminder:
    id: str
    ledger_id: str
    remind_at: str
    channel: str
    status: ReminderStatus
    sent_result: str | None = None
    sent_at: datetime | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ProjectMaster:
    id: str
    project_code: str
    project_name: str
    project_status: str
    oa_external_id: str | None = None
    department_name: str | None = None
    owner_name: str | None = None


@dataclass(slots=True)
class OADocument:
    id: str
    document_type: str
    oa_external_id: str
    form_no: str
    title: str
    applicant_name: str
    amount: Decimal | None = None
    currency: str = "CNY"
    counterparty_name: str | None = None
    project_external_id: str | None = None
    project_name: str | None = None
    form_status: str = "approved"
    submitted_at: str | None = None
    completed_at: str | None = None
    source_payload: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class IntegrationMapping:
    id: str
    source_system: IntegrationSource
    object_type: IntegrationObjectType
    external_id: str
    internal_object_type: str | None = None
    internal_object_id: str | None = None
    display_name: str | None = None
    sync_status: IntegrationSyncStatus = IntegrationSyncStatus.SUCCEEDED
    last_synced_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class IntegrationSyncIssue:
    id: str
    run_id: str
    object_type: IntegrationObjectType
    external_id: str
    title: str
    reason: str
    retryable: bool = True


@dataclass(slots=True)
class IntegrationSyncRun:
    id: str
    source_system: IntegrationSource
    scope: str
    triggered_by: str
    status: IntegrationSyncStatus
    pulled_count: int
    success_count: int
    failed_count: int
    retry_of_run_id: str | None = None
    started_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    finished_at: datetime | None = None
    issues: list[IntegrationSyncIssue] = field(default_factory=list)

    @property
    def issue_count(self) -> int:
        return len(self.issues)


@dataclass(slots=True)
class ProjectAssignmentRecord:
    id: str
    object_type: str
    object_id: str
    project_id: str
    source: str
    assigned_by: str | None = None
    note: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ProjectSummary:
    project_id: str
    project_code: str
    project_name: str
    income_amount: Decimal = ZERO
    expense_amount: Decimal = ZERO
    reconciled_amount: Decimal = ZERO
    open_ledger_amount: Decimal = ZERO
    invoice_count: int = 0
    transaction_count: int = 0
    case_count: int = 0
    ledger_count: int = 0


@dataclass(slots=True)
class AuditLog:
    id: str
    actor_id: str
    action: str
    entity_type: str
    entity_id: str
    before_amount: Decimal | None = None
    after_amount: Decimal | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))

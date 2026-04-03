from enum import StrEnum


class InvoiceType(StrEnum):
    OUTPUT = "output"
    INPUT = "input"


class InvoiceStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_RECONCILED = "partially_reconciled"
    RECONCILED = "reconciled"
    PENDING_OFFLINE_CONFIRMATION = "pending_offline_confirmation"
    PENDING_OFFSET = "pending_offset"
    PENDING_INVOICE_ISSUE = "pending_invoice_issue"
    PENDING_INVOICE_RECEIVE = "pending_invoice_receive"


class TransactionDirection(StrEnum):
    INFLOW = "inflow"
    OUTFLOW = "outflow"


class TransactionStatus(StrEnum):
    PENDING = "pending"
    PARTIALLY_RECONCILED = "partially_reconciled"
    RECONCILED = "reconciled"
    CLASSIFIED_AS_PREPAYMENT = "classified_as_prepayment"
    CLASSIFIED_AS_ADVANCE_RECEIPT = "classified_as_advance_receipt"
    PENDING_REFUND = "pending_refund"
    PENDING_COUNTERPARTY_CONFIRMATION = "pending_counterparty_confirmation"


class ReconciliationCaseType(StrEnum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    DIFFERENCE = "difference"
    OFFSET = "offset"
    OFFLINE = "offline"


class ReconciliationCaseStatus(StrEnum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    FOLLOW_UP_REQUIRED = "follow_up_required"
    CANCELLED = "cancelled"


class DifferenceReason(StrEnum):
    FEE = "fee"
    ROUNDING = "rounding"
    FX = "fx"
    TAX = "tax"
    OTHER = "other"


class LedgerType(StrEnum):
    PAYMENT_COLLECTION = "payment_collection"
    INVOICE_COLLECTION = "invoice_collection"
    REFUND = "refund"
    ADVANCE_RECEIPT = "advance_receipt"
    PREPAYMENT = "prepayment"
    OUTPUT_INVOICE_ISSUE = "output_invoice_issue"
    PAYMENT_REMINDER = "payment_reminder"
    EXTERNAL_RECEIVABLE_PAYABLE = "external_receivable_payable"
    NON_TAX_INCOME = "non_tax_income"


class LedgerStatus(StrEnum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_EXTERNAL_FEEDBACK = "waiting_external_feedback"
    RESOLVED = "resolved"
    CANCELLED = "cancelled"


class ReminderStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class IntegrationSource(StrEnum):
    OA = "oa"


class IntegrationObjectType(StrEnum):
    COUNTERPARTY = "counterparty"
    PROJECT = "project"
    APPROVAL_FORM = "approval_form"
    PAYMENT_REQUEST = "payment_request"
    EXPENSE_CLAIM = "expense_claim"


class IntegrationSyncStatus(StrEnum):
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"


class BatchType(StrEnum):
    OUTPUT_INVOICE = "output_invoice"
    INPUT_INVOICE = "input_invoice"
    BANK_TRANSACTION = "bank_transaction"


class BatchStatus(StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    COMPLETED_WITH_ERRORS = "completed_with_errors"
    REVERTED = "reverted"
    FAILED = "failed"


class ImportDecision(StrEnum):
    CREATED = "created"
    STATUS_UPDATED = "status_updated"
    DUPLICATE_SKIPPED = "duplicate_skipped"
    SUSPECTED_DUPLICATE = "suspected_duplicate"
    ERROR = "error"


class MatchingResultType(StrEnum):
    AUTOMATIC_MATCH = "automatic_match"
    SUGGESTED_MATCH = "suggested_match"
    MANUAL_REVIEW = "manual_review"


class MatchingConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

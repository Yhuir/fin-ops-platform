from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Any


class SourceFileKind(str, Enum):
    CREDIT_CARD_STATEMENT = "credit_card_statement"
    TICKET_ROOT = "ticket_root"
    SUPPLEMENT_EVIDENCE = "supplement_evidence"
    ETC_ZIP = "etc_zip"


class EtcReconciliationTaskStatus(str, Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    READY_FOR_IMPORT = "ready_for_import"
    IMPORTING = "importing"
    IMPORTED = "imported"
    CLOSED = "closed"
    DELETED = "deleted"


class ParseIssueSeverity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


def utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(slots=True)
class UploadedSourceFileMetadata:
    file_id: str
    task_id: str
    source_kind: SourceFileKind
    original_name: str
    content_type: str
    size_bytes: int
    sha256: str
    stored_path: str
    created_by: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass(slots=True)
class CreditCardItem:
    item_id: str
    task_id: str
    statement_file_id: str
    transaction_date: str
    posting_date: str
    card_last4: str
    description: str
    currency: str
    amount: Decimal
    settlement_amount: Decimal
    is_etc_candidate: bool
    candidate_reason: str | None = None
    source_page: int | None = None
    source_line: int | None = None
    parse_confidence: float = 1.0
    recommendation_status: str = "not_candidate"
    manual_resolution: str = "unresolved"
    manual_resolution_reason: str | None = None
    review_note: str | None = None


@dataclass(slots=True)
class TicketRootItem:
    item_id: str
    task_id: str
    ticket_file_id: str
    vehicle_plate: str
    transaction_at: str
    amount: Decimal
    entry_station: str
    exit_station: str
    invoice_count: int
    source_page: int
    extraction_method: str
    parse_confidence: float = 1.0
    recommendation_status: str = "unmatched"
    linked_credit_card_item_ids: list[str] = field(default_factory=list)
    removed: bool = False
    removed_reason: str | None = None


@dataclass(slots=True)
class SupplementEvidence:
    evidence_id: str
    task_id: str
    source_file_id: str
    source_name: str
    evidence_kind: str
    amount: Decimal | None = None
    paid_at: str | None = None
    merchant_name: str | None = None
    tags: list[str] = field(default_factory=lambda: ["ETC补充凭证"])
    include_in_etc_zip_check: bool = False
    include_in_oa_submission: bool = True
    include_in_workbench: bool = True
    parse_confidence: float = 0.8


@dataclass(slots=True)
class ReconciledItem:
    item_id: str
    task_id: str
    credit_card_item_id: str
    ticket_root_item_ids: list[str] = field(default_factory=list)
    supplement_evidence_ids: list[str] = field(default_factory=list)
    resolution: str = "unresolved"
    note: str | None = None
    claim_amount: Decimal | None = None
    evidence_amount: Decimal | None = None
    amount_delta: Decimal | None = None
    amount_delta_note: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None


@dataclass(slots=True)
class ExpectedEtcInvoiceRequirement:
    requirement_id: str
    task_id: str
    credit_card_item_id: str
    ticket_root_item_id: str | None
    vehicle_plate: str
    transaction_at: str
    date_window_start: str
    date_window_end: str
    amount: Decimal
    invoice_count: int
    required_for_zip: bool = True
    match_status: str = "pending"
    matched_invoice_numbers: list[str] = field(default_factory=list)
    manual_override_note: str | None = None


@dataclass(slots=True)
class SubmissionSupplementAttachment:
    attachment_id: str
    task_id: str
    source_file_id: str
    evidence_id: str
    original_name: str
    stored_path: str
    sha256: str
    amount: Decimal | None = None
    tags: list[str] = field(default_factory=lambda: ["ETC补充凭证"])


@dataclass(slots=True)
class ParseIssue:
    issue_id: str
    file_id: str
    severity: ParseIssueSeverity
    message: str
    source_page: int | None = None
    source_line: int | None = None
    extraction_method: str | None = None
    field_name: str | None = None


@dataclass(slots=True)
class FileParseResult:
    file_id: str
    parser_code: str
    credit_card_items: list[CreditCardItem] = field(default_factory=list)
    ticket_root_items: list[TicketRootItem] = field(default_factory=list)
    supplement_evidences: list[SupplementEvidence] = field(default_factory=list)
    issues: list[ParseIssue] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(issue.severity == ParseIssueSeverity.BLOCKING for issue in self.issues)


@dataclass(slots=True)
class AuditEvent:
    event_id: str
    task_id: str
    event_type: str
    actor: str
    created_at: datetime = field(default_factory=utc_now)
    note: str | None = None
    file_id: str | None = None
    file_name: str | None = None
    file_sha256: str | None = None
    before_status: str | None = None
    after_status: str | None = None
    affected_item_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class EtcReconciliationTask:
    task_id: str
    status: EtcReconciliationTaskStatus
    version: int
    title: str
    period_start: str | None = None
    period_end: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    approved_delta: Decimal | None = None
    approved_delta_note: str | None = None
    card_last4: str | None = None
    oa_total_amount: Decimal | None = None
    etc_invoice_amount: Decimal | None = None
    supplement_amount: Decimal | None = None
    etc_invoice_count: int = 0
    supplement_count: int = 0
    vehicle_plates: list[str] = field(default_factory=list)
    created_by: str = ""
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    confirmed_by: str | None = None
    confirmed_at: datetime | None = None
    import_batch_id: str | None = None
    etc_batch_id: str | None = None
    oa_draft_batch_id: str | None = None
    oa_draft_status: str | None = None
    submitted_confirmed_at: datetime | None = None
    confirmed_item_set_hash: str | None = None
    zip_preview_generation: int = 0
    source_files: list[UploadedSourceFileMetadata] = field(default_factory=list)
    credit_card_items: list[CreditCardItem] = field(default_factory=list)
    ticket_root_items: list[TicketRootItem] = field(default_factory=list)
    supplement_evidences: list[SupplementEvidence] = field(default_factory=list)
    reconciled_items: list[ReconciledItem] = field(default_factory=list)
    expected_etc_invoice_requirements: list[ExpectedEtcInvoiceRequirement] = field(default_factory=list)
    submission_supplement_attachments: list[SubmissionSupplementAttachment] = field(default_factory=list)
    parse_results: list[FileParseResult] = field(default_factory=list)
    audit_events: list[AuditEvent] = field(default_factory=list)


def coerce_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def coerce_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))

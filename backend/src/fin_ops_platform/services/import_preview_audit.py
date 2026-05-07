from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Protocol

from fin_ops_platform.domain.enums import ImportDecision
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService


PLACEHOLDER_EMPTY_VALUES = {"", "--", "—", "-", "——", "nan", "NaN", "None"}
WHITESPACE_RE = re.compile(r"\s+")
AUDIT_STALE_FIELDS = (
    "importable_count",
    "update_count",
    "merge_count",
    "existing_duplicate_count",
    "duplicate_count",
    "suspected_duplicate_count",
    "error_count",
)


@dataclass(frozen=True, slots=True)
class ImportRecordIdentity:
    record_type: str
    identity_key: str | None
    identity_kind: str | None


@dataclass(slots=True)
class ImportPreviewAuditCounts:
    original_count: int = 0
    unique_count: int = 0
    duplicate_count: int = 0
    duplicate_in_file_count: int = 0
    duplicate_across_files_count: int = 0
    existing_duplicate_count: int = 0
    importable_count: int = 0
    update_count: int = 0
    merge_count: int = 0
    suspected_duplicate_count: int = 0
    error_count: int = 0
    confirmable_count: int = 0
    skipped_count: int = 0

    def add(self, other: ImportPreviewAuditCounts) -> None:
        for field_name in self.__dataclass_fields__:
            setattr(self, field_name, getattr(self, field_name) + getattr(other, field_name))

    def stale_projection(self) -> dict[str, int]:
        return {field_name: getattr(self, field_name) for field_name in AUDIT_STALE_FIELDS}


@dataclass(frozen=True, slots=True)
class ImportPreviewAuditRow:
    file_id: str
    file_name: str
    row_no: int
    record_type: str
    identity_key: str | None
    identity_kind: str | None
    decision: ImportDecision | str | None = None
    linked_object_type: str | None = None
    linked_object_id: str | None = None


@dataclass(slots=True)
class ImportPreviewDuplicateGroup:
    identity_key: str
    record_type: str
    duplicate_type: str
    rows: list[dict[str, Any]]


@dataclass(slots=True)
class ImportPreviewFileAudit:
    file_id: str
    file_name: str
    audit: ImportPreviewAuditCounts = field(default_factory=ImportPreviewAuditCounts)


@dataclass(slots=True)
class ImportPreviewSessionAudit:
    audit: ImportPreviewAuditCounts = field(default_factory=ImportPreviewAuditCounts)
    files: list[ImportPreviewFileAudit] = field(default_factory=list)
    duplicate_groups: list[ImportPreviewDuplicateGroup] = field(default_factory=list)


class ImportPreviewStaleError(ValueError):
    def __init__(self, *, preview: ImportPreviewAuditCounts, current: ImportPreviewAuditCounts) -> None:
        super().__init__("preview_stale")
        self.preview = preview
        self.current = current


class RecordIdentityStrategy(Protocol):
    record_type: str

    def identify(self, values: dict[str, Any]) -> ImportRecordIdentity:
        ...


class InvoiceIdentityStrategy:
    record_type = "invoice"

    def __init__(self, identity_service: InvoiceIdentityService | None = None) -> None:
        self._identity_service = identity_service or InvoiceIdentityService()

    def identify(self, values: dict[str, Any]) -> ImportRecordIdentity:
        normalized = {key: clean_placeholder(value) for key, value in values.items()}
        canonical_key = self._identity_service.canonical_key_for_mapping(normalized)
        if canonical_key:
            return ImportRecordIdentity(record_type=self.record_type, identity_key=canonical_key, identity_kind="stable")
        suspected_key = self._identity_service.suspected_key_for_mapping(normalized)
        if suspected_key:
            return ImportRecordIdentity(record_type=self.record_type, identity_key=suspected_key, identity_kind="suspected")
        return ImportRecordIdentity(record_type=self.record_type, identity_key=None, identity_kind=None)


class BankTransactionIdentityStrategy:
    record_type = "bank_transaction"

    def identify(self, values: dict[str, Any]) -> ImportRecordIdentity:
        account_no = clean_placeholder(values.get("account_no"))
        if account_no:
            for field_name in ("bank_serial_no", "enterprise_serial_no", "voucher_no"):
                serial_value = clean_placeholder(values.get(field_name))
                if serial_value:
                    return ImportRecordIdentity(
                        record_type=self.record_type,
                        identity_key=f"bank:{account_no}:{field_name}:{serial_value}",
                        identity_kind="stable",
                    )
        txn_date = clean_placeholder(values.get("txn_date"))
        direction = clean_placeholder(values.get("txn_direction") or values.get("direction"))
        amount = _format_amount(values.get("amount"))
        counterparty_name = clean_placeholder(values.get("normalized_counterparty_name")) or normalize_name(
            str(values.get("counterparty_name") or values.get("counterparty_name_raw") or "")
        )
        if account_no and txn_date and direction and amount and counterparty_name:
            return ImportRecordIdentity(
                record_type=self.record_type,
                identity_key=f"bank:{account_no}:{txn_date}:{direction}:{amount}:{counterparty_name}",
                identity_kind="suspected",
            )
        return ImportRecordIdentity(record_type=self.record_type, identity_key=None, identity_kind=None)


class EtcInvoiceIdentityStrategy(InvoiceIdentityStrategy):
    record_type = "invoice"


def clean_placeholder(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if text in PLACEHOLDER_EMPTY_VALUES:
        return None
    return text or None


def build_import_preview_session_audit(rows: list[ImportPreviewAuditRow]) -> ImportPreviewSessionAudit:
    file_order: dict[str, int] = {}
    file_names: dict[str, str] = {}
    for row in rows:
        file_order.setdefault(row.file_id, len(file_order))
        file_names[row.file_id] = row.file_name

    file_audits = {
        file_id: ImportPreviewFileAudit(file_id=file_id, file_name=file_names[file_id])
        for file_id in file_order
    }
    session_counts = ImportPreviewAuditCounts(original_count=len(rows))
    for row in rows:
        file_audits[row.file_id].audit.original_count += 1
        if _decision_value(row.decision) == ImportDecision.ERROR.value:
            file_audits[row.file_id].audit.error_count += 1
            session_counts.error_count += 1

    grouped: dict[tuple[str, str], list[ImportPreviewAuditRow]] = defaultdict(list)
    for row in rows:
        if _decision_value(row.decision) == ImportDecision.ERROR.value or not row.identity_key:
            continue
        grouped[(row.record_type, row.identity_key)].append(row)

    duplicate_groups: list[ImportPreviewDuplicateGroup] = []
    for (record_type, identity_key), group_rows in grouped.items():
        sorted_rows = sorted(group_rows, key=lambda row: (file_order[row.file_id], row.row_no))
        rows_by_file: dict[str, list[ImportPreviewAuditRow]] = defaultdict(list)
        for row in sorted_rows:
            rows_by_file[row.file_id].append(row)

        first_file_id = sorted_rows[0].file_id
        representative = sorted_rows[0]
        suspected_issue = representative.identity_kind == "suspected" and (
            len(sorted_rows) > 1 or _is_suspected_decision(representative.decision)
        )
        file_audits[first_file_id].audit.unique_count += 1
        session_counts.unique_count += 1
        if not suspected_issue:
            _apply_representative_decision(file_audits[first_file_id].audit, representative)
            _apply_representative_decision(session_counts, representative)

        duplicate_rows_for_group: list[ImportPreviewAuditRow] = []
        group_has_across_file_duplicate = len(rows_by_file) > 1
        for file_id, file_rows in rows_by_file.items():
            sorted_file_rows = sorted(file_rows, key=lambda row: row.row_no)
            if file_id != first_file_id:
                file_audits[file_id].audit.duplicate_across_files_count += 1
                session_counts.duplicate_across_files_count += 1
                duplicate_rows_for_group.append(sorted_file_rows[0])
            if len(sorted_file_rows) > 1:
                duplicate_in_file_count = len(sorted_file_rows) - 1
                file_audits[file_id].audit.duplicate_in_file_count += duplicate_in_file_count
                session_counts.duplicate_in_file_count += duplicate_in_file_count
                duplicate_rows_for_group.extend(sorted_file_rows[1:])

        if suspected_issue:
            suspected_count = len(sorted_rows)
            session_counts.suspected_duplicate_count += suspected_count
            for row in sorted_rows:
                file_audits[row.file_id].audit.suspected_duplicate_count += 1

        duplicate_type = "duplicate_across_files" if group_has_across_file_duplicate else "duplicate_in_file"
        if duplicate_rows_for_group:
            duplicate_groups.append(
                ImportPreviewDuplicateGroup(
                    identity_key=identity_key,
                    record_type=record_type,
                    duplicate_type=duplicate_type,
                    rows=[
                        {"file_id": row.file_id, "file_name": row.file_name, "row_no": row.row_no}
                        for row in sorted_rows
                    ],
                )
            )

    for counts in [session_counts, *(file.audit for file in file_audits.values())]:
        counts.duplicate_count = counts.duplicate_in_file_count + counts.duplicate_across_files_count
        counts.confirmable_count = counts.importable_count + counts.update_count + counts.merge_count
        counts.skipped_count = max(0, counts.original_count - counts.confirmable_count)

    return ImportPreviewSessionAudit(
        audit=session_counts,
        files=[file_audits[file_id] for file_id in file_order],
        duplicate_groups=duplicate_groups,
    )


def _apply_representative_decision(counts: ImportPreviewAuditCounts, row: ImportPreviewAuditRow) -> None:
    decision = _decision_value(row.decision)
    if decision == ImportDecision.STATUS_UPDATED.value:
        counts.update_count += 1
    elif decision == ImportDecision.DUPLICATE_SKIPPED.value:
        counts.existing_duplicate_count += 1
        if row.record_type == "invoice":
            counts.merge_count += 1
    elif decision == ImportDecision.SUSPECTED_DUPLICATE.value:
        counts.suspected_duplicate_count += 1
    elif decision != ImportDecision.ERROR.value:
        counts.importable_count += 1


def _is_suspected_decision(decision: ImportDecision | str | None) -> bool:
    return _decision_value(decision) == ImportDecision.SUSPECTED_DUPLICATE.value


def _decision_value(decision: ImportDecision | str | None) -> str | None:
    return decision.value if isinstance(decision, ImportDecision) else decision


def _format_amount(value: Any) -> str | None:
    cleaned = clean_placeholder(value)
    if cleaned is None:
        return None
    try:
        return f"{Decimal(str(cleaned).replace(',', '')).quantize(Decimal('0.01'))}"
    except (InvalidOperation, ValueError):
        return None


def normalize_name(value: str) -> str:
    return WHITESPACE_RE.sub(" ", str(value).strip()).lower()

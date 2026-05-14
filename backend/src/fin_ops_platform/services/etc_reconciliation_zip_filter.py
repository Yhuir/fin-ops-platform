from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from zipfile import BadZipFile, ZipFile

from fin_ops_platform.services.etc_reconciliation_models import (
    EtcReconciliationTask,
    EtcReconciliationTaskStatus,
    ExpectedEtcInvoiceRequirement,
)
from fin_ops_platform.services.etc_service import ParsedEtcXml, UploadedEtcZipFile, parse_etc_xml


class StaleReconciliationPreviewError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EtcZipFilterItem:
    file_name: str
    invoice_number: str | None
    filter_status: str
    requirement_id: str | None = None
    message: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "fileName": self.file_name,
            "invoiceNumber": self.invoice_number,
            "filterStatus": self.filter_status,
            "requirementId": self.requirement_id,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class EtcZipFilterPreview:
    task_id: str
    task_version: int
    confirmed_item_set_hash: str
    allowed_invoice_numbers: list[str]
    items: list[EtcZipFilterItem]
    blocking_issues: list[dict[str, object]] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "taskId": self.task_id,
            "taskVersion": self.task_version,
            "confirmedItemSetHash": self.confirmed_item_set_hash,
            "allowedInvoiceNumbers": self.allowed_invoice_numbers,
            "items": [item.to_payload() for item in self.items],
            "blockingIssues": list(self.blocking_issues),
        }


def preview_etc_zip_for_task(*, task: EtcReconciliationTask, uploads: list[UploadedEtcZipFile]) -> EtcZipFilterPreview:
    _assert_ready_task(task)
    parsed_items = _parse_uploads(uploads)
    matched_invoice_numbers: set[str] = set()
    items_by_invoice: dict[str, EtcZipFilterItem] = {}
    requirement_ids_by_invoice: dict[str, list[str]] = {}
    blocking_issues: list[dict[str, object]] = []

    for requirement in task.expected_etc_invoice_requirements:
        candidates = [
            (file_name, invoice)
            for file_name, invoice in parsed_items
            if _invoice_matches_requirement(invoice, requirement)
        ]
        if len(candidates) == 1:
            file_name, invoice = candidates[0]
            matched_invoice_numbers.add(invoice.invoice_number)
            requirement_ids_by_invoice.setdefault(invoice.invoice_number, []).append(requirement.requirement_id)
            items_by_invoice[invoice.invoice_number] = EtcZipFilterItem(
                file_name=file_name,
                invoice_number=invoice.invoice_number,
                filter_status="included",
                requirement_id=requirement.requirement_id,
            )
        elif len(candidates) > 1:
            numbers = [invoice.invoice_number for _file_name, invoice in candidates]
            blocking_issues.append(
                {
                    "error": "ambiguous_etc_invoice_match",
                    "requirementId": requirement.requirement_id,
                    "invoiceNumbers": numbers,
                }
            )
            for file_name, invoice in candidates:
                items_by_invoice[invoice.invoice_number] = EtcZipFilterItem(
                    file_name=file_name,
                    invoice_number=invoice.invoice_number,
                    filter_status="ambiguous_zip_match",
                    requirement_id=requirement.requirement_id,
                )
        else:
            blocking_issues.append(
                {
                    "error": "missing_required_etc_invoice",
                    "requirementId": requirement.requirement_id,
                }
            )

    for invoice_number, requirement_ids in requirement_ids_by_invoice.items():
        unique_requirement_ids = list(dict.fromkeys(requirement_ids))
        if len(unique_requirement_ids) <= 1:
            continue
        matched_invoice_numbers.discard(invoice_number)
        blocking_issues.append(
            {
                "error": "duplicate_requirement_invoice_match",
                "invoiceNumber": invoice_number,
                "requirementIds": unique_requirement_ids,
            }
        )
        items_by_invoice[invoice_number] = EtcZipFilterItem(
            file_name=items_by_invoice[invoice_number].file_name,
            invoice_number=invoice_number,
            filter_status="duplicate_requirement_invoice_match",
            requirement_id=None,
        )

    all_items: list[EtcZipFilterItem] = []
    for file_name, invoice in parsed_items:
        existing = items_by_invoice.get(invoice.invoice_number)
        if existing is not None:
            all_items.append(existing)
            continue
        all_items.append(
            EtcZipFilterItem(
                file_name=file_name,
                invoice_number=invoice.invoice_number,
                filter_status="excluded_extra_zip_invoice",
            )
        )

    return EtcZipFilterPreview(
        task_id=task.task_id,
        task_version=task.version,
        confirmed_item_set_hash=task.confirmed_item_set_hash or "",
        allowed_invoice_numbers=sorted(matched_invoice_numbers),
        items=all_items,
        blocking_issues=blocking_issues,
    )


def validate_etc_zip_confirm_for_task(*, task: EtcReconciliationTask, preview: EtcZipFilterPreview) -> None:
    if (
        task.task_id != preview.task_id
        or task.version != preview.task_version
        or task.confirmed_item_set_hash != preview.confirmed_item_set_hash
    ):
        raise StaleReconciliationPreviewError("stale_reconciliation_task_preview")
    _assert_ready_task(task)
    for issue in preview.blocking_issues:
        error = str(issue.get("error") or "")
        if error in {"missing_required_etc_invoice", "ambiguous_etc_invoice_match", "duplicate_requirement_invoice_match"}:
            raise ValueError(error)


def filter_uploads_by_allowlist(
    *,
    uploads: list[UploadedEtcZipFile],
    allowed_invoice_numbers: list[str],
) -> list[UploadedEtcZipFile]:
    allowed = set(allowed_invoice_numbers)
    if not allowed:
        return []
    filtered: list[UploadedEtcZipFile] = []
    for upload in uploads:
        try:
            entries = _extract_entries(upload.file_name, upload.content)
        except BadZipFile:
            continue
        kept: dict[str, bytes] = {}
        xml_paths_by_invoice: dict[str, str] = {}
        for path, content in entries:
            if _is_xml_entry(path):
                try:
                    invoice = parse_etc_xml(content)
                except Exception:
                    continue
                if invoice.invoice_number in allowed:
                    kept[path] = content
                    xml_paths_by_invoice[invoice.invoice_number] = path
        for path, content in entries:
            if not _is_pdf_entry(path):
                continue
            stem = Path(path).stem.lower()
            for invoice_number, xml_path in xml_paths_by_invoice.items():
                invoice_key = invoice_number.lower()
                if invoice_key in stem or stem in invoice_key or stem == Path(xml_path).stem.lower():
                    kept[path] = content
                    break
        if kept:
            filtered.append(UploadedEtcZipFile(upload.file_name, _zip_entries(kept)))
    return filtered


def _assert_ready_task(task: EtcReconciliationTask) -> None:
    if task.status != EtcReconciliationTaskStatus.READY_FOR_IMPORT:
        raise ValueError("invalid_reconciliation_task_status")
    if not task.confirmed_item_set_hash:
        raise ValueError("stale_reconciliation_task_preview")


def _parse_uploads(uploads: list[UploadedEtcZipFile]) -> list[tuple[str, ParsedEtcXml]]:
    parsed: list[tuple[str, ParsedEtcXml]] = []
    for upload in uploads:
        try:
            entries = _extract_entries(upload.file_name, upload.content)
        except BadZipFile:
            continue
        for path, content in entries:
            if not _is_xml_entry(path):
                continue
            try:
                parsed.append((path, parse_etc_xml(content)))
            except Exception:
                continue
    return parsed


def _extract_entries(source_name: str, content: bytes, *, depth: int = 0) -> list[tuple[str, bytes]]:
    if depth > 8:
        raise BadZipFile("nested zip depth exceeds limit")
    entries: list[tuple[str, bytes]] = []
    with ZipFile(BytesIO(content)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            file_content = archive.read(info)
            path = info.filename
            if path.lower().endswith(".zip"):
                entries.extend(_extract_entries(f"{source_name}/{path}", file_content, depth=depth + 1))
            else:
                entries.append((path, file_content))
    return entries


def _is_xml_entry(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    return path.lower().endswith(".xml") and "xml" in parts


def _is_pdf_entry(path: str) -> bool:
    parts = [part.lower() for part in Path(path).parts]
    return path.lower().endswith(".pdf") and "pdf" in parts


def _invoice_matches_requirement(invoice: ParsedEtcXml, requirement: ExpectedEtcInvoiceRequirement) -> bool:
    if Decimal(invoice.total_amount).quantize(Decimal("0.01")) != Decimal(requirement.amount).quantize(Decimal("0.01")):
        return False
    if requirement.vehicle_plate and (invoice.plate_number or "") != requirement.vehicle_plate:
        return False
    candidate_dates = [invoice.passage_start_date, invoice.passage_end_date, invoice.issue_date]
    return any(_date_in_window(candidate, requirement.date_window_start, requirement.date_window_end) for candidate in candidate_dates)


def _date_in_window(candidate: str | None, start: str, end: str) -> bool:
    if not candidate:
        return False
    try:
        candidate_date = date.fromisoformat(candidate[:10])
        start_date = date.fromisoformat(start[:10])
        end_date = date.fromisoformat(end[:10])
    except ValueError:
        return False
    return start_date <= candidate_date <= end_date


def _zip_entries(entries: dict[str, bytes]) -> bytes:
    buffer = BytesIO()
    with ZipFile(buffer, "w") as archive:
        for path, content in entries.items():
            archive.writestr(path, content)
    return buffer.getvalue()

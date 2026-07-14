from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Any

import fin_ops_platform.services.etc_document_parsers as etc_document_parsers
from fin_ops_platform.services.etc_document_parsers import (
    CcbCreditCardStatementParser,
    SupplementEvidenceParser,
    TicketRootClipboardTextParser,
    TicketRootDocumentParser,
)
from fin_ops_platform.services.etc_reconciliation_models import (
    FileParseResult,
    ParseIssue,
    ParseIssueSeverity,
    SourceFileKind,
)


@dataclass(frozen=True)
class EtcReconciliationSourceUpload:
    file_name: str
    content: bytes


class EtcReconciliationWrongSourceSlotError(ValueError):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class EtcReconciliationSourceUploadService:
    def __init__(self, *, task_service: Any) -> None:
        self._task_service = task_service

    def upload_sources(
        self,
        *,
        task_id: str,
        source_kind: SourceFileKind,
        expected_version: int,
        actor: str,
        uploads: list[EtcReconciliationSourceUpload],
        evidence_kind_override: str | None = None,
    ) -> Any:
        if not uploads:
            raise ValueError("invalid_reconciliation_upload")
        task = self._task_service.get_task(task_id)
        if task.version != expected_version:
            raise ValueError("task_version_conflict")
        ticket_root_upload_modes = self._ticket_root_upload_modes(
            task=task,
            source_kind=source_kind,
            uploads=uploads,
        )
        for upload_index, upload in enumerate(uploads):
            ticket_root_upload_mode = (
                ticket_root_upload_modes[upload_index]
                if source_kind == SourceFileKind.TICKET_ROOT and upload_index < len(ticket_root_upload_modes)
                else ""
            )
            content_type = (
                f"text/plain; charset={ticket_root_text_encoding(upload.content) or 'utf-8'}"
                if source_kind == SourceFileKind.TICKET_ROOT and ticket_root_upload_mode == "text_file"
                else "application/octet-stream"
            )
            source_file = self._task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=source_kind,
                original_name=upload.file_name,
                content_type=content_type,
                content=upload.content,
                created_by=actor,
            )
            parse_result = self._parse_uploaded_source(
                source_kind=source_kind,
                source_file=source_file,
                upload=upload,
                ticket_root_upload_mode=ticket_root_upload_mode,
                evidence_kind_override=evidence_kind_override,
            )
            task = self._task_service.apply_parse_result(
                task_id=task_id,
                parse_result=parse_result,
                actor=actor,
                require_source_file=True,
            )
        return task

    def submit_ticket_root_texts(
        self,
        *,
        task_id: str,
        expected_version: int,
        actor: str,
        texts: list[str],
    ) -> Any:
        task = self._task_service.get_task(task_id)
        if task.version != expected_version:
            raise ValueError("task_version_conflict")
        if has_ticket_root_text_file_source(task):
            raise ValueError("ticket_root_source_mode_conflict_text_file")
        if has_ticket_root_document_source(task):
            raise ValueError("ticket_root_source_mode_conflict_pdf")
        parser = TicketRootClipboardTextParser()
        for index, text in enumerate(texts, start=1):
            source_file = self._task_service.store_uploaded_source_file(
                task_id=task.task_id,
                source_kind=SourceFileKind.TICKET_ROOT,
                original_name=ticket_root_clipboard_source_name(text, index=index),
                content_type="text/plain; charset=utf-8",
                content=text.encode("utf-8"),
                created_by=actor,
            )
            parse_result = parser.parse_text(file_id=source_file.file_id, text=text)
            task = self._task_service.apply_parse_result(
                task_id=task_id,
                parse_result=parse_result,
                actor=actor,
                require_source_file=True,
            )
        return task

    def _ticket_root_upload_modes(
        self,
        *,
        task: Any,
        source_kind: SourceFileKind,
        uploads: list[EtcReconciliationSourceUpload],
    ) -> list[str]:
        if source_kind != SourceFileKind.TICKET_ROOT:
            return []
        upload_modes: list[str] = []
        for upload in uploads:
            wrong_slot_message = reconciliation_wrong_slot_message(
                expected_source_kind=source_kind,
                content=upload.content,
            )
            if wrong_slot_message:
                raise EtcReconciliationWrongSourceSlotError(wrong_slot_message)
            upload_modes.append(ticket_root_upload_source_mode(upload))
        validate_ticket_root_upload_source_mode(task=task, upload_modes=upload_modes)
        return upload_modes

    @staticmethod
    def _parse_uploaded_source(
        *,
        source_kind: SourceFileKind,
        source_file: Any,
        upload: EtcReconciliationSourceUpload,
        ticket_root_upload_mode: str,
        evidence_kind_override: str | None,
    ) -> FileParseResult:
        if source_kind == SourceFileKind.CREDIT_CARD_STATEMENT:
            return CcbCreditCardStatementParser().parse_pdf_bytes(
                file_id=source_file.file_id,
                content=upload.content,
            )
        if source_kind == SourceFileKind.TICKET_ROOT:
            if ticket_root_upload_mode == "text_file":
                decoded_text = decode_ticket_root_text(upload.content) or ""
                return (
                    TicketRootClipboardTextParser().parse_text(file_id=source_file.file_id, text=decoded_text)
                    if looks_like_ticket_root_clipboard_text(decoded_text)
                    else ticket_root_text_file_not_trip_result(source_file.file_id)
                )
            return TicketRootDocumentParser().parse_file(file_id=source_file.file_id, content=upload.content)
        return SupplementEvidenceParser().parse_text(
            file_id=source_file.file_id,
            text=upload.content.decode("utf-8", errors="ignore"),
            source_name=source_file.original_name,
            evidence_kind_override=evidence_kind_override,
        )


def validate_ticket_root_upload_source_mode(*, task: object, upload_modes: list[str]) -> None:
    unique_modes = {mode for mode in upload_modes if mode}
    if len(unique_modes) > 1:
        raise ValueError("ticket_root_source_mode_conflict_mixed_upload")
    upload_mode = next(iter(unique_modes), "")
    if upload_mode == "text_file":
        if has_ticket_root_manual_text_source(task):
            raise ValueError("ticket_root_source_mode_conflict")
        if has_ticket_root_document_source(task):
            raise ValueError("ticket_root_source_mode_conflict_pdf")
    elif upload_mode == "document":
        if has_ticket_root_manual_text_source(task):
            raise ValueError("ticket_root_source_mode_conflict")
        if has_ticket_root_text_file_source(task):
            raise ValueError("ticket_root_source_mode_conflict_text_file")


def reconciliation_wrong_slot_message(*, expected_source_kind: SourceFileKind, content: bytes) -> str | None:
    text = content.decode("utf-8", errors="ignore")
    if content.lstrip().startswith(b"%PDF"):
        extracted_text = etc_document_parsers._extract_pdf_text(content)
        if extracted_text.strip():
            text = f"{text}\n{extracted_text}"
    if not text.strip():
        return None
    looks_like_statement = any(
        marker in text
        for marker in (
            "龙卡信用卡对账单",
            "中国建设银行信用卡账单",
            "建设银行信用卡账单",
            "信用卡账单",
            "Credit Card Statement",
            "Statement Date",
            "Payment Due Date",
        )
    )
    looks_like_ticket_root = any(
        marker in text
        for marker in ("票根网", "通行明细", "车牌号", "发票张数", "入口站", "出口站")
    )
    if expected_source_kind == SourceFileKind.TICKET_ROOT and looks_like_statement:
        return "检测到信用卡账单，请上传到信用卡账单栏。"
    if expected_source_kind == SourceFileKind.CREDIT_CARD_STATEMENT and looks_like_ticket_root:
        return "检测到票根网文件，请上传到票根网栏。"
    return None


def is_ticket_root_source(source_file: object) -> bool:
    raw_kind = getattr(getattr(source_file, "source_kind", ""), "value", getattr(source_file, "source_kind", ""))
    return str(raw_kind) == SourceFileKind.TICKET_ROOT.value


def is_ticket_root_manual_text_source(source_file: object) -> bool:
    if not is_ticket_root_source(source_file):
        return False
    original_name = str(getattr(source_file, "original_name", "") or "")
    return original_name.startswith("票根网手工粘贴-")


def is_ticket_root_text_file_source(source_file: object) -> bool:
    if not is_ticket_root_source(source_file) or is_ticket_root_manual_text_source(source_file):
        return False
    content_type = str(getattr(source_file, "content_type", "") or "").lower()
    return content_type.startswith("text/plain")


def is_ticket_root_document_source(source_file: object) -> bool:
    return (
        is_ticket_root_source(source_file)
        and not is_ticket_root_manual_text_source(source_file)
        and not is_ticket_root_text_file_source(source_file)
    )


def has_ticket_root_clipboard_source(task: object) -> bool:
    return has_ticket_root_manual_text_source(task)


def has_ticket_root_manual_text_source(task: object) -> bool:
    return any(is_ticket_root_manual_text_source(source_file) for source_file in getattr(task, "source_files", []) or [])


def has_ticket_root_text_file_source(task: object) -> bool:
    return any(is_ticket_root_text_file_source(source_file) for source_file in getattr(task, "source_files", []) or [])


def has_ticket_root_text_source(task: object) -> bool:
    return has_ticket_root_manual_text_source(task) or has_ticket_root_text_file_source(task)


def has_ticket_root_file_source(task: object) -> bool:
    return has_ticket_root_document_source(task)


def has_ticket_root_document_source(task: object) -> bool:
    return any(is_ticket_root_document_source(source_file) for source_file in getattr(task, "source_files", []) or [])


def ticket_root_upload_source_mode(upload: EtcReconciliationSourceUpload) -> str:
    decoded_text = decode_ticket_root_text(upload.content)
    if decoded_text is None:
        return "document"
    lower_name = str(upload.file_name or "").strip().lower()
    if lower_name.endswith((".txt", ".text")):
        return "text_file"
    if looks_like_ticket_root_clipboard_text(decoded_text):
        return "text_file"
    return "document"


TEXT_FILE_ENCODINGS = ("utf-8-sig", "utf-8", "gb18030", "gbk")


def decode_ticket_root_text(content: bytes) -> str | None:
    decoded = decode_text_file_content(content)
    return decoded[0] if decoded is not None else None


def ticket_root_text_encoding(content: bytes) -> str | None:
    decoded = decode_text_file_content(content)
    return decoded[1] if decoded is not None else None


def decode_text_file_content(content: bytes) -> tuple[str, str] | None:
    for encoding in TEXT_FILE_ENCODINGS:
        try:
            text = content.decode(encoding)
        except UnicodeDecodeError:
            continue
        if "\x00" in text or not text.strip():
            return None
        return text, "utf-8" if encoding == "utf-8-sig" else encoding
    return None


def looks_like_ticket_root_clipboard_text(text: str) -> bool:
    normalized = str(text or "")
    if not normalized.strip():
        return False
    has_ticket_root_context = any(marker in normalized for marker in ("票根网", "收费公路通行费电子发票服务平台", "我的ETC"))
    has_plate = "车牌号" in normalized
    has_trip_amount_row = bool(re.search(r"交易时间\s*[:：]?\s*\d{4}[-/]\d{2}[-/]\d{2}.*?交易金额\s*[:：]?", normalized, flags=re.S))
    has_station_header = "入口收费站/出口收费站" in normalized
    return has_ticket_root_context and has_plate and (has_trip_amount_row or has_station_header)


def ticket_root_text_file_not_trip_result(file_id: str) -> FileParseResult:
    issue_id = hashlib.sha256(f"{file_id}|ticket_root_text_file_not_trip".encode("utf-8")).hexdigest()[:32]
    return FileParseResult(
        file_id=file_id,
        parser_code=TicketRootClipboardTextParser.parser_code,
        issues=[
            ParseIssue(
                issue_id=issue_id,
                file_id=file_id,
                severity=ParseIssueSeverity.BLOCKING,
                message="请上传票根网按行程查看复制文本文件。",
                extraction_method=TicketRootClipboardTextParser.extraction_method,
                field_name="ticket_root_text",
            )
        ],
    )


def ticket_root_clipboard_source_name(text: str, *, index: int) -> str:
    parser = TicketRootClipboardTextParser()
    plate = parser.extract_plate(text) or "未知车牌"
    month = parser.extract_month(text) or f"{index}"
    return f"票根网手工粘贴-{plate}-{month}-{index}.txt"

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import Enum
from io import BytesIO
from pathlib import Path
import hashlib
import json
import mimetypes
import os
import pickle
import re
from typing import Any, Callable, Protocol
import xml.etree.ElementTree as ET
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin
from urllib.request import Request, urlopen
from uuid import uuid4
from zipfile import BadZipFile, ZipFile


class EtcInvoiceStatus(str, Enum):
    UNSUBMITTED = "unsubmitted"
    SUBMITTED = "submitted"


class EtcBatchStatus(str, Enum):
    DRAFT_CREATING = "draft_creating"
    DRAFT_CREATED = "draft_created"
    SUBMITTED_CONFIRMED = "submitted_confirmed"
    NOT_SUBMITTED = "not_submitted"
    FAILED = "failed"


class EtcServiceError(RuntimeError):
    pass


class EtcInvoiceRequestError(EtcServiceError):
    pass


class EtcInvoiceNotFoundError(EtcInvoiceRequestError):
    pass


class EtcBatchNotFoundError(EtcServiceError):
    pass


class EtcDraftRequestError(EtcServiceError):
    pass


class EtcOAClientError(RuntimeError):
    pass


class EtcOAClient(Protocol):
    def upload_attachment(self, path: Path) -> str:
        raise NotImplementedError

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        raise NotImplementedError


class NotConfiguredEtcOAClient:
    def upload_attachment(self, path: Path) -> str:
        raise EtcOAClientError("ETC OA client is not configured.")

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        raise EtcOAClientError("ETC OA client is not configured.")


@dataclass(frozen=True, slots=True)
class EtcOAHttpClientSettings:
    base_url: str | None
    file_upload_path: str = "/file/upload"
    form_draft_path_template: str = "/forms/form/{form_id}/records/record"
    draft_url_template: str = "https://www.yn-sourcing.com/oa/#/normal/forms/form/{form_id}?formId={form_id}&id={draft_id}"
    request_timeout_ms: int = 20000

    @classmethod
    def from_environment(cls) -> "EtcOAHttpClientSettings":
        return cls(
            base_url=os.getenv("FIN_OPS_ETC_OA_BASE_URL") or os.getenv("FIN_OPS_OA_BASE_URL"),
            file_upload_path=os.getenv("FIN_OPS_ETC_OA_FILE_UPLOAD_PATH", "/file/upload").strip() or "/file/upload",
            form_draft_path_template=(
                os.getenv("FIN_OPS_ETC_OA_FORM_DRAFT_PATH", "/forms/form/{form_id}/records/record").strip()
                or "/forms/form/{form_id}/records/record"
            ),
            draft_url_template=(
                os.getenv(
                    "FIN_OPS_ETC_OA_DRAFT_URL_TEMPLATE",
                    "https://www.yn-sourcing.com/oa/#/normal/forms/form/{form_id}?formId={form_id}&id={draft_id}",
                ).strip()
                or "https://www.yn-sourcing.com/oa/#/normal/forms/form/{form_id}?formId={form_id}&id={draft_id}"
            ),
            request_timeout_ms=int(os.getenv("FIN_OPS_ETC_OA_REQUEST_TIMEOUT_MS", os.getenv("FIN_OPS_OA_REQUEST_TIMEOUT_MS", "20000"))),
        )


class HttpEtcOAClient:
    def __init__(self, *, token: str, settings: EtcOAHttpClientSettings | None = None) -> None:
        self._token = token.strip()
        self._settings = settings or EtcOAHttpClientSettings.from_environment()
        if not self._settings.base_url:
            raise EtcOAClientError("ETC OA client base URL is not configured.")
        if not self._token:
            raise EtcOAClientError("ETC OA client token is missing.")

    def upload_attachment(self, path: Path) -> str:
        if not path.exists() or not path.is_file():
            raise EtcOAClientError(f"ETC attachment file is missing: {path.name}")
        boundary = f"----finops-etc-{uuid4().hex}"
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        body = b"".join(
            [
                f"--{boundary}\r\n".encode("utf-8"),
                (
                    f'Content-Disposition: form-data; name="file"; filename="{path.name}"\r\n'
                    f"Content-Type: {content_type}\r\n\r\n"
                ).encode("utf-8"),
                path.read_bytes(),
                b"\r\n",
                f"--{boundary}--\r\n".encode("utf-8"),
            ]
        )
        payload = self._send_json(
            self._settings.file_upload_path,
            method="POST",
            body=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        data = payload.get("data")
        if isinstance(data, dict):
            for key in ("url", "id", "fileId", "file_id", "path"):
                value = data.get(key)
                if value not in (None, ""):
                    return str(value)
        if isinstance(data, str) and data.strip():
            return data.strip()
        raise EtcOAClientError("OA attachment upload response did not include a file id or URL.")

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        path = self._settings.form_draft_path_template.format(form_id=form_id)
        response_payload = self._send_json(
            path,
            method="POST",
            body=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            content_type="application/json;charset=utf-8",
        )
        draft_id = self._extract_draft_id(response_payload)
        draft_url = self._settings.draft_url_template.format(form_id=form_id, draft_id=quote(draft_id, safe=""))
        return draft_id, draft_url

    def _send_json(self, path: str, *, method: str, body: bytes, content_type: str) -> dict[str, object]:
        assert self._settings.base_url is not None
        url = urljoin(f"{self._settings.base_url.rstrip('/')}/", path.lstrip("/"))
        request = Request(
            url,
            data=body,
            headers={
                "Authorization": f"Bearer {self._token}",
                "Accept": "application/json",
                "Content-Type": content_type,
            },
            method=method,
        )
        timeout_seconds = max(self._settings.request_timeout_ms / 1000, 1)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            raw_body = error.read().decode("utf-8", errors="ignore")
            raise EtcOAClientError(_extract_oa_error_message(raw_body) or f"OA request failed with HTTP {error.code}.") from error
        except URLError as error:
            raise EtcOAClientError("Unable to connect to OA service.") from error
        try:
            payload = json.loads(raw_body) if raw_body.strip() else {}
        except json.JSONDecodeError as error:
            raise EtcOAClientError("OA service returned invalid JSON.") from error
        if not isinstance(payload, dict):
            raise EtcOAClientError("OA service returned an invalid response shape.")
        code = payload.get("code", 200)
        if code not in {0, 200, "0", "200", None}:
            raise EtcOAClientError(_extract_oa_error_message(payload) or "OA service rejected the request.")
        return payload

    @staticmethod
    def _extract_draft_id(payload: dict[str, object]) -> str:
        data = payload.get("data")
        if isinstance(data, str) and data.strip():
            return data.strip()
        if isinstance(data, dict):
            for key in ("id", "recordId", "record_id", "businessKey", "business_key"):
                value = data.get(key)
                if value not in (None, ""):
                    return str(value)
        for key in ("id", "recordId", "record_id"):
            value = payload.get(key)
            if value not in (None, ""):
                return str(value)
        raise EtcOAClientError("OA draft response did not include a draft id.")


@dataclass(slots=True)
class UploadedEtcZipFile:
    file_name: str
    content: bytes


@dataclass(slots=True)
class EtcInvoice:
    id: str
    invoice_number: str
    issue_date: str
    passage_start_date: str | None
    passage_end_date: str | None
    plate_number: str | None
    vehicle_type: str | None
    seller_name: str | None
    seller_tax_no: str | None
    buyer_name: str | None
    buyer_tax_no: str | None
    amount_without_tax: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_rate: str | None
    zip_source_name: str
    xml_file_path: str | None
    xml_file_hash: str | None
    pdf_file_path: str | None
    pdf_file_hash: str | None
    status: EtcInvoiceStatus = EtcInvoiceStatus.UNSUBMITTED
    current_batch_id: str | None = None
    last_batch_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class EtcBatch:
    id: str
    etc_batch_id: str
    invoice_ids: list[str]
    invoice_count: int
    total_amount: Decimal
    oa_form_id: int = 2
    oa_draft_id: str | None = None
    oa_draft_url: str | None = None
    oa_marker: str = ""
    status: str = EtcBatchStatus.DRAFT_CREATING.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confirmed_at: datetime | None = None
    error_message: str | None = None


@dataclass(slots=True)
class EtcImportItem:
    file_name: str
    invoice_number: str | None
    status: str
    message: str = ""

    def to_payload(self) -> dict[str, object]:
        return {
            "fileName": self.file_name,
            "invoiceNumber": self.invoice_number,
            "status": self.status,
            "message": self.message,
        }


@dataclass(slots=True)
class EtcImportResult:
    imported: int = 0
    duplicates_skipped: int = 0
    attachments_completed: int = 0
    failed: int = 0
    items: list[EtcImportItem] = field(default_factory=list)

    def to_payload(self) -> dict[str, object]:
        return {
            "imported": self.imported,
            "duplicatesSkipped": self.duplicates_skipped,
            "attachmentsCompleted": self.attachments_completed,
            "failed": self.failed,
            "items": [item.to_payload() for item in self.items],
        }

    def summary_payload(self) -> dict[str, int]:
        return {
            "imported": self.imported,
            "duplicatesSkipped": self.duplicates_skipped,
            "attachmentsCompleted": self.attachments_completed,
            "failed": self.failed,
        }


@dataclass(slots=True)
class EtcImportSession:
    session_id: str
    uploads: list[UploadedEtcZipFile]
    created_at: datetime
    preview_result: EtcImportResult
    confirmed_result: EtcImportResult | None = None
    confirmed_at: datetime | None = None


@dataclass(slots=True)
class EtcDraftResult:
    batch_id: str
    etc_batch_id: str
    oa_draft_id: str
    oa_draft_url: str


@dataclass(frozen=True, slots=True)
class EtcOAFormFieldMapping:
    applicant: str = "applicant"
    application_date: str = "application_date"
    project_name: str = "project_name"
    amount: str = "amount"
    cause: str = "cause"
    attachments: str = "attachments"

    @classmethod
    def from_environment(cls) -> EtcOAFormFieldMapping:
        return cls(
            applicant=os.getenv("FIN_OPS_ETC_OA_FIELD_APPLICANT", "applicant"),
            application_date=os.getenv("FIN_OPS_ETC_OA_FIELD_APPLICATION_DATE", "application_date"),
            project_name=os.getenv("FIN_OPS_ETC_OA_FIELD_PROJECT_NAME", "project_name"),
            amount=os.getenv("FIN_OPS_ETC_OA_FIELD_AMOUNT", "amount"),
            cause=os.getenv("FIN_OPS_ETC_OA_FIELD_CAUSE", "cause"),
            attachments=os.getenv("FIN_OPS_ETC_OA_FIELD_ATTACHMENTS", "attachments"),
        )


@dataclass(slots=True)
class ParsedEtcXml:
    invoice_number: str
    issue_date: str
    passage_start_date: str | None
    passage_end_date: str | None
    plate_number: str | None
    vehicle_type: str | None
    seller_name: str | None
    seller_tax_no: str | None
    buyer_name: str | None
    buyer_tax_no: str | None
    amount_without_tax: Decimal
    tax_amount: Decimal
    total_amount: Decimal
    tax_rate: str | None


@dataclass(slots=True)
class _ArchiveEntry:
    source_name: str
    path: str
    content: bytes


SAFE_PATH_RE = re.compile(r"[^A-Za-z0-9._-]+")


FIELD_ALIASES = {
    "invoice_number": ("InvoiceNumber", "EIid", "invoice_number", "fphm", "发票号码", "发票号"),
    "issue_date": ("IssueDate", "IssueTime", "RequestTime", "issue_date", "kprq", "开票日期", "开票时间"),
    "passage_start_date": ("PassageStartDate", "StartDatesOfPassage", "passage_start_date", "通行开始日期", "通行日期起"),
    "passage_end_date": ("PassageEndDate", "EndDatesOfPassage", "passage_end_date", "通行结束日期", "通行日期止"),
    "plate_number": ("PlateNumber", "plate_number", "cph", "车牌号", "车牌"),
    "vehicle_type": ("VehicleType", "vehicle_type", "车辆类型", "车型"),
    "seller_name": ("SellerName", "seller_name", "销方名称", "销售方名称"),
    "seller_tax_no": ("SellerTaxNo", "SellerIdNum", "seller_tax_no", "销方识别号", "销售方纳税人识别号"),
    "buyer_name": ("BuyerName", "buyer_name", "购方名称", "购买方名称"),
    "buyer_tax_no": ("BuyerTaxNo", "BuyerIdNum", "buyer_tax_no", "购方识别号", "购买方纳税人识别号"),
    "amount_without_tax": ("AmountWithoutTax", "TotalAmWithoutTax", "amount_without_tax", "不含税金额", "金额"),
    "tax_amount": ("TaxAmount", "TotalTaxAm", "tax_amount", "税额"),
    "total_amount": ("TotalAmount", "TotalTax-includedAmount", "TotaltaxIncludedAmount", "total_amount", "价税合计", "合计金额"),
    "tax_rate": ("TaxRate", "tax_rate", "税率"),
}


class EtcService:
    def __init__(
        self,
        *,
        data_dir: Path | None = None,
        state_store: Any | None = None,
        oa_client: EtcOAClient | None = None,
        form_mapping: EtcOAFormFieldMapping | None = None,
    ) -> None:
        root = data_dir or getattr(state_store, "data_dir", None)
        self._data_dir = Path(root) if root is not None else Path.cwd() / ".runtime" / "fin_ops_platform"
        self._state_store = state_store
        self._etc_dir = self._data_dir / "etc"
        self._invoice_file_root = self._etc_dir / "invoices"
        self._state_path = self._etc_dir / "etc_state.pkl"
        self._invoice_file_root.mkdir(parents=True, exist_ok=True)
        self.oa_client: EtcOAClient = oa_client or NotConfiguredEtcOAClient()
        self._form_mapping = form_mapping or EtcOAFormFieldMapping.from_environment()
        self._invoice_counter = 0
        self._batch_counter = 0
        self._batch_day_counters: dict[str, int] = {}
        self._invoices: dict[str, EtcInvoice] = {}
        self._invoice_numbers: dict[str, str] = {}
        self._batches: dict[str, EtcBatch] = {}
        self._import_sessions: dict[str, EtcImportSession] = {}
        self._hydrate(self._load_snapshot())

    def import_zips(self, uploads: list[UploadedEtcZipFile]) -> EtcImportResult:
        return self._process_import_zips(uploads, persist=True)

    def preview_import_zips(self, uploads: list[UploadedEtcZipFile]) -> dict[str, object]:
        result = self._process_import_zips(uploads, persist=False)
        session_id = uuid4().hex
        self._import_sessions[session_id] = EtcImportSession(
            session_id=session_id,
            uploads=[UploadedEtcZipFile(upload.file_name, bytes(upload.content)) for upload in uploads],
            created_at=datetime.now(UTC),
            preview_result=result,
        )
        return self._import_session_payload(session_id, result)

    def confirm_import_session(self, session_id: str) -> EtcImportResult:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        if session.confirmed_result is not None:
            return session.confirmed_result
        result = self._process_import_zips(session.uploads, persist=True)
        session.confirmed_result = result
        session.confirmed_at = datetime.now(UTC)
        return result

    def get_import_session_item_total(self, session_id: str) -> int:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        return len(session.preview_result.items)

    def confirm_import_session_with_progress(
        self,
        session_id: str,
        progress_callback: Callable[[EtcImportResult], None] | None = None,
    ) -> EtcImportResult:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        if session.confirmed_result is not None:
            if progress_callback is not None:
                progress_callback(session.confirmed_result)
            return session.confirmed_result
        result = self._process_import_zips(session.uploads, persist=True, progress_callback=progress_callback)
        session.confirmed_result = result
        session.confirmed_at = datetime.now(UTC)
        return result

    def import_result_payload(self, result: EtcImportResult) -> dict[str, object]:
        return {
            **result.summary_payload(),
            "summary": result.summary_payload(),
            "items": [item.to_payload() for item in result.items],
        }

    def _import_session_payload(self, session_id: str, result: EtcImportResult) -> dict[str, object]:
        payload = self.import_result_payload(result)
        return {
            "sessionId": session_id,
            **payload,
        }

    def _process_import_zips(
        self,
        uploads: list[UploadedEtcZipFile],
        *,
        persist: bool,
        progress_callback: Callable[[EtcImportResult], None] | None = None,
    ) -> EtcImportResult:
        result = EtcImportResult()
        preview_state: dict[str, tuple[bool, bool]] = {
            invoice.invoice_number: (
                self._stored_invoice_file_exists(invoice.xml_file_path),
                self._stored_invoice_file_exists(invoice.pdf_file_path),
            )
            for invoice in self._invoices.values()
        }
        for upload in uploads:
            try:
                entries = self._extract_archive_entries(upload.file_name, upload.content)
            except BadZipFile as exc:
                result.failed += 1
                result.items.append(EtcImportItem(upload.file_name, None, "failed", f"zip 解析失败: {exc}"))
                if progress_callback is not None:
                    progress_callback(result)
                continue
            xml_entries = [entry for entry in entries if self._is_xml_entry(entry.path)]
            if not xml_entries:
                result.failed += 1
                result.items.append(EtcImportItem(upload.file_name, None, "failed", "缺 XML，不能生成 ETC 发票记录。"))
                if progress_callback is not None:
                    progress_callback(result)
                continue
            pdf_entries = [entry for entry in entries if self._is_pdf_entry(entry.path)]
            for xml_entry in xml_entries:
                try:
                    parsed = parse_etc_xml(xml_entry.content)
                    pdf_entry = self._match_pdf_entry(parsed.invoice_number, xml_entry.path, pdf_entries)
                    if persist:
                        status = self._upsert_invoice_from_import(upload.file_name, parsed, xml_entry, pdf_entry)
                    else:
                        status = self._preview_invoice_import_status(parsed, pdf_entry, preview_state)
                except Exception as exc:
                    result.failed += 1
                    result.items.append(EtcImportItem(xml_entry.path, None, "failed", str(exc)))
                    continue
                if status == "imported":
                    result.imported += 1
                elif status == "duplicate_skipped":
                    result.duplicates_skipped += 1
                elif status == "attachment_completed":
                    result.attachments_completed += 1
                result.items.append(EtcImportItem(xml_entry.path, parsed.invoice_number, status))
                if progress_callback is not None:
                    progress_callback(result)
        if persist:
            self._persist()
        return result

    def list_invoices(
        self,
        *,
        status: EtcInvoiceStatus | str | None = None,
        month: str | None = None,
        plate: str | None = None,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[EtcInvoice], int, dict[str, int]]:
        resolved_status = _coerce_invoice_status(status) if status else None
        all_invoices = list(self._invoices.values())
        status_counts = {
            EtcInvoiceStatus.UNSUBMITTED.value: sum(1 for invoice in all_invoices if invoice.status == EtcInvoiceStatus.UNSUBMITTED),
            EtcInvoiceStatus.SUBMITTED.value: sum(1 for invoice in all_invoices if invoice.status == EtcInvoiceStatus.SUBMITTED),
        }
        filtered = [
            invoice
            for invoice in all_invoices
            if (resolved_status is None or invoice.status == resolved_status)
            and (not month or (invoice.issue_date or "").startswith(month))
            and (not plate or plate.lower() in (invoice.plate_number or "").lower())
            and (not keyword or self._invoice_matches_keyword(invoice, keyword))
        ]
        filtered.sort(key=lambda item: (item.issue_date or "", item.invoice_number), reverse=True)
        total = len(filtered)
        current_counts = dict(status_counts)
        current_counts["current"] = total
        safe_page = max(int(page or 1), 1)
        safe_page_size = min(max(int(page_size or 50), 1), 500)
        start = (safe_page - 1) * safe_page_size
        return filtered[start:start + safe_page_size], total, current_counts

    def update_invoice_status(self, invoice_ids: list[str], status: EtcInvoiceStatus | str) -> None:
        resolved_status = _coerce_invoice_status(status)
        now = datetime.now(UTC)
        for invoice_id in invoice_ids:
            invoice = self._get_invoice(invoice_id)
            invoice.status = resolved_status
            if resolved_status == EtcInvoiceStatus.UNSUBMITTED:
                invoice.current_batch_id = None
            invoice.updated_at = now
        self._persist()

    def revoke_submitted(self, invoice_ids: list[str]) -> dict[str, int]:
        if not invoice_ids:
            raise EtcInvoiceRequestError("invoiceIds must not be empty.")
        updated = 0
        now = datetime.now(UTC)
        for invoice_id in invoice_ids:
            invoice = self._get_invoice(invoice_id)
            if invoice.status == EtcInvoiceStatus.SUBMITTED:
                updated += 1
            invoice.status = EtcInvoiceStatus.UNSUBMITTED
            invoice.current_batch_id = None
            invoice.updated_at = now
        self._persist()
        return {"updated": updated}

    def create_oa_draft(self, invoice_ids: list[str], *, oa_client: EtcOAClient | None = None) -> EtcDraftResult:
        invoices = self._validate_draft_invoices(invoice_ids)
        batch = self._create_batch(invoices)
        resolved_oa_client = oa_client or self.oa_client
        try:
            attachment_ids = self._upload_batch_attachments(invoices, resolved_oa_client)
            payload = self._build_oa_draft_payload(batch, invoices, attachment_ids)
            oa_draft_id, oa_draft_url = resolved_oa_client.create_form_draft(form_id=2, payload=payload)
        except EtcOAClientError as exc:
            batch.status = EtcBatchStatus.FAILED.value
            batch.error_message = str(exc)
            self._persist()
            raise EtcDraftRequestError(str(exc)) from exc

        batch.status = EtcBatchStatus.DRAFT_CREATED.value
        batch.oa_draft_id = oa_draft_id
        batch.oa_draft_url = oa_draft_url
        now = datetime.now(UTC)
        for invoice in invoices:
            invoice.current_batch_id = batch.id
            invoice.last_batch_id = batch.id
            invoice.updated_at = now
        self._persist()
        return EtcDraftResult(
            batch_id=batch.id,
            etc_batch_id=batch.etc_batch_id,
            oa_draft_id=oa_draft_id,
            oa_draft_url=oa_draft_url,
        )

    def confirm_submitted(self, batch_id: str) -> EtcBatch:
        batch = self.get_batch(batch_id)
        if batch.status == EtcBatchStatus.FAILED.value:
            raise EtcDraftRequestError("failed batch cannot be confirmed submitted.")
        batch.status = EtcBatchStatus.SUBMITTED_CONFIRMED.value
        batch.confirmed_at = batch.confirmed_at or datetime.now(UTC)
        now = datetime.now(UTC)
        for invoice_id in batch.invoice_ids:
            invoice = self._get_invoice(invoice_id)
            invoice.status = EtcInvoiceStatus.SUBMITTED
            invoice.current_batch_id = batch.id
            invoice.last_batch_id = batch.id
            invoice.updated_at = now
        self._persist()
        return replace(batch, invoice_ids=list(batch.invoice_ids))

    def mark_not_submitted(self, batch_id: str) -> EtcBatch:
        batch = self.get_batch(batch_id)
        batch.status = EtcBatchStatus.NOT_SUBMITTED.value
        now = datetime.now(UTC)
        for invoice_id in batch.invoice_ids:
            invoice = self._get_invoice(invoice_id)
            invoice.status = EtcInvoiceStatus.UNSUBMITTED
            invoice.current_batch_id = None
            invoice.last_batch_id = batch.id
            invoice.updated_at = now
        self._persist()
        return replace(batch, invoice_ids=list(batch.invoice_ids))

    def get_batch(self, batch_id: str) -> EtcBatch:
        batch = self._batches.get(batch_id)
        if batch is None:
            raise EtcBatchNotFoundError(f"ETC batch not found: {batch_id}")
        return batch

    def list_batches(self) -> list[EtcBatch]:
        return sorted(self._batches.values(), key=lambda batch: batch.created_at)

    def snapshot(self) -> dict[str, object]:
        return {
            "invoice_counter": self._invoice_counter,
            "batch_counter": self._batch_counter,
            "batch_day_counters": self._batch_day_counters,
            "invoices": self._invoices,
            "invoice_numbers": self._invoice_numbers,
            "batches": self._batches,
        }

    def _hydrate(self, snapshot: dict[str, object]) -> None:
        self._invoice_counter = int(snapshot.get("invoice_counter", 0) or 0)
        self._batch_counter = int(snapshot.get("batch_counter", 0) or 0)
        self._batch_day_counters = dict(snapshot.get("batch_day_counters") or {})
        self._invoices = dict(snapshot.get("invoices") or {})
        self._invoice_numbers = dict(snapshot.get("invoice_numbers") or {})
        self._batches = dict(snapshot.get("batches") or {})
        for invoice in self._invoices.values():
            if isinstance(invoice.status, str):
                invoice.status = _coerce_invoice_status(invoice.status)

    def _load_snapshot(self) -> dict[str, object]:
        if self._state_store is not None and hasattr(self._state_store, "load_etc_state"):
            loaded = self._state_store.load_etc_state()
            return loaded if isinstance(loaded, dict) else {}
        if not self._state_path.exists():
            return {}
        with self._state_path.open("rb") as handle:
            loaded = pickle.load(handle)  # noqa: S301 - trusted local application state
        return loaded if isinstance(loaded, dict) else {}

    def _persist(self) -> None:
        if self._state_store is not None and hasattr(self._state_store, "save_etc_state"):
            self._state_store.save_etc_state(self.snapshot())
            return
        self._etc_dir.mkdir(parents=True, exist_ok=True)
        with self._state_path.open("wb") as handle:
            pickle.dump(self.snapshot(), handle)

    def _extract_archive_entries(self, source_name: str, content: bytes, *, depth: int = 0) -> list[_ArchiveEntry]:
        if depth > 8:
            raise BadZipFile("nested zip depth exceeds limit")
        entries: list[_ArchiveEntry] = []
        with ZipFile(BytesIO(content)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                file_content = archive.read(info)
                path = info.filename
                if path.lower().endswith(".zip"):
                    entries.extend(self._extract_archive_entries(f"{source_name}/{path}", file_content, depth=depth + 1))
                else:
                    entries.append(_ArchiveEntry(source_name, path, file_content))
        return entries

    @staticmethod
    def _is_xml_entry(path: str) -> bool:
        parts = [part.lower() for part in Path(path).parts]
        return path.lower().endswith(".xml") and "xml" in parts

    @staticmethod
    def _is_pdf_entry(path: str) -> bool:
        parts = [part.lower() for part in Path(path).parts]
        return path.lower().endswith(".pdf") and "pdf" in parts

    @staticmethod
    def _match_pdf_entry(invoice_number: str, xml_path: str, pdf_entries: list[_ArchiveEntry]) -> _ArchiveEntry | None:
        xml_stem = Path(xml_path).stem.lower()
        invoice_key = invoice_number.lower()
        for entry in pdf_entries:
            stem = Path(entry.path).stem.lower()
            if invoice_key in stem or stem in invoice_key or stem == xml_stem:
                return entry
        return None

    @staticmethod
    def _preview_invoice_import_status(
        parsed: ParsedEtcXml,
        pdf_entry: _ArchiveEntry | None,
        preview_state: dict[str, tuple[bool, bool]],
    ) -> str:
        has_pdf = pdf_entry is not None
        existing = preview_state.get(parsed.invoice_number)
        if existing is None:
            preview_state[parsed.invoice_number] = (True, has_pdf)
            return "imported"

        has_xml_before, has_pdf_before = existing
        if has_xml_before and has_pdf_before:
            return "duplicate_skipped"

        completed = False
        has_xml_after = has_xml_before
        has_pdf_after = has_pdf_before
        if not has_xml_after:
            has_xml_after = True
            completed = True
        if has_pdf and not has_pdf_after:
            has_pdf_after = True
            completed = True
        preview_state[parsed.invoice_number] = (has_xml_after, has_pdf_after)
        return "attachment_completed" if completed else "duplicate_skipped"

    def _upsert_invoice_from_import(
        self,
        zip_source_name: str,
        parsed: ParsedEtcXml,
        xml_entry: _ArchiveEntry,
        pdf_entry: _ArchiveEntry | None,
    ) -> str:
        existing_id = self._invoice_numbers.get(parsed.invoice_number)
        existing = self._invoices.get(existing_id) if existing_id else None
        existing_has_xml = existing is not None and self._stored_invoice_file_exists(existing.xml_file_path)
        existing_has_pdf = existing is not None and self._stored_invoice_file_exists(existing.pdf_file_path)
        if existing is not None and existing_has_xml and existing_has_pdf:
            return "duplicate_skipped"

        xml_path, xml_hash = (None, None)
        pdf_path, pdf_hash = (None, None)
        now = datetime.now(UTC)
        if existing is None or not existing_has_xml:
            xml_path, xml_hash = self._store_invoice_file(parsed, "invoice.xml", xml_entry.content)
        if pdf_entry is not None and (existing is None or not existing_has_pdf):
            pdf_path, pdf_hash = self._store_invoice_file(parsed, "invoice.pdf", pdf_entry.content)

        if existing is None:
            invoice = EtcInvoice(
                id=self._next_invoice_id(),
                invoice_number=parsed.invoice_number,
                issue_date=parsed.issue_date,
                passage_start_date=parsed.passage_start_date,
                passage_end_date=parsed.passage_end_date,
                plate_number=parsed.plate_number,
                vehicle_type=parsed.vehicle_type,
                seller_name=parsed.seller_name,
                seller_tax_no=parsed.seller_tax_no,
                buyer_name=parsed.buyer_name,
                buyer_tax_no=parsed.buyer_tax_no,
                amount_without_tax=parsed.amount_without_tax,
                tax_amount=parsed.tax_amount,
                total_amount=parsed.total_amount,
                tax_rate=parsed.tax_rate,
                zip_source_name=zip_source_name,
                xml_file_path=xml_path,
                xml_file_hash=xml_hash,
                pdf_file_path=pdf_path,
                pdf_file_hash=pdf_hash,
                created_at=now,
                updated_at=now,
            )
            self._invoices[invoice.id] = invoice
            self._invoice_numbers[invoice.invoice_number] = invoice.id
            return "imported"

        completed = False
        if not existing_has_xml and xml_path:
            existing.xml_file_path = xml_path
            existing.xml_file_hash = xml_hash
            completed = True
        if not existing_has_pdf and pdf_path:
            existing.pdf_file_path = pdf_path
            existing.pdf_file_hash = pdf_hash
            completed = True
        existing.updated_at = now
        return "attachment_completed" if completed else "duplicate_skipped"

    @staticmethod
    def _stored_invoice_file_exists(path: str | None) -> bool:
        return bool(path and Path(path).exists())

    def _store_invoice_file(self, parsed: ParsedEtcXml, file_name: str, content: bytes) -> tuple[str, str]:
        month = parsed.issue_date[:7] if parsed.issue_date else "unknown"
        year, month_part = (month.split("-", 1) + ["unknown"])[:2] if "-" in month else ("unknown", "unknown")
        invoice_dir = self._invoice_file_root / _safe_path_part(year) / _safe_path_part(month_part) / _safe_path_part(parsed.invoice_number)
        invoice_dir.mkdir(parents=True, exist_ok=True)
        path = invoice_dir / file_name
        path.write_bytes(content)
        return str(path), hashlib.sha256(content).hexdigest()

    @staticmethod
    def _invoice_matches_keyword(invoice: EtcInvoice, keyword: str) -> bool:
        needle = keyword.lower()
        fields = (
            invoice.invoice_number,
            invoice.seller_name or "",
            invoice.buyer_name or "",
            invoice.plate_number or "",
        )
        return any(needle in field.lower() for field in fields)

    def _validate_draft_invoices(self, invoice_ids: list[str]) -> list[EtcInvoice]:
        if not invoice_ids:
            raise EtcDraftRequestError("invoiceIds must not be empty.")
        invoices = [self._get_invoice(invoice_id) for invoice_id in invoice_ids]
        for invoice in invoices:
            if invoice.status != EtcInvoiceStatus.UNSUBMITTED:
                raise EtcDraftRequestError(f"ETC invoice {invoice.invoice_number} is already submitted.")
            if not invoice.xml_file_path or not invoice.pdf_file_path:
                raise EtcDraftRequestError(f"ETC invoice {invoice.invoice_number} is missing PDF or XML attachment.")
            if not Path(invoice.xml_file_path).exists() or not Path(invoice.pdf_file_path).exists():
                raise EtcDraftRequestError(f"ETC invoice {invoice.invoice_number} attachment file is missing.")
        return invoices

    def _create_batch(self, invoices: list[EtcInvoice]) -> EtcBatch:
        self._batch_counter += 1
        batch_id = f"etc_batch_{self._batch_counter:04d}"
        etc_batch_id = self._next_etc_batch_id()
        total_amount = sum((invoice.total_amount for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        marker = f"ETC批量提交\netc_batch_id={etc_batch_id}"
        batch = EtcBatch(
            id=batch_id,
            etc_batch_id=etc_batch_id,
            invoice_ids=[invoice.id for invoice in invoices],
            invoice_count=len(invoices),
            total_amount=total_amount,
            oa_marker=marker,
        )
        self._batches[batch.id] = batch
        self._persist()
        return batch

    def _upload_batch_attachments(self, invoices: list[EtcInvoice], oa_client: EtcOAClient) -> list[str]:
        attachment_ids: list[str] = []
        for invoice in invoices:
            assert invoice.pdf_file_path is not None
            assert invoice.xml_file_path is not None
            attachment_ids.append(oa_client.upload_attachment(Path(invoice.pdf_file_path)))
            attachment_ids.append(oa_client.upload_attachment(Path(invoice.xml_file_path)))
        return attachment_ids

    def _build_oa_draft_payload(self, batch: EtcBatch, invoices: list[EtcInvoice], attachment_ids: list[str]) -> dict[str, object]:
        lines = [
            f"{invoice.issue_date} {invoice.plate_number or ''} {invoice.total_amount:.2f}".strip()
            for invoice in invoices
        ]
        cause = f"{batch.oa_marker}\n\n" + "\n".join(lines)
        data = {
            self._form_mapping.application_date: datetime.now(UTC).date().isoformat(),
            self._form_mapping.project_name: "云南溯源科技",
            self._form_mapping.amount: f"{batch.total_amount:.2f}",
            self._form_mapping.cause: cause,
            self._form_mapping.attachments: attachment_ids,
        }
        return {
            "formId": 2,
            "isDraft": True,
            "data": data,
            "etc_batch_id": batch.etc_batch_id,
            "oa_marker": batch.oa_marker,
            "invoiceIds": list(batch.invoice_ids),
        }

    def _get_invoice(self, invoice_id: str) -> EtcInvoice:
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise EtcInvoiceNotFoundError(f"ETC invoice not found: {invoice_id}")
        return invoice

    def _next_invoice_id(self) -> str:
        self._invoice_counter += 1
        return f"etc_invoice_{self._invoice_counter:04d}"

    def _next_etc_batch_id(self) -> str:
        day = datetime.now(UTC).strftime("%Y%m%d")
        next_value = self._batch_day_counters.get(day, 0) + 1
        self._batch_day_counters[day] = next_value
        return f"etc_{day}_{next_value:03d}"


def parse_etc_xml(content: bytes) -> ParsedEtcXml:
    try:
        root = ET.fromstring(content)
    except ET.ParseError as exc:
        raise ValueError(f"XML 解析失败: {exc}") from exc
    values: dict[str, str] = {}
    for element in root.iter():
        local_name = _local_name(element.tag)
        normalized_name = _normalize_field_name(local_name)
        text = (element.text or "").strip()
        if not text:
            continue
        for field_name, aliases in FIELD_ALIASES.items():
            normalized_aliases = {_normalize_field_name(alias) for alias in aliases}
            if normalized_name in normalized_aliases and field_name not in values:
                values[field_name] = text
    invoice_number = _required_text(values, "invoice_number")
    issue_date = _normalize_date(_required_text(values, "issue_date"))
    return ParsedEtcXml(
        invoice_number=invoice_number,
        issue_date=issue_date,
        passage_start_date=_normalize_date(values["passage_start_date"]) if values.get("passage_start_date") else None,
        passage_end_date=_normalize_date(values["passage_end_date"]) if values.get("passage_end_date") else None,
        plate_number=values.get("plate_number"),
        vehicle_type=values.get("vehicle_type"),
        seller_name=values.get("seller_name"),
        seller_tax_no=values.get("seller_tax_no"),
        buyer_name=values.get("buyer_name"),
        buyer_tax_no=values.get("buyer_tax_no"),
        amount_without_tax=_required_decimal(values, "amount_without_tax"),
        tax_amount=_required_decimal(values, "tax_amount"),
        total_amount=_required_decimal(values, "total_amount"),
        tax_rate=values.get("tax_rate"),
    )


def _coerce_invoice_status(status: EtcInvoiceStatus | str) -> EtcInvoiceStatus:
    if isinstance(status, EtcInvoiceStatus):
        return status
    try:
        return EtcInvoiceStatus(str(status))
    except ValueError as exc:
        raise EtcInvoiceRequestError("status must be unsubmitted or submitted.") from exc


def _required_text(values: dict[str, str], field_name: str) -> str:
    value = values.get(field_name)
    if not value:
        raise ValueError(f"XML 缺少必填字段: {field_name}")
    return value.strip()


def _required_decimal(values: dict[str, str], field_name: str) -> Decimal:
    raw_value = _required_text(values, field_name)
    try:
        return Decimal(raw_value.replace(",", "")).quantize(Decimal("0.01"))
    except InvalidOperation as exc:
        raise ValueError(f"XML 金额字段无效: {field_name}") from exc


def _normalize_date(value: str) -> str:
    text = value.strip()
    if len(text) >= 10 and re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", text):
        return text[:10].replace("/", "-")
    if len(text) >= 8 and re.match(r"^\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.match(r"^\d{8}$", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _normalize_field_name(value: str) -> str:
    return re.sub(r"[\s_\-:：]+", "", value).lower()


def _safe_path_part(value: str) -> str:
    safe = SAFE_PATH_RE.sub("_", value.strip())
    return safe.strip("._ ") or "unknown"


def _extract_oa_error_message(payload: object) -> str:
    if isinstance(payload, str):
        try:
            decoded = json.loads(payload)
        except json.JSONDecodeError:
            return payload.strip()
        return _extract_oa_error_message(decoded)
    if not isinstance(payload, dict):
        return ""
    for key in ("msg", "message", "error"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return ""

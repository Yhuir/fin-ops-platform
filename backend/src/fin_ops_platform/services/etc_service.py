from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
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
from threading import RLock
from tempfile import TemporaryDirectory
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


class EtcBusinessBatchStatus(str, Enum):
    DRAFT = "draft"
    REVIEWING = "reviewing"
    READY_FOR_IMPORT = "ready_for_import"
    IMPORTING = "importing"
    IMPORTED = "imported"
    IMPORT_FAILED = "import_failed"
    IMPORT_PARTIAL_FAILED = "import_partial_failed"
    OA_DRAFT_CREATING = "oa_draft_creating"
    OA_DRAFT_FAILED = "oa_draft_failed"
    OA_SUBMISSION_DETECTING = "oa_submission_detecting"
    OA_SUBMITTED = "oa_submitted"
    CLOSED = "closed"
    NOT_SUBMITTED = "not_submitted"
    OA_DETECTION_TIMEOUT = "oa_detection_timeout"
    OA_DETECTION_CONFLICT = "oa_detection_conflict"
    OA_DETECTION_UNAVAILABLE = "oa_detection_unavailable"
    MANUALLY_MARKED_SUBMITTED = "manually_marked_submitted"
    MANUALLY_MARKED_NOT_SUBMITTED = "manually_marked_not_submitted"
    MIGRATION_CONFLICT = "migration_conflict"
    BUSINESS_BATCH_INVARIANT_BROKEN = "business_batch_invariant_broken"
    DELETED = "deleted"
    SUPERSEDED = "superseded"


ETC_BUSINESS_BATCH_ACTIVE_STATUSES = {
    EtcBusinessBatchStatus.DRAFT.value,
    EtcBusinessBatchStatus.REVIEWING.value,
    EtcBusinessBatchStatus.READY_FOR_IMPORT.value,
    EtcBusinessBatchStatus.IMPORTING.value,
    EtcBusinessBatchStatus.IMPORTED.value,
    EtcBusinessBatchStatus.IMPORT_FAILED.value,
    EtcBusinessBatchStatus.IMPORT_PARTIAL_FAILED.value,
    EtcBusinessBatchStatus.OA_DRAFT_CREATING.value,
    EtcBusinessBatchStatus.OA_DRAFT_FAILED.value,
    EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value,
    EtcBusinessBatchStatus.OA_DETECTION_TIMEOUT.value,
    EtcBusinessBatchStatus.OA_DETECTION_CONFLICT.value,
    EtcBusinessBatchStatus.OA_DETECTION_UNAVAILABLE.value,
    EtcBusinessBatchStatus.NOT_SUBMITTED.value,
    EtcBusinessBatchStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
    EtcBusinessBatchStatus.MIGRATION_CONFLICT.value,
    EtcBusinessBatchStatus.BUSINESS_BATCH_INVARIANT_BROKEN.value,
}

ETC_BUSINESS_BATCH_IMPORT_ALLOWED_STATUSES = {
    EtcBusinessBatchStatus.DRAFT.value,
    EtcBusinessBatchStatus.REVIEWING.value,
    EtcBusinessBatchStatus.READY_FOR_IMPORT.value,
    EtcBusinessBatchStatus.IMPORTED.value,
    EtcBusinessBatchStatus.IMPORT_FAILED.value,
    EtcBusinessBatchStatus.IMPORT_PARTIAL_FAILED.value,
    EtcBusinessBatchStatus.OA_DRAFT_FAILED.value,
    EtcBusinessBatchStatus.NOT_SUBMITTED.value,
    EtcBusinessBatchStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
}

ETC_BUSINESS_BATCH_DRAFT_REVOCABLE_STATUSES = {
    EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value,
    EtcBusinessBatchStatus.OA_DETECTION_TIMEOUT.value,
    EtcBusinessBatchStatus.OA_DETECTION_CONFLICT.value,
    EtcBusinessBatchStatus.OA_DETECTION_UNAVAILABLE.value,
}


class EtcServiceError(RuntimeError):
    pass


class EtcImportPreviewStaleError(EtcServiceError):
    pass


class EtcInvoiceRequestError(EtcServiceError):
    pass


class EtcInvoiceNotFoundError(EtcInvoiceRequestError):
    pass


class EtcBatchNotFoundError(EtcServiceError):
    pass


class EtcBatchDeleteError(EtcServiceError):
    pass


class EtcBusinessBatchNotFoundError(EtcServiceError):
    pass


class EtcBusinessBatchActiveExistsError(EtcServiceError):
    pass


class EtcBusinessBatchVersionConflictError(EtcServiceError):
    def __init__(self, business_batch_id: str, expected_version: int, actual_version: int) -> None:
        self.business_batch_id = business_batch_id
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__("ETC business batch version conflict.")


class EtcBusinessBatchInvalidTransitionError(EtcServiceError):
    def __init__(self, message: str, *, code: str = "invalid_status_transition") -> None:
        self.code = code
        super().__init__(message)


class EtcDraftRequestError(EtcServiceError):
    pass


class EtcOAClientError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class EtcUploadedAttachment:
    name: str
    url: str
    size: int = 0


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

    def __post_init__(self) -> None:
        if self.base_url is None:
            return
        trimmed = self.base_url.strip().rstrip("/")
        if trimmed.endswith("/oa") and not trimmed.endswith("/oa-api"):
            trimmed = f"{trimmed}-api"
        object.__setattr__(self, "base_url", trimmed)

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
    import_batch_id: str | None = None
    import_session_id: str | None = None
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
    source_type: str = "normal_oa_draft"
    linked_oa_row_id: str | None = None
    linked_oa_case_id: str | None = None
    amount_delta: Decimal | None = None
    note: str = ""
    issue_start_date: str | None = None
    issue_end_date: str | None = None
    passage_start_date: str | None = None
    passage_end_date: str | None = None
    plate_summary: list[dict[str, object]] = field(default_factory=list)
    oa_form_id: int = 2
    oa_draft_id: str | None = None
    oa_draft_url: str | None = None
    oa_marker: str = ""
    status: str = EtcBatchStatus.DRAFT_CREATING.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    confirmed_at: datetime | None = None
    error_message: str | None = None
    reconciliation_task_id: str | None = None
    statement_period_start: str | None = None
    statement_period_end: str | None = None
    oa_total_amount: Decimal | None = None
    etc_invoice_amount: Decimal | None = None
    supplement_amount: Decimal = Decimal("0.00")
    etc_invoice_count: int | None = None
    supplement_count: int = 0
    supplement_items: list[dict[str, object]] = field(default_factory=list)
    display_count_text: str | None = None


@dataclass(slots=True)
class EtcImportBatch:
    id: str
    source_names: list[str]
    invoice_ids: list[str] = field(default_factory=list)
    invoice_count: int = 0
    total_amount: Decimal = Decimal("0.00")
    issue_date_start: str | None = None
    issue_date_end: str | None = None
    passage_date_start: str | None = None
    passage_date_end: str | None = None
    source_session_id: str | None = None
    submission_batch_id: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class EtcBusinessBatch:
    business_batch_id: str
    task_id: str
    status: str = EtcBusinessBatchStatus.DRAFT.value
    version: int = 1
    idempotency_key: str | None = None
    owner_user_id: str | None = None
    owner_org_id: str | None = None
    task_active_key: str | None = None
    import_batch_ids: list[str] = field(default_factory=list)
    submission_batch_id: str | None = None
    external_etc_batch_id: str | None = None
    oa_draft_id: str | None = None
    oa_draft_url: str | None = None
    oa_row_id: str | None = None
    oa_process_status: str = "unknown"
    oa_detection_status: str = "not_started"
    oa_detection_started_at: datetime | None = None
    oa_detection_next_run_at: datetime | None = None
    oa_detection_deadline_at: datetime | None = None
    oa_detection_final_retry_until: datetime | None = None
    oa_detection_attempts: int = 0
    oa_detection_error: str | None = None
    oa_detection_reason: str | None = None
    invoice_ids: list[str] = field(default_factory=list)
    import_attempts: list[dict[str, object]] = field(default_factory=list)
    audit_events: list[dict[str, object]] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def is_active(self) -> bool:
        return str(self.status) in ETC_BUSINESS_BATCH_ACTIVE_STATUSES


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
class EtcImportPreviewAudit:
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

    def finalize(self) -> "EtcImportPreviewAudit":
        self.duplicate_count = self.duplicate_in_file_count + self.duplicate_across_files_count
        self.confirmable_count = self.importable_count + self.update_count + self.merge_count
        self.skipped_count = (
            self.duplicate_count
            + self.existing_duplicate_count
            + self.suspected_duplicate_count
            + self.error_count
        )
        return self

    def to_payload(self) -> dict[str, int]:
        self.finalize()
        return {
            "original_count": self.original_count,
            "unique_count": self.unique_count,
            "duplicate_count": self.duplicate_count,
            "duplicate_in_file_count": self.duplicate_in_file_count,
            "duplicate_across_files_count": self.duplicate_across_files_count,
            "existing_duplicate_count": self.existing_duplicate_count,
            "importable_count": self.importable_count,
            "update_count": self.update_count,
            "merge_count": self.merge_count,
            "suspected_duplicate_count": self.suspected_duplicate_count,
            "error_count": self.error_count,
            "confirmable_count": self.confirmable_count,
            "skipped_count": self.skipped_count,
        }

    def stale_key_payload(self) -> dict[str, int]:
        payload = self.to_payload()
        return {key: payload[key] for key in ETC_IMPORT_STALE_AUDIT_KEYS}


ETC_IMPORT_STALE_AUDIT_KEYS = (
    "importable_count",
    "update_count",
    "merge_count",
    "existing_duplicate_count",
    "duplicate_count",
    "suspected_duplicate_count",
    "error_count",
)


@dataclass(slots=True)
class EtcImportSession:
    session_id: str
    uploads: list[UploadedEtcZipFile]
    created_at: datetime
    preview_result: EtcImportResult
    preview_audit: EtcImportPreviewAudit
    preview_files: list[dict[str, object]] = field(default_factory=list)
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
    applicant: str = "userName"
    application_date: str = "applicationDate"
    category: str = "category"
    payment_proof: str = "paymentProof"
    project_name: str = "projectName"
    amount: str = "amount"
    cause: str = "cause"
    attachments: str = "field101"
    category_value: str = "s5"
    payment_proof_value: str = ""
    project_name_value: str = "6486ca70cd6cae5d4e2b0b48"

    @classmethod
    def from_environment(cls) -> EtcOAFormFieldMapping:
        return cls(
            applicant=os.getenv("FIN_OPS_ETC_OA_FIELD_APPLICANT", "userName"),
            application_date=os.getenv("FIN_OPS_ETC_OA_FIELD_APPLICATION_DATE", "applicationDate"),
            category=os.getenv("FIN_OPS_ETC_OA_FIELD_CATEGORY", "category"),
            payment_proof=os.getenv("FIN_OPS_ETC_OA_FIELD_PAYMENT_PROOF", "paymentProof"),
            project_name=os.getenv("FIN_OPS_ETC_OA_FIELD_PROJECT_NAME", "projectName"),
            amount=os.getenv("FIN_OPS_ETC_OA_FIELD_AMOUNT", "amount"),
            cause=os.getenv("FIN_OPS_ETC_OA_FIELD_CAUSE", "cause"),
            attachments=os.getenv("FIN_OPS_ETC_OA_FIELD_ATTACHMENTS", "field101"),
            category_value=os.getenv("FIN_OPS_ETC_OA_CATEGORY_VALUE", "s5").strip() or "s5",
            payment_proof_value=os.getenv("FIN_OPS_ETC_OA_PAYMENT_PROOF_VALUE", "").strip(),
            project_name_value=(
                os.getenv("FIN_OPS_ETC_OA_PROJECT_VALUE", "6486ca70cd6cae5d4e2b0b48").strip()
                or "6486ca70cd6cae5d4e2b0b48"
            ),
        )


@dataclass(slots=True)
class ParsedEtcXml:
    invoice_number: str
    issue_date: str
    issue_datetime: str | None
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
        self._import_batch_counter = 0
        self._business_batch_counter = 0
        self._batch_day_counters: dict[str, int] = {}
        self._invoices: dict[str, EtcInvoice] = {}
        self._invoice_numbers: dict[str, str] = {}
        self._batches: dict[str, EtcBatch] = {}
        self._import_batches: dict[str, EtcImportBatch] = {}
        self._business_batches: dict[str, EtcBusinessBatch] = {}
        self._import_sessions: dict[str, EtcImportSession] = {}
        self._canonical_invoice_key_exists: Callable[[str], bool] | None = None
        self._business_batch_lock = RLock()
        self._hydrate(self._load_snapshot())
        if self._migrate_local_invoice_files_to_state_store():
            self._persist()

    def set_canonical_invoice_key_exists(self, callback: Callable[[str], bool] | None) -> None:
        self._canonical_invoice_key_exists = callback

    def create_business_batch(
        self,
        *,
        task_id: str,
        owner_user_id: str | None = None,
        owner_org_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> EtcBusinessBatch:
        normalized_task_id = str(task_id or "").strip()
        normalized_idempotency_key = str(idempotency_key or "").strip() or None
        if not normalized_task_id:
            raise EtcBusinessBatchInvalidTransitionError("task_id is required.", code="invalid_business_batch_request")
        with self._business_batch_lock:
            existing = self._active_business_batch_for_task(normalized_task_id)
            if existing is not None:
                if normalized_idempotency_key and existing.idempotency_key == normalized_idempotency_key:
                    return self._copy_business_batch(existing)
                raise EtcBusinessBatchActiveExistsError(f"Active ETC business batch already exists for task {normalized_task_id}.")
            self._business_batch_counter += 1
            now = datetime.now(UTC)
            batch = EtcBusinessBatch(
                business_batch_id=f"etc_business_batch_{self._business_batch_counter:04d}",
                task_id=normalized_task_id,
                idempotency_key=normalized_idempotency_key,
                owner_user_id=str(owner_user_id or "").strip() or None,
                owner_org_id=str(owner_org_id or "").strip() or None,
                task_active_key=f"{normalized_task_id}:active",
                created_at=now,
                updated_at=now,
            )
            self._append_business_batch_audit(batch, "business_batch_created", before_status=None, after_status=batch.status)
            self._business_batches[batch.business_batch_id] = batch
            self._persist()
            return self._copy_business_batch(batch)

    def list_business_batches(
        self,
        *,
        task_id: str | None = None,
        status: str | None = None,
    ) -> list[EtcBusinessBatch]:
        normalized_task_id = str(task_id or "").strip()
        normalized_status = str(status or "").strip()
        batches = [
            batch
            for batch in self._business_batches.values()
            if (not normalized_task_id or batch.task_id == normalized_task_id)
            and (not normalized_status or batch.status == normalized_status)
            and batch.status != EtcBusinessBatchStatus.DELETED.value
        ]
        return [self._copy_business_batch(batch) for batch in sorted(batches, key=lambda item: item.created_at, reverse=True)]

    def get_business_batch(self, business_batch_id: str) -> EtcBusinessBatch:
        batch = self._get_business_batch_mutable(business_batch_id)
        if batch.status == EtcBusinessBatchStatus.DELETED.value:
            raise EtcBusinessBatchNotFoundError(f"ETC business batch not found: {business_batch_id}")
        return self._copy_business_batch(batch)

    def preview_business_batch_import_zips(
        self,
        business_batch_id: str,
        uploads: list[UploadedEtcZipFile],
        *,
        expected_version: int | None = None,
    ) -> dict[str, object]:
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            self._assert_business_batch_version(batch, expected_version)
            self._assert_business_batch_allows_import(batch)
            payload = self.preview_import_zips(uploads)
            payload["businessBatch"] = self.business_batch_payload(batch)
            return payload

    def confirm_business_batch_import(
        self,
        business_batch_id: str,
        session_id: str,
        *,
        expected_version: int | None = None,
        idempotency_key: str | None = None,
        progress_callback: Callable[[EtcImportResult], None] | None = None,
    ) -> tuple[EtcBusinessBatch, EtcImportResult]:
        normalized_session_id = str(session_id or "").strip()
        normalized_idempotency_key = str(idempotency_key or "").strip() or None
        if not normalized_session_id:
            raise EtcServiceError("ETC import session not found.")
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            if normalized_idempotency_key:
                for attempt in list(batch.import_attempts or []):
                    if str(attempt.get("idempotency_key") or "") != normalized_idempotency_key:
                        continue
                    session = self._import_sessions.get(normalized_session_id)
                    if session is not None and session.confirmed_result is not None:
                        return self._copy_business_batch(batch), session.confirmed_result
                    summary = attempt.get("summary") if isinstance(attempt.get("summary"), dict) else {}
                    replayed = EtcImportResult(
                        imported=int(summary.get("imported", 0) or 0),
                        duplicates_skipped=int(summary.get("duplicatesSkipped", 0) or 0),
                        attachments_completed=int(summary.get("attachmentsCompleted", 0) or 0),
                        failed=int(summary.get("failed", 0) or 0),
                    )
                    return self._copy_business_batch(batch), replayed
            self._assert_business_batch_version(batch, expected_version)
            self._assert_business_batch_allows_import(batch)
            before_status = batch.status
            result = self.confirm_import_session_with_progress(
                normalized_session_id,
                progress_callback=progress_callback,
            ) if progress_callback is not None else self.confirm_import_session(normalized_session_id)
            linked_import_batches = [
                import_batch
                for import_batch in self._import_batches.values()
                if str(import_batch.source_session_id or "").strip() == normalized_session_id
            ]
            now = datetime.now(UTC)
            for import_batch in linked_import_batches:
                if import_batch.id not in batch.import_batch_ids:
                    batch.import_batch_ids.append(import_batch.id)
                for invoice_id in list(import_batch.invoice_ids or []):
                    if invoice_id not in batch.invoice_ids:
                        batch.invoice_ids.append(invoice_id)
            for invoice_id in list(batch.invoice_ids):
                invoice = self._invoices.get(invoice_id)
                if invoice is None:
                    continue
                if invoice.status == EtcInvoiceStatus.SUBMITTED:
                    raise EtcBusinessBatchInvalidTransitionError(
                        f"ETC invoice {invoice.invoice_number} is already submitted.",
                        code="invoice_already_submitted",
                    )
                invoice.current_batch_id = batch.business_batch_id
                invoice.last_batch_id = batch.business_batch_id
                invoice.updated_at = now
            if result.failed and (result.imported or result.attachments_completed):
                after_status = EtcBusinessBatchStatus.IMPORT_PARTIAL_FAILED.value
            elif result.failed:
                after_status = EtcBusinessBatchStatus.IMPORT_FAILED.value
            else:
                after_status = EtcBusinessBatchStatus.IMPORTED.value
            batch.status = after_status
            self._refresh_business_batch_active_key(batch)
            batch.import_attempts.append(
                {
                    "session_id": normalized_session_id,
                    "idempotency_key": normalized_idempotency_key,
                    "import_batch_ids": [item.id for item in linked_import_batches],
                    **result.summary_payload(),
                    "summary": result.summary_payload(),
                    "created_at": now,
                }
            )
            self._bump_business_batch_version(
                batch,
                event_type="business_batch_import_confirmed",
                before_status=before_status,
                after_status=batch.status,
            )
            self._persist()
            return self._copy_business_batch(batch), result

    def create_business_batch_oa_draft(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None = None,
        oa_client: EtcOAClient | None = None,
        reconciliation_task: object | None = None,
    ) -> EtcBusinessBatch:
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            if batch.status == EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value and batch.submission_batch_id:
                return self._copy_business_batch(batch)
            self._assert_business_batch_version(batch, expected_version)
            if batch.status not in {
                EtcBusinessBatchStatus.IMPORTED.value,
                EtcBusinessBatchStatus.NOT_SUBMITTED.value,
                EtcBusinessBatchStatus.MANUALLY_MARKED_NOT_SUBMITTED.value,
                EtcBusinessBatchStatus.OA_DRAFT_FAILED.value,
            }:
                raise EtcBusinessBatchInvalidTransitionError("current status does not allow creating an OA draft.")
            invoice_ids = list(batch.invoice_ids)
            if not invoice_ids:
                raise EtcBusinessBatchInvalidTransitionError("business batch has no ETC invoices.", code="empty_business_batch")
            before_status = batch.status
            batch.status = EtcBusinessBatchStatus.OA_DRAFT_CREATING.value
            self._refresh_business_batch_active_key(batch)
            self._persist()
            try:
                draft = self.create_oa_draft(
                    invoice_ids,
                    oa_client=oa_client,
                    reconciliation_task=reconciliation_task,
                    business_batch_id=batch.business_batch_id,
                )
            except EtcDraftRequestError as exc:
                batch.status = EtcBusinessBatchStatus.OA_DRAFT_FAILED.value
                self._bump_business_batch_version(
                    batch,
                    event_type="oa_draft_failed",
                    before_status=before_status,
                    after_status=batch.status,
                    reason=str(exc),
                )
                self._persist()
                raise
            now = datetime.now(UTC)
            batch.submission_batch_id = draft.batch_id
            batch.external_etc_batch_id = draft.etc_batch_id
            batch.oa_draft_id = draft.oa_draft_id
            batch.oa_draft_url = draft.oa_draft_url
            batch.status = EtcBusinessBatchStatus.OA_SUBMISSION_DETECTING.value
            batch.oa_detection_status = "pending"
            batch.oa_detection_started_at = now
            batch.oa_detection_next_run_at = now
            batch.oa_detection_deadline_at = now + timedelta(minutes=30)
            batch.oa_detection_final_retry_until = now + timedelta(hours=24)
            for import_batch_id in list(batch.import_batch_ids):
                import_batch = self._import_batches.get(import_batch_id)
                if import_batch is not None:
                    import_batch.submission_batch_id = draft.batch_id
                    import_batch.updated_at = now
            self._bump_business_batch_version(
                batch,
                event_type="oa_draft_created",
                before_status=before_status,
                after_status=batch.status,
            )
            self._persist()
            return self._copy_business_batch(batch)

    def revoke_business_batch_oa_draft(
        self,
        business_batch_id: str,
        *,
        reason: str,
        expected_version: int | None = None,
    ) -> EtcBusinessBatch:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise EtcBusinessBatchInvalidTransitionError("reason is required.", code="reason_required")
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            if batch.status == EtcBusinessBatchStatus.NOT_SUBMITTED.value and batch.submission_batch_id is None:
                return self._copy_business_batch(batch)
            self._assert_business_batch_version(batch, expected_version)
            if batch.status not in ETC_BUSINESS_BATCH_DRAFT_REVOCABLE_STATUSES:
                raise EtcBusinessBatchInvalidTransitionError("current status does not allow revoking the OA draft.")
            before_status = batch.status
            old_submission_batch_id = batch.submission_batch_id
            now = datetime.now(UTC)
            if old_submission_batch_id and (submission_batch := self._batches.get(old_submission_batch_id)) is not None:
                submission_batch.status = EtcBatchStatus.NOT_SUBMITTED.value
            for invoice_id in list(batch.invoice_ids):
                invoice = self._invoices.get(invoice_id)
                if invoice is None:
                    continue
                invoice.status = EtcInvoiceStatus.UNSUBMITTED
                if invoice.current_batch_id in {old_submission_batch_id, batch.business_batch_id}:
                    invoice.current_batch_id = None
                invoice.last_batch_id = old_submission_batch_id or batch.business_batch_id
                invoice.updated_at = now
            for import_batch_id in list(batch.import_batch_ids):
                import_batch = self._import_batches.get(import_batch_id)
                if import_batch is not None and import_batch.submission_batch_id == old_submission_batch_id:
                    import_batch.submission_batch_id = None
                    import_batch.updated_at = now
            batch.submission_batch_id = None
            batch.external_etc_batch_id = None
            batch.oa_draft_id = None
            batch.oa_draft_url = None
            batch.oa_detection_status = "revoked"
            batch.oa_detection_reason = "user_revoked"
            batch.status = EtcBusinessBatchStatus.NOT_SUBMITTED.value
            self._bump_business_batch_version(
                batch,
                event_type="oa_draft_revoked",
                before_status=before_status,
                after_status=batch.status,
                reason=normalized_reason,
                submission_batch_id=old_submission_batch_id,
            )
            self._persist()
            return self._copy_business_batch(batch)

    def refresh_business_batch_oa_status(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None = None,
    ) -> EtcBusinessBatch:
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            self._assert_business_batch_version(batch, expected_version)
            if batch.status not in ETC_BUSINESS_BATCH_DRAFT_REVOCABLE_STATUSES:
                raise EtcBusinessBatchInvalidTransitionError("current status does not allow OA status refresh.")
            before_status = batch.status
            batch.oa_detection_attempts += 1
            batch.oa_detection_status = "stub_unavailable"
            batch.oa_detection_reason = "oa_detector_not_configured"
            self._bump_business_batch_version(
                batch,
                event_type="oa_status_refresh_requested",
                before_status=before_status,
                after_status=batch.status,
                reason=batch.oa_detection_reason,
            )
            self._persist()
            return self._copy_business_batch(batch)

    def apply_business_batch_oa_detection_result(
        self,
        business_batch_id: str,
        *,
        detection_status: str,
        reason: str,
        expected_version: int | None = None,
        oa_row_id: str | None = None,
        process_status: str | None = None,
        error: str | None = None,
        candidates: list[dict[str, object]] | None = None,
    ) -> EtcBusinessBatch:
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            self._assert_business_batch_version(batch, expected_version)
            if batch.status not in ETC_BUSINESS_BATCH_DRAFT_REVOCABLE_STATUSES:
                raise EtcBusinessBatchInvalidTransitionError("current status does not allow OA status refresh.")
            before_status = batch.status
            normalized_status = str(detection_status or "").strip()
            normalized_reason = str(reason or "").strip() or normalized_status
            now = datetime.now(UTC)
            batch.oa_detection_attempts += 1
            batch.oa_detection_reason = normalized_reason
            batch.oa_detection_error = str(error or "").strip() or None
            batch.oa_detection_next_run_at = now
            if normalized_status == "detected":
                batch.status = EtcBusinessBatchStatus.OA_SUBMITTED.value
                batch.oa_detection_status = "detected"
                batch.oa_row_id = str(oa_row_id or "").strip() or None
                batch.oa_process_status = str(process_status or "in_progress").strip() or "in_progress"
                if batch.submission_batch_id and (submission_batch := self._batches.get(batch.submission_batch_id)) is not None:
                    submission_batch.status = EtcBatchStatus.SUBMITTED_CONFIRMED.value
                    submission_batch.confirmed_at = submission_batch.confirmed_at or now
                    submission_batch.linked_oa_row_id = batch.oa_row_id or submission_batch.linked_oa_row_id
                for invoice_id in list(batch.invoice_ids):
                    invoice = self._invoices.get(invoice_id)
                    if invoice is None:
                        continue
                    invoice.status = EtcInvoiceStatus.SUBMITTED
                    invoice.current_batch_id = batch.submission_batch_id or batch.business_batch_id
                    invoice.last_batch_id = invoice.current_batch_id
                    invoice.updated_at = now
            elif normalized_status == "conflict":
                batch.status = EtcBusinessBatchStatus.OA_DETECTION_CONFLICT.value
                batch.oa_detection_status = "conflict"
            elif normalized_status == "unavailable":
                batch.status = EtcBusinessBatchStatus.OA_DETECTION_UNAVAILABLE.value
                batch.oa_detection_status = "unavailable"
            elif normalized_status == "timeout":
                batch.status = EtcBusinessBatchStatus.OA_DETECTION_TIMEOUT.value
                batch.oa_detection_status = "timeout"
            else:
                batch.oa_detection_status = "missing"
            self._bump_business_batch_version(
                batch,
                event_type="oa_submission_detection_refreshed",
                before_status=before_status,
                after_status=batch.status,
                reason=normalized_reason,
                oa_row_id=batch.oa_row_id,
                candidates=list(candidates or [])[:10],
            )
            self._persist()
            return self._copy_business_batch(batch)

    def manual_business_batch_oa_status(
        self,
        business_batch_id: str,
        *,
        decision: str,
        reason: str,
        expected_version: int | None = None,
        candidate_oa_row_id: str | None = None,
    ) -> EtcBusinessBatch:
        normalized_reason = str(reason or "").strip()
        if not normalized_reason:
            raise EtcBusinessBatchInvalidTransitionError("reason is required.", code="reason_required")
        normalized_decision = str(decision or "").strip().lower()
        if normalized_decision not in {"submitted", "not_submitted"}:
            raise EtcBusinessBatchInvalidTransitionError("decision must be submitted or not_submitted.", code="invalid_manual_decision")
        with self._business_batch_lock:
            batch = self._get_business_batch_mutable(business_batch_id)
            self._assert_business_batch_version(batch, expected_version)
            if normalized_decision == "submitted":
                before_status = batch.status
                if before_status not in ETC_BUSINESS_BATCH_DRAFT_REVOCABLE_STATUSES:
                    raise EtcBusinessBatchInvalidTransitionError(
                        "manual submitted decision is allowed only while an OA draft is under detection or exception handling.",
                        code="invalid_manual_status",
                    )
                now = datetime.now(UTC)
                if batch.submission_batch_id and (submission_batch := self._batches.get(batch.submission_batch_id)) is not None:
                    submission_batch.status = EtcBatchStatus.SUBMITTED_CONFIRMED.value
                    submission_batch.confirmed_at = submission_batch.confirmed_at or now
                for invoice_id in list(batch.invoice_ids):
                    invoice = self._invoices.get(invoice_id)
                    if invoice is None:
                        continue
                    invoice.status = EtcInvoiceStatus.SUBMITTED
                    invoice.current_batch_id = batch.submission_batch_id or batch.business_batch_id
                    invoice.last_batch_id = invoice.current_batch_id
                    invoice.updated_at = now
                batch.status = EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value
                batch.oa_row_id = str(candidate_oa_row_id or "").strip() or None
                batch.oa_process_status = "manual_without_oa_row" if batch.oa_row_id is None else "in_progress"
                self._refresh_business_batch_active_key(batch)
                self._bump_business_batch_version(
                    batch,
                    event_type="manual_oa_status_submitted",
                    before_status=before_status,
                    after_status=batch.status,
                    reason=normalized_reason,
                    oa_row_id=batch.oa_row_id,
                )
                self._persist()
                return self._copy_business_batch(batch)
            return self.revoke_business_batch_oa_draft(
                business_batch_id,
                reason=normalized_reason,
                expected_version=expected_version,
            )

    def delete_business_batch(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None = None,
        reason: str | None = None,
    ) -> dict[str, object]:
        normalized_id = str(business_batch_id or "").strip()
        with self._business_batch_lock:
            try:
                batch = self._get_business_batch_mutable(normalized_id)
            except EtcBusinessBatchNotFoundError:
                if normalized_id.startswith("etc_business_batch_"):
                    return {"deleted": True, "businessBatchId": normalized_id, "kind": "business_batch"}
                raise
            if batch.status == EtcBusinessBatchStatus.DELETED.value:
                return {"deleted": True, "businessBatchId": normalized_id, "kind": "business_batch"}
            self._assert_business_batch_version(batch, expected_version)
            if batch.status in {
                EtcBusinessBatchStatus.OA_SUBMITTED.value,
                EtcBusinessBatchStatus.MANUALLY_MARKED_SUBMITTED.value,
                EtcBusinessBatchStatus.CLOSED.value,
            }:
                raise EtcBusinessBatchInvalidTransitionError("submitted or closed ETC business batch cannot be deleted.")
            if batch.submission_batch_id and batch.submission_batch_id in self._batches:
                self._delete_submission_batch(self._batches[batch.submission_batch_id])
            for invoice_id in list(batch.invoice_ids):
                invoice = self._invoices.get(invoice_id)
                if invoice is None:
                    continue
                if invoice.status == EtcInvoiceStatus.SUBMITTED:
                    raise EtcBusinessBatchInvalidTransitionError("submitted ETC invoices cannot be deleted.")
                if invoice.current_batch_id in {batch.business_batch_id, batch.submission_batch_id}:
                    invoice.current_batch_id = None
            for import_batch_id in list(batch.import_batch_ids):
                import_batch = self._import_batches.get(import_batch_id)
                if import_batch is not None:
                    self._delete_import_batch(import_batch)
            before_status = batch.status
            batch.status = EtcBusinessBatchStatus.DELETED.value
            batch.task_active_key = None
            self._append_business_batch_audit(
                batch,
                "business_batch_deleted",
                before_status=before_status,
                after_status=EtcBusinessBatchStatus.DELETED.value,
                reason=str(reason or "").strip() or None,
            )
            self._persist()
            return {"deleted": True, "businessBatchId": normalized_id, "kind": "business_batch"}

    def business_batch_payload(self, batch_or_id: EtcBusinessBatch | str) -> dict[str, object]:
        batch = self._get_business_batch_mutable(batch_or_id) if isinstance(batch_or_id, str) else batch_or_id
        invoices = [self._invoices[invoice_id] for invoice_id in list(batch.invoice_ids) if invoice_id in self._invoices]
        amount = sum((invoice.total_amount for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        return {
            "businessBatchId": batch.business_batch_id,
            "taskId": batch.task_id,
            "status": batch.status,
            "version": batch.version,
            "idempotencyKey": batch.idempotency_key,
            "isActive": batch.is_active,
            "taskActiveKey": batch.task_active_key,
            "ownerUserId": batch.owner_user_id,
            "ownerOrgId": batch.owner_org_id,
            "importBatchIds": list(batch.import_batch_ids),
            "submissionBatchId": batch.submission_batch_id,
            "externalEtcBatchId": batch.external_etc_batch_id,
            "oaDraftId": batch.oa_draft_id,
            "oaDraftUrl": batch.oa_draft_url,
            "oaRowId": batch.oa_row_id,
            "oaProcessStatus": batch.oa_process_status,
            "oaDetectionStatus": batch.oa_detection_status,
            "oaDetectionAttempts": batch.oa_detection_attempts,
            "oaDetectionReason": batch.oa_detection_reason,
            "invoiceIds": list(batch.invoice_ids),
            "invoiceSummary": {"count": len(invoices), "amount": amount},
            "importAttempts": list(batch.import_attempts),
            "auditEvents": list(batch.audit_events),
            "createdAt": batch.created_at,
            "updatedAt": batch.updated_at,
        }

    def import_zips(self, uploads: list[UploadedEtcZipFile]) -> EtcImportResult:
        return self._process_import_zips(uploads, persist=True)

    def preview_import_zips(self, uploads: list[UploadedEtcZipFile]) -> dict[str, object]:
        result, audit, file_audits = self.inspect_import_zips(uploads)
        session_id = uuid4().hex
        self._import_sessions[session_id] = EtcImportSession(
            session_id=session_id,
            uploads=[UploadedEtcZipFile(upload.file_name, bytes(upload.content)) for upload in uploads],
            created_at=datetime.now(UTC),
            preview_result=result,
            preview_audit=audit,
            preview_files=file_audits,
        )
        return self._import_session_payload(session_id, result, audit=audit, files=file_audits)

    def inspect_import_zips(
        self,
        uploads: list[UploadedEtcZipFile],
    ) -> tuple[EtcImportResult, EtcImportPreviewAudit, list[dict[str, object]]]:
        result = self._process_import_zips(uploads, persist=False)
        audit, file_audits = self._calculate_import_preview_audit(uploads)
        return result, audit, file_audits

    def confirm_import_session(self, session_id: str) -> EtcImportResult:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        if session.confirmed_result is not None:
            return session.confirmed_result
        self._assert_import_preview_fresh(session)
        result = self._process_import_zips(session.uploads, persist=True, import_session_id=session.session_id)
        session.confirmed_result = result
        session.confirmed_at = datetime.now(UTC)
        return result

    def get_import_session_item_total(self, session_id: str) -> int:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        return len(session.preview_result.items)

    def validate_import_session_preview_fresh(self, session_id: str) -> None:
        session = self._import_sessions.get(session_id)
        if session is None:
            raise EtcServiceError("ETC import session not found.")
        if session.confirmed_result is not None:
            return
        self._assert_import_preview_fresh(session)

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
        self._assert_import_preview_fresh(session)
        result = self._process_import_zips(
            session.uploads,
            persist=True,
            import_session_id=session.session_id,
            progress_callback=progress_callback,
        )
        session.confirmed_result = result
        session.confirmed_at = datetime.now(UTC)
        return result

    def import_result_payload(self, result: EtcImportResult) -> dict[str, object]:
        return {
            **result.summary_payload(),
            "summary": result.summary_payload(),
            "items": [item.to_payload() for item in result.items],
        }

    def _import_session_payload(
        self,
        session_id: str,
        result: EtcImportResult,
        *,
        audit: EtcImportPreviewAudit | None = None,
        files: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        payload = self.import_result_payload(result)
        response = {
            "sessionId": session_id,
            **payload,
        }
        if audit is not None:
            response["audit"] = audit.to_payload()
        if files is not None:
            response["files"] = files
        return response

    def _assert_import_preview_fresh(self, session: EtcImportSession) -> None:
        current_audit, _files = self._calculate_import_preview_audit(session.uploads)
        if current_audit.stale_key_payload() != session.preview_audit.stale_key_payload():
            raise EtcImportPreviewStaleError("ETC import preview is stale; refresh preview before confirming.")

    def _calculate_import_preview_audit(
        self,
        uploads: list[UploadedEtcZipFile],
    ) -> tuple[EtcImportPreviewAudit, list[dict[str, object]]]:
        session_audit = EtcImportPreviewAudit()
        file_payloads: list[dict[str, object]] = []
        seen_invoice_numbers: dict[str, str] = {}
        preview_state: dict[str, tuple[bool, bool]] = {
            invoice.invoice_number: (
                self._stored_invoice_file_exists(invoice.xml_file_path),
                self._stored_invoice_file_exists(invoice.pdf_file_path),
            )
            for invoice in self._invoices.values()
        }

        for file_index, upload in enumerate(uploads, start=1):
            file_id = f"file_{file_index:04d}"
            file_audit = EtcImportPreviewAudit()
            try:
                entries = self._extract_archive_entries(upload.file_name, upload.content)
            except BadZipFile:
                self._record_audit_error(session_audit, file_audit)
                file_payloads.append(self._etc_import_file_audit_payload(file_id, upload.file_name, file_audit))
                continue

            xml_entries = [entry for entry in entries if self._is_xml_entry(entry.path)]
            if not xml_entries:
                self._record_audit_error(session_audit, file_audit)
                file_payloads.append(self._etc_import_file_audit_payload(file_id, upload.file_name, file_audit))
                continue

            pdf_entries = [entry for entry in entries if self._is_pdf_entry(entry.path)]
            for xml_entry in xml_entries:
                session_audit.original_count += 1
                file_audit.original_count += 1
                try:
                    parsed = parse_etc_xml(xml_entry.content)
                except Exception:
                    session_audit.error_count += 1
                    file_audit.error_count += 1
                    continue

                invoice_number = parsed.invoice_number.strip()
                first_file_id = seen_invoice_numbers.get(invoice_number)
                if first_file_id is not None:
                    if first_file_id == file_id:
                        session_audit.duplicate_in_file_count += 1
                        file_audit.duplicate_in_file_count += 1
                    else:
                        session_audit.duplicate_across_files_count += 1
                        file_audit.duplicate_across_files_count += 1
                    continue

                seen_invoice_numbers[invoice_number] = file_id
                session_audit.unique_count += 1
                file_audit.unique_count += 1
                pdf_entry = self._match_pdf_entry(invoice_number, xml_entry.path, pdf_entries)
                status = self._preview_invoice_import_status(parsed, pdf_entry, preview_state)
                self._record_unique_audit_classification(session_audit, status, parsed)
                self._record_unique_audit_classification(file_audit, status, parsed)

            file_payloads.append(self._etc_import_file_audit_payload(file_id, upload.file_name, file_audit))

        return session_audit.finalize(), file_payloads

    @staticmethod
    def _record_audit_error(session_audit: EtcImportPreviewAudit, file_audit: EtcImportPreviewAudit) -> None:
        session_audit.original_count += 1
        session_audit.error_count += 1
        file_audit.original_count += 1
        file_audit.error_count += 1

    def _record_unique_audit_classification(
        self,
        audit: EtcImportPreviewAudit,
        status: str,
        parsed: ParsedEtcXml,
    ) -> None:
        if status == "attachment_completed":
            audit.update_count += 1
            return
        if status == "duplicate_skipped":
            audit.existing_duplicate_count += 1
            return
        if self._canonical_invoice_exists_for_etc(parsed):
            audit.merge_count += 1
            return
        audit.importable_count += 1

    def _canonical_invoice_exists_for_etc(self, parsed: ParsedEtcXml) -> bool:
        invoice_number = parsed.invoice_number.strip()
        if not invoice_number or self._canonical_invoice_key_exists is None:
            return False
        return self._canonical_invoice_key_exists(invoice_number)

    @staticmethod
    def _etc_import_file_audit_payload(
        file_id: str,
        file_name: str,
        audit: EtcImportPreviewAudit,
    ) -> dict[str, object]:
        return {
            "id": file_id,
            "fileName": file_name,
            "file_name": file_name,
            "audit": audit.to_payload(),
        }

    def _process_import_zips(
        self,
        uploads: list[UploadedEtcZipFile],
        *,
        persist: bool,
        import_session_id: str | None = None,
        progress_callback: Callable[[EtcImportResult], None] | None = None,
    ) -> EtcImportResult:
        result = EtcImportResult()
        import_batch = self._create_import_batch(uploads, import_session_id=import_session_id) if persist else None
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
                        assert import_batch is not None
                        status, invoice_id = self._upsert_invoice_from_import(
                            upload.file_name,
                            parsed,
                            xml_entry,
                            pdf_entry,
                            import_batch=import_batch,
                        )
                        if invoice_id is not None:
                            self._add_invoice_to_import_batch(import_batch, invoice_id)
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
            if import_batch is not None:
                self._refresh_import_batch_summary(import_batch)
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

    def import_missing_invoices_from_zips(
        self,
        *,
        invoice_numbers: list[str],
        uploads: list[UploadedEtcZipFile],
    ) -> EtcImportResult:
        requested_numbers = {
            str(invoice_number).strip()
            for invoice_number in list(invoice_numbers or [])
            if str(invoice_number).strip()
        }
        if not requested_numbers:
            raise EtcInvoiceRequestError("invoice_numbers must not be empty.")
        missing_numbers = {
            invoice_number
            for invoice_number in requested_numbers
            if invoice_number not in self._invoice_numbers
        }
        if not missing_numbers:
            return EtcImportResult()

        filtered_uploads: list[UploadedEtcZipFile] = []
        for upload in uploads:
            try:
                entries = self._extract_archive_entries(upload.file_name, upload.content)
            except BadZipFile:
                continue
            xml_entries = [entry for entry in entries if self._is_xml_entry(entry.path)]
            pdf_entries = [entry for entry in entries if self._is_pdf_entry(entry.path)]
            selected_entries: dict[str, bytes] = {}
            for xml_entry in xml_entries:
                try:
                    parsed = parse_etc_xml(xml_entry.content)
                except Exception:
                    continue
                if parsed.invoice_number not in missing_numbers:
                    continue
                selected_entries[xml_entry.path] = xml_entry.content
                pdf_entry = self._match_pdf_entry(parsed.invoice_number, xml_entry.path, pdf_entries)
                if pdf_entry is not None:
                    selected_entries[pdf_entry.path] = pdf_entry.content
            if selected_entries:
                buffer = BytesIO()
                with ZipFile(buffer, "w") as archive:
                    for path, content in selected_entries.items():
                        archive.writestr(path, content)
                filtered_uploads.append(UploadedEtcZipFile(upload.file_name, buffer.getvalue()))

        if not filtered_uploads:
            raise EtcInvoiceNotFoundError(f"ETC invoices not found in repair zips: {', '.join(sorted(missing_numbers))}")
        result = self.import_zips(filtered_uploads)
        still_missing = [
            invoice_number
            for invoice_number in sorted(missing_numbers)
            if invoice_number not in self._invoice_numbers
        ]
        if still_missing:
            raise EtcInvoiceNotFoundError(f"ETC invoices not found after repair import: {', '.join(still_missing)}")
        return result

    def import_historical_invoices_from_records(
        self,
        *,
        records: list[dict[str, object]],
        source_name: str,
    ) -> EtcImportResult:
        result = EtcImportResult()
        if not records:
            return result
        import_batch = self._create_import_batch(
            [UploadedEtcZipFile(str(source_name or "historical_etc_parsed_seed"), b"")],
            import_session_id=None,
        )
        now = datetime.now(UTC)
        for record in records:
            invoice_number = str(record.get("invoice_number") or "").strip()
            if not invoice_number:
                result.failed += 1
                result.items.append(EtcImportItem(str(source_name), None, "failed", "parsed seed invoice_number is missing."))
                continue
            if invoice_number in self._invoice_numbers:
                result.duplicates_skipped += 1
                result.items.append(EtcImportItem(str(source_name), invoice_number, "duplicate_skipped", "already imported"))
                continue
            invoice = EtcInvoice(
                id=self._next_invoice_id(),
                invoice_number=invoice_number,
                issue_date=str(record.get("issue_date") or ""),
                passage_start_date=str(record.get("passage_start_date") or "") or None,
                passage_end_date=str(record.get("passage_end_date") or "") or None,
                plate_number=str(record.get("plate_number") or "") or None,
                vehicle_type=str(record.get("vehicle_type") or "") or None,
                seller_name=str(record.get("seller_name") or "") or None,
                seller_tax_no=str(record.get("seller_tax_no") or "") or None,
                buyer_name=str(record.get("buyer_name") or "") or None,
                buyer_tax_no=str(record.get("buyer_tax_no") or "") or None,
                amount_without_tax=_decimal_from_amount(record.get("amount_without_tax") or "0"),
                tax_amount=_decimal_from_amount(record.get("tax_amount") or "0"),
                total_amount=_decimal_from_amount(record.get("total_amount") or "0"),
                tax_rate=str(record.get("tax_rate") or "") or None,
                zip_source_name=str(source_name or "historical_etc_parsed_seed"),
                xml_file_path=None,
                xml_file_hash=None,
                pdf_file_path=None,
                pdf_file_hash=None,
                import_batch_id=import_batch.id,
                import_session_id=None,
                created_at=now,
                updated_at=now,
            )
            self._invoices[invoice.id] = invoice
            self._invoice_numbers[invoice.invoice_number] = invoice.id
            self._add_invoice_to_import_batch(import_batch, invoice.id)
            result.imported += 1
            result.items.append(EtcImportItem(str(source_name), invoice_number, "imported"))
        self._refresh_import_batch_summary(import_batch)
        self._persist()
        return result

    def create_historical_submitted_batch(
        self,
        *,
        case_id: str,
        external_batch_id: str,
        invoice_numbers: list[str],
        linked_oa_row_id: str,
        oa_amount: Decimal | str | int | float,
        note: str | None = None,
    ) -> EtcBatch:
        resolved_case_id = str(case_id).strip()
        resolved_external_batch_id = str(external_batch_id).strip()
        resolved_oa_row_id = str(linked_oa_row_id).strip()
        if not resolved_case_id:
            raise EtcInvoiceRequestError("case_id is required.")
        if not resolved_external_batch_id:
            raise EtcInvoiceRequestError("external_batch_id is required.")
        if not resolved_oa_row_id:
            raise EtcInvoiceRequestError("linked_oa_row_id is required.")

        existing_batch = self._historical_batch_by_case_or_external_id(
            case_id=resolved_case_id,
            external_batch_id=resolved_external_batch_id,
        )
        if existing_batch is not None:
            return replace(existing_batch, invoice_ids=list(existing_batch.invoice_ids), plate_summary=list(existing_batch.plate_summary))

        invoices = self._invoices_for_invoice_numbers(invoice_numbers)
        self._batch_counter += 1
        total_amount = sum((invoice.total_amount for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        normalized_oa_amount = _decimal_from_amount(oa_amount).quantize(Decimal("0.01"))
        now = datetime.now(UTC)
        summary = self._batch_computed_summary(invoices)
        batch = EtcBatch(
            id=f"etc_batch_{self._batch_counter:04d}",
            etc_batch_id=resolved_external_batch_id,
            invoice_ids=[invoice.id for invoice in invoices],
            invoice_count=len(invoices),
            total_amount=total_amount,
            source_type="historical_repair",
            linked_oa_row_id=resolved_oa_row_id,
            linked_oa_case_id=resolved_case_id,
            amount_delta=(normalized_oa_amount - total_amount).quantize(Decimal("0.01")),
            note=str(note or "").strip(),
            issue_start_date=summary["issue_start_date"],
            issue_end_date=summary["issue_end_date"],
            passage_start_date=summary["passage_start_date"],
            passage_end_date=summary["passage_end_date"],
            plate_summary=summary["plate_summary"],
            oa_marker=f"ETC历史补关联\netc_batch_id={resolved_external_batch_id}",
            status=EtcBatchStatus.SUBMITTED_CONFIRMED.value,
            created_at=now,
            confirmed_at=now,
        )
        self._batches[batch.id] = batch
        self._apply_submitted_batch_metadata(batch, invoices=invoices, updated_at=now)
        self._persist()
        return replace(batch, invoice_ids=list(batch.invoice_ids), plate_summary=list(batch.plate_summary))

    def create_oa_draft(
        self,
        invoice_ids: list[str],
        *,
        oa_client: EtcOAClient | None = None,
        reconciliation_task: object | None = None,
        business_batch_id: str | None = None,
    ) -> EtcDraftResult:
        invoices = self._validate_draft_invoices(invoice_ids)
        batch = self._create_batch(invoices, reconciliation_task=reconciliation_task, business_batch_id=business_batch_id)
        resolved_oa_client = oa_client or self.oa_client
        try:
            attachments = self._upload_batch_attachments(invoices, resolved_oa_client, reconciliation_task=reconciliation_task)
            payload = self._build_oa_draft_payload(batch, attachments)
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
        for import_batch in self._import_batches_for_invoices(invoices):
            import_batch.submission_batch_id = batch.id
            import_batch.updated_at = now
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
        self._apply_submitted_batch_metadata(batch, updated_at=now)
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
        batch = self._batch_by_id_or_external_id(batch_id)
        if batch is None:
            raise EtcBatchNotFoundError(f"ETC batch not found: {batch_id}")
        return batch

    def list_batches(
        self,
        *,
        status: str | None = None,
        month: str | None = None,
        plate: str | None = None,
        keyword: str | None = None,
    ) -> list[EtcBatch]:
        filtered = [
            batch
            for batch in self._batches.values()
            if self._batch_matches_status(batch, status)
            and self._batch_matches_month(batch, month)
            and self._batch_matches_plate(batch, plate)
            and self._batch_matches_keyword(batch, keyword)
        ]
        return sorted(filtered, key=lambda batch: batch.created_at)

    def batch_counts(self) -> dict[str, int]:
        batches = list(self._batches.values())
        submitted = sum(1 for batch in batches if batch.status == EtcBatchStatus.SUBMITTED_CONFIRMED.value)
        unsubmitted = len(batches) - submitted
        return {"unsubmitted": unsubmitted, "submitted": submitted}

    def get_batch_detail(self, batch_id: str) -> dict[str, object]:
        batch = self.get_batch(batch_id)
        invoices = [self._get_invoice(invoice_id) for invoice_id in batch.invoice_ids if invoice_id in self._invoices]
        summary = self._batch_summary_payload(batch)
        return {
            "batch": replace(batch, invoice_ids=list(batch.invoice_ids), plate_summary=list(batch.plate_summary)),
            "summary": summary,
            "plate_summary": list(batch.plate_summary),
            "invoice_items": [self._batch_invoice_item_payload(invoice) for invoice in invoices],
            "supplement_items": list(getattr(batch, "supplement_items", []) or []),
        }

    def list_import_batches(self) -> list[EtcImportBatch]:
        return sorted(self._import_batches.values(), key=lambda batch: batch.created_at)

    def delete_batch(self, batch_id: str) -> dict[str, object]:
        resolved_batch_id = str(batch_id or "").strip()
        if not resolved_batch_id:
            raise EtcBatchNotFoundError("ETC batch not found: empty batch id")

        import_batch = self._import_batches.get(resolved_batch_id)
        if import_batch is not None:
            result = self._delete_import_batch(import_batch)
            self._persist()
            return result

        batch = self._batch_by_id_or_external_id(resolved_batch_id)
        if batch is None:
            raise EtcBatchNotFoundError(f"ETC batch not found: {resolved_batch_id}")
        result = self._delete_submission_batch(batch)
        self._persist()
        return result

    def release_missing_submission_batch_link(self, batch_id: str) -> list[EtcInvoice]:
        resolved_batch_id = str(batch_id or "").strip()
        if not resolved_batch_id:
            raise EtcBatchNotFoundError("ETC batch not found: empty batch id")
        if self._batch_by_id_or_external_id(resolved_batch_id) is not None:
            raise EtcBatchDeleteError("ETC batch still exists and must be deleted through the batch delete flow.")

        now = datetime.now(UTC)
        changed_invoice_ids: set[str] = set()
        for import_batch in self._import_batches.values():
            if str(import_batch.submission_batch_id or "").strip() == resolved_batch_id:
                import_batch.submission_batch_id = None
                import_batch.updated_at = now
                changed_invoice_ids.update(str(invoice_id) for invoice_id in list(import_batch.invoice_ids or []))
        for invoice in self._invoices.values():
            if str(invoice.current_batch_id or "").strip() == resolved_batch_id:
                invoice.current_batch_id = None
                invoice.status = EtcInvoiceStatus.UNSUBMITTED
                invoice.updated_at = now
                changed_invoice_ids.add(invoice.id)
        if changed_invoice_ids:
            self._persist()
        return [replace(self._get_invoice(invoice_id)) for invoice_id in sorted(changed_invoice_ids) if invoice_id in self._invoices]

    def list_invoices_by_ids(self, invoice_ids: list[str]) -> list[EtcInvoice]:
        return [replace(self._get_invoice(invoice_id)) for invoice_id in invoice_ids]

    def list_invoices_by_numbers(self, invoice_numbers: list[str]) -> list[EtcInvoice]:
        normalized_numbers = [str(number).strip() for number in invoice_numbers if str(number).strip()]
        invoices: list[EtcInvoice] = []
        for invoice_number in normalized_numbers:
            invoice_id = self._invoice_numbers.get(invoice_number)
            if invoice_id is None:
                continue
            invoices.append(replace(self._get_invoice(invoice_id)))
        return invoices

    def list_invoices_by_import_batch_id(self, import_batch_id: str) -> list[EtcInvoice]:
        normalized_batch_id = str(import_batch_id or "").strip()
        if not normalized_batch_id:
            return []
        return [
            replace(invoice)
            for invoice in self._invoices.values()
            if str(getattr(invoice, "import_batch_id", "") or "").strip() == normalized_batch_id
        ]

    def delete_import_batch_sources(self, import_batch_id: str) -> dict[str, object]:
        normalized_batch_id = str(import_batch_id or "").strip()
        if not normalized_batch_id:
            raise EtcBatchNotFoundError("ETC batch not found: empty batch id")

        import_batch = self._import_batches.get(normalized_batch_id)
        if import_batch is not None:
            result = self._delete_import_batch(import_batch)
            self._persist()
            return result

        invoices = [
            invoice
            for invoice in self._invoices.values()
            if str(getattr(invoice, "import_batch_id", "") or "").strip() == normalized_batch_id
        ]
        for invoice in invoices:
            if str(invoice.current_batch_id or "").strip():
                raise EtcBatchDeleteError("import batch contains invoices assigned to an OA batch and cannot be deleted.")
        for invoice in invoices:
            self._delete_invoice_files(invoice)
            self._invoice_numbers.pop(invoice.invoice_number, None)
            self._invoices.pop(invoice.id, None)
        self._persist()
        return {
            "deleted": True,
            "batchId": normalized_batch_id,
            "kind": "missing_import_batch",
            "orphanInvoiceCount": len(invoices),
        }

    def snapshot(self) -> dict[str, object]:
        return {
            "invoice_counter": self._invoice_counter,
            "batch_counter": self._batch_counter,
            "import_batch_counter": self._import_batch_counter,
            "business_batch_counter": self._business_batch_counter,
            "batch_day_counters": self._batch_day_counters,
            "invoices": self._invoices,
            "invoice_numbers": self._invoice_numbers,
            "batches": self._batches,
            "import_batches": self._import_batches,
            "business_batches": self._business_batches,
        }

    def _hydrate(self, snapshot: dict[str, object]) -> None:
        self._invoice_counter = int(snapshot.get("invoice_counter", 0) or 0)
        self._batch_counter = int(snapshot.get("batch_counter", 0) or 0)
        self._import_batch_counter = int(snapshot.get("import_batch_counter", 0) or 0)
        self._business_batch_counter = int(snapshot.get("business_batch_counter", 0) or 0)
        self._batch_day_counters = dict(snapshot.get("batch_day_counters") or {})
        self._invoices = dict(snapshot.get("invoices") or {})
        self._invoice_numbers = dict(snapshot.get("invoice_numbers") or {})
        self._batches = dict(snapshot.get("batches") or {})
        self._import_batches = dict(snapshot.get("import_batches") or {})
        self._business_batches = dict(snapshot.get("business_batches") or {})
        for invoice in self._invoices.values():
            if isinstance(invoice.status, str):
                invoice.status = _coerce_invoice_status(invoice.status)
            if not hasattr(invoice, "import_batch_id"):
                invoice.import_batch_id = None
            if not hasattr(invoice, "import_session_id"):
                invoice.import_session_id = None
        for batch in self._batches.values():
            self._ensure_batch_metadata_fields(batch)
        for business_batch in self._business_batches.values():
            self._ensure_business_batch_fields(business_batch)

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

    def _active_business_batch_for_task(self, task_id: str) -> EtcBusinessBatch | None:
        active = [
            batch
            for batch in self._business_batches.values()
            if batch.task_id == task_id and batch.is_active
        ]
        if len(active) > 1:
            now = datetime.now(UTC)
            for batch in active:
                before_status = batch.status
                batch.status = EtcBusinessBatchStatus.MIGRATION_CONFLICT.value
                batch.task_active_key = f"{batch.task_id}:active"
                batch.updated_at = now
                self._append_business_batch_audit(
                    batch,
                    "business_batch_active_conflict_detected",
                    before_status=before_status,
                    after_status=batch.status,
                )
            self._persist()
            return active[0]
        return active[0] if active else None

    def _get_business_batch_mutable(self, business_batch_id: str | EtcBusinessBatch) -> EtcBusinessBatch:
        if isinstance(business_batch_id, EtcBusinessBatch):
            return business_batch_id
        normalized_id = str(business_batch_id or "").strip()
        batch = self._business_batches.get(normalized_id)
        if batch is None:
            raise EtcBusinessBatchNotFoundError(f"ETC business batch not found: {normalized_id}")
        self._ensure_business_batch_fields(batch)
        return batch

    @staticmethod
    def _copy_business_batch(batch: EtcBusinessBatch) -> EtcBusinessBatch:
        return replace(
            batch,
            import_batch_ids=list(batch.import_batch_ids),
            invoice_ids=list(batch.invoice_ids),
            import_attempts=[dict(item) for item in batch.import_attempts],
            audit_events=[dict(item) for item in batch.audit_events],
        )

    @staticmethod
    def _ensure_business_batch_fields(batch: EtcBusinessBatch) -> None:
        defaults: dict[str, object] = {
            "status": EtcBusinessBatchStatus.DRAFT.value,
            "version": 1,
            "idempotency_key": None,
            "owner_user_id": None,
            "owner_org_id": None,
            "task_active_key": None,
            "import_batch_ids": [],
            "submission_batch_id": None,
            "external_etc_batch_id": None,
            "oa_draft_id": None,
            "oa_draft_url": None,
            "oa_row_id": None,
            "oa_process_status": "unknown",
            "oa_detection_status": "not_started",
            "oa_detection_started_at": None,
            "oa_detection_next_run_at": None,
            "oa_detection_deadline_at": None,
            "oa_detection_final_retry_until": None,
            "oa_detection_attempts": 0,
            "oa_detection_error": None,
            "oa_detection_reason": None,
            "invoice_ids": [],
            "import_attempts": [],
            "audit_events": [],
            "created_at": datetime.now(UTC),
            "updated_at": datetime.now(UTC),
        }
        for field_name, default in defaults.items():
            if not hasattr(batch, field_name):
                setattr(batch, field_name, default)
        if batch.task_active_key is None and batch.is_active:
            batch.task_active_key = f"{batch.task_id}:active"
        if batch.task_active_key is not None and not batch.is_active:
            batch.task_active_key = None

    @staticmethod
    def _assert_business_batch_version(batch: EtcBusinessBatch, expected_version: int | None) -> None:
        if expected_version is None:
            return
        if int(expected_version) != int(batch.version):
            raise EtcBusinessBatchVersionConflictError(batch.business_batch_id, int(expected_version), int(batch.version))

    @staticmethod
    def _assert_business_batch_allows_import(batch: EtcBusinessBatch) -> None:
        if batch.status not in ETC_BUSINESS_BATCH_IMPORT_ALLOWED_STATUSES:
            raise EtcBusinessBatchInvalidTransitionError(
                "ETC business batch already has an OA draft; revoke it before supplement import.",
                code="oa_draft_already_exists",
            )
        if str(batch.submission_batch_id or "").strip() or str(batch.oa_draft_id or "").strip():
            raise EtcBusinessBatchInvalidTransitionError(
                "ETC business batch already has an OA draft; revoke it before supplement import.",
                code="oa_draft_already_exists",
            )

    @staticmethod
    def _refresh_business_batch_active_key(batch: EtcBusinessBatch) -> None:
        batch.task_active_key = f"{batch.task_id}:active" if batch.is_active else None

    def _bump_business_batch_version(
        self,
        batch: EtcBusinessBatch,
        *,
        event_type: str,
        before_status: str | None,
        after_status: str | None,
        reason: str | None = None,
        submission_batch_id: str | None = None,
        oa_row_id: str | None = None,
        candidates: list[dict[str, object]] | None = None,
    ) -> None:
        batch.version += 1
        batch.updated_at = datetime.now(UTC)
        self._refresh_business_batch_active_key(batch)
        self._append_business_batch_audit(
            batch,
            event_type,
            before_status=before_status,
            after_status=after_status,
            reason=reason,
            submission_batch_id=submission_batch_id,
            oa_row_id=oa_row_id,
            candidates=candidates,
        )

    def _append_business_batch_audit(
        self,
        batch: EtcBusinessBatch,
        event_type: str,
        *,
        before_status: str | None,
        after_status: str | None,
        reason: str | None = None,
        submission_batch_id: str | None = None,
        oa_row_id: str | None = None,
        candidates: list[dict[str, object]] | None = None,
    ) -> None:
        event = {
            "event_id": f"etc_business_audit_{uuid4().hex[:12]}",
            "event_type": event_type,
            "source": "api",
            "business_batch_id": batch.business_batch_id,
            "task_id": batch.task_id,
            "import_batch_ids": list(batch.import_batch_ids),
            "submission_batch_id": submission_batch_id if submission_batch_id is not None else batch.submission_batch_id,
            "external_etc_batch_id": batch.external_etc_batch_id,
            "oa_row_id": oa_row_id if oa_row_id is not None else batch.oa_row_id,
            "before_status": before_status,
            "after_status": after_status,
            "actual_version": batch.version,
            "reason": reason,
            "created_at": datetime.now(UTC),
        }
        if candidates is not None:
            event["candidates"] = list(candidates)
        batch.audit_events.append(event)

    def _extract_archive_entries(
        self,
        source_name: str,
        content: bytes,
        *,
        depth: int = 0,
        path_prefix: str = "",
    ) -> list[_ArchiveEntry]:
        if depth > 8:
            raise BadZipFile("nested zip depth exceeds limit")
        entries: list[_ArchiveEntry] = []
        with ZipFile(BytesIO(content)) as archive:
            for info in archive.infolist():
                if info.is_dir():
                    continue
                file_content = archive.read(info)
                path = f"{path_prefix}{info.filename}"
                if path.lower().endswith(".zip"):
                    entries.extend(
                        self._extract_archive_entries(
                            source_name,
                            file_content,
                            depth=depth + 1,
                            path_prefix=f"{path}/",
                        )
                    )
                else:
                    entries.append(_ArchiveEntry(source_name, path, file_content))
        return entries

    @staticmethod
    def _is_xml_entry(path: str) -> bool:
        return path.lower().endswith(".xml") and not Path(path).name.startswith(".")

    @staticmethod
    def _is_pdf_entry(path: str) -> bool:
        return path.lower().endswith(".pdf") and not Path(path).name.startswith(".")

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
        *,
        import_batch: EtcImportBatch,
    ) -> tuple[str, str | None]:
        existing_id = self._invoice_numbers.get(parsed.invoice_number)
        existing = self._invoices.get(existing_id) if existing_id else None
        existing_has_xml = existing is not None and self._stored_invoice_file_exists(existing.xml_file_path)
        existing_has_pdf = existing is not None and self._stored_invoice_file_exists(existing.pdf_file_path)
        if existing is not None and existing_has_xml and existing_has_pdf:
            return "duplicate_skipped", None

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
                import_batch_id=import_batch.id,
                import_session_id=import_batch.source_session_id,
                created_at=now,
                updated_at=now,
            )
            self._invoices[invoice.id] = invoice
            self._invoice_numbers[invoice.invoice_number] = invoice.id
            return "imported", invoice.id

        completed = False
        if not existing_has_xml and xml_path:
            existing.xml_file_path = xml_path
            existing.xml_file_hash = xml_hash
            completed = True
        if not existing_has_pdf and pdf_path:
            existing.pdf_file_path = pdf_path
            existing.pdf_file_hash = pdf_hash
            completed = True
        if existing.import_batch_id is None:
            existing.import_batch_id = import_batch.id
        if existing.import_session_id is None:
            existing.import_session_id = import_batch.source_session_id
        existing.updated_at = now
        return ("attachment_completed" if completed else "duplicate_skipped"), existing.id if completed else None

    def _create_import_batch(
        self,
        uploads: list[UploadedEtcZipFile],
        *,
        import_session_id: str | None,
    ) -> EtcImportBatch:
        self._import_batch_counter += 1
        batch = EtcImportBatch(
            id=f"etc_import_batch_{self._import_batch_counter:04d}",
            source_names=[upload.file_name for upload in uploads],
            source_session_id=import_session_id,
        )
        self._import_batches[batch.id] = batch
        return batch

    @staticmethod
    def _add_invoice_to_import_batch(import_batch: EtcImportBatch, invoice_id: str) -> None:
        if invoice_id not in import_batch.invoice_ids:
            import_batch.invoice_ids.append(invoice_id)

    def _refresh_import_batch_summary(self, import_batch: EtcImportBatch) -> None:
        invoices = [self._invoices[invoice_id] for invoice_id in import_batch.invoice_ids if invoice_id in self._invoices]
        import_batch.invoice_count = len(invoices)
        import_batch.total_amount = sum((invoice.total_amount for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        issue_dates = sorted(invoice.issue_date for invoice in invoices if invoice.issue_date)
        passage_dates = sorted(
            date_value
            for invoice in invoices
            for date_value in (invoice.passage_start_date, invoice.passage_end_date)
            if date_value
        )
        import_batch.issue_date_start = issue_dates[0] if issue_dates else None
        import_batch.issue_date_end = issue_dates[-1] if issue_dates else None
        import_batch.passage_date_start = passage_dates[0] if passage_dates else None
        import_batch.passage_date_end = passage_dates[-1] if passage_dates else None
        import_batch.updated_at = datetime.now(UTC)

    @staticmethod
    def _is_external_file_ref(path: str | None) -> bool:
        return bool(path and "://" in path)

    def _stored_invoice_file_exists(self, path: str | None) -> bool:
        if not path:
            return False
        if self._is_external_file_ref(path):
            exists = getattr(self._state_store, "etc_invoice_file_exists", None)
            return bool(callable(exists) and exists(path))
        return Path(path).exists()

    def _read_stored_invoice_file(self, path: str) -> bytes:
        if self._is_external_file_ref(path):
            reader = getattr(self._state_store, "read_etc_invoice_file", None)
            if not callable(reader):
                raise EtcDraftRequestError("ETC invoice attachment storage is not readable.")
            return bytes(reader(path))
        return Path(path).read_bytes()

    def _delete_stored_invoice_file(self, path: str) -> None:
        if self._is_external_file_ref(path):
            deleter = getattr(self._state_store, "delete_etc_invoice_file", None)
            if callable(deleter):
                deleter(path)
            return
        file_path = Path(path)
        if file_path.exists():
            file_path.unlink()

    def _migrate_local_invoice_files_to_state_store(self) -> bool:
        if self._state_store is None or not hasattr(self._state_store, "store_etc_invoice_file"):
            return False
        changed = False
        for invoice in self._invoices.values():
            for path_field, hash_field, file_name in (
                ("xml_file_path", "xml_file_hash", "invoice.xml"),
                ("pdf_file_path", "pdf_file_hash", "invoice.pdf"),
            ):
                current_path = getattr(invoice, path_field)
                if not current_path or self._is_external_file_ref(current_path):
                    continue
                local_path = Path(current_path)
                if not local_path.exists() or not local_path.is_file():
                    continue
                content = local_path.read_bytes()
                stored_path = self._state_store.store_etc_invoice_file(
                    invoice_number=invoice.invoice_number,
                    file_name=file_name,
                    content=content,
                )
                setattr(invoice, path_field, str(stored_path))
                setattr(invoice, hash_field, hashlib.sha256(content).hexdigest())
                invoice.updated_at = datetime.now(UTC)
                changed = True
        return changed

    def _store_invoice_file(self, parsed: ParsedEtcXml, file_name: str, content: bytes) -> tuple[str, str]:
        if self._state_store is not None and hasattr(self._state_store, "store_etc_invoice_file"):
            stored_path = self._state_store.store_etc_invoice_file(
                invoice_number=parsed.invoice_number,
                file_name=file_name,
                content=content,
            )
            return str(stored_path), hashlib.sha256(content).hexdigest()
        month = parsed.issue_date[:7] if parsed.issue_date else "unknown"
        year, month_part = (month.split("-", 1) + ["unknown"])[:2] if "-" in month else ("unknown", "unknown")
        invoice_dir = self._invoice_file_root / _safe_path_part(year) / _safe_path_part(month_part) / _safe_path_part(parsed.invoice_number)
        invoice_dir.mkdir(parents=True, exist_ok=True)
        path = invoice_dir / file_name
        path.write_bytes(content)
        return str(path), hashlib.sha256(content).hexdigest()

    def _canonical_invoice_file_candidates(self, invoice: EtcInvoice, file_name: str) -> list[Path]:
        candidates: list[Path] = []
        month = invoice.issue_date[:7] if invoice.issue_date else ""
        if "-" in month:
            year, month_part = (month.split("-", 1) + ["unknown"])[:2]
            candidates.append(
                self._invoice_file_root
                / _safe_path_part(year)
                / _safe_path_part(month_part)
                / _safe_path_part(invoice.invoice_number)
                / file_name
            )
        candidates.extend(
            sorted(
                self._invoice_file_root.glob(f"*/*/{_safe_path_part(invoice.invoice_number)}/{file_name}"),
                key=lambda path: str(path),
            )
        )
        unique_candidates: list[Path] = []
        seen: set[str] = set()
        for candidate in candidates:
            key = str(candidate)
            if key in seen:
                continue
            seen.add(key)
            unique_candidates.append(candidate)
        return unique_candidates

    def _repair_invoice_attachment_paths(self, invoice: EtcInvoice) -> bool:
        changed = False
        attachment_fields = (
            ("xml_file_path", "xml_file_hash", "invoice.xml"),
            ("pdf_file_path", "pdf_file_hash", "invoice.pdf"),
        )
        for path_field, hash_field, file_name in attachment_fields:
            current_path = getattr(invoice, path_field)
            if self._stored_invoice_file_exists(current_path):
                continue
            for candidate in self._canonical_invoice_file_candidates(invoice, file_name):
                if not candidate.exists() or not candidate.is_file():
                    continue
                setattr(invoice, path_field, str(candidate))
                setattr(invoice, hash_field, hashlib.sha256(candidate.read_bytes()).hexdigest())
                invoice.updated_at = datetime.now(UTC)
                changed = True
                break
        return changed

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
        self._validate_complete_import_batches(invoices)
        repaired = False
        missing_attachments: list[str] = []
        for invoice in invoices:
            repaired = self._repair_invoice_attachment_paths(invoice) or repaired
            if invoice.status != EtcInvoiceStatus.UNSUBMITTED:
                raise EtcDraftRequestError(f"ETC invoice {invoice.invoice_number} is already submitted.")
            missing_parts: list[str] = []
            if not self._stored_invoice_file_exists(invoice.pdf_file_path):
                missing_parts.append("PDF")
            if not self._stored_invoice_file_exists(invoice.xml_file_path):
                missing_parts.append("XML")
            if missing_parts:
                missing_attachments.append(f"{invoice.invoice_number} 缺少 {'/'.join(missing_parts)}")
        if repaired:
            self._persist()
        if missing_attachments:
            missing_text = "；".join(missing_attachments)
            raise EtcDraftRequestError(f"ETC OA 草稿附件不完整：{missing_text}.")
        return invoices

    def _validate_complete_import_batches(self, invoices: list[EtcInvoice]) -> None:
        selected_ids = {invoice.id for invoice in invoices}
        for invoice in invoices:
            if not invoice.import_batch_id:
                continue
            expected_ids = {
                candidate.id
                for candidate in self._invoices.values()
                if candidate.import_batch_id == invoice.import_batch_id and candidate.status == EtcInvoiceStatus.UNSUBMITTED
            }
            if not expected_ids.issubset(selected_ids):
                missing_numbers = sorted(
                    candidate.invoice_number
                    for candidate in self._invoices.values()
                    if candidate.id in expected_ids - selected_ids
                )
                missing_text = "、".join(missing_numbers)
                raise EtcDraftRequestError(
                    f"ETC OA 草稿必须覆盖完整未提交 ETC 导入批次 {invoice.import_batch_id}；缺少发票: {missing_text}."
                )

    def _import_batches_for_invoices(self, invoices: list[EtcInvoice]) -> list[EtcImportBatch]:
        import_batch_ids = {invoice.import_batch_id for invoice in invoices if invoice.import_batch_id}
        return [batch for batch_id in sorted(import_batch_ids) if (batch := self._import_batches.get(batch_id)) is not None]

    def _delete_import_batch(self, import_batch: EtcImportBatch) -> dict[str, object]:
        if str(import_batch.submission_batch_id or "").strip():
            raise EtcBatchDeleteError("import batch has an OA draft and cannot be deleted before deleting the draft batch.")
        invoice_ids = [str(invoice_id) for invoice_id in list(import_batch.invoice_ids or [])]
        invoices = [self._invoices[invoice_id] for invoice_id in invoice_ids if invoice_id in self._invoices]
        for invoice in invoices:
            if str(invoice.current_batch_id or "").strip():
                raise EtcBatchDeleteError("import batch contains invoices assigned to an OA batch and cannot be deleted.")
        for invoice in invoices:
            self._delete_invoice_files(invoice)
            self._invoice_numbers.pop(invoice.invoice_number, None)
            self._invoices.pop(invoice.id, None)
        self._import_batches.pop(import_batch.id, None)
        return {"deleted": True, "batchId": import_batch.id, "kind": "import_batch"}

    def _delete_submission_batch(self, batch: EtcBatch) -> dict[str, object]:
        if batch.status == EtcBatchStatus.SUBMITTED_CONFIRMED.value:
            raise EtcBatchDeleteError("submitted ETC batch cannot be deleted.")
        if str(batch.linked_oa_row_id or "").strip() or str(batch.linked_oa_case_id or "").strip():
            raise EtcBatchDeleteError("ETC batch is linked to OA/workbench records and cannot be deleted.")
        if batch.confirmed_at is not None:
            raise EtcBatchDeleteError("ETC batch has submitted confirmation metadata and cannot be deleted.")
        allowed_statuses = {
            EtcBatchStatus.DRAFT_CREATING.value,
            EtcBatchStatus.DRAFT_CREATED.value,
            EtcBatchStatus.NOT_SUBMITTED.value,
            EtcBatchStatus.FAILED.value,
        }
        if str(batch.status) not in allowed_statuses:
            raise EtcBatchDeleteError(f"ETC batch status {batch.status} cannot be deleted.")

        now = datetime.now(UTC)
        invoices = [self._get_invoice(invoice_id) for invoice_id in batch.invoice_ids if invoice_id in self._invoices]
        for invoice in invoices:
            if invoice.current_batch_id == batch.id:
                invoice.current_batch_id = None
            invoice.status = EtcInvoiceStatus.UNSUBMITTED
            invoice.updated_at = now
        for import_batch in self._import_batches_for_invoices(invoices):
            if import_batch.submission_batch_id == batch.id:
                import_batch.submission_batch_id = None
                import_batch.updated_at = now
        self._batches.pop(batch.id, None)
        return {"deleted": True, "batchId": batch.id, "kind": "submission_batch"}

    def _delete_invoice_files(self, invoice: EtcInvoice) -> None:
        for raw_path in (invoice.xml_file_path, invoice.pdf_file_path):
            if not raw_path:
                continue
            self._delete_stored_invoice_file(raw_path)
            if self._is_external_file_ref(raw_path):
                continue
            path = Path(raw_path)
            parent = path.parent
            try:
                if parent != self._invoice_file_root and parent.exists() and not any(parent.iterdir()):
                    parent.rmdir()
            except OSError:
                pass

    def _create_batch(
        self,
        invoices: list[EtcInvoice],
        *,
        reconciliation_task: object | None = None,
        business_batch_id: str | None = None,
    ) -> EtcBatch:
        self._batch_counter += 1
        batch_id = f"etc_batch_{self._batch_counter:04d}"
        etc_batch_id = self._next_etc_batch_id()
        total_amount = sum((invoice.total_amount for invoice in invoices), Decimal("0.00")).quantize(Decimal("0.01"))
        summary = self._batch_computed_summary(invoices)
        reconciliation_metadata = self._reconciliation_batch_metadata(reconciliation_task)
        if reconciliation_metadata:
            total_amount = Decimal(str(reconciliation_metadata["oa_total_amount"])).quantize(Decimal("0.01"))
        marker_lines = ["ETC批量提交", f"etc_batch_id={etc_batch_id}"]
        normalized_business_batch_id = str(business_batch_id or "").strip()
        if normalized_business_batch_id:
            marker_lines.append(f"business_batch_id={normalized_business_batch_id}")
        marker = "\n".join(marker_lines)
        batch = EtcBatch(
            id=batch_id,
            etc_batch_id=etc_batch_id,
            invoice_ids=[invoice.id for invoice in invoices],
            invoice_count=len(invoices),
            total_amount=total_amount,
            issue_start_date=summary["issue_start_date"],
            issue_end_date=summary["issue_end_date"],
            passage_start_date=summary["passage_start_date"],
            passage_end_date=summary["passage_end_date"],
            plate_summary=summary["plate_summary"],
            oa_marker=marker,
        )
        if reconciliation_metadata:
            batch.reconciliation_task_id = str(reconciliation_metadata["reconciliation_task_id"])
            batch.statement_period_start = _optional_text(reconciliation_metadata.get("statement_period_start"))
            batch.statement_period_end = _optional_text(reconciliation_metadata.get("statement_period_end"))
            batch.oa_total_amount = Decimal(str(reconciliation_metadata["oa_total_amount"])).quantize(Decimal("0.01"))
            batch.etc_invoice_amount = Decimal(str(reconciliation_metadata["etc_invoice_amount"])).quantize(Decimal("0.01"))
            batch.supplement_amount = Decimal(str(reconciliation_metadata["supplement_amount"])).quantize(Decimal("0.01"))
            batch.etc_invoice_count = int(reconciliation_metadata["etc_invoice_count"])
            batch.supplement_count = int(reconciliation_metadata["supplement_count"])
            batch.supplement_items = list(reconciliation_metadata["supplement_items"])
            batch.display_count_text = (
                f"ETC票 {batch.etc_invoice_count} + 补充凭证 {batch.supplement_count}"
            )
            batch.passage_start_date = _optional_text(reconciliation_metadata.get("period_start"))
            batch.passage_end_date = _optional_text(reconciliation_metadata.get("period_end"))
        self._batches[batch.id] = batch
        self._persist()
        return batch

    def _upload_batch_attachments(
        self,
        invoices: list[EtcInvoice],
        oa_client: EtcOAClient,
        *,
        reconciliation_task: object | None = None,
    ) -> list[EtcUploadedAttachment]:
        attachments: list[EtcUploadedAttachment] = []
        with TemporaryDirectory(prefix="fin-ops-etc-oa-") as temp_dir:
            temp_root = Path(temp_dir)
            for invoice in invoices:
                assert invoice.pdf_file_path is not None
                attachment_name = f"{invoice.invoice_number}.pdf"
                if self._is_external_file_ref(invoice.pdf_file_path):
                    content = self._read_stored_invoice_file(invoice.pdf_file_path)
                    pdf_path = temp_root / attachment_name
                    pdf_path.write_bytes(content)
                else:
                    pdf_path = Path(invoice.pdf_file_path)
                attachment_url = oa_client.upload_attachment(pdf_path)
                attachments.append(
                    EtcUploadedAttachment(
                        name=attachment_name,
                        url=attachment_url,
                        size=pdf_path.stat().st_size,
                    )
                )
            for supplement in list(getattr(reconciliation_task, "submission_supplement_attachments", []) or []):
                stored_path = Path(str(getattr(supplement, "stored_path", "") or ""))
                if not stored_path.exists() or not stored_path.is_file():
                    raise EtcOAClientError(f"ETC supplement attachment file is missing: {stored_path.name or stored_path}")
                attachment_url = oa_client.upload_attachment(stored_path)
                attachments.append(
                    EtcUploadedAttachment(
                        name=str(getattr(supplement, "original_name", "") or stored_path.name),
                        url=attachment_url,
                        size=stored_path.stat().st_size,
                    )
                )
        return attachments

    def _build_oa_draft_payload(self, batch: EtcBatch, attachments: list[EtcUploadedAttachment]) -> dict[str, object]:
        cause = batch.oa_marker
        data = {
            self._form_mapping.application_date: date.today().isoformat(),
            self._form_mapping.category: self._form_mapping.category_value,
            self._form_mapping.payment_proof: self._form_mapping.payment_proof_value,
            self._form_mapping.project_name: self._form_mapping.project_name_value,
            self._form_mapping.amount: f"{batch.total_amount:.2f}",
            "invoiceCount": batch.invoice_count,
            "invoice_count": batch.invoice_count,
            "etcInvoiceCount": batch.invoice_count,
            self._form_mapping.cause: cause,
            self._form_mapping.attachments: self._build_oa_upload_custom_value(attachments),
        }
        return {
            "formId": 2,
            "isDraft": True,
            "data": data,
            "etc_batch_id": batch.etc_batch_id,
            "oa_marker": batch.oa_marker,
            "invoiceCount": batch.invoice_count,
            "invoiceIds": list(batch.invoice_ids),
        }

    @staticmethod
    def _build_oa_upload_custom_value(attachments: list[EtcUploadedAttachment]) -> dict[str, list[dict[str, object]]]:
        base_uid = int(datetime.now(UTC).timestamp() * 1000)
        items: list[dict[str, object]] = []
        for index, attachment in enumerate(attachments, start=1):
            uid = base_uid + index
            suffix = Path(attachment.name).suffix.lstrip(".").lower()
            items.append(
                {
                    "name": attachment.name,
                    "percentage": 100,
                    "raw": {"uid": uid},
                    "response": {
                        "data": attachment.url,
                        "dataSize": 1,
                        "description": "上传完成",
                        "errorCode": 0,
                        "extra": {
                            "createdTime": None,
                            "downloads": None,
                            "fileIndex": None,
                            "fileName": attachment.name,
                            "filePath": attachment.url,
                            "folderId": None,
                            "folderList": None,
                            "id": None,
                            "modifiedTime": None,
                            "suffix": suffix,
                            "targetId": None,
                            "targetName": None,
                        },
                        "success": True,
                    },
                    "size": attachment.size,
                    "status": "success",
                    "uid": uid,
                }
            )
        return {"list": items}

    def _get_invoice(self, invoice_id: str) -> EtcInvoice:
        invoice = self._invoices.get(invoice_id)
        if invoice is None:
            raise EtcInvoiceNotFoundError(f"ETC invoice not found: {invoice_id}")
        return invoice

    def _invoices_for_invoice_numbers(self, invoice_numbers: list[str]) -> list[EtcInvoice]:
        normalized_numbers = [
            str(invoice_number).strip()
            for invoice_number in list(invoice_numbers or [])
            if str(invoice_number).strip()
        ]
        if not normalized_numbers:
            raise EtcInvoiceRequestError("invoice_numbers must not be empty.")
        seen_numbers: set[str] = set()
        invoices: list[EtcInvoice] = []
        missing_numbers: list[str] = []
        for invoice_number in normalized_numbers:
            if invoice_number in seen_numbers:
                continue
            seen_numbers.add(invoice_number)
            invoice_id = self._invoice_numbers.get(invoice_number)
            if invoice_id is None:
                missing_numbers.append(invoice_number)
                continue
            invoices.append(self._get_invoice(invoice_id))
        if missing_numbers:
            raise EtcInvoiceNotFoundError(f"ETC invoices not found: {', '.join(missing_numbers)}")
        return invoices

    def _historical_batch_by_case_or_external_id(self, *, case_id: str, external_batch_id: str) -> EtcBatch | None:
        for batch in self._batches.values():
            if str(getattr(batch, "linked_oa_case_id", "") or "").strip() == case_id:
                return batch
            if str(batch.etc_batch_id).strip() == external_batch_id and getattr(batch, "source_type", "") == "historical_repair":
                return batch
        return None

    def _batch_by_id_or_external_id(self, batch_id: str) -> EtcBatch | None:
        resolved_batch_id = str(batch_id).strip()
        if not resolved_batch_id:
            return None
        batch = self._batches.get(resolved_batch_id)
        if batch is not None:
            return batch
        for candidate in self._batches.values():
            if candidate.etc_batch_id == resolved_batch_id:
                return candidate
        return None

    def _apply_submitted_batch_metadata(
        self,
        batch: EtcBatch,
        *,
        invoices: list[EtcInvoice] | None = None,
        updated_at: datetime | None = None,
    ) -> None:
        resolved_invoices = invoices if invoices is not None else [self._get_invoice(invoice_id) for invoice_id in batch.invoice_ids]
        now = updated_at or datetime.now(UTC)
        for invoice in resolved_invoices:
            invoice.status = EtcInvoiceStatus.SUBMITTED
            invoice.current_batch_id = batch.id
            invoice.last_batch_id = batch.id
            invoice.updated_at = now
        for import_batch in self._import_batches_for_invoices(resolved_invoices):
            import_batch.submission_batch_id = batch.id
            import_batch.updated_at = now

    @staticmethod
    def _batch_computed_summary(invoices: list[EtcInvoice]) -> dict[str, object]:
        issue_dates = sorted(invoice.issue_date for invoice in invoices if invoice.issue_date)
        passage_dates = sorted(
            date_value
            for invoice in invoices
            for date_value in (invoice.passage_start_date, invoice.passage_end_date)
            if date_value
        )
        plate_totals: dict[str, dict[str, object]] = {}
        for invoice in invoices:
            plate_number = (invoice.plate_number or "未识别车牌").strip() or "未识别车牌"
            summary = plate_totals.setdefault(
                plate_number,
                {"plate_number": plate_number, "invoice_count": 0, "total_amount": Decimal("0.00")},
            )
            summary["invoice_count"] = int(summary["invoice_count"]) + 1
            summary["total_amount"] = (summary["total_amount"] + invoice.total_amount).quantize(Decimal("0.01"))
        plate_summary = list(plate_totals.values())
        plate_summary.sort(key=lambda item: -int(item["invoice_count"]))
        return {
            "issue_start_date": issue_dates[0] if issue_dates else None,
            "issue_end_date": issue_dates[-1] if issue_dates else None,
            "passage_start_date": passage_dates[0] if passage_dates else None,
            "passage_end_date": passage_dates[-1] if passage_dates else None,
            "plate_summary": plate_summary,
        }

    def _batch_summary_payload(self, batch: EtcBatch) -> dict[str, object]:
        payload = {
            "id": batch.id,
            "etc_batch_id": batch.etc_batch_id,
            "source_type": getattr(batch, "source_type", "normal_oa_draft"),
            "status": batch.status,
            "invoice_count": batch.invoice_count,
            "total_amount": batch.total_amount,
            "issue_start_date": getattr(batch, "issue_start_date", None),
            "issue_end_date": getattr(batch, "issue_end_date", None),
            "passage_start_date": getattr(batch, "passage_start_date", None),
            "passage_end_date": getattr(batch, "passage_end_date", None),
            "linked_oa_row_id": getattr(batch, "linked_oa_row_id", None),
            "linked_oa_case_id": getattr(batch, "linked_oa_case_id", None),
            "amount_delta": getattr(batch, "amount_delta", None),
            "note": getattr(batch, "note", ""),
        }
        payload.update(self._batch_reconciliation_payload(batch))
        return payload

    def _batch_invoice_item_payload(self, invoice: EtcInvoice) -> dict[str, object]:
        return {
            "id": invoice.id,
            "invoice_number": invoice.invoice_number,
            "issue_date": invoice.issue_date,
            "passage_start_date": invoice.passage_start_date,
            "passage_end_date": invoice.passage_end_date,
            "plate_number": invoice.plate_number,
            "seller_name": invoice.seller_name,
            "buyer_name": invoice.buyer_name,
            "amount_without_tax": invoice.amount_without_tax,
            "tax_amount": invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "status": invoice.status,
            "has_pdf": self._stored_invoice_file_exists(invoice.pdf_file_path),
            "has_xml": self._stored_invoice_file_exists(invoice.xml_file_path),
        }

    def _batch_matches_status(self, batch: EtcBatch, status: str | None) -> bool:
        normalized = str(status or "").strip().lower()
        if not normalized:
            return True
        if normalized == "submitted":
            return batch.status == EtcBatchStatus.SUBMITTED_CONFIRMED.value
        if normalized == "unsubmitted":
            return batch.status != EtcBatchStatus.SUBMITTED_CONFIRMED.value
        return batch.status == normalized

    def _batch_matches_month(self, batch: EtcBatch, month: str | None) -> bool:
        normalized_month = str(month or "").strip()
        if not normalized_month:
            return True
        dates = [
            str(getattr(batch, "issue_start_date", "") or ""),
            str(getattr(batch, "issue_end_date", "") or ""),
            str(getattr(batch, "passage_start_date", "") or ""),
            str(getattr(batch, "passage_end_date", "") or ""),
        ]
        if any(date_value.startswith(normalized_month) for date_value in dates):
            return True
        for invoice_id in batch.invoice_ids:
            invoice = self._invoices.get(invoice_id)
            if invoice is None:
                continue
            if any(
                str(date_value or "").startswith(normalized_month)
                for date_value in (invoice.issue_date, invoice.passage_start_date, invoice.passage_end_date)
            ):
                return True
        return False

    def _batch_matches_plate(self, batch: EtcBatch, plate: str | None) -> bool:
        normalized_plate = str(plate or "").strip().lower()
        if not normalized_plate:
            return True
        for item in list(getattr(batch, "plate_summary", []) or []):
            if normalized_plate in str(item.get("plate_number", "")).lower():
                return True
        return False

    def _batch_matches_keyword(self, batch: EtcBatch, keyword: str | None) -> bool:
        normalized_keyword = str(keyword or "").strip().lower()
        if not normalized_keyword:
            return True
        fields = [
            batch.id,
            batch.etc_batch_id,
            getattr(batch, "linked_oa_row_id", "") or "",
            getattr(batch, "linked_oa_case_id", "") or "",
            getattr(batch, "note", "") or "",
        ]
        if any(normalized_keyword in str(field).lower() for field in fields):
            return True
        for invoice_id in batch.invoice_ids:
            invoice = self._invoices.get(invoice_id)
            if invoice is not None and self._invoice_matches_keyword(invoice, normalized_keyword):
                return True
        return False

    @staticmethod
    def _ensure_batch_metadata_fields(batch: EtcBatch) -> None:
        defaults = {
            "source_type": "normal_oa_draft",
            "linked_oa_row_id": None,
            "linked_oa_case_id": None,
            "amount_delta": None,
            "note": "",
            "issue_start_date": None,
            "issue_end_date": None,
            "passage_start_date": None,
            "passage_end_date": None,
            "plate_summary": [],
            "reconciliation_task_id": None,
            "statement_period_start": None,
            "statement_period_end": None,
            "oa_total_amount": None,
            "etc_invoice_amount": None,
            "supplement_amount": Decimal("0.00"),
            "etc_invoice_count": None,
            "supplement_count": 0,
            "supplement_items": [],
            "display_count_text": None,
        }
        for field_name, default_value in defaults.items():
            if not hasattr(batch, field_name):
                setattr(batch, field_name, list(default_value) if isinstance(default_value, list) else default_value)

    @staticmethod
    def _reconciliation_batch_metadata(reconciliation_task: object | None) -> dict[str, object]:
        if reconciliation_task is None:
            return {}
        oa_total_amount = _decimal_or_none(getattr(reconciliation_task, "oa_total_amount", None))
        if oa_total_amount is None:
            return {}
        etc_invoice_amount = _decimal_or_none(getattr(reconciliation_task, "etc_invoice_amount", None)) or Decimal("0.00")
        supplement_amount = _decimal_or_none(getattr(reconciliation_task, "supplement_amount", None)) or Decimal("0.00")
        supplement_items = []
        evidences_by_id = {
            str(getattr(evidence, "evidence_id", "")): evidence
            for evidence in list(getattr(reconciliation_task, "supplement_evidences", []) or [])
        }
        for attachment in list(getattr(reconciliation_task, "submission_supplement_attachments", []) or []):
            evidence = evidences_by_id.get(str(getattr(attachment, "evidence_id", "") or ""))
            supplement_items.append(
                {
                    "id": str(getattr(attachment, "evidence_id", "") or getattr(attachment, "attachment_id", "") or ""),
                    "sourceFileId": str(getattr(attachment, "source_file_id", "") or ""),
                    "sourceName": str(getattr(attachment, "original_name", "") or ""),
                    "storedPath": str(getattr(attachment, "stored_path", "") or ""),
                    "amount": _decimal_or_none(getattr(attachment, "amount", None)) or Decimal("0.00"),
                    "tags": list(getattr(attachment, "tags", []) or ["ETC补充凭证"]),
                    "evidenceKind": str(getattr(evidence, "evidence_kind", "") or "non_etc") if evidence is not None else "non_etc",
                    "merchantName": getattr(evidence, "merchant_name", None) if evidence is not None else None,
                    "paidAt": getattr(evidence, "paid_at", None) if evidence is not None else None,
                }
            )
        return {
            "reconciliation_task_id": str(getattr(reconciliation_task, "task_id", "") or ""),
            "period_start": getattr(reconciliation_task, "period_start", None),
            "period_end": getattr(reconciliation_task, "period_end", None),
            "statement_period_start": getattr(reconciliation_task, "statement_period_start", None),
            "statement_period_end": getattr(reconciliation_task, "statement_period_end", None),
            "oa_total_amount": oa_total_amount,
            "etc_invoice_amount": etc_invoice_amount,
            "supplement_amount": supplement_amount,
            "etc_invoice_count": int(getattr(reconciliation_task, "etc_invoice_count", 0) or 0),
            "supplement_count": int(getattr(reconciliation_task, "supplement_count", 0) or 0),
            "supplement_items": supplement_items,
        }

    @staticmethod
    def _batch_reconciliation_payload(batch: EtcBatch) -> dict[str, object]:
        task_id = str(getattr(batch, "reconciliation_task_id", "") or "").strip()
        if not task_id:
            return {}
        etc_invoice_count = int(getattr(batch, "etc_invoice_count", None) or getattr(batch, "invoice_count", 0) or 0)
        supplement_count = int(getattr(batch, "supplement_count", 0) or 0)
        return {
            "reconciliation_task_id": task_id,
            "statement_period_start": getattr(batch, "statement_period_start", None),
            "statement_period_end": getattr(batch, "statement_period_end", None),
            "oa_total_amount": getattr(batch, "oa_total_amount", None) or getattr(batch, "total_amount", Decimal("0.00")),
            "etc_invoice_amount": getattr(batch, "etc_invoice_amount", None) or getattr(batch, "total_amount", Decimal("0.00")),
            "supplement_amount": getattr(batch, "supplement_amount", Decimal("0.00")),
            "etc_invoice_count": etc_invoice_count,
            "supplement_count": supplement_count,
            "supplement_items": list(getattr(batch, "supplement_items", []) or []),
            "display_count_text": getattr(batch, "display_count_text", None)
            or f"ETC票 {etc_invoice_count} + 补充凭证 {supplement_count}",
        }

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
        if normalized_name in {_normalize_field_name(alias) for alias in ("RequestTime", "IssueTime", "开票时间")}:
            values.setdefault("issue_datetime", text)
        for field_name, aliases in FIELD_ALIASES.items():
            normalized_aliases = {_normalize_field_name(alias) for alias in aliases}
            if normalized_name in normalized_aliases and field_name not in values:
                values[field_name] = text
    invoice_number = _required_text(values, "invoice_number")
    raw_issue_date = _required_text(values, "issue_date")
    issue_date = _normalize_date(raw_issue_date)
    return ParsedEtcXml(
        invoice_number=invoice_number,
        issue_date=issue_date,
        issue_datetime=_normalize_datetime(values.get("issue_datetime") or raw_issue_date),
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


def _decimal_from_amount(value: Decimal | str | int | float) -> Decimal:
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", ""))
    except (InvalidOperation, ValueError) as exc:
        raise EtcInvoiceRequestError("amount must be a valid decimal.") from exc


def _decimal_or_none(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _normalize_date(value: str) -> str:
    text = value.strip()
    if len(text) >= 10 and re.match(r"^\d{4}[-/]\d{2}[-/]\d{2}", text):
        return text[:10].replace("/", "-")
    if len(text) >= 8 and re.match(r"^\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    if re.match(r"^\d{8}$", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]}"
    return text


def _normalize_datetime(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    normalized = text.replace("/", "-")
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}", normalized):
        return normalized[:19].replace("T", " ")
    if re.match(r"^\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}", normalized):
        return f"{normalized[:16].replace('T', ' ')}:00"
    if re.match(r"^\d{14}$", normalized):
        return f"{normalized[:4]}-{normalized[4:6]}-{normalized[6:8]} {normalized[8:10]}:{normalized[10:12]}:{normalized[12:14]}"
    return None


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

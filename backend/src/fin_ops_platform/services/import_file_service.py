from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from io import BytesIO
import re
from typing import Any
import warnings

from openpyxl import load_workbook
import xlrd

from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.domain.models import ImportedBatchRowResult
from fin_ops_platform.services.imports import ImportNormalizationService


DATE_ONLY_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})$")
DATE_TIME_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})$")
COMPACT_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
COMPACT_DATE_TIME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})[ T]?(\d{2})(\d{2})(\d{2})$")
COMPANY_TAX_NOS = {"91330106589876543T", "915300007194052520"}
COMPANY_NAME_KEYWORDS = ("杭州溯源科技有限公司", "云南溯源科技有限公司", "溯源科技有限公司")
TEMPLATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "template_code": "invoice_export",
        "label": "发票导出",
        "file_extensions": [".xlsx"],
        "record_type": "invoice",
        "allowed_batch_types": [BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value],
        "required_headers": ["发票代码", "发票号码", "销方识别号", "购买方名称", "开票日期", "金额", "税额"],
    },
    {
        "template_code": "icbc_historydetail",
        "label": "工商银行流水",
        "file_extensions": [".xlsx"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["[HISTORYDETAIL]", "凭证号", "交易时间", "对方单位", "对方账号", "转入金额", "转出金额"],
    },
    {
        "template_code": "ceb_transaction_detail",
        "label": "光大银行流水",
        "file_extensions": [".xls"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["交易日期", "交易时间", "借方发生额", "贷方发生额", "账户余额", "对方名称", "对方账号"],
    },
    {
        "template_code": "ccb_transaction_detail",
        "label": "建设银行流水",
        "file_extensions": [".xls"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["账号", "账户名称", "交易时间", "借方发生额（支取）", "贷方发生额（收入）", "对方户名"],
    },
    {
        "template_code": "cmbc_transaction_detail",
        "label": "民生银行流水",
        "file_extensions": [".xlsx"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["交易时间", "交易流水号", "借方发生额", "贷方发生额", "账户余额", "对方账号名称"],
    },
    {
        "template_code": "pingan_transaction_detail",
        "label": "平安银行流水",
        "file_extensions": [".xlsx"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["交易时间", "账号", "收入", "支出", "对方户名", "交易流水号", "核心唯一流水号"],
    },
]


@dataclass(slots=True)
class UploadedImportFile:
    file_name: str
    content: bytes
    template_code_override: str | None = None
    batch_type_override: str | None = None
    selected_bank_mapping_id: str | None = None
    selected_bank_name: str | None = None
    selected_bank_last4: str | None = None


@dataclass(slots=True)
class FileImportPreviewItem:
    id: str
    file_name: str
    template_code: str | None
    batch_type: BatchType | None
    status: str
    message: str
    row_count: int
    success_count: int = 0
    error_count: int = 0
    duplicate_count: int = 0
    suspected_duplicate_count: int = 0
    updated_count: int = 0
    preview_batch_id: str | None = None
    batch_id: str | None = None
    stored_file_path: str | None = None
    override_template_code: str | None = None
    override_batch_type: BatchType | None = None
    selected_bank_mapping_id: str | None = None
    selected_bank_name: str | None = None
    selected_bank_last4: str | None = None
    detected_bank_name: str | None = None
    detected_last4: str | None = None
    bank_selection_conflict: bool = False
    conflict_message: str | None = None
    row_results: list[ImportedBatchRowResult] = field(default_factory=list)
    normalized_rows: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class FileImportSession:
    id: str
    imported_by: str
    file_count: int
    status: str
    files: list[FileImportPreviewItem]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class ParsedImportFile:
    template_code: str
    batch_type: BatchType
    rows: list[dict[str, Any]]


class FileImportService:
    def __init__(self, import_service: ImportNormalizationService, *, file_store: Any | None = None) -> None:
        self._import_service = import_service
        self._session_counter = 0
        self._file_counter = 0
        self._sessions: dict[str, FileImportSession] = {}
        self._file_store = file_store

    @classmethod
    def from_snapshot(
        cls,
        import_service: ImportNormalizationService,
        snapshot: dict[str, Any] | None,
        *,
        file_store: Any | None = None,
    ) -> FileImportService:
        service = cls(import_service, file_store=file_store)
        if not snapshot:
            return service
        service._session_counter = int(snapshot.get("session_counter", 0))
        service._file_counter = int(snapshot.get("file_counter", 0))
        service._sessions = dict(snapshot.get("sessions", {}))
        return service

    def snapshot(self) -> dict[str, Any]:
        return {
            "session_counter": self._session_counter,
            "file_counter": self._file_counter,
            "sessions": self._sessions,
        }

    def list_templates(self) -> list[dict[str, Any]]:
        return [dict(template) for template in TEMPLATE_DEFINITIONS]

    def preview_files(self, *, imported_by: str, uploads: list[UploadedImportFile]) -> FileImportSession:
        session = FileImportSession(
            id=self._next_session_id(),
            imported_by=imported_by,
            file_count=len(uploads),
            status="preview_ready",
            files=[],
        )

        for upload in uploads:
            file_id = self._next_file_id()
            stored_file_path = self._store_upload_file(session.id, file_id, upload)
            file_item = self._preview_single_file(
                imported_by=imported_by,
                upload=upload,
                file_id=file_id,
                stored_file_path=stored_file_path,
                template_code_override=upload.template_code_override,
                batch_type_override=upload.batch_type_override,
                selected_bank_mapping_id=upload.selected_bank_mapping_id,
                selected_bank_name=upload.selected_bank_name,
                selected_bank_last4=upload.selected_bank_last4,
            )
            session.files.append(file_item)

        if any(file.status == "unrecognized_template" for file in session.files):
            session.status = "preview_ready_with_errors"

        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> FileImportSession:
        return self._sessions[session_id]

    def confirm_session(self, *, session_id: str, selected_file_ids: list[str]) -> FileImportSession:
        session = self._sessions[session_id]
        selected = set(selected_file_ids)
        known_ids = {item.id for item in session.files}
        unknown_ids = sorted(selected - known_ids)
        if unknown_ids:
            raise KeyError(f"Unknown selected file ids: {', '.join(unknown_ids)}")

        confirmed_any = False
        for item in session.files:
            if item.id not in selected:
                if item.status == "preview_ready":
                    item.status = "skipped"
                    item.batch_id = None
                continue
            if item.status == "confirmed":
                confirmed_any = True
                continue
            if not item.preview_batch_id:
                continue
            batch = self._import_service.confirm_import(item.preview_batch_id)
            item.batch_id = batch.id
            item.status = "confirmed"
            confirmed_any = True

        session.status = "confirmed" if confirmed_any else "skipped"
        self._sessions[session.id] = session
        return session

    def retry_session_files(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
        overrides: dict[str, dict[str, str]] | None = None,
    ) -> FileImportSession:
        session = self._sessions[session_id]
        override_map = overrides or {}
        selected = set(selected_file_ids)
        for item in session.files:
            if item.id not in selected:
                continue
            if item.status == "confirmed":
                raise ValueError("confirmed files cannot be retried directly")
            if not item.stored_file_path:
                raise ValueError("original upload file is missing")
            if self._file_store is None:
                raise ValueError("import file storage is not configured")
            upload = UploadedImportFile(
                file_name=item.file_name,
                content=self._file_store.read_import_file(item.stored_file_path),
                selected_bank_mapping_id=item.selected_bank_mapping_id,
                selected_bank_name=item.selected_bank_name,
                selected_bank_last4=item.selected_bank_last4,
            )
            override_payload = override_map.get(item.id, {})
            refreshed = self._preview_single_file(
                imported_by=session.imported_by,
                upload=upload,
                file_id=item.id,
                stored_file_path=item.stored_file_path,
                template_code_override=override_payload.get("template_code"),
                batch_type_override=override_payload.get("batch_type"),
                selected_bank_mapping_id=override_payload.get("bank_mapping_id") or item.selected_bank_mapping_id,
                selected_bank_name=override_payload.get("bank_name") or item.selected_bank_name,
                selected_bank_last4=override_payload.get("last4") or item.selected_bank_last4,
            )
            item.template_code = refreshed.template_code
            item.batch_type = refreshed.batch_type
            item.status = refreshed.status
            item.message = refreshed.message
            item.row_count = refreshed.row_count
            item.success_count = refreshed.success_count
            item.error_count = refreshed.error_count
            item.duplicate_count = refreshed.duplicate_count
            item.suspected_duplicate_count = refreshed.suspected_duplicate_count
            item.updated_count = refreshed.updated_count
            item.preview_batch_id = refreshed.preview_batch_id
            item.row_results = refreshed.row_results
            item.normalized_rows = refreshed.normalized_rows
            item.override_template_code = refreshed.override_template_code
            item.override_batch_type = refreshed.override_batch_type
            item.selected_bank_mapping_id = refreshed.selected_bank_mapping_id
            item.selected_bank_name = refreshed.selected_bank_name
            item.selected_bank_last4 = refreshed.selected_bank_last4
            item.detected_bank_name = refreshed.detected_bank_name
            item.detected_last4 = refreshed.detected_last4
            item.bank_selection_conflict = refreshed.bank_selection_conflict
            item.conflict_message = refreshed.conflict_message

        session.status = "preview_ready_with_errors" if any(
            file.status == "unrecognized_template" for file in session.files
        ) else "preview_ready"
        self._sessions[session.id] = session
        return session

    def mark_batch_reverted(self, batch_id: str) -> None:
        for session in self._sessions.values():
            for item in session.files:
                if item.batch_id == batch_id:
                    item.status = "reverted"
            if any(file.status == "reverted" for file in session.files):
                session.status = "reverted"

    def _preview_single_file(
        self,
        *,
        imported_by: str,
        upload: UploadedImportFile,
        file_id: str,
        stored_file_path: str | None,
        template_code_override: str | None = None,
        batch_type_override: str | None = None,
        selected_bank_mapping_id: str | None = None,
        selected_bank_name: str | None = None,
        selected_bank_last4: str | None = None,
    ) -> FileImportPreviewItem:
        try:
            rows = self._read_rows(upload)
            parsed = self._parse_rows(
                file_name=upload.file_name,
                rows=rows,
                template_code_override=template_code_override,
                batch_type_override=batch_type_override,
            )
        except ValueError as exc:
            return self._build_preview_error_item(
                file_id=file_id,
                upload=upload,
                stored_file_path=stored_file_path,
                message=str(exc),
                template_code_override=template_code_override,
                batch_type_override=batch_type_override,
                selected_bank_mapping_id=selected_bank_mapping_id,
                selected_bank_name=selected_bank_name,
                selected_bank_last4=selected_bank_last4,
            )
        except Exception:
            return self._build_preview_error_item(
                file_id=file_id,
                upload=upload,
                stored_file_path=stored_file_path,
                message="文件读取失败，请确认文件未损坏且为受支持的 Excel 模板。",
                template_code_override=template_code_override,
                batch_type_override=batch_type_override,
                selected_bank_mapping_id=selected_bank_mapping_id,
                selected_bank_name=selected_bank_name,
                selected_bank_last4=selected_bank_last4,
            )

        detected_bank_name, detected_last4 = self._detect_bank_selection(parsed)
        conflict_message = self._build_bank_selection_conflict_message(
            selected_bank_name=selected_bank_name,
            selected_bank_last4=selected_bank_last4,
            detected_bank_name=detected_bank_name,
            detected_last4=detected_last4,
        )
        bank_selection_conflict = bool(conflict_message)
        if parsed.batch_type == BatchType.BANK_TRANSACTION:
            for row in parsed.rows:
                row["selected_bank_mapping_id"] = selected_bank_mapping_id
                row["selected_bank_name"] = selected_bank_name
                row["selected_bank_last4"] = selected_bank_last4
                row["detected_bank_name"] = detected_bank_name
                row["detected_last4"] = detected_last4

        try:
            preview = self._import_service.preview_import(
                batch_type=parsed.batch_type,
                source_name=upload.file_name,
                imported_by=imported_by,
                rows=parsed.rows,
            )
        except Exception:
            return self._build_preview_error_item(
                file_id=file_id,
                upload=upload,
                stored_file_path=stored_file_path,
                message="文件预览失败，请检查字段格式后重试。",
                template_code_override=template_code_override,
                batch_type_override=batch_type_override,
                selected_bank_mapping_id=selected_bank_mapping_id,
                selected_bank_name=selected_bank_name,
                selected_bank_last4=selected_bank_last4,
            )
        return FileImportPreviewItem(
            id=file_id,
            file_name=upload.file_name,
            template_code=parsed.template_code,
            batch_type=parsed.batch_type,
            status="preview_ready",
            message="模板识别成功。",
            row_count=len(parsed.rows),
            success_count=preview.success_count,
            error_count=preview.error_count,
            duplicate_count=preview.duplicate_count,
            suspected_duplicate_count=preview.suspected_duplicate_count,
            updated_count=preview.updated_count,
            preview_batch_id=preview.id,
            stored_file_path=stored_file_path,
            override_template_code=template_code_override,
            override_batch_type=BatchType(batch_type_override) if batch_type_override else None,
            selected_bank_mapping_id=selected_bank_mapping_id,
            selected_bank_name=selected_bank_name,
            selected_bank_last4=selected_bank_last4,
            detected_bank_name=detected_bank_name,
            detected_last4=detected_last4,
            bank_selection_conflict=bank_selection_conflict,
            conflict_message=conflict_message,
            row_results=preview.row_results,
            normalized_rows=preview.normalized_rows,
        )

    @staticmethod
    def _build_preview_error_item(
        *,
        file_id: str,
        upload: UploadedImportFile,
        stored_file_path: str | None,
        message: str,
        template_code_override: str | None,
        batch_type_override: str | None,
        selected_bank_mapping_id: str | None,
        selected_bank_name: str | None,
        selected_bank_last4: str | None,
    ) -> FileImportPreviewItem:
        return FileImportPreviewItem(
            id=file_id,
            file_name=upload.file_name,
            template_code=None,
            batch_type=None,
            status="unrecognized_template",
            message=message,
            row_count=0,
            stored_file_path=stored_file_path,
            override_template_code=template_code_override,
            override_batch_type=BatchType(batch_type_override) if batch_type_override else None,
            selected_bank_mapping_id=selected_bank_mapping_id,
            selected_bank_name=selected_bank_name,
            selected_bank_last4=selected_bank_last4,
        )

    def _parse_rows(
        self,
        *,
        file_name: str,
        rows: list[list[str]],
        template_code_override: str | None = None,
        batch_type_override: str | None = None,
    ) -> ParsedImportFile:
        detector = TemplateDetector(rows)
        template_code = template_code_override or detector.detect()
        if template_code == "invoice_export":
            parsed_rows = parse_invoice_rows(rows)
            resolved_batch_type = self._resolve_invoice_batch_type(parsed_rows, batch_type_override)
            for parsed_row in parsed_rows:
                parsed_row["counterparty_name"] = (
                    parsed_row.get("buyer_name") if resolved_batch_type == BatchType.OUTPUT_INVOICE else parsed_row.get("seller_name")
                )
            return ParsedImportFile(
                template_code=template_code,
                batch_type=resolved_batch_type,
                rows=parsed_rows,
            )
        if template_code == "icbc_historydetail":
            return ParsedImportFile(
                template_code=template_code,
                batch_type=BatchType.BANK_TRANSACTION,
                rows=parse_icbc_rows(rows, file_name=file_name),
            )
        if template_code == "pingan_transaction_detail":
            return ParsedImportFile(
                template_code=template_code,
                batch_type=BatchType.BANK_TRANSACTION,
                rows=parse_pingan_rows(rows),
            )
        if template_code == "cmbc_transaction_detail":
            return ParsedImportFile(
                template_code=template_code,
                batch_type=BatchType.BANK_TRANSACTION,
                rows=parse_cmbc_rows(rows),
            )
        if template_code == "ccb_transaction_detail":
            return ParsedImportFile(
                template_code=template_code,
                batch_type=BatchType.BANK_TRANSACTION,
                rows=parse_ccb_rows(rows),
            )
        if template_code == "ceb_transaction_detail":
            return ParsedImportFile(
                template_code=template_code,
                batch_type=BatchType.BANK_TRANSACTION,
                rows=parse_ceb_rows(rows),
            )
        raise ValueError("无法识别文件模板。")

    @staticmethod
    def _read_rows(upload: UploadedImportFile) -> list[list[str]]:
        suffix = upload.file_name.lower().rsplit(".", 1)[-1] if "." in upload.file_name else ""
        if suffix == "xlsx":
            return read_xlsx_rows(upload.content)
        if suffix == "xls":
            return read_xls_rows(upload.content)
        raise ValueError("无法识别文件模板。")

    def _next_session_id(self) -> str:
        while True:
            self._session_counter += 1
            session_id = f"import_session_{self._session_counter:04d}"
            if session_id not in self._sessions and not self._file_store_has("import_session_exists", session_id):
                return session_id

    def _next_file_id(self) -> str:
        while True:
            self._file_counter += 1
            file_id = f"import_file_{self._file_counter:04d}"
            if not self._file_store_has("import_file_exists", file_id):
                return file_id

    def _resolve_invoice_batch_type(self, rows: list[dict[str, Any]], override: str | None) -> BatchType:
        if override:
            return BatchType(override)
        if not rows:
            return BatchType.INPUT_INVOICE
        input_votes = 0
        output_votes = 0
        for row in rows:
            if is_company_identity(row.get("buyer_tax_no"), row.get("buyer_name")) and not is_company_identity(
                row.get("seller_tax_no"),
                row.get("seller_name"),
            ):
                input_votes += 1
            elif is_company_identity(row.get("seller_tax_no"), row.get("seller_name")) and not is_company_identity(
                row.get("buyer_tax_no"),
                row.get("buyer_name"),
            ):
                output_votes += 1
        return BatchType.OUTPUT_INVOICE if output_votes > input_votes else BatchType.INPUT_INVOICE

    def _store_upload_file(self, session_id: str, file_id: str, upload: UploadedImportFile) -> str | None:
        if self._file_store is None:
            return None
        return self._file_store.store_import_file(
            session_id=session_id,
            file_id=file_id,
            file_name=upload.file_name,
            content=upload.content,
        )

    def _file_store_has(self, method_name: str, identifier: str) -> bool:
        checker = getattr(self._file_store, method_name, None)
        if not callable(checker):
            return False
        return bool(checker(identifier))

    @staticmethod
    def _detect_bank_selection(parsed: ParsedImportFile) -> tuple[str | None, str | None]:
        if parsed.batch_type != BatchType.BANK_TRANSACTION:
            return None, None
        detected_bank_name = {
            "icbc_historydetail": "工商银行",
            "pingan_transaction_detail": "平安银行",
            "cmbc_transaction_detail": "民生银行",
            "ccb_transaction_detail": "建设银行",
            "ceb_transaction_detail": "光大银行",
        }.get(parsed.template_code)
        detected_last4 = None
        for row in parsed.rows:
            account_no = clean(row.get("account_no"))
            if len(account_no) >= 4:
                detected_last4 = account_no[-4:]
                break
        return detected_bank_name, detected_last4

    @staticmethod
    def _build_bank_selection_conflict_message(
        *,
        selected_bank_name: str | None,
        selected_bank_last4: str | None,
        detected_bank_name: str | None,
        detected_last4: str | None,
    ) -> str | None:
        mismatches: list[str] = []
        if (
            selected_bank_name
            and detected_bank_name
            and FileImportService._normalize_bank_name_for_conflict(selected_bank_name)
            != FileImportService._normalize_bank_name_for_conflict(detected_bank_name)
        ):
            mismatches.append(f"银行选择为{selected_bank_name}，系统识别为{detected_bank_name}")
        if selected_bank_last4 and detected_last4 and selected_bank_last4 != detected_last4:
            mismatches.append(f"后四位选择为{selected_bank_last4}，系统识别为{detected_last4}")
        if not mismatches:
            return None
        return "；".join(mismatches)

    @staticmethod
    def _normalize_bank_name_for_conflict(bank_name: str) -> str:
        normalized = re.sub(r"\s+", "", str(bank_name or "").strip())
        return normalized.removesuffix("银行")


class TemplateDetector:
    def __init__(self, rows: list[list[str]]) -> None:
        self._rows = rows

    def detect(self) -> str:
        for row in self._rows:
            normalized = normalize_row(row)
            if not normalized:
                continue
            row_set = set(normalized)
            if {"发票代码", "发票号码", "销方识别号", "购买方名称", "开票日期", "金额", "税额"}.issubset(row_set):
                return "invoice_export"
            if "[HISTORYDETAIL]" in row_set:
                return "icbc_historydetail"
            if {"交易时间", "账号", "收入", "支出", "对方户名", "交易流水号", "核心唯一流水号"}.issubset(row_set):
                return "pingan_transaction_detail"
            if {"交易时间", "交易流水号", "借方发生额", "贷方发生额", "账户余额", "对方账号", "对方账号名称"}.issubset(
                row_set
            ):
                return "cmbc_transaction_detail"
            if {
                "账号",
                "账户名称",
                "交易时间",
                "借方发生额（支取）",
                "贷方发生额（收入）",
                "对方户名",
                "账户明细编号-交易流水号",
            }.issubset(row_set):
                return "ccb_transaction_detail"
            if {"交易日期", "交易时间", "借方发生额", "贷方发生额", "账户余额", "对方名称", "对方账号", "凭证号"}.issubset(
                row_set
            ):
                return "ceb_transaction_detail"
        raise ValueError("无法识别文件模板。")


def read_xlsx_rows(content: bytes) -> list[list[str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = load_workbook(BytesIO(content), data_only=True)
    sheet = workbook[workbook.sheetnames[0]]
    rows: list[list[str]] = []
    for excel_row in sheet.iter_rows(values_only=True):
        rows.append([stringify_cell(value) for value in excel_row])
    return rows


def read_xls_rows(content: bytes) -> list[list[str]]:
    workbook = xlrd.open_workbook(file_contents=content)
    sheet = workbook.sheet_by_index(0)
    rows: list[list[str]] = []
    for row_index in range(sheet.nrows):
        rows.append([stringify_cell(sheet.cell_value(row_index, column_index)) for column_index in range(sheet.ncols)])
    return rows


def parse_invoice_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_header_index(
        rows,
        {"发票代码", "发票号码", "销方识别号", "购买方名称", "开票日期", "金额", "税额"},
    )
    header = rows[header_index]
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        data_rows.append(
            {
                "invoice_code": mapped.get("发票代码"),
                "invoice_no": mapped.get("发票号码"),
                "digital_invoice_no": mapped.get("数电发票号码"),
                "seller_tax_no": mapped.get("销方识别号"),
                "seller_name": mapped.get("销方名称"),
                "buyer_tax_no": mapped.get("购方识别号"),
                "buyer_name": mapped.get("购买方名称"),
                "counterparty_name": mapped.get("销方名称"),
                "invoice_date": to_date_string(mapped.get("开票日期")),
                "tax_classification_code": mapped.get("税收分类编码"),
                "specific_business_type": mapped.get("特定业务类型"),
                "taxable_item_name": mapped.get("货物或应税劳务名称"),
                "specification_model": mapped.get("规格型号"),
                "unit": mapped.get("单位"),
                "quantity": mapped.get("数量"),
                "unit_price": mapped.get("单价"),
                "amount": mapped.get("金额"),
                "tax_rate": mapped.get("税率"),
                "tax_amount": mapped.get("税额"),
                "total_with_tax": mapped.get("价税合计"),
                "invoice_source": mapped.get("发票来源"),
                "invoice_kind": mapped.get("发票票种"),
                "invoice_status_from_source": mapped.get("发票状态"),
                "is_positive_invoice": mapped.get("是否正数发票"),
                "risk_level": mapped.get("发票风险等级"),
                "issuer": mapped.get("开票人"),
                "remark": mapped.get("备注"),
            }
        )
    return data_rows


def parse_icbc_rows(rows: list[list[str]], *, file_name: str) -> list[dict[str, Any]]:
    header_index = find_header_index(rows, {"凭证号", "交易时间", "对方单位", "对方账号", "转入金额", "转出金额", "摘要"})
    header = rows[header_index]
    account_no = derive_account_no_from_filename(file_name)
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        trade_time = normalize_datetime_string(mapped.get("交易时间"))
        data_rows.append(
            {
                "account_no": account_no,
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": to_date_string(mapped.get("交易时间")),
                "counterparty_name": mapped.get("对方单位") or mapped.get("对方行名") or "未知对手方",
                "counterparty_account_no": mapped.get("对方账号"),
                "counterparty_bank_name": mapped.get("对方行名"),
                "credit_amount": mapped.get("转入金额"),
                "debit_amount": mapped.get("转出金额"),
                "balance": mapped.get("余额"),
                "summary": mapped.get("摘要"),
                "remark": mapped.get("附言") or mapped.get("用途"),
                "voucher_no": mapped.get("凭证号"),
                "bank_serial_no": mapped.get("附言") or mapped.get("凭证号"),
                "currency": "CNY",
            }
        )
    return data_rows


def parse_pingan_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_header_index(rows, {"交易时间", "账号", "收入", "支出", "对方户名", "交易流水号", "核心唯一流水号"})
    header = rows[header_index]
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        trade_time = normalize_datetime_string(mapped.get("交易时间"))
        data_rows.append(
            {
                "account_no": mapped.get("账号"),
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": to_date_string(mapped.get("交易日期") or mapped.get("交易时间")),
                "counterparty_name": mapped.get("对方户名"),
                "counterparty_account_no": mapped.get("对方账号"),
                "counterparty_bank_name": mapped.get("对方账号开户行"),
                "credit_amount": mapped.get("收入"),
                "debit_amount": mapped.get("支出"),
                "balance": mapped.get("账户余额"),
                "summary": mapped.get("摘要"),
                "remark": mapped.get("交易用途"),
                "bank_serial_no": mapped.get("核心唯一流水号") or mapped.get("交易流水号"),
                "enterprise_serial_no": mapped.get("业务流水号"),
                "account_detail_no": mapped.get("交易流水号"),
                "currency": mapped.get("币种") or "CNY",
            }
        )
    return data_rows


def parse_cmbc_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_header_index(rows, {"交易时间", "交易流水号", "借方发生额", "贷方发生额", "账户余额", "对方账号", "对方账号名称"})
    header = rows[header_index]
    meta = extract_key_value_metadata(rows[:header_index])
    account_no = meta.get("账号")
    account_name = meta.get("账户名称")
    currency = meta.get("币种") or "CNY"
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        trade_time = normalize_datetime_string(mapped.get("交易时间"))
        data_rows.append(
            {
                "account_no": account_no,
                "account_name": account_name,
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": to_date_string(mapped.get("交易时间")),
                "counterparty_name": mapped.get("对方账号名称") or "未知对手方",
                "counterparty_account_no": mapped.get("对方账号"),
                "counterparty_bank_name": mapped.get("对方开户行"),
                "credit_amount": mapped.get("贷方发生额"),
                "debit_amount": mapped.get("借方发生额"),
                "balance": mapped.get("账户余额"),
                "summary": mapped.get("客户附言"),
                "remark": mapped.get("客户附言"),
                "voucher_no": mapped.get("凭证号"),
                "bank_serial_no": mapped.get("交易流水号"),
                "currency": currency,
            }
        )
    return data_rows


def parse_ccb_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_header_index(
        rows,
        {"账号", "账户名称", "交易时间", "借方发生额（支取）", "贷方发生额（收入）", "对方户名", "账户明细编号-交易流水号"},
    )
    header = rows[header_index]
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        trade_time = normalize_datetime_string(mapped.get("交易时间"))
        data_rows.append(
            {
                "account_no": mapped.get("账号"),
                "account_name": mapped.get("账户名称"),
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": to_date_string(mapped.get("记账日期") or mapped.get("交易时间")),
                "booked_date": to_date_string(mapped.get("记账日期")),
                "counterparty_name": mapped.get("对方户名") or "未知对手方",
                "counterparty_account_no": mapped.get("对方账号"),
                "counterparty_bank_name": mapped.get("对方开户机构"),
                "credit_amount": mapped.get("贷方发生额（收入）"),
                "debit_amount": mapped.get("借方发生额（支取）"),
                "balance": mapped.get("余额"),
                "summary": mapped.get("摘要"),
                "remark": mapped.get("备注"),
                "account_detail_no": mapped.get("账户明细编号-交易流水号"),
                "enterprise_serial_no": mapped.get("企业流水号"),
                "voucher_kind": mapped.get("凭证种类"),
                "voucher_no": mapped.get("凭证号"),
                "currency": mapped.get("币种") or "CNY",
            }
        )
    return data_rows


def parse_ceb_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_header_index(rows, {"交易日期", "交易时间", "借方发生额", "贷方发生额", "账户余额", "对方名称", "对方账号", "凭证号"})
    header = rows[header_index]
    meta = extract_key_value_metadata(rows[:header_index])
    account_no = meta.get("账号")
    account_name = meta.get("账户名称")
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        trade_time = normalize_datetime_string(f"{mapped.get('交易日期')} {mapped.get('交易时间')}")
        data_rows.append(
            {
                "account_no": account_no,
                "account_name": account_name,
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": to_date_string(mapped.get("交易日期")),
                "counterparty_name": mapped.get("对方名称") or "未知对手方",
                "counterparty_account_no": mapped.get("对方账号"),
                "counterparty_bank_name": mapped.get("对方银行"),
                "credit_amount": mapped.get("贷方发生额"),
                "debit_amount": mapped.get("借方发生额"),
                "balance": mapped.get("账户余额"),
                "summary": mapped.get("摘要"),
                "voucher_no": mapped.get("凭证号"),
                "bank_serial_no": mapped.get("流水号") or mapped.get("凭证号"),
                "currency": "CNY",
            }
        )
    return data_rows


def normalize_row(row: list[str]) -> list[str]:
    return [normalize_header(cell) for cell in row if clean(cell)]


def normalize_header(value: str) -> str:
    return clean(value).replace(" ", "")


def clean(value: Any) -> str:
    return str(value).strip() if value is not None else ""


def stringify_cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def find_header_index(rows: list[list[str]], required_headers: set[str]) -> int:
    normalized_required = {normalize_header(value) for value in required_headers}
    for index, row in enumerate(rows):
        normalized_row = set(normalize_row(row))
        if normalized_required.issubset(normalized_row):
            return index
    raise ValueError("无法识别文件模板。")


def row_to_dict(header: list[str], row: list[str]) -> dict[str, str]:
    payload: dict[str, str] = {}
    width = max(len(header), len(row))
    for index in range(width):
        key = header[index] if index < len(header) else ""
        if not clean(key):
            continue
        payload[clean(key)] = clean(row[index] if index < len(row) else "")
    return payload


def extract_key_value_metadata(rows: list[list[str]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in rows:
        if len(row) < 2:
            continue
        key = clean(row[0]).rstrip(":：")
        value = clean(row[1])
        if key:
            metadata[key] = value
    return metadata


def to_date_string(value: str | None) -> str | None:
    text = clean(value)
    if not text:
        return None
    for pattern in (DATE_ONLY_RE, DATE_TIME_RE, COMPACT_DATE_RE, COMPACT_DATE_TIME_RE):
        match = pattern.match(text)
        if not match:
            continue
        groups = match.groups()
        return f"{groups[0]}-{groups[1]}-{groups[2]}"
    try:
        return datetime.fromisoformat(text.replace("/", "-")).date().isoformat()
    except ValueError:
        return None


def normalize_datetime_string(value: str | None) -> str | None:
    text = clean(value)
    if not text:
        return None
    match = DATE_TIME_RE.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)} {match.group(4)}:{match.group(5)}:{match.group(6)}"
    match = COMPACT_DATE_TIME_RE.match(text)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)} {match.group(4)}:{match.group(5)}:{match.group(6)}"
    if COMPACT_DATE_RE.match(text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} 00:00:00"
    try:
        parsed = datetime.fromisoformat(text.replace("/", "-"))
    except ValueError:
        return text
    return parsed.strftime("%Y-%m-%d %H:%M:%S")


def derive_account_no_from_filename(file_name: str) -> str:
    digit_groups = re.findall(r"\d+", file_name)
    if not digit_groups:
        return file_name
    return digit_groups[-1]


def is_company_identity(tax_no: str | None, company_name: str | None) -> bool:
    normalized_tax_no = clean(tax_no).upper()
    normalized_name = clean(company_name)
    if normalized_tax_no and normalized_tax_no in COMPANY_TAX_NOS:
        return True
    return any(keyword in normalized_name for keyword in COMPANY_NAME_KEYWORDS)


def sanitize_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("._")
    return cleaned or "uploaded_file"

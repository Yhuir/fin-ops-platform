from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from copy import deepcopy
import hashlib
import re
from typing import Any, Callable
import unicodedata
import warnings

from openpyxl import load_workbook
import xlrd

from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.domain.models import ImportedBatchRowResult
from fin_ops_platform.services.import_preview_audit import (
    BankTransactionIdentityStrategy,
    ImportRecordIdentity,
    ImportPreviewAuditCounts,
    ImportPreviewFileAudit,
    ImportPreviewAuditRow,
    ImportPreviewDuplicateGroup,
    ImportPreviewSessionAudit,
    ImportPreviewStaleError,
    InvoiceIdentityStrategy,
    build_import_preview_session_audit,
)
from fin_ops_platform.services.imports import ImportNormalizationService


DATE_ONLY_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})$")
DATE_TIME_RE = re.compile(r"^(\d{4})[-/](\d{2})[-/](\d{2})[ T](\d{2}):(\d{2}):(\d{2})$")
COMPACT_DATE_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})$")
COMPACT_DATE_TIME_RE = re.compile(r"^(\d{4})(\d{2})(\d{2})[ T]?(\d{2})(\d{2})(\d{2})$")
COMPANY_TAX_NOS = {"91330106589876543T", "915300007194052520"}
COMPANY_NAME_KEYWORDS = ("云南溯源科技有限公司", "溯源科技有限公司")
ACCOUNT_METADATA_KEYWORDS = ("账号", "账户", "卡号")
BANK_TEXT_FIELD_LABELS = ("摘要", "备注", "用途", "交易用途", "客户附言", "附言")
INVOICE_REQUIRED_HEADERS = {"发票代码", "发票号码", "销方识别号", "购买方名称", "开票日期", "金额", "税额"}
INVOICE_HEADER_ALIASES = {
    "数电号码": "数电发票号码",
    "销方税号": "销方识别号",
    "销方企业名称": "销方名称",
    "购方税号": "购方识别号",
    "购方企业名称": "购买方名称",
    "商品名称": "货物或应税劳务名称",
    "规格": "规格型号",
    "发票类型": "发票票种",
}
TEMPLATE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "template_code": "invoice_export",
        "label": "发票导出",
        "file_extensions": [".xlsx"],
        "record_type": "invoice",
        "allowed_batch_types": [BatchType.INPUT_INVOICE.value, BatchType.OUTPUT_INVOICE.value],
        "required_headers": sorted(INVOICE_REQUIRED_HEADERS),
    },
    {
        "template_code": "bank_statement",
        "label": "银行流水",
        "file_extensions": [".xls", ".xlsx"],
        "record_type": "bank_transaction",
        "allowed_batch_types": [BatchType.BANK_TRANSACTION.value],
        "required_headers": ["交易日期或时间", "借方和贷方金额，或金额和收支方向"],
    },
]

BANK_FIELD_LABELS = {
    "account_no": "本方账号",
    "account_name": "本方户名",
    "trade_time": "交易时间",
    "txn_date": "交易日期",
    "txn_clock": "交易时刻",
    "debit_amount": "支出金额",
    "credit_amount": "收入金额",
    "amount": "交易金额",
    "direction": "收支方向",
    "balance": "账户余额",
    "counterparty_name": "对方名称",
    "counterparty_account_no": "对方账号",
    "counterparty_bank_name": "对方开户行",
    "summary": "摘要",
    "remark": "备注/用途",
    "bank_serial_no": "银行流水号",
    "account_detail_no": "账户明细编号",
    "enterprise_serial_no": "企业流水号",
    "voucher_kind": "凭证种类",
    "voucher_no": "凭证号",
    "currency": "币种",
    "booked_date": "记账日期",
}
BANK_FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "account_no": ("账号", "帐号", "客户账号", "查询账号", "本方账号", "账户号", "卡号"),
    "account_name": ("账户名称", "帐户名称", "户名", "本方户名", "客户名称"),
    "trade_time": ("交易时间", "交易日期时间", "交易日期及时间", "发生时间", "入账时间", "记账时间"),
    "txn_date": ("交易日期", "交易日", "日期"),
    "txn_clock": ("交易时刻", "交易时间点", "时间"),
    "debit_amount": (
        "借方发生额", "借方发生额支取", "借方发生额支出", "借方金额", "借方金额支出", "支出", "支出金额", "转出金额", "付出金额",
    ),
    "credit_amount": (
        "贷方发生额", "贷方发生额收入", "贷方金额", "贷方金额收入", "收入", "收入金额", "转入金额", "收款金额",
    ),
    "amount": ("交易金额", "发生额", "金额", "本次金额"),
    "direction": ("收支方向", "交易方向", "借贷标志", "收付标志", "收支标志", "借贷方向"),
    "balance": ("余额", "账户余额", "帐户余额", "交易后余额", "可用余额"),
    "counterparty_name": (
        "对方户名", "对方名称", "对方单位", "对方账号名称", "对手方名称", "对手方户名", "收付款人名称",
    ),
    "counterparty_account_no": ("对方账号", "对方账户", "对手方账号", "收付款人账号"),
    "counterparty_bank_name": ("对方开户行", "对方开户机构", "对方银行", "对方账号开户行", "对手方开户行", "对方行名"),
    "summary": ("摘要", "交易摘要"),
    "remark": ("备注", "用途", "交易用途", "客户附言", "附言"),
    "bank_serial_no": ("银行流水号", "交易流水号", "流水号", "核心唯一流水号", "银行交易流水号"),
    "account_detail_no": ("账户明细编号交易流水号", "账户明细编号", "明细编号"),
    "enterprise_serial_no": ("企业流水号", "业务流水号", "客户流水号"),
    "voucher_kind": ("凭证种类", "凭证类型"),
    "voucher_no": ("凭证号", "凭证号码"),
    "currency": ("币种", "货币种类"),
    "booked_date": ("记账日期", "入账日期", "账务日期"),
}
BANK_NAME_MARKERS = {
    "工商银行": ("中国工商银行", "工商银行", "[historydetail]"),
    "建设银行": ("中国建设银行", "建设银行"),
    "光大银行": ("中国光大银行", "光大银行"),
    "民生银行": ("中国民生银行", "民生银行"),
    "平安银行": ("平安银行", "核心唯一流水号"),
    "交通银行": ("交通银行",),
}


@dataclass(slots=True)
class UploadedImportFile:
    file_name: str
    content: bytes
    template_code_override: str | None = None
    batch_type_override: str | None = None
    selected_bank_mapping_id: str | None = None
    selected_bank_name: str | None = None
    selected_bank_short_name: str | None = None
    selected_bank_last4: str | None = None
    field_mapping: dict[str, str] = field(default_factory=dict)


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
    selected_bank_short_name: str | None = None
    selected_bank_last4: str | None = None
    detected_bank_name: str | None = None
    detected_last4: str | None = None
    bank_selection_conflict: bool = False
    conflict_message: str | None = None
    header_signature: str | None = None
    mapping_candidates: list[dict[str, str]] = field(default_factory=list)
    mapping_fields: list[dict[str, Any]] = field(default_factory=list)
    field_mapping: dict[str, str] = field(default_factory=dict)
    mapping_source: str | None = None
    row_results: list[ImportedBatchRowResult] = field(default_factory=list)
    normalized_rows: list[dict[str, Any]] = field(default_factory=list)
    audit: ImportPreviewAuditCounts = field(default_factory=ImportPreviewAuditCounts)


@dataclass(slots=True)
class FileImportSession:
    id: str
    imported_by: str
    file_count: int
    status: str
    files: list[FileImportPreviewItem]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    audit: ImportPreviewAuditCounts = field(default_factory=ImportPreviewAuditCounts)
    duplicate_groups: list[ImportPreviewDuplicateGroup] = field(default_factory=list)


@dataclass(slots=True)
class ParsedImportFile:
    template_code: str
    batch_type: BatchType
    rows: list[dict[str, Any]]
    detected_bank_name: str | None = None
    header_signature: str | None = None
    mapping_candidates: list[dict[str, str]] = field(default_factory=list)
    mapping_fields: list[dict[str, Any]] = field(default_factory=list)
    field_mapping: dict[str, str] = field(default_factory=dict)
    mapping_source: str | None = None


class BankStatementMappingRequired(ValueError):
    def __init__(
        self,
        message: str,
        *,
        header_signature: str | None = None,
        candidates: list[dict[str, str]] | None = None,
        mapping_fields: list[dict[str, Any]] | None = None,
        field_mapping: dict[str, str] | None = None,
        detected_bank_name: str | None = None,
    ) -> None:
        super().__init__(message)
        self.header_signature = header_signature
        self.candidates = list(candidates or [])
        self.mapping_fields = list(mapping_fields or [])
        self.field_mapping = dict(field_mapping or {})
        self.detected_bank_name = detected_bank_name


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

    def preview_session_persistence_payload(self, session_id: str) -> dict[str, Any]:
        session = self._sessions[session_id]
        batch_ids = [
            str(item.preview_batch_id).strip()
            for item in session.files
            if str(item.preview_batch_id or "").strip()
        ]
        return {
            "imports": self._import_service.persistence_snapshot_for_batches(
                batch_ids,
                include_facts=False,
            ),
            "file_imports": {
                "session_counter": self._session_counter,
                "file_counter": self._file_counter,
                "sessions": {session.id: session},
            },
        }

    def confirmed_session_persistence_payload(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
    ) -> dict[str, Any]:
        session = self._sessions[session_id]
        selected = {str(file_id).strip() for file_id in selected_file_ids if str(file_id).strip()}
        batch_ids = [
            str(item.batch_id).strip()
            for item in session.files
            if item.id in selected and item.status == "confirmed" and str(item.batch_id or "").strip()
        ]
        return {
            "imports": self._import_service.persistence_snapshot_for_batches(batch_ids),
            "file_imports": {
                "session_counter": self._session_counter,
                "file_counter": self._file_counter,
                "sessions": {session.id: session},
            },
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
                selected_bank_short_name=upload.selected_bank_short_name,
                selected_bank_last4=upload.selected_bank_last4,
                field_mapping=upload.field_mapping,
            )
            session.files.append(file_item)

        if any(file.status == "unrecognized_template" for file in session.files):
            session.status = "preview_ready_with_errors"

        self._refresh_session_audit(session)
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> FileImportSession:
        return self._sessions[session_id]

    def confirm_session(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
        progress_callback: Callable[[FileImportSession, int, int], None] | None = None,
    ) -> FileImportSession:
        session = self._sessions[session_id]
        selected = set(selected_file_ids)
        known_ids = {item.id for item in session.files}
        unknown_ids = sorted(selected - known_ids)
        if unknown_ids:
            raise KeyError(f"Unknown selected file ids: {', '.join(unknown_ids)}")

        confirmed_any = False
        selected_items = [item for item in session.files if item.id in selected]
        if any(item.status == "preview_ready" for item in selected_items):
            self.assert_session_preview_current(session_id=session_id)
        progress_total = len(selected_items)
        progress_current = 0
        rollback_session = deepcopy(session)
        try:
            for item in session.files:
                if item.id not in selected:
                    if item.status == "preview_ready":
                        item.status = "skipped"
                        item.batch_id = None
                    continue
                progress_current += 1
                if item.status == "confirmed":
                    confirmed_any = True
                    if progress_callback is not None:
                        progress_callback(session, progress_current, progress_total)
                    continue
                if not item.preview_batch_id:
                    if progress_callback is not None:
                        progress_callback(session, progress_current, progress_total)
                    continue
                batch = self._import_service.confirm_import(item.preview_batch_id)
                item.batch_id = batch.id
                item.status = "confirmed"
                confirmed_any = True
                if progress_callback is not None:
                    progress_callback(session, progress_current, progress_total)

            session.status = "confirmed" if confirmed_any else "skipped"
            self._sessions[session.id] = session
            return session
        except Exception:
            self._sessions[session.id] = rollback_session
            raise

    def assert_session_preview_current(self, *, session_id: str) -> None:
        session = self._sessions[session_id]
        current_audit = self._build_session_audit(session, refresh_existing=True)
        if current_audit.audit.stale_projection() != session.audit.stale_projection():
            raise ImportPreviewStaleError(preview=session.audit, current=current_audit.audit)

    def retry_session_files(
        self,
        *,
        session_id: str,
        selected_file_ids: list[str],
        overrides: dict[str, dict[str, Any]] | None = None,
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
                selected_bank_short_name=item.selected_bank_short_name,
                selected_bank_last4=item.selected_bank_last4,
                field_mapping=item.field_mapping,
            )
            override_payload = override_map.get(item.id, {})
            field_mapping = override_payload.get("field_mapping")
            if not isinstance(field_mapping, dict):
                field_mapping = item.field_mapping
            refreshed = self._preview_single_file(
                imported_by=session.imported_by,
                upload=upload,
                file_id=item.id,
                stored_file_path=item.stored_file_path,
                template_code_override=override_payload.get("template_code"),
                batch_type_override=override_payload.get("batch_type"),
                selected_bank_mapping_id=override_payload.get("bank_mapping_id") or item.selected_bank_mapping_id,
                selected_bank_name=override_payload.get("bank_name") or item.selected_bank_name,
                selected_bank_short_name=override_payload.get("bank_short_name") or item.selected_bank_short_name,
                selected_bank_last4=override_payload.get("last4") or item.selected_bank_last4,
                field_mapping={str(key): str(value) for key, value in field_mapping.items()},
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
            item.selected_bank_short_name = refreshed.selected_bank_short_name
            item.selected_bank_last4 = refreshed.selected_bank_last4
            item.detected_bank_name = refreshed.detected_bank_name
            item.detected_last4 = refreshed.detected_last4
            item.bank_selection_conflict = refreshed.bank_selection_conflict
            item.conflict_message = refreshed.conflict_message
            item.header_signature = refreshed.header_signature
            item.mapping_candidates = refreshed.mapping_candidates
            item.mapping_fields = refreshed.mapping_fields
            item.field_mapping = refreshed.field_mapping
            item.mapping_source = refreshed.mapping_source

        session.status = "preview_ready_with_errors" if any(
            file.status == "unrecognized_template" for file in session.files
        ) else "preview_ready"
        self._refresh_session_audit(session)
        self._sessions[session.id] = session
        return session

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
        selected_bank_short_name: str | None = None,
        selected_bank_last4: str | None = None,
        field_mapping: dict[str, str] | None = None,
    ) -> FileImportPreviewItem:
        try:
            rows = self._read_rows(upload)
            try:
                parsed = self._parse_rows(
                    rows=rows,
                    template_code_override=template_code_override,
                    batch_type_override=batch_type_override,
                    field_mapping=field_mapping,
                )
                if field_mapping and parsed.batch_type == BatchType.BANK_TRANSACTION:
                    parsed.mapping_source = "manual"
            except BankStatementMappingRequired as mapping_error:
                saved_mapping = self._saved_field_mapping(mapping_error.header_signature)
                if field_mapping or not saved_mapping:
                    return self._build_preview_error_item(
                        file_id=file_id,
                        upload=upload,
                        stored_file_path=stored_file_path,
                        message=str(mapping_error),
                        template_code_override=template_code_override,
                        batch_type_override=batch_type_override,
                        selected_bank_mapping_id=selected_bank_mapping_id,
                        selected_bank_name=selected_bank_name,
                        selected_bank_short_name=selected_bank_short_name,
                        selected_bank_last4=selected_bank_last4,
                        template_code="bank_statement",
                        batch_type=BatchType.BANK_TRANSACTION,
                        header_signature=mapping_error.header_signature,
                        mapping_candidates=mapping_error.candidates,
                        mapping_fields=mapping_error.mapping_fields,
                        field_mapping=mapping_error.field_mapping,
                        detected_bank_name=mapping_error.detected_bank_name,
                    )
                parsed = self._parse_rows(
                    rows=rows,
                    template_code_override="bank_statement",
                    batch_type_override=BatchType.BANK_TRANSACTION.value,
                    field_mapping=saved_mapping,
                )
                parsed.mapping_source = "saved"
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
                selected_bank_short_name=selected_bank_short_name,
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
                selected_bank_short_name=selected_bank_short_name,
                selected_bank_last4=selected_bank_last4,
            )

        detected_bank_name, detected_last4 = self._detect_bank_selection(parsed)
        conflict_message = self._build_bank_selection_conflict_message(
            selected_bank_name=selected_bank_name,
            selected_bank_short_name=selected_bank_short_name,
            selected_bank_last4=selected_bank_last4,
            detected_bank_name=detected_bank_name,
            detected_last4=detected_last4,
        )
        bank_selection_conflict = bool(conflict_message)
        if parsed.batch_type == BatchType.BANK_TRANSACTION:
            for row in parsed.rows:
                if not clean(row.get("account_no")) and (selected_bank_mapping_id or selected_bank_last4):
                    row["account_no"] = selected_bank_mapping_id or selected_bank_last4
                row["selected_bank_mapping_id"] = selected_bank_mapping_id
                row["selected_bank_name"] = selected_bank_name
                row["selected_bank_short_name"] = selected_bank_short_name
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
                selected_bank_short_name=selected_bank_short_name,
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
            selected_bank_short_name=selected_bank_short_name,
            selected_bank_last4=selected_bank_last4,
            detected_bank_name=detected_bank_name,
            detected_last4=detected_last4,
            bank_selection_conflict=bank_selection_conflict,
            conflict_message=conflict_message,
            header_signature=parsed.header_signature,
            mapping_candidates=parsed.mapping_candidates,
            mapping_fields=parsed.mapping_fields,
            field_mapping=parsed.field_mapping,
            mapping_source=parsed.mapping_source,
            row_results=preview.row_results,
            normalized_rows=preview.normalized_rows,
        )

    def _refresh_session_audit(self, session: FileImportSession) -> None:
        audit = self._build_session_audit(session, refresh_existing=False)
        session.audit = audit.audit
        session.duplicate_groups = audit.duplicate_groups
        file_audits = {file_audit.file_id: file_audit.audit for file_audit in audit.files}
        for item in session.files:
            item.audit = file_audits.get(item.id, ImportPreviewAuditCounts())

    def _build_session_audit(self, session: FileImportSession, *, refresh_existing: bool) -> ImportPreviewSessionAudit:
        rows: list[ImportPreviewAuditRow] = []
        for item in session.files:
            if item.batch_type is None:
                continue
            for row_result, normalized in zip(item.row_results, item.normalized_rows, strict=True):
                decision = row_result.decision
                linked_object_type = row_result.linked_object_type
                linked_object_id = row_result.linked_object_id
                if refresh_existing and row_result.decision != ImportDecision.ERROR:
                    decision, linked_object_type, linked_object_id = self._import_service.current_import_decision_for_normalized_row(
                        batch_type=item.batch_type,
                        normalized=normalized,
                    )
                identity = self._identity_for_row(row_result.source_record_type, normalized)
                rows.append(
                    ImportPreviewAuditRow(
                        file_id=item.id,
                        file_name=item.file_name,
                        row_no=row_result.row_no,
                        record_type=row_result.source_record_type,
                        identity_key=identity.identity_key,
                        identity_kind=identity.identity_kind,
                        decision=decision,
                        decision_reason=row_result.decision_reason,
                        linked_object_type=linked_object_type,
                        linked_object_id=linked_object_id,
                        **self._audit_row_display_fields(row_result.source_record_type, normalized),
                    )
                )
        audit = build_import_preview_session_audit(rows)
        existing_file_ids = {file_audit.file_id for file_audit in audit.files}
        for item in session.files:
            if item.id not in existing_file_ids:
                audit.files.append(self._empty_file_audit(item))
        return audit

    @staticmethod
    def _empty_file_audit(item: FileImportPreviewItem) -> ImportPreviewFileAudit:
        return ImportPreviewFileAudit(
            file_id=item.id,
            file_name=item.file_name,
            audit=ImportPreviewAuditCounts(error_count=item.error_count),
        )

    @staticmethod
    def _identity_for_row(record_type: str, normalized: dict[str, Any]) -> ImportRecordIdentity:
        if record_type == "bank_transaction":
            return BankTransactionIdentityStrategy().identify(normalized)
        return InvoiceIdentityStrategy().identify(normalized)

    @staticmethod
    def _audit_row_display_fields(record_type: str, normalized: dict[str, Any]) -> dict[str, str | None]:
        if record_type != "bank_transaction":
            return {}
        return {
            "account_no": normalized.get("account_no"),
            "trade_time": normalized.get("trade_time") or normalized.get("pay_receive_time") or normalized.get("txn_date"),
            "direction": normalized.get("txn_direction") or normalized.get("direction"),
            "amount": normalized.get("amount"),
            "counterparty_name": normalized.get("counterparty_name_raw") or normalized.get("counterparty_name"),
        }

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
        selected_bank_short_name: str | None,
        selected_bank_last4: str | None,
        template_code: str | None = None,
        batch_type: BatchType | None = None,
        header_signature: str | None = None,
        mapping_candidates: list[dict[str, str]] | None = None,
        mapping_fields: list[dict[str, Any]] | None = None,
        field_mapping: dict[str, str] | None = None,
        detected_bank_name: str | None = None,
    ) -> FileImportPreviewItem:
        return FileImportPreviewItem(
            id=file_id,
            file_name=upload.file_name,
            template_code=template_code,
            batch_type=batch_type,
            status="unrecognized_template",
            message=message,
            row_count=0,
            stored_file_path=stored_file_path,
            override_template_code=template_code_override,
            override_batch_type=BatchType(batch_type_override) if batch_type_override else None,
            selected_bank_mapping_id=selected_bank_mapping_id,
            selected_bank_name=selected_bank_name,
            selected_bank_short_name=selected_bank_short_name,
            selected_bank_last4=selected_bank_last4,
            detected_bank_name=detected_bank_name,
            header_signature=header_signature,
            mapping_candidates=list(mapping_candidates or []),
            mapping_fields=list(mapping_fields or []),
            field_mapping=dict(field_mapping or {}),
        )

    def _parse_rows(
        self,
        *,
        rows: list[list[str]],
        template_code_override: str | None = None,
        batch_type_override: str | None = None,
        field_mapping: dict[str, str] | None = None,
    ) -> ParsedImportFile:
        template_code = template_code_override
        if not template_code:
            try:
                template_code = detect_invoice_template(rows)
            except ValueError:
                template_code = "bank_statement"
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
        if template_code == "bank_statement" or batch_type_override == BatchType.BANK_TRANSACTION.value:
            return parse_bank_statement_rows(rows, field_mapping=field_mapping)
        raise ValueError("无法识别文件模板。")

    def _saved_field_mapping(self, header_signature: str | None) -> dict[str, str]:
        if not header_signature:
            return {}
        for session in reversed(list(self._sessions.values())):
            for item in reversed(session.files):
                if item.header_signature == header_signature and item.field_mapping and item.mapping_source in {"manual", "saved"}:
                    return dict(item.field_mapping)
        return {}

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
        detected_bank_name = parsed.detected_bank_name
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
        selected_bank_short_name: str | None,
        selected_bank_last4: str | None,
        detected_bank_name: str | None,
        detected_last4: str | None,
    ) -> str | None:
        mismatches: list[str] = []
        selected_bank_aliases = {
            normalized
            for raw_name in (selected_bank_name, selected_bank_short_name)
            if (normalized := FileImportService._normalize_bank_name_for_conflict(raw_name or ""))
        }
        detected_bank_alias = FileImportService._normalize_bank_name_for_conflict(detected_bank_name or "")
        if (
            selected_bank_aliases
            and detected_bank_alias
            and not any(
                FileImportService._bank_name_alias_matches(selected_alias, detected_bank_alias)
                for selected_alias in selected_bank_aliases
            )
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

    @staticmethod
    def _bank_name_alias_matches(selected_alias: str, detected_alias: str) -> bool:
        return selected_alias == detected_alias or selected_alias in detected_alias or detected_alias in selected_alias


def detect_invoice_template(rows: list[list[str]]) -> str:
    find_invoice_header_index(rows)
    return "invoice_export"


def read_xlsx_rows(content: bytes) -> list[list[str]]:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        workbook = load_workbook(BytesIO(content), data_only=True)
    sheet = _select_template_sheet(workbook)
    return _worksheet_rows(sheet)


def _select_template_sheet(workbook: Any) -> Any:
    first_sheet = workbook[workbook.sheetnames[0]]
    for sheet in workbook.worksheets:
        rows = _worksheet_rows(sheet)
        try:
            detect_invoice_template(rows)
            return sheet
        except ValueError:
            if find_bank_header_candidate(rows) is not None:
                return sheet
    return first_sheet


def _worksheet_rows(sheet: Any) -> list[list[str]]:
    rows: list[list[str]] = []
    for excel_row in sheet.iter_rows(values_only=True):
        rows.append([stringify_cell(value) for value in excel_row])
    return rows


def read_xls_rows(content: bytes) -> list[list[str]]:
    workbook = xlrd.open_workbook(file_contents=content)
    first_rows: list[list[str]] = []
    for sheet_index in range(workbook.nsheets):
        sheet = workbook.sheet_by_index(sheet_index)
        rows = [
            [stringify_cell(sheet.cell_value(row_index, column_index)) for column_index in range(sheet.ncols)]
            for row_index in range(sheet.nrows)
        ]
        if sheet_index == 0:
            first_rows = rows
        try:
            detect_invoice_template(rows)
            return rows
        except ValueError:
            if find_bank_header_candidate(rows) is not None:
                return rows
    return first_rows


def parse_invoice_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    header_index = find_invoice_header_index(rows)
    header = [canonical_invoice_header(cell) for cell in rows[header_index]]
    data_rows = []
    for row in rows[header_index + 1 :]:
        mapped = row_to_dict(header, row)
        if not any(mapped.values()):
            continue
        if is_invoice_summary_footer(mapped):
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
    return aggregate_invoice_line_rows(data_rows)


def aggregate_invoice_line_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    order: list[tuple[str, ...]] = []
    for index, row in enumerate(rows):
        digital_no = clean(row.get("digital_invoice_no"))
        invoice_code = clean(row.get("invoice_code"))
        invoice_no = clean(row.get("invoice_no"))
        identity = (
            ("digital", digital_no)
            if digital_no
            else ("code_no", invoice_code, invoice_no)
            if invoice_code and invoice_no
            else ("row", str(index))
        )
        if identity not in grouped:
            grouped[identity] = []
            order.append(identity)
        grouped[identity].append(row)

    aggregated: list[dict[str, Any]] = []
    for identity in order:
        line_rows = grouped[identity]
        if len(line_rows) == 1:
            aggregated.append(line_rows[0])
            continue
        line_signatures = [_invoice_line_signature(row) for row in line_rows]
        if len(set(line_signatures)) == 1:
            aggregated.extend(line_rows)
            continue
        if len(set(line_signatures)) != len(line_signatures):
            raise ValueError("同一发票同时包含重复行和不同明细行，无法安全判断合计金额。")
        for field_name in (
            "digital_invoice_no",
            "invoice_code",
            "invoice_no",
            "seller_tax_no",
            "seller_name",
            "buyer_tax_no",
            "buyer_name",
            "invoice_date",
            "invoice_status_from_source",
        ):
            values = {clean(row.get(field_name)) for row in line_rows if clean(row.get(field_name))}
            if len(values) > 1:
                raise ValueError(f"同一发票的 {field_name} 不一致，无法安全合并明细行。")
        try:
            amount = sum((_invoice_line_decimal(row.get("amount")) for row in line_rows), Decimal("0"))
            tax_amount = sum((_invoice_line_decimal(row.get("tax_amount")) for row in line_rows), Decimal("0"))
            total_with_tax = sum(
                (_invoice_line_decimal(row.get("total_with_tax")) for row in line_rows),
                Decimal("0"),
            )
        except InvalidOperation:
            aggregated.extend(line_rows)
            continue
        merged = dict(line_rows[0])
        merged.update(
            {
                "amount": _invoice_line_decimal_text(amount),
                "tax_amount": _invoice_line_decimal_text(tax_amount),
                "total_with_tax": _invoice_line_decimal_text(total_with_tax),
                "source_line_count": len(line_rows),
                "source_line_items": [dict(row) for row in line_rows],
            }
        )
        tax_rates = {clean(row.get("tax_rate")) for row in line_rows if clean(row.get("tax_rate"))}
        merged["tax_rate"] = next(iter(tax_rates)) if len(tax_rates) == 1 else "mixed"
        aggregated.append(merged)
    return aggregated


def _invoice_line_decimal(value: Any) -> Decimal:
    text = clean(value).replace(",", "")
    if not text:
        return Decimal("0")
    return Decimal(text)


def _invoice_line_decimal_text(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.01")), "f")


def _invoice_line_signature(row: dict[str, Any]) -> tuple[str, ...]:
    return tuple(
        clean(row.get(field_name))
        for field_name in (
            "tax_classification_code",
            "taxable_item_name",
            "specification_model",
            "unit",
            "quantity",
            "unit_price",
            "amount",
            "tax_rate",
            "tax_amount",
            "total_with_tax",
        )
    )


def is_invoice_summary_footer(mapped: dict[str, str]) -> bool:
    invoice_kind = clean(mapped.get("发票票种"))
    return invoice_kind.startswith("份数：") and not any(
        clean(mapped.get(key)) for key in ("数电发票号码", "发票代码", "发票号码", "开票日期", "金额", "税额")
    )


@dataclass(slots=True)
class BankHeaderCandidate:
    index: int
    headers: list[str]
    candidates: list[dict[str, str]]
    automatic_mapping: dict[str, str]
    signature: str


def normalize_bank_header(value: Any) -> str:
    text = unicodedata.normalize("NFKC", str(value).strip() if value is not None else "").lower()
    text = text.replace("帐号", "账号").replace("帐户", "账户")
    text = re.sub(r"人民币|rmb|cny|/元|\(元\)|元", "", text)
    return re.sub(r"[\s/\\()\[\]{}<>:：_\-—]+", "", text)


_BANK_ALIAS_LOOKUP = {
    normalize_bank_header(alias): field_name
    for field_name, aliases in BANK_FIELD_ALIASES.items()
    for alias in aliases
}


def find_bank_header_candidate(rows: list[list[str]]) -> BankHeaderCandidate | None:
    best: tuple[int, BankHeaderCandidate] | None = None
    for index, row in enumerate(rows[:60]):
        headers = [clean(cell) for cell in row]
        populated = [(column, header) for column, header in enumerate(headers) if header]
        if len(populated) < 3:
            continue
        resolved: dict[str, list[int]] = {}
        keyword_count = 0
        for column, header in populated:
            normalized = normalize_bank_header(header)
            field_name = _BANK_ALIAS_LOOKUP.get(normalized)
            if field_name:
                resolved.setdefault(field_name, []).append(column)
            if re.search(r"时间|日期|金额|余额|对方|账号|户名|摘要|备注|流水|凭证|收支|借方|贷方", header):
                keyword_count += 1
        automatic_mapping = {
            field_name: str(columns[0])
            for field_name, columns in resolved.items()
            if len(columns) == 1
        }
        next_row = rows[index + 1] if index + 1 < len(rows) else []
        data_score = sum(
            1
            for value in next_row
            if re.search(r"\d{4}[-/]?\d{2}[-/]?\d{2}|^-?[\d,]+(?:\.\d+)?$", clean(value))
        )
        score = len(automatic_mapping) * 10 + keyword_count + min(data_score, 5)
        if score < 5:
            continue
        candidates = [
            {"key": str(column), "label": f"第{column + 1}列 · {header}"}
            for column, header in populated
        ]
        signature_source = "|".join(normalize_bank_header(header) for header in headers)
        candidate = BankHeaderCandidate(
            index=index,
            headers=headers,
            candidates=candidates,
            automatic_mapping=automatic_mapping,
            signature=hashlib.sha256(signature_source.encode("utf-8")).hexdigest()[:24],
        )
        if best is None or score > best[0]:
            best = (score, candidate)
    return best[1] if best else None


def parse_bank_statement_rows(
    rows: list[list[str]],
    *,
    field_mapping: dict[str, str] | None = None,
) -> ParsedImportFile:
    candidate = find_bank_header_candidate(rows)
    if candidate is None:
        raise ValueError("无法识别银行流水表头，请确认文件包含交易明细。")
    mapping = dict(candidate.automatic_mapping)
    for field_name, raw_column in dict(field_mapping or {}).items():
        if field_name not in BANK_FIELD_LABELS or not str(raw_column).isdigit():
            raise ValueError("字段映射无效，请重新选择源列。")
        column = int(raw_column)
        if column < 0 or column >= len(candidate.headers) or not candidate.headers[column]:
            raise ValueError("字段映射中的源列不存在，请重新选择。")
        mapping[field_name] = str(column)

    mapping_fields = _bank_mapping_fields(mapping)
    missing = _missing_bank_core_fields(mapping)
    detected_bank_name = detect_bank_name(rows, header_index=candidate.index)
    if missing:
        raise BankStatementMappingRequired(
            f"需要补充字段映射：{'、'.join(missing)}。",
            header_signature=candidate.signature,
            candidates=candidate.candidates,
            mapping_fields=mapping_fields,
            field_mapping=mapping,
            detected_bank_name=detected_bank_name,
        )

    header = candidate.headers
    metadata = extract_key_value_metadata(rows[: candidate.index])
    metadata_account_no = extract_account_no_from_metadata(rows[: candidate.index])
    metadata_account_name = first_metadata_value(metadata, "账户名称", "帐户名称", "户名")
    metadata_currency = first_metadata_value(metadata, "币种", "货币种类") or "CNY"
    parsed_rows: list[dict[str, Any]] = []
    for row in rows[candidate.index + 1 :]:
        if not any(clean(cell) for cell in row):
            continue

        def cell(field_name: str) -> str | None:
            raw_index = mapping.get(field_name)
            if raw_index is None:
                return None
            column = int(raw_index)
            return clean(row[column] if column < len(row) else "") or None

        raw_trade_time = cell("trade_time")
        raw_txn_date = cell("txn_date") or cell("booked_date")
        raw_txn_clock = cell("txn_clock")
        if raw_trade_time and to_date_string(raw_trade_time) is None and raw_txn_date:
            raw_trade_time = f"{raw_txn_date} {raw_trade_time}"
        elif not raw_trade_time and raw_txn_date:
            raw_trade_time = f"{raw_txn_date} {raw_txn_clock or '00:00:00'}"
        txn_date = to_date_string(raw_txn_date or raw_trade_time)
        if not txn_date:
            continue
        trade_time = normalize_datetime_string(raw_trade_time)
        debit_amount, credit_amount = normalize_signed_debit_credit_columns(
            cell("debit_amount"),
            cell("credit_amount"),
        )
        if not debit_amount and not credit_amount:
            debit_amount, credit_amount = split_amount_by_direction(cell("amount"), cell("direction"))
        account_detail_no = cell("account_detail_no")
        voucher_no = cell("voucher_no")
        remark = cell("remark")
        parsed_rows.append(
            {
                "account_no": cell("account_no") or metadata_account_no,
                "account_name": cell("account_name") or metadata_account_name,
                "trade_time": trade_time,
                "pay_receive_time": trade_time,
                "txn_date": txn_date,
                "booked_date": to_date_string(cell("booked_date")),
                "counterparty_name": cell("counterparty_name") or "未知对手方",
                "counterparty_account_no": cell("counterparty_account_no"),
                "counterparty_bank_name": cell("counterparty_bank_name"),
                "credit_amount": credit_amount,
                "debit_amount": debit_amount,
                "balance": cell("balance"),
                "summary": cell("summary"),
                "remark": remark,
                "bank_text_fields": extract_bank_text_fields_from_row(header, row),
                "bank_serial_no": cell("bank_serial_no") or account_detail_no or voucher_no or remark,
                "account_detail_no": account_detail_no,
                "enterprise_serial_no": cell("enterprise_serial_no"),
                "voucher_kind": cell("voucher_kind"),
                "voucher_no": voucher_no,
                "currency": cell("currency") or metadata_currency,
            }
        )
    if not parsed_rows:
        raise ValueError("未找到可导入的银行交易明细。")
    return ParsedImportFile(
        template_code="bank_statement",
        batch_type=BatchType.BANK_TRANSACTION,
        rows=parsed_rows,
        detected_bank_name=detected_bank_name,
        header_signature=candidate.signature,
        mapping_candidates=candidate.candidates,
        mapping_fields=mapping_fields,
        field_mapping=mapping,
        mapping_source="manual" if field_mapping else "auto",
    )


def _bank_mapping_fields(mapping: dict[str, str]) -> list[dict[str, Any]]:
    return [
        {
            "key": field_name,
            "label": label,
            "selected": mapping.get(field_name),
            "required": field_name in {"trade_time", "txn_date", "debit_amount", "credit_amount", "amount", "direction"},
        }
        for field_name, label in BANK_FIELD_LABELS.items()
    ]


def _missing_bank_core_fields(mapping: dict[str, str]) -> list[str]:
    missing: list[str] = []
    if not ({"trade_time", "txn_date"} & mapping.keys()):
        missing.append("交易日期或时间")
    has_split_amount = {"debit_amount", "credit_amount"}.issubset(mapping)
    has_directed_amount = {"amount", "direction"}.issubset(mapping)
    if not has_split_amount and not has_directed_amount:
        missing.append("借方和贷方金额，或金额和收支方向")
    return missing


def detect_bank_name(rows: list[list[str]], *, header_index: int | None = None) -> str | None:
    limit = min((header_index + 1) if header_index is not None else 20, 20)
    sample = " ".join(clean(cell).lower() for row in rows[:limit] for cell in row if clean(cell))
    for bank_name, markers in BANK_NAME_MARKERS.items():
        if any(marker.lower() in sample for marker in markers):
            return bank_name
    normalized = normalize_bank_header(sample)
    structural_markers = (
        ("工商银行", ("historydetail",)),
        ("平安银行", ("核心唯一流水号",)),
        ("民生银行", ("对方账号名称", "交易流水号")),
        ("建设银行", ("账户明细编号交易流水号",)),
        ("交通银行", ("查询账号", "借方发生额支出", "贷方发生额收入")),
    )
    for bank_name, markers in structural_markers:
        if all(normalize_bank_header(marker) in normalized for marker in markers):
            return bank_name
    return None


def split_amount_by_direction(amount: str | None, direction: str | None) -> tuple[str | None, str | None]:
    amount_text = clean(amount)
    direction_text = clean(direction).lower()
    if not amount_text:
        return None, None
    if any(marker in direction_text for marker in ("支", "出", "借", "付", "debit")):
        return amount_text.lstrip("-"), None
    if any(marker in direction_text for marker in ("收", "入", "贷", "credit")):
        return None, amount_text.lstrip("-")
    return None, None


def first_metadata_value(metadata: dict[str, str], *keys: str) -> str | None:
    normalized = {normalize_bank_header(key): value for key, value in metadata.items()}
    for key in keys:
        value = clean(normalized.get(normalize_bank_header(key)))
        if value:
            return value
    return None


def extract_bank_text_fields_from_row(header: list[str], row: list[str]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    normalized_header = [normalize_bank_header(label) for label in header]
    for label in BANK_TEXT_FIELD_LABELS:
        normalized_label = normalize_bank_header(label)
        for index, header_label in enumerate(normalized_header):
            if header_label != normalized_label:
                continue
            value = clean(row[index] if index < len(row) else "")
            if value:
                fields.append({"label": clean(header[index]), "value": value})
            break
    return fields


def normalize_row(row: list[str]) -> list[str]:
    return [normalize_header(cell) for cell in row if clean(cell)]


def normalize_header(value: str) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", clean(value)))


def canonical_invoice_header(value: str) -> str:
    normalized = normalize_header(value)
    return INVOICE_HEADER_ALIASES.get(normalized, normalized)


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


def find_invoice_header_index(rows: list[list[str]]) -> int:
    for index, row in enumerate(rows):
        normalized_row = {canonical_invoice_header(cell) for cell in normalize_row(row)}
        if INVOICE_REQUIRED_HEADERS.issubset(normalized_row):
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


def normalize_signed_debit_credit_columns(debit_amount: str | None, credit_amount: str | None) -> tuple[str | None, str | None]:
    debit_text = clean(debit_amount)
    credit_text = clean(credit_amount)
    if debit_text.startswith("-") and not credit_text:
        return None, debit_text[1:].strip()
    if credit_text.startswith("-") and not debit_text:
        return credit_text[1:].strip(), None
    return debit_amount, credit_amount


def extract_key_value_metadata(rows: list[list[str]]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    for row in rows:
        for cell in row:
            text = clean(cell)
            if "：" in text:
                key, value = text.split("：", 1)
            elif ":" in text:
                key, value = text.split(":", 1)
            else:
                continue
            normalized_key = clean(key)
            normalized_value = clean(value)
            if normalized_key and normalized_value:
                metadata[normalized_key] = normalized_value
        for index in range(0, len(row) - 1, 2):
            key = clean(row[index]).rstrip(":：")
            value = clean(row[index + 1])
            if key and value:
                metadata[key] = value
    return metadata


def extract_account_no_from_metadata(rows: list[list[str]]) -> str | None:
    metadata = extract_key_value_metadata(rows)
    for key, value in metadata.items():
        if is_account_no_key(key):
            account_no = normalize_account_no(value)
            if account_no:
                return account_no
    return None


def is_account_no_key(key: str) -> bool:
    normalized_key = normalize_header(key)
    if not any(keyword in normalized_key for keyword in ACCOUNT_METADATA_KEYWORDS):
        return False
    return not any(excluded in normalized_key for excluded in ("对方", "户名", "名称", "开户", "余额"))


def normalize_account_no(value: Any) -> str | None:
    digits = re.sub(r"\D+", "", clean(value))
    return digits if len(digits) >= 4 else None


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


def is_company_identity(tax_no: str | None, company_name: str | None) -> bool:
    normalized_tax_no = clean(tax_no).upper()
    normalized_name = clean(company_name)
    if normalized_tax_no and normalized_tax_no in COMPANY_TAX_NOS:
        return True
    return any(keyword in normalized_name for keyword in COMPANY_NAME_KEYWORDS)


def sanitize_file_name(file_name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", file_name).strip("._")
    return cleaned or "uploaded_file"

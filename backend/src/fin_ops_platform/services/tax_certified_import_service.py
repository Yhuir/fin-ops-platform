from __future__ import annotations

import re
import warnings
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any
from uuid import uuid4
from zipfile import BadZipFile
from xml.etree.ElementTree import ParseError

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException

from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy

OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()

MAX_IMPORT_RECORDS = 20_000
MAX_SHEET_ROWS = 50_000
MAX_SHEET_COLUMNS = 64

SOURCE_COLUMNS = {
    "序号": "sequence_no", "勾选状态": "selection_status", "发票来源": "invoice_source",
    "转内销证明编号": "domestic_sales_certificate_no", "数电发票号码": "digital_invoice_no",
    "发票代码": "invoice_code", "发票号码": "invoice_no", "开票日期": "issue_date",
    "销售方纳税人识别号": "seller_tax_no", "销售方纳税人名称": "seller_name",
    "金额": "amount", "税额": "tax_amount", "有效抵扣税额": "deductible_tax_amount",
    "票种": "invoice_kind", "票种标签": "invoice_kind_label", "发票状态": "invoice_status",
    "勾选时间": "selection_time", "发票风险等级": "risk_level", "风险状态": "risk_status",
}


@dataclass(slots=True)
class UploadedCertifiedImportFile:
    file_name: str
    content: bytes


@dataclass(slots=True)
class TaxCertifiedInvoiceRecord:
    id: str
    unique_key: str
    month: str | None
    source_file_name: str
    source_row_number: int
    taxpayer_tax_no: str | None = None
    taxpayer_name: str | None = None
    buyer_tax_no: str | None = None
    digital_invoice_no: str | None = None
    invoice_code: str | None = None
    invoice_no: str | None = None
    issue_date: str | None = None
    seller_tax_no: str | None = None
    seller_name: str | None = None
    amount: str | None = None
    tax_amount: str | None = None
    deductible_tax_amount: str | None = None
    selection_status: str | None = None
    invoice_status: str | None = None
    selection_time: str | None = None
    invoice_source: str | None = None
    invoice_kind: str | None = None
    invoice_kind_label: str | None = None
    risk_level: str | None = None
    risk_status: str | None = None
    domestic_sales_certificate_no: str | None = None
    source_fields: dict[str, Any] = field(default_factory=dict)
    batch_id: str | None = None
    match_status: str = "unresolved"
    matched_invoice_id: str | None = None
    status: str = "active"
    version: int = 1
    imported_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(slots=True)
class TaxCertifiedImportPreviewFile:
    id: str
    file_name: str
    month: str | None
    recognized_count: int
    invalid_count: int
    ignored_count: int
    rows: list[TaxCertifiedInvoiceRecord] = field(default_factory=list)
    row_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class TaxCertifiedImportSession:
    id: str
    imported_by: str
    file_count: int
    status: str
    files: list[TaxCertifiedImportPreviewFile]
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class TaxCertifiedImportService:
    """Parse source evidence; persist only targeted commands through its repository."""

    def __init__(self, *, repository: Any | None = None) -> None:
        self._repository = repository

    def preview_files(self, *, imported_by: str, uploads: list[UploadedCertifiedImportFile],
                      month: str | None = None, buyer_tax_no: str | None = None) -> TaxCertifiedImportSession:
        self._require_repository()
        if not uploads:
            raise ValueError("请选择认证文件。")
        if month is not None and not re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", month):
            raise ValueError("所属期格式必须为 YYYY-MM。")
        session = TaxCertifiedImportSession(
            id=f"tax-certified-session-{uuid4().hex}", imported_by=imported_by,
            file_count=len(uploads), status="preview_ready", files=[],
        )
        remaining_rows = MAX_IMPORT_RECORDS
        for upload in uploads:
            file = self._preview_single_file(upload, month=month, buyer_tax_no=buyer_tax_no, max_business_rows=remaining_rows)
            remaining_rows -= file.recognized_count + file.invalid_count + file.ignored_count
            session.files.append(file)
        self._repository.save_session(session)
        return session

    def _require_repository(self) -> Any:
        if self._repository is None:
            raise RuntimeError("认证导入仓库未配置。")
        return self._repository

    def session_owner(self, session_id: str) -> str:
        return self.get_session(session_id).imported_by

    def get_session(self, session_id: str) -> Any:
        return self._require_repository().get_session(session_id)

    def confirm_session(self, session_id: str, *, actor_id: str,
                        corrections: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        return self._require_repository().confirm_session(session_id, actor_id=actor_id, corrections=corrections or [])

    def records_payload(self, month: str | None = None, *, records_page: int = 1, batches_page: int = 1,
                        page_size: int = 20) -> dict[str, Any]:
        return self._require_repository().records_payload(month, records_page=records_page, batches_page=batches_page, page_size=page_size)

    def revoke_batch(self, batch_id: str, *, actor_id: str, expected_version: int) -> dict[str, Any]:
        return self._require_repository().revoke_batch(batch_id, actor_id=actor_id, expected_version=expected_version)

    def classify_rows(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return self._require_repository().classify_rows(rows)

    def _preview_single_file(self, upload: UploadedCertifiedImportFile, *, month: str | None = None,
                             buyer_tax_no: str | None = None, max_business_rows: int = MAX_IMPORT_RECORDS) -> TaxCertifiedImportPreviewFile:
        taxpayer, taxpayer_name, source_month, rows = self._read_template(upload, max_business_rows=max_business_rows)
        resolved_month = month or source_month
        if month and source_month and month != source_month:
            raise ValueError("指定所属期与文件所属期不一致。")
        if buyer_tax_no and taxpayer and buyer_tax_no != taxpayer:
            raise ValueError("指定买方税号与文件不一致。")
        buyer = buyer_tax_no or taxpayer
        records, results = [], []
        for row_number, mapped in rows:
            if not any(_normalize_text(mapped.get(key)) for key in ("勾选状态", "数电发票号码", "发票代码", "发票号码", "票种标签")):
                continue
            source = {key: _source_value(mapped.get(label)) for label, key in SOURCE_COLUMNS.items()}
            error = None
            ignored = False
            kind_label = _normalize_text(mapped.get("票种标签"))
            if kind_label != "增值税专用发票":
                error = "非增值税专用发票。"
                ignored = True
            elif _normalize_text(mapped.get("勾选状态")) not in {"已勾选", "已认证"}:
                error = "发票未勾选认证。"
            elif _normalize_text(mapped.get("发票状态")) != "正常":
                error = "发票状态非正常。"
            values = {key: _normalize_text(mapped.get(label)) for label, key in SOURCE_COLUMNS.items()}
            try:
                for key in ("amount", "tax_amount", "deductible_tax_amount"):
                    values[key] = _to_money_string(values[key])
                values["issue_date"] = _to_date_string(mapped.get("开票日期"))
                values["selection_time"] = _to_datetime_string(mapped.get("勾选时间"))
                identity = _build_unique_key(digital_invoice_no=values["digital_invoice_no"],
                                             invoice_code=values["invoice_code"], invoice_no=values["invoice_no"])
            except ValueError as exc:
                error = error or str(exc)
                identity = None
            if error:
                results.append({**values, "id": f"{upload.file_name}:{row_number}", "unique_key": identity,
                                "month": resolved_month, "source_file_name": upload.file_name,
                                "source_row_number": row_number, "row_status": "ignored" if ignored else "invalid", "error_message": error,
                                "source_fields": source, "dedupe_status": "not_applicable", "match_status": "unknown"})
                continue
            record = TaxCertifiedInvoiceRecord(
                id=identity, unique_key=identity, month=resolved_month, source_file_name=upload.file_name,
                source_row_number=row_number, taxpayer_tax_no=buyer, taxpayer_name=taxpayer_name,
                buyer_tax_no=buyer, source_fields=source,
                **{key: value for key, value in values.items() if key in TaxCertifiedInvoiceRecord.__dataclass_fields__},
            )
            records.append(record)
            results.append({**asdict(record), "row_status": "recognized", "error_message": None,
                            "dedupe_status": "new"})
        return TaxCertifiedImportPreviewFile(id=f"tax-certified-file-{uuid4().hex}", file_name=upload.file_name,
                    month=resolved_month, recognized_count=len(records),
                    invalid_count=sum(row["row_status"] == "invalid" for row in results),
                    ignored_count=sum(row["row_status"] == "ignored" for row in results),
                    rows=records, row_results=results)

    @staticmethod
    def _read_template(upload: UploadedCertifiedImportFile, *, max_business_rows: int) -> tuple[str | None, str | None, str | None, list]:
        try:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message="Workbook contains no default style")
                workbook = load_workbook(BytesIO(upload.content), data_only=True, read_only=True)
            try:
                if "发票" not in workbook.sheetnames:
                    raise ValueError("认证文件缺少“发票”sheet。")
                sheet = workbook["发票"]
                sheet.reset_dimensions()
                rows = []
                row_numbers = []
                business_rows = 0
                header_found = False
                required_headers = {"勾选状态", "数电发票号码", "发票代码", "发票号码", "票种标签"}
                header = []
                for index, row in enumerate(sheet.iter_rows(values_only=True)):
                    if index >= MAX_SHEET_ROWS:
                        raise ValueError("认证文件最多允许扫描 50000 行。")
                    if len(row) > MAX_SHEET_COLUMNS:
                        raise ValueError("认证文件最多允许 64 列。")
                    if not header_found:
                        header = [_normalize_text(value) for value in row]
                        header_found = required_headers.issubset(set(header))
                        if not header_found and index >= 49:
                            raise ValueError("无法识别认证文件表头。")
                    else:
                        mapped = {key: row[column] if column < len(row) else None for column, key in enumerate(header) if key}
                        if any(_normalize_text(mapped.get(key)) for key in required_headers):
                            business_rows += 1
                            if business_rows > max_business_rows:
                                raise ValueError("每次认证导入最多允许 20000 条业务记录。")
                        else:
                            continue
                    rows.append(row)
                    row_numbers.append(index+1)
            finally:
                workbook.close()
        except (BadZipFile, InvalidFileException, ParseError, EOFError, KeyError) as exc:
            raise ValueError("认证文件损坏或不是有效的 XLSX 文件。") from exc
        required = {"勾选状态", "数电发票号码", "发票代码", "发票号码", "票种标签"}
        header_index = next((i for i, row in enumerate(rows) if required.issubset({_normalize_text(v) for v in row})), None)
        if header_index is None:
            raise ValueError("无法识别认证文件表头。")
        metadata = {}
        for row in rows[:header_index]:
            for index, cell in enumerate(row[:-1]):
                label = (_normalize_text(cell) or "").rstrip("：:")
                if label in {"纳税人识别号", "纳税人名称", "税款所属期", "所属期", "所属月份"}:
                    metadata[label] = _normalize_text(row[index+1])
        raw_month = metadata.get("税款所属期") or metadata.get("所属期") or metadata.get("所属月份")
        source_month = None
        if raw_month:
            matched = re.fullmatch(r"(\d{4})[-年]?(\d{2})月?", raw_month)
            if not matched or not 1 <= int(matched[2]) <= 12:
                raise ValueError("文件所属期格式无效。")
            source_month = f"{matched[1]}-{matched[2]}"
        header = [_normalize_text(v) for v in rows[header_index]]
        data = [(row_numbers[i], {label: row[j] if j < len(row) else None for j, label in enumerate(header) if label})
                for i, row in enumerate(rows[header_index+1:], header_index+1)]
        return metadata.get("纳税人识别号"), metadata.get("纳税人名称"), source_month, data


def _normalize_text(value: Any) -> str | None:
    return str(value).strip() or None if value is not None else None


def _source_value(value: Any) -> Any:
    return value.isoformat(sep=" ") if isinstance(value, datetime) else value.isoformat() if isinstance(value, date) else value


def _to_date_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value)).date().isoformat()
    except ValueError as exc:
        raise ValueError("开票日期无效。") from exc


def _to_datetime_string(value: Any) -> str | None:
    if value is None or value == "":
        return None
    try:
        return datetime.fromisoformat(str(value)).isoformat(sep=" ")
    except ValueError as exc:
        raise ValueError("勾选时间无效。") from exc


def _to_money_string(value: Any) -> str | None:
    normalized = _normalize_text(value)
    if normalized is None:
        return None
    try:
        amount = Decimal(normalized.replace(",", ""))
        if not amount.is_finite():
            raise InvalidOperation
        return str(amount)
    except InvalidOperation as exc:
        raise ValueError("认证金额字段无效。") from exc


def _build_unique_key(*, digital_invoice_no: str | None, invoice_code: str | None,
                      invoice_no: str | None) -> str:
    if not digital_invoice_no and not (invoice_code and invoice_no):
        raise ValueError("缺少数电发票号码或发票代码与号码。")
    return OBJECT_IDENTITY_POLICY.tax_certified_unique_key({
        "digital_invoice_no": digital_invoice_no, "invoice_code": invoice_code, "invoice_no": invoice_no,
    })

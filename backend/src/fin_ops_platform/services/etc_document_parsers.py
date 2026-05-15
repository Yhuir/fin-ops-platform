from __future__ import annotations

from dataclasses import replace
from decimal import Decimal, InvalidOperation
from io import BytesIO
import re
import shutil
import subprocess
import tempfile
from typing import Any, Callable
from uuid import uuid5, NAMESPACE_URL

try:
    import fitz
except Exception:  # pragma: no cover - optional dependency fallback
    fitz = None

try:
    import pdfplumber
except Exception:  # pragma: no cover - optional dependency fallback
    pdfplumber = None

try:
    from PIL import Image, ImageOps
except Exception:  # pragma: no cover - optional dependency fallback
    Image = None
    ImageOps = None

try:
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover - optional dependency fallback
    RapidOCR = None

from fin_ops_platform.services.etc_reconciliation_models import (
    CreditCardItem,
    FileParseResult,
    ParseIssue,
    ParseIssueSeverity,
    SupplementEvidence,
    TicketRootItem,
)


CCB_ROW_RE = re.compile(
    r"^(?P<transaction_date>\d{4}[-/]\d{2}[-/]\d{2})\s+"
    r"(?P<posting_date>\d{4}[-/]\d{2}[-/]\d{2})\s+"
    r"(?P<card_last4>\d{4})\s+"
    r"(?P<description>.+?)\s+"
    r"(?P<currency>[A-Z]{3}|人民币|CNY)\s+"
    r"(?P<amount>-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s+"
    r"(?:(?:[A-Z]{3}|人民币|CNY)\s+)?"
    r"(?P<settlement_amount>-?[0-9][0-9,]*(?:\.[0-9]{1,2})?)\s*$"
)
ETC_KEYWORDS = ("etc", "高速", "通行费", "收费站", "联网公司", "联网收费", "票根", "黔通智联", "贵州黔通智联")
REPAYMENT_KEYWORDS = ("还款", "自动还款", "存入", "退款")
PLATE_RE = re.compile(r"[\u4e00-\u9fff][A-Z][A-Z0-9]{5,6}")
DATETIME_RE = re.compile(r"(\d{4}[-/]\d{2}[-/]\d{2}\s*\d{2}:\d{2}(?::\d{2})?)")
AMOUNT_RE = re.compile(r"(?:交易金额|金额|收费金额|合计|￥|¥)\s*[:：]?\s*[￥¥]?\s*([0-9]+(?:\.[0-9]{1,2})?)")
INVOICE_COUNT_RE = re.compile(r"(?:发票张数|发票数量|张数)\s*[:：]?\s*(\d+)")
ENTRY_RE = re.compile(r"(?:入口站|入口)\s*[:：]?\s*([^\s]+)")
EXIT_RE = re.compile(r"(?:出口站|出口)\s*[:：]?\s*([^\s]+)")
TRIP_TRANSACTION_AMOUNT_RE = re.compile(
    r"交易时间\s*[:：]?\s*\d{4}[-/]\d{2}[-/]\d{2}\s*\d{2}:\d{2}(?::\d{2})?.*?"
    r"交易金额\s*[:：]?\s*[￥¥]?\s*[0-9]+(?:\.[0-9]{1,2})?",
    re.S,
)
STATION_LINE_RE = re.compile(r"^[\u4e00-\u9fffA-Za-z0-9（）()·\-]{2,30}站$")
STATION_ARROW_RE = re.compile(
    r"(?P<entry>[\u4e00-\u9fffA-Za-z0-9（）()·\-]{2,30}站)\s*(?:->|→|至|到|-)\s*"
    r"(?P<exit>[\u4e00-\u9fffA-Za-z0-9（）()·\-]{2,30}站)"
)
MERCHANT_RE = re.compile(r"(?:商户全称|商户|销售方|收款方)\s*[:：]?\s*([^\n]+)")
PAID_AT_RE = re.compile(r"(?:支付时间|交易时间)\s*[:：]?\s*(\d{4}年\d{1,2}月\d{1,2}日\s*\d{1,2}:\d{2}(?::\d{2})?)")
INVOICE_APPLICATION_MARKERS = ("消费发票申请", "开票完成", "开票记录", "开票申请时间", "开票金额")
CLIPBOARD_TRIP_TAB_MARKERS = ("按行程查看", "入口收费站/出口收费站")
CLIPBOARD_SKIP_LINE_MARKERS = (
    "查看发票",
    "发票下载",
    "发票转发",
    "入口收费站/出口收费站",
    "点击此处选择月份",
    "版权所有",
)
PROVINCE_LINE_VALUES = {
    "北京",
    "天津",
    "河北",
    "山西",
    "内蒙古",
    "辽宁",
    "吉林",
    "黑龙江",
    "上海",
    "江苏",
    "浙江",
    "安徽",
    "福建",
    "江西",
    "山东",
    "河南",
    "湖北",
    "湖南",
    "广东",
    "广西",
    "海南",
    "重庆",
    "四川",
    "贵州",
    "云南",
    "西藏",
    "陕西",
    "甘肃",
    "青海",
    "宁夏",
    "新疆",
}


class CcbCreditCardStatementParser:
    parser_code = "ccb_credit_card_statement_v1"

    def parse_text(self, *, file_id: str, text: str, task_id: str = "") -> FileParseResult:
        if not text.strip():
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, "empty_statement_text"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message="信用卡账单未提取到可解析文本，不能进入核对。",
                        field_name="statement_rows",
                    )
                ],
            )
        items: list[CreditCardItem] = []
        for line_no, raw_line in enumerate(text.splitlines(), start=1):
            line = raw_line.strip()
            if not line:
                continue
            match = CCB_ROW_RE.match(line)
            if match is None:
                continue
            amount = _parse_decimal(match.group("amount"))
            settlement_amount = _parse_decimal(match.group("settlement_amount"))
            if amount is None or settlement_amount is None:
                continue
            description = match.group("description").strip()
            is_candidate = _is_etc_candidate(description, amount)
            item = CreditCardItem(
                item_id=_stable_id("ccb", file_id, line_no, line),
                task_id=task_id,
                statement_file_id=file_id,
                transaction_date=match.group("transaction_date").replace("/", "-"),
                posting_date=match.group("posting_date").replace("/", "-"),
                card_last4=match.group("card_last4"),
                description=description,
                currency="CNY" if match.group("currency") == "人民币" else match.group("currency"),
                amount=amount,
                settlement_amount=settlement_amount,
                is_etc_candidate=is_candidate,
                candidate_reason="etc_keyword" if is_candidate else None,
                source_page=1,
                source_line=line_no,
                recommendation_status="needs_review" if is_candidate else "not_candidate",
            )
            items.append(item)
        if not items:
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, "no_statement_rows_matched"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message="信用卡账单未识别到交易明细行，不能进入核对。",
                        field_name="statement_rows",
                    )
                ],
            )
        return FileParseResult(file_id=file_id, parser_code=self.parser_code, credit_card_items=items)

    def parse_pdf_bytes(self, *, file_id: str, content: bytes, task_id: str = "") -> FileParseResult:
        return self.parse_text(file_id=file_id, text=_extract_pdf_text(content), task_id=task_id)


class TicketRootPdfTextParser:
    parser_code = "ticket_root_pdf_text_v1"

    def parse_text(
        self,
        *,
        file_id: str,
        text: str,
        page_number: int = 1,
        task_id: str = "",
        extraction_method: str = "pdf_text",
        default_plate: str | None = None,
    ) -> FileParseResult:
        normalized_text = text.strip()
        if not normalized_text:
            return FileParseResult(file_id=file_id, parser_code=self.parser_code)

        plate_match = PLATE_RE.search(normalized_text)
        inherited_plate = str(default_plate or "").strip()
        transaction_match = DATETIME_RE.search(normalized_text)
        amount = _first_decimal(AMOUNT_RE.findall(normalized_text))
        has_ticket_shape = _has_ticket_detail_structure(normalized_text)
        if plate_match is None and not inherited_plate:
            if has_ticket_shape:
                return FileParseResult(
                    file_id=file_id,
                    parser_code=self.parser_code,
                    issues=[
                        ParseIssue(
                            issue_id=_stable_id("issue", file_id, page_number, extraction_method, "missing_plate"),
                            file_id=file_id,
                            severity=ParseIssueSeverity.BLOCKING,
                            message="票根网通行项缺少车牌号，不能进入核对。",
                            source_page=page_number,
                            extraction_method=extraction_method,
                            field_name="vehicle_plate",
                        )
                    ],
                )
            return FileParseResult(file_id=file_id, parser_code=self.parser_code)
        if transaction_match is None or amount is None:
            if not has_ticket_shape:
                return FileParseResult(file_id=file_id, parser_code=self.parser_code)
            missing_field = "transaction_at" if transaction_match is None else "amount"
            missing_label = "交易时间" if transaction_match is None else "金额"
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, page_number, extraction_method, f"missing_{missing_field}"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message=f"票根网通行项缺少{missing_label}，不能进入核对。",
                        source_page=page_number,
                        extraction_method=extraction_method,
                        field_name=missing_field,
                    )
                ],
            )

        plate = plate_match.group(0) if plate_match is not None else inherited_plate
        items = [
            _ticket_item_from_block(
                file_id=file_id,
                task_id=task_id,
                page_number=page_number,
                extraction_method=extraction_method,
                plate=plate,
                block=block,
            )
            for block in _ticket_record_blocks(normalized_text)
        ]
        parsed_items = [item for item in items if item is not None]
        if parsed_items:
            return FileParseResult(file_id=file_id, parser_code=self.parser_code, ticket_root_items=parsed_items)
        return FileParseResult(file_id=file_id, parser_code=self.parser_code)


class TicketRootClipboardTextParser:
    parser_code = "ticket_root_clipboard_text_v1"
    extraction_method = "clipboard_text"

    def parse_text(self, *, file_id: str, text: str, task_id: str = "") -> FileParseResult:
        normalized_text = _normalize_clipboard_text(text)
        if _is_invoice_application_without_ticket_details(normalized_text):
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, "clipboard_invoice_record_page"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message="请切换到按行程查看后复制粘贴。",
                        extraction_method=self.extraction_method,
                        field_name="ticket_root_text",
                    )
                ],
            )
        plate = self.extract_plate(normalized_text)
        if not plate:
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, "clipboard_missing_plate"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message="票根网手工粘贴内容缺少车牌号，不能进入核对。",
                        extraction_method=self.extraction_method,
                        field_name="vehicle_plate",
                    )
                ],
            )

        items: list[TicketRootItem] = []
        for record_index, block in enumerate(_ticket_record_blocks(normalized_text), start=1):
            item = _ticket_item_from_block(
                file_id=file_id,
                task_id=task_id,
                page_number=1,
                extraction_method=self.extraction_method,
                plate=plate,
                block=_clean_clipboard_record_block(block),
                require_station=False,
                record_index=record_index,
            )
            if item is not None:
                items.append(item)
        if not items:
            return FileParseResult(
                file_id=file_id,
                parser_code=self.parser_code,
                issues=[
                    ParseIssue(
                        issue_id=_stable_id("issue", file_id, "clipboard_no_trip_rows"),
                        file_id=file_id,
                        severity=ParseIssueSeverity.BLOCKING,
                        message="票根网手工粘贴内容未识别到通行明细，不能进入核对。",
                        extraction_method=self.extraction_method,
                        field_name="ticket_root_items",
                    )
                ],
            )
        return FileParseResult(file_id=file_id, parser_code=self.parser_code, ticket_root_items=items)

    @staticmethod
    def extract_plate(text: str) -> str:
        plate_label_match = re.search(r"车牌号\s*[:：]?\s*(?P<plate>[\u4e00-\u9fff][A-Z][A-Z0-9]{5,6})", text)
        if plate_label_match is not None:
            return plate_label_match.group("plate")
        plate_match = PLATE_RE.search(text)
        return plate_match.group(0) if plate_match is not None else ""

    @staticmethod
    def extract_month(text: str) -> str:
        month_match = re.search(r"(?<!\d)(20\d{2})(0[1-9]|1[0-2])(?!\d)", text)
        return month_match.group(0) if month_match is not None else ""


class TicketRootDocumentParser:
    parser_code = "ticket_root_document_v1"

    def __init__(
        self,
        *,
        pdf_text_extractor: Callable[[bytes], str] | None = None,
        ocr_text_extractor: Callable[[bytes], list[str]] | None = None,
    ) -> None:
        self._pdf_text_extractor = pdf_text_extractor or _extract_pdf_text
        self._ocr_text_extractor = ocr_text_extractor or TicketRootOcrTextExtractor()
        self._text_parser = TicketRootPdfTextParser()

    def parse_file(self, *, file_id: str, content: bytes, task_id: str = "") -> FileParseResult:
        pdf_text = self._pdf_text_extractor(content)
        has_invoice_application_only_page = _is_invoice_application_without_ticket_details(pdf_text)
        pdf_text_result = self._text_parser.parse_text(
            file_id=file_id,
            text=pdf_text,
            page_number=1,
            task_id=task_id,
            extraction_method="pdf_text",
        )
        if pdf_text_result.ticket_root_items:
            return pdf_text_result

        combined = FileParseResult(file_id=file_id, parser_code=self.parser_code)
        document_plate_match = PLATE_RE.search(pdf_text)
        document_plate = document_plate_match.group(0) if document_plate_match is not None else None
        for page_index, page_text in enumerate(self._ocr_text_extractor(content), start=1):
            if _is_invoice_application_without_ticket_details(page_text):
                has_invoice_application_only_page = True
            page_plate_match = PLATE_RE.search(page_text)
            if page_plate_match is not None:
                document_plate = page_plate_match.group(0)
            page_result = self._text_parser.parse_text(
                file_id=file_id,
                text=page_text,
                page_number=page_index,
                task_id=task_id,
                extraction_method="ocr",
                default_plate=document_plate,
            )
            combined.ticket_root_items.extend(page_result.ticket_root_items)
            combined.issues.extend(page_result.issues)
        if combined.ticket_root_items:
            return combined
        if pdf_text_result.issues:
            combined.issues = [*pdf_text_result.issues, *combined.issues]
        if has_invoice_application_only_page and not combined.issues:
            return combined
        if not combined.issues:
            combined.issues.append(
                ParseIssue(
                    issue_id=_stable_id("issue", file_id, "ticket_root_text_unavailable"),
                    file_id=file_id,
                    severity=ParseIssueSeverity.BLOCKING,
                    message="票根网文件未提取到可解析通行明细，不能进入核对。",
                    extraction_method="pdf_text_or_ocr",
                    field_name="ticket_root_text",
                )
            )
        return combined


class TicketRootOcrTextExtractor:
    def __init__(self) -> None:
        self._ocr_engine: Any | None = None
        self._ocr_engine_unavailable = False

    def __call__(self, content: bytes) -> list[str]:
        pdf_pages = self._render_pdf_pages_for_ocr(content)
        if pdf_pages:
            return [self._extract_image_text(page_content) for page_content in pdf_pages]
        image_text = self._extract_image_text(content)
        return [image_text] if image_text else []

    def _render_pdf_pages_for_ocr(self, content: bytes) -> list[bytes]:
        if fitz is None or not content.lstrip().startswith(b"%PDF"):
            return []
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception:
            return []
        try:
            page_images: list[bytes] = []
            matrix = fitz.Matrix(2, 2)
            for page in document:
                pixmap = page.get_pixmap(matrix=matrix, alpha=False)
                page_images.append(pixmap.tobytes("png"))
            return page_images
        except Exception:
            return []
        finally:
            document.close()

    def _extract_image_text(self, content: bytes) -> str:
        for image_content in self._iter_image_ocr_inputs(content):
            lines = self._run_image_ocr(image_content)
            if lines:
                return _normalize_ocr_text("\n".join(lines))
        return ""

    def _run_image_ocr(self, content: bytes) -> list[str]:
        engine = self._get_ocr_engine()
        if engine is None:
            return []
        try:
            raw_result = engine(content)
        except Exception:
            return []
        result = raw_result[0] if isinstance(raw_result, tuple) else raw_result
        if not result:
            return []
        lines: list[str] = []
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = _clean_ocr_line(item[1])
            if text:
                lines.append(text)
        return lines

    def _get_ocr_engine(self) -> Any | None:
        if self._ocr_engine is not None:
            return self._ocr_engine
        if self._ocr_engine_unavailable or RapidOCR is None:
            return None
        try:
            self._ocr_engine = RapidOCR()
        except Exception:
            self._ocr_engine_unavailable = True
            return None
        return self._ocr_engine

    def _iter_image_ocr_inputs(self, content: bytes) -> list[bytes]:
        candidates = [content]
        preprocessed = self._preprocess_image_for_ocr(content)
        if preprocessed and preprocessed != content:
            candidates.append(preprocessed)
        return candidates

    @staticmethod
    def _preprocess_image_for_ocr(content: bytes) -> bytes:
        if Image is None or ImageOps is None:
            return b""
        try:
            with Image.open(BytesIO(content)) as image:
                normalized = ImageOps.exif_transpose(image).convert("RGB")
                width, height = normalized.size
                if max(width, height) < 1600:
                    normalized = normalized.resize((width * 2, height * 2))
                grayscale = ImageOps.grayscale(normalized)
                enhanced = ImageOps.autocontrast(grayscale)
                output = BytesIO()
                enhanced.save(output, format="PNG")
                return output.getvalue()
        except Exception:
            return b""


class SupplementEvidenceParser:
    parser_code = "supplement_evidence_v1"

    def parse_text(
        self,
        *,
        file_id: str,
        text: str,
        source_name: str,
        task_id: str = "",
        evidence_kind_override: str | None = None,
    ) -> FileParseResult:
        normalized_text = text.strip()
        evidence_kind = _normalize_evidence_kind(
            evidence_kind_override or ("etc_invoice" if _contains_etc_keyword(normalized_text) else "non_etc_invoice")
        )
        amount = _first_decimal(AMOUNT_RE.findall(normalized_text))
        merchant = _first_group(MERCHANT_RE, normalized_text)
        paid_at_match = PAID_AT_RE.search(normalized_text)
        paid_at = _normalize_chinese_datetime(paid_at_match.group(1)) if paid_at_match else None
        evidence = SupplementEvidence(
            evidence_id=_stable_id("supplement", file_id, source_name, evidence_kind, amount, paid_at, merchant),
            task_id=task_id,
            source_file_id=file_id,
            source_name=source_name,
            evidence_kind=evidence_kind,
            amount=amount,
            paid_at=paid_at,
            merchant_name=merchant,
            include_in_etc_zip_check=evidence_kind == "etc_invoice",
        )
        return FileParseResult(file_id=file_id, parser_code=self.parser_code, supplement_evidences=[evidence])


def _is_etc_candidate(description: str, amount: Decimal) -> bool:
    if amount < 0:
        return False
    lowered = description.lower()
    if any(keyword in lowered for keyword in REPAYMENT_KEYWORDS):
        return False
    return _contains_etc_keyword(description)


def _contains_etc_keyword(text: str) -> bool:
    lowered = text.lower()
    return any(keyword in lowered for keyword in ETC_KEYWORDS)


def _normalize_evidence_kind(value: str | None) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {"etc", "etc_invoice", "etc-invoice"}:
        return "etc_invoice"
    if normalized in {"non_etc", "non_etc_invoice", "non-etc", "non-etc-invoice", "supplement"}:
        return "non_etc_invoice"
    return normalized or "non_etc_invoice"


def _ticket_record_blocks(text: str) -> list[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return []
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in lines:
        current_text = "\n".join(current)
        starts_next_record = (
            bool(DATETIME_RE.search(line))
            and bool(current)
            and bool(DATETIME_RE.search(current_text))
            and bool(AMOUNT_RE.search(current_text))
        ) or (
            bool(AMOUNT_RE.search(line))
            and not bool(DATETIME_RE.search(line))
            and bool(current)
            and bool(DATETIME_RE.search(current_text))
            and bool(AMOUNT_RE.search(current_text))
            and _ticket_block_has_record_boundary(current_text)
        )
        if starts_next_record:
            blocks.append(current)
            current = []
        current.append(line)
    if current:
        blocks.append(current)
    return ["\n".join(block) for block in blocks]


def _ticket_block_has_record_boundary(text: str) -> bool:
    if all(_extract_ticket_stations(text)):
        return True
    return any(marker in text for marker in ("发票数量", "发票张数"))


def _ticket_item_from_block(
    *,
    file_id: str,
    task_id: str,
    page_number: int,
    extraction_method: str,
    plate: str,
    block: str,
    require_station: bool = True,
    record_index: int | None = None,
) -> TicketRootItem | None:
    transaction_match = DATETIME_RE.search(block)
    amount = _first_decimal(AMOUNT_RE.findall(block))
    if transaction_match is None or amount is None:
        return None
    transaction_at = _normalize_ticket_datetime(transaction_match.group(1))
    entry_station, exit_station = _extract_ticket_stations(block)
    if require_station and not entry_station and not exit_station:
        return None
    invoice_count_match = INVOICE_COUNT_RE.search(block)
    invoice_count = int(invoice_count_match.group(1)) if invoice_count_match else 1
    confidence = 1.0 if entry_station and exit_station else 0.72
    item_id = (
        _stable_id("ticket", file_id, record_index, plate, transaction_at, amount, entry_station, exit_station)
        if record_index is not None
        else _stable_id("ticket", file_id, plate, transaction_at, amount, entry_station, exit_station)
    )
    return TicketRootItem(
        item_id=item_id,
        task_id=task_id,
        ticket_file_id=file_id,
        vehicle_plate=plate,
        transaction_at=transaction_at,
        amount=amount,
        entry_station=entry_station,
        exit_station=exit_station,
        invoice_count=invoice_count,
        source_page=page_number,
        extraction_method=extraction_method,
        parse_confidence=confidence,
    )


def _parse_decimal(raw: str) -> Decimal | None:
    try:
        return Decimal(raw.replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _first_decimal(values: list[str]) -> Decimal | None:
    for value in values:
        parsed = _parse_decimal(value)
        if parsed is not None:
            return parsed
    return None


def _first_group(pattern: re.Pattern[str], text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _extract_ticket_stations(block: str) -> tuple[str, str]:
    entry_station = _first_group(ENTRY_RE, block) or ""
    exit_station = _first_group(EXIT_RE, block) or ""
    if _is_station_header_value(entry_station):
        entry_station = ""
    if _is_station_header_value(exit_station):
        exit_station = ""
    if entry_station or exit_station:
        return entry_station, exit_station
    arrow_match = STATION_ARROW_RE.search(block)
    if arrow_match is not None:
        return arrow_match.group("entry").strip(), arrow_match.group("exit").strip()
    station_lines = []
    for raw_line in block.splitlines():
        line = _clean_clipboard_station_line(raw_line)
        if line and STATION_LINE_RE.match(line) and "收费站/" not in line:
            station_lines.append(line)
    if len(station_lines) >= 2:
        return station_lines[0], station_lines[1]
    return "", ""


def _is_station_header_value(value: str) -> bool:
    return "/" in value or "入口" in value or "出口" in value or value in {"收费站", "入口收费站", "出口收费站"}


def _has_ticket_detail_structure(text: str) -> bool:
    if not str(text or "").strip():
        return False
    entry_station, exit_station = _extract_ticket_stations(text)
    if entry_station or exit_station:
        return True
    return any(marker in text for marker in ("通行明细", *CLIPBOARD_TRIP_TAB_MARKERS)) and bool(DATETIME_RE.search(text) or AMOUNT_RE.search(text))


def _is_invoice_application_without_ticket_details(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if not any(marker in normalized for marker in INVOICE_APPLICATION_MARKERS):
        return False
    return not _has_ticket_trip_page_structure(normalized)


def _has_ticket_trip_page_structure(text: str) -> bool:
    normalized = str(text or "")
    if "入口收费站/出口收费站" in normalized:
        return True
    entry_station, exit_station = _extract_ticket_stations(normalized)
    if entry_station or exit_station:
        return True
    return bool(TRIP_TRANSACTION_AMOUNT_RE.search(normalized))


def _normalize_ticket_datetime(value: str) -> str:
    normalized = value.replace("/", "-").strip()
    match = re.match(r"(\d{4}-\d{2}-\d{2})\s*(\d{2}:\d{2}(?::\d{2})?)", normalized)
    if match is None:
        return normalized
    return f"{match.group(1)} {match.group(2)}"


def _clean_ocr_line(value: object) -> str:
    return re.sub(r"[\s\u3000]+", " ", str(value or "")).strip()


def _normalize_ocr_text(text: str) -> str:
    return (
        text.replace("¥", "￥")
        .replace("—>", "->")
        .replace("一>", "->")
        .strip()
    )


def _normalize_clipboard_text(text: str) -> str:
    return str(text or "").replace("\u3000", " ").replace("¥", "￥").strip()


def _clean_clipboard_record_block(block: str) -> str:
    lines: list[str] = []
    for raw_line in block.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if any(marker in line for marker in CLIPBOARD_SKIP_LINE_MARKERS):
            line = re.sub(r"查看发票\s*发票下载\s*发票转发", "", line).strip()
        cleaned = _clean_clipboard_station_line(line)
        if cleaned:
            lines.append(cleaned)
    return "\n".join(lines)


def _clean_clipboard_station_line(line: str) -> str:
    normalized = str(line or "").strip()
    if not normalized:
        return ""
    if normalized in PROVINCE_LINE_VALUES:
        return ""
    if normalized.isdigit():
        return ""
    if any(marker in normalized for marker in ("版权所有", "首页", "我的ETC", "我要开票", "我的发票", "发票抬头", "个人中心", "客服协助")):
        return ""
    if any(marker in normalized for marker in ("查看发票", "发票下载", "发票转发", "入口收费站/出口收费站", "点击此处选择月份")):
        return ""
    return normalized


def _stable_id(*parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    return uuid5(NAMESPACE_URL, raw).hex


def _normalize_chinese_datetime(value: str) -> str:
    normalized = value.strip()
    normalized = normalized.replace("年", "-").replace("月", "-").replace("日", "")
    date_part, _, time_part = normalized.partition(" ")
    year, month, day = date_part.split("-")
    return f"{int(year):04d}-{int(month):02d}-{int(day):02d} {time_part.strip()}"


def _extract_pdf_text(content: bytes) -> str:
    if pdfplumber is not None:
        try:
            with pdfplumber.open(BytesIO(content)) as document:
                text = "\n".join(page.extract_text() or "" for page in document.pages).strip()
                if text:
                    return text
        except Exception:
            pass
    if fitz is not None:
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception:
            document = None
        if document is not None:
            try:
                text = "\n".join(page.get_text("text") for page in document).strip()
                if text:
                    return text
            except Exception:
                pass
            finally:
                document.close()
    return _extract_pdf_text_with_pdftotext(content)


def _extract_pdf_text_with_pdftotext(content: bytes) -> str:
    executable = shutil.which("pdftotext")
    if not executable:
        return ""
    try:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as pdf_file:
            pdf_file.write(content)
            pdf_file.flush()
            result = subprocess.run(
                [executable, "-layout", pdf_file.name, "-"],
                timeout=10,
                capture_output=True,
                check=False,
            )
    except Exception:
        return ""
    if result.returncode != 0:
        return ""
    return result.stdout.decode("utf-8", errors="ignore").strip()


def with_task_id(parse_result: FileParseResult, task_id: str) -> FileParseResult:
    return FileParseResult(
        file_id=parse_result.file_id,
        parser_code=parse_result.parser_code,
        credit_card_items=[replace(item, task_id=task_id) for item in parse_result.credit_card_items],
        ticket_root_items=[replace(item, task_id=task_id) for item in parse_result.ticket_root_items],
        supplement_evidences=[replace(item, task_id=task_id) for item in parse_result.supplement_evidences],
        issues=list(parse_result.issues),
    )

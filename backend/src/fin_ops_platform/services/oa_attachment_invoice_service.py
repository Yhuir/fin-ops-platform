from __future__ import annotations

from io import BytesIO
import os
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlsplit, urlunsplit
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile
import xml.etree.ElementTree as ET

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

from fin_ops_platform.services.imports import clean_string


INVOICE_CODE_RE = re.compile(r"发票代码:([0-9A-Za-z]+)")
INVOICE_NO_RE = re.compile(r"发票号码:([0-9A-Za-z]+)")
LOOSE_INVOICE_CODE_RE = re.compile(r"发票代码[:：]?([0-9A-Za-z]{8,20})")
LOOSE_INVOICE_NO_RE = re.compile(r"发票号码[:：]?([0-9A-Za-z]{6,20})")
ISSUE_DATE_RE = re.compile(r"开票日期:(\d{4})年(\d{2})月(\d{2})日")
DIGITAL_INVOICE_NO_RE = re.compile(r"(?<![0-9A-Z])([0-9]{20})(?![0-9A-Z])")
LOOSE_ISSUE_DATE_RE = re.compile(r"(\d{4})年(\d{2})月(\d{2})日")
TOTALS_RE = re.compile(r"合计¥([0-9]+(?:\.\d+)?)¥([0-9]+(?:\.\d+)?)")
TOTAL_WITH_TAX_RE = re.compile(r"价税合计.*?¥([0-9]+(?:\.\d+)?)")
CURRENCY_AMOUNT_RE = re.compile(r"[¥Y]\s*([0-9]+(?:\.\d+)?)")
SMALL_TOTAL_RE = re.compile(r"[（(]?小写[)）]?[^0-9]{0,8}([0-9]+(?:[.,，][0-9]{2})?)")
TAX_RATE_RE = re.compile(r"(?<![0-9])([0-9]{1,2}(?:\.\d{1,2})?%)(?![0-9])")
TAX_ID_RE = re.compile(r"([0-9A-Z]{15,25})")
NAME_LABEL_RE = re.compile(r"(?:名称|称):")
COMPANY_NAME_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9（）()·、&\-.]+?"
    r"(?:有限责任公司|股份有限公司|有限公司|集团|银行|中心|厂|店|站|酒店|宾馆|学院|大学|学校|局|医院|政府|委员会|事务所|研究院|支行|分行))"
)

SUPPORTED_SUFFIXES = {"pdf", "jpg", "jpeg", "png", "docx"}
SUPPORTED_DOCX_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


class OAAttachmentInvoiceService:
    PARSER_VERSION = "2026-04-30-docx-railway-cny-machine-nontax"

    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float = 10.0,
        max_download_bytes: int = 20 * 1024 * 1024,
    ) -> None:
        configured_base_url = clean_string(os.getenv("FIN_OPS_OA_ATTACHMENT_BASE_URL") or "")
        self._base_url = (base_url or configured_base_url or "https://www.yn-sourcing.com/oa-api").rstrip("/")
        self._timeout_seconds = max(float(timeout_seconds), 1.0)
        self._max_download_bytes = max(int(max_download_bytes), 1024 * 1024)
        self._ocr_engine: Any | None = None
        self._ocr_engine_unavailable = False

    def parse_files(self, files: list[dict[str, object]]) -> list[dict[str, str]]:
        invoices: list[dict[str, str]] = []
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            try:
                parsed_invoices = self._parse_single_file(file_entry)
            except Exception:
                parsed_invoices = []
            invoices.extend(parsed_invoices)
        return invoices

    def build_download_url(self, file_path: str) -> str:
        normalized_path = clean_string(file_path)
        if normalized_path.startswith(("http://", "https://")):
            return self._quote_url(normalized_path)
        encoded_path = quote(normalized_path.lstrip("/"), safe="/")
        return f"{self._base_url}/{encoded_path}" if encoded_path else self._base_url

    @staticmethod
    def _quote_url(url: str) -> str:
        parsed = urlsplit(url)
        return urlunsplit(
            (
                parsed.scheme,
                parsed.netloc,
                quote(parsed.path, safe="/%"),
                quote(parsed.query, safe="=&%"),
                quote(parsed.fragment, safe="%"),
            )
        )

    def _parse_single_file(self, file_entry: dict[str, object]) -> list[dict[str, str]]:
        file_name = clean_string(file_entry.get("fileName") or file_entry.get("name") or "")
        file_path = clean_string(file_entry.get("filePath") or file_entry.get("url") or "")
        suffix = clean_string(file_entry.get("suffix") or Path(file_name or file_path).suffix.lstrip(".")).lower()
        if suffix not in SUPPORTED_SUFFIXES:
            return []
        if not file_path:
            return []

        content = self._download_content(self.build_download_url(file_path))
        if content is None:
            return []

        attachment_name = file_name or Path(file_path).name
        parsed_invoices: list[dict[str, str]] = []
        seen_keys: set[str] = set()
        for extracted_text in self._extract_text_segments(content, suffix):
            if not extracted_text:
                continue
            parsed_invoice = self._parse_invoice_text(extracted_text)
            if parsed_invoice is None:
                continue
            parsed_invoice["attachment_name"] = attachment_name
            parsed_invoice.setdefault("invoice_type", "进项发票")
            dedupe_key = self._invoice_dedupe_key(parsed_invoice)
            if dedupe_key and dedupe_key in seen_keys:
                continue
            if dedupe_key:
                seen_keys.add(dedupe_key)
            parsed_invoices.append(parsed_invoice)
        return parsed_invoices

    def _extract_text_segments(self, content: bytes, suffix: str) -> list[str]:
        if suffix == "pdf":
            return [self._extract_pdf_text(content)]
        if suffix == "docx":
            return self._extract_docx_text_segments(content)
        return [self._extract_image_text(content)]

    @staticmethod
    def _invoice_dedupe_key(invoice: dict[str, str]) -> str:
        return "|".join(
            clean_string(invoice.get(key) or "")
            for key in ("invoice_no", "issue_date", "total_with_tax", "attachment_name")
        )

    def _download_content(self, url: str) -> bytes | None:
        request = Request(url, headers={"User-Agent": "fin-ops-platform/oa-attachment-parser"})
        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                content = response.read(self._max_download_bytes + 1)
        except (HTTPError, OSError, URLError, TimeoutError, UnicodeError, ValueError):
            return None
        if len(content) > self._max_download_bytes:
            return None
        return content

    def _extract_pdf_text(self, content: bytes) -> str:
        text = self._extract_pdf_text_with_pdfplumber(content)
        if text:
            return text
        return self._extract_pdf_text_with_fitz(content)

    def _extract_image_text(self, content: bytes) -> str:
        for image_content in self._iter_image_ocr_inputs(content):
            lines = self._run_image_ocr(image_content)
            if lines:
                return "\n".join(lines).strip()
        return ""

    def _extract_docx_text_segments(self, content: bytes) -> list[str]:
        try:
            with ZipFile(BytesIO(content)) as document:
                segments = self._extract_docx_xml_text_segments(document)
                segments.extend(self._extract_docx_media_text_segments(document))
                return [segment for segment in segments if clean_string(segment)]
        except (BadZipFile, KeyError, OSError, ET.ParseError, ValueError):
            return []

    @staticmethod
    def _extract_docx_xml_text_segments(document: ZipFile) -> list[str]:
        xml_names = [
            name
            for name in document.namelist()
            if name == "word/document.xml"
            or (name.startswith("word/header") and name.endswith(".xml"))
            or (name.startswith("word/footer") and name.endswith(".xml"))
        ]
        segments: list[str] = []
        for xml_name in xml_names:
            root = ET.fromstring(document.read(xml_name))
            texts = [
                clean_string(element.text)
                for element in root.iter()
                if element.tag.endswith("}t") and clean_string(element.text)
            ]
            if texts:
                segments.append("\n".join(texts))
        return segments

    def _extract_docx_media_text_segments(self, document: ZipFile) -> list[str]:
        image_names = [
            name
            for name in document.namelist()
            if name.startswith("word/media/")
            and Path(name).suffix.lower() in SUPPORTED_DOCX_IMAGE_SUFFIXES
        ]
        segments: list[str] = []
        for image_name in image_names:
            image_text = self._extract_image_text(document.read(image_name))
            if image_text:
                segments.append(image_text)
        return segments

    @staticmethod
    def _extract_pdf_text_with_pdfplumber(content: bytes) -> str:
        if pdfplumber is None:
            return ""
        try:
            with pdfplumber.open(BytesIO(content)) as pdf:
                return "\n".join(filter(None, (page.extract_text() for page in pdf.pages))).strip()
        except Exception:
            return ""

    @staticmethod
    def _extract_pdf_text_with_fitz(content: bytes) -> str:
        if fitz is None:
            return ""
        try:
            document = fitz.open(stream=content, filetype="pdf")
        except Exception:
            return ""
        try:
            return "\n".join(
                page.get_text().strip()
                for page in document
                if page.get_text().strip()
            ).strip()
        finally:
            document.close()

    def _run_image_ocr(self, content: bytes) -> list[str]:
        engine = self._get_ocr_engine()
        if engine is None:
            return []
        try:
            result, _ = engine(content)
        except Exception:
            return []
        if not result:
            return []
        lines: list[str] = []
        for item in result:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                continue
            text = clean_string(item[1])
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
                    scale_ratio = 2
                    normalized = normalized.resize((width * scale_ratio, height * scale_ratio))
                grayscale = ImageOps.grayscale(normalized)
                enhanced = ImageOps.autocontrast(grayscale)
                output = BytesIO()
                enhanced.save(output, format="PNG")
                return output.getvalue()
        except Exception:
            return b""

    def _parse_invoice_text(self, extracted_text: str) -> dict[str, str] | None:
        compact_text = re.sub(r"[\s\u3000]+", "", extracted_text).replace("：", ":").replace("￥", "¥")

        invoice_code = self._match_text(INVOICE_CODE_RE, compact_text)
        invoice_no = self._match_text(INVOICE_NO_RE, compact_text) or self._extract_digital_invoice_no(compact_text)
        issue_date = self._extract_issue_date(compact_text)
        totals = self._extract_amount_summary(compact_text)
        if not invoice_no or not issue_date or totals is None:
            non_tax_receipt = self._parse_non_tax_payment_receipt_text(extracted_text, compact_text)
            if non_tax_receipt is not None:
                return non_tax_receipt
            machine_printed_invoice = self._parse_machine_printed_invoice_text(
                extracted_text,
                compact_text,
                invoice_code=invoice_code,
                invoice_no=invoice_no,
                issue_date=issue_date,
            )
            if machine_printed_invoice is not None:
                return machine_printed_invoice
            return None

        names = self._extract_names(compact_text)
        line_names = self._extract_names_from_lines(extracted_text)
        if len(names) < 2 or any(self._is_suspicious_company_name(name) for name in names[:2]):
            names = line_names or names
        tax_ids = [
            tax_id
            for tax_id in self._extract_tax_ids(compact_text)
            if tax_id not in {invoice_no, invoice_no[:18]}
        ]
        line_tax_ids = self._extract_tax_ids_from_lines(extracted_text, excluded_values={invoice_no, invoice_no[:18]})
        if len(tax_ids) < 2:
            for tax_id in line_tax_ids:
                if tax_id not in tax_ids:
                    tax_ids.append(tax_id)
        buyer_name = names[0] if len(names) >= 1 else ""
        seller_name = names[1] if len(names) >= 2 else ""
        buyer_tax_no = tax_ids[0] if len(tax_ids) >= 1 else ""
        seller_tax_no = tax_ids[1] if len(tax_ids) >= 2 else ""
        net_amount, tax_amount, total_with_tax = totals

        parsed = {
            "invoice_code": invoice_code,
            "invoice_no": invoice_no,
            "seller_tax_no": seller_tax_no,
            "seller_name": seller_name,
            "buyer_tax_no": buyer_tax_no,
            "buyer_name": buyer_name,
            "issue_date": issue_date,
            "amount": net_amount,
            "net_amount": net_amount,
            "tax_rate": self._extract_tax_rate(extracted_text, compact_text),
            "tax_amount": tax_amount,
            "total_with_tax": total_with_tax,
            "invoice_type": "进项发票",
            "invoice_kind": self._extract_invoice_kind(extracted_text),
        }
        return parsed

    def _parse_non_tax_payment_receipt_text(self, extracted_text: str, compact_text: str) -> dict[str, str] | None:
        if "非税收入一般缴款书" not in compact_text:
            return None
        invoice_no = self._match_text(re.compile(r"票据号码:([0-9A-Za-z]+)"), compact_text)
        issue_date = self._extract_non_tax_receipt_date(compact_text)
        total_amount = self._extract_non_tax_receipt_amount(compact_text)
        if not invoice_no or not issue_date or not total_amount:
            return None

        return {
            "invoice_code": self._match_text(re.compile(r"票据代码:([0-9A-Za-z]+)"), compact_text),
            "invoice_no": invoice_no,
            "seller_tax_no": "",
            "seller_name": self._extract_non_tax_receipt_collector(compact_text),
            "buyer_tax_no": "",
            "buyer_name": "",
            "issue_date": issue_date,
            "amount": total_amount,
            "net_amount": total_amount,
            "tax_rate": "",
            "tax_amount": "0.00",
            "total_with_tax": total_amount,
            "invoice_type": "进项发票",
            "invoice_kind": self._extract_invoice_kind(extracted_text) or "非税收入一般缴款书",
        }

    def _extract_non_tax_receipt_date(self, compact_text: str) -> str:
        match = re.search(r"填制日期:(\d{4})-(\d{2})-(\d{2})", compact_text)
        if match is None:
            return ""
        year, month, day = match.groups()
        return f"{year}-{month}-{day}"

    def _extract_non_tax_receipt_amount(self, compact_text: str) -> str:
        small_total_match = SMALL_TOTAL_RE.search(compact_text)
        if small_total_match is None:
            return ""
        return self._normalize_amount_text(small_total_match.group(1))

    @staticmethod
    def _extract_non_tax_receipt_collector(compact_text: str) -> str:
        match = re.search(r"执收单位名称:(.+?)票据号码:", compact_text)
        if match is None:
            return ""
        return clean_string(match.group(1))

    def _parse_machine_printed_invoice_text(
        self,
        extracted_text: str,
        compact_text: str,
        *,
        invoice_code: str,
        invoice_no: str,
        issue_date: str,
    ) -> dict[str, str] | None:
        if "机打发票" not in compact_text and "用机发票" not in compact_text:
            return None
        normalized_invoice_code = invoice_code or self._match_text(LOOSE_INVOICE_CODE_RE, compact_text)
        normalized_invoice_no = invoice_no or self._match_text(LOOSE_INVOICE_NO_RE, compact_text)
        total_amount = self._extract_machine_printed_total_amount(extracted_text)
        if not normalized_invoice_code or not normalized_invoice_no or not total_amount:
            return None

        names = self._extract_names_from_lines(extracted_text) or self._extract_names(compact_text)
        seller_name = names[0] if names else ""
        return {
            "invoice_code": normalized_invoice_code,
            "invoice_no": normalized_invoice_no,
            "seller_tax_no": "",
            "seller_name": seller_name,
            "buyer_tax_no": "",
            "buyer_name": "",
            "issue_date": issue_date,
            "amount": total_amount,
            "net_amount": total_amount,
            "tax_rate": "",
            "tax_amount": "0.00",
            "total_with_tax": total_amount,
            "invoice_type": "进项发票",
            "invoice_kind": self._extract_invoice_kind(extracted_text) or "通用机打发票",
        }

    def _extract_machine_printed_total_amount(self, extracted_text: str) -> str:
        for line in extracted_text.splitlines():
            normalized_line = clean_string(line).replace("：", ":")
            if "收费金额" not in normalized_line and not normalized_line.startswith("金额"):
                continue
            amount_match = re.search(r"(?:收费金额|金额):?\s*([0-9]+(?:\.\d+)?)", normalized_line)
            if amount_match is not None:
                return self._normalize_amount_text(amount_match.group(1))
        return ""

    @staticmethod
    def _match_text(pattern: re.Pattern[str], text: str) -> str:
        match = pattern.search(text)
        return clean_string(match.group(1)) if match is not None else ""

    def _extract_issue_date(self, compact_text: str) -> str:
        match = ISSUE_DATE_RE.search(compact_text) or LOOSE_ISSUE_DATE_RE.search(compact_text)
        if match is None:
            return ""
        issue_year, issue_month, issue_day = match.groups()
        return f"{issue_year}-{issue_month}-{issue_day}"

    def _extract_digital_invoice_no(self, compact_text: str) -> str:
        for match in DIGITAL_INVOICE_NO_RE.finditer(compact_text):
            candidate = clean_string(match.group(1))
            if candidate:
                return candidate
        return ""

    def _extract_names(self, compact_text: str) -> list[str]:
        names: list[str] = []
        for match in NAME_LABEL_RE.finditer(compact_text):
            segment = compact_text[match.end() : match.end() + 120]
            company_match = COMPANY_NAME_RE.search(segment)
            if company_match is None:
                continue
            company_name = clean_string(company_match.group(1))
            if company_name and company_name not in names:
                names.append(company_name)
        return names

    def _extract_names_from_lines(self, extracted_text: str) -> list[str]:
        names: list[str] = []
        for line in extracted_text.splitlines():
            normalized_line = clean_string(line)
            if (
                not normalized_line
                or "开户银行" in normalized_line
                or "国家税务总局" in normalized_line
                or "税务局" in normalized_line
                or "统一发票监" in normalized_line
            ):
                continue
            for match in COMPANY_NAME_RE.finditer(normalized_line):
                company_name = clean_string(match.group(1))
                if company_name and company_name not in names:
                    names.append(company_name)
        return names

    @staticmethod
    def _is_suspicious_company_name(value: str) -> bool:
        normalized = clean_string(value)
        return (
            not normalized
            or normalized[0].isdigit()
            or "国家税务总局" in normalized
            or "统一发票监制" in normalized
        )

    def _extract_tax_ids(self, compact_text: str) -> list[str]:
        tax_ids: list[str] = []
        for match in re.finditer(r"(?:纳税人识别号|统一社会信用代码(?:/纳税人识别号)?):", compact_text):
            segment = compact_text[match.end() : match.end() + 40]
            tax_match = TAX_ID_RE.search(segment)
            if tax_match is None:
                continue
            normalized_tax_id = self._normalize_tax_id(tax_match.group(1))
            if normalized_tax_id and normalized_tax_id not in tax_ids:
                tax_ids.append(normalized_tax_id)
        return tax_ids

    def _extract_tax_ids_from_lines(self, extracted_text: str, *, excluded_values: set[str]) -> list[str]:
        excluded = {clean_string(value).upper() for value in excluded_values if clean_string(value)}
        tax_ids: list[str] = []
        for line in extracted_text.splitlines():
            normalized_line = clean_string(line).upper()
            if not normalized_line or "银行账号" in normalized_line or "开户银行" in normalized_line:
                continue
            for match in TAX_ID_RE.finditer(normalized_line):
                normalized_tax_id = self._normalize_tax_id(match.group(1))
                if len(normalized_tax_id) != 18:
                    continue
                if normalized_tax_id in excluded or normalized_tax_id in tax_ids:
                    continue
                tax_ids.append(normalized_tax_id)
        return tax_ids

    @staticmethod
    def _normalize_tax_id(value: str) -> str:
        normalized = clean_string(value).upper()
        if len(normalized) >= 18:
            return normalized[:18]
        return normalized

    @staticmethod
    def _extract_invoice_kind(extracted_text: str) -> str:
        for line in extracted_text.splitlines():
            normalized_line = clean_string(line)
            if "非税收入一般缴款书" in normalized_line:
                return normalized_line
            if "发票" in normalized_line and "发票号码" not in normalized_line:
                return normalized_line
        return ""

    def _extract_tax_rate(self, extracted_text: str, compact_text: str) -> str:
        for line in extracted_text.splitlines():
            match = TAX_RATE_RE.search(clean_string(line))
            if match is not None:
                return clean_string(match.group(1))
        return self._match_text(TAX_RATE_RE, compact_text)

    def _extract_amount_summary(self, compact_text: str) -> tuple[str, str, str] | None:
        totals_match = TOTALS_RE.search(compact_text)
        total_with_tax = self._normalize_amount_text(self._match_text(TOTAL_WITH_TAX_RE, compact_text))
        if totals_match is not None and total_with_tax:
            return (
                self._normalize_amount_text(totals_match.group(1)),
                self._normalize_amount_text(totals_match.group(2)),
                total_with_tax,
            )

        currency_amounts = CURRENCY_AMOUNT_RE.findall(compact_text)
        if len(currency_amounts) >= 3:
            net_amount, tax_amount, total_amount = currency_amounts[-3:]
            return (
                self._normalize_amount_text(net_amount),
                self._normalize_amount_text(tax_amount),
                self._normalize_amount_text(total_amount),
            )
        if len(currency_amounts) >= 2:
            small_total_match = SMALL_TOTAL_RE.search(compact_text)
            if small_total_match is not None:
                tax_amount, net_amount = currency_amounts[-2:]
                total_amount = self._normalize_amount_text(small_total_match.group(1))
                if total_amount:
                    return (
                        self._normalize_amount_text(net_amount),
                        self._normalize_amount_text(tax_amount),
                        total_amount,
                    )
        railway_ticket_amount = self._extract_railway_ticket_amount(compact_text, currency_amounts)
        if railway_ticket_amount:
            return (railway_ticket_amount, "0.00", railway_ticket_amount)
        return None

    def _extract_railway_ticket_amount(self, compact_text: str, currency_amounts: list[str]) -> str:
        if "电子客票" not in compact_text and "铁路" not in compact_text:
            return ""
        for pattern in (r"¥([0-9]+(?:\.\d+)?)票价", r"票价[:：]?¥([0-9]+(?:\.\d+)?)"):
            match = re.search(pattern, compact_text)
            if match is not None:
                return self._normalize_amount_text(match.group(1))
        if len(currency_amounts) == 1:
            return self._normalize_amount_text(currency_amounts[0])
        return ""

    @staticmethod
    def _normalize_amount_text(value: str) -> str:
        normalized = clean_string(value)
        if not normalized:
            return ""
        normalized = normalized.replace("，", ".")
        if normalized.count(",") == 1 and "." not in normalized:
            integer_part, decimal_part = normalized.split(",", 1)
            if len(decimal_part) == 2:
                normalized = f"{integer_part}.{decimal_part}"
        if re.fullmatch(r"[0-9]+", normalized):
            normalized = f"{normalized}.00"
        return normalized

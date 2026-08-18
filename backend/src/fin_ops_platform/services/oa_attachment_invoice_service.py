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
    from rapidocr_onnxruntime import RapidOCR
except Exception:  # pragma: no cover - optional dependency fallback
    RapidOCR = None

from fin_ops_platform.services.imports import clean_string
from fin_ops_platform.services.untrusted_document_policy import (
    OA_ATTACHMENT_LIMITS,
    UntrustedDocumentError,
    ValidatedDocument,
    inspect_untrusted_document,
    normalize_image_for_ocr,
)
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy


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
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()


class OAAttachmentInvoiceService:
    PARSER_VERSION = "2026-08-16-railway-ticket-amount-v2"

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
        return [
            dict(evidence)
            for evidence in self.parse_evidences(files)
            if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence)
        ]

    def recognize_uploaded_invoice(self, *, file_name: str, content: bytes) -> dict[str, str]:
        suffix = Path(file_name).suffix.lower()
        expected_kind = (
            "jpeg" if suffix in {".jpg", ".jpeg"}
            else "png" if suffix == ".png"
            else "pdf" if suffix == ".pdf"
            else ""
        )
        document = inspect_untrusted_document(
            file_name=file_name,
            content=content,
            allowed_kinds=frozenset({expected_kind}) if expected_kind else frozenset(),
            limits=OA_ATTACHMENT_LIMITS,
        )
        if document.kind == "pdf":
            for segment in self._extract_pdf_text_segments(document):
                if evidence := self._first_invoice_evidence(segment):
                    return evidence
            return self._recognize_first_invoice_from_pdf_images(document)
        extracted_text = self._extract_image_text(document)
        return self._first_invoice_evidence(extracted_text) or {}

    def _recognize_first_invoice_from_pdf_images(self, document: ValidatedDocument) -> dict[str, str]:
        if fitz is None:
            return {}
        try:
            pdf = fitz.open(stream=document.content, filetype="pdf")
        except Exception:
            return {}
        try:
            for page in pdf:
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                    normalized_image = normalize_image_for_ocr(
                        content=pixmap.tobytes("png"),
                        limits=OA_ATTACHMENT_LIMITS,
                    )
                except (UntrustedDocumentError, ValueError):
                    continue
                extracted_text = "\n".join(self._run_image_ocr(normalized_image)).strip()
                if evidence := self._first_invoice_evidence(extracted_text):
                    return evidence
        finally:
            pdf.close()
        return {}

    def _first_invoice_evidence(self, extracted_text: str) -> dict[str, str] | None:
        if not clean_string(extracted_text):
            return None
        for evidence in self._parse_evidences_from_text(extracted_text):
            if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence):
                return dict(evidence)
        return None

    def parse_evidences(self, files: list[dict[str, object]]) -> list[dict[str, str]]:
        evidences: list[dict[str, str]] = []
        for file_entry in files:
            if not isinstance(file_entry, dict):
                continue
            parsed_evidences = [
                dict(evidence)
                for evidence in list(self.parse_file_result(file_entry).get("evidences") or [])
                if isinstance(evidence, dict)
            ]
            evidences.extend(parsed_evidences)
        return evidences

    def parse_file_result(self, file_entry: dict[str, object]) -> dict[str, object]:
        file_name = clean_string(file_entry.get("fileName") or file_entry.get("name") or "")
        file_path = clean_string(file_entry.get("filePath") or file_entry.get("url") or "")
        suffix = clean_string(file_entry.get("suffix") or Path(file_name or file_path).suffix.lstrip(".")).lower()
        base_result: dict[str, object] = {
            "attachment_name": file_name or Path(file_path).name,
            "file_path": file_path,
            "suffix": suffix,
            "parse_status": "no_evidence",
            "parse_error": "",
            "evidences": [],
        }
        if suffix not in SUPPORTED_SUFFIXES:
            base_result["parse_status"] = "unsupported_file"
            return base_result
        if not file_path:
            base_result["parse_status"] = "download_failed"
            base_result["parse_error"] = "missing_file_path"
            return base_result

        try:
            content = self._download_content(self.build_download_url(file_path))
        except Exception as exc:
            base_result["parse_status"] = "download_failed"
            base_result["parse_error"] = type(exc).__name__
            return base_result
        if content is None:
            base_result["parse_status"] = "download_failed"
            return base_result

        try:
            extracted_segments = self._extract_text_segments(
                content,
                suffix,
                file_name or Path(file_path).name,
            )
        except UntrustedDocumentError as exc:
            base_result["parse_status"] = "parse_failed"
            base_result["parse_error"] = exc.code
            return base_result
        except Exception as exc:
            base_result["parse_status"] = "parse_failed"
            base_result["parse_error"] = type(exc).__name__
            return base_result

        parsed_evidences: list[dict[str, str]] = []
        seen_keys: set[str] = set()
        attachment_name = clean_string(base_result.get("attachment_name") or "")
        for extracted_text in extracted_segments:
            if not clean_string(extracted_text):
                continue
            try:
                evidences = self._parse_evidences_from_text(extracted_text)
            except Exception as exc:
                base_result["parse_status"] = "parse_failed"
                base_result["parse_error"] = type(exc).__name__
                base_result["evidences"] = parsed_evidences
                return base_result
            for evidence in evidences:
                evidence["attachment_name"] = attachment_name
                dedupe_key = self._evidence_dedupe_key(evidence)
                if dedupe_key and dedupe_key in seen_keys:
                    continue
                if dedupe_key:
                    seen_keys.add(dedupe_key)
                parsed_evidences.append(evidence)

        base_result["evidences"] = parsed_evidences
        if parsed_evidences:
            base_result["parse_status"] = "parsed"
        elif suffix in {"jpg", "jpeg", "png"}:
            base_result["parse_status"] = "ocr_empty"
        else:
            base_result["parse_status"] = "no_evidence"
        return base_result

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
        return [
            dict(evidence)
            for evidence in self._parse_single_file_evidences(file_entry)
            if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence)
        ]

    def _parse_single_file_evidences(self, file_entry: dict[str, object]) -> list[dict[str, str]]:
        return [
            dict(evidence)
            for evidence in list(self.parse_file_result(file_entry).get("evidences") or [])
            if isinstance(evidence, dict)
        ]

    def _parse_evidences_from_text(self, extracted_text: str) -> list[dict[str, str]]:
        payment_receipt = self._parse_payment_receipt_text(extracted_text)
        if payment_receipt is not None:
            return [payment_receipt]

        compact_text = re.sub(r"[\s\u3000]+", "", extracted_text).replace("：", ":").replace("￥", "¥")
        machine_printed_invoices = self._parse_machine_printed_invoice_texts(extracted_text, compact_text)
        if machine_printed_invoices:
            return machine_printed_invoices

        parsed_invoice = self._parse_invoice_text(extracted_text)
        if parsed_invoice is None:
            return []
        return [self._invoice_to_evidence(parsed_invoice)]

    def _extract_text_segments(self, content: bytes, suffix: str, file_name: str) -> list[str]:
        expected_kind = "jpeg" if suffix in {"jpg", "jpeg"} else suffix
        document = inspect_untrusted_document(
            file_name=file_name,
            content=content,
            allowed_kinds=frozenset({expected_kind}),
            limits=OA_ATTACHMENT_LIMITS,
        )
        if document.kind == "pdf":
            return self._extract_pdf_text_segments(document)
        if document.kind == "docx":
            return self._extract_docx_text_segments(document)
        return [self._extract_image_text(document)]

    @staticmethod
    def _evidence_dedupe_key(evidence: dict[str, str]) -> str:
        evidence_type = clean_string(evidence.get("evidence_type") or "")
        if evidence_type == "payment_receipt":
            transaction_no = clean_string(evidence.get("transaction_no") or "")
            if transaction_no:
                return f"payment_receipt:transaction_no:{transaction_no}"
            merchant_order_no = clean_string(evidence.get("merchant_order_no") or "")
            if merchant_order_no:
                return f"payment_receipt:merchant_order_no:{merchant_order_no}"
            return "|".join(
                clean_string(evidence.get(key) or "")
                for key in ("evidence_type", "document_kind", "amount", "merchant_name", "paid_at", "attachment_name")
            )
        if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence):
            return OAAttachmentInvoiceService._invoice_evidence_dedupe_key(evidence)
        return "|".join(clean_string(evidence.get(key) or "") for key in sorted(evidence))

    @staticmethod
    def _invoice_evidence_dedupe_key(evidence: dict[str, str]) -> str:
        keys = OBJECT_IDENTITY_POLICY.oa_attachment_invoice_dedupe_keys(evidence)
        if not keys:
            return ""
        key_kind, key_value = keys[0]
        return f"{key_kind}:{key_value}"

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
        document = inspect_untrusted_document(
            file_name="attachment.pdf",
            content=content,
            allowed_kinds=frozenset({"pdf"}),
            limits=OA_ATTACHMENT_LIMITS,
        )
        return "\n".join(self._extract_pdf_text_segments(document)).strip()

    def _extract_pdf_text_segments(self, document: ValidatedDocument) -> list[str]:
        segments = self._extract_pdf_text_segments_with_pdfplumber(document)
        if segments:
            return segments
        return self._extract_pdf_text_segments_with_fitz(document)

    def _extract_image_text(self, document: ValidatedDocument) -> str:
        lines = self._run_image_ocr(document.ocr_content or b"")
        return "\n".join(lines).strip() if lines else ""

    def _extract_docx_text_segments(self, document: ValidatedDocument) -> list[str]:
        try:
            with ZipFile(BytesIO(document.content)) as archive:
                segments = self._extract_docx_xml_text_segments(archive)
                segments.extend(self._extract_docx_media_text_segments(archive))
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
            image_document = inspect_untrusted_document(
                file_name=image_name,
                content=document.read(image_name),
                allowed_kinds=frozenset({"jpeg", "png"}),
                limits=OA_ATTACHMENT_LIMITS,
            )
            image_text = self._extract_image_text(image_document)
            if image_text:
                segments.append(image_text)
        return segments

    @staticmethod
    def _extract_pdf_text_with_pdfplumber(content: bytes) -> str:
        document = inspect_untrusted_document(
            file_name="attachment.pdf",
            content=content,
            allowed_kinds=frozenset({"pdf"}),
            limits=OA_ATTACHMENT_LIMITS,
        )
        return "\n".join(
            OAAttachmentInvoiceService._extract_pdf_text_segments_with_pdfplumber(document)
        ).strip()

    @staticmethod
    def _extract_pdf_text_segments_with_pdfplumber(document: ValidatedDocument) -> list[str]:
        if pdfplumber is None:
            return []
        try:
            with pdfplumber.open(BytesIO(document.content)) as pdf:
                return [
                    text
                    for page in pdf.pages[: document.pdf_page_count]
                    if (text := clean_string(page.extract_text() or ""))
                ]
        except Exception:
            return []

    @staticmethod
    def _extract_pdf_text_with_fitz(content: bytes) -> str:
        document = inspect_untrusted_document(
            file_name="attachment.pdf",
            content=content,
            allowed_kinds=frozenset({"pdf"}),
            limits=OA_ATTACHMENT_LIMITS,
        )
        return "\n".join(
            OAAttachmentInvoiceService._extract_pdf_text_segments_with_fitz(document)
        ).strip()

    @staticmethod
    def _extract_pdf_text_segments_with_fitz(document: ValidatedDocument) -> list[str]:
        if fitz is None:
            return []
        try:
            pdf = fitz.open(stream=document.content, filetype="pdf")
        except Exception:
            return []
        try:
            return [
                text
                for page in pdf
                if (text := clean_string(page.get_text() or ""))
            ]
        finally:
            pdf.close()

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

    def _invoice_to_evidence(self, invoice: dict[str, str]) -> dict[str, str]:
        evidence = dict(invoice)
        invoice_kind = clean_string(evidence.get("invoice_kind") or "")
        if "非税收入一般缴款书" in invoice_kind:
            evidence_type = "non_tax_receipt"
            document_kind = "non_tax_receipt"
        elif "机打发票" in invoice_kind or "用机发票" in invoice_kind:
            evidence_type = "machine_invoice"
            document_kind = "yunnan_machine_invoice"
        elif "铁路电子客票" in invoice_kind:
            evidence_type = "tax_invoice"
            document_kind = "railway_e_ticket_invoice"
        else:
            evidence_type = "tax_invoice"
            document_kind = "digital_invoice"
        evidence.setdefault("evidence_type", evidence_type)
        evidence.setdefault("document_kind", document_kind)
        evidence.setdefault("source_region_key", "document:1")
        evidence.setdefault("invoice_type", "进项发票")
        return evidence

    def _parse_payment_receipt_text(self, extracted_text: str) -> dict[str, str] | None:
        normalized_text = extracted_text.replace("：", ":").replace("－", "-")
        compact_text = re.sub(r"[\s\u3000]+", "", normalized_text)
        if not self._looks_like_payment_receipt(compact_text):
            return None
        amount = self._extract_payment_receipt_amount(normalized_text)
        if not amount:
            return None

        merchant_name = self._extract_labeled_line_value(normalized_text, "商户全称")
        transaction_no = self._extract_labeled_line_value(normalized_text, "交易单号")
        merchant_order_no = self._extract_labeled_line_value(normalized_text, "商户单号")
        payment_method = self._extract_labeled_line_value(normalized_text, "支付方式")
        paid_at = self._extract_payment_receipt_paid_at(normalized_text)

        if not any((merchant_name, transaction_no, merchant_order_no, paid_at)):
            return None

        return {
            "evidence_type": "payment_receipt",
            "document_kind": self._payment_receipt_document_kind(compact_text),
            "amount": amount,
            "net_amount": "",
            "tax_amount": "",
            "total_with_tax": "",
            "invoice_no": "",
            "invoice_code": "",
            "digital_invoice_no": "",
            "seller_name": "",
            "buyer_name": "",
            "merchant_name": merchant_name,
            "paid_at": paid_at,
            "issue_date": paid_at[:10] if paid_at else "",
            "transaction_no": transaction_no,
            "merchant_order_no": merchant_order_no,
            "payment_method": payment_method,
            "source_region_key": "payment_receipt:1",
            "confidence": "high",
            "parse_status": "parsed",
        }

    @staticmethod
    def _looks_like_payment_receipt(compact_text: str) -> bool:
        has_receipt_marker = any(
            marker in compact_text
            for marker in ("全部账单", "支付成功", "交易单号", "商户单号", "商户全称", "财付通")
        )
        has_invoice_marker = any(marker in compact_text for marker in ("发票号码", "发票代码", "价税合计"))
        return has_receipt_marker and not has_invoice_marker

    def _extract_payment_receipt_amount(self, text: str) -> str:
        for line in text.splitlines():
            normalized_line = clean_string(line).replace("￥", "¥")
            match = re.search(r"(?<![0-9])[-]\s*¥?\s*([0-9]+(?:[.,，][0-9]{1,2})?)(?![0-9])", normalized_line)
            if match is not None:
                return self._normalize_amount_text(match.group(1))
        match = re.search(r"(?<![0-9])[-]\s*¥?\s*([0-9]+(?:[.,，][0-9]{1,2})?)(?![0-9])", text)
        return self._normalize_amount_text(match.group(1)) if match is not None else ""

    @staticmethod
    def _extract_labeled_line_value(text: str, label: str) -> str:
        for line in text.splitlines():
            normalized_line = clean_string(line).replace("：", ":")
            if not normalized_line.startswith(label):
                continue
            value = clean_string(normalized_line[len(label) :].lstrip(":"))
            if value:
                return value
        compact_text = re.sub(r"[\s\u3000]+", "", text.replace("：", ":"))
        label_index = compact_text.find(f"{label}:")
        if label_index < 0:
            label_index = compact_text.find(label)
            if label_index < 0:
                return ""
            start = label_index + len(label)
        else:
            start = label_index + len(label) + 1
        end = len(compact_text)
        for next_label in ("当前状态", "支付时间", "商品", "商户全称", "收单机构", "支付方式", "交易单号", "商户单号", "商家小程序", "账单服务"):
            next_index = compact_text.find(next_label, start)
            if next_index >= 0:
                end = min(end, next_index)
        return clean_string(compact_text[start:end])

    @staticmethod
    def _extract_payment_receipt_paid_at(text: str) -> str:
        match = re.search(
            r"支付时间[:：]?\s*(\d{4})年(\d{1,2})月(\d{1,2})日\s*(\d{1,2}:\d{2}:\d{2})",
            text,
        )
        if match is None:
            compact_text = re.sub(r"[\s\u3000]+", "", text)
            match = re.search(r"支付时间[:：]?(\d{4})年(\d{1,2})月(\d{1,2})日(\d{1,2}:\d{2}:\d{2})", compact_text)
        if match is None:
            return ""
        year, month, day, time_text = match.groups()
        return f"{year}-{int(month):02d}-{int(day):02d} {time_text}"

    @staticmethod
    def _payment_receipt_document_kind(compact_text: str) -> str:
        if any(marker in compact_text for marker in ("高速通行费", "ETC", "联网收费", "高速公路")):
            return "wechat_etc_payment"
        if any(marker in compact_text for marker in ("加油", "中国石化", "中国石油")):
            return "wechat_fuel_payment"
        if "支付宝" in compact_text:
            return "alipay_payment"
        if "财付通" in compact_text or "微信" in compact_text or "全部账单" in compact_text:
            return "wechat_payment"
        return "payment_receipt"

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
            machine_printed_invoices = self._parse_machine_printed_invoice_texts(extracted_text, compact_text)
            if machine_printed_invoices:
                return machine_printed_invoices[0]
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

    def _parse_machine_printed_invoice_texts(
        self,
        extracted_text: str,
        compact_text: str,
    ) -> list[dict[str, str]]:
        if "机打发票" not in compact_text and "用机发票" not in compact_text:
            return []

        invoice_codes = [
            clean_string(match.group(1))
            for match in LOOSE_INVOICE_CODE_RE.finditer(compact_text)
            if clean_string(match.group(1))
        ]
        invoice_numbers = [
            clean_string(match.group(1))
            for match in LOOSE_INVOICE_NO_RE.finditer(compact_text)
            if clean_string(match.group(1))
        ]
        amounts = self._extract_machine_printed_total_amounts(extracted_text, compact_text)
        if not invoice_numbers or not amounts:
            return []

        names = self._extract_names_from_lines(extracted_text) or self._extract_names(compact_text)
        seller_name = names[0] if names else ""
        issue_date = self._extract_issue_date(compact_text)
        invoice_kind = self._extract_invoice_kind(extracted_text) or "通用机打发票"
        evidences: list[dict[str, str]] = []
        for index, invoice_no in enumerate(invoice_numbers):
            invoice_code = invoice_codes[index] if index < len(invoice_codes) else (invoice_codes[0] if invoice_codes else "")
            amount = amounts[index] if index < len(amounts) else amounts[-1]
            if not invoice_code or not invoice_no or not amount:
                continue
            evidences.append(
                {
                    "evidence_type": "machine_invoice",
                    "document_kind": "yunnan_machine_invoice",
                    "invoice_code": invoice_code,
                    "invoice_no": invoice_no,
                    "seller_tax_no": "",
                    "seller_name": seller_name,
                    "buyer_tax_no": "",
                    "buyer_name": "",
                    "issue_date": issue_date,
                    "amount": amount,
                    "net_amount": amount,
                    "tax_rate": "",
                    "tax_amount": "0.00",
                    "total_with_tax": amount,
                    "invoice_type": "进项发票",
                    "invoice_kind": invoice_kind,
                    "source_region_key": f"machine_invoice:{index + 1}",
                    "confidence": "high",
                    "parse_status": "parsed",
                }
            )
        return evidences

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

    def _extract_machine_printed_total_amount(self, extracted_text: str) -> str:
        amounts = self._extract_machine_printed_total_amounts(
            extracted_text,
            re.sub(r"[\s\u3000]+", "", extracted_text).replace("：", ":").replace("￥", "¥"),
        )
        return amounts[0] if amounts else ""

    def _extract_machine_printed_total_amounts(self, extracted_text: str, compact_text: str) -> list[str]:
        amounts: list[str] = []
        for line in extracted_text.splitlines():
            normalized_line = clean_string(line).replace("：", ":")
            if "收费金额" not in normalized_line and not normalized_line.startswith("金额"):
                continue
            amount_match = re.search(r"(?:收费金额|金额):?\s*([0-9]+(?:\.\d+)?)", normalized_line)
            if amount_match is not None:
                amount = self._normalize_amount_text(amount_match.group(1))
                if amount:
                    amounts.append(amount)
        if amounts:
            return amounts
        return [
            self._normalize_amount_text(match.group(1))
            for match in re.finditer(r"(?:收费金额|金额):?([0-9]+(?:\.\d+)?)", compact_text)
            if self._normalize_amount_text(match.group(1))
        ]

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
        for pattern in (
            r"¥([0-9]+(?:\.\d{1,2})?)票价",
            r"票价[:：]?¥([0-9]+(?:\.\d{1,2})?)",
        ):
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

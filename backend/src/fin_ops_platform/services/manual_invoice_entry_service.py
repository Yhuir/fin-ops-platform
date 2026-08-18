from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
from http import HTTPStatus
import re
from typing import Any, Protocol

from fin_ops_platform.domain.enums import BatchType, ImportDecision
from fin_ops_platform.services.import_file_service import FileImportSession


CENT = Decimal("0.01")
HUNDRED = Decimal("100")
MANUAL_INVOICE_SOURCE = "manual_invoice_entry"
TWENTY_DIGIT_INVOICE_RE = re.compile(r"^\d{20}$")


class ManualInvoiceEntryError(ValueError):
    def __init__(self, error: str, message: str, *, status_code: HTTPStatus = HTTPStatus.BAD_REQUEST) -> None:
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code


class ManualInvoiceImportPort(Protocol):
    def preview_manual_invoice_entries(
        self,
        *,
        imported_by: str,
        entries: list[tuple[BatchType, dict[str, Any]]],
    ) -> FileImportSession: ...

    def discard_session(self, *, session_id: str, imported_by: str) -> FileImportSession: ...


class InvoiceDocumentRecognizerPort(Protocol):
    def recognize_uploaded_invoice(self, *, file_name: str, content: bytes) -> dict[str, str]: ...


@dataclass(frozen=True, slots=True)
class ManualInvoiceEntryBatchPreview:
    session: FileImportSession
    file_ids: list[str]
    values: list[dict[str, str]]


class ManualInvoiceEntryService:
    def __init__(
        self,
        *,
        file_import_service: ManualInvoiceImportPort,
        document_recognizer: InvoiceDocumentRecognizerPort,
    ) -> None:
        self._file_import_service = file_import_service
        self._document_recognizer = document_recognizer

    def recognize(self, *, file_name: str, content: bytes) -> dict[str, str]:
        try:
            evidence = self._document_recognizer.recognize_uploaded_invoice(
                file_name=file_name,
                content=content,
            )
        except ValueError as exc:
            code = str(getattr(exc, "code", "") or str(exc) or "invoice_recognition_failed")
            raise ManualInvoiceEntryError(code, self._recognition_error_message(code)) from exc
        if not isinstance(evidence, dict):
            return {}
        invoice_no = self._text(evidence.get("digital_invoice_no") or evidence.get("invoice_no"))
        return {
            "seller_name": self._text(evidence.get("seller_name")),
            "seller_tax_no": self._text(evidence.get("seller_tax_no")),
            "buyer_name": self._text(evidence.get("buyer_name")),
            "buyer_tax_no": self._text(evidence.get("buyer_tax_no")),
            "invoice_number": invoice_no,
            "invoice_code": self._text(evidence.get("invoice_code")),
            "invoice_date": self._text(evidence.get("issue_date") or evidence.get("invoice_date")),
            "net_amount": self._text(evidence.get("net_amount") or evidence.get("amount")),
            "tax_rate": self._text(evidence.get("tax_rate")).removesuffix("%"),
            "tax_amount": self._text(evidence.get("tax_amount")),
            "total_with_tax": self._text(evidence.get("total_with_tax")),
        }

    def preview_batch(
        self,
        *,
        payloads: list[dict[str, Any]],
        imported_by: str,
    ) -> ManualInvoiceEntryBatchPreview:
        if not payloads:
            raise ManualInvoiceEntryError("manual_invoice_batch_empty", "请至少录入一张发票。")
        normalized_entries = [self._normalize_payload(payload) for payload in payloads]
        identities: set[tuple[str, str, str, str, str]] = set()
        for values, _row, _batch_type in normalized_entries:
            identity = (
                values["invoice_direction"],
                values["invoice_number"],
                values["invoice_code"],
                values["seller_tax_no"],
                values["buyer_tax_no"],
            )
            if identity in identities:
                raise ManualInvoiceEntryError(
                    "manual_invoice_batch_duplicate",
                    "本次录入中存在重复发票，请修改或删除重复项后再提交。",
                    status_code=HTTPStatus.CONFLICT,
                )
            identities.add(identity)
        session = self._file_import_service.preview_manual_invoice_entries(
            imported_by=imported_by,
            entries=[(batch_type, row) for _values, row, batch_type in normalized_entries],
        )
        invalid_result = next(
            (
                row_result
                for file_item in session.files
                for row_result in file_item.row_results
                if row_result.decision != ImportDecision.CREATED
            ),
            None,
        )
        if invalid_result is not None:
            self._file_import_service.discard_session(session_id=session.id, imported_by=imported_by)
            if invalid_result.decision == ImportDecision.DUPLICATE_SKIPPED:
                raise ManualInvoiceEntryError(
                    "manual_invoice_duplicate",
                    "批次中有发票已存在于统一发票池，整批未录入。",
                    status_code=HTTPStatus.CONFLICT,
                )
            if invalid_result.decision == ImportDecision.SUSPECTED_DUPLICATE:
                raise ManualInvoiceEntryError(
                    "manual_invoice_suspected_duplicate",
                    "批次中有发票与现有记录高度相似，整批未录入。",
                    status_code=HTTPStatus.CONFLICT,
                )
            raise ManualInvoiceEntryError(
                "manual_invoice_invalid",
                invalid_result.decision_reason or "批次中有发票未通过导入校验，整批未录入。",
            )
        return ManualInvoiceEntryBatchPreview(
            session=session,
            file_ids=[item.id for item in session.files],
            values=[values for values, _row, _batch_type in normalized_entries],
        )

    def _normalize_payload(
        self,
        payload: dict[str, Any],
    ) -> tuple[dict[str, str], dict[str, str], BatchType]:
        direction = self._choice(payload, "invoice_direction", {"input", "output"}, "请选择票据方向。")
        nature = self._choice(payload, "invoice_nature", {"blue", "red"}, "请选择发票性质。")
        seller_name = self._required_text(payload, "seller_name", "请填写销方名称。")
        seller_tax_no = self._required_text(payload, "seller_tax_no", "请填写销方识别号。").upper()
        buyer_name = self._required_text(payload, "buyer_name", "请填写购方名称。")
        buyer_tax_no = self._required_text(payload, "buyer_tax_no", "请填写购方识别号。").upper()
        invoice_number = self._required_text(payload, "invoice_number", "请填写发票号码。")
        invoice_code = self._text(payload.get("invoice_code"))
        is_digital_invoice = bool(TWENTY_DIGIT_INVOICE_RE.fullmatch(invoice_number))
        if not is_digital_invoice and not invoice_code:
            raise ManualInvoiceEntryError("manual_invoice_code_required", "传统发票必须填写发票代码。")

        invoice_date = self._required_text(payload, "invoice_date", "请选择开票日期。")
        try:
            date.fromisoformat(invoice_date)
        except ValueError as exc:
            raise ManualInvoiceEntryError("manual_invoice_date_invalid", "开票日期格式不正确。") from exc

        net_amount = self._money(payload, "net_amount", "不含税价格", allow_zero=False)
        tax_amount = self._money(payload, "tax_amount", "税额", allow_zero=True)
        total_with_tax = self._money(payload, "total_with_tax", "价税合计", allow_zero=False)
        if net_amount + tax_amount != total_with_tax:
            raise ManualInvoiceEntryError(
                "manual_invoice_amounts_unbalanced",
                "价税合计必须等于不含税价格与税额之和。",
            )
        tax_rate = self._rate(payload.get("tax_rate"))
        sign = Decimal("-1") if nature == "red" else Decimal("1")
        signed_net_amount = (net_amount * sign).quantize(CENT)
        signed_tax_amount = (tax_amount * sign).quantize(CENT)
        signed_total = (total_with_tax * sign).quantize(CENT)
        normalized_rate = self._decimal_text(tax_rate)
        values = {
            "invoice_direction": direction,
            "invoice_nature": nature,
            "seller_name": seller_name,
            "seller_tax_no": seller_tax_no,
            "buyer_name": buyer_name,
            "buyer_tax_no": buyer_tax_no,
            "invoice_number": invoice_number,
            "invoice_code": invoice_code,
            "invoice_date": invoice_date,
            "net_amount": self._money_text(net_amount),
            "tax_rate": normalized_rate,
            "tax_amount": self._money_text(tax_amount),
            "total_with_tax": self._money_text(total_with_tax),
        }
        row = {
            "counterparty_name": seller_name if direction == "input" else buyer_name,
            "invoice_code": invoice_code,
            "invoice_no": "" if is_digital_invoice else invoice_number,
            "digital_invoice_no": invoice_number if is_digital_invoice else "",
            "invoice_date": invoice_date,
            "amount": self._money_text(signed_net_amount),
            "tax_amount": self._money_text(signed_tax_amount),
            "total_with_tax": self._money_text(signed_total),
            "tax_rate": f"{normalized_rate}%",
            "seller_name": seller_name,
            "seller_tax_no": seller_tax_no,
            "buyer_name": buyer_name,
            "buyer_tax_no": buyer_tax_no,
            "invoice_source": MANUAL_INVOICE_SOURCE,
            "is_positive_invoice": "否" if nature == "red" else "是",
            "tags": ["人工录入", "红字发票" if nature == "red" else "蓝字发票"],
        }
        batch_type = BatchType.INPUT_INVOICE if direction == "input" else BatchType.OUTPUT_INVOICE
        return values, row, batch_type

    @staticmethod
    def _recognition_error_message(code: str) -> str:
        if code in {"document_format_not_allowed", "document_signature_mismatch", "document_signature_invalid"}:
            return "仅支持有效的 JPG、JPEG 或 PDF 发票文件。"
        if code in {"document_too_large", "document_image_too_large", "document_pdf_render_too_large"}:
            return "文件过大，无法安全解析。"
        if code in {"document_pdf_too_many_pages"}:
            return "PDF 页数超过解析上限。"
        return "发票文件解析失败，请改用手工录入。"

    @staticmethod
    def _choice(payload: dict[str, Any], key: str, choices: set[str], message: str) -> str:
        value = ManualInvoiceEntryService._text(payload.get(key)).lower()
        if value not in choices:
            raise ManualInvoiceEntryError(f"manual_{key}_invalid", message)
        return value

    @staticmethod
    def _required_text(payload: dict[str, Any], key: str, message: str) -> str:
        value = ManualInvoiceEntryService._text(payload.get(key))
        if not value:
            raise ManualInvoiceEntryError(f"manual_{key}_required", message)
        return value

    @staticmethod
    def _money(payload: dict[str, Any], key: str, label: str, *, allow_zero: bool) -> Decimal:
        try:
            value = Decimal(ManualInvoiceEntryService._text(payload.get(key))).quantize(CENT)
        except (InvalidOperation, ValueError) as exc:
            raise ManualInvoiceEntryError(f"manual_{key}_invalid", f"{label}必须是有效数字。") from exc
        if value < 0 or (not allow_zero and value == 0):
            qualifier = "非负数" if allow_zero else "正数"
            raise ManualInvoiceEntryError(f"manual_{key}_invalid", f"{label}必须填写{qualifier}。")
        return value

    @staticmethod
    def _rate(value: Any) -> Decimal:
        normalized = ManualInvoiceEntryService._text(value).removesuffix("%")
        try:
            rate = Decimal(normalized)
        except (InvalidOperation, ValueError) as exc:
            raise ManualInvoiceEntryError("manual_tax_rate_invalid", "税率必须是 0 到 100 之间的数字。") from exc
        if rate < 0 or rate > HUNDRED:
            raise ManualInvoiceEntryError("manual_tax_rate_invalid", "税率必须是 0 到 100 之间的数字。")
        return rate.normalize()

    @staticmethod
    def _text(value: Any) -> str:
        return str(value or "").strip()

    @staticmethod
    def _money_text(value: Decimal) -> str:
        return format(value, ".2f")

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value, "f").rstrip("0").rstrip(".") or "0"

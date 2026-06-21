from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Protocol

from fin_ops_platform.domain.models import Invoice
from fin_ops_platform.services.invoice_identity_service import InvoiceIdentityService


LINK_EXISTING_INVOICE = "link_existing_invoice"
CREATE_INVOICE_AND_LINK = "create_invoice_and_link"
IGNORE = "ignore"


@dataclass(frozen=True, slots=True)
class InvoiceAttachmentRecognitionDecision:
    action: str
    reason: str
    identity_key: str | None = None
    invoice: Invoice | None = None

    @property
    def allow_create(self) -> bool:
        return self.action == CREATE_INVOICE_AND_LINK


class InvoiceIdentityRepository(Protocol):
    def find_invoice_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> Invoice | None:
        ...

    def find_invoices_by_identity(
        self,
        *,
        canonical_key: str | None = None,
        suspected_key: str | None = None,
    ) -> list[Invoice]:
        ...


class InvoiceAttachmentRecognitionService:
    """Decide whether an OA attachment may affect the unified invoice pool."""

    _NON_FORMAL_EVIDENCE_TYPES = frozenset(
        {
            "bank_receipt",
            "non_tax_receipt",
            "payment_receipt",
            "receipt",
            "traffic_ticket",
        }
    )
    _FORMAL_EVIDENCE_TYPES = frozenset({"machine_invoice", "tax_invoice"})
    _FORMAL_DOCUMENT_KINDS = frozenset(
        {
            "digital_invoice",
            "railway_e_ticket_invoice",
            "yunnan_machine_invoice",
        }
    )
    _NON_FORMAL_KEYWORDS = (
        "付款凭证",
        "公安局交通管理",
        "缴款书",
        "罚款",
        "罚没",
        "财政票据",
        "交通管理支队",
        "交通违法",
        "收据",
        "非税",
        "银行回单",
    )
    _PLACEHOLDER_VALUES = frozenset({"", "-", "--", "—", "无", "暂无", "null", "none", "n/a", "nan"})

    def __init__(
        self,
        *,
        invoice_repository: InvoiceIdentityRepository,
        invoice_identity_service: InvoiceIdentityService | None = None,
    ) -> None:
        self._invoice_repository = invoice_repository
        self._invoice_identity_service = invoice_identity_service or InvoiceIdentityService()

    def decide(self, attachment_invoice: dict[str, Any]) -> InvoiceAttachmentRecognitionDecision:
        normalized = self._normalize_candidate(attachment_invoice)
        if normalized is None:
            return InvoiceAttachmentRecognitionDecision(action=IGNORE, reason="not_formal_invoice")

        identity_key = self._strong_identity_key(normalized)
        if not identity_key:
            return InvoiceAttachmentRecognitionDecision(action=IGNORE, reason="missing_strong_invoice_identity")

        existing_matches = self._find_existing_invoices(identity_key)
        if len(existing_matches) > 1:
            return InvoiceAttachmentRecognitionDecision(
                action=IGNORE,
                reason="ambiguous_invoice_identity",
                identity_key=identity_key,
            )
        existing = existing_matches[0] if existing_matches else None
        if existing is not None:
            return InvoiceAttachmentRecognitionDecision(
                action=LINK_EXISTING_INVOICE,
                reason="matched_existing_invoice",
                identity_key=identity_key,
                invoice=existing,
            )

        if not self._has_minimum_create_fields(normalized):
            return InvoiceAttachmentRecognitionDecision(
                action=IGNORE,
                reason="missing_required_invoice_fields",
                identity_key=identity_key,
            )

        return InvoiceAttachmentRecognitionDecision(
            action=CREATE_INVOICE_AND_LINK,
            reason="formal_invoice_not_in_pool",
            identity_key=identity_key,
        )

    def _find_existing_invoices(self, identity_key: str) -> list[Invoice]:
        finder = getattr(self._invoice_repository, "find_invoices_by_identity", None)
        if callable(finder):
            return [
                invoice
                for invoice in list(finder(canonical_key=identity_key, suspected_key=None) or [])
                if isinstance(invoice, Invoice)
            ]
        existing = self._invoice_repository.find_invoice_by_identity(
            canonical_key=identity_key,
            suspected_key=None,
        )
        return [existing] if existing is not None else []

    def _normalize_candidate(self, attachment_invoice: dict[str, Any]) -> dict[str, Any] | None:
        if not isinstance(attachment_invoice, dict):
            return None
        evidence_type = self._clean(attachment_invoice.get("evidence_type"))
        document_kind = self._clean(attachment_invoice.get("document_kind"))
        if evidence_type in self._NON_FORMAL_EVIDENCE_TYPES or document_kind in self._NON_FORMAL_EVIDENCE_TYPES:
            return None
        if evidence_type and evidence_type not in self._FORMAL_EVIDENCE_TYPES:
            return None
        if not evidence_type and not self._is_formal_document_kind(document_kind):
            return None

        text_fields = (
            attachment_invoice.get("invoice_kind"),
            attachment_invoice.get("document_kind"),
            attachment_invoice.get("seller_name"),
            attachment_invoice.get("buyer_name"),
            attachment_invoice.get("issuer"),
            attachment_invoice.get("remark"),
            attachment_invoice.get("taxable_item_name"),
        )
        haystack = " ".join(str(value or "") for value in text_fields)
        if any(keyword in haystack for keyword in self._NON_FORMAL_KEYWORDS):
            return None

        normalized = dict(attachment_invoice)
        invoice_no = self._clean(normalized.get("invoice_no"))
        digital_invoice_no = self._clean(normalized.get("digital_invoice_no"))
        if not digital_invoice_no and invoice_no and invoice_no.isdigit() and len(invoice_no) == 20:
            normalized["digital_invoice_no"] = invoice_no
        return normalized

    def _is_formal_document_kind(self, document_kind: str | None) -> bool:
        if not document_kind:
            return False
        if document_kind in self._FORMAL_DOCUMENT_KINDS:
            return True
        return "发票" in document_kind or "电子客票" in document_kind

    def _strong_identity_key(self, values: dict[str, Any]) -> str | None:
        digital_invoice_no = self._clean(values.get("digital_invoice_no"))
        if digital_invoice_no:
            return self._invoice_identity_service.canonical_key_for_mapping(
                {
                    "digital_invoice_no": digital_invoice_no,
                }
            )

        invoice_code = self._clean(values.get("invoice_code"))
        invoice_no = self._clean(values.get("invoice_no"))
        if invoice_code and invoice_no:
            return self._invoice_identity_service.canonical_key_for_mapping(
                {
                    "invoice_code": invoice_code,
                    "invoice_no": invoice_no,
                }
            )
        return None

    def _has_minimum_create_fields(self, values: dict[str, Any]) -> bool:
        issue_date = self._clean(values.get("issue_date") or values.get("invoice_date"))
        amount = self._format_amount(
            values.get("total_with_tax")
            or values.get("amount")
            or values.get("net_amount")
        )
        seller_name = self._clean(values.get("seller_name"))
        buyer_name = self._clean(values.get("buyer_name"))
        return bool(issue_date and amount and (seller_name or buyer_name))

    def _clean(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        if text.lower() in self._PLACEHOLDER_VALUES:
            return None
        return text or None

    @staticmethod
    def _format_amount(value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{Decimal(str(value)).quantize(Decimal('0.01'))}"
        except (InvalidOperation, ValueError):
            return None

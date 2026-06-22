from __future__ import annotations

from typing import Any


class EtcBatchInvoiceLinkService:
    """Persist ETC business batch membership for canonical invoices."""

    def __init__(self, *, repository: Any) -> None:
        self._repository = repository

    def link_submitted_invoice(
        self,
        *,
        invoice: Any,
        etc_invoice: Any,
        link_source: str = "formal_invoice_import",
        confidence: str = "strict",
        raw_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        upsert = getattr(self._repository, "upsert_etc_batch_invoice_link", None)
        if not callable(upsert):
            return None
        invoice_id = self._text(getattr(invoice, "id", None))
        if not invoice_id:
            raise ValueError("invoice id is required for ETC batch invoice link")
        business_batch_id = self._business_batch_id(etc_invoice)
        if not business_batch_id:
            raise ValueError("business batch id is required for ETC batch invoice link")
        invoice_no = self._text(
            getattr(invoice, "digital_invoice_no", None)
            or getattr(invoice, "invoice_no", None)
            or getattr(etc_invoice, "invoice_number", None)
        )
        invoice_code = self._text(getattr(invoice, "invoice_code", None))
        digital_invoice_no = self._text(getattr(invoice, "digital_invoice_no", None))
        if not invoice_no and not digital_invoice_no and not invoice_code:
            raise ValueError("invoice identity is required for ETC batch invoice link")
        return upsert(
            invoice_id=invoice_id,
            business_batch_id=business_batch_id,
            etc_invoice_id=self._text(getattr(etc_invoice, "id", None)),
            invoice_no=invoice_no,
            invoice_code=invoice_code,
            digital_invoice_no=digital_invoice_no,
            invoice_date=self._text(getattr(invoice, "invoice_date", None) or getattr(etc_invoice, "issue_date", None)),
            link_source=self._text(link_source) or "formal_invoice_import",
            confidence=self._text(confidence) or "strict",
            raw_payload=raw_payload or {},
        )

    @classmethod
    def _business_batch_id(cls, etc_invoice: Any) -> str | None:
        return cls._text(
            getattr(etc_invoice, "business_batch_id", None)
            or getattr(etc_invoice, "current_batch_id", None)
            or getattr(etc_invoice, "last_batch_id", None)
        )

    @staticmethod
    def _text(value: Any) -> str | None:
        text = str(value or "").strip()
        return text or None


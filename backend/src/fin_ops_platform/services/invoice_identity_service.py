from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any


CENT = Decimal("0.01")


@dataclass(frozen=True, slots=True)
class InvoiceIdentityResult:
    canonical_key: str | None
    suspected_key: str | None = None


class InvoiceIdentityService:
    def identity_for_mapping(self, values: dict[str, Any]) -> InvoiceIdentityResult:
        canonical_key = self.canonical_key_for_mapping(values)
        suspected_key = None if canonical_key else self.suspected_key_for_mapping(values)
        return InvoiceIdentityResult(canonical_key=canonical_key, suspected_key=suspected_key)

    def canonical_key_for_invoice(self, invoice: Any) -> str | None:
        return self.canonical_key_for_mapping(
            {
                "digital_invoice_no": getattr(invoice, "digital_invoice_no", None),
                "invoice_code": getattr(invoice, "invoice_code", None),
                "invoice_no": getattr(invoice, "invoice_no", None),
                "seller_tax_no": getattr(invoice, "seller_tax_no", None),
                "buyer_tax_no": getattr(invoice, "buyer_tax_no", None),
                "invoice_date": getattr(invoice, "invoice_date", None),
                "total_with_tax": getattr(invoice, "total_with_tax", None),
            }
        )

    def canonical_key_for_mapping(self, values: dict[str, Any]) -> str | None:
        digital_invoice_no = self._clean(values.get("digital_invoice_no"))
        if digital_invoice_no:
            return digital_invoice_no

        invoice_code = self._clean(values.get("invoice_code"))
        invoice_no = self._clean(values.get("invoice_no"))
        if invoice_code and invoice_no:
            return f"{invoice_code}:{invoice_no}"

        seller_tax_no = self._clean(values.get("seller_tax_no"))
        buyer_tax_no = self._clean(values.get("buyer_tax_no"))
        invoice_date = self._clean(values.get("invoice_date"))
        total_with_tax = self._format_amount(values.get("total_with_tax"))
        if seller_tax_no and buyer_tax_no and invoice_date and total_with_tax:
            return f"tax:{seller_tax_no}:{buyer_tax_no}:{invoice_date}:{total_with_tax}"

        return None

    def suspected_key_for_mapping(self, values: dict[str, Any]) -> str | None:
        seller_name = self._clean(values.get("seller_name"))
        buyer_name = self._clean(values.get("buyer_name"))
        invoice_date = self._clean(values.get("invoice_date"))
        total_with_tax = self._format_amount(values.get("total_with_tax"))
        if seller_name and buyer_name and invoice_date and total_with_tax:
            return f"suspected:{seller_name}:{buyer_name}:{invoice_date}:{total_with_tax}"
        return None

    @staticmethod
    def _clean(value: Any) -> str | None:
        if value in (None, ""):
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _format_amount(value: Any) -> str | None:
        if value in (None, ""):
            return None
        try:
            return f"{Decimal(str(value)).quantize(CENT)}"
        except (InvalidOperation, ValueError):
            return None

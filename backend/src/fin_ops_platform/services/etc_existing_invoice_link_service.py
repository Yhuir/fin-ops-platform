from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class EtcExistingInvoiceLinkService:
    """Link ETC metadata to invoices that already exist in the canonical pool."""

    def __init__(
        self,
        *,
        import_service: Any,
        etc_service: Any | None = None,
        persist_linked_invoices: Callable[[list[Any]], None] | None = None,
    ) -> None:
        self._import_service = import_service
        self._etc_service = etc_service
        self._persist_linked_invoices = persist_linked_invoices

    def link_import_result_to_existing_invoices(self, result: Any) -> list[str]:
        return self.link_etc_invoices_to_existing_invoices(self._etc_invoices_from_import_result(result))

    def link_etc_invoices_to_existing_invoices(self, etc_invoices: list[Any]) -> list[str]:
        changed_months: set[str] = set()
        linked_invoices: list[Any] = []
        for etc_invoice in list(etc_invoices or []):
            invoice = self._import_service.upsert_etc_invoice(etc_invoice)
            if invoice is not None:
                linked_invoices.append(invoice)
            for date_value in (
                getattr(invoice, "invoice_date", None) if invoice is not None else None,
                getattr(etc_invoice, "issue_date", None),
                getattr(etc_invoice, "passage_start_date", None),
                getattr(etc_invoice, "passage_end_date", None),
            ):
                if isinstance(date_value, str) and MONTH_RE.match(date_value[:7]):
                    changed_months.add(date_value[:7])
        if linked_invoices and self._persist_linked_invoices is not None:
            self._persist_linked_invoices(linked_invoices)
        return sorted(changed_months)

    def _etc_invoices_from_import_result(self, result: Any) -> list[Any]:
        direct_invoices = list(getattr(result, "invoices", None) or getattr(result, "imported_invoices", None) or [])
        if direct_invoices:
            return direct_invoices
        list_invoices_by_numbers = getattr(self._etc_service, "list_invoices_by_numbers", None)
        if not callable(list_invoices_by_numbers):
            return []
        invoice_numbers: list[str] = []
        seen: set[str] = set()
        for item in list(getattr(result, "items", None) or []):
            invoice_number = str(getattr(item, "invoice_number", "") or "").strip()
            if not invoice_number or invoice_number in seen:
                continue
            invoice_numbers.append(invoice_number)
            seen.add(invoice_number)
        if not invoice_numbers:
            return []
        return list(list_invoices_by_numbers(invoice_numbers) or [])

from __future__ import annotations

from typing import Callable


class WorkbenchOaPayloadBuilder:
    """Builds the OA-source Workbench raw payload through explicit ports."""

    def __init__(
        self,
        *,
        use_retained_all_payload: Callable[[str], bool],
        build_retained_all_oa_row_payload: Callable[[], dict[str, object]],
        get_workbench_payload: Callable[[str], object],
        serialize_value: Callable[[object], object],
        is_month_scope: Callable[[str], bool],
        promote_oa_attachment_invoices_to_canonical: Callable[[set[str]], int],
        append_canonical_oa_attachment_invoice_rows: Callable[[dict[str, object]], None],
    ) -> None:
        self._use_retained_all_payload = use_retained_all_payload
        self._build_retained_all_oa_row_payload = build_retained_all_oa_row_payload
        self._get_workbench_payload = get_workbench_payload
        self._serialize_value = serialize_value
        self._is_month_scope = is_month_scope
        self._promote_oa_attachment_invoices_to_canonical = promote_oa_attachment_invoices_to_canonical
        self._append_canonical_oa_attachment_invoice_rows = append_canonical_oa_attachment_invoice_rows

    def build(self, month: str) -> dict[str, object]:
        if self._use_retained_all_payload(month):
            payload = self._build_retained_all_oa_row_payload()
        else:
            serialized = self._serialize_value(self._get_workbench_payload(month))
            payload = serialized if isinstance(serialized, dict) else {}
            if self._is_month_scope(month):
                self._promote_oa_attachment_invoices_to_canonical({month})
        self._append_canonical_oa_attachment_invoice_rows(payload)
        return payload

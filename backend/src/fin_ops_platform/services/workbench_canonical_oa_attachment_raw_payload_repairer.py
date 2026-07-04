from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.oa_attachment_invoice_linking import oa_row_source_ids


class WorkbenchCanonicalOaAttachmentRawPayloadRepairer:
    """Appends or replaces canonical OA attachment invoice rows in raw payloads."""

    def __init__(
        self,
        *,
        list_invoices: Callable[[], list[object]],
        source_link_for_invoice: Callable[[object, set[str]], dict[str, str] | None],
        source_oa_id_for_attachment_link: Callable[[dict[str, str], set[str]], str | None],
        canonical_oa_attachment_invoice_row: Callable[..., dict[str, object]],
        replace_raw_workbench_row: Callable[..., bool],
        dedupe_raw_workbench_rows_by_id: Callable[..., None],
        refresh_raw_workbench_payload_summary: Callable[[dict[str, object]], None],
    ) -> None:
        self._list_invoices = list_invoices
        self._source_link_for_invoice = source_link_for_invoice
        self._source_oa_id_for_attachment_link = source_oa_id_for_attachment_link
        self._canonical_oa_attachment_invoice_row = canonical_oa_attachment_invoice_row
        self._replace_raw_workbench_row = replace_raw_workbench_row
        self._dedupe_raw_workbench_rows_by_id = dedupe_raw_workbench_rows_by_id
        self._refresh_raw_workbench_payload_summary = refresh_raw_workbench_payload_summary

    def repair(self, payload: dict[str, object]) -> None:
        oa_rows_by_id: dict[str, dict[str, object]] = {}
        oa_sections_by_id: dict[str, str] = {}
        existing_invoice_row_ids: set[str] = set()
        for section_name in ("paired", "open"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            for oa_row in list(section_payload.get("oa") or []):
                if not isinstance(oa_row, dict):
                    continue
                oa_row_id = str(oa_row.get("id", "")).strip()
                if not oa_row_id or oa_row_id in oa_rows_by_id:
                    continue
                oa_rows_by_id[oa_row_id] = oa_row
                oa_sections_by_id[oa_row_id] = section_name
            for invoice_row in list(section_payload.get("invoice") or []):
                if isinstance(invoice_row, dict) and str(invoice_row.get("id", "")).strip():
                    existing_invoice_row_ids.add(str(invoice_row.get("id", "")).strip())

        if not oa_rows_by_id:
            return

        appended = 0
        changed = False
        oa_source_id_to_row_id: dict[str, str] = {}
        for oa_row_id in sorted(oa_rows_by_id):
            oa_row = oa_rows_by_id[oa_row_id]
            for source_id in oa_row_source_ids(oa_row) or [oa_row_id]:
                oa_source_id_to_row_id.setdefault(source_id, oa_row_id)
        oa_row_ids = set(oa_source_id_to_row_id)
        for invoice in self._list_invoices():
            invoice_id = str(getattr(invoice, "id", "") or "").strip()
            if not invoice_id:
                continue
            source_link = self._source_link_for_invoice(invoice, oa_row_ids)
            if source_link is None:
                continue
            source_oa_id = self._source_oa_id_for_attachment_link(source_link, oa_row_ids)
            if source_oa_id is None:
                continue
            source_oa_id = oa_source_id_to_row_id.get(source_oa_id, source_oa_id)
            if source_oa_id not in oa_rows_by_id:
                continue
            row = self._canonical_oa_attachment_invoice_row(
                invoice,
                source_link=source_link,
                oa_row=oa_rows_by_id[source_oa_id],
            )
            if invoice_id in existing_invoice_row_ids:
                if self._replace_raw_workbench_row(payload, row_type="invoice", replacement=row):
                    changed = True
                continue
            section_name = oa_sections_by_id.get(source_oa_id, "open")
            section_payload = payload.setdefault(section_name, {})
            if not isinstance(section_payload, dict):
                continue
            invoice_rows = section_payload.setdefault("invoice", [])
            if not isinstance(invoice_rows, list):
                continue
            invoice_rows.append(row)
            existing_invoice_row_ids.add(invoice_id)
            appended += 1
            changed = True

        if appended or changed:
            self._dedupe_raw_workbench_rows_by_id(payload, row_type="invoice")
            self._refresh_raw_workbench_payload_summary(payload)

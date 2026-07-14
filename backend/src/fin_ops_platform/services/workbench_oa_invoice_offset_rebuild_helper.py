from __future__ import annotations

from typing import Callable


class WorkbenchOaInvoiceOffsetRebuildHelper:
    """Detects cached Workbench payloads missing OA invoice offset metadata."""

    def __init__(
        self,
        *,
        applicant_names_provider: Callable[[], list[str]],
        attachment_matches_oa: Callable[[dict[str, object], object], bool],
        offset_tag: str,
    ) -> None:
        self._applicant_names_provider = applicant_names_provider
        self._attachment_matches_oa = attachment_matches_oa
        self._offset_tag = offset_tag

    def cached_payload_needs_rebuild(self, payload: dict[str, object]) -> bool:
        applicant_names = self._applicant_names()
        if not applicant_names:
            return False
        for section in ("paired", "unpaired"):
            section_payload = payload.get(section, {})
            if not isinstance(section_payload, dict):
                continue
            for group in list(section_payload.get("groups", [])):
                if not isinstance(group, dict):
                    continue
                oa_rows = [row for row in list(group.get("oa_rows", [])) if isinstance(row, dict)]
                invoice_rows = [row for row in list(group.get("invoice_rows", [])) if isinstance(row, dict)]
                for oa_row in oa_rows:
                    if str(oa_row.get("applicant", "")).strip() not in applicant_names:
                        continue
                    if not self.attachment_invoice_rows_for_oa(oa_row, invoice_rows):
                        continue
                    if section == "unpaired":
                        return True
                    for row in [*oa_rows, *invoice_rows]:
                        tags = {str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()}
                        if self._offset_tag not in tags or not bool(row.get("cost_excluded")):
                            return True
        return False

    def attachment_invoice_rows_for_oa(
        self,
        oa_row: dict[str, object],
        invoice_rows: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        oa_row_id = str(oa_row.get("id", "")).strip()
        matches: list[dict[str, object]] = []
        for invoice_row in invoice_rows:
            if str(invoice_row.get("source_kind", "")) != "oa_attachment_invoice":
                continue
            if self._attachment_matches_oa(invoice_row, oa_row_id):
                matches.append(invoice_row)
        return matches

    def _applicant_names(self) -> set[str]:
        return {
            str(name).strip()
            for name in self._applicant_names_provider()
            if str(name).strip()
        }

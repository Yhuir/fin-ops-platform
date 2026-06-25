from __future__ import annotations

from typing import Callable


class WorkbenchOaAttachmentContextRowIndex:
    """Indexes raw Workbench rows and maps OA attachment invoice rows to OA rows."""

    def __init__(
        self,
        *,
        attachment_parent_oa_id: Callable[[object], str],
        attachment_matches_oa: Callable[[dict[str, object], object], bool],
        attachment_row_id_matches_oa: Callable[[str, str], bool],
    ) -> None:
        self._attachment_parent_oa_id = attachment_parent_oa_id
        self._attachment_matches_oa = attachment_matches_oa
        self._attachment_row_id_matches_oa = attachment_row_id_matches_oa

    def raw_payload_rows_by_id(self, payload: dict[str, object]) -> dict[str, dict[str, object]]:
        rows_by_id: dict[str, dict[str, object]] = {}
        for section_name in ("paired", "open"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            for pane in ("oa", "bank", "invoice"):
                for row in list(section_payload.get(pane) or []):
                    if not isinstance(row, dict):
                        continue
                    row_id = str(row.get("id") or "").strip()
                    if row_id:
                        rows_by_id[row_id] = row
        return rows_by_id

    def attachment_row_ids_by_oa_id(
        self,
        rows_by_id: dict[str, dict[str, object]],
    ) -> dict[str, list[str]]:
        attachment_row_ids_by_oa_id: dict[str, list[str]] = {}
        oa_row_ids = {
            row_id
            for row_id, row in rows_by_id.items()
            if str(row.get("type") or "").strip() == "oa"
        }
        if not oa_row_ids:
            return attachment_row_ids_by_oa_id
        for row_id, row in rows_by_id.items():
            if not self.invoice_row_is_attachment_context(row):
                continue
            derived_from_oa_id = str(row.get("derived_from_oa_id") or "").strip()
            matched_oa_id = None
            for oa_row_id in sorted(oa_row_ids):
                if (
                    derived_from_oa_id == oa_row_id
                    or self._attachment_parent_oa_id(derived_from_oa_id) == oa_row_id
                    or self._attachment_matches_oa(row, oa_row_id)
                ):
                    matched_oa_id = oa_row_id
                    break
            if matched_oa_id is None:
                matched_oa_id = self.oa_id_from_attachment_invoice_id(row_id, list(oa_row_ids))
            if matched_oa_id:
                attachment_row_ids_by_oa_id.setdefault(matched_oa_id, []).append(row_id)
        return attachment_row_ids_by_oa_id

    @staticmethod
    def invoice_row_is_attachment_context(row: dict[str, object]) -> bool:
        if str(row.get("type") or "").strip() != "invoice":
            return False
        return str(row.get("source_kind") or "").strip() == "oa_attachment_invoice"

    def oa_id_from_attachment_invoice_id(self, invoice_id: str, oa_row_ids: list[str]) -> str | None:
        for oa_row_id in sorted(oa_row_ids, key=len, reverse=True):
            if self._attachment_row_id_matches_oa(invoice_id, oa_row_id):
                return oa_row_id
        return None

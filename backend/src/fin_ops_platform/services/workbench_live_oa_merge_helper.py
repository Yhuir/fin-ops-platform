from __future__ import annotations

from typing import Callable


class WorkbenchLiveOaMergeHelper:
    """Merges live Workbench payload rows with OA raw payload rows."""

    def __init__(
        self,
        *,
        serialize_value: Callable[[object], object],
    ) -> None:
        self._serialize_value = serialize_value

    def merge_rows(
        self,
        live_payload: dict[str, object],
        oa_payload: dict[str, object],
    ) -> dict[str, object]:
        merged = self._serialize_value(live_payload)
        if not isinstance(merged, dict):
            merged = {}
        merged["oa_status"] = self._serialize_value(oa_payload.get("oa_status") or {"code": "ready", "message": "OA 已同步"})
        paired = merged.setdefault("paired", {})
        open_rows = merged.setdefault("open", {})
        if not isinstance(paired, dict):
            paired = {}
            merged["paired"] = paired
        if not isinstance(open_rows, dict):
            open_rows = {}
            merged["open"] = open_rows
        oa_paired = oa_payload.get("paired") if isinstance(oa_payload.get("paired"), dict) else {}
        oa_open = oa_payload.get("open") if isinstance(oa_payload.get("open"), dict) else {}
        paired["oa"] = self._serialize_value(oa_paired.get("oa", []))
        open_rows["oa"] = self._serialize_value(oa_open.get("oa", []))
        paired["invoice"] = self.dedupe_rows_by_id_preferring_last([
            *self._as_list(self._serialize_value(paired.get("invoice", []))),
            *[
                row
                for row in self._as_list(self._serialize_value(oa_paired.get("invoice", [])))
                if isinstance(row, dict) and str(row.get("source_kind", "")) == "oa_attachment_invoice"
            ],
        ])
        open_rows["invoice"] = self.dedupe_rows_by_id_preferring_last([
            *self._as_list(self._serialize_value(open_rows.get("invoice", []))),
            *[
                row
                for row in self._as_list(self._serialize_value(oa_open.get("invoice", [])))
                if isinstance(row, dict) and str(row.get("source_kind", "")) == "oa_attachment_invoice"
            ],
        ])
        return merged

    @staticmethod
    def dedupe_rows_by_id_preferring_last(rows: list[object]) -> list[object]:
        row_ids_in_order: list[str] = []
        rows_by_id: dict[str, object] = {}
        passthrough_rows: list[object] = []
        for row in rows:
            if not isinstance(row, dict):
                passthrough_rows.append(row)
                continue
            row_id = str(row.get("id", "")).strip()
            if not row_id:
                passthrough_rows.append(row)
                continue
            if row_id not in rows_by_id:
                row_ids_in_order.append(row_id)
            rows_by_id[row_id] = row
        return [rows_by_id[row_id] for row_id in row_ids_in_order] + passthrough_rows

    @staticmethod
    def _as_list(value: object) -> list[object]:
        return list(value) if isinstance(value, list) else []

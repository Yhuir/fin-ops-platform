from __future__ import annotations

from typing import Callable


class WorkbenchRawPayloadMutationHelper:
    """Mutates raw Workbench payload rows and summary through local payload-only operations."""

    def __init__(
        self,
        *,
        serialize_value: Callable[[object], object],
    ) -> None:
        self._serialize_value = serialize_value

    def replace_row(
        self,
        payload: dict[str, object],
        *,
        row_type: str,
        replacement: dict[str, object],
    ) -> bool:
        replacement_id = str(replacement.get("id", "")).strip()
        if not replacement_id:
            return False
        replaced = False
        for section_name in ("paired", "open"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            rows = section_payload.get(row_type)
            if not isinstance(rows, list):
                continue
            for index, row in enumerate(rows):
                if isinstance(row, dict) and str(row.get("id", "")).strip() == replacement_id:
                    rows[index] = self._serialize_value(replacement)
                    replaced = True
        return replaced

    @staticmethod
    def dedupe_rows_by_id(payload: dict[str, object], *, row_type: str) -> None:
        seen_row_ids: set[str] = set()
        for section_name in ("paired", "open"):
            section_payload = payload.get(section_name)
            if not isinstance(section_payload, dict):
                continue
            rows = section_payload.get(row_type)
            if not isinstance(rows, list):
                continue
            deduped_rows: list[object] = []
            for row in rows:
                if not isinstance(row, dict):
                    deduped_rows.append(row)
                    continue
                row_id = str(row.get("id", "")).strip()
                if row_id and row_id in seen_row_ids:
                    continue
                if row_id:
                    seen_row_ids.add(row_id)
                deduped_rows.append(row)
            section_payload[row_type] = deduped_rows

    @staticmethod
    def refresh_summary(payload: dict[str, object]) -> None:
        paired = payload.get("paired") if isinstance(payload.get("paired"), dict) else {}
        open_rows = payload.get("open") if isinstance(payload.get("open"), dict) else {}
        payload["summary"] = {
            "oa_count": len(list(paired.get("oa") or [])) + len(list(open_rows.get("oa") or [])),
            "bank_count": len(list(paired.get("bank") or [])) + len(list(open_rows.get("bank") or [])),
            "invoice_count": len(list(paired.get("invoice") or [])) + len(list(open_rows.get("invoice") or [])),
            "paired_count": sum(len(list(paired.get(row_type) or [])) for row_type in ("oa", "bank", "invoice")),
            "open_count": sum(len(list(open_rows.get(row_type) or [])) for row_type in ("oa", "bank", "invoice")),
            "exception_count": sum(
                1
                for row in [
                    *list(open_rows.get("oa") or []),
                    *list(open_rows.get("bank") or []),
                    *list(open_rows.get("invoice") or []),
                ]
                if isinstance(row, dict)
                and str(
                    row.get("oa_bank_relation", row.get("invoice_relation", row.get("invoice_bank_relation", {}))).get(
                        "tone",
                        "",
                    )
                )
                == "danger"
            ),
        }

from __future__ import annotations

from typing import Callable


class WorkbenchGroupRowPayloadHelper:
    """Groups raw Workbench row payloads through an explicit grouping service."""

    def __init__(
        self,
        *,
        grouping_service: object,
        serialize_value: Callable[[object], object],
    ) -> None:
        self._grouping_service = grouping_service
        self._serialize_value = serialize_value

    def group(
        self,
        payload: dict[str, object],
        *,
        turnover_relations: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        paired = payload.get("paired", {})
        open_rows = payload.get("open", {})
        if not isinstance(paired, dict):
            paired = {}
        if not isinstance(open_rows, dict):
            open_rows = {}
        oa_rows = self._active_rows([*list(paired.get("oa", [])), *list(open_rows.get("oa", []))])
        bank_rows = self._active_rows([*list(paired.get("bank", [])), *list(open_rows.get("bank", []))])
        invoice_rows = self._active_rows([*list(paired.get("invoice", [])), *list(open_rows.get("invoice", []))])
        grouped = self._grouping_service.group_payload(
            str(payload.get("month", "")),
            oa_rows=oa_rows,
            bank_rows=bank_rows,
            invoice_rows=invoice_rows,
            turnover_relations=turnover_relations,
        )
        oa_status = payload.get("oa_status")
        if isinstance(oa_status, dict):
            grouped["oa_status"] = self._serialize_value(oa_status)
        return grouped

    @staticmethod
    def _active_rows(rows: list[object]) -> list[dict[str, object]]:
        return [row for row in rows if isinstance(row, dict) and not row.get("ignored")]

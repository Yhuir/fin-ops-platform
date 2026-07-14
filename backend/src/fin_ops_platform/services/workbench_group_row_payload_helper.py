from __future__ import annotations

from typing import Callable

from fin_ops_platform.services.workbench_object_identity_arbitration import WorkbenchObjectIdentityArbitrationService


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
        _ = turnover_relations
        paired = payload.get("paired", {})
        unpaired = payload.get("unpaired", {})
        if not isinstance(paired, dict):
            paired = {}
        if not isinstance(unpaired, dict):
            unpaired = {}
        paired_rows = self._active_rows(
            [
                *list(paired.get("oa", [])),
                *list(paired.get("bank", [])),
                *list(paired.get("invoice", [])),
            ]
        )
        paired_row_ids = {
            str(row.get("id") or "").strip()
            for row in paired_rows
            if str(row.get("id") or "").strip()
        }
        oa_rows = self._active_rows([*list(paired.get("oa", [])), *list(unpaired.get("oa", []))])
        bank_rows = self._active_rows([*list(paired.get("bank", [])), *list(unpaired.get("bank", []))])
        invoice_rows = self._active_rows([*list(paired.get("invoice", [])), *list(unpaired.get("invoice", []))])
        rows_by_id = {
            str(row.get("id") or "").strip(): dict(row)
            for row in [*oa_rows, *bank_rows, *invoice_rows]
            if str(row.get("id") or "").strip()
        }
        WorkbenchObjectIdentityArbitrationService().arbitrate_rows(rows_by_id)
        relations_by_case: dict[str, dict[str, object]] = {}
        for row_id, row in rows_by_id.items():
            if row_id not in paired_row_ids:
                continue
            case_id = str(row.get("case_id") or "").strip()
            if not case_id:
                raise ValueError("Paired Workbench rows require an active relation case_id.")
            relation = relations_by_case.setdefault(
                case_id,
                {
                    "case_id": case_id,
                    "row_ids": [],
                    "row_types": [],
                    "status": "active",
                    "relation_mode": str(row.get("relation_mode") or "manual_confirmed"),
                },
            )
            relation["row_ids"].append(str(row["id"]))
            relation["row_types"].append(str(row["type"]))
        grouped = self._grouping_service.group_payload(
            str(payload.get("month", "")),
            rows_by_id=rows_by_id,
            active_relations=list(relations_by_case.values()),
        )
        oa_status = payload.get("oa_status")
        if isinstance(oa_status, dict):
            grouped["oa_status"] = self._serialize_value(oa_status)
        return grouped

    @staticmethod
    def _active_rows(rows: list[object]) -> list[dict[str, object]]:
        return [row for row in rows if isinstance(row, dict) and not row.get("ignored")]

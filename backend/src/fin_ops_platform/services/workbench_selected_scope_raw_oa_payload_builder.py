from __future__ import annotations

from typing import Callable


class WorkbenchSelectedScopeRawOaPayloadBuilder:
    """Builds selected-scope raw OA payloads through explicit read-only ports."""

    def __init__(
        self,
        *,
        manual_retained_oa_row_ids: Callable[[], list[str]],
        record_snapshots: Callable[[], list[dict[str, object]]],
        serialize_row: Callable[[dict[str, object]], dict[str, object]],
        oa_status_payload: Callable[[], dict[str, object]],
    ) -> None:
        self._manual_retained_oa_row_ids = manual_retained_oa_row_ids
        self._record_snapshots = record_snapshots
        self._serialize_row = serialize_row
        self._oa_status_payload = oa_status_payload

    def build(
        self,
        *,
        months: set[str],
        supplemental_oa_row_ids: set[str],
    ) -> dict[str, object]:
        paired: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        open_rows: dict[str, list[dict[str, object]]] = {"oa": [], "bank": [], "invoice": []}
        retained_oa_row_ids = set(supplemental_oa_row_ids) | set(self._manual_retained_oa_row_ids())

        for row in self._record_snapshots():
            row_type = str(row.get("type", "")).strip()
            row_month = str(row.get("_month", "")).strip()
            include_row = False
            if row_type == "oa":
                include_row = row_month in months or str(row.get("id", "")) in retained_oa_row_ids
            elif row_type == "invoice" and str(row.get("source_kind", "")) == "oa_attachment_invoice":
                include_row = row_month in months or str(row.get("derived_from_oa_id", "")) in retained_oa_row_ids
            if not include_row:
                continue
            section_payload = paired if row.get("_section") == "paired" else open_rows
            section_payload[row_type].append(self._serialize_row(row))

        month_rows = [*paired["oa"], *open_rows["oa"], *paired["invoice"], *open_rows["invoice"]]
        return {
            "month": "all",
            "oa_status": self._oa_status_payload(),
            "summary": {
                "oa_count": len(paired["oa"]) + len(open_rows["oa"]),
                "bank_count": 0,
                "invoice_count": len(paired["invoice"]) + len(open_rows["invoice"]),
                "paired_count": len(paired["oa"]) + len(paired["invoice"]),
                "open_count": len(open_rows["oa"]) + len(open_rows["invoice"]),
                "exception_count": sum(
                    1
                    for row in month_rows
                    if str(
                        row.get("oa_bank_relation", row.get("invoice_bank_relation", {})).get("tone", "")
                    )
                    == "danger"
                ),
            },
            "paired": paired,
            "open": open_rows,
        }

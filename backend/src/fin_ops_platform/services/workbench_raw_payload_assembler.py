from __future__ import annotations

from typing import Callable


class WorkbenchRawPayloadAssembler:
    """Orchestrates legacy raw Workbench payload construction."""

    def __init__(
        self,
        *,
        has_live_rows_for_month: Callable[[str], bool],
        sync_live_auto_pair_relations: Callable[[], None],
        build_live_workbench_row_payload: Callable[[str], dict[str, object]],
        build_oa_workbench_row_payload: Callable[[str], dict[str, object]],
        sync_oa_invoice_offset_auto_pair_relations: Callable[[dict[str, object]], None],
        repair_active_relations_with_oa_attachment_context: Callable[[dict[str, object]], None],
        apply_pair_relations_to_payload: Callable[..., dict[str, object]],
        apply_overrides_to_payload: Callable[[dict[str, object]], dict[str, object]],
    ) -> None:
        self._has_live_rows_for_month = has_live_rows_for_month
        self._sync_live_auto_pair_relations = sync_live_auto_pair_relations
        self._build_live_workbench_row_payload = build_live_workbench_row_payload
        self._build_oa_workbench_row_payload = build_oa_workbench_row_payload
        self._sync_oa_invoice_offset_auto_pair_relations = sync_oa_invoice_offset_auto_pair_relations
        self._repair_active_relations_with_oa_attachment_context = repair_active_relations_with_oa_attachment_context
        self._apply_pair_relations_to_payload = apply_pair_relations_to_payload
        self._apply_overrides_to_payload = apply_overrides_to_payload

    def build(
        self,
        month: str,
        *,
        supplement_missing_pair_relation_rows: bool = True,
    ) -> dict[str, object]:
        if self._has_live_rows_for_month(month):
            self._sync_live_auto_pair_relations()
            payload = self._build_live_workbench_row_payload(month)
        else:
            payload = self._build_oa_workbench_row_payload(month)
        self._sync_oa_invoice_offset_auto_pair_relations(payload)
        self._repair_active_relations_with_oa_attachment_context(payload)
        paired_payload = self._apply_pair_relations_to_payload(
            payload,
            supplement_missing_rows=supplement_missing_pair_relation_rows,
        )
        return self._apply_overrides_to_payload(paired_payload)

from __future__ import annotations

from typing import Callable


class WorkbenchApiPayloadAssembler:
    """Orchestrates legacy grouped Workbench API payload post-processing."""

    def __init__(
        self,
        *,
        read_model_provider: Callable[..., dict[str, object]],
        apply_oa_retention: Callable[[dict[str, object]], dict[str, object]],
        append_etc_invoice_summary_rows: Callable[[dict[str, object]], None],
        build_invoice_inventory: Callable[[dict[str, object]], dict[str, int]],
        derive_tags: Callable[[dict[str, object]], dict[str, object]],
    ) -> None:
        self._read_model_provider = read_model_provider
        self._apply_oa_retention = apply_oa_retention
        self._append_etc_invoice_summary_rows = append_etc_invoice_summary_rows
        self._build_invoice_inventory = build_invoice_inventory
        self._derive_tags = derive_tags

    def build(self, month: str, *, visibility_key: str = "global") -> dict[str, object]:
        read_model = self._read_model_provider(
            month,
            visibility_key=visibility_key,
            ensure_candidate_matches=True,
        )
        payload = read_model.get("payload")
        retained = self._apply_oa_retention(payload if isinstance(payload, dict) else {})
        self._append_etc_invoice_summary_rows(retained)
        retained["invoice_inventory"] = self._build_invoice_inventory(retained)
        return self._derive_tags(retained)

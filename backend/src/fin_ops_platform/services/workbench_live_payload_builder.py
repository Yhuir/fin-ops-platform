from __future__ import annotations

from typing import Callable


class WorkbenchLivePayloadBuilder:
    """Builds the live-source Workbench raw payload through explicit ports."""

    def __init__(
        self,
        *,
        get_live_workbench: Callable[[str], dict[str, object]],
        build_oa_workbench_row_payload: Callable[[str], dict[str, object]],
        merge_live_with_oa_rows: Callable[[dict[str, object], dict[str, object]], dict[str, object]],
        serialize_value: Callable[[object], object],
    ) -> None:
        self._get_live_workbench = get_live_workbench
        self._build_oa_workbench_row_payload = build_oa_workbench_row_payload
        self._merge_live_with_oa_rows = merge_live_with_oa_rows
        self._serialize_value = serialize_value

    def build(self, month: str) -> dict[str, object]:
        live_payload = self._get_live_workbench(month)
        oa_payload = self._build_oa_workbench_row_payload(month)
        merged = self._merge_live_with_oa_rows(live_payload, oa_payload)
        serialized = self._serialize_value(merged)
        return serialized if isinstance(serialized, dict) else {}

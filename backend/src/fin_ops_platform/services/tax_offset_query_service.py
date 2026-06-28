from __future__ import annotations

from typing import Any


class TaxOffsetQueryService:
    def __init__(
        self,
        *,
        tax_offset_service: Any | None,
        runtime_service: Any,
    ) -> None:
        self._tax_offset_service = tax_offset_service
        self._runtime_service = runtime_service

    def get_month_payload(self, month: str) -> tuple[dict[str, Any], bool]:
        if self._tax_offset_service is None:
            raise RuntimeError("Tax offset service is not configured.")
        payload = self._tax_offset_service.get_month_payload(month)
        return payload, False

    def calculate(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        return (
            self._require_tax_offset_service().calculate(
                month=str(payload["month"]),
                selected_output_ids=list(payload["selected_output_ids"]),
                selected_input_ids=list(payload["selected_input_ids"]),
            ),
            200,
        )

    def _require_tax_offset_service(self) -> Any:
        if self._tax_offset_service is None:
            raise RuntimeError("Tax offset service is not configured.")
        return self._tax_offset_service

    def get_summary_payload(self, month: str) -> tuple[dict[str, Any], bool]:
        scope_key = self._runtime_service.request_scope_key(month)
        full_payload, cache_hit = self.get_month_payload(month)
        return self._runtime_service.summary_payload(full_payload, scope_key=scope_key), cache_hit

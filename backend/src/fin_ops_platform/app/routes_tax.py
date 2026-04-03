from __future__ import annotations

from fin_ops_platform.services.tax_offset_service import TaxOffsetService


class TaxApiRoutes:
    def __init__(self, tax_offset_service: TaxOffsetService) -> None:
        self._tax_offset_service = tax_offset_service

    def get_tax_offset(self, month: str) -> dict[str, object]:
        return self._tax_offset_service.get_month_payload(month)

    def calculate(self, payload: dict[str, object]) -> dict[str, object]:
        return self._tax_offset_service.calculate(
            month=str(payload["month"]),
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

from __future__ import annotations

from typing import Any


class TaxOffsetQueryService:
    """Serve tax-offset reads from one canonical snapshot per API request."""

    def __init__(
        self,
        *,
        canonical_repository: Any,
        tax_offset_service: Any,
    ) -> None:
        if not callable(getattr(canonical_repository, "load_month_payload", None)):
            raise ValueError("Tax offset query service requires a canonical repository.")
        if not callable(getattr(tax_offset_service, "calculate_from_month_payload", None)):
            raise ValueError("Tax offset query service requires a tax offset service.")
        self._canonical_repository = canonical_repository
        self._tax_offset_service = tax_offset_service

    def get_month_payload(self, month: str) -> dict[str, Any]:
        return dict(self._canonical_repository.load_month_payload(month))

    def get_summary_payload(self, month: str) -> dict[str, Any]:
        payload = self.get_month_payload(month)
        return {
            "month": payload["month"],
            "summary": dict(payload.get("summary") or {}),
            "statistics": dict(payload.get("statistics") or {}),
            "canonical_snapshot_version": payload.get("canonical_snapshot_version"),
        }

    def calculate(self, payload: dict[str, Any]) -> tuple[dict[str, Any], int]:
        month_payload = self.get_month_payload(str(payload["month"]))
        return self.calculate_from_month_payload(payload, month_payload=month_payload), 200

    def calculate_from_month_payload(
        self,
        payload: dict[str, Any],
        *,
        month_payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._tax_offset_service.calculate_from_month_payload(
            month=str(payload["month"]),
            month_payload=month_payload,
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

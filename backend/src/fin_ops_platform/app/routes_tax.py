from __future__ import annotations

from datetime import datetime
from http import HTTPStatus
from time import monotonic
from typing import Any, Callable

from fin_ops_platform.services.tax_offset_service import TaxOffsetService


class TaxApiRoutes:
    def __init__(
        self,
        tax_offset_service: TaxOffsetService | None,
        *,
        query_service: Any | None = None,
        certified_import_job_service: Any | None = None,
        json_response: Callable[[HTTPStatus, dict[str, Any]], Any] | None = None,
        month_metric_emitter: Callable[..., None] | None = None,
        calculate_metric_emitter: Callable[..., None] | None = None,
        duration_ms: Callable[[float], float] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._tax_offset_service = tax_offset_service
        self._query_service = query_service
        self._certified_import_job_service = certified_import_job_service
        self._json_response = json_response
        self._month_metric_emitter = month_metric_emitter
        self._calculate_metric_emitter = calculate_metric_emitter
        self._duration_ms = duration_ms or (lambda started_at: (monotonic() - started_at) * 1000)
        self._now_provider = now_provider or datetime.now

    def get_tax_offset(self, month: str) -> dict[str, object]:
        return self._tax_offset_service.get_month_payload(month)

    def calculate(self, payload: dict[str, object]) -> dict[str, object]:
        return self._tax_offset_service.calculate(
            month=str(payload["month"]),
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

    def calculate_from_month_payload(
        self,
        payload: dict[str, object],
        *,
        month_payload: dict[str, object],
    ) -> dict[str, object]:
        return self._tax_offset_service.calculate_from_month_payload(
            month=str(payload["month"]),
            month_payload=month_payload,
            selected_output_ids=list(payload["selected_output_ids"]),
            selected_input_ids=list(payload["selected_input_ids"]),
        )

    def handle_month(self, month: str | None) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        started_at = monotonic()
        cache_hit = False
        try:
            payload, cache_hit = self._require_query_service().get_month_payload(current_month)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_request", "message": str(exc)},
            )
        if self._month_metric_emitter is not None:
            self._month_metric_emitter(
                month=current_month,
                cache_hit=cache_hit,
                duration_ms=self._duration_ms(started_at),
                payload=payload,
            )
        status = (
            HTTPStatus.ACCEPTED
            if payload.get("read_model_status") == "refreshing"
            and not payload.get("input_plan_items")
            and not payload.get("output_items")
            and not payload.get("certified_items")
            else HTTPStatus.OK
        )
        return self._respond(status, payload)

    def handle_summary(self, month: str | None) -> Any:
        current_month = month or self._now_provider().strftime("%Y-%m")
        try:
            payload, _cache_hit = self._require_query_service().get_summary_payload(current_month)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_request", "message": str(exc)},
            )
        status = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
        return self._respond(status, payload)

    def handle_calculate(self, payload: dict[str, object]) -> Any:
        started_at = monotonic()
        try:
            result, status_code = self._require_query_service().calculate(payload)
        except (KeyError, TypeError, ValueError) as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {"error": "invalid_tax_offset_calculate_request", "message": str(exc)},
            )
        if self._calculate_metric_emitter is not None:
            self._calculate_metric_emitter(
                month=str(payload.get("month") or ""),
                selected_output_count=_safe_list_count(payload.get("selected_output_ids")),
                selected_input_count=_safe_list_count(payload.get("selected_input_ids")),
                duration_ms=self._duration_ms(started_at),
            )
        return self._respond(HTTPStatus(status_code), result)

    def handle_import_job(self, import_job_id: str) -> Any:
        try:
            import_job = self._require_import_job_service().get_confirm_job_payload(import_job_id)
        except ValueError as exc:
            return self._respond(
                HTTPStatus.BAD_REQUEST,
                {
                    "error": "invalid_tax_certified_import_job_request",
                    "message": str(exc),
                },
            )
        except RuntimeError as exc:
            return self._respond(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"error": "import_job_repository_unavailable", "message": str(exc)},
            )
        except KeyError:
            return self._respond(
                HTTPStatus.NOT_FOUND,
                {
                    "error": "tax_certified_import_job_not_found",
                    "import_job_id": str(import_job_id or "").strip(),
                },
            )
        return self._respond(HTTPStatus.OK, {"import_job": import_job})

    def _require_query_service(self) -> Any:
        if self._query_service is None:
            raise RuntimeError("Tax offset query service is not configured.")
        return self._query_service

    def _require_import_job_service(self) -> Any:
        if self._certified_import_job_service is None:
            raise RuntimeError("Tax certified import job service is not configured.")
        return self._certified_import_job_service

    def _respond(self, status: HTTPStatus, payload: dict[str, Any]) -> Any:
        if self._json_response is None:
            return status, payload
        return self._json_response(status, payload)


def _safe_list_count(value: object) -> int:
    return len(value) if isinstance(value, list) else 0

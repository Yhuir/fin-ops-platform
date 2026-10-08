from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService


class BatchAccountingApiRoutes:
    def __init__(self, service_factory: Callable[[], BatchAccountingService]) -> None:
        self._service_factory = service_factory

    def list_payload(
        self,
        query: dict[str, list[str]],
        *,
        timing_observer: Callable[[str, float], None] | None = None,
    ) -> tuple[HTTPStatus, dict[str, Any]]:
        if set(query) - {"bank_year", "page", "page_size"} or any(len(values) != 1 for values in query.values()):
            return HTTPStatus.BAD_REQUEST, {
                "error": "invalid_batch_accounting_request",
                "message": "历史查询参数无效。",
            }
        try:
            payload = self._service_factory().build_payload(
                bank_year=query.get("bank_year", ["all"])[0],
                page=query.get("page", ["1"])[0],
                page_size=query.get("page_size", ["50"])[0],
                timing_observer=timing_observer,
            )
            return HTTPStatus.OK, payload
        except BatchAccountingError as exc:
            return self._error(exc)

    def detail(self, relation_id: str) -> tuple[HTTPStatus, dict[str, Any]]:
        try:
            return HTTPStatus.OK, self._service_factory().detail(relation_id)
        except BatchAccountingError as exc:
            return self._error(exc)

    @staticmethod
    def _error(exc: BatchAccountingError) -> tuple[HTTPStatus, dict[str, Any]]:
        status = HTTPStatus.BAD_REQUEST
        if exc.code in {
            "batch_accounting_canonical_query_unavailable",
            "batch_accounting_invalid_amount",
            "batch_accounting_invalid_history",
        }:
            status = HTTPStatus.SERVICE_UNAVAILABLE
        elif exc.code == "batch_accounting_relation_not_found":
            status = HTTPStatus.NOT_FOUND
        return status, {"error": exc.code, "message": str(exc)}

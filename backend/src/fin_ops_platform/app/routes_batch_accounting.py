from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.batch_accounting_service import BatchAccountingError, BatchAccountingService


class BatchAccountingApiRoutes:
    def __init__(self, service_factory: Callable[..., BatchAccountingService]) -> None:
        self._service_factory = service_factory

    def list_payload(self, query: dict[str, list[str]]) -> tuple[HTTPStatus, dict[str, Any]]:
        year = (query.get("year") or [""])[0]
        bank_year = (query.get("bank_year") or [year])[0]
        oa_year = (query.get("oa_year") or [year])[0]
        bucket = (query.get("bucket") or ["unsubmitted"])[0] or "unsubmitted"
        try:
            payload = self._service_factory(use_sql_read_model=True).build_payload(
                year=year,
                bank_year=bank_year,
                oa_year=oa_year,
                bucket=bucket,
                page=self._query_value(query, "page"),
                page_size=self._query_value(query, "page_size", "pageSize"),
                bank_page=self._query_value(query, "bank_page", "bankPage"),
                bank_page_size=self._query_value(query, "bank_page_size", "bankPageSize"),
                oa_page=self._query_value(query, "oa_page", "oaPage"),
                oa_page_size=self._query_value(query, "oa_page_size", "oaPageSize"),
            )
        except BatchAccountingError as exc:
            return self._batch_accounting_error_response(exc)
        return HTTPStatus.OK, payload

    @staticmethod
    def _query_value(query: dict[str, list[str]], *names: str) -> str | None:
        for name in names:
            if name in query:
                return (query.get(name) or [None])[0]
        return None

    @staticmethod
    def _batch_accounting_error_response(exc: BatchAccountingError) -> tuple[HTTPStatus, dict[str, Any]]:
        status = HTTPStatus.CONFLICT if exc.code == "batch_accounting_version_conflict" else HTTPStatus.BAD_REQUEST
        payload: dict[str, Any] = {"error": exc.code, "message": str(exc)}
        payload.update(exc.payload)
        return status, payload

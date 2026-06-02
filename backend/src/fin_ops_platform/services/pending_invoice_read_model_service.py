from __future__ import annotations

from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.pending_invoice_service import (
    EXPENSE_FILTERS,
    INCOME_FILTERS,
    VALID_FILTERS,
    PendingInvoiceError,
)
from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons


RowNormalizer = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]
SettingsProvider = Callable[[], dict[str, Any]]
SourceVersionsProvider = Callable[[], dict[str, Any]]


def pending_invoice_source_versions(
    settings: dict[str, Any] | None,
    *,
    attachment_invoice_parser_version: str,
    oa_projection_sync_version: str,
) -> dict[str, Any]:
    payload = settings if isinstance(settings, dict) else {}
    pending_groups = payload.get("pending_invoice_tag_groups")
    pending_output_groups = payload.get("pending_output_invoice_tag_groups")
    bank_tags = payload.get("bank_transaction_tags")
    return {
        "pending_invoice_read_model_schema_version": "2026-06-pending-invoice-oa-identity-v1",
        "pending_invoice_tag_groups_version": pending_groups.get("version") if isinstance(pending_groups, dict) else 1,
        "pending_output_invoice_tag_groups_version": pending_output_groups.get("version") if isinstance(pending_output_groups, dict) else 1,
        "bank_auto_tag_rules_version": bank_tags.get("version") if isinstance(bank_tags, dict) else 1,
        "oa_attachment_invoice_parser_version": attachment_invoice_parser_version,
        "oa_projection_sync_version": oa_projection_sync_version,
    }


class PendingInvoiceReadModelService:
    def __init__(
        self,
        *,
        repository: Any | None,
        queue_repository: Any | None = None,
        row_normalizer: RowNormalizer | None = None,
        settings_provider: SettingsProvider | None = None,
        source_versions_provider: SourceVersionsProvider | None = None,
    ) -> None:
        self._repository = repository
        self._queue_repository = queue_repository
        self._row_normalizer = row_normalizer
        self._settings_provider = settings_provider or (lambda: {})
        self._source_versions_provider = source_versions_provider or (lambda: {})

    def rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        direction = str(query.get("direction", ["expense"])[0] or "expense").strip()
        filter_name = str(query.get("filter", ["all"])[0] or "all").strip() or "all"
        self._validate_direction_filter(direction=direction, filter_name=filter_name)
        list_rows = self._list_rows_callable()
        try:
            payload = list_rows(
                direction=direction,
                filter=filter_name,
                date_from=query.get("date_from", [None])[0],
                date_to=query.get("date_to", [None])[0],
                keyword=query.get("keyword", [None])[0],
                filters=query.get("filters", [None])[0],
                sort_field=query.get("sort_field", [None])[0],
                sort_direction=query.get("sort_direction", [None])[0],
                page=query.get("page", [1])[0],
                page_size=query.get("page_size", [50])[0],
            )
        except ValueError as exc:
            raise PendingInvoiceError("invalid_pending_invoice_query", str(exc)) from exc

        scope_key = self.scope_key(direction=direction, filter_name=filter_name)
        if not isinstance(payload, dict):
            self.enqueue_refreshes_for_scope(direction=direction, filter_name=filter_name, reason="api_miss")
            return self.refreshing_payload(direction=direction, filter_name=filter_name, scope_key=scope_key, query=query)

        refresh_status = str(payload.get("refresh_status") or "fresh")
        if self.payload_requires_schema_refresh(payload):
            if refresh_status == "fresh":
                self.enqueue_refreshes_for_scope(direction=direction, filter_name=filter_name, reason="api_schema_stale")
            return self.refreshing_payload(
                direction=direction,
                filter_name=filter_name,
                scope_key=scope_key,
                query=query,
                source_payload=payload,
            )

        if refresh_status != "fresh":
            return self.payload_response(payload, read_model_status=refresh_status, scope_key=scope_key)

        stale_reasons = source_version_mismatch_reasons(
            expected=self.expected_source_versions(),
            actual=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
        )
        if stale_reasons:
            self.enqueue_refreshes_for_scope(direction=direction, filter_name=filter_name, reason="api_source_versions_stale")
            if list(payload.get("rows") or []):
                result = self.payload_response(payload, read_model_status="refreshing", scope_key=scope_key)
                result["read_model_stale_reasons"] = list(stale_reasons)
                return result
            return self.refreshing_payload(
                direction=direction,
                filter_name=filter_name,
                scope_key=scope_key,
                query=query,
                source_payload=payload,
                stale_reasons=stale_reasons,
            )

        return self.payload_response(payload, read_model_status=refresh_status, scope_key=scope_key)

    def all_rows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        page_size = 200
        first_query = {key: list(values) for key, values in query.items()}
        first_query["page"] = ["1"]
        first_query["page_size"] = [str(page_size)]
        first_payload = self.rows(first_query)
        if first_payload.get("read_model_status") != "fresh":
            return first_payload

        rows = list(first_payload.get("rows") or [])
        pagination = first_payload.get("pagination") if isinstance(first_payload.get("pagination"), dict) else {}
        total = int(pagination.get("total") or len(rows))
        page = 2
        while len(rows) < total:
            page_query = {key: list(values) for key, values in query.items()}
            page_query["page"] = [str(page)]
            page_query["page_size"] = [str(page_size)]
            page_payload = self.rows(page_query)
            if page_payload.get("read_model_status") != "fresh":
                return page_payload
            page_rows = list(page_payload.get("rows") or [])
            if not page_rows:
                break
            rows.extend(page_rows)
            page += 1
        return {
            "direction": first_payload.get("direction"),
            "filter": first_payload.get("filter"),
            "rows": rows,
            "pagination": {"page": 1, "page_size": page_size, "total": total},
            "summary": first_payload.get("summary") if isinstance(first_payload.get("summary"), dict) else {},
            "read_model_status": "fresh",
            "read_model_scope_key": first_payload.get("read_model_scope_key"),
        }

    def expected_source_versions(self) -> dict[str, Any]:
        return dict(self._source_versions_provider() or {})

    def source_summary_for_query(
        self,
        *,
        direction: str,
        query: dict[str, list[str]],
        source_payload: dict[str, Any] | None = None,
    ) -> dict[str, int]:
        summary = source_payload.get("summary") if isinstance(source_payload, dict) else None
        source_summary = summary.get("source_summary") if isinstance(summary, dict) else None
        if isinstance(source_summary, dict):
            return {
                "bank_transaction_rows": self._optional_int(source_summary.get("bank_transaction_rows")) or 0,
                "expense_rows": self._optional_int(source_summary.get("expense_rows")) or 0,
                "income_rows": self._optional_int(source_summary.get("income_rows")) or 0,
                "current_direction_rows": self._optional_int(source_summary.get("current_direction_rows")) or 0,
                "excluded_direction_rows": self._optional_int(source_summary.get("excluded_direction_rows")) or 0,
            }
        source_summary_loader = getattr(self._repository, "pending_invoice_source_summary", None)
        if callable(source_summary_loader):
            try:
                return source_summary_loader(
                    direction=direction,
                    date_from=query.get("date_from", [None])[0],
                    date_to=query.get("date_to", [None])[0],
                )
            except Exception:
                return {}
        return {}

    def payload_response(
        self,
        payload: dict[str, Any],
        *,
        read_model_status: str,
        scope_key: str,
    ) -> dict[str, Any]:
        result = dict(payload)
        summary = result.get("summary")
        if isinstance(summary, dict) and not isinstance(summary.get("source_summary"), dict):
            direction, _sep, _filter_name = scope_key.partition(":")
            summary = dict(summary)
            summary["source_summary"] = self.source_summary_for_query(
                direction=direction,
                query={},
                source_payload=result,
            )
            result["summary"] = summary
        rows = result.get("rows")
        if isinstance(rows, list) and callable(self._row_normalizer):
            result["rows"] = self._row_normalizer([row for row in rows if isinstance(row, dict)])
        settings_payload = self._settings_provider()
        bank_transaction_tags = (
            settings_payload.get("bank_transaction_tags")
            if isinstance(settings_payload, dict)
            else None
        )
        if isinstance(bank_transaction_tags, dict):
            result["bank_transaction_tags"] = bank_transaction_tags
            result["bank_transaction_tags_version"] = int(
                bank_transaction_tags.get("version") or result.get("bank_transaction_tags_version") or 1
            )
        result["read_model_status"] = read_model_status
        result["read_model_scope_key"] = scope_key
        result.pop("refresh_status", None)
        return result

    def refreshing_payload(
        self,
        *,
        direction: str,
        filter_name: str,
        scope_key: str,
        query: dict[str, list[str]],
        source_payload: dict[str, Any] | None = None,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "direction": direction,
            "filter": filter_name,
            "rows": [],
            "pagination": {"page": 1, "page_size": 50, "total": 0},
            "summary": {
                "total_rows": 0,
                "missing_invoice_rows": 0,
                "create_invoice_available_rows": 0,
                "source_summary": self.source_summary_for_query(
                    direction=direction,
                    query=query,
                    source_payload=source_payload,
                ),
            },
            "bank_transaction_tags": {},
            "bank_transaction_tags_version": 1,
            "read_model_status": "refreshing",
            "read_model_scope_key": scope_key,
        }
        if stale_reasons:
            payload["read_model_stale_reasons"] = list(stale_reasons)
        return payload

    def enqueue_refreshes_for_scope(self, *, direction: str, filter_name: str, reason: str) -> list[str]:
        scope_keys = ["expense:all", "income:all"] if direction == "all" else [self.scope_key(direction=direction, filter_name=filter_name)]
        return [
            scope_key
            for scope_key in scope_keys
            if self.enqueue_refresh(scope_key, reason=reason)
        ]

    def invalidate_base_scopes(self, reason: str) -> list[str]:
        scope_keys = [
            "expense:all",
            "expense:requires_invoice",
            "expense:bank_statement_as_invoice",
            "expense:no_invoice_required",
            "income:all",
            "income:requires_invoice",
            "income:no_invoice_required",
            "income:cash_income",
        ]
        return [
            scope_key
            for scope_key in scope_keys
            if self.enqueue_refresh(scope_key, reason=reason)
        ]

    def enqueue_refresh(self, scope_key: str, *, reason: str) -> bool:
        enqueue = getattr(self._queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            return False
        enqueue(scope_type="pending_invoice", scope_key=scope_key, reason=reason)
        return True

    @staticmethod
    def scope_key(*, direction: str, filter_name: str | None = None) -> str:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter_name or "all").strip() or "all"
        return f"{normalized_direction}:{normalized_filter}"

    @staticmethod
    def payload_requires_schema_refresh(payload: dict[str, Any]) -> bool:
        rows = list(payload.get("rows") or [])
        if not rows:
            return False
        for row in rows:
            if not isinstance(row, dict):
                return True
            if not isinstance(row.get("invoice_acquisition_status"), dict):
                return True
            if not isinstance(row.get("input_invoices"), dict):
                return True
            if not isinstance(row.get("oa"), dict):
                return True
        return False

    def _list_rows_callable(self) -> Callable[..., Any]:
        list_rows = getattr(self._repository, "list_pending_invoice_rows", None)
        if not callable(list_rows):
            raise PendingInvoiceError(
                "pending_invoice_read_model_unavailable",
                "Pending invoice SQL read repository is not configured.",
                status_code=HTTPStatus.SERVICE_UNAVAILABLE,
            )
        return list_rows

    @staticmethod
    def _validate_direction_filter(*, direction: str, filter_name: str) -> None:
        if direction not in {"expense", "income", "all"}:
            raise PendingInvoiceError("invalid_direction", "direction must be expense, income or all.")
        if filter_name not in VALID_FILTERS:
            raise PendingInvoiceError("invalid_filter", "filter must be all or a supported pending invoice group.")
        if direction == "all" and filter_name != "all":
            raise PendingInvoiceError(
                "invalid_filter_for_all",
                "All pending invoice rows only support filter=all.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if direction == "income" and filter_name not in {"all", *INCOME_FILTERS}:
            raise PendingInvoiceError(
                "invalid_filter_for_income",
                "Income pending invoice rows support all, requires_invoice, no_invoice_required or cash_income filters.",
                status_code=HTTPStatus.BAD_REQUEST,
            )
        if direction == "expense" and filter_name not in {"all", *EXPENSE_FILTERS}:
            raise PendingInvoiceError(
                "invalid_filter_for_expense",
                "Expense pending invoice rows support all, requires_invoice, bank_statement_as_invoice or no_invoice_required filters.",
                status_code=HTTPStatus.BAD_REQUEST,
            )

    @staticmethod
    def _optional_int(value: object) -> int | None:
        try:
            if value in (None, ""):
                return None
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None

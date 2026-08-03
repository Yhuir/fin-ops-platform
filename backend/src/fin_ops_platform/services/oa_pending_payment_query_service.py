from __future__ import annotations

from datetime import date
from http import HTTPStatus
from typing import Any, Callable

from fin_ops_platform.services.oa_pending_payment_canonical_rows import build_oa_pending_payment_rows
from fin_ops_platform.services.oa_pending_payment_query_contract import (
    OaPendingPaymentError,
    filter_config,
    parse_filters,
    parse_positive_int,
    parse_sort,
    parse_view_mode,
)
from fin_ops_platform.services.oa_pending_payment_details import (
    oa_pending_payment_bank_detail_from_row,
    oa_pending_payment_invoice_detail_from_row,
    oa_pending_payment_oa_detail_from_row,
    oa_pending_payment_relation_details_from_row,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    PostgresOaPendingPaymentStatusSnapshotReader,
)
from fin_ops_platform.services.search_query import normalize_money_search_query


class OaPendingPaymentQueryService:
    """Compose the OA pending-payment page from canonical PostgreSQL facts."""

    def __init__(self, *, repository: Any | None) -> None:
        self._repository = repository

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        repository = self._repository_required()
        month = _parse_month(_query_value(query, "month"))
        trade_date_from = _parse_date(_query_value(query, "trade_date_from"), "trade_date_from")
        trade_date_to = _parse_date(_query_value(query, "trade_date_to"), "trade_date_to")
        if trade_date_from and trade_date_to and trade_date_from > trade_date_to:
            raise OaPendingPaymentError(
                "invalid_trade_date_range",
                "trade_date_from must be on or before trade_date_to.",
            )
        page = parse_positive_int(_query_value(query, "page") or 1, "page")
        page_size = parse_positive_int(_query_value(query, "page_size") or 50, "page_size", maximum=200)
        filters = parse_filters(_query_value(query, "filters"))
        sort_field, sort_direction = parse_sort(
            _query_value(query, "sort_field") or "bank_trade_time",
            _query_value(query, "sort_direction") or "desc",
        )
        view_mode = parse_view_mode(_query_value(query, "view_mode"))
        keyword = normalize_money_search_query(_query_value(query, "keyword")) or None
        try:
            with repository.snapshot() as snapshot:
                selected = snapshot.select_page(
                    tenant_id=tenant_id,
                    month=month,
                    keyword=keyword,
                    trade_date_from=trade_date_from,
                    trade_date_to=trade_date_to,
                    filters=filters,
                    sort_field=sort_field,
                    sort_direction=sort_direction,
                    page=page,
                    page_size=page_size,
                    view_mode=view_mode,
                )
                descriptors = list(selected.get("descriptors") or [])
                rows = self._hydrate_rows(snapshot, descriptors, tenant_id=tenant_id)
        except OaPendingPaymentError:
            raise
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_oa_pending_payment_query", str(exc)) from exc
        return {
            "rows": rows,
            "pagination": dict(selected.get("pagination") or {}),
            "summary": dict(selected.get("summary") or {}),
            "statistics": dict(selected.get("statistics") or {}),
            "filterConfig": filter_config(),
            "filterOptions": dict(selected.get("filterOptions") or {}),
            "appliedFilters": {"filters": filters},
            "sort": {"field": sort_field, "direction": sort_direction},
            "viewMode": view_mode,
        }

    def bank_transaction_candidates(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        relation_status = str(_query_value(query, "relation_status") or "all").strip() or "all"
        keyword = normalize_money_search_query(_query_value(query, "keyword")) or None
        page = parse_positive_int(_query_value(query, "page") or 1, "page")
        page_size = parse_positive_int(
            _query_value(query, "page_size") or _query_value(query, "pageSize") or 100,
            "page_size",
            maximum=200,
        )
        repository = self._repository_required()
        with repository.snapshot() as snapshot:
            result = snapshot.bank_transaction_candidates(
                tenant_id=tenant_id,
                relation_status=relation_status,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
        return {
            **result,
            "filters": {
                "relationStatus": relation_status,
                "keyword": keyword or "",
                "oaRowIds": _query_values(query, "oa_row_ids", "oaRowIds"),
            },
        }

    def oa_detail(
        self,
        oa_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None = None,
    ) -> dict[str, Any]:
        return self._detail(
            identifier_kind="oa",
            identifier=oa_id,
            tenant_id=tenant_id,
            requested_scope_key=requested_scope_key,
            builder=oa_pending_payment_oa_detail_from_row,
            not_found_code="oa_not_found",
            not_found_message=f"OA detail not found: {oa_id}",
        )

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None = None,
    ) -> dict[str, Any]:
        return self._detail(
            identifier_kind="bank",
            identifier=bank_transaction_id,
            tenant_id=tenant_id,
            requested_scope_key=requested_scope_key,
            builder=lambda row: oa_pending_payment_bank_detail_from_row(row, bank_transaction_id),
            not_found_code="bank_transaction_not_found",
            not_found_message=f"Bank transaction detail not found: {bank_transaction_id}",
        )

    def invoice_detail(
        self,
        invoice_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None = None,
    ) -> dict[str, Any]:
        return self._detail(
            identifier_kind="invoice",
            identifier=invoice_id,
            tenant_id=tenant_id,
            requested_scope_key=requested_scope_key,
            builder=lambda row: oa_pending_payment_invoice_detail_from_row(row, invoice_id),
            not_found_code="invoice_not_found",
            not_found_message=f"Invoice detail not found: {invoice_id}",
        )

    def relation_details(
        self,
        row_id: str,
        *,
        kind: str,
        tenant_id: str,
        requested_scope_key: str | None = None,
    ) -> dict[str, Any]:
        return self._detail(
            identifier_kind="row",
            identifier=row_id,
            tenant_id=tenant_id,
            requested_scope_key=requested_scope_key,
            builder=lambda row: oa_pending_payment_relation_details_from_row(row, kind=kind),
            not_found_code="row_not_found",
            not_found_message=f"OA pending payment row not found: {row_id}",
        )

    def _detail(
        self,
        *,
        identifier_kind: str,
        identifier: str,
        tenant_id: str,
        requested_scope_key: str | None,
        builder: Callable[[dict[str, Any]], dict[str, Any]],
        not_found_code: str,
        not_found_message: str,
    ) -> dict[str, Any]:
        repository = self._repository_required()
        scope_key = _parse_month(requested_scope_key)
        try:
            with repository.snapshot() as snapshot:
                descriptor = snapshot.find_descriptor(
                    tenant_id=tenant_id,
                    identifier_kind=identifier_kind,
                    identifier=identifier,
                    month=scope_key,
                )
                if not isinstance(descriptor, dict):
                    raise OaPendingPaymentError(
                        not_found_code,
                        not_found_message,
                        status_code=HTTPStatus.NOT_FOUND,
                    )
                rows = self._hydrate_rows(snapshot, [descriptor], tenant_id=tenant_id)
        except OaPendingPaymentError:
            raise
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_oa_pending_payment_query", str(exc)) from exc
        if not rows:
            raise OaPendingPaymentError(
                not_found_code,
                not_found_message,
                status_code=HTTPStatus.NOT_FOUND,
            )
        try:
            return builder(rows[0])
        except ValueError as exc:
            raise OaPendingPaymentError("invalid_relation_kind", str(exc)) from exc

    @staticmethod
    def _hydrate_rows(
        repository: Any,
        descriptors: list[dict[str, Any]],
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        if not descriptors:
            return []
        facts = repository.load_facts(descriptors, tenant_id=tenant_id)
        completed_records = list(facts.get("completed_records") or [])
        in_progress_records = list(facts.get("in_progress_records") or [])
        canonical_relations = list(facts.get("canonical_relations") or [])
        pending_relations = list(facts.get("pending_relations") or [])
        bank_transactions = list(facts.get("bank_transactions") or [])
        invoices = list(facts.get("invoices") or [])
        payment_statuses = dict(facts.get("payment_statuses") or {})
        rows_by_id: dict[str, dict[str, Any]] = {}
        scopes = sorted(
            {
                (str(descriptor.get("scope_key") or ""), str(descriptor.get("source_kind") or ""))
                for descriptor in descriptors
            }
        )
        for scope_key, source_kind in scopes:
            if not scope_key:
                continue
            rows = build_oa_pending_payment_rows(
                records=completed_records if source_kind == "completed" else in_progress_records,
                relations=canonical_relations if source_kind == "completed" else pending_relations,
                bank_transactions=bank_transactions,
                invoices=invoices,
                payment_statuses_by_flow_id=payment_statuses,
                flow_id_resolver=PostgresOaPendingPaymentStatusSnapshotReader.resolve_flow_id,
                scope_key=scope_key,
            )
            rows_by_id.update(
                {
                    str(row.get("id") or ""): row
                    for row in rows
                    if isinstance(row, dict) and str(row.get("id") or "")
                }
            )
        expected_ids = [str(descriptor.get("row_id") or "") for descriptor in descriptors]
        missing_ids = [row_id for row_id in expected_ids if row_id not in rows_by_id]
        if missing_ids:
            raise RuntimeError(
                "OA pending payment canonical hydration is incomplete: " + ", ".join(missing_ids)
            )
        return [rows_by_id[row_id] for row_id in expected_ids]

    def _repository_required(self) -> Any:
        if self._repository is None:
            raise RuntimeError("OA pending payment canonical query repository is not configured.")
        return self._repository


def _query_value(query: dict[str, list[str]], key: str) -> Any:
    values = query.get(key)
    return values[0] if values else None


def _query_values(query: dict[str, list[str]], *keys: str) -> list[str]:
    values: list[str] = []
    for key in keys:
        for value in query.get(key, []):
            normalized = str(value or "").strip()
            if normalized and normalized not in values:
                values.append(normalized)
    return values


def _parse_month(value: Any) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        date.fromisoformat(f"{normalized}-01")
    except ValueError as exc:
        raise OaPendingPaymentError("invalid_month", "month must be YYYY-MM.") from exc
    if len(normalized) != 7:
        raise OaPendingPaymentError("invalid_month", "month must be YYYY-MM.")
    return normalized


def _parse_date(value: Any, field: str) -> str | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise OaPendingPaymentError(f"invalid_{field}", f"{field} must be YYYY-MM-DD.") from exc

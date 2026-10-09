from __future__ import annotations

from datetime import date
from typing import Any

from fin_ops_platform.services.bank_settings import bank_short_names_from_mappings, bank_summary_with_short_names
from fin_ops_platform.services.bank_transaction_unit import original_bank_transaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    PaymentStatusEvaluationContext,
    evaluate_payment_status_rules,
    normalize_payment_status_rules_settings,
    public_payment_status_rules_payload,
)
from fin_ops_platform.services.input_invoice_usage_query_contract import (
    input_invoice_usage_filter_config,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
    _money,
)
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
)
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    InvoiceUsageCollectionCanonicalSnapshot,
)
from fin_ops_platform.services.source_record_details import (
    bank_source_detail,
    invoice_source_detail,
    oa_source_detail,
    source_invoice_groups,
)


class InputInvoiceUsageCanonicalQueryService:
    """Serve the input-invoice page from one canonical snapshot per request."""

    def __init__(
        self,
        *,
        repository: Any | None,
        row_assembler: InputInvoiceUsageQueryService,
    ) -> None:
        self._repository = repository
        self._row_assembler = row_assembler

    def rows(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> dict[str, Any]:
        kwargs = _query_kwargs(query)
        return self.list_rows(**kwargs, tenant_id=tenant_id)

    def list_rows(
        self,
        *,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        month: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = "invoice_date",
        sort_direction: str | None = "desc",
        tenant_id: str = "default",
        include_statistics: bool = True,
    ) -> dict[str, Any]:
        page_number = _positive_int(page, "page")
        page_limit = _positive_int(page_size, "page_size", maximum=200)
        try:
            month, invoice_date_from, invoice_date_to = _validate_temporal_query(
                month,
                invoice_date_from,
                invoice_date_to,
            )
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_date_filter", str(exc)) from exc
        parsed_filters = self._row_assembler._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = (
            self._row_assembler._parse_sort(sort_field, sort_direction)
        )
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        snapshot = self._repository.load_page(
            page=page_number,
            page_size=page_limit,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field=normalized_sort_field,
            sort_direction=normalized_sort_direction,
            tenant_id=tenant_id,
        )
        return self._payload(
            snapshot,
            filters=parsed_filters,
            sort_field=normalized_sort_field,
            sort_direction=normalized_sort_direction,
            include_statistics=include_statistics,
        )

    def candidate_rows(self, query: dict[str, list[str]], *, tenant_id: str = "default") -> dict[str, Any]:
        """Use the main page's unused scope, paginated by individual invoice."""
        kwargs = _query_kwargs(query)
        page = _positive_int(kwargs["page"], "page")
        page_size = _positive_int(kwargs["page_size"], "page_size", maximum=200)
        try:
            month, invoice_date_from, invoice_date_to = _validate_temporal_query(
                kwargs["month"], kwargs["invoice_date_from"], kwargs["invoice_date_to"],
            )
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_date_filter", str(exc)) from exc
        filters = [item for item in self._row_assembler._parse_filters(kwargs["filters"])
                   if item["field"] not in {"usage_status", "payment_group", "payment_status"}]
        filters.append({"field": "usage_status", "operator": "in", "values": ["unused"]})
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "反提候选查询未配置。", status_code=503)
        snapshot = self._repository.load_page(
            page=page, page_size=page_size, keyword=kwargs["keyword"],
            invoice_date_from=invoice_date_from, invoice_date_to=invoice_date_to, month=month,
            filters=filters, sort_field="invoice_date", sort_direction="desc",
            tenant_id=tenant_id, invoice_level=True,
        )
        return self._candidate_payload(snapshot, filters=filters)

    def candidate_rows_by_invoice_ids(self, invoice_ids: list[str], *, tenant_id: str = "default") -> dict[str, Any]:
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "反提候选查询未配置。", status_code=503)
        snapshot = self._repository.load_rows_by_invoice_ids(invoice_ids, tenant_id=tenant_id, invoice_level=True)
        return self._candidate_payload(snapshot, filters=[])

    def _candidate_payload(
        self, snapshot: InvoiceUsageCollectionCanonicalSnapshot, *, filters: list[dict[str, Any]],
    ) -> dict[str, Any]:
        payload = self._payload(snapshot, filters=filters, sort_field="invoice_date", sort_direction="desc", include_statistics=False)
        usage_by_id = {group["primary"].id: group["usage_status"] for group in snapshot.groups}
        for row in payload["rows"]:
            row["usageStatus"] = usage_by_id[row["invoiceId"]]
        return payload

    def filter_options(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        payload = self.rows(
            {
                **query,
                "page": ["1"],
                "page_size": ["1"],
            },
            tenant_id=tenant_id,
        )
        return {
            "fields": list(payload.get("filterOptions") or []),
            "context": {
                "keyword": _first(query, "keyword"),
                "invoiceDateFrom": _first(query, "invoice_date_from") or None,
                "invoiceDateTo": _first(query, "invoice_date_to") or None,
                "month": _first(query, "month") or None,
                "filters": self._row_assembler._parse_filters(
                    _first(query, "filters") or None
                ),
            },
        }

    def export_page(self, **kwargs: Any) -> dict[str, Any]:
        kwargs.pop("include_statistics", None)
        return self.list_rows(**kwargs, include_statistics=False)

    def export_rows(
        self,
        *,
        limit: int,
        tenant_id: str = "default",
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            month, invoice_date_from, invoice_date_to = _validate_temporal_query(
                kwargs.get("month"),
                kwargs.get("invoice_date_from"),
                kwargs.get("invoice_date_to"),
            )
        except ValueError as exc:
            raise InputInvoiceUsageError("invalid_date_filter", str(exc)) from exc
        parsed_filters = self._row_assembler._parse_filters(kwargs.get("filters"))
        sort_field, sort_direction = self._row_assembler._parse_sort(
            kwargs.get("sort_field"),
            kwargs.get("sort_direction"),
        )
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        payload = self._repository.export_invoices(
            limit=limit, keyword=kwargs.get("keyword"),
            invoice_date_from=invoice_date_from, invoice_date_to=invoice_date_to,
            month=month, filters=parsed_filters, sort_field=sort_field,
            sort_direction=sort_direction, tenant_id=tenant_id,
        )
        return {
            "rows": [{"invoice": self._row_assembler._invoice_summary(invoice, [invoice])}
                     for invoice in payload["invoices"]],
            "total": payload["total"],
        }

    def rows_by_invoice_ids(
        self,
        invoice_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        snapshot = self._repository.load_rows_by_invoice_ids(
            invoice_ids,
            tenant_id=tenant_id,
        )
        return self._payload(
            snapshot,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
            include_statistics=False,
        )

    def invoice_detail(
        self,
        invoice_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        records = self._repository.load_invoice_records(invoice_id, tenant_id=tenant_id)
        group = _group_for_invoice(source_invoice_groups(records), invoice_id)
        if group is None:
            raise InputInvoiceUsageError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=404,
            )
        return invoice_source_detail(group)

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        transaction, labels = self._repository.load_bank_source(bank_transaction_id, tenant_id=tenant_id)
        if transaction is None:
            raise InputInvoiceUsageError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=404,
            )
        return bank_source_detail(transaction, labels=labels)

    def oa_detail(
        self,
        oa_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            raise InputInvoiceUsageError("input_invoice_usage_query_unavailable", "进项发票查询未配置。", status_code=503)
        record = self._repository.load_oa_record(oa_id, tenant_id=tenant_id)
        return _oa_detail(record, oa_id=oa_id)


    def payment_status_rules(self) -> dict[str, Any]:
        return self._row_assembler.payment_status_rules()

    def _payload(
        self,
        snapshot: InvoiceUsageCollectionCanonicalSnapshot,
        *,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
        include_statistics: bool,
    ) -> dict[str, Any]:
        fields = _filter_options(
            config=input_invoice_usage_filter_config(),
            counts=snapshot.facet_counts,
        )
        payload: dict[str, Any] = {
            "classification": snapshot.classification,
            "rows": self._rows_from_snapshot(snapshot),
            "pagination": dict(snapshot.pagination),
            "summary": dict(snapshot.summary),
            "appliedFilters": {"filters": filters},
            "sort": {"field": sort_field, "direction": sort_direction},
            "filterConfig": input_invoice_usage_filter_config(),
            "filterOptions": fields,
        }
        if include_statistics:
            payload["statistics"] = dict(snapshot.statistics)
        return payload

    def _rows_from_snapshot(
        self,
        snapshot: InvoiceUsageCollectionCanonicalSnapshot,
    ) -> list[dict[str, Any]]:
        context = _context(snapshot)
        lifecycle_policy = InvoiceLifecyclePolicy(
            input_payment_rules_provider=_SnapshotPaymentRulesProvider(
                snapshot.payment_status_rules
            )
        )
        rows = [
            self._row_assembler._row_payload(
                group,
                context=context,
                lifecycle_policy=lifecycle_policy,
            )
            for group in snapshot.groups
        ]
        names = bank_short_names_from_mappings(snapshot.bank_account_mappings)
        for row in rows:
            if "bankTransactions" in row:
                row["bankTransactions"] = bank_summary_with_short_names(row["bankTransactions"], names)
        return rows


class _SnapshotPaymentRulesProvider:
    def __init__(self, settings: dict[str, Any]) -> None:
        self._settings = normalize_payment_status_rules_settings(settings)

    def payment_status_rules_payload(self, *, can_save: bool = True) -> dict[str, Any]:
        return public_payment_status_rules_payload(
            self._settings,
            read_only=True,
            can_save=can_save,
        )

    def rules_source_version(self) -> int:
        return int(self._settings["version"])

    def evaluate(self, context: PaymentStatusEvaluationContext) -> dict[str, str]:
        return evaluate_payment_status_rules(self._settings["rules"], context)


class _StaticOaProjection:
    def __init__(self, records: list[Any]) -> None:
        self._records = {
            str(getattr(record, "id", "") or ""): record for record in records
        }

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[Any]:
        return [self._records[row_id] for row_id in row_ids if row_id in self._records]


def _context(
    snapshot: InvoiceUsageCollectionCanonicalSnapshot,
) -> DistributedInvoiceRelationContext:
    invoices = [
        invoice
        for group in [*snapshot.groups, *snapshot.supporting_groups]
        for invoice in list(group.get("line_items") or [])
    ]
    context = DistributedInvoiceRelationContext(
        import_service=ImportNormalizationService(
            existing_invoices=_dedupe_objects(invoices),
            existing_transactions=list(snapshot.transactions),
        ),
        relation_reader=None,
        oa_projection=_StaticOaProjection(snapshot.oa_records),
    )
    context.add_distributed_relations(snapshot.relations)
    return context


def _query_kwargs(query: dict[str, list[str]]) -> dict[str, Any]:
    return {
        "page": _first(query, "page") or 1,
        "page_size": _first(query, "page_size") or 50,
        "keyword": _first(query, "keyword") or None,
        "invoice_date_from": _first(query, "invoice_date_from") or None,
        "invoice_date_to": _first(query, "invoice_date_to") or None,
        "month": _first(query, "month") or None,
        "filters": _first(query, "filters") or None,
        "sort_field": _first(query, "sort_field") or "invoice_date",
        "sort_direction": _first(query, "sort_direction") or "desc",
    }


def _first(query: dict[str, list[str]], key: str) -> str:
    values = query.get(key) or []
    return str(values[0]) if values else ""


def _positive_int(
    value: int | str | None,
    field: str,
    *,
    maximum: int | None = None,
) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise InputInvoiceUsageError(
            "invalid_paging",
            f"{field} must be a positive integer.",
        ) from exc
    if number < 1 or (maximum is not None and number > maximum):
        limit = f" <= {maximum}" if maximum is not None else ""
        raise InputInvoiceUsageError(
            "invalid_paging",
            f"{field} must be a positive integer{limit}.",
        )
    return number


def _validate_temporal_query(
    month: str | None,
    invoice_date_from: str | None,
    invoice_date_to: str | None,
) -> tuple[str | None, str | None, str | None]:
    normalized_month = str(month or "").strip() or None
    if normalized_month not in {None, "all"}:
        try:
            date.fromisoformat(f"{normalized_month}-01")
        except ValueError as exc:
            raise ValueError("month must be YYYY-MM or all.") from exc
    normalized_from = _query_date(invoice_date_from, "invoice_date_from")
    normalized_to = _query_date(invoice_date_to, "invoice_date_to")
    if normalized_from and normalized_to and normalized_from > normalized_to:
        raise ValueError("invoice_date_from must not be after invoice_date_to.")
    return normalized_month, normalized_from, normalized_to


def _query_date(value: str | None, field: str) -> str | None:
    normalized = str(value or "").strip() or None
    if normalized is None:
        return None
    try:
        return date.fromisoformat(normalized).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} must be YYYY-MM-DD.") from exc


def _filter_options(
    *,
    config: list[dict[str, Any]],
    counts: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    return [{**item, "options": list(counts.get(str(item["field"]), []))} for item in config]


def _filters_without_field(
    filters: list[dict[str, Any]],
    field: str,
) -> list[dict[str, Any]]:
    return [
        item
        for item in filters
        if str(item.get("field") or "") != field
    ]


def _replace_filter_option_field(
    fields: list[dict[str, Any]],
    replacement_fields: list[dict[str, Any]],
    *,
    field: str,
) -> list[dict[str, Any]]:
    replacement = next(
        (
            item
            for item in replacement_fields
            if str(item.get("field") or "") == field
        ),
        None,
    )
    if replacement is None:
        return fields
    return [
        replacement if str(item.get("field") or "") == field else item
        for item in fields
    ]


def _dedupe_objects(values: list[Any]) -> list[Any]:
    result: list[Any] = []
    seen: set[str] = set()
    for value in values:
        key = str(getattr(value, "id", "") or "")
        if key and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _group_for_invoice(
    groups: list[dict[str, Any]],
    invoice_id: str,
) -> dict[str, Any] | None:
    return next(
        (
            group
            for group in groups
            if invoice_id
            in {
                str(getattr(invoice, "id", "") or "")
                for invoice in list(group.get("line_items") or [])
            }
        ),
        None,
    )


def _oa_detail(record: Any | None, *, oa_id: str) -> dict[str, Any]:
    if record is None:
        return {"oaId": oa_id, "detailAvailable": False}
    return oa_source_detail(record)

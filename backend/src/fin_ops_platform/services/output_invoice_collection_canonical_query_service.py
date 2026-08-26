from __future__ import annotations

from typing import Any

from fin_ops_platform.services.input_invoice_usage_canonical_query_service import (
    _dedupe_objects,
    _filter_options,
    _filters_without_field,
    _first,
    _replace_filter_option_field,
    _validate_temporal_query,
)
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
)
from fin_ops_platform.services.output_invoice_collection_service import (
    OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT,
    OutputInvoiceCollectionError,
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    InvoiceUsageCollectionCanonicalSnapshot,
)


class OutputInvoiceCollectionCanonicalQueryService:
    """Serve the output-invoice page from one canonical snapshot per request."""

    def __init__(
        self,
        *,
        repository: Any | None,
        row_assembler: OutputInvoiceCollectionQueryService,
    ) -> None:
        self._repository = repository
        self._row_assembler = row_assembler

    def rows(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self.list_rows(**_query_kwargs(query), tenant_id=tenant_id)

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
            raise OutputInvoiceCollectionError(
                "invalid_date_filter",
                str(exc),
            ) from exc
        parsed_filters = self._row_assembler._parse_filters(filters)
        normalized_sort_field, normalized_sort_direction = (
            self._row_assembler._parse_sort(sort_field, sort_direction)
        )
        if self._repository is None:
            payload = self._row_assembler.list_rows(
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
            options = self._row_assembler.filter_options(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=parsed_filters,
                tenant_id=tenant_id,
            )
            status_options = self._row_assembler.filter_options(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=_filters_without_field(parsed_filters, "collection_status"),
                tenant_id=tenant_id,
            )
            payload["filterOptions"] = _replace_filter_option_field(
                list(options.get("fields") or []),
                list(status_options.get("fields") or []),
                field="collection_status",
            )
            payload["statistics"] = _local_statistics(list(payload.get("rows") or []))
            return payload
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
        )

    def filter_options(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        payload = self.rows(
            {**query, "page": ["1"], "page_size": ["1"]},
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

    def export_preview(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        rows = self._export_rows(query, tenant_id=tenant_id)
        return self._row_assembler.export_preview_for_rows(rows=rows)

    def export(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> tuple[str, bytes]:
        rows = self._export_rows(query, tenant_id=tenant_id)
        return self._row_assembler.export_for_rows(rows)

    def row_by_id(
        self,
        row_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        if self._repository is None:
            return self._row_assembler.row_by_id(row_id, tenant_id=tenant_id)
        snapshot = self._repository.load_row(row_id, tenant_id=tenant_id)
        return next(
            (
                row
                for row in self._rows_from_snapshot(snapshot)
                if row.get("id") == row_id or row.get("invoiceId") == row_id
            ),
            None,
        )

    def relation_details(
        self,
        row_id: str,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        kind = _first(query, "kind")
        if kind not in {"bank", "invoice"}:
            raise OutputInvoiceCollectionError(
                "invalid_relation_kind",
                "kind must be bank or invoice.",
            )
        row = self.row_by_id(row_id, tenant_id=tenant_id)
        if row is None:
            raise OutputInvoiceCollectionError(
                "row_not_found",
                f"Output invoice collection row not found: {row_id}",
                status_code=404,
            )
        relation_payload = {
            "bank": row["bankTransactions"],
            "invoice": row["invoiceRelations"],
        }[kind]
        return {
            "rowId": row_id,
            "kind": kind,
            "title": {
                "bank": "银行流水关联明细",
                "invoice": "发票关联明细",
            }[kind],
            "relationCount": int(relation_payload.get("relationCount") or 0),
            "summaries": list(relation_payload.get("summaries") or []),
        }

    def invoice_detail(
        self,
        invoice_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            return self._row_assembler.invoice_detail(invoice_id)
        snapshot = self._repository.load_row(invoice_id, tenant_id=tenant_id)
        group = next(
            (
                candidate
                for candidate in snapshot.groups
                if invoice_id
                in {
                    str(getattr(invoice, "id", "") or "")
                    for invoice in list(candidate.get("line_items") or [])
                }
            ),
            None,
        )
        if group is None:
            raise OutputInvoiceCollectionError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=404,
            )
        return _output_invoice_detail(group)

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            return self._row_assembler.bank_transaction_detail(bank_transaction_id)
        snapshot = self._repository.load_row(
            bank_transaction_id,
            tenant_id=tenant_id,
        )
        transaction = next(
            (
                item
                for item in snapshot.transactions
                if str(getattr(item, "id", "") or "") == bank_transaction_id
            ),
            None,
        )
        if transaction is None:
            raise OutputInvoiceCollectionError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=404,
            )
        return {
            "id": transaction.id,
            "counterpartyName": transaction.counterparty_name_raw,
            "tradeTime": transaction.trade_time or transaction.txn_date or "",
            "amount": f"{transaction.amount:.2f}",
            "direction": str(
                getattr(transaction.txn_direction, "value", transaction.txn_direction)
            ),
            "bankName": transaction.imported_bank_name or "",
            "accountNo": transaction.account_no,
            "accountLast4": transaction.imported_bank_last4
            or str(transaction.account_no or "")[-4:],
            "summary": transaction.summary or "",
            "remark": transaction.remark or "",
            "currency": transaction.currency or "CNY",
            "bankTextFields": list(transaction.bank_text_fields),
        }

    def _export_rows(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        try:
            month, invoice_date_from, invoice_date_to = _validate_temporal_query(
                _first(query, "month") or None,
                _first(query, "invoice_date_from") or None,
                _first(query, "invoice_date_to") or None,
            )
        except ValueError as exc:
            raise OutputInvoiceCollectionError(
                "invalid_date_filter",
                str(exc),
            ) from exc
        if self._repository is None:
            local_kwargs = _query_kwargs(query)
            local_kwargs.update(
                {
                    "month": month,
                    "invoice_date_from": invoice_date_from,
                    "invoice_date_to": invoice_date_to,
                }
            )
            local_kwargs.pop("page", None)
            local_kwargs.pop("page_size", None)
            return self._row_assembler._export_rows(
                **local_kwargs,
                tenant_id=tenant_id,
            )
        parsed_filters = self._row_assembler._parse_filters(
            _first(query, "filters") or None
        )
        sort_field, sort_direction = self._row_assembler._parse_sort(
            _first(query, "sort_field") or "invoice_date",
            _first(query, "sort_direction") or "desc",
        )
        snapshot = self._repository.load_page(
            page=1,
            page_size=OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT + 1,
            keyword=_first(query, "keyword") or None,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            tenant_id=tenant_id,
        )
        if snapshot.pagination["total"] > OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT:
            raise OutputInvoiceCollectionError(
                "output_invoice_collection_export_row_limit_exceeded",
                "当前筛选结果超过 20000 行，请缩小筛选范围后导出。",
                details={
                    "total": snapshot.pagination["total"],
                    "limit": OUTPUT_INVOICE_COLLECTION_EXPORT_ROW_LIMIT,
                },
            )
        return self._rows_from_snapshot(snapshot)

    def _payload(
        self,
        snapshot: InvoiceUsageCollectionCanonicalSnapshot,
        *,
        filters: list[dict[str, Any]],
        sort_field: str,
        sort_direction: str,
    ) -> dict[str, Any]:
        config = self._row_assembler._filter_config()
        return {
            "rows": self._rows_from_snapshot(snapshot),
            "pagination": dict(snapshot.pagination),
            "summary": dict(snapshot.summary),
            "statistics": dict(snapshot.statistics),
            "appliedFilters": {"filters": filters},
            "sort": {"field": sort_field, "direction": sort_direction},
            "filterConfig": config,
            "filterOptions": _filter_options(
                config=config,
                counts=snapshot.facet_counts,
            ),
        }

    def _rows_from_snapshot(
        self,
        snapshot: InvoiceUsageCollectionCanonicalSnapshot,
    ) -> list[dict[str, Any]]:
        context = _context(snapshot)
        all_groups = [*snapshot.groups, *snapshot.supporting_groups]
        groups_by_key = {
            str(group.get("group_key") or ""): group
            for group in all_groups
        }
        return [
            self._row_assembler._row_payload(
                group,
                [
                    group,
                    *[
                        groups_by_key[key]
                        for key in list(group.get("supporting_group_keys") or [])
                        if key in groups_by_key
                    ],
                ],
                context=context,
            )
            for group in snapshot.groups
        ]


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


def _positive_int(
    value: int | str | None,
    field: str,
    *,
    maximum: int | None = None,
) -> int:
    try:
        number = int(value if value not in (None, "") else 1)
    except (TypeError, ValueError) as exc:
        raise OutputInvoiceCollectionError(
            "invalid_paging",
            f"{field} must be a positive integer.",
        ) from exc
    if number < 1 or (maximum is not None and number > maximum):
        limit = f" <= {maximum}" if maximum is not None else ""
        raise OutputInvoiceCollectionError(
            "invalid_paging",
            f"{field} must be a positive integer{limit}.",
        )
    return number


def _output_invoice_detail(group: dict[str, Any]) -> dict[str, Any]:
    primary = group["primary"]
    lines = list(group["line_items"])
    return {
        "id": primary.id,
        "invoiceIdentityKey": group["identity_key"],
        "invoiceNo": primary.invoice_no,
        "invoiceCode": primary.invoice_code or "",
        "digitalInvoiceNo": primary.digital_invoice_no or "",
        "invoiceDate": primary.invoice_date or "",
        "sellerName": primary.seller_name or "",
        "sellerTaxNo": primary.seller_tax_no or "",
        "buyerName": primary.buyer_name or primary.counterparty.name,
        "buyerTaxNo": primary.buyer_tax_no or primary.counterparty.tax_no or "",
        "amount": f"{sum((invoice.amount for invoice in lines), start=0):.2f}",
        "taxAmount": f"{sum((invoice.tax_amount or 0 for invoice in lines), start=0):.2f}",
        "totalWithTax": f"{sum((invoice.total_with_tax or invoice.amount for invoice in lines), start=0):.2f}",
        "taxRate": primary.tax_rate or "",
        "specificBusinessType": primary.specific_business_type or "",
        "taxableItemName": primary.taxable_item_name or "",
        "isPositiveInvoice": primary.is_positive_invoice or "",
        "lineItems": [
            OutputInvoiceCollectionQueryService._line_item_payload(invoice)
            for invoice in lines
        ],
    }


def _local_statistics(rows: list[dict[str, Any]]) -> dict[str, int]:
    invoice_count = sum(
        max(
            1,
            len(
                list(
                    (
                        row.get("invoiceRelations")
                        if isinstance(row.get("invoiceRelations"), dict)
                        else {}
                    ).get("summaries")
                    or []
                )
            ),
        )
        for row in rows
    )
    bank_rows = {
        str(item.get("id") or ""): item
        for row in rows
        for item in list((row.get("bankTransactions") or {}).get("summaries") or [])
        if isinstance(item, dict) and str(item.get("id") or "")
    }
    red_count = sum(
        1
        for row in rows
        if str((row.get("invoice") or {}).get("totalWithTax") or "").startswith("-")
    )
    return {
        "invoiceCount": invoice_count,
        "incomeBankTransactionCount": sum(
            str(item.get("direction") or "") in {"inflow", "收入"}
            for item in bank_rows.values()
        ),
        "blueInvoiceCount": max(0, invoice_count - red_count),
        "redInvoiceCount": red_count,
    }

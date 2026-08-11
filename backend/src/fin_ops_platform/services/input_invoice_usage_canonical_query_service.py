from __future__ import annotations

from datetime import date
from typing import Any

from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_query_contract import (
    input_invoice_usage_filter_config,
)
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    PaymentStatusEvaluationContext,
    evaluate_payment_status,
    normalize_payment_status_rules_settings,
    public_payment_status_rules_payload,
)
from fin_ops_platform.services.input_invoice_usage_service import (
    InputInvoiceUsageError,
    InputInvoiceUsageQueryService,
    _money,
    input_invoice_usage_relation_details_from_row,
)
from fin_ops_platform.services.invoice_relation_query_context import (
    DistributedInvoiceRelationContext,
)
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import (
    InvoiceUsageCollectionCanonicalSnapshot,
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
            )
            options = self._row_assembler.filter_options(
                keyword=keyword,
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=parsed_filters,
            )
            payload["filterOptions"] = list(options.get("fields") or [])
            payload["statistics"] = _input_statistics_from_rows(
                list(payload.get("rows") or [])
            )
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
            include_statistics=include_statistics,
        )

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
            payload = self._row_assembler.list_rows(
                page=1,
                page_size=min(limit, 200),
                keyword=kwargs.get("keyword"),
                invoice_date_from=invoice_date_from,
                invoice_date_to=invoice_date_to,
                month=month,
                filters=parsed_filters,
                sort_field=sort_field,
                sort_direction=sort_direction,
            )
            return payload
        snapshot = self._repository.load_page(
            page=1,
            page_size=limit,
            keyword=kwargs.get("keyword"),
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            month=month,
            filters=parsed_filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            tenant_id=tenant_id,
        )
        return self._payload(
            snapshot,
            filters=parsed_filters,
            sort_field=sort_field,
            sort_direction=sort_direction,
            include_statistics=False,
        )

    def rows_by_invoice_ids(
        self,
        invoice_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            rows = [
                row
                for row in self._row_assembler._build_rows(
                    month=None,
                    context=self._row_assembler._query_context(),
                )
                if str(row.get("invoiceId") or "") in set(invoice_ids)
                or any(
                    str(item.get("invoiceId") or "") in set(invoice_ids)
                    for item in list(
                        (row.get("invoiceRelations") or {}).get("summaries") or []
                    )
                    if isinstance(item, dict)
                )
            ]
            return {
                "rows": rows,
                "pagination": {"page": 1, "pageSize": len(rows), "total": len(rows)},
            }
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
            return self._row_assembler.invoice_detail(invoice_id)
        snapshot = self._repository.load_rows_by_invoice_ids(
            [invoice_id],
            tenant_id=tenant_id,
        )
        group = _group_for_invoice(snapshot.groups, invoice_id)
        if group is None:
            raise InputInvoiceUsageError(
                "invoice_not_found",
                f"Invoice detail not found: {invoice_id}",
                status_code=404,
            )
        return _input_invoice_detail(group)

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
        context = _context(snapshot)
        transaction = context.bank_transactions_by_id().get(bank_transaction_id)
        if transaction is None:
            raise InputInvoiceUsageError(
                "bank_transaction_not_found",
                f"Bank transaction detail not found: {bank_transaction_id}",
                status_code=404,
            )
        return _bank_detail(transaction, context=context)

    def oa_detail(
        self,
        oa_id: str,
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        if self._repository is None:
            return self._row_assembler.oa_detail(oa_id)
        record = self._repository.load_oa_record(oa_id, tenant_id=tenant_id)
        return _oa_detail(record, oa_id=oa_id)

    def relation_details(
        self,
        row_id: str,
        query: dict[str, list[str]],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        kind = _first(query, "kind")
        if kind not in {"oa", "bank", "invoice"}:
            raise InputInvoiceUsageError(
                "invalid_relation_kind",
                "kind must be oa, bank or invoice.",
            )
        if self._repository is None:
            return self._row_assembler.row_relation_details(row_id, kind=kind)
        snapshot = self._repository.load_row(row_id, tenant_id=tenant_id)
        rows = self._rows_from_snapshot(snapshot)
        row = next((item for item in rows if item.get("id") == row_id), None)
        if row is None:
            raise InputInvoiceUsageError(
                "row_not_found",
                f"Input invoice usage row not found: {row_id}",
                status_code=404,
            )
        relation_payload = {
            "oa": row["oa"],
            "bank": row["bankTransactions"],
            "invoice": row["invoiceRelations"],
        }[kind]
        return input_invoice_usage_relation_details_from_row(
            row,
            kind=kind,
            relations=_context(snapshot).relation_summaries_for_row(
                str(row.get("invoiceId") or "")
            ),
            relation_payload=relation_payload,
        )

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
        return [
            self._row_assembler._row_payload(
                group,
                context=context,
                lifecycle_policy=lifecycle_policy,
            )
            for group in snapshot.groups
        ]


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
        return evaluate_payment_status(self._settings, context)


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
        relation_facade=None,
        oa_projection=_StaticOaProjection(snapshot.oa_records),
        require_fresh_relations=False,
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


def _input_invoice_detail(group: dict[str, Any]) -> dict[str, Any]:
    primary = group["primary"]
    lines = list(group["line_items"])
    total = sum(
        (
            invoice.total_with_tax
            if invoice.total_with_tax is not None
            else invoice.amount + (invoice.tax_amount or 0)
            for invoice in lines
        ),
        start=0,
    )
    return {
        "id": primary.id,
        "invoiceIdentityKey": group["identity_key"],
        "invoiceNo": primary.invoice_no,
        "invoiceCode": primary.invoice_code or "",
        "digitalInvoiceNo": primary.digital_invoice_no or "",
        "invoiceDate": primary.invoice_date or "",
        "sellerName": primary.seller_name or primary.counterparty.name,
        "sellerTaxNo": primary.seller_tax_no or primary.counterparty.tax_no or "",
        "buyerName": primary.buyer_name or "",
        "buyerTaxNo": primary.buyer_tax_no or "",
        "amount": f"{sum((invoice.amount for invoice in lines), start=0):.2f}",
        "taxAmount": f"{sum((invoice.tax_amount or 0 for invoice in lines), start=0):.2f}",
        "totalWithTax": f"{total:.2f}",
        "taxRate": primary.tax_rate or "",
        "taxClassificationCode": primary.tax_classification_code or "",
        "specificBusinessType": primary.specific_business_type or "",
        "taxableItemName": primary.taxable_item_name or "",
        "invoiceSource": primary.invoice_source or "",
        "invoiceKind": primary.invoice_kind or "",
        "invoiceStatus": primary.invoice_status_from_source
        or str(primary.status.value),
        "isPositiveInvoice": primary.is_positive_invoice or "",
        "riskLevel": primary.risk_level or "",
        "issuer": primary.issuer or "",
        "remark": primary.remark or "",
        "sourceBatchId": primary.source_batch_id or "",
        "sourceLinks": list(primary.source_links),
        "lineItems": [
            InputInvoiceUsageQueryService._line_item_payload(invoice)
            for invoice in lines
        ],
    }


def _bank_detail(transaction: Any, *, context: DistributedInvoiceRelationContext) -> dict[str, Any]:
    direction = str(getattr(transaction.txn_direction, "value", transaction.txn_direction))
    return {
        "id": transaction.id,
        "counterpartyName": transaction.counterparty_name_raw,
        "tradeTime": transaction.trade_time or transaction.txn_date or "",
        "amount": f"{transaction.amount:.2f}",
        "direction": direction,
        "bankName": transaction.imported_bank_name or "",
        "accountNo": transaction.account_no,
        "accountLast4": transaction.imported_bank_last4
        or str(transaction.account_no or "")[-4:],
        "counterpartyAccountNo": transaction.counterparty_account_no or "",
        "counterpartyBankName": transaction.counterparty_bank_name or "",
        "bookedDate": transaction.booked_date or "",
        "summary": transaction.summary or "",
        "remark": transaction.remark or "",
        "currency": transaction.currency or "CNY",
        "bankTextFields": list(transaction.bank_text_fields),
        "relations": context.relation_summaries_for_row(transaction.id),
    }


def _oa_detail(record: Any | None, *, oa_id: str) -> dict[str, Any]:
    if record is None:
        return {"oaId": oa_id, "detailAvailable": False}
    return {
        "oaId": record.id,
        "detailAvailable": True,
        "applicantName": record.applicant,
        "applicationType": record.apply_type,
        "projectName": record.project_name_display or record.project_name,
        "workflowNo": record.case_id or "",
        "status": record.section,
        "amount": _money(record.amount),
        "month": record.month,
        "reason": record.reason,
        "counterpartyName": record.counterparty_name,
        "detailFields": dict(record.detail_fields),
        "openUrl": str(
            record.detail_fields.get("url")
            or record.detail_fields.get("open_url")
            or ""
        ),
    }


def _input_statistics_from_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
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
    linked_oa = sum(
        1 for row in rows if int((row.get("oa") or {}).get("relationCount") or 0)
    )
    linked_bank = sum(
        1
        for row in rows
        if int((row.get("bankTransactions") or {}).get("relationCount") or 0)
    )
    paid = sum(
        1
        for row in rows
        if str((row.get("paymentStatus") or {}).get("code") or "") == "paid"
    )
    return {
        "invoiceCount": invoice_count,
        "linkedOaInvoiceCount": linked_oa,
        "linkedBankInvoiceCount": linked_bank,
        "paidInvoiceCount": paid,
        "unlinkedOaInvoiceCount": max(0, invoice_count - linked_oa),
        "unlinkedBankInvoiceCount": max(0, invoice_count - linked_bank),
        "unpaidInvoiceCount": max(0, invoice_count - paid),
        "formalRelationGroupCount": sum(
            1
            for row in rows
            if int((row.get("oa") or {}).get("relationCount") or 0)
            or int((row.get("bankTransactions") or {}).get("relationCount") or 0)
        ),
        "oaReverseBatchCount": 0,
    }

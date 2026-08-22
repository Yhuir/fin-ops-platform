from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import (
    ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
    attachment_invoice_cache_parser_version,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)


class PostgresOAAttachmentInvoiceRepository:
    def __init__(self, connection: Any, *, identity_locks_held: bool = False) -> None:
        self._connection = connection
        self._identity_locks_held = identity_locks_held

    def find_invoices_by_identity_keys(self, *, canonical_keys: set[str]) -> list[Any]:
        return PostgresCoreRepository(self._connection).find_invoices_by_identity_keys(
            canonical_keys=canonical_keys,
        )

    def save_invoices(self, invoices: list[Any]) -> None:
        repository = PostgresCoreRepository(self._connection)
        if self._identity_locks_held:
            # ConfirmedInvoiceImportUnitOfWork already locked these identities,
            # saved the formal rows, then reloaded them for the promotion decision.
            repository.save_invoices(invoices)
            return
        transaction_factory = getattr(self._connection, "transaction", None)
        if callable(transaction_factory):
            with transaction_factory() as transaction:
                repository.save_oa_attachment_invoices_in_transaction(
                    transaction,
                    invoices,
                )
            return
        repository.save_oa_attachment_invoices_in_transaction(
            self._connection,
            invoices,
        )

    def resolve_active_oa_source_aliases(self, oa_row_ids: set[str]) -> dict[str, str]:
        normalized_row_ids = sorted(
            {str(row_id).strip() for row_id in oa_row_ids if str(row_id).strip()}
        )
        if not normalized_row_ids:
            return {}
        rows = self._connection.fetch_all(
            """
            select alias_row_id, canonical_row_id
            from app.oa_source_aliases
            where status = 'active'
              and (
                  alias_row_id = any(%s::text[])
                  or canonical_row_id = any(%s::text[])
              )
            order by alias_row_id
            """,
            (normalized_row_ids, normalized_row_ids),
        )
        resolved = {row_id: row_id for row_id in normalized_row_ids}
        for row in rows or []:
            alias_row_id = str(row.get("alias_row_id") or "").strip()
            canonical_row_id = str(row.get("canonical_row_id") or "").strip()
            if not alias_row_id or not canonical_row_id:
                continue
            resolved[alias_row_id] = canonical_row_id
            resolved[canonical_row_id] = canonical_row_id
        return resolved

    def save_invoices_and_mark_matching_dirty(
        self,
        invoices: list[Any],
        *,
        scope_months: list[str],
        reason: str,
        debounce_seconds: int,
    ) -> list[str]:
        with self._connection.transaction() as transaction:
            PostgresCoreRepository(transaction).save_oa_attachment_invoices_in_transaction(
                transaction,
                invoices,
            )
            return PostgresWorkbenchMatchingQueueRepository.mark_workbench_matching_dirty_scopes_in_transaction(
                transaction=transaction,
                tenant_id="default",
                scope_months=scope_months,
                reason=reason,
                source_versions={},
                debounce_seconds=debounce_seconds,
            )

    def list_promotion_source_rows(
        self,
        *,
        oa_row_ids: list[str] | None = None,
        canonical_keys: set[str] | None = None,
        parser_version: str | None = None,
        cache_schema_version: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_row_ids = sorted(
            {str(row_id).strip() for row_id in oa_row_ids or [] if str(row_id).strip()}
        )
        normalized_keys = sorted(
            {str(key).strip() for key in canonical_keys or set() if str(key).strip()}
        )
        key_filter_sql = """coalesce(
            nullif(btrim(invoice.value->>'digital_invoice_no'), ''),
            case
                when btrim(invoice.value->>'invoice_no') ~ '^\\d{20}$'
                    then btrim(invoice.value->>'invoice_no')
                when nullif(btrim(invoice.value->>'invoice_code'), '') is not null
                 and nullif(btrim(invoice.value->>'invoice_no'), '') is not null
                    then btrim(invoice.value->>'invoice_code') || ':' || btrim(invoice.value->>'invoice_no')
                else null
            end
        ) = any(%s::text[])""" if normalized_keys else "true"
        oa_filter_sql = "and app.row_id = any(%s::text[])" if normalized_row_ids else ""
        sql = f"""
            with matched_invoices as (
                select cache.source_attachment_key as cache_source_attachment_key,
                       cache.parsed_at,
                       invoice.value as invoice_payload,
                       invoice.ordinality
                from app.oa_attachment_invoice_cache cache
                cross join lateral jsonb_array_elements(
                    case when jsonb_typeof(cache.invoices) = 'array'
                         then cache.invoices else '[]'::jsonb end
                ) with ordinality invoice(value, ordinality)
                where cache.parser_version = %s
                  and cache.cache_schema_version = %s
                  and {key_filter_sql}
            ),
            proven_contexts as (
                select distinct
                       matched.cache_source_attachment_key,
                       matched.ordinality,
                       attachment.oa_application_id::text as oa_application_id,
                       coalesce(app.oa_source_id, attachment.oa_source_id) as oa_source_id,
                       app.row_id as oa_row_id,
                       source.source_expense_item_id,
                       source.source_expense_row_index,
                       source.source_attachment_key,
                       source.source_attachment_name,
                       to_char(app.scope_month, 'YYYY-MM') as month
                from matched_invoices matched
                join app.oa_attachment_invoice_cache_sources source
                  on source.cache_source_attachment_key = matched.cache_source_attachment_key
                join app.oa_attachments attachment
                  on attachment.source_attachment_key = source.source_attachment_key
                join app.oa_applications app
                  on app.id = attachment.oa_application_id
                where source.source_kind <> 'cache_key'
                  and nullif(btrim(source.source_expense_item_id), '') is not null
                  and nullif(btrim(source.source_attachment_key), '') is not null
                  and (
                       nullif(btrim(matched.invoice_payload->>'source_attachment_key'), '')
                           = source.source_attachment_key
                       or (
                            nullif(btrim(matched.invoice_payload->>'source_expense_item_id'), '')
                                = source.source_expense_item_id
                        and nullif(btrim(coalesce(
                                matched.invoice_payload->>'source_attachment_name',
                                matched.invoice_payload->>'attachment_name',
                                matched.invoice_payload->>'fileName',
                                matched.invoice_payload->>'filename'
                            )), '') = source.source_attachment_name
                       )
                  )
                  {oa_filter_sql}
            )
            select matched.cache_source_attachment_key,
                   jsonb_build_array(matched.invoice_payload) as invoices,
                   array[(matched.ordinality - 1)::integer] as invoice_indexes,
                   context.oa_application_id,
                   context.oa_source_id,
                   context.oa_row_id,
                   context.source_expense_item_id,
                   context.source_expense_row_index,
                   context.source_attachment_key,
                   context.source_attachment_name,
                   context.month
            from matched_invoices matched
            join proven_contexts context
              on context.cache_source_attachment_key = matched.cache_source_attachment_key
             and context.ordinality = matched.ordinality
            order by matched.parsed_at, matched.cache_source_attachment_key,
                     context.oa_row_id, context.source_expense_row_index,
                     context.source_attachment_key, matched.ordinality
        """
        params: list[Any] = [
            str(parser_version or attachment_invoice_cache_parser_version()),
            str(cache_schema_version or ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION),
        ]
        if normalized_keys:
            params.append(normalized_keys)
        if normalized_row_ids:
            params.append(normalized_row_ids)
        return list(self._connection.fetch_all(sql, tuple(params)) or [])

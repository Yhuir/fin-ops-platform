from __future__ import annotations

from typing import Any

from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)


class PostgresOAAttachmentInvoiceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def find_invoices_by_identity_keys(self, *, canonical_keys: set[str]) -> list[Any]:
        return PostgresCoreRepository(self._connection).find_invoices_by_identity_keys(
            canonical_keys=canonical_keys,
        )

    def save_invoices(self, invoices: list[Any]) -> None:
        PostgresCoreRepository(self._connection).save_invoices(invoices)

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
            PostgresCoreRepository(transaction).save_invoices(invoices)
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
    ) -> list[dict[str, Any]]:
        normalized_row_ids = sorted(
            {str(row_id).strip() for row_id in oa_row_ids or [] if str(row_id).strip()}
        )
        where_sql = "where context.oa_row_id = any(%s::text[])" if normalized_row_ids else ""
        sql = f"""
            select cache.source_attachment_key as cache_source_attachment_key,
                   cache.invoices,
                   context.oa_application_id,
                   context.oa_source_id,
                   context.oa_row_id,
                   context.source_expense_item_id,
                   context.source_expense_row_index,
                   context.source_attachment_key,
                   context.source_attachment_name,
                   context.month
            from app.oa_attachment_invoice_cache cache
            left join lateral (
                select distinct on (
                           source.source_attachment_key,
                           coalesce(source.source_expense_item_id, ''),
                           coalesce(source.source_expense_row_index, '')
                       )
                       attachment.oa_application_id::text as oa_application_id,
                       coalesce(app.oa_source_id, attachment.oa_source_id) as oa_source_id,
                       app.row_id as oa_row_id,
                       source.source_expense_item_id,
                       source.source_expense_row_index,
                       source.source_attachment_key,
                       source.source_attachment_name,
                       to_char(app.scope_month, 'YYYY-MM') as month
                from app.oa_attachment_invoice_cache_sources source
                left join app.oa_attachments attachment
                  on attachment.source_attachment_key = source.source_attachment_key
                left join app.oa_applications app
                  on app.id = attachment.oa_application_id
                where source.cache_source_attachment_key = cache.source_attachment_key
                  and source.source_kind <> 'cache_key'
                order by
                  source.source_attachment_key,
                  coalesce(source.source_expense_item_id, ''),
                  coalesce(source.source_expense_row_index, ''),
                  case when attachment.oa_application_id is not null then 0 else 1 end,
                  source.source_kind
            ) context on true
            {where_sql}
            order by cache.parsed_at, cache.source_attachment_key,
                     context.oa_row_id, context.source_expense_row_index,
                     context.source_attachment_key
        """
        if normalized_row_ids:
            return list(self._connection.fetch_all(sql, (normalized_row_ids,)) or [])
        return list(self._connection.fetch_all(sql) or [])

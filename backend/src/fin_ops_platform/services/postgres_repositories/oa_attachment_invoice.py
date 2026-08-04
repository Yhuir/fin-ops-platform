from __future__ import annotations

from typing import Any


class PostgresOAAttachmentInvoiceRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

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
                   context.source_attachment_name
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
                       source.source_attachment_name
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

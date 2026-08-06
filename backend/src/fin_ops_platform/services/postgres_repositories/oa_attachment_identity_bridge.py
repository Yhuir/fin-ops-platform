from __future__ import annotations

from typing import Any


def reconcile_oa_attachment_cache_identity_sources(
    connection: Any,
    *,
    cache_source_attachment_keys: list[str] | None = None,
    oa_row_ids: list[str] | None = None,
) -> int:
    """Bridge parser cache identities after either side of the OA write arrives."""

    normalized_cache_keys = sorted(
        {str(value).strip() for value in cache_source_attachment_keys or [] if str(value).strip()}
    )
    normalized_oa_row_ids = sorted(
        {str(value).strip() for value in oa_row_ids or [] if str(value).strip()}
    )
    if not normalized_cache_keys and not normalized_oa_row_ids:
        return 0
    return int(
        connection.execute(
            """
            with attachment_sources as (
                select distinct
                    attachment.source_attachment_key,
                    nullif(attachment.normalized_payload->>'source_expense_item_id', '') as source_expense_item_id,
                    nullif(attachment.normalized_payload->>'source_expense_row_index', '') as source_expense_row_index,
                    nullif(
                        coalesce(
                            attachment.normalized_payload->>'source_attachment_name',
                            attachment.normalized_payload->>'attachment_name',
                            attachment.normalized_payload->>'fileName',
                            attachment.normalized_payload->>'filename'
                        ),
                        ''
                    ) as source_attachment_name
                from app.oa_attachments attachment
                join app.oa_applications app on app.id = attachment.oa_application_id
                where nullif(attachment.source_attachment_key, '') is not null
                  and nullif(attachment.normalized_payload->>'source_expense_item_id', '') is not null
                  and nullif(
                        coalesce(
                            attachment.normalized_payload->>'source_attachment_name',
                            attachment.normalized_payload->>'attachment_name',
                            attachment.normalized_payload->>'fileName',
                            attachment.normalized_payload->>'filename'
                        ),
                        ''
                      ) is not null
                  and (not %s or app.row_id = any(%s::text[]))
            ),
            cache_evidence_sources as (
                select
                    source.cache_source_attachment_key,
                    source.source_attachment_key as parsed_source_attachment_key,
                    source.source_expense_item_id,
                    source.source_expense_row_index,
                    source.source_attachment_name,
                    cache.parsed_at,
                    ('attachment_identity_' || source.source_kind)::text as source_kind
                from app.oa_attachment_invoice_cache_sources source
                join app.oa_attachment_invoice_cache cache
                  on cache.source_attachment_key = source.cache_source_attachment_key
                where source.source_kind in ('invoice', 'evidence', 'artifact')
                  and nullif(source.source_expense_item_id, '') is not null
                  and nullif(source.source_attachment_name, '') is not null
                  and (not %s or source.cache_source_attachment_key = any(%s::text[]))
            ),
            identity_matches as (
                select distinct on (
                    cache.cache_source_attachment_key,
                    attachment.source_attachment_key,
                    cache.source_kind
                )
                    cache.cache_source_attachment_key,
                    attachment.source_attachment_key,
                    cache.source_kind,
                    attachment.source_expense_item_id,
                    coalesce(
                        attachment.source_expense_row_index,
                        cache.source_expense_row_index
                    ) as source_expense_row_index,
                    attachment.source_attachment_name,
                    cache.parsed_at
                from attachment_sources attachment
                join cache_evidence_sources cache
                  on cache.source_expense_item_id = attachment.source_expense_item_id
                 and cache.source_attachment_name = attachment.source_attachment_name
                where attachment.source_attachment_key <> coalesce(cache.parsed_source_attachment_key, '')
                order by
                    cache.cache_source_attachment_key,
                    attachment.source_attachment_key,
                    cache.source_kind,
                    cache.parsed_at desc nulls last
            )
            insert into app.oa_attachment_invoice_cache_sources as existing (
                cache_source_attachment_key,
                source_attachment_key,
                source_kind,
                source_expense_item_id,
                source_expense_row_index,
                source_attachment_name,
                updated_at
            )
            select
                cache_source_attachment_key,
                source_attachment_key,
                source_kind,
                source_expense_item_id,
                source_expense_row_index,
                source_attachment_name,
                now()
            from identity_matches
            on conflict (cache_source_attachment_key, source_attachment_key, source_kind) do update set
                source_expense_item_id = excluded.source_expense_item_id,
                source_expense_row_index = excluded.source_expense_row_index,
                source_attachment_name = excluded.source_attachment_name,
                updated_at = now()
            where (
                existing.source_expense_item_id,
                existing.source_expense_row_index,
                existing.source_attachment_name
            ) is distinct from (
                excluded.source_expense_item_id,
                excluded.source_expense_row_index,
                excluded.source_attachment_name
            )
            """,
            (
                bool(normalized_oa_row_ids),
                normalized_oa_row_ids,
                bool(normalized_cache_keys),
                normalized_cache_keys,
            ),
        )
        or 0
    )

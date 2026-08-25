from __future__ import annotations

from typing import Any


def reconcile_oa_attachment_cache_identity_sources(
    connection: Any,
    *,
    cache_source_attachment_keys: list[str] | None = None,
    oa_row_ids: list[str] | None = None,
) -> int:
    """Bridge only cache identities with one proven current OA attachment owner."""

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
            with requested_scope as (
                select
                    %s::boolean as restrict_oa_rows,
                    %s::text[] as oa_row_ids,
                    %s::boolean as restrict_cache_keys,
                    %s::text[] as cache_source_attachment_keys
            ),
            target_attachment_sources as (
                select distinct
                    attachment.source_attachment_key,
                    item.row_id as source_expense_item_id,
                    coalesce(
                        nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                        ),
                        nullif(attachment.filename, '')
                    ) as source_attachment_name
                from app.oa_attachments attachment
                join app.oa_applications app
                  on app.id = attachment.oa_application_id
                join app.oa_application_items item
                  on item.oa_application_id = attachment.oa_application_id
                 and item.row_id = nullif(
                        attachment.normalized_payload->>'source_expense_item_id',
                        ''
                     )
                cross join requested_scope scope
                where scope.restrict_oa_rows
                  and app.row_id = any(scope.oa_row_ids)
                  and app.status <> 'deleted'
                  and nullif(attachment.source_attachment_key, '') is not null
                  and nullif(
                        attachment.normalized_payload->>'source_expense_item_id',
                        ''
                      ) is not null
                  and coalesce(
                        nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                        ),
                        nullif(attachment.filename, '')
                      ) is not null
            ),
            oa_affected_cache_keys as (
                select distinct source.cache_source_attachment_key
                from app.oa_attachment_invoice_cache_sources source
                join target_attachment_sources target
                  on source.source_attachment_key = target.source_attachment_key
                  or (
                       source.source_expense_item_id = target.source_expense_item_id
                   and source.source_attachment_name = target.source_attachment_name
                  )
                where source.source_kind in (
                    'invoice',
                    'evidence',
                    'artifact',
                    'attachment_identity_invoice',
                    'attachment_identity_evidence',
                    'attachment_identity_artifact'
                )
            ),
            affected_cache_keys as (
                select unnest(scope.cache_source_attachment_keys) as cache_source_attachment_key
                from requested_scope scope
                where scope.restrict_cache_keys
                union
                select cache_source_attachment_key
                from oa_affected_cache_keys
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
                join affected_cache_keys affected
                  on affected.cache_source_attachment_key = source.cache_source_attachment_key
                where source.source_kind in ('invoice', 'evidence', 'artifact')
                  and nullif(source.source_expense_item_id, '') is not null
                  and nullif(source.source_attachment_key, '') is not null
                  and nullif(source.source_attachment_name, '') is not null
            ),
            attachment_sources as (
                select distinct
                    attachment.source_attachment_key,
                    attachment.oa_application_id,
                    item.row_id as source_expense_item_id,
                    coalesce(
                        nullif(attachment.normalized_payload->>'source_expense_row_index', ''),
                        nullif(item.normalized_payload->>'row_index', ''),
                        nullif(item.item_no, '')
                    ) as source_expense_row_index,
                    coalesce(
                        nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                        ),
                        nullif(attachment.filename, '')
                    ) as source_attachment_name
                from app.oa_attachments attachment
                join app.oa_applications app on app.id = attachment.oa_application_id
                join app.oa_application_items item
                  on item.oa_application_id = attachment.oa_application_id
                 and item.row_id = nullif(
                        attachment.normalized_payload->>'source_expense_item_id',
                        ''
                     )
                where nullif(attachment.source_attachment_key, '') is not null
                  and app.status <> 'deleted'
                  and nullif(attachment.normalized_payload->>'source_expense_item_id', '') is not null
                  and coalesce(
                        nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                        ),
                        nullif(attachment.filename, '')
                      ) is not null
                  and (
                       attachment.source_attachment_key in (
                           select cache.parsed_source_attachment_key
                           from cache_evidence_sources cache
                       )
                       or exists (
                           select 1
                           from cache_evidence_sources cache
                           where cache.source_expense_item_id = item.row_id
                             and cache.source_attachment_name = coalesce(
                                 nullif(
                                     coalesce(
                                         attachment.normalized_payload->>'source_attachment_name',
                                         attachment.normalized_payload->>'attachment_name',
                                         attachment.normalized_payload->>'fileName',
                                         attachment.normalized_payload->>'filename'
                                     ),
                                     ''
                                 ),
                                 nullif(attachment.filename, '')
                             )
                       )
                  )
            ),
            identity_candidates as (
                select
                    cache.cache_source_attachment_key,
                    cache.parsed_source_attachment_key,
                    cache.source_kind,
                    attachment.source_attachment_key,
                    attachment.oa_application_id,
                    attachment.source_expense_item_id,
                    coalesce(
                        attachment.source_expense_row_index,
                        cache.source_expense_row_index
                    ) as source_expense_row_index,
                    attachment.source_attachment_name,
                    cache.parsed_at
                from attachment_sources attachment
                join cache_evidence_sources cache
                  on cache.parsed_source_attachment_key = attachment.source_attachment_key
                  or (
                       not exists (
                           select 1
                           from attachment_sources exact_attachment
                           where exact_attachment.source_attachment_key =
                                 cache.parsed_source_attachment_key
                       )
                   and cache.source_expense_item_id = attachment.source_expense_item_id
                   and cache.source_attachment_name = attachment.source_attachment_name
                  )
            ),
            unique_identity_owners as (
                select
                    cache_source_attachment_key,
                    parsed_source_attachment_key,
                    source_kind
                from identity_candidates
                group by
                    cache_source_attachment_key,
                    parsed_source_attachment_key,
                    source_kind
                having count(distinct (
                    oa_application_id,
                    source_attachment_key,
                    source_expense_item_id
                )) = 1
            ),
            identity_matches as (
                select distinct on (
                    candidate.cache_source_attachment_key,
                    candidate.source_attachment_key,
                    candidate.source_kind
                )
                    candidate.cache_source_attachment_key,
                    candidate.source_attachment_key,
                    candidate.source_kind,
                    candidate.source_expense_item_id,
                    candidate.source_expense_row_index,
                    candidate.source_attachment_name,
                    candidate.parsed_at
                from identity_candidates candidate
                join unique_identity_owners owner
                  on owner.cache_source_attachment_key = candidate.cache_source_attachment_key
                 and owner.parsed_source_attachment_key = candidate.parsed_source_attachment_key
                 and owner.source_kind = candidate.source_kind
                order by
                    candidate.cache_source_attachment_key,
                    candidate.source_attachment_key,
                    candidate.source_kind,
                    candidate.parsed_at desc nulls last
            ),
            discarded_invalid_identity_sources as (
                delete from app.oa_attachment_invoice_cache_sources existing
                using affected_cache_keys affected
                where existing.source_kind like 'attachment_identity_%%'
                  and existing.cache_source_attachment_key = affected.cache_source_attachment_key
                  and not exists (
                      select 1
                      from identity_matches desired
                      where desired.cache_source_attachment_key = existing.cache_source_attachment_key
                        and desired.source_attachment_key = existing.source_attachment_key
                        and desired.source_kind = existing.source_kind
                  )
                returning 1
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

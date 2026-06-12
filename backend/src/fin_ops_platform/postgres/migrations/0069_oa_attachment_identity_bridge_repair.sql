create index if not exists oa_attachments_source_identity_idx
    on app.oa_attachments (
        (nullif(normalized_payload->>'source_expense_item_id', '')),
        (nullif(
            coalesce(
                normalized_payload->>'source_attachment_name',
                normalized_payload->>'attachment_name',
                normalized_payload->>'fileName',
                normalized_payload->>'filename'
            ),
            ''
        )),
        source_attachment_key
    )
    where nullif(source_attachment_key, '') is not null
      and nullif(normalized_payload->>'source_expense_item_id', '') is not null
      and nullif(
            coalesce(
                normalized_payload->>'source_attachment_name',
                normalized_payload->>'attachment_name',
                normalized_payload->>'fileName',
                normalized_payload->>'filename'
            ),
            ''
          ) is not null;

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
),
cache_evidence_sources as (
    select
        cache.source_attachment_key as cache_source_attachment_key,
        nullif(evidence.value->>'source_attachment_key', '') as parsed_source_attachment_key,
        nullif(evidence.value->>'source_expense_item_id', '') as source_expense_item_id,
        nullif(evidence.value->>'source_expense_row_index', '') as source_expense_row_index,
        nullif(
            coalesce(
                evidence.value->>'source_attachment_name',
                evidence.value->>'attachment_name',
                evidence.value->>'fileName',
                evidence.value->>'filename'
            ),
            ''
        ) as source_attachment_name,
        cache.parsed_at,
        evidence.source_kind
    from app.oa_attachment_invoice_cache cache
    cross join lateral (
        select invoice.value, 'attachment_identity_invoice'::text as source_kind
        from jsonb_array_elements(coalesce(cache.invoices, '[]'::jsonb)) as invoice(value)
        union all
        select evidence.value, 'attachment_identity_evidence'::text as source_kind
        from jsonb_array_elements(coalesce(cache.evidences, '[]'::jsonb)) as evidence(value)
        union all
        select artifact.value, 'attachment_identity_artifact'::text as source_kind
        from jsonb_array_elements(
            coalesce(
                case
                    when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                    when jsonb_typeof(cache.artifacts) = 'object' then jsonb_build_array(cache.artifacts)
                    else '[]'::jsonb
                end,
                '[]'::jsonb
            )
        ) as artifact(value)
    ) evidence
    where nullif(evidence.value->>'source_expense_item_id', '') is not null
      and nullif(
            coalesce(
                evidence.value->>'source_attachment_name',
                evidence.value->>'attachment_name',
                evidence.value->>'fileName',
                evidence.value->>'filename'
            ),
            ''
          ) is not null
),
identity_matches as (
    select distinct on (cache.cache_source_attachment_key, attachment.source_attachment_key, cache.source_kind)
        cache.cache_source_attachment_key,
        attachment.source_attachment_key,
        cache.source_kind,
        attachment.source_expense_item_id,
        coalesce(attachment.source_expense_row_index, cache.source_expense_row_index) as source_expense_row_index,
        attachment.source_attachment_name,
        cache.parsed_at
    from attachment_sources attachment
    join cache_evidence_sources cache
      on cache.source_expense_item_id = attachment.source_expense_item_id
     and cache.source_attachment_name = attachment.source_attachment_name
    where cache.cache_source_attachment_key is not null
      and attachment.source_attachment_key <> coalesce(cache.parsed_source_attachment_key, '')
    order by
        cache.cache_source_attachment_key,
        attachment.source_attachment_key,
        cache.source_kind,
        cache.parsed_at desc nulls last
)
insert into app.oa_attachment_invoice_cache_sources (
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
    updated_at = now();

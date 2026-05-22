create table if not exists app.oa_attachment_invoice_cache_sources (
    cache_source_attachment_key text not null references app.oa_attachment_invoice_cache(source_attachment_key) on delete cascade,
    source_attachment_key text not null,
    source_kind text not null,
    source_expense_item_id text,
    source_expense_row_index text,
    source_attachment_name text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (cache_source_attachment_key, source_attachment_key, source_kind)
);

create index if not exists oa_attachment_invoice_cache_sources_source_idx
    on app.oa_attachment_invoice_cache_sources (source_attachment_key, cache_source_attachment_key);

create index if not exists oa_attachment_invoice_cache_sources_cache_idx
    on app.oa_attachment_invoice_cache_sources (cache_source_attachment_key);

with normalized_sources as (
    select
        cache.source_attachment_key as cache_source_attachment_key,
        cache.source_attachment_key as source_attachment_key,
        'cache_key'::text as source_kind,
        nullif(cache.normalized_payload->>'source_expense_item_id', '') as source_expense_item_id,
        nullif(cache.normalized_payload->>'source_expense_row_index', '') as source_expense_row_index,
        nullif(
            coalesce(
                cache.normalized_payload->>'source_attachment_name',
                cache.normalized_payload->>'attachment_name',
                cache.normalized_payload->>'filename'
            ),
            ''
        ) as source_attachment_name
    from app.oa_attachment_invoice_cache cache
    where nullif(cache.source_attachment_key, '') is not null
    union all
    select
        cache.source_attachment_key as cache_source_attachment_key,
        nullif(invoice.value->>'source_attachment_key', '') as source_attachment_key,
        'invoice'::text as source_kind,
        nullif(invoice.value->>'source_expense_item_id', '') as source_expense_item_id,
        nullif(invoice.value->>'source_expense_row_index', '') as source_expense_row_index,
        nullif(
            coalesce(
                invoice.value->>'source_attachment_name',
                invoice.value->>'attachment_name',
                invoice.value->>'filename'
            ),
            ''
        ) as source_attachment_name
    from app.oa_attachment_invoice_cache cache
    cross join lateral jsonb_array_elements(coalesce(cache.invoices, '[]'::jsonb)) as invoice(value)
    union all
    select
        cache.source_attachment_key as cache_source_attachment_key,
        nullif(evidence.value->>'source_attachment_key', '') as source_attachment_key,
        'evidence'::text as source_kind,
        nullif(evidence.value->>'source_expense_item_id', '') as source_expense_item_id,
        nullif(evidence.value->>'source_expense_row_index', '') as source_expense_row_index,
        nullif(
            coalesce(
                evidence.value->>'source_attachment_name',
                evidence.value->>'attachment_name',
                evidence.value->>'filename'
            ),
            ''
        ) as source_attachment_name
    from app.oa_attachment_invoice_cache cache
    cross join lateral jsonb_array_elements(coalesce(cache.evidences, '[]'::jsonb)) as evidence(value)
    union all
    select
        cache.source_attachment_key as cache_source_attachment_key,
        nullif(artifact.value->>'source_attachment_key', '') as source_attachment_key,
        'artifact'::text as source_kind,
        nullif(artifact.value->>'source_expense_item_id', '') as source_expense_item_id,
        nullif(artifact.value->>'source_expense_row_index', '') as source_expense_row_index,
        nullif(
            coalesce(
                artifact.value->>'source_attachment_name',
                artifact.value->>'attachment_name',
                artifact.value->>'filename'
            ),
            ''
        ) as source_attachment_name
    from app.oa_attachment_invoice_cache cache
    cross join lateral jsonb_array_elements(
        coalesce(
            case
                when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                else '[]'::jsonb
            end,
            '[]'::jsonb
        )
    ) as artifact(value)
),
deduped_sources as (
    select distinct on (cache_source_attachment_key, source_attachment_key, source_kind)
        cache_source_attachment_key,
        source_attachment_key,
        source_kind,
        source_expense_item_id,
        source_expense_row_index,
        source_attachment_name
    from normalized_sources
    where nullif(source_attachment_key, '') is not null
    order by
        cache_source_attachment_key,
        source_attachment_key,
        source_kind,
        source_expense_item_id nulls last,
        source_expense_row_index nulls last,
        source_attachment_name nulls last
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
from deduped_sources
on conflict (cache_source_attachment_key, source_attachment_key, source_kind) do update set
    source_expense_item_id = excluded.source_expense_item_id,
    source_expense_row_index = excluded.source_expense_row_index,
    source_attachment_name = excluded.source_attachment_name,
    updated_at = now();

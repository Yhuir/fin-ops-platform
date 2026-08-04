-- Restore manual-import provenance only where an OA attachment promotion overwrote it.
with provenance_edges as (
    select
        invoice.id as invoice_id,
        batch.id as batch_uuid,
        coalesce(nullif(rows.legacy_batch_id, ''), nullif(batch.legacy_mongo_id, ''), batch.id::text) as batch_id,
        coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, '')) as source_id,
        rows.created_at,
        rows.decision,
        rows.id as row_id,
        jsonb_strip_nulls(jsonb_build_object(
            'source_type', 'manual_invoice_import',
            'source_id', coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, '')),
            'batch_id', coalesce(nullif(rows.legacy_batch_id, ''), nullif(batch.legacy_mongo_id, ''), batch.id::text),
            'created_at', rows.created_at::text,
            'request_key', nullif(
                rows.raw_payload->'normalized_payload'->'normalized_row'->>'pending_invoice_request_key',
                ''
            ),
            'bank_transaction_id', nullif(
                rows.raw_payload->'normalized_payload'->'normalized_row'->>'pending_invoice_bank_transaction_id',
                ''
            )
        )) as source_link
    from app.invoices invoice
    join app.import_batch_rows rows
      on rows.linked_object_id = coalesce(invoice.legacy_mongo_id, invoice.id::text)
    join app.import_batches batch on batch.id = rows.import_batch_id
    where rows.source_record_type = 'invoice'
      and rows.linked_object_type = 'invoice'
      and rows.decision in ('created', 'status_updated', 'duplicate_skipped')
      and coalesce(nullif(rows.source_unique_key, ''), nullif(rows.data_fingerprint, '')) is not null
      and exists (
          select 1
          from jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb)) link
          where link->>'source_type' = 'oa_attachment_invoice'
      )
), missing_edges as (
    select edge.*
    from provenance_edges edge
    join app.invoices invoice on invoice.id = edge.invoice_id
    where not exists (
        select 1
        from jsonb_array_elements(coalesce(invoice.source_links, '[]'::jsonb)) link
        where link->>'source_type' = 'manual_invoice_import'
          and link->>'source_id' = edge.source_id
          and link->>'batch_id' = edge.batch_id
    )
), additions as (
    select
        invoice_id,
        jsonb_agg(source_link order by created_at, batch_id, source_id, row_id) as source_links
    from missing_edges
    group by invoice_id
), owners as (
    select distinct on (invoice_id)
        invoice_id,
        batch_uuid,
        batch_id
    from provenance_edges
    order by
        invoice_id,
        case decision when 'created' then 0 when 'status_updated' then 1 else 2 end,
        created_at,
        row_id
), plans as (
    select
        invoice.id as invoice_id,
        coalesce(invoice.legacy_mongo_id, invoice.id::text) as legacy_id,
        owner.batch_uuid,
        owner.batch_id,
        case
            when '人工导入' = any(coalesce(invoice.tags, array[]::text[])) then invoice.tags
            else array_append(coalesce(invoice.tags, array[]::text[]), '人工导入')
        end as tags,
        coalesce(invoice.source_links, '[]'::jsonb) || additions.source_links as source_links
    from additions
    join app.invoices invoice on invoice.id = additions.invoice_id
    join owners owner on owner.invoice_id = invoice.id
), updated as (
    update app.invoices invoice
    set
        source_batch_id = coalesce(invoice.source_batch_id, plan.batch_uuid),
        legacy_source_batch_id = coalesce(invoice.legacy_source_batch_id, plan.batch_id),
        tags = plan.tags,
        source_links = plan.source_links,
        raw_payload = jsonb_set(
            jsonb_set(
                jsonb_set(
                    jsonb_set(
                        coalesce(invoice.raw_payload, '{}'::jsonb)
                            || jsonb_build_object(
                                'normalized_payload',
                                coalesce(invoice.raw_payload->'normalized_payload', '{}'::jsonb)
                            ),
                        '{normalized_payload,id}',
                        to_jsonb(plan.legacy_id),
                        true
                    ),
                    '{normalized_payload,source_batch_id}',
                    to_jsonb(coalesce(invoice.legacy_source_batch_id, plan.batch_id)),
                    true
                ),
                '{normalized_payload,tags}',
                to_jsonb(plan.tags),
                true
            ),
            '{normalized_payload,source_links}',
            plan.source_links,
            true
        ),
        updated_at = now()
    from plans plan
    where invoice.id = plan.invoice_id
    returning invoice.id
)
insert into audit.events(
    event_type,
    object_type,
    object_id,
    actor_id,
    scope,
    payload,
    raw_payload
)
select
    'invoice.manual_import_provenance_restored',
    'invoice_provenance',
    'oa_attachment_overlap',
    'migration:0134',
    'canonical_invoices',
    jsonb_build_object('updated_invoice_count', count(*)),
    jsonb_build_object(
        'normalized_payload',
        jsonb_build_object('migration', '0134_restore_invoice_import_provenance')
    )
from updated
having count(*) > 0;

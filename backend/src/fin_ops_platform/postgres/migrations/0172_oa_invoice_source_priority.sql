-- Current ownership has one authority. Import batches/rows retain import history.
-- Preserve canonical IDs, amounts, lifecycle, ETC references and source batch IDs.
with plans as (
    select invoice.id, coalesce(invoice.legacy_mongo_id, invoice.id::text) as invoice_id,
           invoice.invoice_month, invoice.source_links as before_links,
           coalesce((select jsonb_agg(link order by ordinal)
               from jsonb_array_elements(invoice.source_links) with ordinality as source(link, ordinal)
               where link->>'source_type' not in ('manual_invoice_import', 'oa_expense_item_invoice')
                  or link->>'source_type' is null), '[]'::jsonb) as source_links,
           array(select tag from unnest(invoice.tags) tag
                 where tag not in ('人工导入', '明细归属')) as tags
    from app.invoices invoice
    where invoice.status <> 'deleted'
      and invoice.source_links @> '[{"source_type":"oa_attachment_invoice"}]'::jsonb
      and (invoice.source_links @> '[{"source_type":"manual_invoice_import"}]'::jsonb
        or invoice.source_links @> '[{"source_type":"oa_expense_item_invoice"}]'::jsonb
        or invoice.tags && array['人工导入', '明细归属'])
), updated as (
    update app.invoices invoice
    set source_links = plan.source_links, tags = plan.tags,
        raw_payload = jsonb_set(coalesce(invoice.raw_payload, '{}'::jsonb), '{normalized_payload}',
            coalesce(invoice.raw_payload->'normalized_payload', '{}'::jsonb)
              || jsonb_build_object('source_links', plan.source_links, 'tags', to_jsonb(plan.tags)), true),
        updated_at = now()
    from plans plan where invoice.id = plan.id
    returning invoice.id, plan.invoice_id, plan.invoice_month, plan.before_links,
              plan.source_links
), audited as (
    insert into audit.events(event_type, object_type, object_id, actor_id, scope, payload, raw_payload)
    select 'invoice.oa_source_priority_applied', 'invoice', invoice_id,
           'migration:0172', 'canonical_invoices',
           jsonb_build_object('before_source_links', before_links, 'source_links', source_links),
           '{"migration":"0172_oa_invoice_source_priority"}'::jsonb
    from updated returning object_id
), source_months as (
    select invoice_month as month from updated
    union
    select oa.scope_month from updated u
    cross join lateral jsonb_array_elements(u.source_links) link
    left join app.oa_source_aliases alias
      on alias.alias_row_id = link->>'derived_from_oa_id' and alias.status = 'active'
    join app.oa_applications oa
      on oa.row_id = coalesce(alias.canonical_row_id, link->>'derived_from_oa_id')
    union
    select relation.month_scope
    from app.workbench_pair_relations relation
    join updated u on u.invoice_id = any(relation.row_ids)
    where relation.status = 'active' and relation.month_scope is not null
), months as (
    select distinct (month + shift * interval '1 month')::date as month
    from source_months cross join generate_series(-2, 2) shift
    where month is not null
)
insert into job.workbench_matching_dirty_scopes(
    tenant_id, scope_month, reason, status, available_at, source_versions, raw_payload)
select 'default', month, 'oa_invoice_source_priority', 'dirty', now(), '{}'::jsonb,
       '{"expedite":true,"migration":"0172"}'::jsonb from months
on conflict (tenant_id, scope_month) do update set
    reason = excluded.reason,
    status = case when job.workbench_matching_dirty_scopes.status = 'processing'
                  then 'processing' else 'dirty' end,
    available_at = case when job.workbench_matching_dirty_scopes.status = 'processing'
                       then job.workbench_matching_dirty_scopes.available_at else now() end,
    raw_payload = job.workbench_matching_dirty_scopes.raw_payload || excluded.raw_payload
       || case when job.workbench_matching_dirty_scopes.status = 'processing'
               then '{"refresh_requested_while_processing":true}'::jsonb else '{}'::jsonb end,
    lease_owner = case when job.workbench_matching_dirty_scopes.status = 'processing'
                       then job.workbench_matching_dirty_scopes.lease_owner else null end,
    lease_expires_at = case when job.workbench_matching_dirty_scopes.status = 'processing'
                            then job.workbench_matching_dirty_scopes.lease_expires_at else null end,
    updated_at = now();

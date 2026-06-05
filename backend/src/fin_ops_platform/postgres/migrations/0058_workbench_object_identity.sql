alter table read_model.workbench_rows
    add column if not exists object_identity_key text;

alter table read_model.workbench_rows
    add column if not exists object_identity_kind text;

alter table read_model.workbench_rows
    add column if not exists object_identity_source text;

alter table read_model.workbench_rows
    add column if not exists object_identity_confidence text;

alter table read_model.workbench_group_rows
    add column if not exists object_identity_key text;

alter table read_model.workbench_group_rows
    add column if not exists object_identity_kind text;

alter table read_model.workbench_group_rows
    add column if not exists object_identity_source text;

alter table read_model.workbench_group_rows
    add column if not exists object_identity_confidence text;

create index if not exists workbench_rows_generation_scope_identity_idx
    on read_model.workbench_rows (generation_id, scope_key, object_identity_key, status)
    where object_identity_key is not null;

create index if not exists workbench_group_rows_generation_scope_identity_zone_idx
    on read_model.workbench_group_rows (generation_id, scope_key, pane, object_identity_key, zone)
    where object_identity_key is not null
      and coalesce(row_role, '') <> 'summary';

create or replace view read_model.workbench_generation_consistency as
with row_counts as (
    select generation_id, scope_key, count(distinct row_id)::bigint as actual_row_count
    from read_model.workbench_rows
    group by generation_id, scope_key
),
group_counts as (
    select generation_id, scope_key, count(*)::bigint as actual_group_count
    from read_model.workbench_groups
    group by generation_id, scope_key
),
group_row_counts as (
    select
        generation_id,
        scope_key,
        count(distinct row_id) filter (where coalesce(row_role, '') <> 'summary')::bigint as actual_group_row_count
    from read_model.workbench_group_rows
    group by generation_id, scope_key
),
summary_counts as (
    select generation_id, scope_key, count(*)::bigint as actual_summary_count
    from read_model.workbench_summary
    group by generation_id, scope_key
),
duplicate_identity_counts as (
    select
        duplicate_rows.generation_id,
        duplicate_rows.scope_key,
        count(*) filter (where duplicate_rows.object_kind = 'invoice')::bigint as duplicate_invoice_identity_count,
        count(*) filter (where duplicate_rows.object_kind = 'bank')::bigint as duplicate_bank_identity_count,
        jsonb_agg(
            jsonb_build_object(
                'object_kind', duplicate_rows.object_kind,
                'object_identity_key', duplicate_rows.object_identity_key,
                'object_identity_kind', duplicate_rows.object_identity_kind,
                'zones', duplicate_rows.zones,
                'row_ids', duplicate_rows.row_ids
            )
            order by duplicate_rows.object_kind, duplicate_rows.object_identity_key
        ) as duplicate_identity_samples
    from (
        select
            gr.generation_id,
            gr.scope_key,
            case
                when gr.pane = 'invoice'
                 and gr.object_identity_kind in ('digital_invoice_no', 'invoice_code_no')
                    then 'invoice'
                when gr.pane = 'bank'
                 and gr.object_identity_kind = 'business_fields'
                    then 'bank'
                else null
            end as object_kind,
            gr.object_identity_key,
            gr.object_identity_kind,
            array_agg(distinct gr.zone order by gr.zone) as zones,
            array_agg(distinct gr.row_id order by gr.row_id) as row_ids
        from read_model.workbench_group_rows gr
        where gr.row_role <> 'summary'
          and gr.object_identity_key is not null
          and gr.zone in ('paired', 'open')
        group by gr.generation_id, gr.scope_key, gr.pane, gr.object_identity_key, gr.object_identity_kind
        having bool_or(gr.zone = 'paired') and bool_or(gr.zone = 'open')
    ) duplicate_rows
    where duplicate_rows.object_kind is not null
    group by duplicate_rows.generation_id, duplicate_rows.scope_key
)
select
    gen.tenant_id,
    gen.scope_key,
    gen.generation_id,
    gen.status,
    gen.row_count as metadata_row_count,
    gen.group_count as metadata_group_count,
    gen.summary_count as metadata_summary_count,
    coalesce(row_counts.actual_row_count, 0)::bigint as actual_row_count,
    coalesce(group_counts.actual_group_count, 0)::bigint as actual_group_count,
    coalesce(group_row_counts.actual_group_row_count, 0)::bigint as actual_group_row_count,
    coalesce(summary_counts.actual_summary_count, 0)::bigint as actual_summary_count,
    coalesce(duplicate_identity_counts.duplicate_invoice_identity_count, 0)::bigint
        as duplicate_invoice_identity_count,
    coalesce(duplicate_identity_counts.duplicate_bank_identity_count, 0)::bigint
        as duplicate_bank_identity_count,
    coalesce(duplicate_identity_counts.duplicate_identity_samples, '[]'::jsonb)
        as duplicate_identity_samples,
    case
        when gen.status <> 'active' then 'inactive'
        when coalesce(gen.build_metadata->>'tombstone', 'false') = 'true'
             and gen.row_count = 0
             and gen.group_count = 0
             then 'consistent'
        when gen.group_count <> coalesce(group_counts.actual_group_count, 0) then 'inconsistent'
        when gen.row_count > 0 and coalesce(group_row_counts.actual_group_row_count, 0) = 0 then 'inconsistent'
        when gen.summary_count > 0 and coalesce(summary_counts.actual_summary_count, 0) = 0 then 'inconsistent'
        when coalesce(duplicate_identity_counts.duplicate_invoice_identity_count, 0) > 0 then 'inconsistent'
        when coalesce(duplicate_identity_counts.duplicate_bank_identity_count, 0) > 0 then 'inconsistent'
        else 'consistent'
    end as consistency_status,
    gen.parent_generation_ids,
    gen.build_batch_id,
    gen.build_metadata,
    gen.last_error,
    gen.error_reason,
    gen.activated_at,
    gen.updated_at
from read_model.workbench_generations gen
left join row_counts
  on row_counts.generation_id = gen.generation_id
 and row_counts.scope_key = gen.scope_key
left join group_counts
  on group_counts.generation_id = gen.generation_id
 and group_counts.scope_key = gen.scope_key
left join group_row_counts
  on group_row_counts.generation_id = gen.generation_id
 and group_row_counts.scope_key = gen.scope_key
left join summary_counts
  on summary_counts.generation_id = gen.generation_id
 and summary_counts.scope_key = gen.scope_key
left join duplicate_identity_counts
  on duplicate_identity_counts.generation_id = gen.generation_id
 and duplicate_identity_counts.scope_key = gen.scope_key;

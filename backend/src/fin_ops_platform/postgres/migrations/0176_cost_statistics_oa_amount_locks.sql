set local lock_timeout = '10s';
set local statement_timeout = '1min';

alter table app.cost_statistics_manual_allocations
    add column oa_amount_locks jsonb;

-- Initialize a new constraint, never rewrite amounts or infer historical intent.
with originals as (
    select 'oa:' || row_id as unit_id, normalized_payload->>'amount' as amount
    from app.oa_applications where form_type = '支付申请'
    union all
    select 'oa:' || oa.row_id || ':item:' || coalesce(nullif(item->>'expense_item_id', ''),
        nullif(item->>'row_id', ''), item->>'item_id'),
        coalesce(nullif(item->>'settlement_amount', ''), nullif(item->>'amount', ''), item->>'total_with_tax')
    from app.oa_applications oa
    cross join lateral jsonb_array_elements(coalesce(oa.normalized_payload->'expense_items', '[]'::jsonb)) item
    where oa.form_type = '日常报销'
), initialized as (
    select d.relation_case_id, coalesce(jsonb_object_agg(line->>'unit_id',
        case when o.amount ~ '^[0-9]+(\.[0-9]+)?$'
             then (line->>'amount')::numeric = o.amount::numeric else false end)
        filter (where line->>'unit_id' like 'oa:%'), '{}'::jsonb) as locks
    from app.cost_statistics_manual_allocations d
    left join lateral jsonb_array_elements(d.unit_allocations) line on true
    left join originals o on o.unit_id = line->>'unit_id'
    group by d.relation_case_id
)
update app.cost_statistics_manual_allocations d
set oa_amount_locks = initialized.locks
from initialized where initialized.relation_case_id = d.relation_case_id;

alter table app.cost_statistics_manual_allocations
    alter column oa_amount_locks set not null,
    add check (jsonb_typeof(oa_amount_locks) = 'object');

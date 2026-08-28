set local lock_timeout = '10s';
set local statement_timeout = '1min';

-- Existing decisions used one row for every OA unit x bank source pair.  Before
-- changing the contract, fail closed if any persisted row cannot be reduced to
-- one non-negative amount per OA allocation unit.
do $$
begin
    if exists (
        select 1
        from app.cost_statistics_manual_allocations as decision
        cross join lateral jsonb_array_elements(decision.allocations) as line(value)
        where jsonb_typeof(line.value) <> 'object'
           or not (line.value ? 'unit_id')
           or not (line.value ? 'source_kind')
           or not (line.value ? 'source_id')
           or not (line.value ? 'amount')
           or btrim(line.value->>'unit_id') = ''
           or btrim(line.value->>'source_id') = ''
           or line.value->>'source_kind' not in ('outflow', 'paid_wrong_refund')
           or line.value->>'amount' !~ '^(0|[1-9][0-9]{0,14})\.[0-9]{2}$'
           or exists (
               select 1
               from jsonb_object_keys(line.value) as field(name)
               where field.name not in ('unit_id', 'source_kind', 'source_id', 'amount')
           )
    ) then
        raise exception
            '0162 cannot migrate malformed cost statistics matrix allocations';
    end if;
end
$$;

do $$
begin
    if exists (
        select 1
        from app.cost_statistics_manual_allocations as decision
        cross join lateral (
            select
                count(*) as unit_count,
                min(grouped.unit_amount) as minimum_unit_amount,
                coalesce(sum(grouped.unit_amount), 0::numeric) as allocated_total
            from (
                select
                    line.value->>'unit_id' as unit_id,
                    sum(
                        case line.value->>'source_kind'
                            when 'paid_wrong_refund'
                                then -(line.value->>'amount')::numeric
                            else (line.value->>'amount')::numeric
                        end
                    )::numeric(18, 2) as unit_amount
                from jsonb_array_elements(decision.allocations) as line(value)
                group by line.value->>'unit_id'
            ) as grouped
        ) as reduced
        where reduced.unit_count = 0
           or reduced.minimum_unit_amount < 0
           or reduced.allocated_total <> decision.net_cash_cost
    ) then
        raise exception
            '0162 cannot migrate cost statistics decisions that do not close net cash cost';
    end if;
end
$$;

update app.cost_statistics_manual_allocations as decision
set allocations = (
    select jsonb_agg(
        jsonb_build_object(
            'unit_id', grouped.unit_id,
            'amount', to_char(grouped.unit_amount, 'FM999999999999990.00')
        )
        order by grouped.unit_id
    ) as unit_allocations
    from (
        select
            line.value->>'unit_id' as unit_id,
            sum(
                case line.value->>'source_kind'
                    when 'paid_wrong_refund'
                        then -(line.value->>'amount')::numeric
                    else (line.value->>'amount')::numeric
                end
            )::numeric(18, 2) as unit_amount
        from jsonb_array_elements(decision.allocations) as line(value)
        group by line.value->>'unit_id'
    ) as grouped
);

alter table app.cost_statistics_manual_allocations
    rename column oa_allocation_total to oa_total;
alter table app.cost_statistics_manual_allocations
    rename column bank_outflow_total to gross_outflow_total;
alter table app.cost_statistics_manual_allocations
    rename column paid_wrong_refund_total to wrong_payment_refund_total;
alter table app.cost_statistics_manual_allocations
    rename column net_cash_cost to net_outflow_total;
alter table app.cost_statistics_manual_allocations
    rename column allocations to unit_allocations;

alter table app.cost_statistics_manual_allocations
    add column non_cost_amount numeric(18, 2) not null default 0.00,
    add column non_cost_reason text not null default '';

alter table app.cost_statistics_manual_allocations
    add constraint cost_statistics_manual_allocations_non_cost_amount_check
        check (
            non_cost_amount >= 0
            and non_cost_amount <= net_outflow_total
        ),
    add constraint cost_statistics_manual_allocations_non_cost_reason_check
        check (
            (non_cost_amount = 0 and btrim(non_cost_reason) = '')
            or (non_cost_amount > 0 and btrim(non_cost_reason) <> '')
        );

comment on column app.cost_statistics_manual_allocations.unit_allocations is
    'One exact non-negative cost amount per OA allocation unit; no bank-source ownership is inferred.';
comment on column app.cost_statistics_manual_allocations.non_cost_amount is
    'Optional part of net outflow explicitly excluded from cost; unit allocations plus this amount close net outflow.';
comment on column app.cost_statistics_manual_allocations.non_cost_reason is
    'Required explanation when non_cost_amount is greater than zero.';

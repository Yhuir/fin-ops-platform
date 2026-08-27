set local lock_timeout = '10s';
set local statement_timeout = '2min';

create table if not exists app.oa_payment_status_writeback_states (
    tenant_id text not null default 'default',
    flow_id text not null,
    oa_row_ids text[] not null,
    app_owned boolean not null default false,
    sync_state text not null check (sync_state in ('stable', 'applying')),
    desired_pay_status integer not null check (desired_pay_status in (0, 1)),
    observed_pay_status integer check (observed_pay_status in (0, 1, 2)),
    last_event_id text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    primary key (tenant_id, flow_id)
);

comment on table app.oa_payment_status_writeback_states is
    'Durable ownership and recovery state for OA payment statuses changed by Workbench relation events.';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on app.oa_payment_status_writeback_states to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select on app.oa_payment_status_writeback_states to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update on app.oa_payment_status_writeback_states to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.oa_payment_status_writeback_states to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update on app.oa_payment_status_writeback_states to fin_ops_migrator;
    end if;
end $$;

with active_relations as (
    select
        relation.case_id,
        relation.version,
        array(
            select member.row_id
            from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
            where member.row_type in ('oa', 'oa_application')
            order by member.row_id
        ) as oa_row_ids
    from app.workbench_pair_relations relation
    where relation.status = 'active'
      and cardinality(relation.row_ids) = cardinality(relation.row_types)
      and exists (
          select 1
          from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
          where member.row_type in ('oa', 'oa_application')
      )
      and exists (
          select 1
          from unnest(relation.row_ids, relation.row_types) member(row_id, row_type)
          join app.bank_transactions bank
            on member.row_id in (bank.id::text, bank.legacy_mongo_id)
           and bank.status <> 'deleted'
           and bank.txn_direction = 'outflow'
          where member.row_type in ('bank', 'bank_transaction')
      )
)
insert into job.outbox_events(
    tenant_id, event_type, aggregate_type, aggregate_id, scope_type, scope_key,
    dedupe_key, payload, schema_version, source_version, priority, raw_payload
)
select
    'default',
    'oa.payment_status.reconcile',
    'workbench_relation',
    active.case_id,
    'oa_payment_status',
    active.case_id,
    'oa.payment_status.reconcile:backfill:' || md5(
        active.case_id || ':' || active.version::text || ':' || array_to_string(active.oa_row_ids, ',')
    ),
    jsonb_build_object(
        'oa_row_ids', to_jsonb(active.oa_row_ids),
        'relation_case_id', active.case_id,
        'relation_status', 'active',
        'relation_version', active.version,
        'reason', 'migration_0158_backfill'
    ),
    1,
    active.version,
    'high',
    jsonb_build_object('migration', '0158_oa_payment_status_auto_reconcile')
from active_relations active
on conflict (tenant_id, dedupe_key)
where dedupe_key is not null and status = 'pending'
do nothing;

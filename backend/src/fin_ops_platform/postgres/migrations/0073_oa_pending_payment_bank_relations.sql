create table if not exists app.oa_pending_payment_bank_relations (
    id uuid primary key default gen_random_uuid(),
    relation_id text not null unique,
    status text not null default 'active',
    version integer not null default 1,
    scope_month date,
    oa_row_ids text[] not null default array[]::text[],
    bank_transaction_ids text[] not null default array[]::text[],
    source_action text,
    note text,
    amount_check jsonb not null default '{}'::jsonb,
    writeback_status jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    migrated_from_workbench_case_id text,
    promoted_workbench_case_id text,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    cancelled_by text,
    cancelled_at timestamptz,
    cancellation_reason text,
    raw_payload jsonb not null default '{}'::jsonb,
    check (status in ('active', 'cancelled', 'promoted', 'promotion_conflict'))
);

create index if not exists oa_pending_payment_bank_relations_status_scope_idx
    on app.oa_pending_payment_bank_relations (status, scope_month);
create index if not exists oa_pending_payment_bank_relations_oa_gin
    on app.oa_pending_payment_bank_relations using gin (oa_row_ids);
create index if not exists oa_pending_payment_bank_relations_bank_gin
    on app.oa_pending_payment_bank_relations using gin (bank_transaction_ids);
create index if not exists oa_pending_payment_bank_relations_migrated_idx
    on app.oa_pending_payment_bank_relations (migrated_from_workbench_case_id)
    where migrated_from_workbench_case_id is not null;
create index if not exists oa_pending_payment_bank_relations_promoted_idx
    on app.oa_pending_payment_bank_relations (promoted_workbench_case_id)
    where promoted_workbench_case_id is not null;

create table if not exists app.bank_transaction_relation_claims (
    id uuid primary key default gen_random_uuid(),
    bank_transaction_id text not null,
    owner_type text not null,
    owner_id text not null,
    status text not null default 'active',
    scope_month date,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    released_by text,
    released_at timestamptz,
    release_reason text,
    raw_payload jsonb not null default '{}'::jsonb,
    check (owner_type in ('oa_pending_payment_relation', 'workbench_relation')),
    check (status in ('active', 'released', 'cancelled', 'promoted'))
);

create unique index if not exists bank_transaction_relation_claims_active_bank_uidx
    on app.bank_transaction_relation_claims (bank_transaction_id)
    where status = 'active';
create index if not exists bank_transaction_relation_claims_owner_idx
    on app.bank_transaction_relation_claims (owner_type, owner_id, status);
create index if not exists bank_transaction_relation_claims_scope_idx
    on app.bank_transaction_relation_claims (status, scope_month);

create table if not exists app.oa_pending_payment_bank_relation_events (
    id uuid primary key default gen_random_uuid(),
    relation_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    before_payload jsonb not null default '{}'::jsonb,
    after_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists oa_pending_payment_bank_relation_events_relation_idx
    on app.oa_pending_payment_bank_relation_events (relation_id, occurred_at desc);

with legacy_relations as (
    select
        relation.case_id,
        relation.month_scope,
        relation.row_ids,
        relation.row_types,
        relation.note,
        relation.amount_check,
        relation.special_metadata,
        relation.source_versions,
        relation.created_by,
        relation.created_at,
        relation.updated_at,
        relation.raw_payload
    from app.workbench_pair_relations relation
    where relation.status = 'active'
      and relation.special_metadata->>'origin' = 'oa_pending_payment_in_progress'
),
typed_rows as (
    select
        legacy.case_id,
        legacy.month_scope,
        legacy.note,
        legacy.amount_check,
        legacy.special_metadata,
        legacy.source_versions,
        legacy.created_by,
        legacy.created_at,
        legacy.updated_at,
        legacy.raw_payload,
        typed.row_id,
        typed.row_type
    from legacy_relations legacy
    cross join lateral (
        select ids.row_id, coalesce(types.row_type, '') as row_type
        from unnest(legacy.row_ids) with ordinality as ids(row_id, ord)
        left join unnest(legacy.row_types) with ordinality as types(row_type, ord)
            on types.ord = ids.ord
    ) typed
),
normalized_relations as (
    select
        case_id,
        month_scope,
        note,
        amount_check,
        special_metadata,
        source_versions,
        created_by,
        min(created_at) as created_at,
        max(updated_at) as updated_at,
        (array_agg(raw_payload order by updated_at desc nulls last, created_at desc nulls last))[1] as raw_payload,
        array_agg(distinct row_id order by row_id)
            filter (where row_type = 'oa' or row_id like 'oa-%' or row_id like 'oa_pay_%') as oa_row_ids,
        array_agg(distinct row_id order by row_id)
            filter (where row_type = 'bank' or row_id like 'txn_%' or row_id like 'bank-%') as bank_transaction_ids
    from typed_rows
    group by case_id, month_scope, note, amount_check, special_metadata, source_versions, created_by
),
inserted_relations as (
    insert into app.oa_pending_payment_bank_relations(
        relation_id, status, scope_month, oa_row_ids, bank_transaction_ids,
        source_action, note, amount_check, source_versions, migrated_from_workbench_case_id,
        created_by, created_at, updated_at, raw_payload
    )
    select
        'oa-pending-' || case_id,
        'active',
        month_scope,
        coalesce(oa_row_ids, array[]::text[]),
        coalesce(bank_transaction_ids, array[]::text[]),
        coalesce(special_metadata->>'source_action', 'legacy_workbench_migration'),
        note,
        coalesce(amount_check, '{}'::jsonb),
        coalesce(source_versions, '{}'::jsonb),
        case_id,
        created_by,
        coalesce(created_at, now()),
        coalesce(updated_at, now()),
        jsonb_build_object(
            'normalized_payload',
            jsonb_build_object(
                'relation_id', 'oa-pending-' || case_id,
                'status', 'active',
                'month_scope', month_scope,
                'oa_row_ids', coalesce(oa_row_ids, array[]::text[]),
                'bank_transaction_ids', coalesce(bank_transaction_ids, array[]::text[]),
                'source_action', coalesce(special_metadata->>'source_action', 'legacy_workbench_migration'),
                'migrated_from_workbench_case_id', case_id
            )
        )
    from normalized_relations
    where coalesce(array_length(bank_transaction_ids, 1), 0) > 0
    on conflict (relation_id) do update set
        status = excluded.status,
        scope_month = excluded.scope_month,
        oa_row_ids = excluded.oa_row_ids,
        bank_transaction_ids = excluded.bank_transaction_ids,
        source_action = excluded.source_action,
        note = excluded.note,
        amount_check = excluded.amount_check,
        source_versions = excluded.source_versions,
        migrated_from_workbench_case_id = excluded.migrated_from_workbench_case_id,
        raw_payload = excluded.raw_payload,
        updated_at = now()
    returning relation_id, scope_month, bank_transaction_ids, created_by
)
insert into app.bank_transaction_relation_claims(
    bank_transaction_id, owner_type, owner_id, status, scope_month, created_by, raw_payload
)
select distinct
    bank_id,
    'oa_pending_payment_relation',
    inserted.relation_id,
    'active',
    inserted.scope_month,
    inserted.created_by,
    jsonb_build_object(
        'normalized_payload',
        jsonb_build_object(
            'bank_transaction_id', bank_id,
            'owner_type', 'oa_pending_payment_relation',
            'owner_id', inserted.relation_id,
            'status', 'active',
            'source', 'workbench_origin_migration'
        )
    )
from inserted_relations inserted
cross join lateral unnest(inserted.bank_transaction_ids) as bank_id
on conflict (bank_transaction_id) where status = 'active' do nothing;

insert into app.oa_pending_payment_bank_relation_events(
    relation_id, event_type, actor_id, before_payload, after_payload, raw_payload
)
select
    'oa-pending-' || relation.case_id,
    'migrate_from_workbench_origin',
    'migration:0073',
    jsonb_build_object(
        'case_id', relation.case_id,
        'status', 'active',
        'row_ids', relation.row_ids,
        'row_types', relation.row_types,
        'special_metadata', relation.special_metadata
    ),
    jsonb_build_object(
        'relation_id', 'oa-pending-' || relation.case_id,
        'status', 'active',
        'migrated_from_workbench_case_id', relation.case_id
    ),
    jsonb_build_object('normalized_payload', jsonb_build_object('source', 'migration:0073'))
from app.workbench_pair_relations relation
where relation.status = 'active'
  and relation.special_metadata->>'origin' = 'oa_pending_payment_in_progress';

insert into app.workbench_pair_relation_history(
    relation_id, case_id, event_type, actor_id, before_payload, after_payload, raw_payload
)
select
    relation.id,
    relation.case_id,
    'oa_pending_payment_in_progress_relation_migrated',
    'migration:0073',
    jsonb_build_object(
        'case_id', relation.case_id,
        'status', 'active',
        'row_ids', relation.row_ids,
        'row_types', relation.row_types,
        'special_metadata', relation.special_metadata
    ),
    jsonb_build_object(
        'case_id', relation.case_id,
        'status', 'cancelled',
        'migrated_to_pending_relation_id', 'oa-pending-' || relation.case_id
    ),
    jsonb_build_object('normalized_payload', jsonb_build_object('source', 'migration:0073'))
from app.workbench_pair_relations relation
where relation.status = 'active'
  and relation.special_metadata->>'origin' = 'oa_pending_payment_in_progress';

update app.workbench_pair_relations relation
set
    status = 'cancelled',
    withdrawn_by = 'migration:0073',
    withdrawn_at = now(),
    special_metadata = coalesce(relation.special_metadata, '{}'::jsonb)
        || jsonb_build_object(
            'migrated_to_pending_relation_id', 'oa-pending-' || relation.case_id,
            'migration', '0073_oa_pending_payment_bank_relations'
        ),
    raw_payload = jsonb_set(
        jsonb_set(
            jsonb_set(
                case
                    when relation.raw_payload ? 'normalized_payload' then relation.raw_payload
                    else jsonb_build_object('normalized_payload', relation.raw_payload)
                end,
                '{normalized_payload,status}',
                to_jsonb('cancelled'::text),
                true
            ),
            '{normalized_payload,withdrawn_by}',
            to_jsonb('migration:0073'::text),
            true
        ),
        '{normalized_payload,special_metadata}',
        coalesce(relation.special_metadata, '{}'::jsonb)
            || jsonb_build_object(
                'migrated_to_pending_relation_id', 'oa-pending-' || relation.case_id,
                'migration', '0073_oa_pending_payment_bank_relations'
            ),
        true
    ),
    updated_at = now()
where relation.status = 'active'
  and relation.special_metadata->>'origin' = 'oa_pending_payment_in_progress';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.oa_pending_payment_bank_relations to fin_ops_app_runtime;
        grant select, insert, update, delete on app.bank_transaction_relation_claims to fin_ops_app_runtime;
        grant select, insert on app.oa_pending_payment_bank_relation_events to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on app.oa_pending_payment_bank_relations to fin_ops_api;
        grant select on app.bank_transaction_relation_claims to fin_ops_api;
        grant select on app.oa_pending_payment_bank_relation_events to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.oa_pending_payment_bank_relations to fin_ops_worker;
        grant select, insert, update, delete on app.bank_transaction_relation_claims to fin_ops_worker;
        grant select, insert on app.oa_pending_payment_bank_relation_events to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.oa_pending_payment_bank_relations to fin_ops_readonly;
        grant select on app.bank_transaction_relation_claims to fin_ops_readonly;
        grant select on app.oa_pending_payment_bank_relation_events to fin_ops_readonly;
    end if;
end $$;

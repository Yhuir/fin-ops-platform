create table if not exists app.bank_flow_rule_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_id text not null unique,
    status text not null,
    status_bucket text,
    version integer not null default 1,
    scope_month date,
    account_key text,
    total_amount numeric(20, 6) not null default 0,
    bank_transaction_ids text[] not null default array[]::text[],
    submitted_by text,
    submitted_at timestamptz,
    withdrawn_by text,
    withdrawn_at timestamptz,
    source_versions jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists bank_flow_rule_batches_scope_status_idx
    on app.bank_flow_rule_batches (scope_month, status);

create index if not exists bank_flow_rule_batches_account_idx
    on app.bank_flow_rule_batches (account_key, scope_month);

create table if not exists app.bank_flow_rule_batch_events (
    id uuid primary key default gen_random_uuid(),
    bank_flow_rule_batch_id uuid references app.bank_flow_rule_batches(id),
    batch_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists bank_flow_rule_batch_events_batch_idx
    on app.bank_flow_rule_batch_events (batch_id, occurred_at desc);

create table if not exists read_model.bank_flow_rule_batch_rows (
    id uuid primary key default gen_random_uuid(),
    batch_id text not null unique,
    scope_month date,
    batch_type text,
    status text not null,
    status_bucket text,
    account_key text,
    total_amount numeric(20, 6) not null default 0,
    row_count integer not null default 0,
    submitted_at timestamptz,
    withdrawn_at timestamptz,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists bank_flow_rule_batch_rows_filters_idx
    on read_model.bank_flow_rule_batch_rows (scope_month, batch_type, status, status_bucket, account_key);

create index if not exists bank_flow_rule_batch_rows_generated_idx
    on read_model.bank_flow_rule_batch_rows (generated_at desc, batch_id);

create index if not exists bank_flow_rule_batch_rows_source_versions_gin
    on read_model.bank_flow_rule_batch_rows using gin (source_versions);

insert into app.bank_flow_rule_batches(
    id, legacy_mongo_id, batch_id, status, status_bucket, version, scope_month, account_key,
    total_amount, bank_transaction_ids, submitted_by, submitted_at, withdrawn_by, withdrawn_at,
    source_versions, created_at, updated_at, raw_payload
)
select
    id, legacy_mongo_id, batch_id, status, status_bucket, version, scope_month, account_key,
    total_amount, bank_transaction_ids, submitted_by, submitted_at, withdrawn_by, withdrawn_at,
    source_versions, created_at, updated_at, raw_payload
from app.no_oa_bank_batches
where coalesce(nullif(raw_payload->'normalized_payload'->>'relation_mode', ''), 'no_oa_bank_batch') = 'bank_flow_rule_batch'
on conflict (batch_id) do update set
    status = excluded.status,
    status_bucket = excluded.status_bucket,
    version = excluded.version,
    scope_month = excluded.scope_month,
    account_key = excluded.account_key,
    total_amount = excluded.total_amount,
    bank_transaction_ids = excluded.bank_transaction_ids,
    submitted_by = excluded.submitted_by,
    submitted_at = excluded.submitted_at,
    withdrawn_by = excluded.withdrawn_by,
    withdrawn_at = excluded.withdrawn_at,
    source_versions = excluded.source_versions,
    raw_payload = excluded.raw_payload,
    updated_at = now();

insert into app.bank_flow_rule_batch_events(
    id, bank_flow_rule_batch_id, batch_id, event_type, actor_id, occurred_at, payload, raw_payload
)
select
    event.id,
    batch.id,
    event.batch_id,
    event.event_type,
    event.actor_id,
    event.occurred_at,
    case
        when jsonb_typeof(event.payload) = 'object'
        then event.payload || '{"relation_mode": "bank_flow_rule_batch"}'::jsonb
        else event.payload
    end,
    event.raw_payload
from app.no_oa_bank_batch_events event
join app.bank_flow_rule_batches batch on batch.batch_id = event.batch_id
where not exists (
    select 1
    from app.bank_flow_rule_batch_events existing
    where existing.id = event.id
)
on conflict (id) do update set
    bank_flow_rule_batch_id = excluded.bank_flow_rule_batch_id,
    batch_id = excluded.batch_id,
    event_type = excluded.event_type,
    actor_id = excluded.actor_id,
    occurred_at = excluded.occurred_at,
    payload = excluded.payload,
    raw_payload = excluded.raw_payload;

insert into read_model.bank_flow_rule_batch_rows(
    id, batch_id, scope_month, batch_type, status, status_bucket, account_key,
    total_amount, row_count, submitted_at, withdrawn_at, source_versions,
    generated_at, cache_status, payload, raw_payload, created_at, updated_at
)
select
    id, batch_id, scope_month, batch_type, status, status_bucket, account_key,
    total_amount, row_count, submitted_at, withdrawn_at, source_versions,
    generated_at, cache_status, payload, raw_payload, created_at, updated_at
from read_model.no_oa_bank_batch_rows
where coalesce(nullif(payload->>'relation_mode', ''), 'no_oa_bank_batch') = 'bank_flow_rule_batch'
on conflict (batch_id) do update set
    scope_month = excluded.scope_month,
    batch_type = excluded.batch_type,
    status = excluded.status,
    status_bucket = excluded.status_bucket,
    account_key = excluded.account_key,
    total_amount = excluded.total_amount,
    row_count = excluded.row_count,
    submitted_at = excluded.submitted_at,
    withdrawn_at = excluded.withdrawn_at,
    source_versions = excluded.source_versions,
    generated_at = excluded.generated_at,
    cache_status = excluded.cache_status,
    payload = excluded.payload,
    raw_payload = excluded.raw_payload,
    updated_at = now();

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_api;
        grant select, insert, update, delete on app.bank_flow_rule_batch_events to fin_ops_api;
        grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_app;
        grant select, insert, update, delete on app.bank_flow_rule_batch_events to fin_ops_app;
        grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_app;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_app_runtime;
        grant select, insert, update, delete on app.bank_flow_rule_batch_events to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_app_runtime;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_worker;
        grant select, insert, update, delete on app.bank_flow_rule_batch_events to fin_ops_worker;
        grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.bank_flow_rule_batches to fin_ops_readonly;
        grant select on app.bank_flow_rule_batch_events to fin_ops_readonly;
        grant select on read_model.bank_flow_rule_batch_rows to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.bank_flow_rule_batches to fin_ops_migrator;
        grant select, insert, update, delete on app.bank_flow_rule_batch_events to fin_ops_migrator;
        grant select, insert, update, delete on read_model.bank_flow_rule_batch_rows to fin_ops_migrator;
    end if;
end $$;

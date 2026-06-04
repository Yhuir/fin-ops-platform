create table if not exists read_model.app_status_readiness (
    tenant_id text not null default 'default',
    read_model_key text not null,
    scope_type text not null,
    scope_key text not null,
    status text not null,
    schema_version text not null default '',
    source_versions jsonb not null default '{}'::jsonb,
    row_count bigint,
    generated_at timestamptz,
    last_error text,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    primary key (tenant_id, read_model_key, scope_type, scope_key),
    constraint app_status_readiness_status_check check (
        status in (
            'fresh',
            'missing',
            'refreshing',
            'stale',
            'schema_mismatch',
            'source_mismatch',
            'failed',
            'unavailable'
        )
    )
);

create index if not exists app_status_readiness_key_status_idx
    on read_model.app_status_readiness (tenant_id, read_model_key, status, updated_at desc);

create index if not exists app_status_readiness_scope_idx
    on read_model.app_status_readiness (tenant_id, scope_type, scope_key);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.app_status_readiness to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.app_status_readiness to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.app_status_readiness to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.app_status_readiness to fin_ops_migrator;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.app_status_readiness to fin_ops_app_runtime;
    end if;
end $$;

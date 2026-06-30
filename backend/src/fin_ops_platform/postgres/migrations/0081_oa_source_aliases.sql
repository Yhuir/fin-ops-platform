create table if not exists app.oa_source_aliases (
    id uuid primary key default gen_random_uuid(),
    alias_row_id text not null,
    canonical_row_id text not null,
    reason text not null,
    evidence_hash text not null,
    status text not null default 'pending_review',
    reviewed_by text,
    reviewed_at timestamptz,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint oa_source_aliases_status_chk
        check (status in ('pending_review', 'active', 'rejected', 'revoked')),
    constraint oa_source_aliases_distinct_rows_chk
        check (alias_row_id <> canonical_row_id)
);

create unique index if not exists oa_source_aliases_alias_uidx
    on app.oa_source_aliases(alias_row_id)
    where status in ('pending_review', 'active');

create index if not exists oa_source_aliases_canonical_status_idx
    on app.oa_source_aliases(canonical_row_id, status, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on app.oa_source_aliases to fin_ops_app;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.oa_source_aliases to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.oa_source_aliases to fin_ops_migrator;
    end if;
end $$;

create table if not exists app.oa_applicant_credentials (
    id uuid primary key default gen_random_uuid(),
    target_applicant_code text not null,
    target_applicant_name text not null,
    oa_username text not null,
    encrypted_password bytea,
    credential_status text not null default 'unconfigured',
    enabled boolean not null default true,
    updated_by text not null default '',
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint oa_applicant_credentials_status_chk
        check (credential_status in ('configured', 'unconfigured')),
    constraint oa_applicant_credentials_configured_password_chk
        check (credential_status <> 'configured' or encrypted_password is not null)
);

create unique index if not exists oa_applicant_credentials_target_uidx
    on app.oa_applicant_credentials(target_applicant_code);

create index if not exists oa_applicant_credentials_status_idx
    on app.oa_applicant_credentials(credential_status, enabled, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update, delete on app.oa_applicant_credentials to fin_ops_app;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.oa_applicant_credentials to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.oa_applicant_credentials to fin_ops_migrator;
    end if;
end $$;

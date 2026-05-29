create table if not exists app.bank_transaction_category_confirmations (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    bank_transaction_id uuid null references app.bank_transactions(id) on delete cascade,
    legacy_transaction_id text null,
    category_code text not null,
    candidate_category_codes jsonb not null default '[]'::jsonb,
    rule_version text not null default '',
    status text not null default 'active',
    version integer not null default 1,
    confirmed_by text not null default '',
    confirmed_at timestamptz not null default now(),
    revoked_by text null,
    revoked_at timestamptz null,
    raw_payload jsonb not null default '{}'::jsonb,
    constraint bank_transaction_category_confirmations_target_check
        check (bank_transaction_id is not null or nullif(legacy_transaction_id, '') is not null),
    constraint bank_transaction_category_confirmations_status_check
        check (status in ('active', 'revoked'))
);

create unique index if not exists bank_transaction_category_confirmations_one_active_id
    on app.bank_transaction_category_confirmations(tenant_id, bank_transaction_id)
    where status = 'active' and bank_transaction_id is not null;

create unique index if not exists bank_transaction_category_confirmations_one_active_legacy
    on app.bank_transaction_category_confirmations(tenant_id, legacy_transaction_id)
    where status = 'active' and legacy_transaction_id is not null;

create index if not exists bank_transaction_category_confirmations_category_idx
    on app.bank_transaction_category_confirmations(tenant_id, category_code);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on app.bank_transaction_category_confirmations to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on app.bank_transaction_category_confirmations to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.bank_transaction_category_confirmations to fin_ops_migrator;
    end if;
end $$;

create table if not exists read_model.bank_account_balances (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    account_identity text not null,
    account_key text not null,
    bank_name text not null,
    account_last4 text not null,
    account_no text,
    account_name text,
    identity_confidence text not null default 'fallback',
    latest_balance numeric(20, 6),
    latest_balance_at timestamptz,
    latest_balance_transaction_id text,
    latest_trade_time_sort timestamptz,
    latest_bank_serial_no text,
    source_batch_id text,
    legacy_source_batch_id text,
    currency text not null default 'CNY',
    transaction_total_count bigint not null default 0,
    schema_version integer not null,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint bank_account_balances_identity_confidence_chk
        check (identity_confidence in ('account_no', 'bank_last4', 'fallback'))
);

create unique index if not exists bank_account_balances_identity_uidx
    on read_model.bank_account_balances (tenant_id, account_identity);

create index if not exists bank_account_balances_currency_idx
    on read_model.bank_account_balances (tenant_id, currency);

create index if not exists bank_account_balances_latest_time_idx
    on read_model.bank_account_balances (tenant_id, latest_trade_time_sort desc, latest_balance_transaction_id desc);

create index if not exists bank_account_balances_schema_idx
    on read_model.bank_account_balances (tenant_id, schema_version);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.bank_account_balances to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.bank_account_balances to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.bank_account_balances to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.bank_account_balances to fin_ops_migrator;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.bank_account_balances to fin_ops_app_runtime;
    end if;
end $$;

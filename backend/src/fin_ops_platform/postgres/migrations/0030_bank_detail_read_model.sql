create table if not exists read_model.bank_detail_rows (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    transaction_id text not null,
    scope_key text not null,
    scope_month date not null,
    source_batch_id text,
    legacy_source_batch_id text,
    account_key text not null,
    bank_name text not null,
    account_last4 text not null,
    account_no text,
    account_name text,
    trade_time timestamptz,
    trade_date date,
    trade_time_sort timestamptz not null,
    direction text not null,
    direction_label text not null,
    amount numeric(20, 6) not null,
    signed_amount numeric(20, 6),
    balance numeric(20, 6),
    currency text,
    counterparty_name text,
    summary text,
    purpose text,
    manual_category_code text,
    manual_category_label text,
    manual_category_path text[] not null default '{}'::text[],
    manual_category_source text,
    manual_category_version integer,
    auto_category_code text,
    auto_category_label text,
    auto_category_path text[] not null default '{}'::text[],
    auto_category_source text,
    auto_category_rule_code text,
    auto_category_reason text,
    auto_category_confidence text,
    auto_category_rule_version text,
    effective_category_code text,
    effective_category_label text,
    effective_category_path text[] not null default '{}'::text[],
    effective_category_source text,
    category_version integer,
    category_source text,
    oa_relation_tag text,
    invoice_relation_tag text,
    relation_tags text[] not null default '{}'::text[],
    relation_case_id text,
    search_text text not null default '',
    schema_version integer not null,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint bank_detail_rows_direction_chk check (direction in ('income', 'expense'))
);

create table if not exists read_model.bank_detail_scopes (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_type text not null default 'bank_detail',
    scope_key text not null,
    scope_month date,
    schema_version integer not null,
    status text not null default 'fresh',
    row_count integer not null default 0,
    source_version bigint,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz,
    last_error text,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    constraint bank_detail_scopes_status_chk check (status in ('fresh', 'pending', 'processing', 'stale', 'failed'))
);

create unique index if not exists bank_detail_rows_transaction_uidx
    on read_model.bank_detail_rows (tenant_id, transaction_id);

create index if not exists bank_detail_rows_month_time_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, trade_time_sort desc, transaction_id desc);

create index if not exists bank_detail_rows_month_account_time_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, account_key, trade_time_sort desc, transaction_id desc);

create index if not exists bank_detail_rows_category_idx
    on read_model.bank_detail_rows (tenant_id, scope_month, effective_category_code);

create index if not exists bank_detail_rows_search_trgm
    on read_model.bank_detail_rows using gin (search_text gin_trgm_ops);

create unique index if not exists bank_detail_scopes_tenant_scope_uidx
    on read_model.bank_detail_scopes (tenant_id, scope_type, scope_key);

create index if not exists bank_detail_scopes_status_idx
    on read_model.bank_detail_scopes (tenant_id, scope_type, status, updated_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.bank_detail_rows to fin_ops_api;
        grant select on read_model.bank_detail_scopes to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.bank_detail_rows to fin_ops_worker;
        grant select, insert, update, delete on read_model.bank_detail_scopes to fin_ops_worker;
        grant select, insert, update on job.read_model_dirty_scopes to fin_ops_worker;
        grant select, insert, update on job.outbox_events to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.bank_detail_rows to fin_ops_readonly;
        grant select on read_model.bank_detail_scopes to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.bank_detail_rows to fin_ops_migrator;
        grant select, insert, update, delete on read_model.bank_detail_scopes to fin_ops_migrator;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select on read_model.bank_detail_rows to fin_ops_app_runtime;
        grant select on read_model.bank_detail_scopes to fin_ops_app_runtime;
    end if;
end $$;

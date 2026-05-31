create table if not exists read_model.oa_pending_payment_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null,
    scope_key text not null,
    scope_month date not null,
    oa_id text not null,
    oa_applicant text,
    oa_application_type text,
    oa_project_name text,
    oa_amount numeric(20, 6),
    payment_status text,
    payment_status_label text,
    bank_transaction_id text,
    bank_trade_time timestamptz,
    bank_amount numeric(20, 6),
    bank_name text,
    bank_counterparty_name text,
    bank_summary text,
    invoice_id text,
    invoice_no text,
    invoice_date date,
    seller_name text,
    invoice_total_with_tax numeric(20, 6),
    searchable_text text not null default '',
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (row_id, scope_key)
);

create table if not exists read_model.oa_pending_payment_scopes (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null unique,
    scope_month date,
    row_count integer not null default 0,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    source_versions jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists oa_pending_payment_rows_scope_trade_idx
    on read_model.oa_pending_payment_rows (scope_key, bank_trade_time desc, row_id);
create index if not exists oa_pending_payment_rows_month_trade_idx
    on read_model.oa_pending_payment_rows (scope_month, bank_trade_time desc);
create index if not exists oa_pending_payment_rows_status_idx
    on read_model.oa_pending_payment_rows (payment_status, scope_month);
create index if not exists oa_pending_payment_rows_applicant_trgm
    on read_model.oa_pending_payment_rows using gin (oa_applicant gin_trgm_ops);
create index if not exists oa_pending_payment_rows_project_trgm
    on read_model.oa_pending_payment_rows using gin (oa_project_name gin_trgm_ops);
create index if not exists oa_pending_payment_rows_bank_counterparty_trgm
    on read_model.oa_pending_payment_rows using gin (bank_counterparty_name gin_trgm_ops);
create index if not exists oa_pending_payment_rows_search_trgm
    on read_model.oa_pending_payment_rows using gin (searchable_text gin_trgm_ops);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update, delete on read_model.oa_pending_payment_rows to fin_ops_app_runtime;
        grant select, insert, update, delete on read_model.oa_pending_payment_scopes to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.oa_pending_payment_rows to fin_ops_api;
        grant select on read_model.oa_pending_payment_scopes to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.oa_pending_payment_rows to fin_ops_worker;
        grant select, insert, update, delete on read_model.oa_pending_payment_scopes to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.oa_pending_payment_rows to fin_ops_readonly;
        grant select on read_model.oa_pending_payment_scopes to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.oa_pending_payment_rows to fin_ops_migrator;
        grant select, insert, update, delete on read_model.oa_pending_payment_scopes to fin_ops_migrator;
    end if;
end $$;

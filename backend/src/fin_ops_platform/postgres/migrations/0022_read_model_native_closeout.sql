-- SQL-native read model closeout for API hot paths.
--
-- Source-of-truth remains in app.* and job.* tables. These read_model tables
-- are deterministic projections rebuilt by workers and safe to delete/rebuild.

alter table read_model.pending_invoice_rows
    add column if not exists scope_key text;

update read_model.pending_invoice_rows
set scope_key = case
    when scope_month is not null then direction || ':' || filter_group || ':' || to_char(scope_month, 'YYYY-MM')
    else direction || ':' || filter_group
end
where scope_key is null or scope_key = '';

create index if not exists pending_invoice_rows_scope_key_idx
    on read_model.pending_invoice_rows (scope_key);

create index if not exists pending_invoice_rows_scope_page_idx
    on read_model.pending_invoice_rows (direction, filter_group, scope_month, trade_date desc, row_id);

create table if not exists read_model.cost_statistics_rows (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null,
    project_scope text not null,
    scope_month date not null,
    row_key text not null,
    transaction_id text not null,
    group_id text,
    trade_time_text text,
    trade_date date,
    counterparty_name text,
    payment_account_label text,
    direction text,
    remark text,
    project_id text,
    project_name text not null,
    expense_type text not null,
    expense_content text,
    amount numeric(20, 6) not null default 0,
    oa_applicant text,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (scope_key, row_key),
    check (project_scope in ('active', 'all'))
);

create index if not exists cost_statistics_rows_scope_time_idx
    on read_model.cost_statistics_rows (scope_key, trade_date desc nulls last, trade_time_text desc, transaction_id);

create index if not exists cost_statistics_rows_project_idx
    on read_model.cost_statistics_rows (scope_key, project_name, expense_type);

create index if not exists cost_statistics_rows_expense_idx
    on read_model.cost_statistics_rows (scope_key, expense_type, project_name);

create table if not exists read_model.tax_offset_items (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null,
    scope_month date not null,
    item_type text not null,
    item_id text not null,
    item_index integer not null default 0,
    issue_date date,
    invoice_no text,
    invoice_code text,
    digital_invoice_no text,
    seller_name text,
    seller_tax_no text,
    buyer_name text,
    buyer_tax_no text,
    invoice_type text,
    tax_rate text,
    tax_amount numeric(20, 6),
    total_with_tax numeric(20, 6),
    source_kind text,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (scope_key, item_type, item_id),
    check (item_type in ('output', 'input_plan', 'certified', 'certified_matched', 'certified_outside'))
);

create index if not exists tax_offset_items_scope_type_idx
    on read_model.tax_offset_items (scope_key, item_type, item_index, item_id);

create index if not exists tax_offset_items_invoice_identity_idx
    on read_model.tax_offset_items (digital_invoice_no, invoice_code, invoice_no)
    where digital_invoice_no is not null or invoice_no is not null;

create table if not exists read_model.no_oa_bank_batch_rows (
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

create index if not exists no_oa_bank_batch_rows_filters_idx
    on read_model.no_oa_bank_batch_rows (scope_month, batch_type, status, status_bucket, account_key);

create index if not exists no_oa_bank_batch_rows_generated_idx
    on read_model.no_oa_bank_batch_rows (generated_at desc, batch_id);

create table if not exists read_model.turnover_ledger_rows (
    id uuid primary key default gen_random_uuid(),
    relation_id text not null unique,
    scope_month date,
    family text,
    status text,
    relation_type text,
    source text,
    counterparty_name text,
    amount numeric(20, 6),
    bank_row_ids text[] not null default array[]::text[],
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists turnover_ledger_rows_filters_idx
    on read_model.turnover_ledger_rows (family, status, scope_month, generated_at desc);

create index if not exists turnover_ledger_rows_counterparty_trgm
    on read_model.turnover_ledger_rows using gin (counterparty_name gin_trgm_ops);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.cost_statistics_rows to fin_ops_api;
        grant select on read_model.tax_offset_items to fin_ops_api;
        grant select, insert, update, delete on read_model.no_oa_bank_batch_rows to fin_ops_api;
        grant select, insert, update, delete on read_model.turnover_ledger_rows to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.cost_statistics_rows to fin_ops_worker;
        grant select, insert, update, delete on read_model.tax_offset_items to fin_ops_worker;
        grant select, insert, update, delete on read_model.no_oa_bank_batch_rows to fin_ops_worker;
        grant select, insert, update, delete on read_model.turnover_ledger_rows to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.cost_statistics_rows to fin_ops_readonly;
        grant select on read_model.tax_offset_items to fin_ops_readonly;
        grant select on read_model.no_oa_bank_batch_rows to fin_ops_readonly;
        grant select on read_model.turnover_ledger_rows to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.cost_statistics_rows to fin_ops_migrator;
        grant select, insert, update, delete on read_model.tax_offset_items to fin_ops_migrator;
        grant select, insert, update, delete on read_model.no_oa_bank_batch_rows to fin_ops_migrator;
        grant select, insert, update, delete on read_model.turnover_ledger_rows to fin_ops_migrator;
    end if;
end $$;

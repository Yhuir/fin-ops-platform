create table if not exists read_model.input_invoice_usage_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null,
    scope_key text not null,
    scope_month date not null,
    invoice_id text not null,
    invoice_identity_key text not null,
    invoice_no text,
    invoice_date date,
    buyer_name text,
    buyer_tax_no text,
    seller_name text,
    seller_tax_no text,
    total_with_tax numeric(20, 6),
    amount numeric(20, 6),
    tax_amount numeric(20, 6),
    tax_rate text,
    specific_business_type text,
    taxable_item_name text,
    payment_status text,
    payment_status_label text,
    collection_status text,
    collection_status_label text,
    collected_amount numeric(20, 6),
    pending_amount numeric(20, 6),
    oa_applicant text,
    oa_application_type text,
    oa_project_name text,
    bank_counterparty_name text,
    bank_trade_time timestamptz,
    bank_amount numeric(20, 6),
    bank_name text,
    bank_summary text,
    receipt_status text,
    receipt_status_label text,
    oa_relation_count integer not null default 0,
    bank_relation_count integer not null default 0,
    red_invoice_relation_count integer not null default 0,
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

create table if not exists read_model.input_invoice_usage_scopes (
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

create index if not exists input_invoice_usage_rows_scope_date_idx on read_model.input_invoice_usage_rows (scope_key, invoice_date desc, row_id);
create index if not exists input_invoice_usage_rows_month_date_idx on read_model.input_invoice_usage_rows (scope_month, invoice_date desc);
create index if not exists input_invoice_usage_rows_status_idx on read_model.input_invoice_usage_rows (payment_status, scope_month);
create index if not exists input_invoice_usage_rows_seller_trgm on read_model.input_invoice_usage_rows using gin (seller_name gin_trgm_ops);
create index if not exists input_invoice_usage_rows_bank_counterparty_trgm on read_model.input_invoice_usage_rows using gin (bank_counterparty_name gin_trgm_ops);
create index if not exists input_invoice_usage_rows_search_trgm on read_model.input_invoice_usage_rows using gin (searchable_text gin_trgm_ops);

create table if not exists read_model.output_invoice_collection_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null,
    scope_key text not null,
    scope_month date not null,
    invoice_id text not null,
    invoice_identity_key text not null,
    invoice_no text,
    invoice_date date,
    buyer_name text,
    buyer_tax_no text,
    seller_name text,
    seller_tax_no text,
    total_with_tax numeric(20, 6),
    amount numeric(20, 6),
    tax_amount numeric(20, 6),
    tax_rate text,
    specific_business_type text,
    taxable_item_name text,
    payment_status text,
    payment_status_label text,
    collection_status text,
    collection_status_label text,
    collected_amount numeric(20, 6),
    pending_amount numeric(20, 6),
    bank_counterparty_name text,
    bank_trade_time timestamptz,
    bank_amount numeric(20, 6),
    bank_name text,
    bank_summary text,
    receipt_status text,
    receipt_status_label text,
    oa_applicant text,
    oa_application_type text,
    oa_project_name text,
    oa_relation_count integer not null default 0,
    bank_relation_count integer not null default 0,
    red_invoice_relation_count integer not null default 0,
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

create table if not exists read_model.output_invoice_collection_scopes (
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

create index if not exists output_invoice_collection_rows_scope_date_idx on read_model.output_invoice_collection_rows (scope_key, invoice_date desc, row_id);
create index if not exists output_invoice_collection_rows_month_date_idx on read_model.output_invoice_collection_rows (scope_month, invoice_date desc);
create index if not exists output_invoice_collection_rows_status_idx on read_model.output_invoice_collection_rows (collection_status, scope_month);
create index if not exists output_invoice_collection_rows_buyer_trgm on read_model.output_invoice_collection_rows using gin (buyer_name gin_trgm_ops);
create index if not exists output_invoice_collection_rows_bank_counterparty_trgm on read_model.output_invoice_collection_rows using gin (bank_counterparty_name gin_trgm_ops);
create index if not exists output_invoice_collection_rows_search_trgm on read_model.output_invoice_collection_rows using gin (searchable_text gin_trgm_ops);

do $$
begin
    grant select, insert, update, delete on read_model.input_invoice_usage_rows to fin_ops_app;
    grant select, insert, update, delete on read_model.input_invoice_usage_scopes to fin_ops_app;
    grant select, insert, update, delete on read_model.output_invoice_collection_rows to fin_ops_app;
    grant select, insert, update, delete on read_model.output_invoice_collection_scopes to fin_ops_app;
exception
    when undefined_object then
        null;
end $$;

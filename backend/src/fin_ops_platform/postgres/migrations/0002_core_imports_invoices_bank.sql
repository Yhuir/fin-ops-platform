create table if not exists app.import_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_type text not null,
    source_name text not null,
    imported_by text not null,
    row_count integer not null default 0,
    success_count integer not null default 0,
    error_count integer not null default 0,
    duplicate_count integer not null default 0,
    suspected_duplicate_count integer not null default 0,
    updated_count integer not null default 0,
    status text not null,
    imported_at timestamptz not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists import_batches_type_time_idx on app.import_batches (batch_type, imported_at desc);
create index if not exists import_batches_status_time_idx on app.import_batches (status, imported_at desc);

create table if not exists app.import_batch_rows (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    import_batch_id uuid references app.import_batches(id),
    legacy_batch_id text,
    row_no integer not null,
    source_record_type text not null,
    source_unique_key text,
    data_fingerprint text,
    decision text not null,
    decision_reason text,
    linked_object_type text,
    linked_object_id text,
    identity_kind text,
    account_no text,
    trade_time timestamptz,
    direction text,
    amount numeric(20, 6),
    counterparty_name text,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists import_batch_rows_batch_idx on app.import_batch_rows (import_batch_id, row_no);
create index if not exists import_batch_rows_decision_idx on app.import_batch_rows (decision);

create table if not exists app.file_objects (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    legacy_gridfs_id text,
    storage_backend text not null,
    storage_uri text not null,
    bucket_name text,
    object_key text,
    filename text,
    sha256 text,
    size_bytes bigint,
    content_type text,
    uploaded_at timestamptz,
    file_metadata jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists file_objects_storage_idx on app.file_objects (storage_backend, storage_uri);
create index if not exists file_objects_sha256_idx on app.file_objects (sha256) where sha256 is not null;

create table if not exists app.import_files (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    import_batch_id uuid references app.import_batches(id),
    file_object_id uuid references app.file_objects(id),
    session_id text,
    stored_file_path text,
    original_filename text,
    template_kind text,
    status text not null default 'stored',
    uploaded_by text,
    uploaded_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists import_files_session_idx on app.import_files (session_id);
create index if not exists import_files_batch_idx on app.import_files (import_batch_id);

create table if not exists app.invoices (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    invoice_type text not null,
    invoice_no text not null,
    invoice_code text,
    digital_invoice_no text,
    source_unique_key text,
    data_fingerprint text,
    invoice_date date,
    invoice_month date,
    counterparty_id text,
    counterparty_name text,
    seller_name text,
    seller_tax_no text,
    buyer_name text,
    buyer_tax_no text,
    amount numeric(20, 6) not null,
    signed_amount numeric(20, 6) not null,
    written_off_amount numeric(20, 6) not null default 0,
    tax_rate text,
    tax_amount numeric(20, 6),
    total_with_tax numeric(20, 6),
    currency text not null default 'CNY',
    source_batch_id uuid references app.import_batches(id),
    legacy_source_batch_id text,
    oa_form_id text,
    etc_invoice_id text,
    workbench_visibility text not null default 'visible',
    status text not null,
    tags text[] not null default array[]::text[],
    source_links jsonb not null default '[]'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists invoices_source_unique_key_uidx on app.invoices (source_unique_key) where source_unique_key is not null;
create unique index if not exists invoices_data_fingerprint_uidx on app.invoices (data_fingerprint) where data_fingerprint is not null;
create index if not exists invoices_month_no_idx on app.invoices (invoice_month, invoice_no);
create index if not exists invoices_month_buyer_idx on app.invoices (invoice_month, buyer_name);
create index if not exists invoices_month_seller_idx on app.invoices (invoice_month, seller_name);
create index if not exists invoices_status_type_idx on app.invoices (status, invoice_type);
create index if not exists invoices_source_batch_idx on app.invoices (source_batch_id);
create index if not exists invoices_invoice_no_trgm on app.invoices using gin (invoice_no gin_trgm_ops);
create index if not exists invoices_counterparty_trgm on app.invoices using gin (counterparty_name gin_trgm_ops);
create index if not exists invoices_buyer_trgm on app.invoices using gin (buyer_name gin_trgm_ops);
create index if not exists invoices_seller_trgm on app.invoices using gin (seller_name gin_trgm_ops);

create table if not exists app.bank_transactions (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    account_no text not null,
    account_name text,
    txn_direction text not null,
    counterparty_name_raw text not null,
    normalized_counterparty_name text,
    amount numeric(20, 6) not null,
    signed_amount numeric(20, 6) not null,
    written_off_amount numeric(20, 6) not null default 0,
    txn_date date,
    txn_month date,
    trade_time timestamptz,
    pay_receive_time timestamptz,
    bank_serial_no text,
    source_unique_key text,
    data_fingerprint text,
    source_batch_id uuid references app.import_batches(id),
    legacy_source_batch_id text,
    counterparty_id text,
    project_id text,
    balance numeric(20, 6),
    currency text,
    summary text,
    remark text,
    bank_text_fields jsonb not null default '[]'::jsonb,
    status text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists bank_transactions_source_unique_key_uidx on app.bank_transactions (source_unique_key) where source_unique_key is not null;
create unique index if not exists bank_transactions_data_fingerprint_uidx on app.bank_transactions (data_fingerprint) where data_fingerprint is not null;
create index if not exists bank_transactions_month_account_idx on app.bank_transactions (txn_month, account_no, txn_date);
create index if not exists bank_transactions_month_direction_amount_idx on app.bank_transactions (txn_month, txn_direction, amount);
create index if not exists bank_transactions_source_batch_idx on app.bank_transactions (source_batch_id);
create index if not exists bank_transactions_counterparty_trgm on app.bank_transactions using gin (counterparty_name_raw gin_trgm_ops);

create table if not exists app.bank_transaction_categories (
    id uuid primary key default gen_random_uuid(),
    bank_transaction_id uuid references app.bank_transactions(id),
    legacy_transaction_id text,
    category text not null,
    source text not null,
    confidence numeric(10, 6),
    status text not null default 'active',
    version integer not null default 1,
    updated_by text,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists bank_transaction_categories_txn_idx on app.bank_transaction_categories (bank_transaction_id, status);

create table if not exists app.bank_transaction_category_events (
    id uuid primary key default gen_random_uuid(),
    category_id uuid references app.bank_transaction_categories(id),
    bank_transaction_id uuid references app.bank_transactions(id),
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists bank_transaction_category_events_txn_idx on app.bank_transaction_category_events (bank_transaction_id, occurred_at desc);

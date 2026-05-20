create table if not exists app.tax_certified_import_sessions (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    session_id text not null unique,
    status text not null,
    scope_month date,
    imported_by text,
    imported_at timestamptz not null default now(),
    record_count integer not null default 0,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.tax_certified_import_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_id text not null unique,
    session_id uuid references app.tax_certified_import_sessions(id),
    status text not null,
    scope_month date,
    row_count integer not null default 0,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.tax_certified_import_records (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_id uuid references app.tax_certified_import_batches(id),
    certified_unique_key text not null,
    invoice_no text,
    invoice_code text,
    digital_invoice_no text,
    seller_name text,
    seller_tax_no text,
    invoice_date date,
    scope_month date,
    amount numeric(20, 6),
    tax_amount numeric(20, 6) not null default 0,
    matched_plan_id text,
    status text not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (certified_unique_key)
);

create index if not exists tax_certified_records_scope_idx on app.tax_certified_import_records (scope_month, status);
create index if not exists tax_certified_records_invoice_idx on app.tax_certified_import_records (invoice_no, invoice_code);

create table if not exists app.etc_invoices (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    etc_invoice_id text not null unique,
    invoice_no text,
    invoice_code text,
    invoice_date date,
    scope_month date,
    seller_name text,
    buyer_name text,
    amount numeric(20, 6),
    tax_amount numeric(20, 6),
    total_with_tax numeric(20, 6),
    status text not null,
    batch_id text,
    task_id text,
    business_batch_id text,
    oa_detection_payload jsonb not null default '{}'::jsonb,
    file_object_id uuid references app.file_objects(id),
    file_path text,
    file_sha256 text,
    version integer not null default 1,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists etc_invoices_scope_status_idx on app.etc_invoices (scope_month, status);
create index if not exists etc_invoices_invoice_trgm on app.etc_invoices using gin (invoice_no gin_trgm_ops);

create table if not exists app.etc_import_sessions (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    session_id text not null unique,
    status text not null,
    imported_by text,
    imported_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.etc_import_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_id text not null unique,
    session_id uuid references app.etc_import_sessions(id),
    status text not null,
    scope_month date,
    invoice_count integer not null default 0,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.etc_submission_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    submission_batch_id text not null unique,
    status text not null,
    scope_month date,
    invoice_ids text[] not null default array[]::text[],
    submitted_by text,
    submitted_at timestamptz,
    version integer not null default 1,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.etc_business_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    business_batch_id text not null unique,
    task_id text,
    status text not null,
    scope_month date,
    invoice_count integer not null default 0,
    total_amount numeric(20, 6) not null default 0,
    oa_detection_status text,
    oa_detection_payload jsonb not null default '{}'::jsonb,
    import_attempts jsonb not null default '[]'::jsonb,
    audit_events jsonb not null default '[]'::jsonb,
    version integer not null default 1,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create unique index if not exists etc_business_batches_active_task_uidx on app.etc_business_batches (task_id) where status <> 'withdrawn' and task_id is not null;

create table if not exists app.etc_reconciliation_tasks (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    task_id text not null unique,
    status text not null,
    scope_month date,
    source_file_id text,
    source_file_object_id uuid references app.file_objects(id),
    result_summary jsonb not null default '{}'::jsonb,
    version integer not null default 1,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.etc_reconciliation_files (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    task_id text,
    file_id text not null unique,
    file_object_id uuid references app.file_objects(id),
    file_kind text not null,
    status text not null default 'stored',
    file_path text,
    file_sha256 text,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.historical_etc_repair_bundles (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    bundle_id text not null unique,
    file_object_id uuid references app.file_objects(id),
    status text not null,
    metadata jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.historical_etc_repair_parsed_seeds (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    seed_id text not null unique,
    bundle_id text,
    status text not null,
    parsed_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.historical_etc_repair_states (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    state_id text not null unique,
    status text not null,
    version integer not null default 1,
    state_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create table if not exists app.turnover_relations (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    relation_id text not null unique,
    bank_transaction_id text,
    status text not null,
    relation_type text,
    scope_month date,
    counterparty_name text,
    amount numeric(20, 6),
    version integer not null default 1,
    audit_payload jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists turnover_relations_scope_status_idx on app.turnover_relations (scope_month, status);
create index if not exists turnover_relations_counterparty_trgm on app.turnover_relations using gin (counterparty_name gin_trgm_ops);

create table if not exists app.turnover_relation_events (
    id uuid primary key default gen_random_uuid(),
    turnover_relation_id uuid references app.turnover_relations(id),
    relation_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists turnover_relation_events_relation_idx on app.turnover_relation_events (relation_id, occurred_at desc);

create table if not exists app.turnover_ledger_extras (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    ledger_key text not null unique,
    scope_month date,
    extra_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now()
);

create table if not exists app.app_settings (
    id uuid primary key default gen_random_uuid(),
    settings_key text not null unique,
    version integer not null default 1,
    settings_payload jsonb not null default '{}'::jsonb,
    updated_by text,
    updated_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create table if not exists job.background_jobs (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    job_id text not null unique,
    job_type text not null,
    status text not null,
    owner_id text,
    visibility text,
    source text,
    affected_months text[] not null default array[]::text[],
    progress jsonb not null default '{}'::jsonb,
    result_summary jsonb not null default '{}'::jsonb,
    error text,
    retry_mode text,
    attention jsonb not null default '{}'::jsonb,
    superseded_by_job_id text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists background_jobs_status_idx on job.background_jobs (status, updated_at desc);
create index if not exists background_jobs_type_idx on job.background_jobs (job_type, created_at desc);

create table if not exists audit.app_health_alerts (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    alert_id text not null unique,
    kind text not null,
    scope text,
    severity text not null,
    status text not null,
    active_at timestamptz,
    recovered_at timestamptz,
    acknowledged_by text,
    acknowledged_at timestamptz,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists app_health_alerts_status_idx on audit.app_health_alerts (status, severity, active_at desc);

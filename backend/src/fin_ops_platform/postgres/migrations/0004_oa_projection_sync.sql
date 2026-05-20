create table if not exists app.oa_applications (
    id uuid primary key default gen_random_uuid(),
    oa_source_id text not null,
    form_id text not null,
    form_type text,
    row_id text not null unique,
    workflow_no text,
    status text not null,
    applicant text,
    application_date date,
    approved_at timestamptz,
    project_id text,
    project_name text,
    amount numeric(20, 6),
    currency text,
    source_updated_at timestamptz,
    normalized_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    synced_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (oa_source_id, form_id)
);

create index if not exists oa_applications_form_status_idx on app.oa_applications (form_id, status);
create index if not exists oa_applications_source_updated_idx on app.oa_applications (source_updated_at);
create index if not exists oa_applications_project_trgm on app.oa_applications using gin (project_name gin_trgm_ops);
create index if not exists oa_applications_applicant_trgm on app.oa_applications using gin (applicant gin_trgm_ops);

create table if not exists app.oa_application_items (
    id uuid primary key default gen_random_uuid(),
    oa_application_id uuid references app.oa_applications(id),
    oa_source_id text,
    form_id text,
    row_id text,
    item_type text,
    item_no text,
    amount numeric(20, 6),
    tax_amount numeric(20, 6),
    project_id text,
    project_name text,
    normalized_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists oa_application_items_application_idx on app.oa_application_items (oa_application_id);
create index if not exists oa_application_items_row_idx on app.oa_application_items (row_id);

create table if not exists app.oa_attachments (
    id uuid primary key default gen_random_uuid(),
    oa_application_id uuid references app.oa_applications(id),
    oa_source_id text,
    form_id text,
    row_id text,
    source_attachment_key text not null,
    filename text,
    content_type text,
    size_bytes bigint,
    source_modified_at timestamptz,
    file_object_id uuid references app.file_objects(id),
    normalized_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    unique (source_attachment_key)
);

create index if not exists oa_attachments_application_idx on app.oa_attachments (oa_application_id);

create table if not exists app.oa_sync_runs (
    id uuid primary key default gen_random_uuid(),
    sync_type text not null,
    status text not null,
    started_at timestamptz not null default now(),
    finished_at timestamptz,
    scanned_count integer not null default 0,
    upserted_count integer not null default 0,
    skipped_count integer not null default 0,
    error_count integer not null default 0,
    last_error text,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists oa_sync_runs_type_time_idx on app.oa_sync_runs (sync_type, started_at desc);

create table if not exists app.oa_sync_watermarks (
    id uuid primary key default gen_random_uuid(),
    sync_key text not null unique,
    form_id text,
    source_updated_after timestamptz,
    last_success_at timestamptz,
    status text not null default 'idle',
    version integer not null default 1,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    updated_at timestamptz not null default now()
);

create table if not exists app.oa_attachment_invoice_cache (
    id uuid primary key default gen_random_uuid(),
    source_attachment_key text not null unique,
    parser_version text not null,
    cache_schema_version text not null,
    source_size_bytes bigint,
    source_modified_at timestamptz,
    parsed_at timestamptz not null,
    evidences jsonb not null default '[]'::jsonb,
    invoices jsonb not null default '[]'::jsonb,
    artifacts jsonb not null default '{}'::jsonb,
    normalized_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists oa_attachment_invoice_cache_parser_idx on app.oa_attachment_invoice_cache (parser_version, cache_schema_version);

create table if not exists app.manual_oa_imports (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    row_id text not null unique,
    source text not null,
    actor_id text,
    imported_at timestamptz not null,
    status text not null default 'active',
    audit_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

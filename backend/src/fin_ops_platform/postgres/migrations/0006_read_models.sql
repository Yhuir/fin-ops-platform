create table if not exists read_model.workbench_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null unique,
    scope_month date,
    scope_key text,
    source_kind text not null,
    status text not null,
    project_id text,
    project_name text,
    counterparty_name text,
    amount numeric(20, 6),
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null,
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists workbench_rows_scope_status_idx on read_model.workbench_rows (scope_month, status);
create index if not exists workbench_rows_source_kind_idx on read_model.workbench_rows (source_kind, scope_month);
create index if not exists workbench_rows_project_trgm on read_model.workbench_rows using gin (project_name gin_trgm_ops);
create index if not exists workbench_rows_counterparty_trgm on read_model.workbench_rows using gin (counterparty_name gin_trgm_ops);
create index if not exists workbench_rows_payload_gin on read_model.workbench_rows using gin (payload);

create table if not exists read_model.workbench_snapshots (
    id uuid primary key default gen_random_uuid(),
    scope_key text not null unique,
    scope_month date,
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null,
    cache_status text not null default 'fresh',
    row_count integer not null default 0,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists workbench_snapshots_scope_idx on read_model.workbench_snapshots (scope_month, generated_at desc);

create table if not exists read_model.workbench_candidate_matches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    candidate_key text not null unique,
    scope_month date,
    status text not null,
    row_ids text[] not null default array[]::text[],
    confidence numeric(10, 6),
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null,
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists workbench_candidate_matches_scope_idx on read_model.workbench_candidate_matches (scope_month, status);
create index if not exists workbench_candidate_matches_row_ids_gin on read_model.workbench_candidate_matches using gin (row_ids);

create table if not exists read_model.search_index_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null unique,
    source_kind text not null,
    scope_month date,
    status text,
    title text,
    subtitle text,
    searchable_text text not null,
    project_name text,
    counterparty_name text,
    amount numeric(20, 6),
    source_versions jsonb not null default '{}'::jsonb,
    generated_at timestamptz not null,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists search_index_rows_scope_kind_idx on read_model.search_index_rows (scope_month, source_kind);
create index if not exists search_index_rows_search_trgm on read_model.search_index_rows using gin (searchable_text gin_trgm_ops);
create index if not exists search_index_rows_project_trgm on read_model.search_index_rows using gin (project_name gin_trgm_ops);
create index if not exists search_index_rows_counterparty_trgm on read_model.search_index_rows using gin (counterparty_name gin_trgm_ops);

create table if not exists read_model.cost_statistics_read_models (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    scope_key text not null unique,
    project_scope text not null,
    scope_month date,
    generated_at timestamptz not null,
    entry_count integer not null default 0,
    source_counts jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists cost_statistics_read_models_scope_idx on read_model.cost_statistics_read_models (project_scope, scope_month);

create table if not exists read_model.tax_offset_read_models (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    scope_key text not null unique,
    scope_month date,
    generated_at timestamptz not null,
    entry_count integer not null default 0,
    source_counts jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists tax_offset_read_models_scope_idx on read_model.tax_offset_read_models (scope_month);

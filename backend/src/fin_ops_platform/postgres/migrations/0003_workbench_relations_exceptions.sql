create table if not exists app.workbench_pair_relations (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    case_id text not null unique,
    relation_mode text not null,
    status text not null,
    version integer not null default 1,
    month_scope date,
    row_ids text[] not null default array[]::text[],
    row_types text[] not null default array[]::text[],
    note text,
    amount_check jsonb not null default '{}'::jsonb,
    special_metadata jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    created_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    withdrawn_by text,
    withdrawn_at timestamptz,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists workbench_pair_relations_status_month_idx on app.workbench_pair_relations (status, month_scope);
create index if not exists workbench_pair_relations_mode_status_idx on app.workbench_pair_relations (relation_mode, status);
create index if not exists workbench_pair_relations_row_ids_gin on app.workbench_pair_relations using gin (row_ids);
create index if not exists workbench_pair_relations_active_idx on app.workbench_pair_relations (month_scope, relation_mode) where status = 'active';

create table if not exists app.workbench_pair_relation_history (
    id uuid primary key default gen_random_uuid(),
    relation_id uuid references app.workbench_pair_relations(id),
    case_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    before_payload jsonb not null default '{}'::jsonb,
    after_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists workbench_pair_relation_history_case_idx on app.workbench_pair_relation_history (case_id, occurred_at desc);

create table if not exists app.workbench_row_overrides (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    row_id text not null,
    row_type text not null,
    scope_month date,
    status text not null default 'active',
    projection_version integer not null default 1,
    override_payload jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    changed_row_ids text[] not null default array[]::text[],
    updated_by text,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create unique index if not exists workbench_row_overrides_row_uidx on app.workbench_row_overrides (row_id, row_type);
create index if not exists workbench_row_overrides_scope_idx on app.workbench_row_overrides (scope_month, status);

create table if not exists app.workbench_exception_cases (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    case_id text not null unique,
    status text not null,
    version integer not null default 1,
    business_line text,
    scenario text,
    resolution text,
    scope_month date,
    row_ids text[] not null default array[]::text[],
    candidate_ids text[] not null default array[]::text[],
    source_versions jsonb not null default '{}'::jsonb,
    history_payload jsonb not null default '[]'::jsonb,
    created_by text,
    created_at timestamptz not null default now(),
    updated_by text,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists workbench_exception_cases_status_scope_idx on app.workbench_exception_cases (status, scope_month);
create index if not exists workbench_exception_cases_row_ids_gin on app.workbench_exception_cases using gin (row_ids);
create index if not exists workbench_exception_cases_candidate_ids_gin on app.workbench_exception_cases using gin (candidate_ids);

create table if not exists app.workbench_exception_case_events (
    id uuid primary key default gen_random_uuid(),
    exception_case_id uuid references app.workbench_exception_cases(id),
    case_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists workbench_exception_case_events_case_idx on app.workbench_exception_case_events (case_id, occurred_at desc);

create table if not exists app.no_oa_bank_batches (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    batch_id text not null unique,
    status text not null,
    status_bucket text,
    version integer not null default 1,
    scope_month date,
    account_key text,
    total_amount numeric(20, 6) not null default 0,
    bank_transaction_ids text[] not null default array[]::text[],
    submitted_by text,
    submitted_at timestamptz,
    withdrawn_by text,
    withdrawn_at timestamptz,
    source_versions jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists no_oa_bank_batches_scope_status_idx on app.no_oa_bank_batches (scope_month, status);
create index if not exists no_oa_bank_batches_account_idx on app.no_oa_bank_batches (account_key, scope_month);

create table if not exists app.no_oa_bank_batch_events (
    id uuid primary key default gen_random_uuid(),
    no_oa_bank_batch_id uuid references app.no_oa_bank_batches(id),
    batch_id text not null,
    event_type text not null,
    actor_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists no_oa_bank_batch_events_batch_idx on app.no_oa_bank_batch_events (batch_id, occurred_at desc);

create table if not exists job.workbench_matching_dirty_scopes (
    id uuid primary key default gen_random_uuid(),
    scope_month date not null,
    reason text,
    status text not null default 'dirty',
    attempt_count integer not null default 0,
    last_error text,
    available_at timestamptz not null default now(),
    source_versions jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create unique index if not exists workbench_matching_dirty_scopes_scope_uidx on job.workbench_matching_dirty_scopes (scope_month);
create index if not exists workbench_matching_dirty_scopes_status_idx on job.workbench_matching_dirty_scopes (status, available_at);

create table if not exists app.matching_runs (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    run_id text not null unique,
    triggered_by text,
    invoice_count integer not null default 0,
    transaction_count integer not null default 0,
    result_count integer not null default 0,
    executed_at timestamptz not null,
    status text not null default 'completed',
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists matching_runs_executed_idx on app.matching_runs (executed_at desc);

create table if not exists app.matching_results (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    run_id uuid references app.matching_runs(id),
    legacy_run_id text,
    result_type text not null,
    confidence text not null,
    rule_code text,
    invoice_ids text[] not null default array[]::text[],
    transaction_ids text[] not null default array[]::text[],
    amount numeric(20, 6) not null default 0,
    difference_amount numeric(20, 6) not null default 0,
    counterparty_name text,
    explanation text,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);

create index if not exists matching_results_run_idx on app.matching_results (run_id);
create index if not exists matching_results_invoices_gin on app.matching_results using gin (invoice_ids);
create index if not exists matching_results_transactions_gin on app.matching_results using gin (transaction_ids);

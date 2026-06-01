create table if not exists app.tax_offset_plans (
    id uuid primary key default gen_random_uuid(),
    legacy_mongo_id text unique,
    plan_id text not null unique,
    scope_month date not null,
    status text not null,
    selected_output_ids text[] not null default array[]::text[],
    selected_input_ids text[] not null default array[]::text[],
    calculation_summary jsonb not null default '{}'::jsonb,
    source_versions jsonb not null default '{}'::jsonb,
    read_model_scope_key text,
    created_by text,
    idempotency_key text unique,
    audit_trace jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists tax_offset_plans_scope_status_idx on app.tax_offset_plans (scope_month, status);
create index if not exists tax_offset_plans_updated_idx on app.tax_offset_plans (updated_at desc);

grant select, insert, update on app.tax_offset_plans to fin_ops_api;
grant select, insert, update, delete on app.tax_offset_plans to fin_ops_worker;
grant select, insert, update, delete on app.tax_offset_plans to fin_ops_migrator;

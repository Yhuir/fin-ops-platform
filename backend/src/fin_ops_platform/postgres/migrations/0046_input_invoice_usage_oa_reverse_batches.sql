create table if not exists app.input_invoice_usage_oa_reverse_batches (
    id uuid primary key default gen_random_uuid(),
    batch_id text not null unique,
    status text not null,
    version integer not null default 1,
    target_applicant_code text not null,
    target_applicant_name text not null,
    invoice_ids text[] not null default array[]::text[],
    invoice_count integer not null default 0,
    total_amount numeric(20, 6) not null default 0,
    preview_hash text not null,
    create_idempotency_key text unique,
    oa_form_id integer not null default 2,
    oa_draft_id text,
    oa_draft_url text,
    oa_row_id text,
    oa_process_status text not null default 'unknown',
    oa_detection_status text not null default 'not_started',
    oa_detection_payload jsonb not null default '{}'::jsonb,
    audit_events jsonb not null default '[]'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_by text,
    updated_by text,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists input_invoice_usage_oa_reverse_batches_status_idx
    on app.input_invoice_usage_oa_reverse_batches(status, updated_at desc);

create index if not exists input_invoice_usage_oa_reverse_batches_invoice_ids_gin
    on app.input_invoice_usage_oa_reverse_batches using gin(invoice_ids);

create index if not exists input_invoice_usage_oa_reverse_batches_oa_draft_idx
    on app.input_invoice_usage_oa_reverse_batches(oa_draft_id)
    where oa_draft_id is not null;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app') then
        grant select, insert, update on app.input_invoice_usage_oa_reverse_batches to fin_ops_app;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update on app.input_invoice_usage_oa_reverse_batches to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update on app.input_invoice_usage_oa_reverse_batches to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.input_invoice_usage_oa_reverse_batches to fin_ops_migrator;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.input_invoice_usage_oa_reverse_batches to fin_ops_readonly;
    end if;
end $$;

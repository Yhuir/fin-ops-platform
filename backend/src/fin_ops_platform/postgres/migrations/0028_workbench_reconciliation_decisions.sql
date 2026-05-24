create table if not exists read_model.workbench_reconciliation_decisions (
    id uuid primary key default gen_random_uuid(),
    tenant_id text not null default 'default',
    scope_month date not null,
    decision_id text,
    decision_key text not null,
    display_state text not null,
    decision_status text not null,
    match_domain text not null,
    match_shape text not null,
    rule_code text not null,
    rule_version text not null,
    row_ids text[] not null default '{}'::text[],
    row_types text[] not null default '{}'::text[],
    oa_row_ids text[] not null default '{}'::text[],
    bank_row_ids text[] not null default '{}'::text[],
    invoice_row_ids text[] not null default '{}'::text[],
    amount numeric(18, 2),
    direction text,
    cardinality text,
    payment_amount_closed boolean not null default false,
    invoice_amount_closed boolean not null default false,
    warnings jsonb not null default '[]'::jsonb,
    evidence jsonb not null default '{}'::jsonb,
    blockers jsonb not null default '[]'::jsonb,
    conflict_set jsonb not null default '[]'::jsonb,
    explanation text,
    source_versions jsonb not null default '{}'::jsonb,
    consumed_by_relation_id uuid,
    suppressed_by_exception_case_id uuid,
    generated_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    constraint workbench_reconciliation_decisions_display_state_chk
        check (display_state in ('paired', 'open')),
    constraint workbench_reconciliation_decisions_status_chk
        check (decision_status in ('proposed', 'paired', 'open', 'suppressed', 'consumed', 'expired')),
    constraint workbench_reconciliation_decisions_domain_chk
        check (match_domain in ('free', 'special'))
);

create unique index if not exists workbench_reconciliation_decisions_tenant_key_uidx
    on read_model.workbench_reconciliation_decisions (tenant_id, decision_key);

create index if not exists workbench_reconciliation_decisions_scope_status_idx
    on read_model.workbench_reconciliation_decisions (tenant_id, scope_month, decision_status);

create index if not exists workbench_reconciliation_decisions_row_ids_gin
    on read_model.workbench_reconciliation_decisions using gin (row_ids);

create index if not exists workbench_reconciliation_decisions_oa_row_ids_gin
    on read_model.workbench_reconciliation_decisions using gin (oa_row_ids);

create index if not exists workbench_reconciliation_decisions_bank_row_ids_gin
    on read_model.workbench_reconciliation_decisions using gin (bank_row_ids);

create index if not exists workbench_reconciliation_decisions_invoice_row_ids_gin
    on read_model.workbench_reconciliation_decisions using gin (invoice_row_ids);

alter table job.workbench_matching_dirty_scopes
    add column if not exists tenant_id text not null default 'default',
    add column if not exists lease_owner text,
    add column if not exists lease_expires_at timestamptz,
    add column if not exists request_id text,
    add column if not exists started_at timestamptz,
    add column if not exists completed_at timestamptz,
    add column if not exists failed_at timestamptz,
    add column if not exists duration_ms integer,
    add column if not exists error_summary text;

drop index if exists job.workbench_matching_dirty_scopes_scope_uidx;

create unique index if not exists workbench_matching_dirty_scopes_tenant_scope_uidx
    on job.workbench_matching_dirty_scopes (tenant_id, scope_month);

create index if not exists workbench_matching_dirty_scopes_claim_idx
    on job.workbench_matching_dirty_scopes (tenant_id, status, available_at, lease_expires_at);

create index if not exists workbench_matching_dirty_scopes_lease_idx
    on job.workbench_matching_dirty_scopes (tenant_id, lease_owner, lease_expires_at);

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'job.workbench_matching_dirty_scopes'::regclass
          and conname = 'workbench_matching_dirty_scopes_status_chk'
    ) then
        alter table job.workbench_matching_dirty_scopes
            add constraint workbench_matching_dirty_scopes_status_chk
            check (status in ('dirty', 'retry', 'processing', 'completed', 'failed')) not valid;
    end if;
end $$;

alter table app.matching_runs
    add column if not exists request_id text,
    add column if not exists scope_month date,
    add column if not exists started_at timestamptz,
    add column if not exists completed_at timestamptz,
    add column if not exists failed_at timestamptz,
    add column if not exists duration_ms integer,
    add column if not exists source_versions jsonb not null default '{}'::jsonb,
    add column if not exists error_summary text;

create unique index if not exists matching_runs_request_id_uidx
    on app.matching_runs (request_id)
    where request_id is not null;

create index if not exists matching_runs_scope_status_idx
    on app.matching_runs (scope_month, status, started_at desc);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.workbench_reconciliation_decisions to fin_ops_api;
        grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.workbench_reconciliation_decisions to fin_ops_worker;
        grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_worker;
        grant select, insert, update on app.matching_runs to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.workbench_reconciliation_decisions to fin_ops_readonly;
        grant select on job.workbench_matching_dirty_scopes to fin_ops_readonly;
        grant select on app.matching_runs to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.workbench_reconciliation_decisions to fin_ops_migrator;
        grant select, insert, update on job.workbench_matching_dirty_scopes to fin_ops_migrator;
        grant select, insert, update on app.matching_runs to fin_ops_migrator;
    end if;
end $$;

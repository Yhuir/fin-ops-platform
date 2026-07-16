-- Move cost-statistics bank-flow detail out of parent JSON so API views and
-- direct detail lookup can use bounded, indexed read-model rows.

create table if not exists read_model.cost_statistics_bank_flow_rows (
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
    bank_tag_code text,
    bank_tag_label text,
    bank_tag_primary_label text,
    bank_tag_sub_label text,
    bank_tag_label_path jsonb not null default '[]'::jsonb,
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

create index if not exists cost_statistics_bank_flow_rows_scope_time_idx
    on read_model.cost_statistics_bank_flow_rows (
        scope_key,
        trade_date desc nulls last,
        trade_time_text desc,
        transaction_id,
        row_key
    );

create index if not exists cost_statistics_bank_flow_rows_parent_rollup_idx
    on read_model.cost_statistics_bank_flow_rows (
        project_scope,
        scope_month,
        trade_date desc nulls last,
        trade_time_text desc,
        transaction_id,
        row_key
    );

create index if not exists cost_statistics_bank_flow_rows_identity_idx
    on read_model.cost_statistics_bank_flow_rows (
        project_scope,
        transaction_id,
        scope_month desc,
        row_key
    );

create index if not exists cost_statistics_rows_identity_idx
    on read_model.cost_statistics_rows (
        project_scope,
        transaction_id,
        scope_month desc,
        row_key
    );

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.cost_statistics_bank_flow_rows to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.cost_statistics_bank_flow_rows to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.cost_statistics_bank_flow_rows to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.cost_statistics_bank_flow_rows to fin_ops_migrator;
    end if;
end $$;

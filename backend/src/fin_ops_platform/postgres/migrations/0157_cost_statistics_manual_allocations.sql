set local lock_timeout = '10s';
set local statement_timeout = '1min';

create table if not exists app.cost_statistics_manual_allocations (
    id uuid primary key default gen_random_uuid(),
    relation_case_id text not null unique,
    relation_version integer not null check (relation_version >= 1),
    source_fingerprint text not null check (source_fingerprint ~ '^[0-9a-f]{64}$'),
    oa_allocation_total numeric(18, 2) not null check (oa_allocation_total >= 0),
    bank_outflow_total numeric(18, 2) not null check (bank_outflow_total >= 0),
    paid_wrong_refund_total numeric(18, 2) not null check (paid_wrong_refund_total >= 0),
    net_cash_cost numeric(18, 2) not null check (net_cash_cost >= 0),
    allocations jsonb not null check (jsonb_typeof(allocations) = 'array'),
    version integer not null default 1 check (version >= 1),
    created_by text not null,
    created_at timestamptz not null default now(),
    updated_by text not null,
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

comment on table app.cost_statistics_manual_allocations is
    'Current explicit OA allocation for one mismatched active workbench relation; source_fingerprint invalidates stale decisions.';

grant select, insert, update on app.cost_statistics_manual_allocations to fin_ops_api;
grant select, insert, update on app.cost_statistics_manual_allocations to fin_ops_app_runtime;
grant select on app.cost_statistics_manual_allocations to fin_ops_readonly;
grant select, insert, update on app.cost_statistics_manual_allocations to fin_ops_migrator;

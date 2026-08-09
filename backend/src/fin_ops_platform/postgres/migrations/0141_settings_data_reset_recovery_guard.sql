-- Bind every destructive settings reset to a fresh, verified PostgreSQL restore point.

set local lock_timeout = '5s';
set local statement_timeout = '2min';

create table if not exists job.settings_data_reset_recovery_receipts (
    receipt_id uuid primary key default gen_random_uuid(),
    action text not null check (action in (
        'reset_bank_transactions', 'reset_invoices', 'reset_oa_and_rebuild'
    )),
    impact_fingerprint text not null check (impact_fingerprint ~ '^[0-9a-f]{64}$'),
    restore_point_run_id text not null check (btrim(restore_point_run_id) <> ''),
    dump_sha256 text not null check (dump_sha256 ~ '^[0-9a-f]{64}$'),
    dump_size_bytes bigint not null check (dump_size_bytes > 0),
    created_by text not null check (btrim(created_by) <> ''),
    created_at timestamptz not null default now(),
    valid_until timestamptz not null,
    consumed_by_job_id text,
    consumed_at timestamptz,
    revoked_at timestamptz,
    raw_payload jsonb not null default '{}'::jsonb,
    unique (restore_point_run_id, action, impact_fingerprint),
    unique (consumed_by_job_id),
    check (valid_until > created_at),
    check ((consumed_by_job_id is null) = (consumed_at is null))
);

create index if not exists settings_data_reset_recovery_available_idx
    on job.settings_data_reset_recovery_receipts (
        action, impact_fingerprint, valid_until desc, created_at desc
    )
    where consumed_by_job_id is null and revoked_at is null;

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, update on job.settings_data_reset_recovery_receipts to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, update on job.settings_data_reset_recovery_receipts to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on job.settings_data_reset_recovery_receipts to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on job.settings_data_reset_recovery_receipts to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on job.settings_data_reset_recovery_receipts to fin_ops_migrator;
    end if;
end $$;

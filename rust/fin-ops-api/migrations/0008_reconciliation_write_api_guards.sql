create extension if not exists pgcrypto;

create table app.write_idempotency_records (
  id uuid primary key default gen_random_uuid(),
  operation text not null,
  idempotency_key text not null,
  request_payload jsonb not null,
  response_payload jsonb not null,
  aggregate_type text not null,
  aggregate_id uuid not null,
  status text not null default 'completed',
  created_by text not null,
  created_at timestamptz not null default now(),
  constraint write_idempotency_records_status_chk check (
    status in ('completed', 'failed')
  ),
  constraint write_idempotency_records_request_payload_chk check (
    jsonb_typeof(request_payload) = 'object'
  ),
  constraint write_idempotency_records_response_payload_chk check (
    jsonb_typeof(response_payload) = 'object'
  ),
  constraint write_idempotency_records_operation_key_uk unique (
    operation,
    idempotency_key
  )
);

create index write_idempotency_records_aggregate_idx
  on app.write_idempotency_records (aggregate_type, aggregate_id, created_at desc);

alter table app.reconciliation_cases
  add column row_version integer not null default 1;

alter table app.reconciliation_cases
  add constraint reconciliation_cases_row_version_chk check (row_version > 0);

alter table app.workbench_row_overrides
  add column idempotency_key text,
  add column row_version integer not null default 1,
  add column cancelled_at timestamptz,
  add column cancelled_by text;

alter table app.workbench_row_overrides
  add constraint workbench_row_overrides_row_version_chk check (row_version > 0);

create unique index workbench_row_overrides_idempotency_key_uidx
  on app.workbench_row_overrides (idempotency_key)
  where idempotency_key is not null;

alter table app.workbench_exception_cases
  add column idempotency_key text,
  add column row_version integer not null default 1,
  add column cancelled_at timestamptz,
  add column cancelled_by text;

alter table app.workbench_exception_cases
  add constraint workbench_exception_cases_row_version_chk check (row_version > 0);

create unique index workbench_exception_cases_idempotency_key_uidx
  on app.workbench_exception_cases (idempotency_key)
  where idempotency_key is not null;

alter table app.no_oa_bank_batches
  add column idempotency_key text,
  add column row_version integer not null default 1,
  add column relation_case_id uuid references app.reconciliation_cases(id),
  add column cancelled_by text;

alter table app.no_oa_bank_batches
  add constraint no_oa_bank_batches_row_version_chk check (row_version > 0);

create unique index no_oa_bank_batches_idempotency_key_uidx
  on app.no_oa_bank_batches (idempotency_key)
  where idempotency_key is not null;

drop index if exists app.reconciliation_case_rows_active_object_idx;

create unique index reconciliation_case_rows_active_object_uidx
  on app.reconciliation_case_rows (object_type, object_id)
  where binding_status = 'active';

create index reconciliation_cases_row_version_idx
  on app.reconciliation_cases (id, row_version);

create index workbench_exception_cases_row_version_idx
  on app.workbench_exception_cases (id, row_version);

create index no_oa_bank_batches_row_version_idx
  on app.no_oa_bank_batches (id, row_version);

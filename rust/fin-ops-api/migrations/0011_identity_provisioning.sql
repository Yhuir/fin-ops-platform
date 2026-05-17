create extension if not exists pgcrypto;

create table app.identity_provisioning_requests (
  id uuid primary key default gen_random_uuid(),
  settings_profile_id uuid not null references app.settings_profiles(id) on delete restrict,
  settings_version integer not null,
  status text not null default 'queued',
  requested_by text not null,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  idempotency_key text not null,
  trace_id text,
  payload_hash text not null,
  audit_event_id uuid references audit.events(id) on delete set null,
  last_error_code text,
  last_error text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint identity_provisioning_requests_version_chk check (settings_version > 0),
  constraint identity_provisioning_requests_status_chk check (
    status in ('queued', 'running', 'succeeded', 'failed', 'retrying', 'dead_lettered', 'cancelled')
  ),
  constraint identity_provisioning_requests_payload_hash_chk check (
    payload_hash ~ '^[0-9a-f]{64}$'
  ),
  constraint identity_provisioning_requests_idempotency_key_uk unique (idempotency_key),
  constraint identity_provisioning_requests_settings_version_uk unique (
    settings_profile_id,
    settings_version
  ),
  constraint identity_provisioning_requests_payload_hash_uk unique (payload_hash)
);

create trigger identity_provisioning_requests_set_updated_at
before update on app.identity_provisioning_requests
for each row
execute function app.set_updated_at();

create index identity_provisioning_requests_status_idx
  on app.identity_provisioning_requests (status, updated_at desc);

create index identity_provisioning_requests_settings_idx
  on app.identity_provisioning_requests (settings_profile_id, settings_version);

create index identity_provisioning_requests_worker_task_idx
  on app.identity_provisioning_requests (worker_task_id)
  where worker_task_id is not null;

create index identity_provisioning_requests_outbox_event_idx
  on app.identity_provisioning_requests (outbox_event_id)
  where outbox_event_id is not null;

create extension if not exists pgcrypto;

create schema if not exists job;

create table job.outbox_events (
  id uuid primary key default gen_random_uuid(),
  aggregate_type text not null,
  aggregate_id uuid not null,
  event_type text not null,
  subject text not null,
  payload jsonb not null,
  status text not null default 'pending',
  idempotency_key text not null,
  trace_id text,
  created_by uuid,
  available_at timestamptz not null default now(),
  locked_by text,
  locked_at timestamptz,
  published_at timestamptz,
  attempt_count integer not null default 0,
  last_error_code text,
  last_error text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint outbox_events_status_chk check (
    status in (
      'pending',
      'publishing',
      'published',
      'retrying',
      'failed',
      'dead_lettered',
      'cancelled'
    )
  ),
  constraint outbox_events_attempt_count_chk check (attempt_count >= 0)
);

create trigger outbox_events_set_updated_at
before update on job.outbox_events
for each row
execute function app.set_updated_at();

create unique index outbox_events_idempotency_key_uidx
  on job.outbox_events (idempotency_key);

create index outbox_events_pending_idx
  on job.outbox_events (status, available_at, created_at)
  where status in ('pending', 'retrying');

create index outbox_events_publishing_timeout_idx
  on job.outbox_events (locked_at, available_at)
  where status = 'publishing';

create index outbox_events_aggregate_idx
  on job.outbox_events (aggregate_type, aggregate_id, created_at);

create index outbox_events_trace_idx
  on job.outbox_events (trace_id)
  where trace_id is not null;

create table job.worker_tasks (
  id uuid primary key default gen_random_uuid(),
  task_type text not null,
  status text not null default 'queued',
  phase text not null default 'queued',
  priority integer not null default 0,
  idempotency_key text not null,
  owner_user_id uuid,
  visibility text not null default 'owner',
  label text not null,
  source jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  result_summary jsonb not null default '{}'::jsonb,
  affected_scopes text[] not null default '{}',
  affected_months date[] not null default '{}',
  current_count integer not null default 0,
  total_count integer not null default 0,
  percent integer not null default 0,
  error_code text,
  error_summary text,
  retryable boolean not null default true,
  max_attempts integer not null default 5,
  attempt_count integer not null default 0,
  available_at timestamptz not null default now(),
  next_attempt_at timestamptz,
  locked_by text,
  locked_at timestamptz,
  created_by text,
  created_at timestamptz not null default now(),
  started_at timestamptz,
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  cancelled_at timestamptz,
  constraint worker_tasks_status_chk check (
    status in (
      'queued',
      'running',
      'succeeded',
      'failed',
      'retrying',
      'dead_lettered',
      'cancelled'
    )
  ),
  constraint worker_tasks_visibility_chk check (visibility in ('owner', 'system')),
  constraint worker_tasks_counts_chk check (
    current_count >= 0
    and total_count >= 0
    and current_count <= total_count
  ),
  constraint worker_tasks_percent_chk check (percent >= 0 and percent <= 100),
  constraint worker_tasks_attempts_chk check (
    attempt_count >= 0
    and max_attempts > 0
    and attempt_count <= max_attempts
  )
);

create trigger worker_tasks_set_updated_at
before update on job.worker_tasks
for each row
execute function app.set_updated_at();

create unique index worker_tasks_idempotency_key_uidx
  on job.worker_tasks (idempotency_key);

create index worker_tasks_owner_status_idx
  on job.worker_tasks (owner_user_id, status, updated_at desc);

create index worker_tasks_active_idx
  on job.worker_tasks (status, next_attempt_at, created_at)
  where status in ('queued', 'retrying', 'running');

create index worker_tasks_claim_idx
  on job.worker_tasks (status, available_at, priority desc, created_at)
  where status in ('queued', 'retrying');

create index worker_tasks_running_lock_idx
  on job.worker_tasks (locked_by, locked_at)
  where status = 'running';

create index worker_tasks_type_status_idx
  on job.worker_tasks (task_type, status, updated_at desc);

create table job.worker_attempts (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references job.worker_tasks(id) on delete cascade,
  attempt_no integer not null,
  worker_id text not null,
  nats_stream text,
  nats_consumer text,
  nats_sequence bigint,
  started_at timestamptz not null default now(),
  heartbeat_at timestamptz,
  finished_at timestamptz,
  duration_ms integer,
  status text not null,
  error_code text,
  error_summary text,
  error_detail jsonb not null default '{}'::jsonb,
  constraint worker_attempts_attempt_no_chk check (attempt_no > 0),
  constraint worker_attempts_duration_chk check (duration_ms is null or duration_ms >= 0),
  constraint worker_attempts_status_chk check (
    status in (
      'running',
      'succeeded',
      'failed',
      'retrying',
      'dead_lettered',
      'cancelled'
    )
  )
);

create unique index worker_attempts_task_attempt_uidx
  on job.worker_attempts (task_id, attempt_no);

create index worker_attempts_task_status_idx
  on job.worker_attempts (task_id, status, started_at desc);

create index worker_attempts_worker_idx
  on job.worker_attempts (worker_id, started_at desc);

create table job.dead_letters (
  id uuid primary key default gen_random_uuid(),
  source_kind text not null,
  source_id uuid not null,
  subject text,
  task_type text,
  idempotency_key text,
  payload jsonb not null,
  error_code text not null,
  error_summary text not null,
  error_detail jsonb not null default '{}'::jsonb,
  replay_status text not null default 'open',
  replayed_by uuid,
  replayed_at timestamptz,
  created_at timestamptz not null default now(),
  constraint dead_letters_source_kind_chk check (
    source_kind in ('outbox', 'worker_task', 'nats_message')
  ),
  constraint dead_letters_replay_status_chk check (
    replay_status in ('open', 'replayed', 'ignored')
  )
);

create index dead_letters_open_idx
  on job.dead_letters (created_at)
  where replay_status = 'open';

create index dead_letters_source_idx
  on job.dead_letters (source_kind, source_id);

create index dead_letters_idempotency_key_idx
  on job.dead_letters (idempotency_key)
  where idempotency_key is not null;

create table job.worker_heartbeats (
  id uuid primary key default gen_random_uuid(),
  worker_id text not null,
  worker_kind text not null,
  task_id uuid references job.worker_tasks(id) on delete set null,
  attempt_id uuid references job.worker_attempts(id) on delete set null,
  status text not null default 'active',
  process_started_at timestamptz,
  heartbeat_at timestamptz not null default now(),
  lease_expires_at timestamptz,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint worker_heartbeats_status_chk check (
    status in ('active', 'draining', 'stopped', 'lost')
  )
);

create trigger worker_heartbeats_set_updated_at
before update on job.worker_heartbeats
for each row
execute function app.set_updated_at();

create unique index worker_heartbeats_worker_id_uidx
  on job.worker_heartbeats (worker_id);

create index worker_heartbeats_active_idx
  on job.worker_heartbeats (status, lease_expires_at, heartbeat_at)
  where status in ('active', 'draining');

create index worker_heartbeats_task_idx
  on job.worker_heartbeats (task_id)
  where task_id is not null;

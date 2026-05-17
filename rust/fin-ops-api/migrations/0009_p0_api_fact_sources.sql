create table job.worker_task_acknowledgements (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references job.worker_tasks(id) on delete cascade,
  actor_id text not null,
  reason text,
  acknowledgement_state text not null default 'acknowledged',
  acknowledged_at timestamptz not null default now(),
  idempotency_key text not null,
  trace_id text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  source_metadata jsonb not null default '{}'::jsonb,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint worker_task_acknowledgements_state_chk check (
    acknowledgement_state in ('acknowledged', 'dismissed')
  ),
  constraint worker_task_acknowledgements_source_metadata_chk check (
    jsonb_typeof(source_metadata) = 'object'
  ),
  constraint worker_task_acknowledgements_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint worker_task_acknowledgements_task_actor_uk unique (task_id, actor_id),
  constraint worker_task_acknowledgements_idempotency_key_uk unique (idempotency_key)
);

create trigger worker_task_acknowledgements_set_updated_at
before update on job.worker_task_acknowledgements
for each row
execute function app.set_updated_at();

create index worker_task_acknowledgements_actor_idx
  on job.worker_task_acknowledgements (actor_id, updated_at desc);

create table app.settings_profiles (
  id uuid primary key default gen_random_uuid(),
  settings_key text not null,
  status text not null default 'active',
  version integer not null default 1,
  settings_payload jsonb not null,
  affected_scopes text[] not null default '{}',
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint settings_profiles_status_chk check (status in ('active', 'superseded', 'disabled')),
  constraint settings_profiles_version_chk check (version > 0),
  constraint settings_profiles_payload_chk check (jsonb_typeof(settings_payload) = 'object'),
  constraint settings_profiles_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint settings_profiles_idempotency_key_uk unique (idempotency_key)
);

create trigger settings_profiles_set_updated_at
before update on app.settings_profiles
for each row
execute function app.set_updated_at();

create unique index settings_profiles_active_key_uidx
  on app.settings_profiles (settings_key)
  where status = 'active';

create index settings_profiles_key_version_idx
  on app.settings_profiles (settings_key, version desc);

create table app.project_profiles (
  id uuid primary key default gen_random_uuid(),
  project_code text not null,
  project_name text not null,
  project_status text not null default 'active',
  project_source text not null,
  department_name text,
  owner_name text,
  external_project_id text,
  source_watermark text,
  version integer not null default 1,
  profile_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  deactivated_at timestamptz,
  deactivated_by text,
  constraint project_profiles_status_chk check (project_status in ('active', 'inactive', 'disabled')),
  constraint project_profiles_source_chk check (project_source in ('manual', 'oa_sync', 'migration')),
  constraint project_profiles_version_chk check (version > 0),
  constraint project_profiles_payload_chk check (jsonb_typeof(profile_payload) = 'object'),
  constraint project_profiles_deactivated_at_chk check (
    (project_status in ('inactive', 'disabled') and deactivated_at is not null)
    or project_status = 'active'
  ),
  constraint project_profiles_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger project_profiles_set_updated_at
before update on app.project_profiles
for each row
execute function app.set_updated_at();

create unique index project_profiles_project_code_uidx
  on app.project_profiles (project_code);

create unique index project_profiles_external_project_uidx
  on app.project_profiles (external_project_id)
  where external_project_id is not null;

create unique index project_profiles_idempotency_key_uidx
  on app.project_profiles (idempotency_key)
  where idempotency_key is not null;

create index project_profiles_status_name_idx
  on app.project_profiles (project_status, project_name);

create table app.project_assignments (
  id uuid primary key default gen_random_uuid(),
  object_type text not null,
  object_id uuid not null,
  object_month date,
  project_id uuid not null references app.project_profiles(id),
  status text not null default 'active',
  note text,
  version integer not null default 1,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  cancelled_at timestamptz,
  cancelled_by text,
  constraint project_assignments_object_type_chk check (
    object_type in ('bank_transaction', 'invoice', 'oa_application', 'oa_application_item', 'workbench_row')
  ),
  constraint project_assignments_status_chk check (status in ('active', 'superseded', 'cancelled')),
  constraint project_assignments_version_chk check (version > 0),
  constraint project_assignments_cancelled_at_chk check (
    (status = 'cancelled' and cancelled_at is not null)
    or status <> 'cancelled'
  ),
  constraint project_assignments_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint project_assignments_idempotency_key_uk unique (idempotency_key)
);

create trigger project_assignments_set_updated_at
before update on app.project_assignments
for each row
execute function app.set_updated_at();

create unique index project_assignments_active_object_uidx
  on app.project_assignments (object_type, object_id)
  where status = 'active';

create index project_assignments_project_idx
  on app.project_assignments (project_id, status, updated_at desc);

create table app.project_profile_events (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references app.project_profiles(id) on delete set null,
  assignment_id uuid references app.project_assignments(id) on delete set null,
  event_type text not null,
  before_state jsonb not null default '{}'::jsonb,
  after_state jsonb not null default '{}'::jsonb,
  affected_scopes text[] not null default '{}',
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint project_profile_events_event_type_chk check (
    event_type in ('created', 'updated', 'deactivated', 'assigned', 'assignment_cancelled', 'migrated')
  ),
  constraint project_profile_events_before_state_chk check (jsonb_typeof(before_state) = 'object'),
  constraint project_profile_events_after_state_chk check (jsonb_typeof(after_state) = 'object'),
  constraint project_profile_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger project_profile_events_set_updated_at
before update on app.project_profile_events
for each row
execute function app.set_updated_at();

create unique index project_profile_events_idempotency_key_uidx
  on app.project_profile_events (idempotency_key)
  where idempotency_key is not null;

create index project_profile_events_project_idx
  on app.project_profile_events (project_id, created_at desc)
  where project_id is not null;

create table staging.project_sync_rows (
  id uuid primary key default gen_random_uuid(),
  sync_run_id uuid references app.oa_sync_runs(id) on delete set null,
  external_project_id text not null,
  project_code text,
  project_name text not null,
  department_name text,
  owner_name text,
  source_watermark text,
  normalized_payload jsonb not null,
  raw_payload jsonb not null,
  payload_hash text not null,
  target_project_id uuid references app.project_profiles(id) on delete set null,
  status text not null default 'pending',
  error_code text,
  error_message text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint project_sync_rows_status_chk check (
    status in ('pending', 'normalized', 'applied', 'skipped', 'failed')
  ),
  constraint project_sync_rows_normalized_payload_chk check (jsonb_typeof(normalized_payload) = 'object'),
  constraint project_sync_rows_raw_payload_chk check (jsonb_typeof(raw_payload) = 'object')
);

create trigger project_sync_rows_set_updated_at
before update on staging.project_sync_rows
for each row
execute function app.set_updated_at();

create unique index project_sync_rows_sync_external_uidx
  on staging.project_sync_rows (sync_run_id, external_project_id)
  where sync_run_id is not null;

create index project_sync_rows_status_idx
  on staging.project_sync_rows (status, source_watermark);

create table app.data_reset_requests (
  id uuid primary key default gen_random_uuid(),
  action text not null,
  status text not null default 'requested',
  approval_id text not null,
  backup_evidence_id text not null,
  scope jsonb not null default '{}'::jsonb,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  execution_mode text not null default 'queued',
  requested_by text not null,
  requested_at timestamptz not null default now(),
  approved_at timestamptz,
  completed_at timestamptz,
  failed_at timestamptz,
  failure_code text,
  failure_message text,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint data_reset_requests_action_chk check (
    action in ('reset_bank_transactions', 'reset_invoices', 'reset_oa_and_rebuild')
  ),
  constraint data_reset_requests_status_chk check (
    status in ('requested', 'queued', 'running', 'succeeded', 'failed', 'cancelled', 'blocked')
  ),
  constraint data_reset_requests_execution_mode_chk check (execution_mode in ('queued', 'maintenance_worker')),
  constraint data_reset_requests_scope_chk check (jsonb_typeof(scope) = 'object'),
  constraint data_reset_requests_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint data_reset_requests_idempotency_key_uk unique (idempotency_key)
);

create trigger data_reset_requests_set_updated_at
before update on app.data_reset_requests
for each row
execute function app.set_updated_at();

create index data_reset_requests_status_idx
  on app.data_reset_requests (status, requested_at desc);

create unique index data_reset_requests_running_uidx
  on app.data_reset_requests (action)
  where status in ('queued', 'running');

create table app.ledgers (
  id uuid primary key default gen_random_uuid(),
  ledger_type text not null,
  ledger_key text not null,
  status text not null default 'open',
  counterparty_id text,
  counterparty_name text,
  project_id uuid references app.project_profiles(id) on delete set null,
  source_case_id uuid references app.reconciliation_cases(id) on delete set null,
  source_turnover_relation_id uuid references app.turnover_relations(id) on delete set null,
  opened_at timestamptz not null default now(),
  closed_at timestamptz,
  due_at timestamptz,
  amount numeric(20, 2) not null default 0,
  remaining_amount numeric(20, 2) not null default 0,
  ledger_payload jsonb not null default '{}'::jsonb,
  version integer not null default 1,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint ledgers_type_chk check (
    ledger_type in (
      'payment_collection',
      'invoice_collection',
      'refund',
      'advance_receipt',
      'prepayment',
      'output_invoice_issue',
      'payment_reminder',
      'external_receivable_payable',
      'non_tax_income'
    )
  ),
  constraint ledgers_status_chk check (
    status in ('open', 'in_progress', 'waiting_external_feedback', 'resolved', 'cancelled')
  ),
  constraint ledgers_amount_chk check (amount >= 0 and remaining_amount >= 0),
  constraint ledgers_version_chk check (version > 0),
  constraint ledgers_payload_chk check (jsonb_typeof(ledger_payload) = 'object'),
  constraint ledgers_closed_at_chk check (
    (status in ('resolved', 'cancelled') and closed_at is not null)
    or status not in ('resolved', 'cancelled')
  ),
  constraint ledgers_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger ledgers_set_updated_at
before update on app.ledgers
for each row
execute function app.set_updated_at();

create unique index ledgers_ledger_key_uidx
  on app.ledgers (ledger_key);

create unique index ledgers_idempotency_key_uidx
  on app.ledgers (idempotency_key)
  where idempotency_key is not null;

create index ledgers_status_due_idx
  on app.ledgers (status, due_at, updated_at desc);

create index ledgers_counterparty_idx
  on app.ledgers (counterparty_id, status)
  where counterparty_id is not null;

create table app.ledger_events (
  id uuid primary key default gen_random_uuid(),
  ledger_id uuid not null references app.ledgers(id) on delete cascade,
  event_type text not null,
  previous_status text,
  new_status text,
  event_payload jsonb not null default '{}'::jsonb,
  affected_scopes text[] not null default '{}',
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint ledger_events_event_type_chk check (
    event_type in ('created', 'status_changed', 'amount_changed', 'cancelled', 'migrated')
  ),
  constraint ledger_events_status_chk check (
    previous_status is null
    or previous_status in ('open', 'in_progress', 'waiting_external_feedback', 'resolved', 'cancelled')
  ),
  constraint ledger_events_new_status_chk check (
    new_status is null
    or new_status in ('open', 'in_progress', 'waiting_external_feedback', 'resolved', 'cancelled')
  ),
  constraint ledger_events_payload_chk check (jsonb_typeof(event_payload) = 'object'),
  constraint ledger_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint ledger_events_idempotency_key_uk unique (idempotency_key)
);

create trigger ledger_events_set_updated_at
before update on app.ledger_events
for each row
execute function app.set_updated_at();

create index ledger_events_ledger_idx
  on app.ledger_events (ledger_id, created_at desc);

create table app.reminders (
  id uuid primary key default gen_random_uuid(),
  reminder_type text not null,
  ledger_id uuid references app.ledgers(id) on delete set null,
  source_object_type text,
  source_object_id uuid,
  status text not null default 'pending',
  due_at timestamptz not null,
  recipient_user_id text,
  message_payload jsonb not null default '{}'::jsonb,
  version integer not null default 1,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint reminders_type_chk check (
    reminder_type in ('ledger_due', 'import_follow_up', 'exception_follow_up', 'manual')
  ),
  constraint reminders_status_chk check (status in ('pending', 'sent', 'skipped', 'cancelled')),
  constraint reminders_version_chk check (version > 0),
  constraint reminders_message_payload_chk check (jsonb_typeof(message_payload) = 'object'),
  constraint reminders_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger reminders_set_updated_at
before update on app.reminders
for each row
execute function app.set_updated_at();

create index reminders_status_due_idx
  on app.reminders (status, due_at);

create index reminders_ledger_idx
  on app.reminders (ledger_id)
  where ledger_id is not null;

create table app.reminder_runs (
  id uuid primary key default gen_random_uuid(),
  run_scope jsonb not null,
  status text not null default 'queued',
  as_of date not null,
  days_ahead integer,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  sent_count integer not null default 0,
  failed_count integer not null default 0,
  result_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint reminder_runs_status_chk check (
    status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')
  ),
  constraint reminder_runs_days_ahead_chk check (days_ahead is null or days_ahead >= 0),
  constraint reminder_runs_counts_chk check (sent_count >= 0 and failed_count >= 0),
  constraint reminder_runs_scope_chk check (jsonb_typeof(run_scope) = 'object'),
  constraint reminder_runs_result_payload_chk check (jsonb_typeof(result_payload) = 'object'),
  constraint reminder_runs_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint reminder_runs_idempotency_key_uk unique (idempotency_key)
);

create trigger reminder_runs_set_updated_at
before update on app.reminder_runs
for each row
execute function app.set_updated_at();

create index reminder_runs_status_created_idx
  on app.reminder_runs (status, created_at desc);

create table app.import_preview_sessions (
  id uuid primary key default gen_random_uuid(),
  session_key text not null,
  batch_id uuid references app.import_batches(id) on delete set null,
  file_id uuid references app.import_files(id) on delete set null,
  file_object_id uuid references app.file_objects(id) on delete set null,
  preview_type text not null,
  template_code text,
  status text not null default 'previewed',
  version integer not null default 1,
  row_count integer not null default 0,
  issue_count integer not null default 0,
  source_hash text not null,
  preview_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  confirmed_at timestamptz,
  reverted_at timestamptz,
  constraint import_preview_sessions_type_chk check (
    preview_type in ('json_rows', 'file_object', 'etc', 'tax_certified')
  ),
  constraint import_preview_sessions_status_chk check (
    status in ('previewed', 'confirming', 'confirmed', 'failed', 'cancelled', 'reverted')
  ),
  constraint import_preview_sessions_version_chk check (version > 0),
  constraint import_preview_sessions_counts_chk check (row_count >= 0 and issue_count >= 0),
  constraint import_preview_sessions_payload_chk check (jsonb_typeof(preview_payload) = 'object'),
  constraint import_preview_sessions_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint import_preview_sessions_session_key_uk unique (session_key),
  constraint import_preview_sessions_idempotency_key_uk unique (idempotency_key)
);

create trigger import_preview_sessions_set_updated_at
before update on app.import_preview_sessions
for each row
execute function app.set_updated_at();

create index import_preview_sessions_batch_idx
  on app.import_preview_sessions (batch_id, status)
  where batch_id is not null;

create index import_preview_sessions_file_idx
  on app.import_preview_sessions (file_id, status)
  where file_id is not null;

create table app.import_fact_lineage (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references app.import_batches(id) on delete cascade,
  preview_session_id uuid references app.import_preview_sessions(id) on delete set null,
  source_parse_result_id uuid references staging.import_parse_results(id) on delete set null,
  target_schema text not null,
  target_table text not null,
  target_id uuid not null,
  target_partition_month date,
  target_status text not null default 'active',
  revert_status text not null default 'not_reverted',
  source_hash text,
  target_snapshot jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint import_fact_lineage_target_status_chk check (
    target_status in ('active', 'superseded', 'reverted', 'failed')
  ),
  constraint import_fact_lineage_revert_status_chk check (
    revert_status in ('not_reverted', 'revert_requested', 'reverted', 'partial_failed', 'blocked')
  ),
  constraint import_fact_lineage_target_snapshot_chk check (jsonb_typeof(target_snapshot) = 'object'),
  constraint import_fact_lineage_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger import_fact_lineage_set_updated_at
before update on app.import_fact_lineage
for each row
execute function app.set_updated_at();

create unique index import_fact_lineage_batch_target_uidx
  on app.import_fact_lineage (batch_id, target_schema, target_table, target_id);

create unique index import_fact_lineage_idempotency_key_uidx
  on app.import_fact_lineage (idempotency_key)
  where idempotency_key is not null;

create index import_fact_lineage_target_idx
  on app.import_fact_lineage (target_schema, target_table, target_id);

create table app.import_revert_events (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid not null references app.import_batches(id) on delete cascade,
  preview_session_id uuid references app.import_preview_sessions(id) on delete set null,
  event_type text not null,
  status text not null,
  reason text,
  affected_scopes text[] not null default '{}',
  revert_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint import_revert_events_type_chk check (
    event_type in ('revert_requested', 'reverted', 'partial_failed', 'blocked')
  ),
  constraint import_revert_events_status_chk check (
    status in ('requested', 'running', 'succeeded', 'failed', 'blocked')
  ),
  constraint import_revert_events_payload_chk check (jsonb_typeof(revert_payload) = 'object'),
  constraint import_revert_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint import_revert_events_idempotency_key_uk unique (idempotency_key)
);

create trigger import_revert_events_set_updated_at
before update on app.import_revert_events
for each row
execute function app.set_updated_at();

create index import_revert_events_batch_idx
  on app.import_revert_events (batch_id, created_at desc);

create table app.matching_runs (
  id uuid primary key default gen_random_uuid(),
  scope_month date,
  scope_key text not null,
  status text not null default 'queued',
  reason text,
  source_watermark text,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  result_count integer not null default 0,
  result_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  finished_at timestamptz,
  constraint matching_runs_status_chk check (
    status in ('queued', 'running', 'succeeded', 'failed', 'cancelled')
  ),
  constraint matching_runs_scope_month_chk check (
    scope_month is null
    or scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint matching_runs_result_count_chk check (result_count >= 0),
  constraint matching_runs_result_payload_chk check (jsonb_typeof(result_payload) = 'object'),
  constraint matching_runs_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint matching_runs_idempotency_key_uk unique (idempotency_key)
);

create trigger matching_runs_set_updated_at
before update on app.matching_runs
for each row
execute function app.set_updated_at();

create index matching_runs_scope_status_idx
  on app.matching_runs (scope_month, status, updated_at desc);

alter table read_model.workbench_candidate_matches
  add column matching_run_id uuid references app.matching_runs(id) on delete set null,
  add column detail_payload jsonb not null default '{}'::jsonb;

alter table read_model.workbench_candidate_matches
  add constraint workbench_candidate_matches_detail_payload_chk check (
    jsonb_typeof(detail_payload) = 'object'
  );

create index workbench_candidate_matches_run_idx
  on read_model.workbench_candidate_matches (matching_run_id)
  where matching_run_id is not null;

create table app.turnover_relation_extras (
  id uuid primary key default gen_random_uuid(),
  relation_id uuid not null references app.turnover_relations(id) on delete cascade,
  status text not null default 'active',
  version integer not null default 1,
  extra_payload jsonb not null,
  fifo_payload jsonb not null default '{}'::jsonb,
  allocation_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint turnover_relation_extras_status_chk check (status in ('active', 'superseded', 'cancelled')),
  constraint turnover_relation_extras_version_chk check (version > 0),
  constraint turnover_relation_extras_payload_chk check (jsonb_typeof(extra_payload) = 'object'),
  constraint turnover_relation_extras_fifo_payload_chk check (jsonb_typeof(fifo_payload) = 'object'),
  constraint turnover_relation_extras_allocation_payload_chk check (jsonb_typeof(allocation_payload) = 'object'),
  constraint turnover_relation_extras_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger turnover_relation_extras_set_updated_at
before update on app.turnover_relation_extras
for each row
execute function app.set_updated_at();

create unique index turnover_relation_extras_active_relation_uidx
  on app.turnover_relation_extras (relation_id)
  where status = 'active';

create unique index turnover_relation_extras_idempotency_key_uidx
  on app.turnover_relation_extras (idempotency_key)
  where idempotency_key is not null;

create table app.turnover_relation_events (
  id uuid primary key default gen_random_uuid(),
  relation_id uuid not null references app.turnover_relations(id) on delete cascade,
  extra_id uuid references app.turnover_relation_extras(id) on delete set null,
  event_type text not null,
  previous_status text,
  new_status text,
  event_payload jsonb not null default '{}'::jsonb,
  affected_months date[] not null default '{}',
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint turnover_relation_events_type_chk check (
    event_type in ('confirmed', 'withdrawn', 'extra_updated', 'migrated')
  ),
  constraint turnover_relation_events_status_chk check (
    previous_status is null or previous_status in ('active', 'settled', 'cancelled')
  ),
  constraint turnover_relation_events_new_status_chk check (
    new_status is null or new_status in ('active', 'settled', 'cancelled')
  ),
  constraint turnover_relation_events_payload_chk check (jsonb_typeof(event_payload) = 'object'),
  constraint turnover_relation_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint turnover_relation_events_idempotency_key_uk unique (idempotency_key)
);

create trigger turnover_relation_events_set_updated_at
before update on app.turnover_relation_events
for each row
execute function app.set_updated_at();

create index turnover_relation_events_relation_idx
  on app.turnover_relation_events (relation_id, created_at desc);

alter table app.turnover_relations
  add column row_version integer not null default 1,
  add column idempotency_key text,
  add column updated_by text,
  add column audit_event_id uuid references audit.events(id),
  add column legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null;

alter table app.turnover_relations
  add constraint turnover_relations_row_version_chk check (row_version > 0);

create unique index turnover_relations_idempotency_key_uidx
  on app.turnover_relations (idempotency_key)
  where idempotency_key is not null;

create table app.etc_import_sessions (
  id uuid primary key default gen_random_uuid(),
  preview_session_id uuid references app.import_preview_sessions(id) on delete set null,
  batch_id uuid references app.import_batches(id) on delete set null,
  status text not null default 'previewed',
  template_code text,
  manifest_hash text not null,
  item_count integer not null default 0,
  warning_count integer not null default 0,
  affected_months date[] not null default '{}',
  session_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  confirmed_at timestamptz,
  constraint etc_import_sessions_status_chk check (
    status in ('previewed', 'confirming', 'confirmed', 'failed', 'cancelled')
  ),
  constraint etc_import_sessions_counts_chk check (item_count >= 0 and warning_count >= 0),
  constraint etc_import_sessions_payload_chk check (jsonb_typeof(session_payload) = 'object'),
  constraint etc_import_sessions_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_import_sessions_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_import_sessions_set_updated_at
before update on app.etc_import_sessions
for each row
execute function app.set_updated_at();

create unique index etc_import_sessions_manifest_uidx
  on app.etc_import_sessions (manifest_hash, template_code);

create table app.etc_reconciliation_tasks (
  id uuid primary key default gen_random_uuid(),
  task_key text not null,
  title text not null,
  period_month date,
  status text not null default 'created',
  ready_for_import boolean not null default false,
  unavailable_reason text,
  version integer not null default 1,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  task_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  cancelled_at timestamptz,
  cancelled_by text,
  constraint etc_reconciliation_tasks_period_month_chk check (
    period_month is null
    or period_month = date_trunc('month', period_month::timestamp)::date
  ),
  constraint etc_reconciliation_tasks_status_chk check (
    status in ('created', 'queued', 'running', 'ready_for_import', 'imported', 'failed', 'cancelled')
  ),
  constraint etc_reconciliation_tasks_version_chk check (version > 0),
  constraint etc_reconciliation_tasks_payload_chk check (jsonb_typeof(task_payload) = 'object'),
  constraint etc_reconciliation_tasks_cancelled_at_chk check (
    (status = 'cancelled' and cancelled_at is not null)
    or status <> 'cancelled'
  ),
  constraint etc_reconciliation_tasks_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_reconciliation_tasks_task_key_uk unique (task_key),
  constraint etc_reconciliation_tasks_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_reconciliation_tasks_set_updated_at
before update on app.etc_reconciliation_tasks
for each row
execute function app.set_updated_at();

create index etc_reconciliation_tasks_status_period_idx
  on app.etc_reconciliation_tasks (status, period_month, updated_at desc);

create index etc_reconciliation_tasks_ready_idx
  on app.etc_reconciliation_tasks (ready_for_import, updated_at desc)
  where ready_for_import;

create table app.etc_reconciliation_task_files (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references app.etc_reconciliation_tasks(id) on delete cascade,
  file_object_id uuid not null references app.file_objects(id),
  file_role text not null,
  status text not null default 'attached',
  artifact_type text,
  source_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_reconciliation_task_files_role_chk check (
    file_role in ('ticket_text', 'ticket_file', 'credit_card_statement', 'evidence', 'source_zip', 'other')
  ),
  constraint etc_reconciliation_task_files_status_chk check (
    status in ('attached', 'parsed', 'failed', 'removed')
  ),
  constraint etc_reconciliation_task_files_payload_chk check (jsonb_typeof(source_payload) = 'object'),
  constraint etc_reconciliation_task_files_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger etc_reconciliation_task_files_set_updated_at
before update on app.etc_reconciliation_task_files
for each row
execute function app.set_updated_at();

create unique index etc_reconciliation_task_files_role_uidx
  on app.etc_reconciliation_task_files (task_id, file_object_id, file_role);

create unique index etc_reconciliation_task_files_idempotency_key_uidx
  on app.etc_reconciliation_task_files (idempotency_key)
  where idempotency_key is not null;

create table app.etc_reconciliation_task_items (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references app.etc_reconciliation_tasks(id) on delete cascade,
  item_key text not null,
  item_type text not null,
  status text not null default 'open',
  invoice_month date,
  invoice_id uuid,
  amount numeric(20, 2),
  item_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_reconciliation_task_items_type_chk check (
    item_type in ('ticket', 'invoice', 'statement_line', 'match_candidate', 'evidence')
  ),
  constraint etc_reconciliation_task_items_status_chk check (
    status in ('open', 'matched', 'ignored', 'resolved', 'removed')
  ),
  constraint etc_reconciliation_task_items_amount_chk check (amount is null or amount >= 0),
  constraint etc_reconciliation_task_items_payload_chk check (jsonb_typeof(item_payload) = 'object'),
  constraint etc_reconciliation_task_items_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger etc_reconciliation_task_items_set_updated_at
before update on app.etc_reconciliation_task_items
for each row
execute function app.set_updated_at();

create unique index etc_reconciliation_task_items_key_uidx
  on app.etc_reconciliation_task_items (task_id, item_key);

create unique index etc_reconciliation_task_items_idempotency_key_uidx
  on app.etc_reconciliation_task_items (idempotency_key)
  where idempotency_key is not null;

create index etc_reconciliation_task_items_status_idx
  on app.etc_reconciliation_task_items (task_id, status, item_type);

create table app.etc_reconciliation_task_evidences (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references app.etc_reconciliation_tasks(id) on delete cascade,
  item_id uuid references app.etc_reconciliation_task_items(id) on delete set null,
  file_object_id uuid references app.file_objects(id) on delete set null,
  evidence_type text not null,
  status text not null default 'active',
  evidence_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_reconciliation_task_evidences_type_chk check (
    evidence_type in ('text', 'file', 'manual_note', 'system_match')
  ),
  constraint etc_reconciliation_task_evidences_status_chk check (
    status in ('active', 'removed', 'superseded')
  ),
  constraint etc_reconciliation_task_evidences_payload_chk check (
    jsonb_typeof(evidence_payload) = 'object'
  ),
  constraint etc_reconciliation_task_evidences_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger etc_reconciliation_task_evidences_set_updated_at
before update on app.etc_reconciliation_task_evidences
for each row
execute function app.set_updated_at();

create unique index etc_reconciliation_task_evidences_idempotency_key_uidx
  on app.etc_reconciliation_task_evidences (idempotency_key)
  where idempotency_key is not null;

create index etc_reconciliation_task_evidences_task_idx
  on app.etc_reconciliation_task_evidences (task_id, status, created_at desc);

create table app.etc_reconciliation_task_events (
  id uuid primary key default gen_random_uuid(),
  task_id uuid not null references app.etc_reconciliation_tasks(id) on delete cascade,
  item_id uuid references app.etc_reconciliation_task_items(id) on delete set null,
  file_id uuid references app.etc_reconciliation_task_files(id) on delete set null,
  evidence_id uuid references app.etc_reconciliation_task_evidences(id) on delete set null,
  event_type text not null,
  previous_status text,
  new_status text,
  event_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_reconciliation_task_events_type_chk check (
    event_type in ('created', 'cancelled', 'artifact_changed', 'item_changed', 'refresh_requested', 'imported', 'migrated')
  ),
  constraint etc_reconciliation_task_events_payload_chk check (jsonb_typeof(event_payload) = 'object'),
  constraint etc_reconciliation_task_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_reconciliation_task_events_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_reconciliation_task_events_set_updated_at
before update on app.etc_reconciliation_task_events
for each row
execute function app.set_updated_at();

create index etc_reconciliation_task_events_task_idx
  on app.etc_reconciliation_task_events (task_id, created_at desc);

create table app.etc_oa_drafts (
  id uuid primary key default gen_random_uuid(),
  batch_scope text not null,
  batch_id text,
  status text not null default 'queued',
  source_watermark text,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  outbox_event_id uuid references job.outbox_events(id) on delete set null,
  selected_invoice_ids uuid[] not null default '{}',
  draft_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  submitted_at timestamptz,
  failed_at timestamptz,
  failure_code text,
  constraint etc_oa_drafts_status_chk check (
    status in ('queued', 'running', 'submitted', 'failed', 'cancelled')
  ),
  constraint etc_oa_drafts_payload_chk check (jsonb_typeof(draft_payload) = 'object'),
  constraint etc_oa_drafts_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_oa_drafts_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_oa_drafts_set_updated_at
before update on app.etc_oa_drafts
for each row
execute function app.set_updated_at();

create index etc_oa_drafts_status_idx
  on app.etc_oa_drafts (status, updated_at desc);

create table app.etc_batch_events (
  id uuid primary key default gen_random_uuid(),
  batch_id text not null,
  event_type text not null,
  previous_status text,
  new_status text,
  invoice_ids uuid[] not null default '{}',
  event_payload jsonb not null default '{}'::jsonb,
  affected_months date[] not null default '{}',
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_batch_events_type_chk check (
    event_type in ('draft_requested', 'submitted_confirmed', 'submission_reverted', 'cancelled', 'migrated')
  ),
  constraint etc_batch_events_payload_chk check (jsonb_typeof(event_payload) = 'object'),
  constraint etc_batch_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_batch_events_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_batch_events_set_updated_at
before update on app.etc_batch_events
for each row
execute function app.set_updated_at();

create index etc_batch_events_batch_idx
  on app.etc_batch_events (batch_id, created_at desc);

create table app.etc_invoice_submission_events (
  id uuid primary key default gen_random_uuid(),
  invoice_month date not null,
  invoice_id uuid not null,
  batch_id text,
  event_type text not null,
  previous_status text,
  new_status text,
  reason text,
  event_payload jsonb not null default '{}'::jsonb,
  affected_months date[] not null default '{}',
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint etc_invoice_submission_events_type_chk check (
    event_type in ('submitted_confirmed', 'submission_revoked', 'batch_cancelled', 'migrated')
  ),
  constraint etc_invoice_submission_events_payload_chk check (jsonb_typeof(event_payload) = 'object'),
  constraint etc_invoice_submission_events_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint etc_invoice_submission_events_idempotency_key_uk unique (idempotency_key)
);

create trigger etc_invoice_submission_events_set_updated_at
before update on app.etc_invoice_submission_events
for each row
execute function app.set_updated_at();

create index etc_invoice_submission_events_invoice_idx
  on app.etc_invoice_submission_events (invoice_month, invoice_id, created_at desc);

create index etc_invoice_submission_events_batch_idx
  on app.etc_invoice_submission_events (batch_id, created_at desc)
  where batch_id is not null;

create table app.tax_certified_import_sessions (
  id uuid primary key default gen_random_uuid(),
  preview_session_id uuid references app.import_preview_sessions(id) on delete set null,
  batch_id uuid references app.import_batches(id) on delete set null,
  file_object_id uuid references app.file_objects(id) on delete set null,
  scope_month date not null,
  status text not null default 'previewed',
  row_count integer not null default 0,
  recognized_count integer not null default 0,
  invalid_count integer not null default 0,
  matched_count integer not null default 0,
  outside_count integer not null default 0,
  session_payload jsonb not null default '{}'::jsonb,
  idempotency_key text not null,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  confirmed_at timestamptz,
  constraint tax_certified_import_sessions_scope_month_chk check (
    scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint tax_certified_import_sessions_status_chk check (
    status in ('previewed', 'confirming', 'confirmed', 'failed', 'cancelled')
  ),
  constraint tax_certified_import_sessions_counts_chk check (
    row_count >= 0
    and recognized_count >= 0
    and invalid_count >= 0
    and matched_count >= 0
    and outside_count >= 0
  ),
  constraint tax_certified_import_sessions_payload_chk check (jsonb_typeof(session_payload) = 'object'),
  constraint tax_certified_import_sessions_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  ),
  constraint tax_certified_import_sessions_idempotency_key_uk unique (idempotency_key)
);

create trigger tax_certified_import_sessions_set_updated_at
before update on app.tax_certified_import_sessions
for each row
execute function app.set_updated_at();

create index tax_certified_import_sessions_scope_status_idx
  on app.tax_certified_import_sessions (scope_month, status, updated_at desc);

create table app.export_artifacts (
  id uuid primary key default gen_random_uuid(),
  export_type text not null,
  status text not null default 'ready',
  scope_key text not null,
  query_hash text not null,
  file_object_id uuid references app.file_objects(id) on delete set null,
  worker_task_id uuid references job.worker_tasks(id) on delete set null,
  content_type text not null,
  content_disposition text not null,
  byte_size bigint,
  checksum_sha256 text,
  expires_at timestamptz,
  access_policy jsonb not null default '{}'::jsonb,
  artifact_payload jsonb not null default '{}'::jsonb,
  idempotency_key text,
  audit_event_id uuid references audit.events(id),
  legacy_id_map_id uuid references staging.legacy_id_map(id) on delete set null,
  legacy_collection text,
  legacy_id text,
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint export_artifacts_type_chk check (
    export_type in ('turnover_ledger_xlsx', 'cost_statistics_xlsx', 'import_batch_archive')
  ),
  constraint export_artifacts_status_chk check (
    status in ('queued', 'running', 'ready', 'failed', 'expired', 'cancelled')
  ),
  constraint export_artifacts_byte_size_chk check (byte_size is null or byte_size >= 0),
  constraint export_artifacts_checksum_chk check (
    checksum_sha256 is null or checksum_sha256 ~ '^[0-9a-f]{64}$'
  ),
  constraint export_artifacts_access_policy_chk check (jsonb_typeof(access_policy) = 'object'),
  constraint export_artifacts_payload_chk check (jsonb_typeof(artifact_payload) = 'object'),
  constraint export_artifacts_legacy_pair_chk check (
    (legacy_collection is null and legacy_id is null)
    or (legacy_collection is not null and legacy_id is not null)
  )
);

create trigger export_artifacts_set_updated_at
before update on app.export_artifacts
for each row
execute function app.set_updated_at();

create unique index export_artifacts_scope_query_uidx
  on app.export_artifacts (export_type, scope_key, query_hash)
  where status in ('queued', 'running', 'ready');

create unique index export_artifacts_idempotency_key_uidx
  on app.export_artifacts (idempotency_key)
  where idempotency_key is not null;

create index export_artifacts_status_idx
  on app.export_artifacts (status, updated_at desc);

create table staging.p0_api_fact_source_backfill_plan (
  id uuid primary key default gen_random_uuid(),
  route_no integer not null,
  method_path text not null,
  source_system text not null,
  legacy_collection text,
  target_schema text not null,
  target_table text not null,
  migration_phase text not null default 'planned',
  backfill_order integer not null,
  required_legacy_id_map boolean not null default true,
  checksum_strategy text not null,
  row_count_query text,
  blocker text,
  plan_payload jsonb not null default '{}'::jsonb,
  audit_event_id uuid references audit.events(id),
  created_by text not null,
  created_at timestamptz not null default now(),
  updated_by text,
  updated_at timestamptz not null default now(),
  constraint p0_api_fact_source_backfill_plan_route_no_chk check (route_no between 1 and 50),
  constraint p0_api_fact_source_backfill_plan_phase_chk check (
    migration_phase in ('planned', 'backfill_ready', 'backfilled', 'verified', 'blocked')
  ),
  constraint p0_api_fact_source_backfill_plan_order_chk check (backfill_order > 0),
  constraint p0_api_fact_source_backfill_plan_payload_chk check (jsonb_typeof(plan_payload) = 'object')
);

create trigger p0_api_fact_source_backfill_plan_set_updated_at
before update on staging.p0_api_fact_source_backfill_plan
for each row
execute function app.set_updated_at();

create unique index p0_api_fact_source_backfill_plan_route_target_uidx
  on staging.p0_api_fact_source_backfill_plan (route_no, target_schema, target_table);

create index p0_api_fact_source_backfill_plan_phase_idx
  on staging.p0_api_fact_source_backfill_plan (migration_phase, backfill_order);

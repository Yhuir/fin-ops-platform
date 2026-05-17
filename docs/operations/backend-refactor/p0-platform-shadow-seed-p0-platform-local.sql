-- P0 platform runtime shadow seed facts.
-- Safe only for disposable local/staging shadow databases.
begin;

-- Clean runtime side effects for this SHADOW_RUN_ID before reseeding.
-- All predicates are restricted to deterministic shadow IDs, run_id payloads, or platform-shadow idempotency keys.
delete from job.worker_task_acknowledgements
where task_id = 'ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or trace_id = 'platform-shadow:p0-platform-local'
   or source_metadata->>'run_id' = 'p0-platform-local';

delete from app.ledger_events
where ledger_id = '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or event_payload->>'run_id' = 'p0-platform-local';

delete from app.reminder_runs
where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or run_scope->>'run_id' = 'p0-platform-local'
   or result_payload->>'run_id' = 'p0-platform-local';

delete from app.project_profile_events
where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or before_state->>'run_id' = 'p0-platform-local'
   or after_state->>'run_id' = 'p0-platform-local'
   or project_id in ('fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid, '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid)
   or created_by in ('test', '63');

delete from app.project_assignments
where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or object_id in ('210895bd-e515-5488-bae8-1815b291a72f'::uuid, '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid)
   or project_id in ('fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid, '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid)
   or created_by in ('test', '63');

delete from app.data_reset_requests
where id in ('ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid)
   or worker_task_id in ('ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid)
   or outbox_event_id in ('45f9d274-d9dc-571a-8bb1-6793e144f072'::uuid)
   or audit_event_id in ('a79c7d79-e79d-5101-a322-a82178205dd7'::uuid)
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or scope->>'run_id' = 'p0-platform-local';

delete from job.outbox_events
where id in (
  select outbox_event_id
  from app.identity_provisioning_requests
  where outbox_event_id is not null
    and settings_profile_id in (
      select id
      from app.settings_profiles
      where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
         or idempotency_key like 'platform-shadow:p0-platform-local:%'
         or idempotency_key like 'shadow-%p0-platform-local%'
         or settings_payload->>'run_id' = 'p0-platform-local'
    )
);

delete from job.worker_tasks
where id in (
  select worker_task_id
  from app.identity_provisioning_requests
  where worker_task_id is not null
    and settings_profile_id in (
      select id
      from app.settings_profiles
      where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
         or idempotency_key like 'platform-shadow:p0-platform-local:%'
         or idempotency_key like 'shadow-%p0-platform-local%'
         or settings_payload->>'run_id' = 'p0-platform-local'
    )
);

delete from app.identity_provisioning_requests
where settings_profile_id in (
  select id
  from app.settings_profiles
  where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
     or idempotency_key like 'platform-shadow:p0-platform-local:%'
     or idempotency_key like 'shadow-%p0-platform-local%'
     or settings_payload->>'run_id' = 'p0-platform-local'
);

delete from app.write_idempotency_records
where idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or request_payload->>'run_id' = 'p0-platform-local'
   or response_payload->>'run_id' = 'p0-platform-local'
   or aggregate_id in (
     'ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid,
     '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid,
     'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid
   );

delete from job.outbox_events
where id in ('45f9d274-d9dc-571a-8bb1-6793e144f072'::uuid)
   or aggregate_id in ('ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid)
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'outbox:platform-shadow:p0-platform-local:%'
   or idempotency_key like '%shadow-%p0-platform-local%'
   or trace_id = 'platform-shadow:p0-platform-local'
   or payload->>'run_id' = 'p0-platform-local';

delete from job.worker_tasks
where id in ('ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid, 'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid)
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or source->>'run_id' = 'p0-platform-local'
   or payload->>'run_id' = 'p0-platform-local'
   or result_summary->>'run_id' = 'p0-platform-local';

delete from app.settings_profiles
where id <> '26232b50-9e6b-599b-939e-e96de970a6ea'::uuid
  and (
    idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
    or idempotency_key like 'platform-shadow:p0-platform-local:%'
    or idempotency_key like 'shadow-%p0-platform-local%'
    or settings_payload->>'run_id' = 'p0-platform-local'
  );

delete from app.project_profiles
where id not in ('fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid, '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid)
  and (
    idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
    or idempotency_key like 'platform-shadow:p0-platform-local:%'
    or idempotency_key like 'shadow-%p0-platform-local%'
    or project_code in ('SHADOW-p0-platform-local', 'SHADOW-HUB-p0-platform-local', 'SHADOW-P0-PLATFORM-LOCAL', 'SHADOW-HUB-P0-PLATFORM-LOCAL')
    or external_project_id in (
      'shadow-main-P0-PLATFORM-LOCAL',
      'shadow-delete-P0-PLATFORM-LOCAL'
    )
    or profile_payload->>'run_id' = 'p0-platform-local'
  );

delete from audit.events
where id in ('a79c7d79-e79d-5101-a322-a82178205dd7'::uuid)
   or trace_id = 'platform-shadow:p0-platform-local'
   or request_id = 'platform-shadow:p0-platform-local'
   or idempotency_key in ('shadow-background-job-ack-p0-platform-local', 'shadow-settings-save-p0-platform-local', 'shadow-project-sync-p0-platform-local', 'shadow-settings-project-p0-platform-local', 'shadow-settings-project-delete-p0-platform-local', 'shadow-data-reset-p0-platform-local', 'shadow-data-reset-direct-p0-platform-local', 'shadow-project-create-p0-platform-local', 'shadow-project-assign-p0-platform-local', 'shadow-ledger-status-p0-platform-local', 'shadow-reminder-run-p0-platform-local')
   or idempotency_key like 'platform-shadow:p0-platform-local:%'
   or idempotency_key like 'shadow-%p0-platform-local%'
   or metadata->>'run_id' = 'p0-platform-local'
   or after_state->>'run_id' = 'p0-platform-local';

select app.create_financial_fact_month_partition('app.bank_transactions'::regclass, date '2026-05-01');

insert into job.worker_tasks (
  id, task_type, status, phase, priority, idempotency_key, visibility, label,
  source, payload, result_summary, affected_scopes, created_by, total_count, current_count, percent,
  error_summary, retryable, available_at, created_at, started_at, updated_at, finished_at
)
values (
  'ad1d1132-89ff-5198-a096-f45ad3573ed1'::uuid,
  'platform_shadow_background_job',
  'failed',
  'failed',
  0,
  'platform-shadow:p0-platform-local:background-job',
  'system',
  'Platform shadow background job',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local'),
  jsonb_build_object('run_id', 'p0-platform-local', 'message', 'Platform shadow attention job ready for acknowledge.'),
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local'),
  array['platform_shadow'],
  '63',
  1,
  1,
  100,
  'platform_shadow_ack_fixture',
  false,
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  status = excluded.status,
  phase = excluded.phase,
  visibility = excluded.visibility,
  label = excluded.label,
  source = excluded.source,
  payload = excluded.payload,
  result_summary = excluded.result_summary,
  affected_scopes = excluded.affected_scopes,
  total_count = excluded.total_count,
  current_count = excluded.current_count,
  percent = excluded.percent,
  error_summary = excluded.error_summary,
  retryable = excluded.retryable,
  available_at = excluded.available_at,
  started_at = excluded.started_at,
  updated_at = excluded.updated_at,
  finished_at = excluded.finished_at;

insert into app.settings_profiles (
  id, settings_key, status, version, settings_payload, affected_scopes,
  idempotency_key, created_by, created_at, updated_by, updated_at
)
values (
  '26232b50-9e6b-599b-939e-e96de970a6ea'::uuid,
  'platform_shadow_seed:P0-PLATFORM-LOCAL',
  'disabled',
  1,
  jsonb_build_object(
    'completed_project_ids', '[]'::jsonb,
    'manual_projects', '[]'::jsonb,
    'synced_projects', '[]'::jsonb,
    'bank_account_mappings', '[]'::jsonb,
    'allowed_usernames', jsonb_build_array('test'),
    'readonly_export_usernames', '[]'::jsonb,
    'admin_usernames', jsonb_build_array('test'),
    'workbench_column_layouts', '{}'::jsonb,
    'oa_retention', '{}'::jsonb,
    'oa_import', '{}'::jsonb,
    'oa_invoice_offset', '{}'::jsonb,
    'fixture', 'platform_shadow',
    'run_id', 'p0-platform-local'
  ),
  array['platform_shadow'],
  'platform-shadow:p0-platform-local:settings-profile',
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  status = excluded.status,
  version = excluded.version,
  settings_payload = excluded.settings_payload,
  affected_scopes = excluded.affected_scopes,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.project_profiles (
  id, project_code, project_name, project_status, project_source,
  department_name, owner_name, external_project_id, profile_payload,
  idempotency_key, created_by, created_at, updated_by, updated_at
)
values
  (
    'fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid,
    'SHADOW-P0-PLATFORM-LOCAL-MAIN',
    '平台 Shadow 项目',
    'active',
    'manual',
    '平台 Shadow',
    'Shadow Owner',
    'shadow-main-P0-PLATFORM-LOCAL',
    jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'purpose', 'project_detail_and_assignment'),
    'platform-shadow:p0-platform-local:project-main',
    'test',
    timestamptz '2026-05-17 09:00:00+08',
    'test',
    timestamptz '2026-05-17 09:00:00+08'
  ),
  (
    '35d0adce-fb9b-5b11-ae5b-78e4ecf90262'::uuid,
    'SHADOW-P0-PLATFORM-LOCAL-DELETE',
    '平台 Shadow 待删除项目',
    'active',
    'manual',
    '平台 Shadow',
    'Shadow Owner',
    'shadow-delete-P0-PLATFORM-LOCAL',
    jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'purpose', 'project_delete'),
    'platform-shadow:p0-platform-local:project-delete',
    'test',
    timestamptz '2026-05-17 09:00:00+08',
    'test',
    timestamptz '2026-05-17 09:00:00+08'
  )
on conflict (id) do update set
  project_status = 'active',
  project_name = excluded.project_name,
  version = 1,
  department_name = excluded.department_name,
  owner_name = excluded.owner_name,
  profile_payload = excluded.profile_payload,
  deactivated_at = null,
  deactivated_by = null,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.bank_transactions (
  id, txn_date, txn_month, trade_time, pay_receive_time, account_no, account_name,
  txn_direction, amount, signed_amount, written_off_amount, balance, currency,
  counterparty_name_raw, counterparty_name_normalized, counterparty_account_no,
  counterparty_bank_name, bank_serial_no, enterprise_serial_no, source_unique_key,
  data_fingerprint, status, summary, remark, bank_text_fields, raw_payload,
  created_by, created_at, updated_by, updated_at
)
values (
  '210895bd-e515-5488-bae8-1815b291a72f'::uuid,
  date '2026-05-17',
  date '2026-05-01',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  '6222000000000000001',
  '平台 Shadow 账户',
  'inflow',
  1288.00,
  1288.00,
  0.00,
  1288.00,
  'CNY',
  '平台 Shadow 往来单位',
  '平台 Shadow 往来单位',
  '6222999900000000',
  '测试银行',
  'SHADOW-P0-PLATFORM-LOCAL-BANK',
  'SHADOW-ENT-P0-PLATFORM-LOCAL',
  'platform-shadow:p0-platform-local:bank-transaction',
  'platform-shadow:p0-platform-local:bank-transaction',
  'pending',
  '平台 shadow project assignment seed',
  'platform shadow',
  '[]'::jsonb,
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local'),
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (txn_month, id) do update set
  status = 'pending',
  project_id = null,
  summary = excluded.summary,
  raw_payload = excluded.raw_payload,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.ledgers (
  id, ledger_type, ledger_key, status, counterparty_id, counterparty_name, project_id, due_at,
  amount, remaining_amount, ledger_payload, idempotency_key, created_by, created_at, updated_by, updated_at
)
values (
  '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid,
  'payment_collection',
  '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91',
  'open',
  'platform-shadow-counterparty',
  '平台 Shadow 往来方',
  'fce10a80-61e0-520c-88dc-57f34e5afaf0'::uuid,
  timestamptz '2026-05-17 18:00:00+08',
  128.00,
  128.00,
  jsonb_build_object(
    'fixture', 'platform_shadow',
    'run_id', 'p0-platform-local',
    'source_object_type', 'bank_transaction',
    'source_object_id', '210895bd-e515-5488-bae8-1815b291a72f',
    'owner_id', '63',
    'latest_note', '平台 Shadow 台账'
  ),
  'platform-shadow:p0-platform-local:ledger',
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  status = 'open',
  counterparty_id = excluded.counterparty_id,
  counterparty_name = excluded.counterparty_name,
  project_id = excluded.project_id,
  due_at = excluded.due_at,
  amount = excluded.amount,
  remaining_amount = excluded.remaining_amount,
  ledger_payload = excluded.ledger_payload,
  closed_at = null,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.reminders (
  id, reminder_type, ledger_id, status, due_at, recipient_user_id,
  message_payload, created_by, created_at, updated_by, updated_at
)
values (
  '442936df-7f55-59cc-b36f-58e37e53025a'::uuid,
  'ledger_due',
  '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91'::uuid,
  'pending',
  timestamptz '2026-05-17 18:00:00+08',
  '63',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'ledger_id', '29c2554f-c6a3-5b69-9fb1-bf0cd431ec91', 'channel', 'in_app'),
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  ledger_id = excluded.ledger_id,
  status = 'pending',
  due_at = excluded.due_at,
  message_payload = excluded.message_payload,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into job.worker_tasks (
  id, task_type, status, phase, priority, idempotency_key, visibility, label,
  source, payload, result_summary, affected_scopes, created_by, total_count, current_count, percent,
  available_at, created_at, started_at, updated_at, finished_at
)
values (
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  'settings_data_reset',
  'succeeded',
  'succeeded',
  0,
  'platform-shadow:p0-platform-local:data-reset-support:task',
  'system',
  'Platform shadow data reset support job',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('schema_version', 'finops.platform_legacy.data_reset_request.v1', 'run_id', 'p0-platform-local', 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('fixture', 'platform_shadow', 'status', 'succeeded'),
  array['platform_shadow'],
  'test',
  1,
  1,
  100,
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  status = excluded.status,
  phase = excluded.phase,
  visibility = excluded.visibility,
  label = excluded.label,
  source = excluded.source,
  payload = excluded.payload,
  result_summary = excluded.result_summary,
  affected_scopes = excluded.affected_scopes,
  total_count = excluded.total_count,
  current_count = excluded.current_count,
  percent = excluded.percent,
  finished_at = excluded.finished_at,
  updated_at = excluded.updated_at;

insert into job.outbox_events (
  id, aggregate_type, aggregate_id, event_type, subject, payload, status,
  idempotency_key, trace_id, available_at, published_at, created_at, updated_at
)
values (
  '45f9d274-d9dc-571a-8bb1-6793e144f072'::uuid,
  'data_reset_request',
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  'data_reset.request.requested',
  'finops.jobs.settings.data_reset',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'action', 'reset_oa_and_rebuild'),
  'published',
  'outbox:platform-shadow:p0-platform-local:data-reset-support',
  'platform-shadow:p0-platform-local',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  payload = excluded.payload,
  status = excluded.status,
  trace_id = excluded.trace_id,
  published_at = excluded.published_at,
  updated_at = excluded.updated_at;

insert into audit.events (
  id, event_type, action, entity_type, entity_id, actor_id, actor_type, trace_id,
  request_id, idempotency_key, after_state, metadata, created_at
)
values (
  'a79c7d79-e79d-5101-a322-a82178205dd7'::uuid,
  'data_reset.request.requested',
  'seed',
  'data_reset_request',
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  'test',
  'system',
  'platform-shadow:p0-platform-local',
  'platform-shadow:p0-platform-local',
  'platform-shadow:p0-platform-local:data-reset-support',
  jsonb_build_object('task_id', 'ac58279c-9284-5bbb-a457-1a91c1d35dc2', 'outbox_event_id', '45f9d274-d9dc-571a-8bb1-6793e144f072', 'status', 'succeeded'),
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local'),
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  after_state = excluded.after_state,
  metadata = excluded.metadata;

insert into app.data_reset_requests (
  id, worker_task_id, outbox_event_id, action, status, scope, approval_id,
  backup_evidence_id, requested_by, requested_at, approved_at, completed_at,
  execution_mode, idempotency_key, audit_event_id, created_by, created_at, updated_by, updated_at
)
values (
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  '45f9d274-d9dc-571a-8bb1-6793e144f072'::uuid,
  'reset_oa_and_rebuild',
  'succeeded',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local'),
  'shadow-seed-approval-P0-PLATFORM-LOCAL',
  'shadow-seed-backup-P0-PLATFORM-LOCAL',
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  timestamptz '2026-05-17 09:00:00+08',
  'queued',
  'platform-shadow:p0-platform-local:data-reset-support',
  'a79c7d79-e79d-5101-a322-a82178205dd7'::uuid,
  'test',
  timestamptz '2026-05-17 09:00:00+08',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (id) do update set
  status = excluded.status,
  scope = excluded.scope,
  completed_at = excluded.completed_at,
  outbox_event_id = excluded.outbox_event_id,
  audit_event_id = excluded.audit_event_id,
  updated_by = excluded.updated_by,
  updated_at = excluded.updated_at;

insert into app.write_idempotency_records (
  operation, idempotency_key, request_payload, response_payload, aggregate_type,
  aggregate_id, status, created_by, created_at
)
values (
  'data_reset.request',
  'platform-shadow:p0-platform-local:data-reset-support',
  jsonb_build_object('fixture', 'platform_shadow', 'run_id', 'p0-platform-local', 'action', 'reset_oa_and_rebuild'),
  jsonb_build_object('task_id', 'ac58279c-9284-5bbb-a457-1a91c1d35dc2', 'outbox_event_id', '45f9d274-d9dc-571a-8bb1-6793e144f072', 'status', 'succeeded'),
  'data_reset_request',
  'ac58279c-9284-5bbb-a457-1a91c1d35dc2'::uuid,
  'completed',
  'test',
  timestamptz '2026-05-17 09:00:00+08'
)
on conflict (operation, idempotency_key) do update set
  request_payload = excluded.request_payload,
  response_payload = excluded.response_payload,
  status = excluded.status,
  created_by = excluded.created_by;

commit;

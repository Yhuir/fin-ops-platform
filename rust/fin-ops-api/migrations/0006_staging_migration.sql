create extension if not exists pgcrypto;

create schema if not exists staging;

create table staging.mongo_export_manifest (
  id uuid primary key default gen_random_uuid(),
  source_database text not null,
  export_name text not null,
  exported_at timestamptz not null,
  collection_count integer not null,
  document_count bigint not null,
  sha256_manifest text not null,
  storage_uri text not null,
  created_by text not null,
  created_at timestamptz not null default now(),
  constraint mongo_export_manifest_collection_count_chk check (collection_count >= 0),
  constraint mongo_export_manifest_document_count_chk check (document_count >= 0)
);

create unique index mongo_export_manifest_export_name_uidx
  on staging.mongo_export_manifest (source_database, export_name);

create index mongo_export_manifest_exported_at_idx
  on staging.mongo_export_manifest (exported_at desc);

create table staging.mongo_import_rows (
  id uuid primary key default gen_random_uuid(),
  manifest_id uuid not null references staging.mongo_export_manifest(id) on delete cascade,
  legacy_collection text not null,
  legacy_id text not null,
  row_no bigint not null,
  payload jsonb not null,
  payload_hash text not null,
  target_table text,
  target_id uuid,
  status text not null default 'pending',
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  constraint mongo_import_rows_row_no_chk check (row_no > 0),
  constraint mongo_import_rows_status_chk check (
    status in ('pending', 'parsed', 'imported', 'skipped', 'failed')
  )
);

create unique index mongo_import_rows_legacy_uidx
  on staging.mongo_import_rows (manifest_id, legacy_collection, legacy_id);

create unique index mongo_import_rows_row_no_uidx
  on staging.mongo_import_rows (manifest_id, legacy_collection, row_no);

create index mongo_import_rows_status_idx
  on staging.mongo_import_rows (manifest_id, status, legacy_collection);

create index mongo_import_rows_target_idx
  on staging.mongo_import_rows (target_table, target_id)
  where target_table is not null and target_id is not null;

create table staging.legacy_id_map (
  id uuid primary key default gen_random_uuid(),
  source_system text not null,
  legacy_collection text not null,
  legacy_id text not null,
  target_schema text not null,
  target_table text not null,
  target_id uuid not null,
  target_partition_month date,
  payload_hash text,
  migration_run_id uuid,
  created_at timestamptz not null default now()
);

create unique index legacy_id_map_source_target_uidx
  on staging.legacy_id_map (
    source_system,
    legacy_collection,
    legacy_id,
    target_schema,
    target_table
  );

create index legacy_id_map_target_idx
  on staging.legacy_id_map (target_schema, target_table, target_id);

create index legacy_id_map_migration_run_idx
  on staging.legacy_id_map (migration_run_id)
  where migration_run_id is not null;

create table staging.import_parse_results (
  id uuid primary key default gen_random_uuid(),
  batch_id uuid references app.import_batches(id) on delete cascade,
  file_id uuid references app.import_files(id) on delete cascade,
  row_no integer not null,
  source_record_type text not null,
  source_unique_key text,
  data_fingerprint text,
  decision text not null,
  decision_reason text,
  linked_object_type text,
  linked_object_id uuid,
  identity_kind text,
  account_no text,
  trade_time timestamptz,
  direction text,
  amount numeric(20, 2),
  counterparty_name text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  constraint import_parse_results_row_no_chk check (row_no > 0),
  constraint import_parse_results_amount_chk check (amount is null or amount >= 0),
  constraint import_parse_results_decision_chk check (
    decision in (
      'new',
      'duplicate',
      'suspected_duplicate',
      'update_existing',
      'skip',
      'error'
    )
  ),
  constraint import_parse_results_direction_chk check (
    direction is null or direction in ('inflow', 'outflow')
  )
);

create unique index import_parse_results_file_row_uidx
  on staging.import_parse_results (file_id, row_no)
  where file_id is not null;

create unique index import_parse_results_source_key_uidx
  on staging.import_parse_results (batch_id, source_record_type, source_unique_key)
  where batch_id is not null and source_unique_key is not null;

create index import_parse_results_batch_decision_idx
  on staging.import_parse_results (batch_id, decision, row_no)
  where batch_id is not null;

create index import_parse_results_fingerprint_idx
  on staging.import_parse_results (data_fingerprint)
  where data_fingerprint is not null;

create table staging.import_parse_issues (
  id uuid primary key default gen_random_uuid(),
  parse_result_id uuid references staging.import_parse_results(id) on delete cascade,
  severity text not null,
  code text not null,
  message text not null,
  field_name text,
  raw_value text,
  created_at timestamptz not null default now(),
  constraint import_parse_issues_severity_chk check (
    severity in ('info', 'warning', 'error')
  )
);

create index import_parse_issues_result_idx
  on staging.import_parse_issues (parse_result_id, severity, code)
  where parse_result_id is not null;

create index import_parse_issues_code_idx
  on staging.import_parse_issues (severity, code, created_at desc);

create table staging.oa_sync_rows (
  id uuid primary key default gen_random_uuid(),
  sync_run_id uuid references app.oa_sync_runs(id) on delete cascade,
  oa_source_id text not null,
  form_type text not null,
  workflow_no text,
  source_updated_at timestamptz not null,
  normalized_summary jsonb not null,
  raw_payload jsonb not null,
  payload_hash text not null,
  target_application_id uuid,
  status text not null default 'pending',
  error_code text,
  error_message text,
  created_at timestamptz not null default now(),
  constraint oa_sync_rows_status_chk check (
    status in ('pending', 'normalized', 'applied', 'skipped', 'failed')
  )
);

create unique index oa_sync_rows_source_uidx
  on staging.oa_sync_rows (sync_run_id, oa_source_id)
  where sync_run_id is not null;

create index oa_sync_rows_status_idx
  on staging.oa_sync_rows (sync_run_id, status, source_updated_at)
  where sync_run_id is not null;

create index oa_sync_rows_source_updated_idx
  on staging.oa_sync_rows (form_type, source_updated_at);

create index oa_sync_rows_target_idx
  on staging.oa_sync_rows (target_application_id)
  where target_application_id is not null;

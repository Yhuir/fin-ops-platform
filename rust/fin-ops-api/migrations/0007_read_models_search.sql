create extension if not exists pgcrypto;
create extension if not exists pg_trgm;

create schema if not exists read_model;

create table read_model.workbench_rows (
  id uuid not null default gen_random_uuid(),
  scope_month date not null,
  scope_key text not null,
  row_id uuid not null,
  row_type text not null,
  source_kind text not null,
  source_entity_type text not null,
  source_entity_id uuid not null,
  business_date date,
  counterparty_name text,
  project_id text,
  project_name text,
  amount numeric(18, 2),
  direction text,
  status text not null,
  zone_hint text not null,
  group_key text,
  relation_case_id uuid,
  candidate_match_id uuid,
  exception_case_id uuid,
  ignored boolean not null default false,
  handled_exception boolean not null default false,
  payload jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  stale boolean not null default false,
  stale_reason text,
  updated_at timestamptz not null default now(),
  constraint workbench_rows_pkey primary key (scope_month, id),
  constraint workbench_rows_scope_month_chk check (
    scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint workbench_rows_row_type_chk check (row_type in ('oa', 'bank', 'invoice')),
  constraint workbench_rows_zone_hint_chk check (
    zone_hint in ('paired', 'open', 'ignored', 'processed_exception')
  ),
  constraint workbench_rows_amount_chk check (amount is null or amount >= 0)
) partition by range (scope_month);

create trigger workbench_rows_set_updated_at
before update on read_model.workbench_rows
for each row
execute function app.set_updated_at();

create unique index workbench_rows_scope_row_uidx
  on read_model.workbench_rows (scope_month, row_type, row_id);

create index workbench_rows_filter_idx
  on read_model.workbench_rows (scope_month, row_type, status, business_date desc);

create index workbench_rows_relation_idx
  on read_model.workbench_rows (relation_case_id)
  where relation_case_id is not null;

create index workbench_rows_exception_idx
  on read_model.workbench_rows (exception_case_id)
  where exception_case_id is not null;

create index workbench_rows_candidate_idx
  on read_model.workbench_rows (candidate_match_id)
  where candidate_match_id is not null;

create index workbench_rows_counterparty_trgm_idx
  on read_model.workbench_rows using gin (counterparty_name gin_trgm_ops);

create table read_model.workbench_snapshots (
  scope_key text primary key,
  scope_type text not null,
  scope_month date,
  schema_version text not null,
  payload jsonb not null,
  ignored_rows jsonb not null default '[]'::jsonb,
  summary jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid references job.worker_tasks(id) on delete set null,
  updated_at timestamptz not null default now(),
  constraint workbench_snapshots_scope_type_chk check (scope_type in ('month', 'all_time')),
  constraint workbench_snapshots_scope_month_chk check (
    scope_month is null
    or scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint workbench_snapshots_scope_consistency_chk check (
    (scope_type = 'month' and scope_month is not null)
    or (scope_type = 'all_time' and scope_month is null)
  )
);

create trigger workbench_snapshots_set_updated_at
before update on read_model.workbench_snapshots
for each row
execute function app.set_updated_at();

create index workbench_snapshots_month_idx
  on read_model.workbench_snapshots (scope_month);

create index workbench_snapshots_stale_idx
  on read_model.workbench_snapshots (stale, updated_at desc)
  where stale;

create table read_model.workbench_candidate_matches (
  id uuid primary key default gen_random_uuid(),
  scope_month date not null,
  candidate_key text not null,
  oa_application_id uuid,
  bank_transaction_id uuid,
  invoice_id uuid,
  score numeric(8, 4) not null,
  reasons jsonb not null default '[]'::jsonb,
  status text not null default 'active',
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint workbench_candidate_matches_scope_month_chk check (
    scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint workbench_candidate_matches_score_chk check (score >= 0),
  constraint workbench_candidate_matches_status_chk check (
    status in ('active', 'superseded', 'dismissed')
  )
);

create trigger workbench_candidate_matches_set_updated_at
before update on read_model.workbench_candidate_matches
for each row
execute function app.set_updated_at();

create unique index workbench_candidate_matches_key_uidx
  on read_model.workbench_candidate_matches (scope_month, candidate_key);

create index workbench_candidate_matches_status_idx
  on read_model.workbench_candidate_matches (scope_month, status, score desc);

create index workbench_candidate_matches_bank_idx
  on read_model.workbench_candidate_matches (bank_transaction_id)
  where bank_transaction_id is not null;

create index workbench_candidate_matches_invoice_idx
  on read_model.workbench_candidate_matches (invoice_id)
  where invoice_id is not null;

create index workbench_candidate_matches_oa_idx
  on read_model.workbench_candidate_matches (oa_application_id)
  where oa_application_id is not null;

create table read_model.search_index_rows (
  id uuid not null default gen_random_uuid(),
  entity_type text not null,
  entity_id uuid not null,
  source_kind text not null,
  scope_month date not null,
  title text not null,
  subtitle text,
  searchable_text text not null,
  searchable_tokens jsonb not null default '{}'::jsonb,
  amount numeric(18, 2),
  status text,
  zone_hint text,
  project_id text,
  project_name text,
  jump_target jsonb not null default '{}'::jsonb,
  payload jsonb not null default '{}'::jsonb,
  source_versions jsonb not null default '{}'::jsonb,
  generated_at timestamptz not null default now(),
  stale boolean not null default false,
  stale_reason text,
  updated_at timestamptz not null default now(),
  constraint search_index_rows_pkey primary key (scope_month, id),
  constraint search_index_rows_scope_month_chk check (
    scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint search_index_rows_entity_type_chk check (
    entity_type in (
      'oa_application',
      'oa_attachment',
      'bank_transaction',
      'invoice',
      'reconciliation_case',
      'project'
    )
  ),
  constraint search_index_rows_amount_chk check (amount is null or amount >= 0)
) partition by range (scope_month);

create trigger search_index_rows_set_updated_at
before update on read_model.search_index_rows
for each row
execute function app.set_updated_at();

create unique index search_index_rows_entity_uidx
  on read_model.search_index_rows (scope_month, entity_type, entity_id);

create index search_index_rows_scope_idx
  on read_model.search_index_rows (scope_month, entity_type, status);

create index search_index_rows_project_idx
  on read_model.search_index_rows (project_id, scope_month)
  where project_id is not null;

create index search_index_rows_stale_idx
  on read_model.search_index_rows (scope_month, stale, updated_at desc)
  where stale;

create index search_index_rows_text_trgm_idx
  on read_model.search_index_rows using gin (searchable_text gin_trgm_ops);

create table read_model.cost_statistics_read_models (
  scope_key text primary key,
  scope_type text not null,
  scope_month date,
  project_scope text not null,
  schema_version text not null,
  payload jsonb not null,
  summary jsonb not null default '{}'::jsonb,
  entry_count integer not null default 0,
  source_scope_keys text[] not null default '{}',
  source_versions jsonb not null default '{}'::jsonb,
  cache_status text not null default 'ready',
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid references job.worker_tasks(id) on delete set null,
  updated_at timestamptz not null default now(),
  constraint cost_statistics_scope_type_chk check (scope_type in ('month', 'all_time')),
  constraint cost_statistics_scope_month_chk check (
    scope_month is null
    or scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint cost_statistics_scope_consistency_chk check (
    (scope_type = 'month' and scope_month is not null)
    or (scope_type = 'all_time' and scope_month is null)
  ),
  constraint cost_statistics_entry_count_chk check (entry_count >= 0),
  constraint cost_statistics_project_scope_chk check (project_scope in ('active', 'all')),
  constraint cost_statistics_cache_status_chk check (
    cache_status in ('ready', 'stale', 'rebuilding', 'failed')
  )
);

create trigger cost_statistics_read_models_set_updated_at
before update on read_model.cost_statistics_read_models
for each row
execute function app.set_updated_at();

create index cost_statistics_scope_month_idx
  on read_model.cost_statistics_read_models (scope_month, project_scope);

create index cost_statistics_stale_idx
  on read_model.cost_statistics_read_models (stale, updated_at desc)
  where stale;

create table read_model.tax_offset_read_models (
  scope_key text primary key,
  scope_month date not null,
  schema_version text not null,
  payload jsonb not null,
  output_count integer not null default 0,
  input_plan_count integer not null default 0,
  certified_count integer not null default 0,
  source_scope_keys text[] not null default '{}',
  source_versions jsonb not null default '{}'::jsonb,
  cache_status text not null default 'ready',
  generated_at timestamptz not null,
  stale boolean not null default false,
  stale_reason text,
  rebuild_task_id uuid references job.worker_tasks(id) on delete set null,
  updated_at timestamptz not null default now(),
  constraint tax_offset_scope_month_chk check (
    scope_month = date_trunc('month', scope_month::timestamp)::date
  ),
  constraint tax_offset_counts_chk check (
    output_count >= 0
    and input_plan_count >= 0
    and certified_count >= 0
  ),
  constraint tax_offset_cache_status_chk check (
    cache_status in ('ready', 'stale', 'rebuilding', 'failed')
  )
);

create trigger tax_offset_read_models_set_updated_at
before update on read_model.tax_offset_read_models
for each row
execute function app.set_updated_at();

create index tax_offset_scope_month_idx
  on read_model.tax_offset_read_models (scope_month);

create index tax_offset_stale_idx
  on read_model.tax_offset_read_models (stale, updated_at desc)
  where stale;

create or replace function read_model.create_workbench_rows_partition(p_scope_month date)
returns void
language plpgsql
as $$
declare
  v_start date;
  v_end date;
  v_partition_name text;
begin
  if p_scope_month is null then
    raise exception 'scope_month cannot be null';
  end if;

  v_start := date_trunc('month', p_scope_month::timestamp)::date;
  v_end := (v_start + interval '1 month')::date;
  v_partition_name := format('workbench_rows_%s', to_char(v_start, 'YYYY_MM'));

  execute format(
    'create table if not exists read_model.%I partition of read_model.workbench_rows for values from (%L) to (%L)',
    v_partition_name,
    v_start,
    v_end
  );
end;
$$;

create or replace function read_model.create_search_index_rows_partition(p_scope_month date)
returns void
language plpgsql
as $$
declare
  v_start date;
  v_end date;
  v_partition_name text;
begin
  if p_scope_month is null then
    raise exception 'scope_month cannot be null';
  end if;

  v_start := date_trunc('month', p_scope_month::timestamp)::date;
  v_end := (v_start + interval '1 month')::date;
  v_partition_name := format('search_index_rows_%s', to_char(v_start, 'YYYY_MM'));

  execute format(
    'create table if not exists read_model.%I partition of read_model.search_index_rows for values from (%L) to (%L)',
    v_partition_name,
    v_start,
    v_end
  );
end;
$$;

create or replace function read_model.ensure_scope_month_partitions(p_scope_month date)
returns void
language plpgsql
as $$
begin
  perform read_model.create_workbench_rows_partition(p_scope_month);
  perform read_model.create_search_index_rows_partition(p_scope_month);
end;
$$;

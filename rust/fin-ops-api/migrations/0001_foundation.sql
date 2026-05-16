create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists btree_gin;

create schema if not exists app authorization fin_ops_migrator;
create schema if not exists read_model authorization fin_ops_migrator;
create schema if not exists job authorization fin_ops_migrator;
create schema if not exists audit authorization fin_ops_migrator;
create schema if not exists staging authorization fin_ops_migrator;

create or replace function app.set_updated_at()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create table audit.events (
  id uuid primary key default gen_random_uuid(),
  event_type text not null,
  action text not null,
  entity_type text not null,
  entity_id uuid not null,
  actor_id text not null,
  actor_type text not null default 'user',
  trace_id text,
  request_id text,
  idempotency_key text,
  source_type text,
  source_id text,
  before_state jsonb not null default '{}'::jsonb,
  after_state jsonb not null default '{}'::jsonb,
  diff jsonb not null default '{}'::jsonb,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  constraint events_actor_type_chk check (
    actor_type in ('user', 'system', 'worker', 'migration')
  ),
  constraint events_before_state_object_chk check (jsonb_typeof(before_state) = 'object'),
  constraint events_after_state_object_chk check (jsonb_typeof(after_state) = 'object'),
  constraint events_diff_object_chk check (jsonb_typeof(diff) = 'object'),
  constraint events_metadata_object_chk check (jsonb_typeof(metadata) = 'object')
);

create index events_entity_created_at_idx
  on audit.events (entity_type, entity_id, created_at desc);

create index events_actor_created_at_idx
  on audit.events (actor_id, created_at desc);

create index events_trace_id_idx
  on audit.events (trace_id)
  where trace_id is not null;

grant usage on schema app, read_model, job, audit, staging
  to fin_ops_api, fin_ops_worker, fin_ops_readonly;

grant select, insert, update, delete on all tables in schema app, read_model, job, staging
  to fin_ops_api, fin_ops_worker;

grant insert on all tables in schema audit
  to fin_ops_api, fin_ops_worker;

grant select on all tables in schema app, read_model, job, audit, staging
  to fin_ops_readonly;

alter default privileges for role fin_ops_migrator in schema app
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema read_model
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema job
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema staging
  grant select, insert, update, delete on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema audit
  grant insert on tables to fin_ops_api, fin_ops_worker;

alter default privileges for role fin_ops_migrator in schema app, read_model, job, audit, staging
  grant select on tables to fin_ops_readonly;

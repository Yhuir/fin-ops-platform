create extension if not exists pgcrypto;
create extension if not exists pg_trgm;
create extension if not exists btree_gin;

create schema if not exists app;
create schema if not exists read_model;
create schema if not exists job;
create schema if not exists audit;
create schema if not exists staging;

create table if not exists audit.events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null,
    object_type text,
    object_id text,
    actor_id text,
    actor_name text,
    scope text,
    trace_id text,
    occurred_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists audit_events_object_idx on audit.events (object_type, object_id, occurred_at desc);
create index if not exists audit_events_actor_idx on audit.events (actor_id, occurred_at desc);
create index if not exists audit_events_payload_gin on audit.events using gin (payload);

create table if not exists job.outbox_events (
    id uuid primary key default gen_random_uuid(),
    event_type text not null,
    aggregate_type text,
    aggregate_id text,
    status text not null default 'pending',
    available_at timestamptz not null default now(),
    attempt_count integer not null default 0,
    last_error text,
    locked_by text,
    locked_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb
);

create index if not exists outbox_events_ready_idx on job.outbox_events (status, available_at);
create index if not exists outbox_events_aggregate_idx on job.outbox_events (aggregate_type, aggregate_id);
create index if not exists outbox_events_payload_gin on job.outbox_events using gin (payload);

create table if not exists staging.mongo_exports (
    id uuid primary key default gen_random_uuid(),
    export_id text not null unique,
    source_database text not null,
    source_backup_archive text,
    source_backup_sha256 text,
    status text not null default 'planned',
    manifest jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb
);

create table if not exists staging.mongo_raw_records (
    id uuid primary key default gen_random_uuid(),
    export_id uuid references staging.mongo_exports(id),
    source_collection text not null,
    legacy_mongo_id text,
    record_type text,
    normalized_payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    imported_at timestamptz not null default now()
);

create unique index if not exists mongo_raw_records_identity_uidx on staging.mongo_raw_records (source_collection, legacy_mongo_id) where legacy_mongo_id is not null;
create index if not exists mongo_raw_records_export_idx on staging.mongo_raw_records (export_id, source_collection);
create index if not exists mongo_raw_records_payload_gin on staging.mongo_raw_records using gin (normalized_payload);

create table if not exists staging.id_mappings (
    id uuid primary key default gen_random_uuid(),
    source_collection text not null,
    legacy_mongo_id text not null,
    target_schema text not null,
    target_table text not null,
    target_id uuid not null,
    mapping_status text not null default 'planned',
    created_at timestamptz not null default now(),
    raw_payload jsonb not null default '{}'::jsonb,
    unique (source_collection, legacy_mongo_id, target_schema, target_table)
);

create index if not exists id_mappings_target_idx on staging.id_mappings (target_schema, target_table, target_id);

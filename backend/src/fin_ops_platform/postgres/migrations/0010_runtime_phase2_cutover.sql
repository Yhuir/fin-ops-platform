alter table app.file_objects
    add column if not exists temporary_object_key text,
    add column if not exists source_storage_backend text,
    add column if not exists source_storage_uri text,
    add column if not exists last_error text,
    add column if not exists uploaded_at timestamptz,
    add column if not exists verified_at timestamptz,
    add column if not exists failed_at timestamptz,
    add column if not exists tombstoned_at timestamptz;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'app.file_objects'::regclass
          and conname = 'file_objects_storage_backend_chk'
    ) then
        alter table app.file_objects
            add constraint file_objects_storage_backend_chk
            check (storage_backend in ('s3', 'minio', 'gridfs_legacy', 'gridfs', 'local', 'local_filesystem')) not valid;
    end if;

    begin
        alter table app.file_objects validate constraint file_objects_storage_backend_chk;
    exception
        when check_violation then
            raise notice 'file_objects_storage_backend_chk remains not valid because existing rows violate the constraint';
    end;

    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'app.file_objects'::regclass
          and conname = 'file_objects_migration_status_chk'
    ) then
        alter table app.file_objects
            add constraint file_objects_migration_status_chk
            check (
                migration_status is null
                or migration_status in ('pending_upload', 'temporary', 'uploaded', 'verified', 'failed', 'tombstoned', 'legacy')
            ) not valid;
    end if;

    begin
        alter table app.file_objects validate constraint file_objects_migration_status_chk;
    exception
        when check_violation then
            raise notice 'file_objects_migration_status_chk remains not valid because existing rows violate the constraint';
    end;
end $$;

create index if not exists file_objects_migration_status_idx
    on app.file_objects (migration_status, created_at desc)
    where migration_status is not null;

create index if not exists file_objects_verified_storage_idx
    on app.file_objects (storage_backend, bucket_name, object_key)
    where migration_status = 'verified';

create index if not exists file_objects_legacy_gridfs_idx
    on app.file_objects (legacy_gridfs_id)
    where legacy_gridfs_id is not null;

create index if not exists file_objects_temporary_object_idx
    on app.file_objects (temporary_object_key, updated_at desc)
    where temporary_object_key is not null and migration_status in ('pending_upload', 'temporary', 'failed');

alter table read_model.tax_offset_read_models
    add column if not exists schema_version text,
    add column if not exists cache_status text not null default 'fresh';

update read_model.tax_offset_read_models
set schema_version = coalesce(schema_version, payload->>'schema_version'),
    cache_status = coalesce(nullif(cache_status, ''), payload->>'cache_status', 'fresh')
where schema_version is null
   or cache_status is null
   or cache_status = '';

create index if not exists tax_offset_read_models_status_scope_idx
    on read_model.tax_offset_read_models (cache_status, scope_month, generated_at desc);

alter table read_model.search_index_rows
    add column if not exists cache_status text not null default 'fresh';

create index if not exists search_index_rows_status_scope_idx
    on read_model.search_index_rows (status, scope_month, source_kind);

create table if not exists read_model.pending_invoice_rows (
    id uuid primary key default gen_random_uuid(),
    row_id text not null,
    direction text not null,
    filter_group text not null default 'all',
    scope_month date,
    trade_date date,
    counterparty_name text,
    amount numeric(20, 6),
    missing_invoice boolean not null default false,
    can_create_invoice boolean not null default false,
    searchable_text text not null default '',
    generated_at timestamptz not null default now(),
    cache_status text not null default 'fresh',
    payload jsonb not null default '{}'::jsonb,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (row_id, direction),
    check (direction in ('expense', 'income')),
    check (filter_group in ('all', 'requires_invoice', 'bank_statement_as_invoice', 'no_invoice_required'))
);

create index if not exists pending_invoice_rows_page_idx
    on read_model.pending_invoice_rows (direction, filter_group, trade_date desc, row_id);

create index if not exists pending_invoice_rows_month_idx
    on read_model.pending_invoice_rows (scope_month, direction, filter_group);

create index if not exists pending_invoice_rows_search_trgm
    on read_model.pending_invoice_rows using gin (searchable_text gin_trgm_ops);

alter table app.oa_applications
    add column if not exists scope_month date;

update app.oa_applications
set scope_month = date_trunc('month', application_date::timestamp)::date
where scope_month is null
  and application_date is not null;

create index if not exists oa_applications_scope_month_row_idx
    on app.oa_applications (scope_month, row_id);

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select on read_model.pending_invoice_rows to fin_ops_api;
        grant select on read_model.search_index_rows to fin_ops_api;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select, insert, update, delete on read_model.pending_invoice_rows to fin_ops_worker;
        grant select, insert, update, delete on read_model.search_index_rows to fin_ops_worker;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on read_model.pending_invoice_rows to fin_ops_readonly;
        grant select on read_model.search_index_rows to fin_ops_readonly;
    end if;

    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on read_model.pending_invoice_rows to fin_ops_migrator;
        grant select, insert, update, delete on read_model.search_index_rows to fin_ops_migrator;
    end if;
end $$;

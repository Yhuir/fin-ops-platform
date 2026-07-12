alter table app.etc_import_sessions
    add column if not exists task_id text,
    add column if not exists task_version integer,
    add column if not exists zip_preview_generation integer,
    add column if not exists confirmed_item_set_hash text,
    add column if not exists preview_fingerprint text,
    add column if not exists preview_summary jsonb not null default '{}'::jsonb,
    add column if not exists last_error text;

alter table app.etc_import_sessions
    alter column imported_at drop not null,
    alter column imported_at drop default;

create index if not exists etc_import_sessions_task_status_idx
    on app.etc_import_sessions (task_id, status, updated_at desc);

create table if not exists app.etc_import_session_files (
    id uuid primary key default gen_random_uuid(),
    session_id uuid not null references app.etc_import_sessions(id) on delete cascade,
    file_id text not null,
    ordinal integer not null,
    file_object_id uuid not null references app.file_objects(id),
    original_filename text not null,
    sha256 text not null,
    size_bytes bigint not null,
    raw_payload jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (session_id, file_id),
    unique (session_id, ordinal)
);

create index if not exists etc_import_session_files_object_idx
    on app.etc_import_session_files (file_object_id);

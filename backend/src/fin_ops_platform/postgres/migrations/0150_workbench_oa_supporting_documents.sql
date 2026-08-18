set local lock_timeout = '10s';
set local statement_timeout = '5min';

create table if not exists app.workbench_oa_supporting_documents (
    id uuid primary key default gen_random_uuid(),
    relation_case_id text,
    oa_row_id text not null,
    expense_item_id text not null,
    file_object_id uuid not null references app.file_objects(id),
    original_filename text not null,
    content_type text not null,
    content_sha256 text not null,
    size_bytes bigint not null check (size_bytes > 0),
    status text not null default 'active' check (status in ('active', 'deleted')),
    created_by text not null,
    created_at timestamptz not null default now(),
    deleted_by text,
    deleted_at timestamptz,
    raw_payload jsonb not null default '{}'::jsonb
);

create unique index if not exists workbench_oa_supporting_documents_active_content_uidx
    on app.workbench_oa_supporting_documents (oa_row_id, expense_item_id, content_sha256)
    where status = 'active';

create index if not exists workbench_oa_supporting_documents_item_idx
    on app.workbench_oa_supporting_documents (oa_row_id, expense_item_id, created_at desc)
    where status = 'active';

do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update on app.workbench_oa_supporting_documents to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update on app.workbench_oa_supporting_documents to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.workbench_oa_supporting_documents to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.workbench_oa_supporting_documents to fin_ops_migrator;
    end if;
end
$$;

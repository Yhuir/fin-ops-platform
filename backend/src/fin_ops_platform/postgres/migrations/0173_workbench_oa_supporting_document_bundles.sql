set local lock_timeout = '10s';
set local statement_timeout = '5min';

create table if not exists app.workbench_oa_supporting_document_bundles (
    oa_row_id text not null,
    expense_item_id text not null,
    total_amount numeric(20,2) check (total_amount >= 0),
    version integer not null default 0 check (version >= 0),
    created_by text not null,
    updated_by text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (oa_row_id, expense_item_id)
);

-- Historical files intentionally have no inferred amount or synthetic bundle version.
do $$
begin
    if exists (select 1 from pg_roles where rolname = 'fin_ops_api') then
        grant select, insert, update on app.workbench_oa_supporting_document_bundles to fin_ops_api;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_app_runtime') then
        grant select, insert, update on app.workbench_oa_supporting_document_bundles to fin_ops_app_runtime;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_worker') then
        grant select on app.workbench_oa_supporting_document_bundles to fin_ops_worker;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_readonly') then
        grant select on app.workbench_oa_supporting_document_bundles to fin_ops_readonly;
    end if;
    if exists (select 1 from pg_roles where rolname = 'fin_ops_migrator') then
        grant select, insert, update, delete on app.workbench_oa_supporting_document_bundles to fin_ops_migrator;
    end if;
end
$$;

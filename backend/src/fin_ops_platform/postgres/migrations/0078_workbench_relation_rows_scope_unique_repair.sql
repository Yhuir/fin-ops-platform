-- Idempotent forward repair for environments that applied an earlier 0077.

alter table if exists read_model.workbench_relation_rows
    drop constraint if exists workbench_relation_rows_tenant_id_row_id_key;

do $$
begin
    if not exists (
        select 1
        from pg_constraint
        where conrelid = 'read_model.workbench_relation_rows'::regclass
          and conname = 'workbench_relation_rows_tenant_scope_row_key'
    ) then
        create unique index if not exists workbench_relation_rows_tenant_scope_row_idx
            on read_model.workbench_relation_rows (tenant_id, scope_key, row_id);
    end if;
end $$;

create index if not exists workbench_relation_rows_tenant_row_idx
    on read_model.workbench_relation_rows (tenant_id, row_id);

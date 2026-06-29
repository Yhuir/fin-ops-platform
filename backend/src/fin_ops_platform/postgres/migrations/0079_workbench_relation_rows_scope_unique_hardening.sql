-- Reassert the workbench relation row scope uniqueness target after accepted
-- 0077/0078 checksum drift.
--
-- The table is a rebuildable read model projection. If an early repair left
-- duplicate rows for the same scope row, keep the newest projection row and let
-- normal read model refresh rebuild any stale payload details from canonical
-- relation facts.

alter table if exists read_model.workbench_relation_rows
    drop constraint if exists workbench_relation_rows_tenant_id_row_id_key;

delete from read_model.workbench_relation_rows target
using (
    select
        id,
        row_number() over (
            partition by tenant_id, scope_key, row_id
            order by generated_at desc, updated_at desc, created_at desc, id desc
        ) as row_rank
    from read_model.workbench_relation_rows
) ranked
where target.id = ranked.id
  and ranked.row_rank > 1;

do $$
begin
    if not exists (
        select 1
        from pg_index idx
        join pg_class tbl on tbl.oid = idx.indrelid
        join pg_namespace ns on ns.oid = tbl.relnamespace
        where ns.nspname = 'read_model'
          and tbl.relname = 'workbench_relation_rows'
          and idx.indisunique
          and idx.indpred is null
          and replace(pg_get_indexdef(idx.indexrelid), ' ', '') like '%(tenant_id,scope_key,row_id)%'
    ) then
        create unique index workbench_relation_rows_tenant_scope_row_idx
            on read_model.workbench_relation_rows (tenant_id, scope_key, row_id);
    end if;

    if not exists (
        select 1
        from pg_index idx
        join pg_class tbl on tbl.oid = idx.indrelid
        join pg_namespace ns on ns.oid = tbl.relnamespace
        where ns.nspname = 'read_model'
          and tbl.relname = 'workbench_relation_rows'
          and idx.indisunique
          and idx.indpred is null
          and replace(pg_get_indexdef(idx.indexrelid), ' ', '') like '%(tenant_id,scope_key,row_id)%'
    ) then
        raise exception 'workbench_relation_rows scope unique index missing after 0079 hardening';
    end if;
end $$;

create index if not exists workbench_relation_rows_tenant_row_idx
    on read_model.workbench_relation_rows (tenant_id, row_id);

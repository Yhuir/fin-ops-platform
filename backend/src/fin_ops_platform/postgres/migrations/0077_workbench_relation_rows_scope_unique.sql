-- Allow one workbench relation row index per scope.
--
-- A confirmed relation can span OA, bank, and invoice objects from different
-- months. Downstream read models query relation context by their own scope, so
-- row indexes must not be overwritten by the last rebuilt month.

alter table if exists read_model.workbench_relation_rows
    drop constraint if exists workbench_relation_rows_tenant_id_row_id_key;

alter table if exists read_model.workbench_relation_rows
    add constraint workbench_relation_rows_tenant_scope_row_key
    unique (tenant_id, scope_key, row_id);

create index if not exists workbench_relation_rows_tenant_row_idx
    on read_model.workbench_relation_rows (tenant_id, row_id);

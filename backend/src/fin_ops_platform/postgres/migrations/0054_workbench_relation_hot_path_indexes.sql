-- Tighten relation distribution hot-path indexes for page read-model consumers.

create index if not exists workbench_relation_rows_scope_status_type_idx
    on read_model.workbench_relation_rows (tenant_id, scope_key, relation_status, row_type);

create index if not exists workbench_relation_groups_tenant_group_idx
    on read_model.workbench_relation_groups (tenant_id, group_id);

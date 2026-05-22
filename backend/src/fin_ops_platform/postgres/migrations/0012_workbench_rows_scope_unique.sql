alter table read_model.workbench_rows
    alter column scope_key set not null;

alter table read_model.workbench_rows
    drop constraint if exists workbench_rows_row_id_key;

create unique index if not exists workbench_rows_scope_row_key
    on read_model.workbench_rows (scope_key, row_id);

create index if not exists workbench_rows_scope_key_status_idx
    on read_model.workbench_rows (scope_key, status, updated_at desc);

create index if not exists oa_application_items_application_row_idx
    on app.oa_application_items (oa_application_id, row_id);

create index if not exists oa_application_items_source_form_idx
    on app.oa_application_items (oa_source_id, form_id);

create index if not exists oa_attachments_application_row_idx
    on app.oa_attachments (oa_application_id, row_id);

create index if not exists oa_attachments_filename_trgm_idx
    on app.oa_attachments using gin (filename gin_trgm_ops);

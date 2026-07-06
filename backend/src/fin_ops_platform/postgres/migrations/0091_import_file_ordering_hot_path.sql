-- Match the import file list endpoint's stable ordering expression.

create index if not exists import_files_uploaded_legacy_id_idx
    on app.import_files (uploaded_at desc, (coalesce(legacy_mongo_id, id::text)) desc);

create index if not exists import_files_session_uploaded_legacy_id_idx
    on app.import_files (session_id, uploaded_at desc, (coalesce(legacy_mongo_id, id::text)) desc);

create index if not exists import_files_status_uploaded_legacy_id_idx
    on app.import_files (status, uploaded_at desc, (coalesce(legacy_mongo_id, id::text)) desc);

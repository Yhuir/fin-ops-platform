-- Import and ETC list hot paths for production first-response SLOs.

create index if not exists import_files_uploaded_id_idx
    on app.import_files (uploaded_at desc, id desc);

create index if not exists import_files_session_uploaded_id_idx
    on app.import_files (session_id, uploaded_at desc, id desc);

create index if not exists import_files_status_uploaded_id_idx
    on app.import_files (status, uploaded_at desc, id desc);

create index if not exists etc_invoices_issue_status_id_idx
    on app.etc_invoices (invoice_date desc, etc_invoice_id desc)
    include (status, batch_id, business_batch_id, file_path, raw_payload)
    where coalesce(status, '') <> 'deleted';

create index if not exists etc_invoices_status_issue_id_idx
    on app.etc_invoices (status, invoice_date desc, etc_invoice_id desc)
    include (batch_id, business_batch_id, file_path);

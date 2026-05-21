create index if not exists invoices_legacy_source_batch_idx
    on app.invoices (legacy_source_batch_id)
    where legacy_source_batch_id is not null;

create index if not exists invoices_created_id_idx
    on app.invoices (created_at desc, legacy_mongo_id desc);

create index if not exists bank_transactions_legacy_source_batch_idx
    on app.bank_transactions (legacy_source_batch_id)
    where legacy_source_batch_id is not null;

create index if not exists bank_transactions_created_id_idx
    on app.bank_transactions (created_at desc, legacy_mongo_id desc);

create index if not exists import_files_status_uploaded_idx
    on app.import_files (status, uploaded_at desc);

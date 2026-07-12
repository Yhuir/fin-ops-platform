drop index if exists app.import_files_batch_idx;

alter table app.import_files
    drop column if exists import_batch_id;

alter table if exists read_model.output_invoice_collection_rows
    add column if not exists bank_account text,
    add column if not exists bank_direction text;

create index if not exists output_invoice_collection_rows_bank_account_idx
    on read_model.output_invoice_collection_rows (bank_account, scope_month);

create index if not exists output_invoice_collection_rows_bank_direction_idx
    on read_model.output_invoice_collection_rows (bank_direction, scope_month);

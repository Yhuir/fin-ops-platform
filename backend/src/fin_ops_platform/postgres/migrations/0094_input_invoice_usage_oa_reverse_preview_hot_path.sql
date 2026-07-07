create index if not exists input_invoice_usage_rows_invoice_id_generated_idx
    on read_model.input_invoice_usage_rows (invoice_id, generated_at desc);

create index if not exists oa_pending_payment_rows_oa_id_idx
    on read_model.oa_pending_payment_rows (oa_id, generated_at desc);

create index if not exists oa_pending_payment_rows_bank_transaction_id_idx
    on read_model.oa_pending_payment_rows (bank_transaction_id, generated_at desc)
    where bank_transaction_id is not null;

create index if not exists oa_pending_payment_rows_invoice_id_idx
    on read_model.oa_pending_payment_rows (invoice_id, generated_at desc)
    where invoice_id is not null;

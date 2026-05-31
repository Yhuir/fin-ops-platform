alter table read_model.oa_pending_payment_rows
    add column if not exists bank_paid_total numeric(20, 6);

create index if not exists oa_pending_payment_rows_scope_paid_total_idx
    on read_model.oa_pending_payment_rows (scope_key, bank_paid_total);

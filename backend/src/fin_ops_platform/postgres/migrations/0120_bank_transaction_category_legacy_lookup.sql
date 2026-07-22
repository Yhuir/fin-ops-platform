create index if not exists bank_transaction_categories_legacy_status_idx
    on app.bank_transaction_categories (legacy_transaction_id, status)
    where legacy_transaction_id is not null;

-- Resolve cross-month Workbench relation members without sorting whole fact tables.

create index if not exists bank_transactions_workbench_identity_idx
    on app.bank_transactions ((coalesce(legacy_mongo_id, id::text)));

create index if not exists invoices_workbench_identity_idx
    on app.invoices ((coalesce(legacy_mongo_id, id::text)));

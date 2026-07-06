-- Speed up scoped workbench_relation source version checks and relation fan-out.

create index if not exists workbench_pair_relations_scope_updated_idx
    on app.workbench_pair_relations (month_scope, updated_at desc);

create index if not exists workbench_pair_relations_updated_idx
    on app.workbench_pair_relations (updated_at desc);

create index if not exists workbench_reconciliation_decisions_scope_updated_idx
    on read_model.workbench_reconciliation_decisions (scope_month, updated_at desc);

create index if not exists bank_transaction_relation_claims_active_scope_updated_idx
    on app.bank_transaction_relation_claims (scope_month, updated_at desc)
    where status = 'active';

create index if not exists bank_transactions_month_updated_idx
    on app.bank_transactions (txn_month, updated_at desc)
    where status <> 'deleted';

create index if not exists invoices_month_updated_idx
    on app.invoices (invoice_month, updated_at desc)
    where status <> 'deleted';

create index if not exists oa_applications_application_updated_idx
    on app.oa_applications (application_date, updated_at desc)
    where application_date is not null;

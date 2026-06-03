-- Allow income cash-income pending invoice read-model rows and keep scope constraint idempotent.

alter table read_model.pending_invoice_rows
    drop constraint if exists pending_invoice_rows_filter_group_check;

alter table read_model.pending_invoice_rows
    add constraint pending_invoice_rows_filter_group_check
    check (filter_group in ('all', 'requires_invoice', 'bank_statement_as_invoice', 'no_invoice_required', 'cash_income'));

alter table read_model.pending_invoice_scopes
    drop constraint if exists pending_invoice_scopes_filter_group_check;

alter table read_model.pending_invoice_scopes
    add constraint pending_invoice_scopes_filter_group_check
    check (filter_group in ('all', 'requires_invoice', 'bank_statement_as_invoice', 'no_invoice_required', 'cash_income'));

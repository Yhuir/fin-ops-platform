-- Allow income cash-income pending invoice read-model scopes.

alter table read_model.pending_invoice_scopes
    drop constraint if exists pending_invoice_scopes_filter_group_check;

alter table read_model.pending_invoice_scopes
    add constraint pending_invoice_scopes_filter_group_check
    check (filter_group in ('all', 'requires_invoice', 'bank_statement_as_invoice', 'no_invoice_required', 'cash_income'));

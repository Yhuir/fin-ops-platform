from __future__ import annotations

# A voucher amount is additional to these exact invoice facts. A later invoice
# change requires reconfirming that amount, rather than silently double counting.
SUPPORTING_DOCUMENT_INVOICE_BASIS_SQL = """
select source.oa_row_id, source.expense_item_id,
       jsonb_object_agg(source.invoice_id, source.amount) as invoice_basis
from (
    select distinct
        case when position(':item:' in link.value->>'source_expense_item_id') > 0
             then split_part(link.value->>'source_expense_item_id', ':item:', 1)
             else coalesce(nullif(link.value->>'derived_from_oa_id', ''),
                           nullif(link.value->>'source_workbench_row_id', '')) end as oa_row_id,
        link.value->>'source_expense_item_id' as expense_item_id,
        invoice.id::text as invoice_id,
        coalesce(invoice.total_with_tax, invoice.amount) as amount
    from app.invoices invoice
    cross join lateral jsonb_array_elements(invoice.source_links) link(value)
    where invoice.status <> 'deleted'
      and link.value->>'source_type' in ('oa_attachment_invoice', 'oa_expense_item_invoice')
      and nullif(link.value->>'source_expense_item_id', '') is not null
) source
group by source.oa_row_id, source.expense_item_id
"""

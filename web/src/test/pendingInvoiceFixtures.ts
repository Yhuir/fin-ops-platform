// Explicit rows used by mocked HTTP tests; production summaries are verified in PostgreSQL.
export function pendingAcquisitionFixture(rows: Array<Record<string, unknown>>) {
  const status_counts: Record<string, number> = {
    paid_pending_invoice: 0, paid_invoiced: 0, invoice_not_fully_paid: 0, bank_statement_as_invoice: 0,
    no_invoice_required: 0, income_pending_invoice: 0, income_invoiced: 0, income_no_invoice_required: 0, cash_income: 0,
  };
  const invoices = new Set<string>();
  for (const row of rows) {
    const status = row.invoice_acquisition_status as { code: string };
    if (!(status.code in status_counts)) throw new Error(`Unknown fixture status: ${status.code}`);
    status_counts[status.code]++;
    const zone = row.input_invoices as { summaries: { id: string }[] };
    for (const invoice of zone.summaries) invoices.add(invoice.id);
  }
  return { bank_count: rows.length, invoice_count: invoices.size, status_counts };
}

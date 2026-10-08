export type InvoiceNavigationSummary = {
  polarity: string | null;
  counterpartyName: string | null;
  totalWithTax: string | null;
  invoiceDate: string | null;
};

export default function InvoiceDocumentOption({ summary, index }: { summary: InvoiceNavigationSummary; index: number }) {
  return <span className="invoice-document-option">
    <span className="invoice-document-option__heading">
      <span className="entity-detail-tab__number">{index}</span>
      {summary.polarity && <span className={`invoice-document-option__polarity${summary.polarity === '红字' ? ' invoice-document-option__polarity--red' : ''}`}>{summary.polarity}</span>}
      <span className="invoice-document-option__amount">{summary.totalWithTax || '—'}</span>
    </span>
    <span className="invoice-document-option__name">{summary.counterpartyName ?? '—'}</span>
    <span className="invoice-document-option__meta">
      <span>{summary.invoiceDate ?? '—'}</span>
    </span>
  </span>;
}

import { Chip } from '@heroui/react';

export type BankNavigationSummary = {
  counterpartyName: string | null;
  amount: string | null;
  direction: string | null;
  transactionDate: string | null;
  labels: string[] | null;
};

export function BankDetailLabels({ labels }: { labels: string[] | null }) {
  if (labels === null) return <span>标签信息未提供</span>;
  if (!labels.length) return <span>未设置标签</span>;
  return <span className="bank-detail-labels">{labels.map((label, index) =>
    <Chip key={`${index}:${label}`} className="bank-detail-label" size="sm" variant="soft"><Chip.Label className="bank-detail-label__text">{label}</Chip.Label></Chip>
  )}</span>;
}

export default function BankDocumentOption({ summary, index }: { summary: BankNavigationSummary; index: number }) {
  return <span className="bank-document-option">
    <span className="bank-document-option__heading">
      <span className="entity-detail-tab__number">{index}</span>
      <span>{summary.direction ?? '方向未知'}</span>
      <span className="bank-document-option__amount">{summary.amount ?? '—'}</span>
    </span>
    <span className="bank-document-option__name">{summary.counterpartyName ?? '—'}</span>
    <span className="bank-document-option__date">{summary.transactionDate ?? '—'}</span>
    <BankDetailLabels labels={summary.labels} />
  </span>;
}

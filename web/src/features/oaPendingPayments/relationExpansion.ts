import type { RelationColumn } from '../../components/common/RelationGroupExpansion';
import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { OaPendingPaymentRow } from './types';

export function oaPendingRelationColumns(row: OaPendingPaymentRow): RelationColumn[] | null {
  if (!row.oa.summaries || !row.bankTransaction.summaries || !row.bankTransaction.nonOutflowRelationEdges || !row.invoice.summaries) return null;
  const banks = originalRelationMembers([...row.bankTransaction.summaries!, ...row.bankTransaction.nonOutflowRelationEdges!].map(item => ({
    id: item.bankTransactionId!, originalId: item.parent_row_id, title: item.counterpartyName!,
    subtitle: [item.bankAccount, item.summary, item.remark].filter(Boolean).join(' · '), date: item.tradeTime,
    amount: item.original_amount, status: item.directionLabel, detailAvailable: Boolean(item.bankTransactionId), relationId: item.relationCaseId,
  })));
  return [
    { kind: 'oa', count: row.oa.relationCount!, members: row.oa.summaries!.map(item => ({
      id: item.oaId!, title: item.applicantName!, subtitle: [item.projectName, item.reason].filter(Boolean).join(' · '), date: item.applicationTime,
      amount: item.amount, status: item.applicationType, detailAvailable: Boolean(item.oaId), relationId: item.relationCaseId,
    })) },
    { kind: 'bank', count: banks.length, members: banks },
    { kind: 'invoice', count: row.invoice.relationCount, members: row.invoice.summaries!.map(item => ({
      id: item.invoiceId!, title: item.digitalInvoiceNo!, subtitle: item.sellerName, date: item.invoiceDate,
      amount: item.totalWithTax, detailAvailable: Boolean(item.invoiceId), relationId: item.relationCaseId,
    })) },
  ];
}

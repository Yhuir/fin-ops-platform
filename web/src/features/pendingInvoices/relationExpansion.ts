import type { RelationColumn } from '../../components/common/RelationGroupExpansion';
import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { PendingInvoiceRow } from './types';

export function pendingInvoiceRelationColumns(row: PendingInvoiceRow): RelationColumn[] {
  return [
    { kind: 'bank', count: row.bankTransactions.originalTransactionCount!, members: originalRelationMembers(row.bankTransactions.summaries.map(item => ({
      id: item.id, originalId: item.parentRowId, title: item.counterpartyName,
      subtitle: [item.bankName, item.accountLast4, item.summary].filter(Boolean).join(' · '), date: item.tradeTime,
      amount: item.originalAmount,  detailAvailable: Boolean(item.id), relationId: item.relationCaseId,
    }))) },
    { kind: 'invoice', count: row.inputInvoices.relationCount, members: row.inputInvoices.summaries.map(item => ({
      id: item.id, title: item.digitalInvoiceNo || [item.invoiceCode, item.invoiceNo].filter(Boolean).join(' '),
      subtitle: item.invoiceType === 'output' ? item.buyerName : item.sellerName, date: item.issueDate,
      amount: item.totalWithTax, detailAvailable: Boolean(item.id), relationId: item.relationCaseId,
    })) },
    { kind: 'oa', count: row.oa.relationCount, members: row.oa.summaries.map(item => ({
      id: item.id, title: item.applicant, subtitle: item.projectName, status: [item.applicationType,item.workflowStatus].filter(Boolean).join(' · '),
      amount: item.amount, detailAvailable: item.detailAvailable, relationId: item.relationCaseId,
    })) },
  ];
}

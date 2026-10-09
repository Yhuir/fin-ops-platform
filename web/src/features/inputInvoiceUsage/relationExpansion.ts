import type { RelationColumn } from '../../components/common/RelationGroupExpansion';
import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { InputInvoiceUsageRow } from './types';

export function inputInvoiceRelationColumns(row: InputInvoiceUsageRow): RelationColumn[] {
  const invoices = row.invoiceRelations.summaries;
  const members = [{ id: row.invoice.id, title: row.invoice.displayNo, subtitle: row.invoice.sellerName,
    date: row.invoice.issueDate, amount: row.invoice.totalWithTax, relationId: invoices.find(item => item.id === row.invoice.id)?.relationCaseId, detailAvailable: Boolean(row.invoice.id) },
    ...invoices.filter(item => item.id !== row.invoice.id).map(item => ({ id: item.id, title: item.displayNo,
      subtitle: item.sellerName, date: item.invoiceDate, amount: item.totalWithTax, relationId: item.relationCaseId, detailAvailable: Boolean(item.id) }))];
  return [
    { kind: 'invoice', count: Math.max(members.length, row.invoiceRelations.relationCount), members },
    { kind: 'oa', count: row.oa.relationCount, members: row.oa.summaries.map(item => ({
      id: item.id, title: item.applicant, subtitle: item.projectName, status: [item.applicationType,item.workflowStatus].filter(Boolean).join(' · '),
      amount: item.amount, relationId: item.relationCaseId, detailAvailable: item.detailAvailable,
    })) },
    { kind: 'bank', count: row.bank.originalTransactionCount!, members: originalRelationMembers(row.bank.summaries.map(item => ({
      id: item.id, originalId: item.parentRowId, title: item.counterpartyName,
      subtitle: [item.bankAccount, item.summary, item.remark].filter(Boolean).join(' · '), date: item.tradeTime,
      amount: item.originalAmount, relationId: item.relationCaseId, status: item.directionLabel, detailAvailable: item.detailAvailable,
    }))) },
  ];
}

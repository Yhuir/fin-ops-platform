import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { OutputInvoiceCollectionRow } from './types';

export function outputInvoiceDisplayRows(row: OutputInvoiceCollectionRow, kind: 'invoice' | 'bank'): OutputInvoiceCollectionRow[] {
  if (kind === 'invoice') return row.invoiceRelations.summaries.map(member => {
    if (!member.memberRow) throw new Error('关联发票成员信息不完整，请重新查询。');
    const { memberRow, invoiceDate, ...invoice } = member;
    return { ...row, invoiceId: member.id, invoice: { ...invoice, issueDate: invoiceDate }, collectionStatus: memberRow.collectionStatus, bank: memberRow.bank };
  });
  return originalRelationMembers(row.bank.summaries.map(bank => ({ ...bank, originalId: bank.parentRowId, relationId: bank.relationCaseId }))).map(bank => ({
    ...row, bank: { ...row.bank, primary: bank, originalAmount: bank.originalAmount, bankSplitParts: bank.bankSplitParts },
  }));
}

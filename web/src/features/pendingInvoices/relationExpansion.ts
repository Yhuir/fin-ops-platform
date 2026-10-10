import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { RelationKind } from '../relations/types';
import type { PendingInvoiceBankTransaction, PendingInvoiceBankTransactionSummary, PendingInvoiceOaSummary, PendingInvoiceRow, PendingInvoiceSummary } from './types';

export type PendingInvoiceDisplayRow = {
  id: string;
  bank: PendingInvoiceBankTransaction | null;
  invoice: PendingInvoiceSummary | null;
  oa: PendingInvoiceOaSummary | null;
};

function relationCases(member: { relationCaseId?: string; relationCaseIds?: string[]; relationIds?: string[] }) {
  return [...new Set([
    ...(member.relationIds ?? []), ...(member.relationCaseIds ?? []),
    ...(member.relationCaseId ? [member.relationCaseId] : []),
  ])];
}

export function pendingInvoiceMembers(row: PendingInvoiceRow) {
  const banks = originalRelationMembers(row.bankTransactions.summaries.map(member => ({
    ...member, originalId: member.parentRowId, relationIds: relationCases(member),
  })));
  const oa = row.oa.relationCount === 1 && row.oa.summaries.length === 0 && row.oa.primary ? [row.oa.primary] : row.oa.summaries;
  return { bank: banks, invoice: row.inputInvoices.summaries, oa };
}

export function pendingInvoiceDisplayRows(row: PendingInvoiceRow, kind: RelationKind, members: ReturnType<typeof pendingInvoiceMembers>): PendingInvoiceDisplayRow[] {
  if (kind === 'bank' && members.bank.length === 0) {
    return [{ id: row.bankTransaction.id, bank: row.bankTransaction, invoice: row.inputInvoices.primary, oa: row.oa.primary }];
  }
  const banksByCase = new Map<string, typeof members.bank[number]>();
  members.bank.forEach(member => member.relationIds.forEach(id => { if (!banksByCase.has(id)) banksByCase.set(id, member); }));
  const invoicesByCase = new Map<string, PendingInvoiceSummary>();
  members.invoice.forEach(member => relationCases(member).forEach(id => { if (!invoicesByCase.has(id)) invoicesByCase.set(id, member); }));
  const oaByCase = new Map<string, PendingInvoiceOaSummary>();
  members.oa.forEach(member => relationCases(member).forEach(id => { if (!oaByCase.has(id)) oaByCase.set(id, member); }));
  return members[kind].map(member => {
    const caseIds = relationCases(member);
    const singleSource = kind === 'bank' && members.bank.length === 1 && caseIds.length === 0
      && row.inputInvoices.relationCount <= 1 && row.oa.relationCount <= 1;
    const bank = kind === 'bank' ? member as PendingInvoiceBankTransactionSummary
      : caseIds.map(id => banksByCase.get(id)).find(Boolean) ?? null;
    const invoice = kind === 'invoice' ? member as PendingInvoiceSummary
      : singleSource ? row.inputInvoices.primary : caseIds.map(id => invoicesByCase.get(id)).find(Boolean) ?? null;
    const oa = kind === 'oa' ? member as PendingInvoiceOaSummary
      : singleSource ? row.oa.primary : caseIds.map(id => oaByCase.get(id)).find(Boolean) ?? null;
    return { id: member.id, bank, invoice, oa };
  });
}

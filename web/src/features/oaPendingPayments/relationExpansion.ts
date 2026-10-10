import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { RelationKind } from '../relations/types';
import type { OaPendingPaymentBankTransactionSummary, OaPendingPaymentInvoiceSummary, OaPendingPaymentOaRelationSummary, OaPendingPaymentRow } from './types';

type OaMember = OaPendingPaymentOaRelationSummary & { id: string; detailAvailable: boolean };
type BankMember = OaPendingPaymentBankTransactionSummary & { id: string; relationIds?: string[] };
type InvoiceMember = OaPendingPaymentInvoiceSummary & { id: string };

export type OaPendingDisplayRow = {
  id: string;
  oa: OaMember | null;
  bank: BankMember | null;
  invoice: InvoiceMember | null;
};

export function oaPendingMembers(row: OaPendingPaymentRow): { oa: OaMember[]; bank: BankMember[]; invoice: InvoiceMember[] } {
  const oa = row.oa.summaries?.length ? row.oa.summaries.map(member => ({
    ...member, id: member.oaId!, detailAvailable: Boolean(member.oaId),
  })) : [{ ...row.oa, id: row.oa.primaryOaId || row.oa.id, oaId: row.oa.primaryOaId || row.oa.id }];
  const summaries = [...(row.bankTransaction.summaries ?? []), ...(row.bankTransaction.nonOutflowRelationEdges ?? [])];
  const bank = summaries.length ? originalRelationMembers(summaries.map(member => ({
    ...member, id: member.bankTransactionId!, originalId: member.parent_row_id, relationId: member.relationCaseId,
  }))) : row.bankTransaction.primaryBankTransactionId ? [{
    ...row.bankTransaction, id: row.bankTransaction.primaryBankTransactionId, bankTransactionId: row.bankTransaction.primaryBankTransactionId,
  }] : [];
  const invoice = row.invoice.summaries?.length ? row.invoice.summaries.map(member => ({ ...member, id: member.invoiceId! }))
    : row.invoice.primaryInvoiceId ? [{ ...row.invoice, id: row.invoice.primaryInvoiceId, invoiceId: row.invoice.primaryInvoiceId }] : [];
  return { oa, bank, invoice };
}

export function oaPendingDisplayRows(kind: RelationKind, members: ReturnType<typeof oaPendingMembers>, ownerOaId: string | null): OaPendingDisplayRow[] {
  const owner = members.oa.length === 1 && members.oa[0].id === ownerOaId ? members.oa[0] : null;
  const oaByCase = new Map<string, OaMember>();
  members.oa.forEach(member => { if (member.relationCaseId && !oaByCase.has(member.relationCaseId)) oaByCase.set(member.relationCaseId, member); });
  const banksByCase = new Map<string, BankMember>();
  members.bank.forEach(member => {
    const ids = member.relationIds ?? (member.relationCaseId ? [member.relationCaseId] : []);
    ids.forEach(id => { if (!banksByCase.has(id)) banksByCase.set(id, member); });
  });
  const invoicesByCase = new Map<string, InvoiceMember>();
  members.invoice.forEach(member => { if (member.relationCaseId && !invoicesByCase.has(member.relationCaseId)) invoicesByCase.set(member.relationCaseId, member); });
  return members[kind].map(member => {
    const caseIds = 'relationIds' in member ? member.relationIds ?? [] : member.relationCaseId ? [member.relationCaseId] : [];
    // Canonical single-OA rows own all their bank/invoice relations; groups resolve by case.
    const sourceOnly = kind === 'oa' && owner !== null && !member.relationCaseId;
    const oa = kind === 'oa' ? member as OaMember
      : owner ?? caseIds.map(id => oaByCase.get(id)).find(Boolean) ?? null;
    const bank = kind === 'bank' ? member as BankMember
      : sourceOnly ? members.bank[0] ?? null : caseIds.map(id => banksByCase.get(id)).find(Boolean) ?? null;
    const invoice = kind === 'invoice' ? member as InvoiceMember
      : sourceOnly ? members.invoice[0] ?? null : caseIds.map(id => invoicesByCase.get(id)).find(Boolean) ?? null;
    return { id: member.id, oa, bank, invoice };
  });
}

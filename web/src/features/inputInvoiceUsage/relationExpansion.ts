import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { RelationKind } from '../relations/types';
import type { InputInvoiceUsageRow } from './types';

export function inputInvoiceMembers(row: InputInvoiceUsageRow) {
  return {
    invoice: row.invoiceRelations.summaries.map(({ invoiceDate, ...member }) => ({ ...member, issueDate: invoiceDate })),
    oa: row.oa.summaries,
    bank: originalRelationMembers(row.bank.summaries.map(member => ({ ...member, originalId: member.parentRowId, relationId: member.relationCaseId }))),
  };
}

export function inputInvoiceDisplayRows(row: InputInvoiceUsageRow, kind: RelationKind) {
  const members = inputInvoiceMembers(row);
  const oaByCase = new Map<string, NonNullable<typeof row.oa.primary>>();
  members.oa.forEach(item => { if (item.relationCaseId && !oaByCase.has(item.relationCaseId)) oaByCase.set(item.relationCaseId, item); });
  const bankByCase = new Map<string, NonNullable<typeof row.bank.primary>>();
  members.bank.forEach(item => item.relationIds.forEach(id => { if (!bankByCase.has(id)) bankByCase.set(id, item); }));
  return members[kind].map(member => {
    const cases = 'relationIds' in member ? member.relationIds : member.relationCaseId ? [member.relationCaseId] : [];
    const invoice = kind === 'invoice' ? member as typeof row.invoice : row.invoice;
    const oa = kind === 'oa' ? member as NonNullable<typeof row.oa.primary>
      : kind === 'invoice' ? row.oa.primary : cases.map(id => oaByCase.get(id)).find(Boolean) ?? null;
    const bank = kind === 'bank' ? member as NonNullable<typeof row.bank.primary>
      : kind === 'invoice' ? members.bank[0] ?? null : cases.map(id => bankByCase.get(id)).find(Boolean) ?? null;
    return { invoice, oa, bank, id: member.id };
  });
}

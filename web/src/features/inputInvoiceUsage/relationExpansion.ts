import type { RelationColumn } from '../../components/common/RelationGroupExpansion';
import { originalRelationMembers } from '../bankSplits/originalRelationMembers';
import type { InputInvoiceUsageRow } from './types';

export function inputInvoiceSourceRelationColumns(row: InputInvoiceUsageRow): RelationColumn[] {
  return [
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

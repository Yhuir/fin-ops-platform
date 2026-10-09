import type { RelationColumn } from '../../components/common/RelationGroupExpansion';
import type { OutputInvoiceCollectionRow } from './types';

export function outputInvoiceRelationColumns(row: OutputInvoiceCollectionRow): RelationColumn[] {
  return row.relationSources;
}

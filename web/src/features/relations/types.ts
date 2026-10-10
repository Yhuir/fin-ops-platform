export type RelationKind = 'invoice' | 'oa' | 'bank';
export type SourceDetailTarget = { kind: RelationKind; id: string; rowId?: string };

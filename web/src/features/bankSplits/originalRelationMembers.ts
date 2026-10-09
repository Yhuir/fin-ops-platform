import type { RelationMember } from '../../components/common/RelationGroupExpansion';

// Source summaries expose parent_row_id for split uses. Never add use amounts to the original amount.
export function originalRelationMembers(members: Array<RelationMember & { originalId?: string }>): RelationMember[] {
  const originals = new Map<string, RelationMember>();
  for (const member of members) {
    const id = member.originalId || member.id;
    const previous = originals.get(id);
    const relationIds = member.relationIds ?? (member.relationId ? [member.relationId] : []);
    if (previous) previous.relationIds = [...new Set([...(previous.relationIds ?? []), ...relationIds])];
    else originals.set(id, { ...member, id, relationIds });
  }
  return [...originals.values()];
}

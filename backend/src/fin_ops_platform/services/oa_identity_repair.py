from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from typing import Any

from fin_ops_platform.services.workbench_free_matching_engine import FormalRelationPlan, relation_fingerprint

CLEANUP_ACTOR = 'system:oa_pending_payment_source_sync'
CLEANUP_EVENTS = {'remove_unavailable_oa_fact', 'cancel_relation_for_unavailable_oa_fact'}


def build_identity_relation_repair(evidence: dict[str, Any], case_ids: list[str]) -> dict[str, Any]:
    """Recover only an exact last cleanup event with proven active source aliases."""
    histories: dict[str, list[dict[str, Any]]] = {}
    for row in evidence['history']:
        histories.setdefault(row['case_id'], []).append(row)
    plans = []
    for case_id in sorted(set(case_ids)):
        current = evidence['current'].get(case_id)
        chain = histories.get(case_id, [])
        history = chain[0] if chain else None
        if not current or not history:
            raise ValueError(f'oa_identity_repair_missing_evidence: {case_id}')
        if history['actor_id'] != CLEANUP_ACTOR or history['event_type'] not in CLEANUP_EVENTS:
            raise ValueError(f'oa_identity_repair_later_change: {case_id}')
        before = next((r for r in history['before_payload'] if r.get('case_id') == case_id), None)
        after = next((r for r in history['after_payload'] if r.get('case_id') == case_id), None)
        if not before:
            raise ValueError(f'oa_identity_repair_missing_before: {case_id}')
        def members(relation):
            return set(zip(relation['row_ids'], relation['row_types'], strict=True))
        if after is None:
            if (history['event_type'] != 'cancel_relation_for_unavailable_oa_fact'
                    or len(chain) != 1 or current['status'] != 'cancelled'
                    or members(current) != members(before)):
                raise ValueError(f'oa_identity_repair_drift: {case_id}')
            after = current
        else:
            latest_after = after
            for later in chain[1:]:
                if (later['actor_id'] != 'system:bank_relation_requirement_recalculation'
                        or later['event_type'] != 'bank_relation_requirement_recalculated'):
                    raise ValueError(f'oa_identity_repair_later_change: {case_id}')
                prior = next((r for r in later['before_payload'] if r.get('case_id') == case_id), None)
                next_after = next((r for r in later['after_payload'] if r.get('case_id') == case_id), None)
                if (not prior or not next_after or members(prior) != members(after)
                        or members(next_after) != members(after)
                        or prior['status'] != after['status'] or next_after['status'] != after['status']):
                    raise ValueError(f'oa_identity_repair_later_members_changed: {case_id}')
                latest_after = next_after
            if current != latest_after:
                raise ValueError(f'oa_identity_repair_drift: {case_id}')
        if len(before['row_ids']) != len(before['row_types']):
            raise ValueError(f'oa_identity_repair_untyped_members: {case_id}')
        replacements = {}
        for row_id, row_type in zip(before['row_ids'], before['row_types'], strict=True):
            if row_type == 'oa' and (after['status'] != 'active' or row_id not in after['row_ids']):
                canonical = evidence['aliases'].get(row_id)
                if not canonical or canonical == row_id:
                    raise ValueError(f'oa_identity_repair_unproven_source: {case_id}')
                replacements[row_id] = canonical
        if not replacements:
            raise ValueError(f'oa_identity_repair_no_removed_oa: {case_id}')
        members = list(zip(current['row_ids'], current['row_types'], strict=True)) if current['status'] == 'active' else []
        for row_id, row_type in zip(before['row_ids'], before['row_types'], strict=True):
            member = (replacements.get(row_id, row_id), row_type)
            if member not in members:
                members.append(member)
        # Exact identifiers only; never rewrite arbitrary text or infer by amount.
        def replace(value):
            if isinstance(value, str):
                return replacements.get(value, value)
            if isinstance(value, list):
                return [replace(item) for item in value]
            if isinstance(value, dict):
                return {key: replace(item) for key, item in value.items()}
            return value
        metadata = deepcopy(before.get('special_metadata') or {})
        if current['status'] == 'active':
            metadata.update(deepcopy(current.get('special_metadata') or {}))
        metadata = replace(metadata)
        metadata.pop('formal_relation', None)
        plans.append({'case_id': case_id, 'members': members, 'before': before,
                      'metadata': metadata, 'replacements': replacements,
                      'target_case_id': case_id if current['status'] == 'active' else None})
    fingerprint = hashlib.sha256(json.dumps(
        {'plans': plans, 'evidence': evidence}, sort_keys=True, ensure_ascii=False, separators=(',', ':'),
    ).encode()).hexdigest()
    return {'fingerprint': fingerprint, 'plans': plans, 'count': len(plans)}


def formal_repair_plans(preview: dict[str, Any]):
    plans = []
    metadata = {}
    for entry in preview['plans']:
        before = entry['before']
        members = tuple((row_type, row_id) for row_id, row_type in entry['members'])
        plans.append(FormalRelationPlan(
            case_id=entry['case_id'], member_keys=members,
            row_ids=tuple(row_id for _, row_id in members), row_types=tuple(kind for kind, _ in members),
            relation_fingerprint=relation_fingerprint(members), rule_code='verified_oa_source_identity_repair',
            rule_version='oa-source-identity-v1', amount_minor=int((before.get('amount_check') or {}).get('amount_minor') or 0),
            currency='CNY', direction='', scope_keys=(before['month_scope'],),
            evidence_summary=(('source_identity_repair', preview['fingerprint']),), batch_hash=preview['fingerprint'],
            target_case_id=entry['target_case_id'], relation_mode=before['relation_mode'],
            oa_attachment_bindings=tuple(
                (item['parent_oa_row_id'], item['invoice_row_id'])
                for item in entry['metadata'].get('oa_attachment_bindings', [])
            ),
        ))
        metadata[entry['case_id']] = entry['metadata']
    return plans, metadata

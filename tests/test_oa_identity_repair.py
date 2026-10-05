from __future__ import annotations

import copy
import unittest

from fin_ops_platform.services.oa_identity_repair import build_identity_relation_repair, formal_repair_plans


class OAIdentityRepairTests(unittest.TestCase):
    def evidence(self):
        before = {'case_id': 'case', 'status': 'active', 'row_ids': ['oa-pay-old', 'bank-1', 'invoice-1'],
                  'row_types': ['oa', 'bank', 'invoice'], 'month_scope': '2026-09',
                  'relation_mode': 'manual_confirmed', 'special_metadata': {'requires_invoice': True}}
        after = {**before, 'row_ids': ['bank-1', 'invoice-1'], 'row_types': ['bank', 'invoice']}
        return {'current': {'case': copy.deepcopy(after)}, 'aliases': {'oa-pay-old': 'oa-pay-current'},
                'history': [{'case_id': 'case', 'id': 'cleanup-event',
                             'actor_id': 'system:oa_pending_payment_source_sync',
                             'event_type': 'remove_unavailable_oa_fact',
                             'before_payload': [before], 'after_payload': [after]}]}

    def test_recovers_exact_members_and_keeps_existing_group(self):
        evidence = self.evidence()
        result = build_identity_relation_repair(evidence, ['case'])
        plans, metadata = formal_repair_plans(result)
        self.assertEqual(result['count'], 1)
        self.assertEqual(plans[0].target_case_id, 'case')
        self.assertEqual(set(plans[0].row_ids), {'bank-1', 'invoice-1', 'oa-pay-current'})
        self.assertTrue(metadata['case']['requires_invoice'])
        self.assertEqual(evidence, self.evidence())

    def test_cancelled_group_can_be_restored_without_target_extension(self):
        evidence = self.evidence()
        evidence['current']['case']['status'] = 'cancelled'
        evidence['history'][0]['after_payload'][0]['status'] = 'cancelled'
        result = build_identity_relation_repair(evidence, ['case'])
        self.assertIsNone(formal_repair_plans(result)[0][0].target_case_id)

    def test_missing_alias_never_guesses_by_amount(self):
        evidence = self.evidence()
        evidence['aliases'] = {}
        with self.assertRaisesRegex(ValueError, 'unproven_source'):
            build_identity_relation_repair(evidence, ['case'])

    def test_later_user_edit_or_current_drift_is_rejected(self):
        for change in ('actor', 'state'):
            evidence = self.evidence()
            if change == 'actor':
                evidence['history'][0]['actor_id'] = 'human'
            else:
                evidence['current']['case']['row_ids'].append('another-bank')
            with self.assertRaises(ValueError):
                build_identity_relation_repair(evidence, ['case'])

    def test_plan_fingerprint_changes_when_source_mapping_changes(self):
        evidence = self.evidence()
        before = build_identity_relation_repair(evidence, ['case'])['fingerprint']
        evidence['aliases']['oa-pay-old'] = 'oa-pay-another'
        self.assertNotEqual(before, build_identity_relation_repair(evidence, ['case'])['fingerprint'])

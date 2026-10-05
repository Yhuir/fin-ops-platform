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

    def test_preserves_later_requirement_recalculation_without_member_changes(self):
        evidence = self.evidence()
        after = evidence['current']['case']
        changed = copy.deepcopy(after)
        changed['special_metadata'] = {'requires_invoice': False, 'paired_requirement_version': 18}
        evidence['current']['case'] = changed
        evidence['history'].append({'case_id': 'case', 'actor_id': 'system:bank_relation_requirement_recalculation',
                                    'event_type': 'bank_relation_requirement_recalculated',
                                    'before_payload': [after], 'after_payload': [changed]})
        _, metadata = formal_repair_plans(build_identity_relation_repair(evidence, ['case']))
        self.assertFalse(metadata['case']['requires_invoice'])
        self.assertEqual(metadata['case']['paired_requirement_version'], 18)
        evidence['history'][-1]['after_payload'][0]['row_ids'].append('new-bank')
        evidence['history'][-1]['after_payload'][0]['row_types'].append('bank')
        with self.assertRaisesRegex(ValueError, 'later_members_changed'):
            build_identity_relation_repair(evidence, ['case'])

    def test_real_cancellation_history_can_have_empty_after_payload(self):
        evidence = self.evidence()
        evidence['history'][0]['event_type'] = 'cancel_relation_for_unavailable_oa_fact'
        evidence['history'][0]['after_payload'] = []
        evidence['current']['case'] = {**evidence['history'][0]['before_payload'][0], 'status': 'cancelled'}
        preview = build_identity_relation_repair(evidence, ['case'])
        self.assertIsNone(formal_repair_plans(preview)[0][0].target_case_id)

    def test_preserves_grouped_attachment_binding_contract(self):
        evidence = self.evidence()
        evidence['history'][0]['before_payload'][0]['special_metadata']['oa_attachment_bindings'] = [
            {'parent_oa_row_id': 'oa-pay-old', 'invoice_row_ids': ['invoice-1']},
        ]
        plans, metadata = formal_repair_plans(build_identity_relation_repair(evidence, ['case']))
        self.assertEqual(plans[0].oa_attachment_bindings, (('oa-pay-current', 'invoice-1'),))
        self.assertEqual(metadata['case']['oa_attachment_bindings'], [
            {'parent_oa_row_id': 'oa-pay-current', 'invoice_row_ids': ['invoice-1']},
        ])

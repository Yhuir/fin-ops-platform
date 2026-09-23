import unittest
from copy import deepcopy

from fin_ops_platform.services.bank_transaction_split_relation_service import BankTransactionSplitRelationService
from fin_ops_platform.services.bank_transaction_split_service import BankTransactionSplitError
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


def relation(case_id, banks):
    return {'case_id': case_id, 'status': 'active', 'relation_mode': 'manual_confirmed',
            'month_scope': '2026-09', 'version': 3, 'row_ids': ['oa-' + case_id, *banks],
            'row_types': ['oa', *['bank'] * len(banks)], 'special_metadata': {'keep': True}}


def fact(parts, version=0):
    return {'transaction_id': 'bank-parent', 'canonical_transaction_id': 'canonical-parent',
            'version': version, 'amount': '1001497.22', 'parts': parts}


PARTS = [{'id': 'principal', 'category_code': 'loan', 'amount': '1000000.00'},
         {'id': 'interest', 'category_code': 'interest', 'amount': '1497.22'}]


class Owners:
    def __init__(self, relations):
        self.relations = deepcopy(relations)
        self.revoked = []
        self.published = []
        self.fail = False

    def acquire_relation_member_locks(self, *args, **kwargs):
        pass

    def load_active_workbench_pair_relations_for_typed_rows(self, ids, row_types):
        return {'pair_relations': {r['case_id']: r for r in self.relations if set(ids) & set(r['row_ids'])}}

    def replace_bank_split_members(self, before, **kwargs):
        if self.fail:
            raise RuntimeError('persist failed')
        domain = WorkbenchPairRelationService(pair_relations={before['case_id']: before})
        domain.replace_bank_split_members(case_id=before['case_id'], **kwargs)
        return domain.snapshot()

    def revoke_for_bank_split(self, case_ids, **kwargs):
        self.revoked.extend(case_ids)
        return case_ids

    def invalidate_bank_split_batches(self, *args, **kwargs):
        return []

    def publish(self, delta, **kwargs):
        self.published.append(delta)

    def service(self):
        return BankTransactionSplitRelationService(
            relation_repository_factory=lambda transaction: self,
            allocation_repository_factory=lambda transaction: self,
            batch_repository_factory=lambda transaction: self,
            settings_snapshot_provider=lambda transaction: {'paired_policy': {'version': 2, 'requirements_by_tag_code': {
                'loan': {'requires_oa': False, 'requires_invoice': False},
                'interest': {'requires_oa': True, 'requires_invoice': True}}}},
            effective_category_rows=lambda transaction, settings, transaction_ids: {
                row_id: {'effective_category_code': 'interest' if row_id == 'interest' else 'loan'} for row_id in transaction_ids},
            turnover_split_migrator=lambda transaction, **kwargs: {},
            relation_delta_publisher=self.publish)


class SplitRelationTests(unittest.TestCase):
    def test_initial_split_keeps_case_and_oa_and_publishes_only_after_commit(self):
        owners = Owners([relation('one', ['bank-parent'])])
        service = owners.service()
        result = service.apply(object(), before=fact([]), after=fact(PARTS, 1), actor_id='user')
        updated = result['_relation_snapshot_delta']['pair_relations']['one']
        self.assertEqual(updated['row_ids'], ['oa-one', 'principal', 'interest'])
        self.assertEqual(updated['version'], 4)
        self.assertTrue(updated['special_metadata']['requires_invoice'])
        self.assertTrue(updated['special_metadata']['bank_split_requires_cost_confirmation'])
        self.assertEqual(owners.revoked, ['one'])
        self.assertFalse(owners.published)
        service.after_commit(result)
        self.assertEqual(len(owners.published), 1)

    def test_unsplit_cannot_merge_two_unrelated_owners(self):
        owners = Owners([relation('one', ['principal']), relation('two', ['interest'])])
        with self.assertRaises(BankTransactionSplitError):
            owners.service().apply(object(), before=fact(PARTS, 1), after=fact([], 2), actor_id='user')
        self.assertEqual(owners.revoked, [])

    def test_new_item_is_not_assigned_to_arbitrary_partial_owner(self):
        owners = Owners([relation('one', ['principal'])])
        parts = [*PARTS, {'id': 'new', 'category_code': 'interest', 'amount': '1.00'}]
        result = owners.service().apply(object(), before=fact(PARTS, 1), after=fact(parts, 2), actor_id='user')
        self.assertEqual(result['changed_case_ids'], [])
        self.assertEqual(owners.revoked, [])

    def test_display_order_only_preserves_existing_cost_decision(self):
        owners = Owners([relation('one', ['principal', 'interest'])])
        result = owners.service().apply(object(), before=fact(PARTS, 1), after=fact(list(reversed(PARTS)), 2), actor_id='user')
        self.assertEqual(result['changed_case_ids'], [])
        self.assertEqual(owners.revoked, [])

    def test_deleted_last_bank_cancels_singleton_without_dropping_oa(self):
        owners = Owners([relation('one', ['interest'])])
        result = owners.service().apply(object(), before=fact(PARTS, 1), after=fact([PARTS[0]], 2), actor_id='user')
        updated = result['_relation_snapshot_delta']['pair_relations']['one']
        self.assertEqual(updated['row_ids'], ['oa-one'])
        self.assertEqual(updated['status'], 'cancelled')

    def test_relation_failure_does_not_revoke_or_publish(self):
        owners = Owners([relation('one', ['bank-parent'])])
        owners.fail = True
        with self.assertRaisesRegex(RuntimeError, 'persist failed'):
            owners.service().apply(object(), before=fact([]), after=fact(PARTS, 1), actor_id='user')
        self.assertEqual(owners.revoked, [])
        self.assertEqual(owners.published, [])


if __name__ == '__main__':
    unittest.main()

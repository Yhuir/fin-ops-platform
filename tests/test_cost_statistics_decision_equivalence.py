import unittest
from copy import deepcopy

from fin_ops_platform.services.cost_statistics_decision_equivalence import automatic_equivalence_reason
from fin_ops_platform.services.cost_statistics_source_allocation import complete_source_task

from tests.test_cost_statistics_source_allocation import confirmed_decision, task_fixture


def equivalent_fixture():
    task = task_fixture()
    task['bank_events'] = [{**task['bank_events'][0], 'amount': '350.00'}]
    for unit, allocation, amount in zip(task['units'], task['allocations'], ('135.00', '215.00'), strict=True):
        unit['oa_original_amount'] = allocation['amount'] = amount
    task.update(oa_total='350.00', net_outflow_total='350.00', source_fingerprint='same-facts')
    task = complete_source_task(task)
    record = {**deepcopy(task), 'source_allocations': None, 'manual_items': [], 'oa_cost_tag_overrides': [],
              'oa_amount_locks': {u['unit_id']: u['lock_oa_amount'] for u in task['units']}}
    return record, task


class CostDecisionEquivalenceTests(unittest.TestCase):
    def test_missing_sources_single_payment_matches_without_mutating_inputs(self):
        record, task = equivalent_fixture()
        before = deepcopy((record, task))
        self.assertEqual(automatic_equivalence_reason(record, task), '')
        self.assertEqual((record, task), before)

    def test_same_total_with_different_unit_amounts_is_not_equivalent(self):
        record, task = equivalent_fixture()
        task['allows_partial'] = True
        record['allocations'][0]['amount'] = '100.00'
        record['allocations'][1]['amount'] = '250.00'
        self.assertEqual(automatic_equivalence_reason(record, task), 'different_amounts')

    def test_ambiguous_history_is_not_replaced_with_automatic_sources(self):
        task = complete_source_task(task_fixture(), confirmed_decision())
        record, _ = equivalent_fixture()
        task['source_fingerprint'] = record['source_fingerprint']
        record['allocations'] = deepcopy(task['allocations'])
        self.assertEqual(automatic_equivalence_reason(record, task), 'missing_sources')

    def test_invalid_source_ownership_is_reported(self):
        record, task = equivalent_fixture()
        task['bank_events'][0]['allowed_unit_ids'] = ['a']
        self.assertEqual(automatic_equivalence_reason(record, task),
                         'historical_sources_invalid:source_owner_mismatch')

    def test_existing_explicit_source_difference_is_preserved(self):
        record, task = equivalent_fixture()
        record['source_allocations'] = deepcopy(task['source_allocations'])
        self.assertEqual(automatic_equivalence_reason(record, task), '')
        record['source_allocations']['cost_lines'][0]['bank_transaction_id'] = 'other-bank'
        self.assertEqual(automatic_equivalence_reason(record, task), 'different_sources')

    def test_manual_semantics_and_changed_facts_are_preserved(self):
        for changes, reason in (
            ({'source_fingerprint': 'changed'}, 'facts_changed'),
            ({'manual_items': [{'unit_id': 'manual:a'}]}, 'manual_content'),
            ({'oa_cost_tag_overrides': [{'cost_tag_code': 'different'}]}, 'manual_content'),
            ({'non_cost_amount': '1.00'}, 'non_cost_decision'),
            ({'non_cost_reason': 'explicit decision'}, 'non_cost_decision'),
            ({'oa_amount_locks': {'a': False, 'b': True}}, 'amount_lock_decision'),
        ):
            with self.subTest(reason=reason, changes=changes):
                record, task = equivalent_fixture()
                record.update(changes)
                self.assertEqual(automatic_equivalence_reason(record, task), reason)
        record, task = equivalent_fixture()
        task['status'] = 'pending'
        self.assertEqual(automatic_equivalence_reason(record, task), 'automatic_unresolved')
        self.assertEqual(automatic_equivalence_reason(record, None), 'no_current_cost_task')

import unittest
from decimal import Decimal
from unittest.mock import Mock, patch

from fin_ops_platform.services.bank_transaction_split_service import BankTransactionSplitError
from fin_ops_platform.services.postgres_repositories.bank_transaction_splits import (
    PostgresBankTransactionSplitRepository,
)


class BankSplitLockingTests(unittest.TestCase):
    def _load(self, *, conflict=False):
        events = []
        class Transaction:
            def fetch_one(self, sql, params):
                if 'bank_transaction_split_sets' in sql:
                    return {'version': 0}
                locked = 'FOR UPDATE' in sql
                events.append('parent_lock' if locked else 'initial_read')
                return {'transaction_id': 'parent', 'canonical_transaction_id': 'canonical',
                        'amount': Decimal('20.00') if locked else Decimal('10.00'),
                        'direction': 'outflow', 'month': '2026-09', 'written_off_amount': Decimal('0.00')}

            def fetch_all(self, sql, params):
                return []

        relation_repository = Mock()
        related = {'pair_relations': {'case': {'row_ids': ['parent', 'other-bank'], 'row_types': ['bank', 'bank'], 'version': 1}}}
        relation_repository.load_active_workbench_pair_relations_for_typed_rows.side_effect = [related, {'pair_relations': {}} if conflict else related]
        relation_repository.acquire_relation_member_locks.side_effect = lambda *args, **kwargs: events.append('all_member_locks')
        patches = [
            patch('fin_ops_platform.services.postgres_repositories.bank_transaction_splits.PostgresWorkbenchRelationRepository', return_value=relation_repository),
            patch('fin_ops_platform.services.postgres_repositories.bank_transaction_splits.PostgresBankDetailsCanonicalQueryRepository.settings_payload', return_value={}),
            patch('fin_ops_platform.services.postgres_repositories.bank_transaction_splits.AppSettingsService.bank_category_relation_policy_snapshot', return_value={'bank_transaction_tags': {'definitions': []}}),
            patch('fin_ops_platform.services.postgres_repositories.bank_transaction_splits.PostgresBankDetailsCanonicalQueryRepository.effective_category_projection_rows', return_value={}),
        ]
        with patches[0], patches[1], patches[2], patches[3]:
            if conflict:
                with self.assertRaises(BankTransactionSplitError) as error:
                    PostgresBankTransactionSplitRepository(object()).load(Transaction(), 'parent', for_update=True)
                self.assertEqual(error.exception.code, 'split_relation_conflict')
                self.assertNotIn('parent_lock', events)
                return
            result = PostgresBankTransactionSplitRepository(object()).load(Transaction(), 'parent', for_update=True)
        relation_repository.acquire_relation_member_locks.assert_called_once_with(['canonical', 'parent'], row_types=['bank', 'bank'], case_ids=['case'])
        self.assertEqual(events, ['initial_read', 'all_member_locks', 'parent_lock'])
        self.assertEqual(result['amount'], '20.00')

    def test_full_case_locks_precede_parent_lock_and_financial_facts_are_reread(self):
        self._load()

    def test_relation_change_during_lock_acquisition_requires_reread(self):
        self._load(conflict=True)

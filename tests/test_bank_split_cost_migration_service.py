import unittest

from fin_ops_platform.services.bank_split_cost_migration_service import BankSplitCostMigrationService


class BankSplitCostMigrationTests(unittest.TestCase):
    def test_preview_revoke_all_history_and_keep_unrelated_decisions(self):
        class Repository:
            def __init__(self):
                self.items = [
                    {'relation_case_id': 'old', 'version': 1, 'row_ids': ['bank-old'], 'row_types': ['bank'], 'source_allocations': None},
                    {'relation_case_id': 'mixed', 'version': 4, 'row_ids': ['bank-old', 'bank-fee'], 'row_types': ['bank', 'bank'], 'source_allocations': {}},
                    {'relation_case_id': 'ordinary', 'version': 2, 'row_ids': ['bank-fee'], 'row_types': ['bank'], 'source_allocations': None},
                ]
                self.calls = []

            def list_bank_split_migration_candidates(self):
                return self.items

            def revoke_for_bank_split(self, case_ids, **kwargs):
                self.calls.append(case_ids)
                self.items = [item for item in self.items if item['relation_case_id'] not in case_ids]
                return case_ids

        repository = Repository()
        service = BankSplitCostMigrationService(
            allocation_repository_factory=lambda tx: repository,
            settings_snapshot_provider=lambda tx: {},
            effective_category_rows=lambda tx, **kwargs: {'bank-old': {'turnover_role': 'external_turnover'}, 'bank-fee': {'turnover_role': ''}})
        preview = service.run(object(), actor_id='test')
        self.assertEqual(preview['affected_case_ids'], ['mixed', 'old'])
        self.assertEqual(preview['mixed_case_ids'], ['mixed'])
        self.assertFalse(repository.calls)
        applied = service.run(object(), actor_id='test', apply=True)
        self.assertEqual(applied['revoked_case_ids'], ['mixed', 'old'])
        self.assertNotIn('marked_case_ids', applied)
        self.assertEqual([item['relation_case_id'] for item in repository.items], ['ordinary'])
        self.assertEqual(service.run(object(), actor_id='test', apply=True)['affected_count'], 0)

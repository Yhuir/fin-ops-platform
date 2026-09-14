import unittest
from datetime import date

from fin_ops_platform.services.workbench_relation_scope import (
    WorkbenchRelationScopeError,
    affected_months,
    canonical_month,
    relation_scope,
    validate_relation_scope,
)


class WorkbenchRelationScopeTests(unittest.TestCase):
    def test_opaque_id_digits_never_supply_or_override_month(self):
        for identity in ('txn_209440', 'txn_209703', 'txn_202608', 'opaque'):
            with self.subTest(identity=identity):
                rows = [{'id': identity, 'scope_month': date(2026, 8, 1)}]
                self.assertEqual(relation_scope(rows), '2026-08')
                self.assertEqual(affected_months(rows), ['2026-08'])
                self.assertEqual(relation_scope([{'id': identity, 'scope_month': None}]), 'all')

    def test_three_oa_one_bank_seven_invoices_span_four_months(self):
        rows = [{'scope_month': month} for month in ['2026-05', '2026-06', '2026-07', '2026-08', *(['2026-07'] * 7)]]
        self.assertEqual(relation_scope(rows), 'all')
        self.assertEqual(affected_months(rows), ['2026-05', '2026-06', '2026-07', '2026-08'])

    def test_null_and_empty_selection_use_all_without_inventing_month(self):
        self.assertEqual(relation_scope([]), 'all')
        self.assertEqual(affected_months([]), [])
        rows = [{'scope_month': None}, {'scope_month': '2026-08'}]
        self.assertEqual(relation_scope(rows), 'all')
        self.assertEqual(affected_months(rows), ['2026-08'])

    def test_invalid_nonnull_values_fail_explicitly(self):
        for value in ('', 'all', '2094-40', '2094-40-01', '2026-02-30', '2026-8', 'junk202608'):
            with self.subTest(value=value), self.assertRaises(WorkbenchRelationScopeError):
                canonical_month(value)
        self.assertIsNone(canonical_month(None))
        self.assertEqual(canonical_month('2026-08-20'), '2026-08')
        self.assertEqual(validate_relation_scope('all'), 'all')
        with self.assertRaises(WorkbenchRelationScopeError):
            validate_relation_scope('2094-40')

import unittest
from copy import deepcopy
from decimal import Decimal

from fin_ops_platform.services.cost_statistics_source_allocation import (
    SourceAllocationError,
    automatic_source_allocations,
    complete_source_task,
    validate_source_allocations,
)


def task_fixture():
    return {
        "status": "pending", "oa_total": "1000.00", "net_outflow_total": "1000.00",
        "non_cost_amount": "0.00", "non_cost_reason": "",
        "units": [{"unit_id": "a", "oa_original_amount": "600.00"}, {"unit_id": "b", "oa_original_amount": "400.00"}],
        "allocations": [{"unit_id": "a", "amount": "600.00"}, {"unit_id": "b", "amount": "400.00"}],
        "bank_events": [
            {"transaction_id": "bank1", "event_kind": "outflow", "amount": "500.00", "trade_time": "2026-08-01", "bank_account_label": "建行", "bank_tag_code": "material", "bank_tag_primary_label": "采购"},
            {"transaction_id": "bank2", "event_kind": "outflow", "amount": "500.00", "trade_time": "2026-09-01", "bank_account_label": "民生", "bank_tag_code": "travel", "bank_tag_primary_label": "项目开销"},
        ],
    }


def confirmed_decision():
    # This is an explicit human decision, never a system recommendation.
    return {"cost_lines": [
        {"unit_id": "a", "bank_transaction_id": "bank1", "amount": "500.00"},
        {"unit_id": "a", "bank_transaction_id": "bank2", "amount": "100.00"},
        {"unit_id": "b", "bank_transaction_id": "bank2", "amount": "400.00"},
    ], "refund_links": [], "non_cost_lines": []}


class SourceAllocationTests(unittest.TestCase):
    def test_equal_totals_do_not_resolve_many_to_many(self):
        task = complete_source_task(task_fixture())
        self.assertEqual(task["pending_reasons"], ["source_required"])
        self.assertIsNone(task["source_allocations"])
        self.assertEqual(task["allocations"][0]["amount"], "600.00")

    def test_explicit_human_decision_closes_both_sides(self):
        task = complete_source_task(task_fixture(), confirmed_decision())
        self.assertEqual(task["status"], "allocated")
        self.assertEqual(len(task["source_allocations"]["cost_lines"]), 3)

    def test_equal_total_cannot_reassign_unit_targets(self):
        task = task_fixture()
        changed = [{"unit_id": "a", "amount": "500.00"}, {"unit_id": "b", "amount": "500.00"}]
        with self.assertRaises(SourceAllocationError) as caught:
            validate_source_allocations(task, changed, Decimal("0"), confirmed_decision())
        self.assertEqual(caught.exception.code, "unit_amount_mismatch")

    def test_rejects_overdraw_unknown_duplicate_and_invalid_amount(self):
        for key, value, code in (("bank_transaction_id", "outside", "invalid_source"), ("amount", "0.00", "invalid_amount"), ("amount", "-1.00", "invalid_amount"), ("amount", "1.001", "invalid_amount"), ("amount", 100, "invalid_amount"), ("amount", "600.00", "source_amount_mismatch")):
            with self.subTest(value=value):
                decision = confirmed_decision()
                decision["cost_lines"][0][key] = value
                with self.assertRaises(SourceAllocationError) as caught:
                    validate_source_allocations(task_fixture(), task_fixture()["allocations"], Decimal("0"), decision)
                self.assertEqual(caught.exception.code, code)
        decision = confirmed_decision()
        decision["cost_lines"].append(deepcopy(decision["cost_lines"][0]))
        with self.assertRaisesRegex(SourceAllocationError, "已有分配行"):
            complete_source_task(task_fixture(), decision)

    def test_single_unit_split_retains_both_bank_sources(self):
        task = task_fixture()
        task["units"] = [{"unit_id": "a", "oa_original_amount": "1000.00"}]
        task["allocations"] = [{"unit_id": "a", "amount": "1000.00"}]
        decision = automatic_source_allocations(task)
        self.assertEqual([line["bank_transaction_id"] for line in decision["cost_lines"]], ["bank1", "bank2"])

    def test_save_with_missing_metadata_stays_pending_and_keeps_decision(self):
        task = task_fixture()
        task["bank_events"][1]["bank_tag_code"] = ""
        task["bank_events"][1]["trade_time"] = ""
        result = complete_source_task(task, confirmed_decision())
        self.assertEqual(result["status"], "pending")
        self.assertEqual(result["pending_reasons"], ["bank_tag_missing", "source_date_missing"])
        self.assertEqual(result["source_allocations"], confirmed_decision())

    def test_refund_and_non_cost_close_original_source(self):
        task = task_fixture()
        task["oa_total"] = "1100.00"
        task["net_outflow_total"] = "900.00"
        task["allocations"][1]["amount"] = "200.00"
        task["non_cost_amount"] = "100.00"
        task["bank_events"].append({"transaction_id": "refund", "event_kind": "wrong_payment_refund", "amount": "100.00"})
        decision = confirmed_decision()
        decision["cost_lines"][2]["amount"] = "200.00"
        decision["refund_links"] = [{"refund_transaction_id": "refund", "bank_transaction_id": "bank2", "amount": "100.00"}]
        decision["non_cost_lines"] = [{"bank_transaction_id": "bank2", "amount": "100.00"}]
        self.assertEqual(validate_source_allocations(task, task["allocations"], Decimal("100"), decision), decision)
        self.assertIsNone(automatic_source_allocations(task))

    def test_stale_decision_never_reassigns_automatically(self):
        task = task_fixture()
        task["status"] = "stale"
        task["bank_events"] = [dict(task["bank_events"][0], amount="1000.00")]
        result = complete_source_task(task)
        self.assertIsNone(result["source_allocations"])
        self.assertEqual(result["pending_reasons"], ["allocation_stale"])


class SourceCostPolicyTests(unittest.TestCase):
    def setUp(self):
        from tests.test_cost_statistics_policy import CostStatisticsPolicyTests
        self.fixture = CostStatisticsPolicyTests()

    def test_one_unit_cross_month_has_two_source_cost_rows(self):
        f = self.fixture
        policy = f._policy([f._group(
            oa_rows=[f._oa("oa-1", amount="600.00")],
            bank_rows=[f._bank("bank-1", "350.00", trade_time="2026-08-01", tag_code="materials", tag_label="材料"),
                       f._bank("bank-2", "250.00", trade_time="2026-09-01", account_label="民生", tag_code="travel", tag_label="差旅")],
        )])
        rows = policy.serialized_cost_rows
        self.assertEqual({(r["transaction_id"], r["month"], r["amount"], r["bank_account_label"]) for r in rows},
                         {("bank-1", "2026-08", "350.00", "建设银行 8106"), ("bank-2", "2026-09", "250.00", "民生")})
        for view in ("project", "cost_tag", "bank_account"):
            for month, amount in (("2026-08", "350.00"), ("2026-09", "250.00")):
                page = policy.explorer_page(scope_kind="month", scope_value=month, view=view, filters={}, cursor_values=None, page_size=20)
                self.assertEqual(page["summary"]["total_amount"], amount)
                self.assertEqual(page["allocation_quality"]["undated_amount"], "0.00")
        for row in rows:
            detail = policy.allocation(allocation_id=row["allocation_id"], scope_kind="all", scope_value=None)
            self.assertEqual(detail["transaction_id"], row["transaction_id"])

    def test_ambiguous_known_amounts_have_no_invented_date_or_source(self):
        f = self.fixture
        policy = f._policy([f._group(oa_rows=[f._oa("a", amount="600.00"), f._oa("b", amount="400.00")],
                                    bank_rows=[f._bank("bank-1", "500.00"), f._bank("bank-2", "500.00")])])
        self.assertEqual(len(policy.serialized_cost_rows), 2)
        self.assertTrue(all(row["occurred_at"] is None and row["transaction_id"] is None for row in policy.serialized_cost_rows))
        page = policy.explorer_page(scope_kind="month", scope_value="2026-05", view="project", filters={}, cursor_values=None, page_size=20)
        self.assertEqual(page["summary"]["total_amount"], "0.00")
        self.assertEqual(page["allocation_quality"]["undated_amount"], "1000.00")
        exported = policy.export_page(month="all", start_month=None, end_month=None, start_date=None, end_date="2026-12-31", project_names=[], bank_tag_primary_keys=[], row_shape="raw_cost", offset=0, page_size=20, include_summary=True)
        self.assertEqual(exported["rows"], [])

    def test_leaf_selection_preserves_sibling_facets(self):
        f = self.fixture
        bank1 = f._bank("bank-1", "50.00", tag_code="a", tag_label="采购")
        bank1["bank_tag_sub_label"] = "材料"
        bank2 = f._bank("bank-2", "50.00", tag_code="b", tag_label="采购")
        bank2["bank_tag_sub_label"] = "设备"
        policy = f._policy([f._group(oa_rows=[f._oa("a", amount="100.00")], bank_rows=[bank1, bank2])])
        page = policy.explorer_page(scope_kind="all", scope_value=None, view="project", filters={"project_name": "项目A", "bank_tag_primary_key": "label:采购", "bank_tag_sub_key": "label:材料"}, cursor_values=None, page_size=20)
        self.assertEqual({r["label"] for r in page["tertiary_facets"]}, {"材料", "设备"})
        self.assertEqual([r["amount"] for r in page["rows"]], ["50.00"])
        self.assertEqual(page["summary"]["total_amount"], "100.00")


class SourceSuggestionTests(unittest.TestCase):
    def fixture(self):
        task = complete_source_task(task_fixture())
        task['version'] = 0
        for unit in task['units']:
            unit['oa_id'] = unit['unit_id']
        task['bank_events'][0]['amount'] = '600.00'
        task['bank_events'][1]['amount'] = '400.00'
        return task

    def suggest(self, task, owners):
        from fin_ops_platform.services.cost_statistics_source_allocation import suggest_source_allocations
        return suggest_source_allocations(task, [
            {'id': key, 'source_oa_ids': value} for key, value in owners.items()
        ])

    def test_exact_amounts_without_source_proof_stay_manual(self):
        task = self.fixture()
        self.assertIsNone(self.suggest(task, {'bank1': [], 'bank2': []}))

    def test_explicit_owners_produce_draft_without_completing_task(self):
        task = self.fixture()
        before = deepcopy(task)
        suggestion = self.suggest(task, {'bank1': ['a'], 'bank2': ['b']})
        self.assertEqual(suggestion['cost_lines'], [
            {'unit_id': 'a', 'bank_transaction_id': 'bank1', 'amount': '600.00'},
            {'unit_id': 'b', 'bank_transaction_id': 'bank2', 'amount': '400.00'},
        ])
        self.assertEqual(task, before)
        self.assertEqual(task['status'], 'pending')
        self.assertIsNone(task['source_allocations'])

    def test_one_oa_multiple_sources_and_partial_proof(self):
        task = self.fixture()
        task['bank_events'][0]['amount'] = '350.00'
        task['bank_events'].append({**task['bank_events'][0], 'transaction_id': 'bank3', 'amount': '250.00'})
        result = self.suggest(task, {'bank1': ['a'], 'bank3': ['a'], 'bank2': []})
        self.assertEqual([line['amount'] for line in result['cost_lines']], ['350.00', '250.00'])
        self.assertIsNone(self.suggest(task, {'bank1': ['a'], 'bank3': [], 'bank2': []}))

    def test_one_source_multiple_cost_items_requires_known_parent_and_targets(self):
        task = self.fixture()
        task['units'][0]['oa_original_amount'] = '350.00'
        task['units'].append({'unit_id': 'a-item-2', 'oa_id': 'a', 'oa_original_amount': '250.00'})
        result = self.suggest(task, {'bank1': ['a'], 'bank2': ['b']})
        self.assertEqual([line['amount'] for line in result['cost_lines']], ['350.00', '250.00', '400.00'])
        task['bank_events'][0]['amount'] = '300.00'
        task['bank_events'].append({**task['bank_events'][0], 'transaction_id': 'bank3'})
        result = self.suggest(task, {'bank1': ['a'], 'bank3': ['a'], 'bank2': ['b']})
        self.assertEqual([line['unit_id'] for line in result['cost_lines']], ['b'])

    def test_conflicting_owners_never_use_first_reference(self):
        task = self.fixture()
        self.assertIsNone(self.suggest(task, {'bank1': ['a', 'b'], 'bank2': ['b']}))
        self.assertIsNone(self.suggest(task, {'bank1': ['outside'], 'bank2': []}))

    def test_saved_stale_variable_targets_and_refunds_do_not_prefill(self):
        for patch in ({'version': 1}, {'pending_reasons': ['allocation_stale']},
                      {'amounts_fixed': False}, {'non_cost_amount': '1.00'}, {'status': 'allocated'}):
            with self.subTest(patch=patch):
                task = self.fixture() | patch
                self.assertIsNone(self.suggest(task, {'bank1': ['a'], 'bank2': ['b']}))
        task = self.fixture()
        task['bank_events'].append({**task['bank_events'][0], 'transaction_id': 'refund', 'event_kind': 'wrong_payment_refund'})
        self.assertIsNone(self.suggest(task, {'bank1': ['a'], 'bank2': ['b']}))

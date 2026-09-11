from copy import deepcopy

import pytest
from fin_ops_platform.services.cost_statistics_policy import CostStatisticsPolicy
from fin_ops_platform.services.cost_statistics_scope import PROJECT_COST_SCOPE_KEY, read_project_cost_scope

from tests import test_cost_statistics_policy as fixtures


def scope(codes):
    return {PROJECT_COST_SCOPE_KEY: {"version": 1, "selected_tag_codes": codes}}


def total(policy):
    totals = [policy.explorer_page(scope_kind="all", scope_value=None, view=view,
              filters={}, cursor_values=None, page_size=20)["summary"]["total_amount"]
              for view in ("project", "cost_tag", "bank_account")]
    assert len(set(totals)) == 1
    return totals[0]


def test_mixed_sources_filter_after_full_allocation_and_restore_facts():
    group = fixtures.CostStatisticsPolicyTests._group(oa_rows=[fixtures.CostStatisticsPolicyTests._oa("a", amount="100.00")], bank_rows=[
        fixtures.CostStatisticsPolicyTests._bank("b", "60.00", tag_code="material"),
        fixtures.CostStatisticsPolicyTests._bank("c", "40.00", tag_code="internal_transfer")])
    original = deepcopy(group)
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["material"]))) == "60.00"
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope([]))) == "0.00"
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["material", "internal_transfer"]))) == "100.00"
    assert group == original


def test_refund_is_deducted_even_when_income_tag_not_selected():
    group = fixtures.CostStatisticsPolicyTests._group(oa_rows=[fixtures.CostStatisticsPolicyTests._oa("a", amount="800.00")], bank_rows=[
        fixtures.CostStatisticsPolicyTests._bank("b", "1000.00", tag_code="material"),
        fixtures.CostStatisticsPolicyTests._bank("r", "200.00", direction="inflow", tag_code="refund", tag_label="付错退款")])
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["material"]))) == "800.00"
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope([]))) == "0.00"


def test_unknown_tags_require_explicit_selection_and_missing_date_is_not_a_gate():
    group = fixtures.CostStatisticsPolicyTests._group(oa_rows=[fixtures.CostStatisticsPolicyTests._oa("a", amount="100.00")], bank_rows=[
        fixtures.CostStatisticsPolicyTests._bank("b", "100.00", tag_code="", trade_time="")])
    assert total(fixtures.CostStatisticsPolicyTests._policy([group], settings=scope([]))) == "0.00"
    policy = fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["uncategorized"]))
    assert total(policy) == "100.00"
    assert policy.serialized_cost_rows[0]["occurred_at"] is None


def test_unresolved_tasks_use_scoped_sources_without_changing_fact_identity():
    group = fixtures.CostStatisticsPolicyTests._group(oa_rows=[fixtures.CostStatisticsPolicyTests._oa("a", amount="60.00"), fixtures.CostStatisticsPolicyTests._oa("b", amount="40.00")],
        bank_rows=[fixtures.CostStatisticsPolicyTests._bank("x", "50.00"), fixtures.CostStatisticsPolicyTests._bank("y", "50.00", tag_code="internal_transfer")])
    included = fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["material"]))
    excluded = fixtures.CostStatisticsPolicyTests._policy([group], settings=scope([]))
    a, b = included.manual_allocation_tasks[0], excluded.manual_allocation_tasks[0]
    assert a["in_project_cost_scope"] and not b["in_project_cost_scope"]
    assert a["source_fingerprint"] == b["source_fingerprint"]
    assert [e["transaction_id"] for e in a["bank_events"]] == ["x"]
    assert a["net_outflow_total"] == "50.00"
    assert b["bank_events"] == []
    assert total(included) == "0.00"
    assert included.allocation_quality["pending_manual_allocation_count"] == 1
    assert excluded.allocation_quality["pending_manual_allocation_count"] == 0


def test_missing_scope_fails_only_project_cost_reads():
    policy = CostStatisticsPolicy({"settings": {}, "bank_rows": [], "groups": [], "bank_statistics": {}})
    with pytest.raises(ValueError, match="未初始化"):
        total(policy)
    assert policy.explorer_page(scope_kind="all", scope_value=None, view="time", filters={},
        cursor_values=None, page_size=20)["summary"]["total_amount"] == "0.00"


@pytest.mark.parametrize("value", [None, {}, {"version": True, "selected_tag_codes": []},
    {"version": 1, "selected_tag_codes": ["a", "a"]}, {"version": 1, "selected_tag_codes": [" a"]}])
def test_invalid_configuration_is_not_replaced_by_default_selection(value):
    with pytest.raises(ValueError):
        read_project_cost_scope({PROJECT_COST_SCOPE_KEY: value})


def test_excluded_loan_2100_leaves_only_hotel_without_auto_confirming():
    f = fixtures.CostStatisticsPolicyTests
    group = f._group(oa_rows=[f._oa('oa-hotel', amount='2100.00')], bank_rows=[
        f._bank('loan', '2100.00', tag_code='external_turnover'),
        f._bank('hotel', '2100.00', tag_code='material')])
    policy = f._policy([group], settings=scope(['material']))
    task = policy.manual_allocation_tasks[0]
    assert [e['transaction_id'] for e in task['bank_events']] == ['hotel']
    assert task['net_outflow_total'] == task['oa_total'] == '2100.00'
    assert task['difference'] == '0.00'
    assert task['status'] == 'pending'
    assert task['source_allocations'] is None
    assert total(policy) == '0.00'
    assert len(group['bank_rows']) == 2


def test_unknown_refund_in_mixed_scope_is_not_guessed():
    f = fixtures.CostStatisticsPolicyTests
    group = f._group(oa_rows=[f._oa('a', amount='500.00'), f._oa('b', amount='300.00')], bank_rows=[
        f._bank('x', '500.00'), f._bank('y', '500.00', tag_code='internal_transfer'),
        f._bank('r', '200.00', direction='inflow', tag_code='refund', tag_label='付错退款')])
    policy = f._policy([group], settings=scope(['material']))
    task = policy.manual_allocation_tasks[0]
    assert task['pending_reasons'] == ['scope_refund_required']
    assert total(policy) == '0.00'


def test_explicit_refund_split_follows_source_and_preserves_original_fact():
    from fin_ops_platform.services.cost_statistics_allocation_scope import project_source_task
    from tests.test_cost_statistics_source_allocation import task_fixture
    task = task_fixture()
    task.update(version=1, non_cost_amount='0.00')
    task['bank_events'][0]['in_project_cost_scope'] = True
    task['bank_events'][1]['in_project_cost_scope'] = False
    task['bank_events'].append({'transaction_id': 'r', 'event_kind': 'wrong_payment_refund', 'amount': '200.00'})
    decision = {'cost_lines': [
        {'unit_id': 'a', 'bank_transaction_id': 'bank1', 'amount': '450.00'},
        {'unit_id': 'b', 'bank_transaction_id': 'bank2', 'amount': '350.00'}],
        'refund_links': [
            {'refund_transaction_id': 'r', 'bank_transaction_id': 'bank1', 'amount': '50.00'},
            {'refund_transaction_id': 'r', 'bank_transaction_id': 'bank2', 'amount': '150.00'}],
        'non_cost_lines': []}
    original = deepcopy(task)
    result = project_source_task(task, decision)
    assert result['net_outflow_total'] == '450.00'
    assert result['wrong_payment_refund_total'] == '50.00'
    assert result['source_allocations']['refund_links'] == decision['refund_links'][:1]
    assert [u['unit_id'] for u in result['units']] == ['a']
    assert task == original

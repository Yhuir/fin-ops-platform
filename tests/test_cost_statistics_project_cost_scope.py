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


def test_unresolved_tasks_keep_full_sources_and_scope_does_not_change_identity():
    group = fixtures.CostStatisticsPolicyTests._group(oa_rows=[fixtures.CostStatisticsPolicyTests._oa("a", amount="60.00"), fixtures.CostStatisticsPolicyTests._oa("b", amount="40.00")],
        bank_rows=[fixtures.CostStatisticsPolicyTests._bank("x", "50.00"), fixtures.CostStatisticsPolicyTests._bank("y", "50.00", tag_code="internal_transfer")])
    included = fixtures.CostStatisticsPolicyTests._policy([group], settings=scope(["material"]))
    excluded = fixtures.CostStatisticsPolicyTests._policy([group], settings=scope([]))
    a, b = included.manual_allocation_tasks[0], excluded.manual_allocation_tasks[0]
    assert a["in_project_cost_scope"] and not b["in_project_cost_scope"]
    assert a["source_fingerprint"] == b["source_fingerprint"]
    assert len(a["bank_events"]) == 2
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

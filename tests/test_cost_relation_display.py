from copy import deepcopy

import pytest
from fin_ops_platform.services.cost_statistics_canonical_repository import (
    _attach_relation_display,
    _attach_source_relations,
)
from fin_ops_platform.services.cost_statistics_manual_allocation_service import _relation_display_groups
from fin_ops_platform.services.workbench_display_subgroups import apply_display_subgroups

from tests.test_workbench_display_subgroups import event, group, relation, row


@pytest.mark.parametrize('amounts,parts', [([199]*7, [[164,35]]*7), ([2000,1500,1500,2000,2000], [[2000],[1500],[1500],[2000],[2000]]), ([2329.32,4426.11], [[100]*7+[1629.32],[500]*7+[926.11]])])
def test_cost_and_workbench_share_history_partition(amounts, parts):
    oas = [row('oa', f'o{i}', a) for i,a in enumerate(amounts)]
    banks = [row('bank',f'b{i}-{j}',a) for i,values in enumerate(parts) for j,a in enumerate(values)]
    rows = oas+banks
    history = [event(relation('merged',rows),[relation(f'old{i}',[oa,*[b for b in banks if b['id'].startswith(f'b{i}-')]]) for i,oa in enumerate(oas)])]
    wb=group(rows)
    cost={'group_id':'merged','row_ids':wb['formal_member_ids'],'row_types':wb['formal_member_types'],'oa_rows':oas,'bank_rows':banks}
    before=deepcopy(cost)
    apply_display_subgroups([wb],history)
    _attach_source_relations([cost], history)
    _attach_relation_display(cost, history)
    assert cost.pop('relation_display_groups')==wb['display_subgroups']
    cost.pop('source_relation_groups')
    assert cost==before
    _attach_source_relations([cost], history)
    _attach_relation_display(cost, history)
    task={'units':[{'unit_id':f'unit-{r["id"]}','oa_id':r['id']} for r in oas], 'bank_events':[{'transaction_id':r['id']} for r in banks]}
    blocks=_relation_display_groups(task,cost)
    assert len(blocks)==len(oas)
    assert sum(len(b['bank_transaction_ids']) for b in blocks)==len(banks)
    # Scope clipping keeps original blocks and never assigns a remaining bank to a different OA.
    task['bank_events']=task['bank_events'][1:]
    assert _relation_display_groups(task,cost)[0]['bank_transaction_ids']==blocks[0]['bank_transaction_ids'][1:]


def test_itemized_oa_keeps_shared_parent_without_inventing_cost_splits():
    oa={**row('oa','oa',100),'expense_items':[{'expense_item_id':'a'},{'expense_item_id':'b'}]}
    cost={'group_id':'one','row_ids':['oa','bank'],'row_types':['oa','bank'],'oa_rows':[oa],'bank_rows':[row('bank','bank',90)]}
    _attach_source_relations([cost], [])
    _attach_relation_display(cost, [])
    task={'units':[{'unit_id':'a','oa_id':'oa'},{'unit_id':'b','oa_id':'oa'}],'bank_events':[]}
    assert _relation_display_groups(task,cost)==[{'unit_ids':['a','b'],'bank_transaction_ids':[],'sources_excluded':True}]


@pytest.mark.parametrize('amounts,parts', [
    ([199,202,199.30,199,199,209.20,199], [[164,35],[167,35],[164.10,35.20],[164,35],[164,35],[174.20,35],[164,35]]),
    ([2000,1500,1500,2000,2000], [[2000],[1500],[1500],[2000],[2000]]),
    ([2329.32,4426.11], [[100]*7+[1629.32],[500]*7+[926.11]]),
])
def test_formal_partitions_prefill_every_source_without_changing_task(amounts, parts):
    from decimal import Decimal

    from fin_ops_platform.services.cost_statistics_source_allocation import (
        suggest_source_allocations,
        validate_source_allocations,
    )

    from tests.test_cost_statistics_source_allocation import SourceSuggestionTests
    task = SourceSuggestionTests().amount_case(amounts, [a for part in parts for a in part])
    oas = [row('oa', u['oa_id'], u['oa_original_amount']) for u in task['units']]
    banks = [row('bank', e['transaction_id'], e['amount']) for e in task['bank_events']]
    rows = oas + banks
    prior = []; offset = 0; expected = []
    for oa, unit, part in zip(oas, task['units'], parts, strict=True):
        subset = banks[offset:offset+len(part)]
        prior.append(relation('old-'+oa['id'], [oa, *subset]))
        expected.extend({'unit_id': unit['unit_id'], 'bank_transaction_id': b['id'], 'amount': f"{Decimal(b['amount']):.2f}"} for b in subset)
        offset += len(part)
    cost = {'group_id':'merged','row_ids':[r['id'] for r in rows], 'row_types':[r['type'] for r in rows], 'oa_rows':oas,'bank_rows':banks}
    _attach_source_relations([cost], [event(relation('merged', rows), prior)])
    _attach_relation_display(cost, [event(relation('merged', rows), prior)])
    before = deepcopy(task)
    suggestion = suggest_source_allocations(task, banks, cost['source_relation_groups'])
    assert suggestion['cost_lines'] == expected
    validate_source_allocations(task, [{'unit_id':u['unit_id'],'amount':u['oa_original_amount']} for u in task['units']], Decimal(0), suggestion)
    assert task == before
    assert task['source_allocations'] is None


def test_amount_display_is_not_ownership_and_old_history_cannot_leak():
    from fin_ops_platform.services.cost_statistics_source_allocation import suggest_source_allocations

    from tests.test_cost_statistics_source_allocation import SourceSuggestionTests
    task = SourceSuggestionTests().amount_case([300,200,100], [300,200,100])
    rows = [row('oa',u['oa_id'],u['oa_original_amount']) for u in task['units']] + [row('bank',e['transaction_id'],e['amount']) for e in task['bank_events']]
    cost = {'group_id':'reused','row_ids':[r['id'] for r in rows], 'row_types':[r['type'] for r in rows], 'oa_rows':rows[:3],'bank_rows':rows[3:]}
    outdated = relation('reused', rows[:-1])
    history = [event(outdated, [relation('old', [rows[0], rows[3]])])]
    _attach_source_relations([cost], history)
    _attach_relation_display(cost, history)
    assert len(cost['relation_display_groups']) == 3  # Amount-based visual alignment.
    assert len(cost['source_relation_groups']) == 1  # No matching historical snapshot.
    assert suggest_source_allocations(task, cost['bank_rows'], cost['source_relation_groups']) is None


def test_scope_clipping_and_conflicting_references_cannot_borrow_other_group_source():
    from fin_ops_platform.services.cost_statistics_source_allocation import suggest_source_allocations

    from tests.test_cost_statistics_source_allocation import SourceSuggestionTests
    task = SourceSuggestionTests().amount_case([100,100], [100,100])
    groups = [{'oa_row_ids':['0'],'bank_row_ids':['0']}, {'oa_row_ids':['1'],'bank_row_ids':['1']}]
    assert suggest_source_allocations(task, [{'id':'0','source_oa_ids':['1']}], groups) is None
    # If scope removes the only source of unit 0, it cannot take the equal source of unit 1.
    task['bank_events'] = task['bank_events'][1:]
    task['net_outflow_total'] = task['oa_total'] = '100.00'
    task['units'] = task['units'][:1]
    assert suggest_source_allocations(task, [], groups) is None


def test_itemized_parent_does_not_imply_arbitrary_cost_split():
    from fin_ops_platform.services.cost_statistics_source_allocation import suggest_source_allocations

    from tests.test_cost_statistics_source_allocation import SourceSuggestionTests
    task = SourceSuggestionTests().amount_case([100,100], [100,100])
    for u in task['units']:
        u['oa_id'] = 'parent'
    assert suggest_source_allocations(task, [], [{'oa_row_ids':['parent'],'bank_row_ids':['0','1']}]) is None



def test_installment_display_does_not_change_cost_source_history_or_facts():
    from fin_ops_platform.services.cost_statistics_canonical_repository import _cost_oa_payload

    from tests.test_workbench_display_subgroups import installment_rows
    rows = installment_rows()
    # Exercise the Cost projection instead of giving display a Workbench DTO.
    rows[:2] = [{**_cost_oa_payload({**r, 'detail_fields': {'申请日期': r['application_date']}}, row_id=r['id']), 'type': 'oa'} for r in rows[:2]]
    old = relation("old", [rows[0], *rows[2:]])
    history = [event(relation("merged", rows), [old])]
    cost = {"group_id": "merged", "row_ids": [r["id"] for r in rows], "row_types": [r["type"] for r in rows], "oa_rows": rows[:2], "bank_rows": rows[2:4]}
    _attach_source_relations([cost], history)
    before = deepcopy(cost)
    _attach_relation_display(cost, history)
    assert cost.pop("relation_display_groups") == [
        {"resolved": True, "oa_row_ids": ["prepay"], "bank_row_ids": ["bank-prepay"]},
        {"resolved": True, "oa_row_ids": ["final"], "bank_row_ids": ["bank-final"]},
    ]
    assert cost == before

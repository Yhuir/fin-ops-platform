from copy import deepcopy

import pytest
from fin_ops_platform.services.cost_statistics_canonical_repository import _attach_relation_display
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
    _attach_relation_display(cost,history)
    assert cost.pop('relation_display_groups')==wb['display_subgroups']
    assert cost==before
    _attach_relation_display(cost,history)
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
    _attach_relation_display(cost,[])
    task={'units':[{'unit_id':'a','oa_id':'oa'},{'unit_id':'b','oa_id':'oa'}],'bank_events':[]}
    assert _relation_display_groups(task,cost)==[{'unit_ids':['a','b'],'bank_transaction_ids':[],'sources_excluded':True}]

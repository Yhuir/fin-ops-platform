import { act, render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, expect, it, vi } from 'vitest';
import Drawer from '../components/cost-statistics/CostStatisticsManualAllocationDrawer';
import { fetchCostStatisticsManualAllocation, fetchCostStatisticsManualAllocations, saveCostStatisticsManualAllocation } from '../features/cost-statistics/api';
import type { CostStatisticsManualAllocationTask } from '../features/cost-statistics/types';
vi.mock('../features/cost-statistics/api',()=>({fetchCostStatisticsManualAllocation:vi.fn(),fetchCostStatisticsManualAllocations:vi.fn(),saveCostStatisticsManualAllocation:vi.fn()}));
let task:CostStatisticsManualAllocationTask;
beforeEach(()=>{
 vi.clearAllMocks();
 task={relationCaseId:'case',relationVersion:1,sourceFingerprint:'first',scopeVersion:1,status:'pending',pendingReasons:['source_required'],amountsFixed:true,oaTotal:'100.00',grossOutflowTotal:'100.00',wrongPaymentRefundTotal:'0.00',netOutflowTotal:'100.00',nonCostAmount:'0.00',nonCostReason:'',version:0,updatedBy:'',updatedAt:'',canSave:true,
 units:[{unitId:'u',oaId:'o',oaApplyType:'支付申请',expenseItemId:'',projectId:'p',projectName:'项目',expenseType:'材料',expenseContent:'原始费用',oaApplicant:'申请人',oaOriginalAmount:'100.00'}],
 bankEvents:[{transactionId:'b',eventKind:'outflow',inProjectCostScope:true,amount:'100.00',tradeTime:'2026-09-01',counterpartyName:'供应商',bankAccountLabel:'建行 8106',bankTagCode:'material',bankTagPrimaryLabel:'材料',bankTagSubLabel:'采购',tags:[]}],
 allocations:[{unitId:'u',amount:'100.00'}],sourceAllocations:null,suggestedSourceAllocations:{costLines:[{unitId:'u',bankTransactionId:'b',amount:'100.00'}],refundLinks:[],nonCostLines:[]},relationDisplayGroups:[{unitIds:['u'],bankTransactionIds:['b'],sourcesExcluded:false}]};
 vi.mocked(fetchCostStatisticsManualAllocations).mockImplementation(async()=>({items:[{...task,projectNames:['项目'],unitCount:1,bankEventCount:1}],counts:{pending:1,allocated:0},rowCount:1}));
 vi.mocked(fetchCostStatisticsManualAllocation).mockImplementation(async()=>structuredClone(task));
});
it('refreshes formal facts while preserving a conflicting dirty draft until explicit reload',async()=>{
 const user=userEvent.setup();const props={canSave:true,onSaved:vi.fn(),refreshKey:'1'};
 const view=render(<Drawer {...props}/>);await user.click(screen.getByRole('button',{name:'打开成本人工分配'}));
 const input=await screen.findByRole('textbox',{name:'分配金额 1'});
 await user.clear(input);await user.type(input,'80');
 task={...task,sourceFingerprint:'changed',relationVersion:2,units:task.units.map(u=>({...u,expenseContent:'更新的费用'}))};
 view.rerender(<Drawer {...props} refreshKey="2"/>);
 await screen.findByText('关联或分配已变化，草稿已保留；请重新加载后核对');
 expect(input).toHaveValue('80');expect(screen.getByRole('button',{name:'保存分配'})).toBeDisabled();
 expect(within(screen.getByRole('table',{name:'OA 与流水对照'})).getByText('更新的费用')).toBeVisible();
 // Further refresh cannot clear the conflict or overwrite the draft.
 view.rerender(<Drawer {...props} refreshKey="3"/>);await waitFor(()=>expect(fetchCostStatisticsManualAllocation).toHaveBeenCalledTimes(3));
 expect(screen.getByRole('button',{name:'保存分配'})).toBeDisabled();
 vi.spyOn(window,'confirm').mockReturnValue(true);
 await user.click(screen.getByRole('button',{name:'重新加载'}));
 await waitFor(()=>expect(input).toHaveValue('100.00'));
 expect(screen.queryByText('关联或分配已变化，草稿已保留；请重新加载后核对')).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'保存分配'})).not.toBeDisabled();expect(saveCostStatisticsManualAllocation).not.toHaveBeenCalled();
});
it('ignores an obsolete detail response after a newer refresh',async()=>{
 let finish!:(t:CostStatisticsManualAllocationTask)=>void;
 vi.mocked(fetchCostStatisticsManualAllocation).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
 const user=userEvent.setup();const props={canSave:true,onSaved:vi.fn()};const view=render(<Drawer {...props} refreshKey="1"/>);
 await user.click(screen.getByRole('button',{name:'打开成本人工分配'}));await waitFor(()=>expect(finish).toBeDefined());
 const old=structuredClone(task);task={...task,units:task.units.map(u=>({...u,expenseContent:'最新费用'}))};
 view.rerender(<Drawer {...props} refreshKey="2"/>);await screen.findAllByText('最新费用');
 await act(async()=>finish(old));expect(screen.queryByText('原始费用')).not.toBeInTheDocument();
});
it('rechecks an open drawer on window focus even without a page refresh',async()=>{
 const user=userEvent.setup();render(<Drawer canSave onSaved={vi.fn()}/>);await user.click(screen.getByRole('button',{name:'打开成本人工分配'}));await screen.findAllByText('原始费用');
 task={...task,units:task.units.map(u=>({...u,expenseContent:'另一个页面修改'}))};
 await act(async()=>window.dispatchEvent(new Event('focus')));await screen.findAllByText('另一个页面修改');
 expect(saveCostStatisticsManualAllocation).not.toHaveBeenCalled();
});

it('reopens an inactive task whose earlier request was aborted by refresh', async () => {
  const summary = {...task, projectNames:['项目'], unitCount:1, bankEventCount:1};
  vi.mocked(fetchCostStatisticsManualAllocations).mockResolvedValue({items:[summary,{...summary,relationCaseId:'case-2',projectNames:['项目二']}],counts:{pending:2,allocated:0},rowCount:2});
  let finish!:(t:CostStatisticsManualAllocationTask)=>void;
  vi.mocked(fetchCostStatisticsManualAllocation).mockImplementationOnce(()=>new Promise(resolve=>{finish=resolve;}));
  const user=userEvent.setup();
  const view=render(<Drawer canSave onSaved={vi.fn()} refreshKey="1"/>);
  await user.click(screen.getByRole('button',{name:'打开成本人工分配'}));
  await waitFor(()=>expect(finish).toBeDefined());
  await user.click(screen.getByRole('button',{name:/项目二/}));
  await screen.findAllByText('原始费用');
  view.rerender(<Drawer canSave onSaved={vi.fn()} refreshKey="2"/>);
  await waitFor(()=>expect(fetchCostStatisticsManualAllocation).toHaveBeenCalledTimes(3));
  await user.click(document.querySelectorAll<HTMLButtonElement>('.cost-source-task-heading')[0]);
  await waitFor(()=>expect(fetchCostStatisticsManualAllocation).toHaveBeenCalledTimes(4));
  await screen.findAllByText('原始费用');
  await act(async()=>finish(task));
});

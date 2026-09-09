import { Button, Chip } from '@heroui/react';
import { ChevronRight, Search } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { ApiClientError } from '../../features/apiClient';
import AppDrawer from '../common/AppDrawer';
import CostSourceAllocationForm from './CostSourceAllocationForm';
import { fetchCostStatisticsManualAllocation, fetchCostStatisticsManualAllocations, saveCostStatisticsManualAllocation } from '../../features/cost-statistics/api';
import { createSourceDraft, sourceDecisionMatches, sourceSaveRequest, type SourceDraft } from '../../features/cost-statistics/sourceAllocation';
import type { CostStatisticsManualAllocationSummary, CostStatisticsManualAllocationTask, SaveCostStatisticsManualAllocationRequest } from '../../features/cost-statistics/types';
import './costSourceAllocation.css';

type Props = { canSave: boolean; pendingCount?: number; onSaved: () => void };
type TaskState = { task?: CostStatisticsManualAllocationTask; draft?: SourceDraft; dirty?: boolean; loading?: boolean; saving?: boolean; error?: string; notice?: string; unconfirmedRequest?: SaveCostStatisticsManualAllocationRequest };
export default function CostStatisticsManualAllocationDrawer({ canSave, pendingCount, onSaved }: Props) {
  const [open, setOpen] = useState(false);
  const [status, setStatus] = useState<'pending' | 'allocated'>('pending');
  const [queryDraft, setQueryDraft] = useState('');
  const [query, setQuery] = useState('');
  const [items, setItems] = useState<CostStatisticsManualAllocationSummary[]>([]);
  const [counts, setCounts] = useState<{ pending: number; allocated: number } | null>(null);
  const [nextCursor, setNextCursor] = useState<string>();
  const [expanded, setExpanded] = useState<string | null>(null);
  const [states, setStates] = useState<Record<string, TaskState>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string>();
  const listRequest = useRef<AbortController | null>(null);
  const details = useRef(new Map<string, AbortController>());
  const currentStates = useRef(states); currentStates.current = states;
  const saving = Object.values(states).some(state => state.saving);
  const setCase = (id: string, patch: Partial<TaskState>) => setStates(current => ({ ...current, [id]: { ...current[id], ...patch } }));
  const loadDetail = async (id: string, force = false) => {
    const current = currentStates.current[id];
    if (!force && (current?.task || current?.loading)) return;
    details.current.get(id)?.abort();
    const controller = new AbortController(); details.current.set(id, controller);
    setCase(id, { loading: true, error: undefined });
    try {
      const task = await fetchCostStatisticsManualAllocation(id, controller.signal);
      if (controller.signal.aborted) return;
      setCase(id, { task, draft: createSourceDraft(task), dirty: false, loading: false, notice: undefined, unconfirmedRequest: undefined });
    } catch (caught) {
      if (!controller.signal.aborted) setCase(id, { loading: false, error: '任务读取失败，请重试' });
    } finally { if (details.current.get(id) === controller) details.current.delete(id); }
  };
  const load = async (targetStatus = status, targetQuery = query, cursor?: string) => {
    listRequest.current?.abort(); const controller = new AbortController(); listRequest.current = controller;
    setLoading(true); setError(undefined);
    try {
      const page = await fetchCostStatisticsManualAllocations({ status: targetStatus, query: targetQuery || undefined, pageSize: 30, cursor, signal: controller.signal });
      if (controller.signal.aborted) return;
      setItems(current => cursor ? [...current, ...page.items.filter(item => !current.some(old => old.relationCaseId === item.relationCaseId))] : page.items);
      setCounts(page.counts); setNextCursor(page.nextCursor);
      if (!cursor) {
        const first = page.items[0]?.relationCaseId ?? null;
        setExpanded(first); if (first) void loadDetail(first);
      }
    } catch (caught) { if (!controller.signal.aborted) setError('人工分配任务加载失败，请重试'); }
    finally { if (listRequest.current === controller) setLoading(false); }
  };
  useEffect(() => () => { listRequest.current?.abort(); details.current.forEach(controller => controller.abort()); }, []);
  const acceptSaved = (id: string, saved: CostStatisticsManualAllocationTask) => {
    const previous = currentStates.current[id].task;
    setCase(id, { task: saved, draft: createSourceDraft(saved), dirty: false, saving: false, error: undefined, unconfirmedRequest: undefined, notice: saved.status === 'allocated' ? '分配已保存' : '已保存，银行信息待完善' });
    if (previous && saved.status !== previous.status) setCounts(value => value ? { pending: value.pending + (saved.status === 'pending' ? 1 : -1), allocated: value.allocated + (saved.status === 'allocated' ? 1 : -1) } : null);
    if (saved.status !== status) {
      setItems(list => list.filter(item => item.relationCaseId !== id)); setExpanded(null);
      requestAnimationFrame(() => {
        const nextHeading = document.querySelector<HTMLElement>('.cost-source-task-heading');
        if (nextHeading) nextHeading.focus();
        else document.querySelector<HTMLElement>('.cost-source-body [role="radio"][aria-checked="true"]')?.focus();
      });
    }
    // The write is already acknowledged. Page refresh failures must never retry the PUT.
    try { onSaved(); } catch { setError('分配已保存，列表刷新失败，请重试读取'); }
  };
  const verifySave = async (id: string) => {
    const request = currentStates.current[id]?.unconfirmedRequest;
    if (!request) return;
    setCase(id, { saving: true, error: undefined });
    try {
      const task = await fetchCostStatisticsManualAllocation(id);
      if (sourceDecisionMatches(request, task)) acceptSaved(id, task);
      else setCase(id, { saving: false, error: '未确认本次保存。请重新读取当前事实并核对，草稿已保留。' });
    } catch { setCase(id, { saving: false, error: '保存结果暂时无法核实，请重试读取' }); }
  };
  const save = async (id: string) => {
    const current = currentStates.current[id];
    if (!current.task || !current.draft || current.saving || current.unconfirmedRequest || !canSave || !current.task.canSave) return;
    const request = sourceSaveRequest(current.task, current.draft);
    setCase(id, { saving: true, error: undefined, notice: undefined });
    let saved: CostStatisticsManualAllocationTask;
    try { saved = await saveCostStatisticsManualAllocation(request); }
    catch (caught) {
      if (caught instanceof ApiClientError && caught.status >= 400 && caught.status < 500) {
        setCase(id, { saving: false, error: caught.status === 409 ? '关联事实已变化，请重新读取并核对；草稿已保留' : caught.status === 403 ? '当前无保存权限' : '分配未保存，请核对金额和来源；草稿已保留' });
      } else {
        setCase(id, { saving: false, unconfirmedRequest: request, error: '保存结果待确认，请核实保存结果；草稿已保留' });
      }
      return;
    }
    acceptSaved(id, saved);
  };
  const close = () => {
    if (saving) return;
    if (Object.values(states).some(state => state.dirty) && !window.confirm('有未保存的分配，关闭将丢弃这些修改。是否关闭？')) return;
    listRequest.current?.abort(); details.current.forEach(controller => controller.abort());
    setStates({}); setExpanded(null); setOpen(false);
  };
  return <>
    <Button aria-label="打开成本人工分配" className="cost-page-action cost-manual-allocation-trigger" size="sm" variant="secondary" onPress={() => { setOpen(true); void load(); }}>
      待分配{(pendingCount ?? counts?.pending) !== undefined ? <Chip color="warning" size="sm" variant="soft">{pendingCount ?? counts?.pending}</Chip> : null}
    </Button>
    <AppDrawer open={open} title="成本人工分配" width="min(1320px, 100vw)" className="cost-source-drawer" onClose={close} closeDisabled={saving}>
      <div className="cost-source-body">
        <div className="cost-source-toolbar">
          <div className="cost-source-tabs" role="radiogroup" aria-label="成本人工分配状态">
            {(['pending', 'allocated'] as const).map(value => <button type="button" role="radio" aria-checked={status === value} key={value} disabled={saving} onClick={() => { setStatus(value); void load(value); }}>
              {value === 'pending' ? '待分配' : '已完成'} <span>{counts ? counts[value] : value === 'pending' ? pendingCount ?? '—' : '—'}</span>
            </button>)}
          </div>
          <form className="cost-source-search" onSubmit={event => { event.preventDefault(); if (saving) return; setQuery(queryDraft.trim()); void load(status, queryDraft.trim()); }}>
            <input aria-label="搜索人工分配任务" placeholder="搜索项目、费用或申请人" value={queryDraft} onChange={event => setQueryDraft(event.target.value)} /><button className="cost-source-icon" aria-label="查询人工分配任务" type="submit" disabled={saving}><Search size={16} /></button>
          </form>
        </div>
        {!canSave ? <p className="cost-source-muted">当前为只读模式</p> : null}
        {error ? <div role="alert" className="cost-source-error">{error}<Button size="sm" onPress={() => void load()}>重试</Button></div> : null}
        {loading ? <p role="status">正在读取分配任务…</p> : null}
        {!loading && !error && !items.length ? <p className="cost-source-empty">当前没有{status === 'pending' ? '待分配' : '已完成'}任务</p> : null}
        {items.map(item => {
          const id = item.relationCaseId; const state = states[id]; const active = expanded === id;
          return <article className={`cost-source-task${active ? ' is-expanded' : ''}`} key={id}>
            <button type="button" className="cost-source-task-heading" aria-expanded={active} onClick={() => { setExpanded(active ? null : id); if (!active) void loadDetail(id); }}>
              <ChevronRight size={15} className={active ? 'is-expanded' : ''} /><strong>{item.projectNames.join('、') || '项目未填写'}</strong>
              <span className="cost-source-task-meta"><span className={`cost-source-badge${item.status === 'allocated' ? ' is-complete' : ''}`}>{item.status === 'pending' ? '待分配' : '已完成'}</span><span>{item.unitCount} 个成本项 · {item.bankEventCount} 条流水{state?.dirty ? ' · 未保存' : ''}</span></span>
            </button>
            {active ? <>
              {state?.loading ? <p role="status">正在读取该关联的来源…</p> : null}
              {state?.task && state.draft ? <CostSourceAllocationForm key={id} task={state.task} draft={state.draft} disabled={!canSave || !state.task.canSave || !!state.saving || !!state.loading || !!state.unconfirmedRequest} saving={!!state.saving} error={state.error} notice={state.notice} onChange={draft => setCase(id, { draft, dirty: true, notice: undefined })} onSave={() => void save(id)} /> : state?.error ? <p className="cost-source-error" role="alert">{state.error}</p> : null}
              {state?.unconfirmedRequest ? <Button size="sm" isDisabled={!!state.saving} onPress={() => void verifySave(id)}>核实保存结果</Button> : null}
              {state?.error ? <Button size="sm" variant="secondary" isDisabled={!!state.saving} onPress={() => { if (!state.dirty || window.confirm('重新读取会替换当前草稿，是否继续？')) void loadDetail(id, true); }}>重新读取当前事实</Button> : null}
            </> : null}
          </article>;
        })}
        {nextCursor ? <Button size="sm" isDisabled={loading || saving} onPress={() => void load(status, query, nextCursor)}>加载更多</Button> : null}
      </div>
    </AppDrawer>
  </>;
}

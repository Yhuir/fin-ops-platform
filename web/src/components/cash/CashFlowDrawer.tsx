import { Button } from "@heroui/react";
import { useId, useState, type FormEvent } from "react";
import { useCashMutation, useCashQuery } from "../../features/cash/hooks";
import AppDrawer from "../common/AppDrawer";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";
import { cashAmount, cashMoneyInput, cashToday, settlementLabels, type CashItem, type CashPageRows, type CashSettlement, type CashSettlementKind } from "./CashItems.types";
import { CashItemDetail } from "./CashItems";
import { CashConfigurationSelect, CashProjectPicker } from "./CashFlowSelectors";
import { CashFlowComposition, flowCompositionPayload, newFlowPart, type FlowPart } from "./CashFlowComposition";
import { cashFlowLabels, type CashFlow, type CashFlowDetail, type CashFlowKind } from "./CashFlows.types";
import { FinanceTablePagination } from "../common/FinanceTable";
import { CashFlowCorrections } from "./CashFlowCorrections";

type TaskContext = { template_id: string; month: string; expected_version: number | null; expected_template_version?: number; planned_amount: string | null; title: string; kind: "receipt" | "payment";
  instructions?: string | null; default_account_id?: string | null; default_category_id?: string | null };
type Props = { open: boolean; onClose: () => void; flowId?: string; kind?: CashFlowKind; task?: TaskContext; existingItem?: CashItem; settlementKind?: CashSettlementKind; onSaved?: () => void };

export function CashFlowDrawer(props: Props) {
  if (!props.open) return null;
  return props.flowId ? <CashFlowDetailDrawer {...props} flowId={props.flowId} /> : <CashFlowEditor {...props} />;
}

function CashFlowEditor({ onClose, onSaved, kind: initialKind = "receipt", task, existingItem, settlementKind, flow }: Props & { flow?: CashFlow }) {
  const formId = useId();
  const [id] = useState(() => flow?.id ?? crypto.randomUUID());
  const [expectedVersion] = useState(flow?.version);
  const [kind, setKind] = useState<CashFlowKind>(flow?.kind ?? task?.kind ?? initialKind);
  const [date, setDate] = useState(flow?.occurred_on ?? cashToday());
  const [amount, setAmount] = useState(flow?.amount ?? "");
  const [from, setFrom] = useState(flow?.from_account?.id ?? (task?.kind === "payment" ? task.default_account_id ?? "" : ""));
  const [to, setTo] = useState(flow?.to_account?.id ?? (task?.kind === "receipt" ? task.default_account_id ?? "" : ""));
  const [category, setCategory] = useState(flow?.category?.id ?? task?.default_category_id ?? "");
  const [content, setContent] = useState(flow?.content ?? ""); const [person, setPerson] = useState(flow?.person_name ?? ""); const [remark, setRemark] = useState(flow?.remark ?? "");
  const [project, setProject] = useState<CashFlow["project"]>(flow?.project ?? null); const [projectPicker, setProjectPicker] = useState(false);
  const [planned, setPlanned] = useState(""); const [error, setError] = useState<string | null>(null);
  const [parts, setParts] = useState<FlowPart[]>(() => existingItem ? [newFlowPart("settlement", kind, existingItem, settlementKind)] : []);
  const [corrections, setCorrections] = useState<Record<string, unknown>>({});
  const [correctionsValid, setCorrectionsValid] = useState(true);
  const [dirty, setDirty] = useState(false); const [closing, setClosing] = useState(false);
  const mutation = useCashMutation();
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(null);
    if (mutation.busy || !correctionsValid) return;
    let body: Record<string, unknown>;
    try {
      if (!date || date > cashToday()) throw new Error("请填写不晚于今天的实际收付日期。");
      if (!content.trim()) throw new Error("请填写现金用途。");
      if (kind !== "transfer" && !category) throw new Error("请选择适用分类。");
      if (kind !== "receipt" && !from || kind !== "payment" && !to) throw new Error("请选择实际收付账户。");
      if (kind === "transfer" && from === to) throw new Error("内部转账的两个账户必须不同。");
      body = { occurred_on: date, kind, amount: cashMoneyInput(amount), from_account_id: kind === "receipt" ? null : from,
        to_account_id: kind === "payment" ? null : to, category_id: kind === "transfer" ? null : category,
        content: content.trim(), person_name: person.trim() || null, remark: remark.trim() || null };
      if (flow) body = { ...body, oa_project_id: project?.id ?? null, expected_version: expectedVersion, ...corrections };
      else if (existingItem) body = { ...body, id, project_mode: "existing_item", project_item_id: existingItem.id, expected_project_item_version: existingItem.version,
        allocations: flowCompositionPayload(parts, date, existingItem.oa_project_id, kind).allocations };
      else body = { ...body, id, project_mode: "selection", oa_project_id: project?.id ?? null, ...flowCompositionPayload(parts, date, project?.id ?? null, kind) };
      if (task) body = { template_id: task.template_id, month: task.month, expected_version: task.expected_version,
        ...(task.expected_template_version === undefined ? {} : { expected_template_version: task.expected_template_version }),
        ...(task.planned_amount === null ? { planned_amount: cashMoneyInput(planned) } : {}), mode: "new_flow", new_flow: body };
    } catch (failure) {
      if (!(failure instanceof Error)) throw failure;
      setError(failure.message); return;
    }
    const result = await mutation.run(task ? "/task-occurrences/confirm" : flow ? `/flows/${id}` : "/flows", body, flow ? "PUT" : "POST");
    if (result) { onSaved?.(); onClose(); }
  }
  return <AppDrawer open title={flow ? "编辑现金流水" : task ? `办理任务 · ${task.title}` : "新增现金流水"} onClose={() => dirty || !correctionsValid ? setClosing(true) : onClose()}
    closeDisabled={mutation.busy} width={720} className="cash-drawer" footer={<>
      <Button size="sm" variant="secondary" isDisabled={mutation.busy} onPress={() => dirty || !correctionsValid ? setClosing(true) : onClose()}>取消</Button>
      <Button size="sm" type="submit" form={formId} isPending={mutation.busy} isDisabled={!correctionsValid}>保存{task ? "并确认任务" : ""}</Button>
    </>}>
    {closing && <div className="cash-confirm" role="alert"><p>未保存的内容将被丢弃。</p><Button size="sm" variant="secondary" onPress={() => setClosing(false)}>继续填写</Button><Button size="sm" variant="danger" onPress={onClose}>放弃并关闭</Button></div>}
    <CashNotice error={error || mutation.error?.message} />
    {task?.instructions && <p className="cash-hint">{task.instructions}</p>}
    {mutation.error?.status === 409 && <p className="cash-hint">记录已变化。请关闭后重新读取并确认，当前输入未被自动覆盖。</p>}
    <form id={formId} onSubmit={save} onChange={() => setDirty(true)} className="cash-form">
      <div className="cash-form-grid">
        <CashSelect label="方向" value={kind} disabled={mutation.busy || Boolean(task || existingItem)} onChange={value => { setKind(value as CashFlowKind); setCategory(""); setParts([]); setDirty(true); }} required options={Object.entries(cashFlowLabels).map(([value, label]) => ({ value, label }))} />
        <CashInput label="实际发生日" type="date" value={date} onChange={setDate} required disabled={mutation.busy} />
        <CashInput label="金额（元）" value={amount} onChange={setAmount} required disabled={mutation.busy} />
        {kind !== "receipt" && <CashConfigurationSelect name="accounts" label="付款账户" value={from} selected={flow?.from_account} onChange={value => { setFrom(value); setDirty(true); }} required disabled={mutation.busy} />}
        {kind !== "payment" && <CashConfigurationSelect name="accounts" label="收款账户" value={to} selected={flow?.to_account} onChange={value => { setTo(value); setDirty(true); }} required disabled={mutation.busy} />}
        {kind !== "transfer" && <CashConfigurationSelect name="categories" label="费用分类" value={category} selected={flow?.category} group={kind} onChange={value => { setCategory(value); setDirty(true); }} required disabled={mutation.busy} />}
        <CashInput label="人员 / 经办对象（可选）" value={person} onChange={setPerson} disabled={mutation.busy} />
        <CashInput label="用途" value={content} onChange={setContent} required disabled={mutation.busy} />
        <CashInput label="备注（可选）" value={remark} onChange={setRemark} disabled={mutation.busy} />
        {task?.planned_amount === null && <CashInput label="本月计划金额" value={planned} onChange={setPlanned} required disabled={mutation.busy} />}
      </div>
    </form>
    <section className="cash-settings-subsection"><h3>项目</h3>
      <p>{existingItem ? existingItem.project_name_snapshot === null ? "无项目" : existingItem.project_name_snapshot : project === null ? "无项目" : project.name_snapshot}</p>
      {existingItem ? <p className="cash-hint">沿用已有事项的项目，不改写 OA 状态。已结束的项目仍可办理其真实结算。</p> : <div className="cash-row-actions">
        <Button size="sm" variant="secondary" isDisabled={mutation.busy} onPress={() => setProjectPicker(true)}>选择项目</Button>
        {project && <Button size="sm" variant="tertiary" isDisabled={mutation.busy} onPress={() => { setProject(null); setDirty(true); }}>清除项目</Button>}
      </div>}
      {projectPicker && <CashProjectPicker onClose={() => setProjectPicker(false)} onSelect={row => { setProject(row); setDirty(true); setProjectPicker(false); }} />}
    </section>
    {kind === "transfer" && <CashNotice>内部转账仅记录现金模块内两个账户之间的资金移动；只生成一笔流水，不算收入或费用，不连接银行流水池。</CashNotice>}
    {flow ? <CashFlowCorrections flowId={flow.id} mode="edit" onValidityChange={setCorrectionsValid} onChange={value => { setCorrections(value); if (value.source_corrections.length || value.settlement_changes.length || value.item_reference_changes.length) setDirty(true); }} /> :
      <CashFlowComposition parts={parts} kind={kind} existingItem={existingItem} disabled={mutation.busy} onChange={value => { setParts(value); setDirty(true); }} />}
  </AppDrawer>;
}

function CashFlowDetailDrawer({ flowId, onClose, onSaved }: Props & { flowId: string }) {
  const query = useCashQuery<CashFlowDetail>(`/flows/${flowId}`);
  const [mode, setMode] = useState("details"); const [page, setPage] = useState(1); const [itemId, setItemId] = useState<string | null>(null);
  const [linkedFlow, setLinkedFlow] = useState<string | null>(null);
  const [actualFlow, setActualFlow] = useState<{ item: CashItem; kind: CashSettlementKind } | null>(null);
  const [corrections, setCorrections] = useState<Record<string, unknown>>({});
  const [correctionsValid, setCorrectionsValid] = useState(true);
  const mutation = useCashMutation();
  const settlements = useCashQuery<CashPageRows<CashSettlement>>(mode === "allocations" ? "/settlements" : null, { flow_id: flowId, page, page_size: 20 });
  const flow = query.data?.flow;
  if (mode === "edit" && flow) return <CashFlowEditor open onClose={onClose} onSaved={onSaved} flow={flow} />;
  async function remove() {
    if (!flow || !correctionsValid) return;
    const result = await mutation.run(`/flows/${flow.id}/delete`, { expected_version: flow.version, ...corrections });
    if (result) { onSaved?.(); onClose(); }
  }
  async function unlinkTask() {
    if (!flow?.task) return;
    const result = await mutation.run(`/flows/${flow.id}/unlink-task`, { expected_version: flow.version, expected_occurrence_version: flow.task.occurrence_version });
    if (result) setMode("details");
  }
  if (linkedFlow) return <CashFlowDrawer open flowId={linkedFlow} onClose={() => setLinkedFlow(null)} />;
  if (actualFlow) return <CashFlowDrawer open existingItem={actualFlow.item} settlementKind={actualFlow.kind}
    kind={actualFlow.kind === "expense_payment" || actualFlow.item.obligation_direction === "payable" ? "payment" : "receipt"} onClose={() => setActualFlow(null)} />;
  if (itemId) return <CashItemDetail itemId={itemId} onClose={() => setItemId(null)} onFlow={setLinkedFlow} onActualFlow={(item, kind) => setActualFlow({ item, kind })} />;
  return <AppDrawer open title={mode === "delete" ? "删除现金流水" : "现金流水详情"} onClose={onClose} closeDisabled={mutation.busy} width={720} className="cash-drawer" footer={flow && <>
    {mode === "delete" ? <><Button size="sm" variant="secondary" onPress={() => setMode("details")} isDisabled={mutation.busy}>返回详情</Button><Button size="sm" variant="danger" isPending={mutation.busy} isDisabled={!correctionsValid} onPress={remove}>确认删除</Button></> :
      mode === "unlink" ? <><Button size="sm" variant="secondary" onPress={() => setMode("details")}>取消解除</Button><Button size="sm" isPending={mutation.busy} onPress={unlinkTask}>确认解除任务关联</Button></> :
        <><Button size="sm" variant="danger" onPress={() => setMode("delete")}>删除</Button><Button size="sm" variant="secondary" onPress={() => setMode("edit")}>编辑</Button></>}
  </>}>
    <CashNotice error={query.error?.message || mutation.error?.message} />
    {query.loading && <p role="status">正在读取流水详情…</p>}
    {query.error && <Button size="sm" variant="secondary" onPress={query.reload}>重新读取</Button>}
    {flow && query.data && <>
      {mode === "delete" ? <><p>删除 {flow.occurred_on} 的{cashFlowLabels[flow.kind]} {cashAmount(flow.amount)} 元。现金流水及其对应账簿处理会一并移除。</p>
        <p>影响：{query.data.delete_impact.task_count} 个任务，{query.data.delete_impact.item_count} 个事项，{query.data.delete_impact.settlement_count} 笔处理。事项若仍有后续业务，须明确选择保留、更正或删除。</p>
        <CashFlowCorrections flowId={flowId} mode="delete" onChange={setCorrections} onValidityChange={setCorrectionsValid} /></> : mode === "unlink" ? <p>仅解除这笔手动流水与“{flow.task?.title}”的错误关联，保留真实现金流水和已有账目处理，任务金额重新计算。</p> : <>
          <CashTabs value={mode} onChange={setMode} tabs={[{ id: "details", label: "流水信息" }, { id: "allocations", label: `对应处理（${query.data.allocation_count}）` }]} />
          {mode === "details" ? <dl className="cash-detail-grid">
            <dt>发生日</dt><dd>{flow.occurred_on}</dd><dt>方向 / 金额</dt><dd>{cashFlowLabels[flow.kind]} · {cashAmount(flow.amount)}</dd>
            <dt>付款账户</dt><dd>{flow.from_account === null ? "—" : flow.from_account.name}</dd><dt>收款账户</dt><dd>{flow.to_account === null ? "—" : flow.to_account.name}</dd>
            <dt>项目</dt><dd>{flow.project === null ? "无项目" : flow.project.name_snapshot}</dd><dt>分类</dt><dd>{flow.category === null ? "—" : flow.category.name}</dd>
            <dt>人员</dt><dd>{flow.person_name === null ? "—" : flow.person_name}</dd><dt>用途</dt><dd>{flow.content}</dd>
            <dt>备注</dt><dd>{flow.remark === null ? "—" : flow.remark}</dd><dt>来源</dt><dd>{flow.source_kind === "manual" ? "手动录入" : "每月任务"}</dd>
            <dt>任务关联</dt><dd>{flow.task ? `${flow.task.month} · ${flow.task.title}` : "无"}{flow.task && flow.source_kind === "manual" && <Button size="sm" variant="tertiary" onPress={() => setMode("unlink")}>解除错误关联</Button>}</dd>
            <dt>录入账号</dt><dd>{flow.created_by_account}{flow.created_by_name === null ? "" : ` · ${flow.created_by_name}`}</dd>
          </dl> : <><CashNotice error={settlements.error?.message} />{settlements.loading && <p role="status">正在读取对应处理…</p>}
            {settlements.data && <><ul className="cash-choice-list">{settlements.data.rows.map(row => <li key={row.id}><span>{row.occurred_on} · {settlementLabels[row.kind]} · {cashAmount(row.amount)}</span>{row.item_id && <Button size="sm" variant="tertiary" onPress={() => setItemId(row.item_id)}>{row.item_content}</Button>}</li>)}</ul>
              {settlements.data.rows.length === 0 && <p>这笔流水没有分配到事项。</p>}<FinanceTablePagination page={page} pageSize={20} total={settlements.data.pagination.total} onPageChange={setPage} /></>}
          </>}
        </>}
    </>}
  </AppDrawer>;
}

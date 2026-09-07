import { Button, Checkbox } from "@heroui/react";
import { useEffect, useState } from "react";

import { useCashMutation, useCashQuery, useCashScope } from "../../features/cash/hooks";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTablePagination, FinanceTableRow } from "../common/FinanceTable";
import { CashFlowDrawer } from "./CashFlowDrawer";
import { cashAmount, cashToday } from "./CashItems.types";
import type { CashAccountSetting, CashCategorySetting } from "./CashSettingsTypes";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";
import { cashTaskIdentity, cashTaskKindLabels, cashTaskStateLabels } from "./CashTasksTypes";
import type { CashOccurrencesPage, CashTaskOccurrence, CashTasksPage, CashTaskTemplate } from "./CashTasksTypes";
import { useCashTaskSettingsCloseGuard } from "./CashTaskSettingsCloseGuard";

const kindOptions = Object.entries(cashTaskKindLabels).map(([value, label]) => ({ value, label }));
const stateOptions = Object.entries(cashTaskStateLabels).map(([value, label]) => ({ value, label }));

type MonthCriteria = { month: string; view: string; kind: string; state: string; keyword: string; page: number };
type TemplateCriteria = { page: number; kind: string; enabled: string; keyword: string; sort: string };
export type CashTasksCriteria = { tab: string; month: MonthCriteria; templates: TemplateCriteria };
export function initialCashTasksCriteria(): CashTasksCriteria {
  return { tab: "month", month: { month: cashToday().slice(0, 7), view: "month", kind: "", state: "", keyword: "", page: 1 },
    templates: { page: 1, kind: "", enabled: "", keyword: "", sort: "title" } };
}
export default function CashTasks({ initialCriteria, onCriteriaChange }: { initialCriteria?: CashTasksCriteria; onCriteriaChange?: (value: CashTasksCriteria) => void }) {
  const [initial] = useState(() => initialCriteria ?? initialCashTasksCriteria());
  const [tab, setTab] = useState(initial.tab); const [month, setMonth] = useState(initial.month); const [templates, setTemplates] = useState(initial.templates);
  useEffect(() => { onCriteriaChange?.({ tab, month, templates }); }, [tab, month, templates, onCriteriaChange]);
  return <><CashTabs value={tab} onChange={setTab} tabs={[{ id: "month", label: "本月处理" }, { id: "templates", label: "任务配置" }]} /><div className="cash-scroll-content">{tab === "month" ? <CashTaskMonth initial={month} onChange={setMonth} /> : <CashTaskTemplates initial={templates} onChange={setTemplates} />}</div></>;
}

export function cashTaskRemaining(row: Pick<CashTaskOccurrence, "planned_amount" | "actual_amount" | "kind">): string | null {
  if (row.kind === "check" || row.planned_amount === null || row.actual_amount === null) return null;
  const cents = (value: string) => {
    if (!/^\d+\.\d{2}$/.test(value)) throw new Error("任务金额格式不正确。");
    return BigInt(value.replace(".", ""));
  };
  const remaining = cents(row.planned_amount) - cents(row.actual_amount);
  const positive = remaining > 0n ? remaining : 0n;
  return `${positive / 100n}.${String(positive % 100n).padStart(2, "0")}`;
}

function CashTaskMonth({ initial, onChange }: { initial: MonthCriteria; onChange: (value: MonthCriteria) => void }) {
  const { revision, refresh } = useCashScope();
  const [today, setToday] = useState(cashToday);
  const [month, setMonth] = useState(initial.month);
  const [view, setView] = useState(initial.view);
  const [kind, setKind] = useState(initial.kind);
  const [state, setState] = useState(initial.state);
  const [keyword, setKeyword] = useState(initial.keyword);
  const [search, setSearch] = useState(initial.keyword);
  const [page, setPage] = useState(initial.page);
  const [action, setAction] = useState<{ row: CashTaskOccurrence; mode: "adjust" | "unpaid" | "check" | "link" | "detail" | "new" } | null>(null);
  const [flowId, setFlowId] = useState<string | null>(null);
  useEffect(() => { onChange({ month, view, kind, state, keyword, page }); }, [month, view, kind, state, keyword, page, onChange]);
  const query = useCashQuery<CashOccurrencesPage>("/task-occurrences", {
    ...(view === "overdue" ? { overdue_as_of: today } : view === "reminders" ? { reminder_from: today, reminder_to: today } : { month }),
    page, page_size: 50, sort: "due_on", order: "asc", kind: kind || undefined, state: state || undefined, keyword: keyword || undefined,
  }, revision);
  useEffect(() => {
    const foreground = () => { if (document.visibilityState === "visible") { setToday(cashToday()); refresh(); } };
    const timer = window.setInterval(() => { const current = cashToday(); if (current !== today) { setToday(current); refresh(); } }, 60_000);
    window.addEventListener("focus", foreground);
    document.addEventListener("visibilitychange", foreground);
    return () => { window.clearInterval(timer); window.removeEventListener("focus", foreground); document.removeEventListener("visibilitychange", foreground); };
  }, [refresh, today]);
  const change = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(1); };
  return <section className="cash-section" aria-label="本月任务处理">
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}>
      <CashInput label="归属月份" type="month" value={month} onChange={change(setMonth)} disabled={view !== "month"} />
      <CashSelect label="任务范围" value={view} onChange={change(setView)} options={[{ value: "month", label: "所选月份" }, { value: "overdue", label: "逾期待办" }, { value: "reminders", label: "今日提醒" }]} />
      <CashSelect label="任务状态" value={state} onChange={change(setState)} options={[{ value: "", label: "全部状态" }, ...stateOptions]} />
      <CashSelect label="任务类别" value={kind} onChange={change(setKind)} options={[{ value: "", label: "全部类别" }, ...kindOptions]} />
      <CashInput label="任务关键词" value={search} onChange={setSearch} placeholder="任务内容" />
      <Button type="submit" variant="secondary">查询任务</Button>
      <Button variant="tertiary" onPress={query.reload} isDisabled={query.loading}>刷新</Button>
    </form>
    {query.data && <div className="cash-summary" aria-label="任务汇总"><span>未处理 {query.data.summary.counts_by_state.pending}</span><span>部分办理 {query.data.summary.counts_by_state.partial}</span><span>已完成 {query.data.summary.counts_by_state.completed}</span><span>收入累计 {cashAmount(query.data.summary.receipt_actual_amount)}</span><span>支出累计 {cashAmount(query.data.summary.payment_actual_amount)}</span></div>}
    <CashNotice error={query.error?.message}>{query.loading ? "正在读取任务…" : query.data?.rows.length === 0 ? "没有匹配任务。可在任务配置中新增每月收付或核对任务。" : null}</CashNotice>
    {query.data && (["receipt", "payment", "check"] as const).map((group) => {
      const rows = query.data!.rows.filter((row) => row.kind === group);
      if (!rows.length) return null;
      return <div className="cash-task-group" key={group}><h3>{cashTaskKindLabels[group]}</h3><FinanceTable ariaLabel={`${cashTaskKindLabels[group]}任务`} minWidth={1450}>
        <FinanceTableHeader>{["任务内容", "归属月份", "执行日期", "提醒日期", "当月目标", "实际累计", "剩余 / 超出", "处理状态", "关联流水", "操作"].map((name, index) => <FinanceTableColumn key={name} id={name} isRowHeader={index === 0}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody>{rows.map((row) => <FinanceTableRow key={row.row_key} id={row.row_key}>
          <FinanceTableCell columnRole="identity">{row.title}</FinanceTableCell><FinanceTableCell columnRole="date">{row.month}</FinanceTableCell>
          <FinanceTableCell columnRole="date">{row.due_on}{row.is_overdue ? <span className="cash-danger"> · 逾期</span> : row.is_due ? " · 今日到期" : ""}</FinanceTableCell><FinanceTableCell columnRole="date">{row.remind_on}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{row.need_planned_amount ? <Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "adjust" })}>待填写本月金额</Button> : cashAmount(row.planned_amount)}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{cashAmount(row.actual_amount)}</FinanceTableCell><FinanceTableCell columnRole="amount">{row.is_over_plan ? `超出 ${cashAmount(row.over_plan_amount)}` : cashAmount(cashTaskRemaining(row))}</FinanceTableCell>
          <FinanceTableCell columnRole="status">{cashTaskStateLabels[row.state]}{row.marked_unpaid ? " · 已标未办" : ""}</FinanceTableCell>
          <FinanceTableCell columnRole="quantity"><Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "detail" })}>{row.flow_count} 笔</Button></FinanceTableCell>
          <FinanceTableCell columnRole="action"><div className="cash-row-actions">
            {row.kind !== "check" && <><Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "new" })}>{row.state === "completed" ? "补记实际收付" : row.state === "partial" ? "继续办理" : row.kind === "receipt" ? "已收，新记一笔" : "已付 / 已还"}</Button><Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "link" })}>关联已录</Button></>}
            {row.kind !== "check" && row.actual_amount === "0.00" && <Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "unpaid" })}>{row.kind === "receipt" ? "未收" : "未付 / 未还"}</Button>}
            {row.kind === "check" && row.state !== "completed" && <Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "check" })}>已核对</Button>}
            <Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "adjust" })}>调整本月</Button>
            <Button variant="tertiary" size="sm" onPress={() => setAction({ row, mode: "detail" })}>明细</Button>
          </div></FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable></div>;
    })}
    {query.data && <FinanceTablePagination page={page} pageSize={50} total={query.data.pagination.total} onPageChange={setPage} isDisabled={query.loading} />}
    {action && ["adjust", "unpaid", "check"].includes(action.mode) && <CashOccurrenceAction row={action.row} mode={action.mode as "adjust" | "unpaid" | "check"} onClose={() => setAction(null)} />}
    {action?.mode === "link" && <CashTaskLink row={action.row} onClose={() => setAction(null)} />}
    {action?.mode === "detail" && <CashTaskDetails row={action.row} onClose={() => setAction(null)} onFlow={(id) => { setAction(null); setFlowId(id); }} />}
    {action?.mode === "new" && action.row.kind !== "check" && <CashFlowDrawer open onClose={() => setAction(null)} task={{ ...cashTaskIdentity(action.row), planned_amount: action.row.planned_amount, title: action.row.title, kind: action.row.kind, instructions: action.row.instructions, default_account_id: action.row.default_account_id, default_category_id: action.row.default_category_id }} />}
    {flowId && <CashFlowDrawer open flowId={flowId} onClose={() => setFlowId(null)} />}
  </section>;
}

function CashOccurrenceAction({ row, mode, onClose }: { row: CashTaskOccurrence; mode: "adjust" | "unpaid" | "check"; onClose: () => void }) {
  const [date, setDate] = useState(row.due_on);
  const [planned, setPlanned] = useState(row.planned_amount ?? "");
  const [note, setNote] = useState(row.note ?? "");
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([date, planned, note], onClose, mutation.busy);
  const title = mode === "adjust" ? "调整本月" : mode === "check" ? "完成核对" : row.kind === "receipt" ? "标记未收" : "标记未付 / 未还";
  return <AppDrawer open title={title} width={520} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" onPress={close.requestClose} isDisabled={mutation.busy}>取消</Button><Button type="submit" form="cash-occurrence-form" isDisabled={mutation.busy}>{mode === "adjust" ? "保存本月调整" : title}</Button></>}>
    <form id="cash-occurrence-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void (async () => {
      const result = await mutation.run(`/task-occurrences/${mode === "adjust" ? "adjust" : mode === "check" ? "complete-check" : "mark-unpaid"}`, { ...cashTaskIdentity(row), note: note || null, ...(mode === "adjust" ? { due_on: date, planned_amount: row.kind === "check" || !planned ? null : planned } : {}) });
      if (result !== null) onClose();
    })(); }}>
      <p>{row.title} · {row.month}</p>{row.instructions && <p className="cash-hint">{row.instructions}</p>}<CashNotice error={mutation.error?.message} />
      {mode === "adjust" && <><CashInput label="本月执行日期" type="date" value={date} onChange={setDate} required disabled={mutation.busy} />{row.kind !== "check" && <CashInput label="本月目标金额" value={planned} onChange={setPlanned} required={row.actual_amount !== "0.00"} disabled={mutation.busy} placeholder="未确定可留空" />}<p className="cash-hint">仅调整此归属月，不修改实际流水或其他月份。日期可在归属月前后各 31 天内调整。</p></>}
      {mode !== "adjust" && <p className="cash-hint">此操作不生成现金流水。{mode === "unpaid" ? "任务仍保留在待办中。" : "只更新核对状态。"}</p>}
      <CashInput label="本月说明" value={note} onChange={setNote} disabled={mutation.busy} />
    </form>
    {close.confirmation}
  </AppDrawer>;
}

type TaskFlow = {
  id: string; version: number; occurred_on: string; content: string; amount: string;
  source_kind: "manual" | "monthly_task"; kind: "receipt" | "payment" | "transfer";
  from_account: { id: string; name: string } | null; to_account: { id: string; name: string } | null;
  project: { id: string; name_snapshot: string } | null;
  task: { occurrence_id: string; occurrence_version: number } | null;
  selectable?: boolean; unavailable_reason?: "direction_mismatch" | "already_claimed" | "target_incompatible" | null;
};

function CashTaskLink({ row, onClose }: { row: CashTaskOccurrence; onClose: () => void }) {
  const { revision } = useCashScope();
  const [from, setFrom] = useState(`${row.month}-01`);
  const [to, setTo] = useState(() => {
    const [year, month] = row.month.split("-").map(Number);
    return `${row.month}-${new Date(Date.UTC(year, month, 0)).getUTCDate()}`;
  });
  const [keyword, setKeyword] = useState("");
  const [search, setSearch] = useState("");
  const [page, setPage] = useState(1);
  const [selected, setSelected] = useState<TaskFlow | null>(null);
  const [planned, setPlanned] = useState("");
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([selected?.id, planned], onClose, mutation.busy);
  const query = useCashQuery<CashTasksPage<TaskFlow>>("/flows", { purpose: "task_link", template_id: row.template_id, month: row.month, date_from: from, date_to: to, page, page_size: 50, keyword: keyword || undefined }, revision);
  const selectionCurrent = Boolean(selected && query.data?.rows.some((flow) => flow.id === selected.id && flow.version === selected.version && flow.selectable));
  const reason = { direction_mismatch: "收付方向不同", already_claimed: "已关联月任务", target_incompatible: "任务月份不可办理" };
  return <AppDrawer open title="关联已录现金" width={880} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" onPress={close.requestClose} isDisabled={mutation.busy}>取消</Button><Button isDisabled={!selectionCurrent || query.loading || mutation.busy || (row.need_planned_amount && !planned)} onPress={() => { if (!selected || !selectionCurrent) return; void (async () => {
      const result = await mutation.run("/task-occurrences/confirm", { ...cashTaskIdentity(row), mode: "existing_flow", ...(row.need_planned_amount ? { planned_amount: planned } : {}), existing_flow: { flow_id: selected.id, expected_flow_version: selected.version } });
      if (result !== null) onClose();
    })(); }}>确认关联</Button></>}>
    <p>{row.title} · {row.month}</p><p className="cash-hint">只认领明确选中的现金流水，保留原来源和已有分配，不重复生成现金。</p>
    <CashNotice error={mutation.error?.message ?? query.error?.message} />
    {row.need_planned_amount && <CashInput label="本月目标金额" value={planned} onChange={setPlanned} required disabled={mutation.busy} />}
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); setSelected(null); }}><CashInput label="流水起始日" type="date" value={from} onChange={(value) => { setFrom(value); setPage(1); setSelected(null); }} disabled={mutation.busy} /><CashInput label="流水截止日" type="date" value={to} onChange={(value) => { setTo(value); setPage(1); setSelected(null); }} disabled={mutation.busy} /><CashInput label="流水关键词" value={search} onChange={setSearch} disabled={mutation.busy} /><Button type="submit" variant="secondary">查询流水</Button></form>
    <CashNotice>{query.loading ? "正在读取现金流水…" : query.data?.rows.length === 0 ? "所选期间没有匹配现金流水。可调整日期或返回新记一笔。" : null}</CashNotice>
    {query.data && <FinanceTable ariaLabel="可关联现金流水" minWidth={750} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data.pagination.total} onPageChange={(value) => { setPage(value); setSelected(null); }} isDisabled={query.loading || mutation.busy} />}>
      <FinanceTableHeader>{["日期", "内容", "金额", "来源", "关联资格"].map((name, i) => <FinanceTableColumn key={name} id={name} isRowHeader={i === 1}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
      <FinanceTableBody>{query.data.rows.map((flow) => <FinanceTableRow id={flow.id} key={flow.id}><FinanceTableCell columnRole="date">{flow.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="description">{flow.content}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(flow.amount)}</FinanceTableCell><FinanceTableCell columnRole="status">{flow.source_kind === "manual" ? "手工录入" : "每月任务"}</FinanceTableCell><FinanceTableCell columnRole="selection"><Button variant={selected?.id === flow.id ? "primary" : "tertiary"} isDisabled={!flow.selectable || mutation.busy || query.loading} onPress={() => setSelected(flow)}>{flow.selectable ? selected?.id === flow.id ? "已选择" : "选择" : flow.unavailable_reason ? reason[flow.unavailable_reason] : "不可选"}</Button></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>}
    {selected && <p role="status">已选：{selected.occurred_on} · {selected.content} · {cashAmount(selected.amount)}</p>}
    {selected && query.data && !selectionCurrent && <CashNotice error="所选流水已变化或不再可关联，请重新选择。其他输入已保留。" />}
    {close.confirmation}
  </AppDrawer>;
}

function CashTaskDetails({ row, onClose, onFlow }: { row: CashTaskOccurrence; onClose: () => void; onFlow: (id: string) => void }) {
  const { revision } = useCashScope();
  const [page, setPage] = useState(1);
  const [unlink, setUnlink] = useState<TaskFlow | null>(null);
  const mutation = useCashMutation();
  const query = useCashQuery<CashTasksPage<TaskFlow>>(row.occurrence_id ? "/flows" : null, { task_occurrence_id: row.occurrence_id, page, page_size: 50 }, revision);
  return <AppDrawer open title="月任务处理明细" width={880} className="cash-drawer" onClose={onClose} closeDisabled={mutation.busy}>
    <p>{row.title} · {row.month}</p><div className="cash-summary"><span>{cashTaskStateLabels[row.state]}</span><span>当月目标 {cashAmount(row.planned_amount)}</span><span>实际累计 {cashAmount(row.actual_amount)}</span></div>{row.instructions && <p className="cash-hint">办理说明：{row.instructions}</p>}<p className="cash-hint">{row.note ?? "未填写本月说明"}</p>
    <CashNotice error={query.error?.message ?? mutation.error?.message}>{!row.occurrence_id ? "本月尚未办理，没有关联现金。" : query.loading ? "正在读取处理明细…" : query.data?.rows.length === 0 ? "本月没有有效关联现金。" : null}</CashNotice>
    {row.kind === "check" && row.state === "completed" && row.occurrence_id && <Button variant="tertiary" isDisabled={mutation.busy} onPress={() => { void (async () => { const result = await mutation.run(`/task-occurrences/${row.occurrence_id}/reopen-check`, { expected_version: row.version }); if (result !== null) onClose(); })(); }}>重新核对</Button>}
    {query.data && <FinanceTable ariaLabel="任务关联现金" minWidth={740} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data.pagination.total} onPageChange={setPage} isDisabled={query.loading || mutation.busy} />}>
      <FinanceTableHeader>{["日期", "内容", "金额", "来源", "操作"].map((name, i) => <FinanceTableColumn id={name} key={name} isRowHeader={i === 1}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
      <FinanceTableBody>{query.data.rows.map((flow) => <FinanceTableRow id={flow.id} key={flow.id}><FinanceTableCell columnRole="date">{flow.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="description">{flow.content}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(flow.amount)}</FinanceTableCell><FinanceTableCell columnRole="status">{flow.source_kind === "manual" ? "手工录入" : "每月任务"}</FinanceTableCell><FinanceTableCell columnRole="action"><Button variant="tertiary" onPress={() => onFlow(flow.id)}>流水详情</Button>{flow.source_kind === "manual" && <Button variant="tertiary" isDisabled={mutation.busy} onPress={() => setUnlink(flow)}>解除误关联</Button>}</FinanceTableCell></FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>}
    {unlink && <div className="cash-confirm" role="group" aria-label="确认解除任务关联"><p>只解除“{unlink.content}”的任务关系，保留现金和已有事项分配。</p><Button variant="tertiary" onPress={() => setUnlink(null)} isDisabled={mutation.busy}>取消</Button><Button isDisabled={mutation.busy} onPress={() => { void (async () => { const result = await mutation.run(`/flows/${unlink.id}/unlink-task`, { expected_version: unlink.version, expected_occurrence_version: unlink.task!.occurrence_version }); if (result !== null) onClose(); })(); }}>确认解除关联</Button></div>}
  </AppDrawer>;
}

function CashTaskTemplates({ initial, onChange }: { initial: TemplateCriteria; onChange: (value: TemplateCriteria) => void }) {
  const { revision } = useCashScope();
  const [page, setPage] = useState(initial.page);
  const [kind, setKind] = useState(initial.kind);
  const [enabled, setEnabled] = useState(initial.enabled);
  const [keyword, setKeyword] = useState(initial.keyword);
  const [search, setSearch] = useState(initial.keyword);
  const [sort, setSort] = useState(initial.sort);
  const [editing, setEditing] = useState<CashTaskTemplate | "new" | null>(null);
  useEffect(() => { onChange({ page, kind, enabled, keyword, sort }); }, [page, kind, enabled, keyword, sort, onChange]);
  const query = useCashQuery<CashTasksPage<CashTaskTemplate>>("/tasks", { page, page_size: 50, sort, order: "asc", kind: kind || undefined, enabled: enabled || undefined, keyword: keyword || undefined }, revision);
  const change = (setter: (value: string) => void) => (value: string) => { setter(value); setPage(1); };
  return <section className="cash-section" aria-label="任务配置">
    <form className="cash-toolbar" onSubmit={(event) => { event.preventDefault(); setKeyword(search.trim()); setPage(1); }}><CashInput label="模板关键词" value={search} onChange={setSearch} placeholder="任务名称或说明" /><Button type="submit" variant="secondary">查询模板</Button><CashSelect label="模板类别" value={kind} onChange={change(setKind)} options={[{ value: "", label: "全部类别" }, ...kindOptions]} /><CashSelect label="模板状态" value={enabled} onChange={change(setEnabled)} options={[{ value: "", label: "全部状态" }, { value: "true", label: "启用" }, { value: "false", label: "停用" }]} /><CashSelect label="模板排序" value={sort} onChange={change(setSort)} options={[{ value: "title", label: "任务名称" }, { value: "execution_day", label: "执行日" }]} /><Button variant="tertiary" onPress={query.reload} isDisabled={query.loading}>刷新</Button><Button onPress={() => setEditing("new")}>新增任务</Button></form>
    <CashNotice error={query.error?.message}>{query.loading ? "正在读取任务配置…" : query.data?.rows.length === 0 ? "暂无匹配模板。可新增收入、支出或核对任务，日期和目标由你明确填写。" : null}</CashNotice>
    {query.data && <FinanceTable ariaLabel="任务模板" minWidth={1050} footer={<FinanceTablePagination page={page} pageSize={50} total={query.data.pagination.total} onPageChange={setPage} isDisabled={query.loading} />}>
      <FinanceTableHeader>{["任务名称", "类别", "执行日", "提前提醒", "生效范围", "默认月目标", "状态", "办理说明", "操作"].map((name, i) => <FinanceTableColumn id={name} key={name} isRowHeader={i === 0}>{name}</FinanceTableColumn>)}</FinanceTableHeader>
      <FinanceTableBody>{query.data.rows.map((row) => <FinanceTableRow id={row.id} key={row.id}><FinanceTableCell columnRole="identity">{row.title}</FinanceTableCell><FinanceTableCell columnRole="status">{cashTaskKindLabels[row.kind]}</FinanceTableCell><FinanceTableCell columnRole="date">每月 {row.execution_day} 日</FinanceTableCell><FinanceTableCell columnRole="quantity">{row.remind_days} 天</FinanceTableCell><FinanceTableCell columnRole="date">{row.effective_from_month} 至 {row.effective_to_month ?? "长期"}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.default_amount)}</FinanceTableCell><FinanceTableCell columnRole="status">{row.enabled ? "启用" : "停用"}</FinanceTableCell><FinanceTableCell columnRole="description">{row.instructions ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="action"><Button variant="tertiary" onPress={() => setEditing(row)}>编辑 / 启停</Button></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>}
    {editing && <CashTaskTemplateEditor template={editing === "new" ? null : editing} onClose={() => setEditing(null)} />}
  </section>;
}

function CashTaskTemplateEditor({ template, onClose }: { template: CashTaskTemplate | null; onClose: () => void }) {
  const [id] = useState(() => crypto.randomUUID());
  const [title, setTitle] = useState(template?.title ?? "");
  const [kind, setKind] = useState<string>(template?.kind ?? "");
  const [day, setDay] = useState(template ? String(template.execution_day) : "");
  const [remind, setRemind] = useState(template ? String(template.remind_days) : "");
  const [from, setFrom] = useState(template?.effective_from_month ?? cashToday().slice(0, 7));
  const [to, setTo] = useState(template?.effective_to_month ?? "");
  const [enabled, setEnabled] = useState(template?.enabled ?? true);
  const [amount, setAmount] = useState(template?.default_amount ?? "");
  const [account, setAccount] = useState(template?.default_account_id ?? "");
  const [category, setCategory] = useState(template?.default_category_id ?? "");
  const [instructions, setInstructions] = useState(template?.instructions ?? "");
  const [accountKeyword, setAccountKeyword] = useState("");
  const [categoryKeyword, setCategoryKeyword] = useState("");
  const [accountSearch, setAccountSearch] = useState("");
  const [categorySearch, setCategorySearch] = useState("");
  const [accountPage, setAccountPage] = useState(1);
  const [categoryPage, setCategoryPage] = useState(1);
  const accounts = useCashQuery<CashTasksPage<CashAccountSetting>>(kind && kind !== "check" ? "/settings/accounts" : null, { enabled: true, page: accountPage, page_size: 50, keyword: accountKeyword || undefined, order: "asc" });
  const categories = useCashQuery<CashTasksPage<CashCategorySetting>>(kind && kind !== "check" ? "/settings/categories" : null, { enabled: true, page: categoryPage, page_size: 50, keyword: categoryKeyword || undefined, order: "asc" });
  const mutation = useCashMutation();
  const close = useCashTaskSettingsCloseGuard([title, kind, day, remind, from, to, enabled, amount, account, category, instructions], onClose, mutation.busy);
  const [validation, setValidation] = useState<string | null>(null);
  const changingStart = template ? from !== template.effective_from_month || (!template.enabled && enabled) : true;
  const save = async () => {
    if (!/^(?:[1-9]|[12]\d|3[01])$/.test(day) || !/^(?:\d|[12]\d|3[01])$/.test(remind)) { setValidation("执行日须为 1–31，提前提醒须为 0–31 的整数。"); return; }
    setValidation(null);
    const body = {
      ...(template ? { expected_version: template.version } : { id }), title, kind,
      execution_day: Number(day), remind_days: Number(remind),
      ...(changingStart ? { effective_from_month: from } : {}), effective_to_month: to || null, enabled,
      default_amount: kind === "check" ? null : amount || null,
      default_account_id: kind === "check" ? null : account || null,
      default_category_id: kind === "check" ? null : category || null, instructions: instructions || null,
    };
    const result = await mutation.run(template ? `/tasks/${template.id}` : "/tasks", body, template ? "PUT" : "POST");
    if (result !== null) onClose();
  };
  return <AppDrawer open title={template ? "编辑每月任务" : "新增每月任务"} width={580} className="cash-drawer" onClose={close.requestClose} closeDisabled={mutation.busy} footer={<><Button variant="tertiary" onPress={close.requestClose} isDisabled={mutation.busy}>取消</Button><Button type="submit" form="cash-task-template-form" isDisabled={mutation.busy}>保存任务</Button></>}>
    <form id="cash-task-template-form" className="cash-form" onSubmit={(event) => { event.preventDefault(); void save(); }}>
      <CashNotice error={validation ?? mutation.error?.message} />
      <CashInput label="任务内容" value={title} onChange={setTitle} required disabled={mutation.busy} />
      <CashSelect label="处理类别" value={kind} onChange={(value) => { setKind(value); setAccount(""); setCategory(""); setAmount(""); }} required disabled={mutation.busy} options={[{ value: "", label: "请选择类别" }, ...kindOptions]} />
      <div className="cash-form-grid"><CashInput label="每月执行日" type="number" value={day} onChange={setDay} required disabled={mutation.busy} /><CashInput label="提前提醒天数" type="number" value={remind} onChange={setRemind} required disabled={mutation.busy} /><CashInput label="生效月份" type="month" value={from} onChange={setFrom} required disabled={mutation.busy} /><CashInput label="结束月份" type="month" value={to} onChange={setTo} disabled={mutation.busy} /></div>
      <Checkbox isSelected={enabled} onChange={setEnabled} isDisabled={mutation.busy}><Checkbox.Control><Checkbox.Indicator /></Checkbox.Control><span>启用任务</span></Checkbox>
      <p className="cash-hint">普通修改与停用作用于未来月份，本月请使用“调整本月”。重新启用须明确当月或未来起点；历史月份和现金不会删除。</p>
      {kind && kind !== "check" && <>
        <CashInput label="默认月目标（选填）" value={amount} onChange={setAmount} disabled={mutation.busy} placeholder="不是每次实际收付金额" />
        <details className="cash-inline-details"><summary>默认账户和费用类型（选填）</summary>
          <CashNotice error={accounts.error?.message ?? categories.error?.message} />
          <CashInput label="搜索默认账户" value={accountSearch} onChange={setAccountSearch} disabled={mutation.busy} /><Button type="button" variant="tertiary" onPress={() => { setAccountKeyword(accountSearch.trim()); setAccountPage(1); }} isDisabled={mutation.busy}>查询默认账户</Button>
          <CashSelect label="默认现金账户" value={account} onChange={setAccount} disabled={mutation.busy || accounts.loading} options={[{ value: "", label: "每次办理时选择" }, ...(account && !accounts.data?.rows.some((item) => item.id === account) ? [{ value: account, label: "当前已设账户（搜索可核对）", disabled: true }] : []), ...(accounts.data?.rows.map((item) => ({ value: item.id, label: item.name })) ?? [])]} />
          {accounts.data && accounts.data.pagination.total > 50 && <FinanceTablePagination page={accountPage} pageSize={50} total={accounts.data.pagination.total} onPageChange={setAccountPage} compact />}
          <CashInput label="搜索默认费用类型" value={categorySearch} onChange={setCategorySearch} disabled={mutation.busy} /><Button type="button" variant="tertiary" onPress={() => { setCategoryKeyword(categorySearch.trim()); setCategoryPage(1); }} isDisabled={mutation.busy}>查询默认费用类型</Button>
          <CashSelect label="默认费用类型" value={category} onChange={setCategory} disabled={mutation.busy || categories.loading} options={[{ value: "", label: "每次办理时选择" }, ...(category && !categories.data?.rows.some((item) => item.id === category) ? [{ value: category, label: "当前已设类型（搜索可核对）", disabled: true }] : []), ...(categories.data?.rows.map((item) => ({ value: item.id, label: item.name, disabled: item.group !== kind && item.group !== "turnover" })) ?? [])]} />
          {categories.data && categories.data.pagination.total > 50 && <FinanceTablePagination page={categoryPage} pageSize={50} total={categories.data.pagination.total} onPageChange={setCategoryPage} compact />}
        </details>
      </>}
      <CashInput label="办理说明" value={instructions} onChange={setInstructions} disabled={mutation.busy} />
      <p className="cash-hint">29/30/31 日遇短月取该月最后一天；不自动顺延节假日，不执行付款或页外通知。</p>
    </form>
    {close.confirmation}
  </AppDrawer>;
}

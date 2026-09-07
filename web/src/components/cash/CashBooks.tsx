import { Button } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";

import { useCashQuery } from "../../features/cash/hooks";
import AppDrawer from "../common/AppDrawer";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTablePagination, FinanceTableRow } from "../common/FinanceTable";
import { CashFlowDrawer } from "./CashFlowDrawer";
import { CashItemDetail, CashItemEditor, CashItemPicker, CashSettlementEditor } from "./CashItems";
import { cashAmount, cashToday, settlementLabels, type CashItem, type CashItemType, type CashPageRows, type CashProject, type CashSettlement, type CashSettlementKind } from "./CashItems.types";
import { CashInput, CashNotice, CashSelect, CashTabs } from "./CashUi";

type Period = { date_from: string; date_to: string };
type Params = Record<string, string | number | boolean | null | undefined>;
function yearPeriod(year: string): Period { return { date_from: `${year}-01-01`, date_to: `${year}-12-31` }; }
const currentYear = () => cashToday().slice(0, 4);
type BookCriteria = { filters: Params; group: string; page: number; sort: string; order: string; project: { id: string; name: string } | null };
type PersonalCriteria = { view: string; year: string; keyword: string; bill: string; project: { id: string; name: string } | null; page: number; order: string };
export type CashBooksCriteria = { tab: string; turnover: BookCriteria; tickets: BookCriteria; personal: PersonalCriteria };
export function initialCashBooksCriteria(): CashBooksCriteria {
  return {
    tab: "turnover",
    turnover: { filters: yearPeriod(currentYear()), group: "all", page: 1, sort: "occurred_on", order: "desc", project: null },
    tickets: { filters: yearPeriod(currentYear()), group: "all", page: 1, sort: "ticket_provided_on", order: "desc", project: null },
    personal: { view: "matrix", year: currentYear(), keyword: "", bill: "", project: null, page: 1, order: "desc" },
  };
}
type TurnoverRow = {
  row_id: string; row_kind: string; ledger_group: string | null; personal_variant: string | null;
  occurred_on: string; item_id: string; counterparty: string | null; project: CashProject; content: string;
  state: string | null; original_amount: string | null; repayment_amount: string | null;
  reimbursement_received_amount: string | null; ticket_offset_amount: string | null; non_ticket_offset_amount: string | null;
  real_expense_amount: string | null; cash_received_amount: string | null; cash_paid_amount: string | null;
  remaining_after_event: string | null; flow_id: string | null; settlement_id: string | null; expense_item_id: string | null;
  category: { id: string; name: string; group: string } | null; remark: string | null; ticket_collection_state: string | null;
};
type Report<T, S> = CashPageRows<T> & { summary: S };
type TurnoverSummary = Record<string, string | number | { receivable: string; payable: string }> & { remaining_obligation_amount: { receivable: string; payable: string } };
type TicketRow = { id: string; version: number; ticket_provider: string; ticket_provided_on: string; content: string; project: CashProject; provided_amount: string; used_amount: string; offset_amount: string; available_source_amount: string; receivable_amount: string; cash_received_amount: string; state: string };
type PersonalRow = CashSettlement & { bill_label: { id: string; bank_name: string; label: string } | null; bill_month: string | null; counterparty: string; project: CashProject };
type MatrixRow = { row_key: string; bill_label: { id: string; bank_name: string; label: string } | null; months: { month: string; principal_amount: string | null; item_count: number | null; coverage_state: string }[]; year_principal_amount: string | null };
type PersonalSummary = { coverage: { state: string; opening_date: string | null; coverage_start: string | null }; opening_obligation_amount: string | null; opening_adjustment_amount: string | null; new_principal_amount: string | null; cash_repayment_amount: string | null; ticket_offset_amount: string | null; non_ticket_offset_amount: string | null; remaining_obligation_amount: string | null };

function ReportState({ error, reload }: { error: { message: string } | null; reload: () => void }) {
  return error && <div className="cash-query-error"><CashNotice error={error.message} /><Button size="sm" variant="secondary" onPress={reload}>重新读取</Button></div>;
}
function ReportEmpty({ loading, failed }: { loading: boolean; failed: boolean }) {
  return <p className="cash-empty" role="status">{loading ? "正在读取账目…" : failed ? "读取失败，请重试。" : "当前条件下暂无记录。"}</p>;
}
function PeriodFilters({ onApply, onReset, children, initial, initialKeyword, activeCount = 0 }: {
  onApply: (params: Period & { keyword: string }) => void; onReset: () => void;
  children?: ReactNode; initial: Period; initialKeyword: string; activeCount?: number;
}) {
  const [dates, setDates] = useState(initial); const [keyword, setKeyword] = useState(initialKeyword);
  const [error, setError] = useState<string | null>(null);
  return <><form className="cash-toolbar cash-filterbar" onSubmit={event => {
    event.preventDefault();
    if (dates.date_from > dates.date_to || (Date.parse(dates.date_to) - Date.parse(dates.date_from)) / 86400000 > 365) {
      setError("查询起止日期须有序，范围不超过 366 天。"); return;
    }
    setError(null); onApply({ ...dates, keyword: keyword.trim() });
  }}>
    <CashInput label="开始日期" type="date" value={dates.date_from} onChange={date_from => setDates(value => ({ ...value, date_from }))} required />
    <CashInput label="结束日期" type="date" value={dates.date_to} onChange={date_to => setDates(value => ({ ...value, date_to }))} required />
    <CashInput label="关键词" value={keyword} onChange={setKeyword} placeholder="搜索内容 / 对象" />
    <Button type="submit" size="sm" variant="secondary">查询</Button><Button size="sm" variant="tertiary" onPress={() => {
      setDates(yearPeriod(currentYear())); setKeyword(""); setError(null); onReset();
    }}>重置</Button>
    {children && <details className="cash-more-filters"><summary>更多筛选{activeCount > 0 ? `（${activeCount}）` : ""}</summary><div className="cash-toolbar">{children}</div></details>}
  </form><CashNotice error={error} /></>;
}
function HistoricalProjectFilter({ period, value, onChange }: {
  period: Period; value: { id: string; name: string } | null; onChange: (value: { id: string; name: string } | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [keyword, setKeyword] = useState(""); const [page, setPage] = useState(1);
  const query = useCashQuery<CashPageRows<{ id: string; name: string }>>(open ? "/reports/project-options" : null, { ...period, keyword: keyword || undefined, page, page_size: 20 });
  return <div className="cash-project-filter"><div className="cash-row-actions"><Button size="sm" variant="tertiary" onPress={() => setOpen(!open)}>历史项目：{value?.name ?? "全部"}</Button>{value && <Button size="sm" variant="tertiary" onPress={() => onChange(null)}>清除项目</Button>}</div>{open && <section className="cash-picker"><CashInput label="搜索现金历史项目" value={keyword} onChange={value => { setKeyword(value); setPage(1); }} /><CashNotice error={query.error?.message} />{query.loading && <p role="status">正在读取历史项目…</p>}{query.data && !query.loading && <><ul className="cash-choice-list">{query.data.rows.map(row => <li key={row.id}><Button size="sm" variant="tertiary" onPress={() => { onChange(row); setOpen(false); }}>{row.name}</Button></li>)}</ul><FinanceTablePagination {...query.data.pagination} pageSize={20} onPageChange={setPage} /></>}</section>}</div>;
}
function SummaryLine({ values }: { values: [string, string | null][] }) { return <dl className="cash-summary-line">{values.map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{cashAmount(value)}</dd></div>)}</dl>; }

const groupLabels: Record<string, string> = { company: "公司", external_person: "外部人员", personal: "个人" };
const collectionLabels: Record<string, string> = { open: "未回款", partial: "部分回款", settled: "已回款" };
const turnoverHeaders = ["日期", "项目", "人员 / 往来对象", "类别", "费用类型", "内容", "收入", "支出", "冲账", "还款", "报账提现", "真实花销", "票抵", "有票回款情况", "本次处理后未结", "备注", "操作"];
function rowColor(row: TurnoverRow) {
  if (row.ledger_group === "company") return "cash-row--company";
  if (row.ledger_group === "external_person") return "cash-row--external-person";
  if (row.ledger_group === "personal") return row.personal_variant === "principal" ? "cash-row--personal-principal" : "cash-row--personal-settlement";
  return "";
}

function TurnoverBook({ onItem, initial, onChange }: { onItem: (id: string) => void; initial: BookCriteria; onChange: (value: BookCriteria) => void }) {
  const [filters, setFilters] = useState<Params>(initial.filters); const [group, setGroup] = useState(initial.group);
  const [state, setState] = useState(String(initial.filters.state ?? "")); const [counterparty, setCounterparty] = useState(String(initial.filters.counterparty ?? "")); const [category, setCategory] = useState(String(initial.filters.category_id ?? ""));
  const [categoryPage, setCategoryPage] = useState(1); const [showCategory, setShowCategory] = useState(false);
  const [page, setPage] = useState(initial.page); const [sort, setSort] = useState(initial.sort); const [order, setOrder] = useState(initial.order);
  const [project, setProject] = useState(initial.project);
  useEffect(() => { onChange({ filters, group: group, page, sort, order, project }); }, [filters, group, page, sort, order, project, onChange]);
  const categories = useCashQuery<CashPageRows<{ id: string; name: string }>>(showCategory ? "/settings/categories" : null, { page: categoryPage, page_size: 50 });
  const query = useCashQuery<Report<TurnoverRow, TurnoverSummary>>("/reports/turnover", { ...filters, ledger_group: group.startsWith("personal_") ? "personal" : group === "all" ? undefined : group, personal_variant: group.startsWith("personal_") ? group.slice(9) : undefined, sort, order, page, page_size: 50 });
  const data = !query.loading && !query.error ? query.data : null;
  useEffect(() => { if (query.data && page > 1 && query.data.rows.length === 0) setPage(Math.max(1, Math.ceil(query.data.pagination.total / 50))); }, [query.data, page]);
  const period = { date_from: String(filters.date_from), date_to: String(filters.date_to) };
  return <>
    <div className="cash-category-switch" role="group" aria-label="往来类别">{[{ id: "all", label: "全部", color: "" }, { id: "company", label: "公司", color: "company" }, { id: "external_person", label: "外部人员", color: "external-person" }, { id: "personal_principal", label: "个人借款 / 代付", color: "personal-principal" }, { id: "personal_settlement", label: "个人归还 / 冲抵", color: "personal-settlement" }].map(option => <Button key={option.id} size="sm" variant={group === option.id ? "secondary" : "tertiary"} aria-pressed={group === option.id} onPress={() => { setGroup(option.id); setPage(1); }}><span className={`cash-color-dot cash-color-dot--${option.color}`} aria-hidden="true" />{option.label}</Button>)}</div>
    <PeriodFilters initial={period} initialKeyword={String(initial.filters.keyword ?? "")} activeCount={[filters.counterparty, filters.state, filters.category_id].filter(Boolean).length} onReset={() => {
      setFilters(yearPeriod(currentYear())); setGroup("all"); setState(""); setCounterparty(""); setCategory(""); setProject(null); setSort("occurred_on"); setOrder("desc"); setPage(1);
    }} onApply={value => { setFilters(old => ({ ...old, ...value, keyword: value.keyword || undefined, counterparty: counterparty || undefined, category_id: category || undefined, state: state || undefined })); setPage(1); }}>
      <CashInput label="往来对象" value={counterparty} onChange={setCounterparty} />
      <CashSelect label="处理状态" value={state} onChange={setState} options={[{ value: "", label: "全部状态" }, { value: "open", label: "未结" }, { value: "partial", label: "部分结算" }, { value: "settled", label: "结清" }]} />
    </PeriodFilters>
    <div className="cash-toolbar cash-secondary-filters"><HistoricalProjectFilter period={period} value={project} onChange={project => { setProject(project); setFilters(old => ({ ...old, project_id: project?.id })); setPage(1); }} /><Button size="sm" variant="tertiary" onPress={() => setShowCategory(!showCategory)}>费用类型</Button><CashSelect label="排序" value={sort} onChange={value => { setSort(value); setPage(1); }} options={[{ value: "occurred_on", label: "日期" }, { value: "original_amount", label: "原始金额" }, { value: "repayment_amount", label: "还款金额" }]} /><Button size="sm" variant="tertiary" onPress={() => { setOrder(order === "desc" ? "asc" : "desc"); setPage(1); }}>{order === "desc" ? "降序 ↓" : "升序 ↑"}</Button><Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button></div>
    {showCategory && <section className="cash-picker"><CashNotice error={categories.error?.message} /><CashSelect label="费用类型" value={category} onChange={value => { setCategory(value); setFilters(old => ({ ...old, category_id: value || undefined })); setPage(1); }} options={[{ value: "", label: "全部费用类型" }, ...(categories.data?.rows.map(row => ({ value: row.id, label: row.name })) ?? [])]} />{categories.data && <FinanceTablePagination {...categories.data.pagination} pageSize={50} onPageChange={setCategoryPage} />}</section>}

    <ReportState error={query.error} reload={query.reload} />
    <FinanceTable ariaLabel="往来账总表" className="cash-main-table cash-turnover-grid" scrollMode="contained" minWidth={1740} selectableText footer={data && <>
      <SummaryLine values={[["收入", data.summary.cash_received_amount as string], ["支出", data.summary.cash_paid_amount as string], ["冲账", data.summary.non_ticket_offset_amount as string], ["还款", data.summary.repayment_amount as string], ["报账提现", data.summary.reimbursement_received_amount as string], ["真实花销", data.summary.real_expense_amount as string], ["票抵", data.summary.ticket_offset_amount as string], ["期末应收未结", data.summary.remaining_obligation_amount.receivable], ["期末应付未结", data.summary.remaining_obligation_amount.payable]]} />
      <FinanceTablePagination {...data.pagination} pageSize={50} onPageChange={setPage} />
    </>}>

        <FinanceTableHeader>{turnoverHeaders.map((label, index) => <FinanceTableColumn key={label} id={`turnover-${index}`} isRowHeader={index === 0} columnRole={index >= 6 && index <= 12 || index === 14 ? "amount" : index === 16 ? "action" : index === 0 ? "date" : index === 2 ? "identity" : index === 3 || index === 13 ? "status" : "description"}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody renderEmptyState={() => <ReportEmpty loading={query.loading} failed={Boolean(query.error)} />}>{(data?.rows ?? []).map(row => <FinanceTableRow key={row.row_id} id={row.row_id} className={rowColor(row)} textValue={`${row.occurred_on} ${row.content}`}>
          <FinanceTableCell columnRole="date">{row.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="description">{row.project?.name_snapshot ?? "无项目"}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.counterparty ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="status">{row.ledger_group ? groupLabels[row.ledger_group] : "—"}{row.ledger_group === "personal" ? row.personal_variant === "principal" ? " · 借出 / 代付" : " · 归还 / 冲抵" : ""}</FinanceTableCell><FinanceTableCell columnRole="description">{row.category?.name ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="description">{row.content}</FinanceTableCell>
          {[row.cash_received_amount, row.cash_paid_amount, row.non_ticket_offset_amount, row.repayment_amount, row.reimbursement_received_amount, row.real_expense_amount, row.ticket_offset_amount].map((value, index) => <FinanceTableCell key={index} columnRole="amount">{cashAmount(value)}</FinanceTableCell>)}
          <FinanceTableCell columnRole="status">{row.ticket_collection_state === null ? "—" : collectionLabels[row.ticket_collection_state]}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.remaining_after_event)}</FinanceTableCell><FinanceTableCell columnRole="description">{row.remark ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" onPress={() => onItem(row.expense_item_id ?? row.item_id)}>详情</Button></FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>
  </>;
}

function TicketBook({ onItem, initial, onChange }: { onItem: (id: string) => void; initial: BookCriteria; onChange: (value: BookCriteria) => void }) {
  const [filters, setFilters] = useState<Params>(initial.filters); const [provider, setProvider] = useState(String(initial.filters.ticket_provider ?? "")); const [state, setState] = useState(String(initial.filters.state ?? ""));
  const [page, setPage] = useState(initial.page); const [sort, setSort] = useState(initial.sort); const [order, setOrder] = useState(initial.order);
  const [project, setProject] = useState(initial.project);
  useEffect(() => { onChange({ filters, group: "all", page, sort, order, project }); }, [filters, page, sort, order, project, onChange]);
  const query = useCashQuery<Report<TicketRow, Record<string, string>>>("/reports/ticket-payments", { ...filters, sort, order, page, page_size: 50 });
  const data = !query.loading && !query.error ? query.data : null;
  useEffect(() => { if (query.data && page > 1 && query.data.rows.length === 0) setPage(Math.max(1, Math.ceil(query.data.pagination.total / 50))); }, [query.data, page]);
  return <><PeriodFilters initial={{ date_from: String(filters.date_from), date_to: String(filters.date_to) }} initialKeyword={String(initial.filters.keyword ?? "")} activeCount={[filters.ticket_provider, filters.state].filter(Boolean).length} onReset={() => {
      setFilters(yearPeriod(currentYear())); setProvider(""); setState(""); setProject(null); setSort("ticket_provided_on"); setOrder("desc"); setPage(1);
    }} onApply={value => { setFilters(old => ({ ...old, ...value, keyword: value.keyword || undefined, ticket_provider: provider || undefined, state: state || undefined })); setPage(1); }}><CashInput label="提供人" value={provider} onChange={setProvider} /><CashSelect label="使用状态" value={state} onChange={setState} options={[{ value: "", label: "全部状态" }, { value: "unused", label: "未使用" }, { value: "partial", label: "部分使用" }, { value: "used", label: "已使用" }]} /></PeriodFilters>
    <div className="cash-toolbar"><HistoricalProjectFilter period={{ date_from: String(filters.date_from), date_to: String(filters.date_to) }} value={project} onChange={project => { setProject(project); setFilters(old => ({ ...old, project_id: project?.id })); setPage(1); }} /><CashSelect label="排序" value={sort} onChange={value => { setSort(value); setPage(1); }} options={[{ value: "ticket_provided_on", label: "提供日期" }, { value: "provided_amount", label: "提供金额" }, { value: "available_source_amount", label: "来源可用金额" }]} /><Button size="sm" variant="tertiary" onPress={() => { setOrder(order === "desc" ? "asc" : "desc"); setPage(1); }}>{order === "desc" ? "降序 ↓" : "升序 ↑"}</Button><Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button></div>
    <ReportState error={query.error} reload={query.reload} />
    <FinanceTable ariaLabel="有票支付" className="cash-main-table cash-tickets-grid" scrollMode="contained" minWidth={1370} footer={data && <><SummaryLine values={[["提供", data.summary.provided_amount], ["使用（含抵债）", data.summary.used_amount], ["票抵", data.summary.offset_amount], ["来源可用", data.summary.available_source_amount], ["明确公司应收", data.summary.receivable_amount], ["实际回款", data.summary.cash_received_amount]]} /><FinanceTablePagination {...data.pagination} pageSize={50} onPageChange={setPage} /></>}><FinanceTableHeader>{["提供日期", "项目", "提供人", "票据 / 用途说明", "提供金额", "已使用", "来源可用", "已抵债", "明确公司应收", "实际回款", "使用状态", "操作"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0} columnRole={index >= 4 && index <= 9 ? "amount" : index === 11 ? "action" : index === 0 ? "date" : "description"}>{label}</FinanceTableColumn>)}</FinanceTableHeader><FinanceTableBody renderEmptyState={() => <ReportEmpty loading={query.loading} failed={Boolean(query.error)} />}>{(data?.rows ?? []).map(row => <FinanceTableRow key={row.id} id={row.id} textValue={row.content}><FinanceTableCell columnRole="date">{row.ticket_provided_on}</FinanceTableCell><FinanceTableCell columnRole="description">{row.project?.name_snapshot ?? "无项目"}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.ticket_provider}</FinanceTableCell><FinanceTableCell columnRole="description">{row.content}</FinanceTableCell>{[row.provided_amount, row.used_amount, row.available_source_amount, row.offset_amount, row.receivable_amount, row.cash_received_amount].map((amount, index) => <FinanceTableCell key={index} columnRole="amount">{cashAmount(amount)}</FinanceTableCell>)}<FinanceTableCell columnRole="status">{{ unused: "未使用", partial: "部分使用", used: "已使用" }[row.state]}</FinanceTableCell><FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" onPress={() => onItem(row.id)}>详情 / 办理</Button></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable>
  </>;
}

function PersonalBook({ onItem, onFlow, initial, onChange }: { onItem: (id: string) => void; onFlow: (id: string) => void; initial: PersonalCriteria; onChange: (value: PersonalCriteria) => void }) {
  const [view, setView] = useState(initial.view); const [year, setYear] = useState(initial.year); const [appliedYear, setAppliedYear] = useState(initial.year); const [keyword, setKeyword] = useState(initial.keyword); const [appliedKeyword, setAppliedKeyword] = useState(initial.keyword);
  const [bill, setBill] = useState(initial.bill); const [billPage, setBillPage] = useState(1); const [showBills, setShowBills] = useState(false); const [project, setProject] = useState(initial.project);
  const [page, setPage] = useState(initial.page); const [order, setOrder] = useState(initial.order); const [drill, setDrill] = useState<{ row: MatrixRow; month: string } | null>(null); const [editing, setEditing] = useState<CashSettlement | null>(null);
  useEffect(() => { onChange({ view, year: appliedYear, keyword: appliedKeyword, bill, project, page, order }); }, [view, appliedYear, appliedKeyword, bill, project, page, order, onChange]);
  const bills = useCashQuery<CashPageRows<{ id: string; bank_name: string; label: string }>>(showBills ? "/settings/bill-labels" : null, { page: billPage, page_size: 50 });
  const query = useCashQuery<Report<MatrixRow | PersonalRow, PersonalSummary>>("/reports/personal", { view, year: appliedYear, keyword: appliedKeyword || undefined, bill_label_id: bill || undefined, project_id: project?.id, page, page_size: 50, order });
  const data = !query.loading && !query.error ? query.data : null;
  useEffect(() => { if (query.data && page > 1 && query.data.rows.length === 0) setPage(Math.max(1, Math.ceil(query.data.pagination.total / 50))); }, [query.data, page]);
  return <>
    <form className="cash-toolbar" onSubmit={event => { event.preventDefault(); setAppliedYear(year); setAppliedKeyword(keyword); setPage(1); }}><CashSelect label="个人专账视图" value={view} onChange={value => { setView(value); setPage(1); }} options={[{ value: "matrix", label: "年度还款矩阵" }, { value: "cash_repayments", label: "现金归还" }, { value: "ticket_offsets", label: "有票直接冲" }, { value: "non_ticket_offsets", label: "无票报销冲抵" }]} /><CashInput label="年份" type="number" value={year} onChange={setYear} required /><CashInput label="关键词" value={keyword} onChange={setKeyword} /><Button size="sm" variant="secondary" type="submit">查询</Button><Button size="sm" variant="tertiary" onPress={() => { setYear(currentYear()); setAppliedYear(currentYear()); setKeyword(""); setAppliedKeyword(""); setBill(""); setProject(null); setOrder("desc"); setPage(1); }}>重置</Button><Button size="sm" variant="tertiary" onPress={() => setShowBills(!showBills)}>银行 / 账单</Button><Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button></form>
    {showBills && <section className="cash-picker"><CashNotice error={bills.error?.message} /><CashSelect label="账单筛选" value={bill} onChange={value => { setBill(value); setPage(1); }} options={[{ value: "", label: "全部账单" }, ...(bills.data?.rows.map(row => ({ value: row.id, label: `${row.bank_name} · ${row.label}` })) ?? [])]} />{bills.data && <FinanceTablePagination {...bills.data.pagination} pageSize={50} onPageChange={setBillPage} />}</section>}
    <HistoricalProjectFilter period={yearPeriod(appliedYear)} value={project} onChange={value => { setProject(value); setPage(1); }} />

    <ReportState error={query.error} reload={query.reload} />
    {data && <>
      {data.summary.coverage.state !== "complete" && <p role="status" className="cash-notice">{data.summary.coverage.state === "unconfigured" ? "个人账起算未配置，完整期初和未结不能确定。请在基础设置配置。" : data.summary.coverage.state === "not_started" ? "所选年份早于个人账起算，金额未知。" : `仅覆盖 ${data.summary.coverage.coverage_start} 起的已知期间，起算前金额未知。`}</p>}
      <SummaryLine values={[["已知年初未结", data.summary.opening_obligation_amount], ["期中起算未结", data.summary.opening_adjustment_amount], ["实际代付 / 新增借款", data.summary.new_principal_amount], ["现金归还", data.summary.cash_repayment_amount], ["有票冲抵", data.summary.ticket_offset_amount], ["无票冲抵", data.summary.non_ticket_offset_amount], ["当前未结", data.summary.remaining_obligation_amount]]} />
    </>}
      {view === "matrix" ? <><h3 className="cash-table-caption">实际代付 / 新增借款</h3><FinanceTable ariaLabel="个人年度还款矩阵" className="cash-main-table cash-personal-grid" scrollMode="contained" minWidth={1430} footer={data && <FinanceTablePagination {...data.pagination} pageSize={50} onPageChange={setPage} />}><FinanceTableHeader><FinanceTableColumn isRowHeader>银行 / 账单</FinanceTableColumn>{Array.from({ length: 12 }, (_, index) => <FinanceTableColumn key={index} columnRole="amount">{index + 1} 月</FinanceTableColumn>)}<FinanceTableColumn columnRole="amount">全年合计</FinanceTableColumn></FinanceTableHeader><FinanceTableBody renderEmptyState={() => <ReportEmpty loading={query.loading} failed={Boolean(query.error)} />}>{((data?.rows ?? []) as MatrixRow[]).map(row => <FinanceTableRow key={row.row_key} id={row.row_key} textValue={row.bill_label?.label ?? "无账单本金"}><FinanceTableCell columnRole="identity">{row.bill_label ? `${row.bill_label.bank_name} · ${row.bill_label.label}` : "无账单本金"}</FinanceTableCell>{row.months.map(month => <FinanceTableCell key={month.month} columnRole="amount">{month.principal_amount === null ? "—" : <Button size="sm" variant="tertiary" aria-label={`${row.bill_label?.label ?? "无账单本金"} ${month.month} 明细`} onPress={() => setDrill({ row, month: month.month })}>{cashAmount(month.principal_amount)}{month.coverage_state === "starts_during_period" ? " *" : ""}</Button>}</FinanceTableCell>)}<FinanceTableCell columnRole="amount">{cashAmount(row.year_principal_amount)}</FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable></> : <><div className="cash-toolbar"><Button size="sm" variant="tertiary" onPress={() => { setOrder(order === "desc" ? "asc" : "desc"); setPage(1); }}>日期 {order === "desc" ? "降序 ↓" : "升序 ↑"}</Button></div><FinanceTable ariaLabel={view === "cash_repayments" ? "个人现金归还" : view === "ticket_offsets" ? "有票直接冲" : "无票报销冲抵"} className="cash-main-table" scrollMode="contained" minWidth={1100} footer={data && <FinanceTablePagination {...data.pagination} pageSize={50} onPageChange={setPage} />}><FinanceTableHeader>{["实际日期", "项目", "往来对象", "归属事项", "账单月份", "处理金额", "来源 / 说明", "操作"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0}>{label}</FinanceTableColumn>)}</FinanceTableHeader><FinanceTableBody renderEmptyState={() => <ReportEmpty loading={query.loading} failed={Boolean(query.error)} />}>{((data?.rows ?? []) as PersonalRow[]).map(row => <FinanceTableRow key={row.id} id={row.id} textValue={`${row.occurred_on} ${row.item_content}`}><FinanceTableCell columnRole="date">{row.occurred_on}</FinanceTableCell><FinanceTableCell columnRole="description">{row.project?.name_snapshot ?? "无项目"}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.counterparty}</FinanceTableCell><FinanceTableCell columnRole="description">{row.item_content}<small>{row.bill_label ? `${row.bill_label.bank_name} · ${row.bill_label.label}` : "无账单"}</small></FinanceTableCell><FinanceTableCell columnRole="date">{row.bill_month ?? "—"}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.amount)}</FinanceTableCell><FinanceTableCell columnRole="description">{row.source_item_content ?? (row.flow_source_kind === "manual" ? "手工现金" : row.flow_source_kind === "monthly_task" ? "任务现金" : "无现金收付")}<small>{row.remark ?? "—"}</small></FinanceTableCell><FinanceTableCell columnRole="action"><div className="cash-actions">{row.item_id && <Button size="sm" variant="tertiary" onPress={() => onItem(row.item_id!)}>事项</Button>}{row.flow_id && <Button size="sm" variant="tertiary" onPress={() => onFlow(row.flow_id!)}>现金</Button>}<Button size="sm" variant="tertiary" onPress={() => setEditing(row)}>更正</Button></div></FinanceTableCell></FinanceTableRow>)}</FinanceTableBody></FinanceTable></>}
    {drill && <AppDrawer open title={`${drill.month} 实际发生本金`} width={760} className="cash-module cash-drawer" onClose={() => setDrill(null)}><CashItemPicker label="本月本金来源" params={{ type: "loan", ledger_group: "personal", is_opening: false, origin_date_from: `${drill.month}-01`, origin_date_to: new Date(Number(drill.month.slice(0, 4)), Number(drill.month.slice(5)), 0).toLocaleDateString("sv-SE"), bill_label_id: drill.row.bill_label?.id, has_bill_label: drill.row.bill_label ? undefined : false, project_id: project?.id }} onSelect={item => { setDrill(null); onItem(item.id); }} /></AppDrawer>}
    {editing && <AppDrawer open title={settlementLabels[editing.kind]} width={760} className="cash-module cash-drawer" onClose={() => setEditing(null)}><CashSettlementEditor settlement={editing} initialKind={editing.kind} onClose={() => setEditing(null)} /></AppDrawer>}
  </>;
}

export default function CashBooks({ initialCriteria, onCriteriaChange }: { initialCriteria?: CashBooksCriteria; onCriteriaChange?: (value: CashBooksCriteria) => void }) {
  const [initial] = useState(() => initialCriteria ?? initialCashBooksCriteria());
  const [turnover, setTurnover] = useState(initial.turnover); const [tickets, setTickets] = useState(initial.tickets); const [personal, setPersonal] = useState(initial.personal);
  const [tab, setTab] = useState(initial.tab);
  useEffect(() => { onCriteriaChange?.({ tab, turnover, tickets, personal }); }, [tab, turnover, tickets, personal, onCriteriaChange]); const [itemId, setItemId] = useState<string | null>(null);
  const [manageItems, setManageItems] = useState(false);
  const [createItem, setCreateItem] = useState<CashItemType | null>(null);
  const [flow, setFlow] = useState<{ id?: string; kind?: "receipt" | "payment" | "transfer"; item?: CashItem; settlementKind?: CashSettlementKind } | null>(null);
  const openFlow = (id: string) => { setItemId(null); setFlow({ id }); };
  const actualFlow = (item: CashItem, kind: CashSettlementKind) => {
    setItemId(null);
    setFlow({ item, settlementKind: kind, kind: kind === "company_collection" || kind === "expense_refund" || (kind === "cash_repayment" && item.obligation_direction === "receivable") ? "receipt" : "payment" });
  };
  return <>
    <div className="cash-book-heading"><CashTabs value={tab} onChange={value => { setTab(value); setItemId(null); setCreateItem(null); setFlow(null); setManageItems(false); }} tabs={[{ id: "turnover", label: "往来账总表" }, { id: "tickets", label: "有票支付" }, { id: "personal", label: "个人专账" }]} /><div className="cash-actions"><Button size="sm" variant="tertiary" onPress={() => setManageItems(true)}>事项管理</Button><Button size="sm" variant="secondary" onPress={() => setCreateItem(tab === "tickets" ? "ticket_source" : "loan")}>{tab === "tickets" ? "登记票据提供" : "新建事项"}</Button></div></div>
    {tab === "turnover" && <TurnoverBook onItem={setItemId} initial={turnover} onChange={setTurnover} />}{tab === "tickets" && <TicketBook onItem={setItemId} initial={tickets} onChange={setTickets} />}{tab === "personal" && <PersonalBook onItem={setItemId} onFlow={openFlow} initial={personal} onChange={setPersonal} />}
    {itemId && <CashItemDetail key={itemId} itemId={itemId} onClose={() => setItemId(null)} onFlow={openFlow} onActualFlow={actualFlow} />}
    {createItem && <CashItemEditor initialType={createItem} onClose={() => setCreateItem(null)} onSaved={setItemId} />}
    {manageItems && <AppDrawer open title="事项管理" width={780} className="cash-module cash-drawer" onClose={() => setManageItems(false)}><CashItemPicker label="全部现金事项" onSelect={item => { setManageItems(false); setItemId(item.id); }} /></AppDrawer>}
    {flow && <CashFlowDrawer open flowId={flow.id} kind={flow.kind} existingItem={flow.item} settlementKind={flow.settlementKind} onClose={() => setFlow(null)} />}
  </>;
}

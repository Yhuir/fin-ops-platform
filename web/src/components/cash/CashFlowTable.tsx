import { Button } from "@heroui/react";
import { useEffect, useState, type ReactNode } from "react";
import { useCashQuery } from "../../features/cash/hooks";
import {
  FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader,
  FinanceTablePagination, FinanceTableRow,
} from "../common/FinanceTable";
import { CashInput, CashNotice, CashSelect } from "./CashUi";
import { cashAmount, cashToday, type CashPageRows } from "./CashItems.types";
import { cashFlowLabels, type CashFlow, type CashFlowSummary } from "./CashFlows.types";
import { CashFlowDrawer } from "./CashFlowDrawer";
import { CashConfigurationSelect } from "./CashFlowSelectors";

export type CashFlowCriteria = {
  keyword: string; date_from: string; date_to: string; account_id: string;
  selectedAccount?: { id: string; name: string } | null;
  kind: string; source: string; order: string; sort: string; page: number;
};
export function initialCashFlowCriteria(scoped = false): CashFlowCriteria {
  return { keyword: "", date_from: scoped ? "" : `${cashToday().slice(0, 4)}-01-01`,
    date_to: scoped ? "" : cashToday(), account_id: "", kind: "", source: "",
    order: "desc", sort: "occurred_on", page: 1 };
}
export default function CashFlowTable({ itemId, taskOccurrenceId, initialCriteria, onCriteriaChange, actions }: {
  itemId?: string; taskOccurrenceId?: string; initialCriteria?: CashFlowCriteria;
  onCriteriaChange?: (value: CashFlowCriteria) => void; actions?: ReactNode;
}) {
  const scoped = Boolean(itemId || taskOccurrenceId);
  const [criteria, setCriteria] = useState(() => initialCriteria ?? initialCashFlowCriteria(scoped));
  const [dateFrom, setDateFrom] = useState(criteria.date_from);
  const [dateTo, setDateTo] = useState(criteria.date_to);
  const [search, setSearch] = useState(criteria.keyword);
  const [detail, setDetail] = useState<string | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [showBalances, setShowBalances] = useState(false);
  const { account_id: account, kind, source, order, sort, page } = criteria;
  const setPage = (page: number) => setCriteria(old => ({ ...old, page }));
  const change = (field: "account_id" | "kind" | "source" | "sort" | "order", value: string) =>
    setCriteria(old => ({ ...old, [field]: value, page: 1 }));
  useEffect(() => { onCriteriaChange?.(criteria); }, [criteria, onCriteriaChange]);
  const { selectedAccount, ...queryCriteria } = criteria;
  const query = useCashQuery<CashPageRows<CashFlow> & { summary: CashFlowSummary }>("/flows", {
    ...queryCriteria, page_size: 50,
    item_id: itemId, task_occurrence_id: taskOccurrenceId,
  });
  const data = !query.loading && !query.error ? query.data : null;
  useEffect(() => {
    if (data && page > 1 && data.rows.length === 0) {
      setCriteria(old => ({ ...old, page: Math.max(1, Math.ceil(data.pagination.total / 50)) }));
    }
  }, [data, page]);
  const reset = () => {
    const value = initialCashFlowCriteria(scoped);
    setDateFrom(value.date_from); setDateTo(value.date_to); setSearch(""); setValidation(null); setCriteria(value);
  };
  const quickPeriod = (from: string) => {
    const today = cashToday();
    setDateFrom(from); setDateTo(today); setValidation(null);
    setCriteria(old => ({ ...old, date_from: from, date_to: today, page: 1 }));
  };
  return <section className="cash-flow-table" aria-label="现金流水">
    <form className="cash-toolbar" onSubmit={event => {
      event.preventDefault();
      if (!(scoped && !dateFrom && !dateTo) && (!dateFrom || !dateTo || dateFrom > dateTo || (Date.parse(dateTo) - Date.parse(dateFrom)) / 86400000 > 365)) { setValidation("查询起止日期须有序，范围不超过 366 天。"); return; }
      setValidation(null); setCriteria(old => ({ ...old, keyword: search.trim(), date_from: dateFrom, date_to: dateTo, page: 1 }));
    }}>
      {!scoped && <div className="cash-row-actions"><Button size="sm" variant="tertiary" onPress={() => quickPeriod(`${cashToday().slice(0, 7)}-01`)}>本月</Button><Button size="sm" variant="tertiary" onPress={() => quickPeriod(`${cashToday().slice(0, 4)}-01-01`)}>本年</Button></div>}
      <CashInput label="起始日期" type="date" value={dateFrom} onChange={setDateFrom} />
      <CashInput label="截止日期" type="date" value={dateTo} onChange={setDateTo} />
      <CashInput label="搜索流水" value={search} onChange={setSearch} placeholder="用途、人员或项目" />
      <Button type="submit" size="sm" variant="secondary">查询</Button>
      <Button size="sm" variant="tertiary" onPress={reset}>重置</Button><Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button><div className="cash-toolbar-actions">{actions}</div>
    </form>
    <div className="cash-toolbar cash-toolbar--compact">
      <CashConfigurationSelect mode="filter" name="accounts" label="账户" value={account} selected={selectedAccount} onChange={(account_id, selectedAccount) => setCriteria(old => ({ ...old, account_id, selectedAccount, page: 1 }))} />
      <CashSelect label="方向" value={kind} onChange={value => change("kind", value)} options={[{ value: "", label: "全部方向" }, { value: "receipt", label: "收入" }, { value: "payment", label: "支出" }, { value: "transfer", label: "内部转账" }]} />
      <CashSelect label="来源" value={source} onChange={value => change("source", value)} options={[{ value: "", label: "全部来源" }, { value: "manual", label: "手动录入" }, { value: "monthly_task", label: "每月任务" }]} />
      <CashSelect label="排序" value={sort} onChange={value => change("sort", value)} options={[{ value: "occurred_on", label: "发生日期" }, { value: "amount", label: "金额" }]} />
      <Button size="sm" variant="tertiary" onPress={() => change("order", order === "desc" ? "asc" : "desc")}>{order === "desc" ? "降序" : "升序"}</Button>
    </div>
    <CashNotice error={validation || query.error?.message} />

    {data && !query.loading && <>
      <div className="cash-summary"><span>筛选合计：收入 {cashAmount(data.summary.filtered_totals.income_amount)}</span><span>支出 {cashAmount(data.summary.filtered_totals.expense_amount)}</span><span>内部转账 {cashAmount(data.summary.filtered_totals.transfer_amount)}</span><Button size="sm" variant="tertiary" aria-expanded={showBalances} onPress={() => setShowBalances(!showBalances)}>账户期间余额</Button></div>
      {data.summary.account_balances.some(row => row.ending_balance?.startsWith("-")) && <p className="cash-hint">部分账户账面为负，请核对或补录。系统不会自动生成收入补平。</p>}
      {showBalances && <FinanceTable ariaLabel="账户期间余额" minWidth={900}>
        <FinanceTableHeader>{["账户", "记账范围", "期间期初", "已知起算余额", "期间转入", "期间转出", "期末余额"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody>{data.summary.account_balances.map(row => <FinanceTableRow key={row.account_id} id={row.account_id}>
          <FinanceTableCell columnRole="identity">{row.account_name}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.coverage_state === "complete" ? "完整期间" : row.coverage_state === "not_started" ? "尚未起算，余额未知" : `自 ${row.coverage_start} 起`}</FinanceTableCell>
          {[row.opening_balance, row.balance_at_coverage_start, row.period_inflow, row.period_outflow, row.ending_balance].map((value, index) => <FinanceTableCell key={index} columnRole="amount">{cashAmount(value)}</FinanceTableCell>)}
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>}
    </>}
      <FinanceTable ariaLabel="现金流水明细" className="cash-main-table cash-flows-grid" scrollMode={scoped ? "natural" : "contained"} minWidth={1340} selectableText footer={
        data && <FinanceTablePagination page={page} pageSize={50} total={data.pagination.total} onPageChange={setPage} />
      }>
        <FinanceTableHeader>{["日期", "账户", "项目", "人员", "分类", "用途", "收入", "支出", "互转金额", "来源 / 任务", "账户余额", "操作"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0} columnRole={index >= 6 && index <= 8 || index === 10 ? "amount" : index === 11 ? "action" : index === 0 ? "date" : index === 1 ? "account" : "description"}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody renderEmptyState={() => <p className="cash-empty" role="status">{query.loading ? "正在读取现金流水…" : query.error ? "读取失败，请刷新重试。" : "该范围内没有现金流水。可调整日期查看历史，或新增实际收付。"}</p>}>{(data?.rows ?? []).map(row => <FinanceTableRow key={row.id} id={row.id} textValue={row.content}>
          <FinanceTableCell columnRole="date">{row.occurred_on}</FinanceTableCell>
          <FinanceTableCell columnRole="account">{row.from_account?.name}{row.kind === "transfer" ? " → " : ""}{row.to_account?.name}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.project === null ? "无项目" : row.project.name_snapshot}</FinanceTableCell>
          <FinanceTableCell columnRole="identity">{row.person_name === null ? "—" : row.person_name}</FinanceTableCell>
          <FinanceTableCell columnRole="status">{row.category === null ? cashFlowLabels[row.kind] : row.category.name}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.content}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{cashAmount(row.income_amount)}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{cashAmount(row.expense_amount)}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{row.kind === "transfer" ? cashAmount(row.amount) : "—"}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.source_kind === "manual" ? "手动录入" : "每月任务"}{row.task && <small>{row.task.month} · {row.task.title}</small>}</FinanceTableCell>
          <FinanceTableCell columnRole="amount">{cashAmount(row.account_running_balance)}</FinanceTableCell>
          <FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" onPress={() => setDetail(row.id)}>详情</Button></FinanceTableCell>
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>

    {detail && <CashFlowDrawer open flowId={detail} onClose={() => setDetail(null)} />}
  </section>;
}

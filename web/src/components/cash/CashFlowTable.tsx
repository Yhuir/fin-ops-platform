import { Button } from "@heroui/react";
import { useState } from "react";
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

export default function CashFlowTable({ itemId, taskOccurrenceId }: { itemId?: string; taskOccurrenceId?: string }) {
  const [dateFrom, setDateFrom] = useState(`${cashToday().slice(0, 4)}-01-01`);
  const [dateTo, setDateTo] = useState(cashToday());
  const [search, setSearch] = useState("");
  const [filters, setFilters] = useState({ keyword: "", date_from: dateFrom, date_to: dateTo });
  const [account, setAccount] = useState(""); const [kind, setKind] = useState(""); const [source, setSource] = useState("");
  const [order, setOrder] = useState("desc"); const [sort, setSort] = useState("occurred_on");
  const [page, setPage] = useState(1); const [detail, setDetail] = useState<string | null>(null);
  const [validation, setValidation] = useState<string | null>(null);
  const [showBalances, setShowBalances] = useState(false);
  const query = useCashQuery<CashPageRows<CashFlow> & { summary: CashFlowSummary }>("/flows", {
    ...filters, account_id: account, kind, source, page, page_size: 50, sort, order,
    item_id: itemId, task_occurrence_id: taskOccurrenceId,
  });
  return <section className="cash-flow-table" aria-label="现金流水">
    <form className="cash-toolbar" onSubmit={event => {
      event.preventDefault();
      if (!dateFrom || !dateTo || dateFrom > dateTo || (Date.parse(dateTo) - Date.parse(dateFrom)) / 86400000 > 365) { setValidation("查询起止日期须有序，范围不超过 366 天。"); return; }
      setValidation(null); setFilters({ keyword: search, date_from: dateFrom, date_to: dateTo }); setPage(1);
    }}>
      <CashInput label="起始日期" type="date" value={dateFrom} onChange={setDateFrom} />
      <CashInput label="截止日期" type="date" value={dateTo} onChange={setDateTo} />
      <CashInput label="搜索流水" value={search} onChange={setSearch} placeholder="用途、人员或项目" />
      <Button type="submit" size="sm" variant="secondary">查询</Button>
      <Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button>
    </form>
    <div className="cash-toolbar cash-toolbar--compact">
      <CashConfigurationSelect name="accounts" label="账户" value={account} onChange={value => { setAccount(value); setPage(1); }} />
      {account && <Button size="sm" variant="tertiary" onPress={() => { setAccount(""); setPage(1); }}>全部账户</Button>}
      <CashSelect label="方向" value={kind} onChange={value => { setKind(value); setPage(1); }} options={[{ value: "receipt", label: "收入" }, { value: "payment", label: "支出" }, { value: "transfer", label: "内部转账" }]} />
      {kind && <Button size="sm" variant="tertiary" onPress={() => { setKind(""); setPage(1); }}>全部方向</Button>}
      <CashSelect label="来源" value={source} onChange={value => { setSource(value); setPage(1); }} options={[{ value: "manual", label: "手动录入" }, { value: "monthly_task", label: "每月任务" }]} />
      {source && <Button size="sm" variant="tertiary" onPress={() => { setSource(""); setPage(1); }}>全部来源</Button>}
      <CashSelect label="排序" value={sort} onChange={value => { setSort(value); setPage(1); }} options={[{ value: "occurred_on", label: "发生日期" }, { value: "amount", label: "金额" }]} />
      <Button size="sm" variant="tertiary" onPress={() => { setOrder(order === "desc" ? "asc" : "desc"); setPage(1); }}>{order === "desc" ? "降序" : "升序"}</Button>
    </div>
    <CashNotice error={validation || query.error?.message} />
    {query.loading && <p role="status">正在读取现金流水…</p>}
    {query.data && !query.loading && <>
      <div className="cash-summary"><span>筛选合计：收入 {cashAmount(query.data.summary.filtered_totals.income_amount)}</span><span>支出 {cashAmount(query.data.summary.filtered_totals.expense_amount)}</span><span>内部转账 {cashAmount(query.data.summary.filtered_totals.transfer_amount)}</span><Button size="sm" variant="tertiary" aria-expanded={showBalances} onPress={() => setShowBalances(!showBalances)}>账户期间余额</Button></div>
      {query.data.summary.account_balances.some(row => row.ending_balance?.startsWith("-")) && <p className="cash-hint">部分账户账面为负，请核对或补录。系统不会自动生成收入补平。</p>}
      {showBalances && <FinanceTable ariaLabel="账户期间余额" minWidth={900}>
        <FinanceTableHeader>{["账户", "记账范围", "期间期初", "已知起算余额", "期间转入", "期间转出", "期末余额"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody>{query.data.summary.account_balances.map(row => <FinanceTableRow key={row.account_id} id={row.account_id}>
          <FinanceTableCell columnRole="identity">{row.account_name}</FinanceTableCell>
          <FinanceTableCell columnRole="description">{row.coverage_state === "complete" ? "完整期间" : row.coverage_state === "not_started" ? "尚未起算，余额未知" : `自 ${row.coverage_start} 起`}</FinanceTableCell>
          {[row.opening_balance, row.balance_at_coverage_start, row.period_inflow, row.period_outflow, row.ending_balance].map((value, index) => <FinanceTableCell key={index} columnRole="amount">{cashAmount(value)}</FinanceTableCell>)}
        </FinanceTableRow>)}</FinanceTableBody>
      </FinanceTable>}
      <FinanceTable ariaLabel="现金流水明细" minWidth={1350} selectableText>
        <FinanceTableHeader>{["日期", "账户", "项目", "人员", "分类", "用途", "收入", "支出", "互转金额", "来源 / 任务", "账户余额", "操作"].map((label, index) => <FinanceTableColumn key={label} isRowHeader={index === 0}>{label}</FinanceTableColumn>)}</FinanceTableHeader>
        <FinanceTableBody>{query.data.rows.map(row => <FinanceTableRow key={row.id} id={row.id} textValue={row.content}>
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
      {query.data.rows.length === 0 && <p className="cash-empty">该范围内没有现金流水。可调整日期查看历史，或新增实际收付。</p>}
      <FinanceTablePagination page={page} pageSize={50} total={query.data.pagination.total} onPageChange={setPage} />
    </>}
    {detail && <CashFlowDrawer open flowId={detail} onClose={() => setDetail(null)} />}
  </section>;
}

import { Button } from "@heroui/react";
import { useEffect, useState } from "react";
import { cashQueryError } from "../../features/cash/api";
import { useCashQuery } from "../../features/cash/hooks";
import { FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn, FinanceTableHeader, FinanceTablePagination, FinanceTableRow } from "../common/FinanceTable";
import { CashColumnHeader, CashFilterPopover, CashTextFilter, type CashFilterOption, type CashFilterValue } from "./CashFilters";
import { CashHistoricalProjectFilter } from "./CashFlowSelectors";
import { cashAmount, cashToday, type CashPageRows, type CashProject } from "./CashItems.types";
import { CashInput, CashNotice } from "./CashUi";

export type CashUnsettledCriteria = { date_to: string; keyword: string; counterparty: string; group: string; projects: CashFilterValue[]; selected: CashFilterOption[]; page: number; sort: string; order: "asc" | "desc" };
export const initialUnsettledCriteria = (): CashUnsettledCriteria => ({ date_to: cashToday(), keyword: "", counterparty: "", group: "", projects: [], selected: [], page: 1, sort: "origin_date", order: "desc" });
type UnsettledRow = { item_id: string; version: number; type: string; origin_date: string; ledger_group: string; counterparty: string; project: CashProject; content: string; obligation_direction: string; original_amount: string; settled_amount: string; remaining_amount: string };
type UnsettledReport = CashPageRows<UnsettledRow> & { view: "unsettled"; summary: { item_count: number; remaining_obligation_amount: { receivable: string; payable: string } } };
const groups = [{ value: "company", label: "公司" }, { value: "external_person", label: "外部人员" }, { value: "personal", label: "个人" }];

export function CashUnsettledBook({ initial, onChange, onItem }: { initial: CashUnsettledCriteria; onChange: (value: CashUnsettledCriteria) => void; onItem: (id: string) => void }) {
  const [criteria, setCriteria] = useState(initial);
  const [date, setDate] = useState(initial.date_to); const [keyword, setKeyword] = useState(initial.keyword);
  const [error, setError] = useState<string | null>(null);
  const params = (value: CashUnsettledCriteria) => ({ view: "unsettled", date_to: value.date_to, keyword: value.keyword, counterparty: value.counterparty, ledger_group: value.group || undefined, project_ids: value.projects, page: value.page, page_size: 50, sort: value.sort, order: value.order });
  const query = useCashQuery<UnsettledReport>("/reports/turnover", params(criteria));
  const data = !query.loading && !query.error ? query.data : null;
  useEffect(() => { onChange(criteria); }, [criteria, onChange]);
  useEffect(() => { if (query.data && criteria.page > 1 && query.data.rows.length === 0) setCriteria(old => ({ ...old, page: Math.max(1, Math.ceil(query.data!.pagination.total / 50)) })); }, [query.data, criteria.page]);
  function apply(patch: Partial<CashUnsettledCriteria>) {
    const next = { ...criteria, page: 1, ...patch }; const validation = cashQueryError(params(next));
    if (!validation) setCriteria(next);
    return validation;
  }
  return <>
    <form className="cash-toolbar cash-filterbar" onSubmit={event => { event.preventDefault(); setError(!date || date > cashToday() ? "截至日期须不晚于今天。" : apply({ date_to: date, keyword: keyword.trim() })); }}>
      <CashInput label="截至日期" type="date" value={date} onChange={setDate} required />
      <CashInput label="事项关键词" value={keyword} onChange={setKeyword} placeholder="搜索已登记的未结事项" />
      <Button type="submit" size="sm" variant="secondary">查询</Button>
      <Button size="sm" variant="tertiary" onPress={() => { const initial = initialUnsettledCriteria(); setCriteria(initial); setDate(initial.date_to); setKeyword(""); setError(null); }}>重置</Button>
      <Button size="sm" variant="tertiary" onPress={query.reload}>刷新</Button>
    </form>
    <p className="cash-hint">截至 {criteria.date_to} 的已登记未结事项，包含本期没有处理的旧欠款。详情显示当前可办理额。</p>
    <CashNotice error={error ?? query.error?.message} />{query.error && <Button size="sm" variant="secondary" onPress={query.reload}>重新读取</Button>}
    <FinanceTable ariaLabel="截至期末未结事项" className="cash-main-table" scrollMode="contained" minWidth={1160}
      sortDescriptor={{ column: criteria.sort, direction: criteria.order === "asc" ? "ascending" : "descending" }} onSortChange={value => setError(apply({ sort: String(value.column), order: value.direction === "ascending" ? "asc" : "desc" }))}
      footer={data && <><dl className="cash-summary-line"><div><dt>未结事项</dt><dd>{data.summary.item_count}</dd></div><div><dt>截至期末应收未结</dt><dd>{cashAmount(data.summary.remaining_obligation_amount.receivable)}</dd></div><div><dt>截至期末应付未结</dt><dd>{cashAmount(data.summary.remaining_obligation_amount.payable)}</dd></div></dl><FinanceTablePagination {...data.pagination} pageSize={50} onPageChange={page => setError(apply({ page }))} /></>}>
      <FinanceTableHeader>
        <FinanceTableColumn id="origin_date" isRowHeader allowsSorting>事项日期</FinanceTableColumn>
        <FinanceTableColumn id="project"><CashColumnHeader label="项目"><CashHistoricalProjectFilter column label="项目" scope={{ date_to: criteria.date_to }} value={criteria.projects} selected={criteria.selected} onApply={(projects, selected) => apply({ projects, selected })} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="counterparty" allowsSorting><CashColumnHeader label="往来对象"><CashTextFilter label="往来对象" value={criteria.counterparty} onApply={counterparty => apply({ counterparty })} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="group"><CashColumnHeader label="类别"><CashFilterPopover column label="往来类别" options={groups} value={criteria.group ? [criteria.group] : []} onApply={value => value.length > 1 ? "本视图请选择一个往来类别；清空可查看全部。" : apply({ group: value[0] ?? "" })} /></CashColumnHeader></FinanceTableColumn>
        <FinanceTableColumn id="content">事项内容</FinanceTableColumn><FinanceTableColumn id="direction">方向</FinanceTableColumn>
        <FinanceTableColumn id="original" columnRole="amount">原始金额</FinanceTableColumn><FinanceTableColumn id="settled" columnRole="amount">截至日已结</FinanceTableColumn>
        <FinanceTableColumn id="remaining_amount" columnRole="amount" allowsSorting>截至日未结</FinanceTableColumn><FinanceTableColumn id="actions">操作</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody renderEmptyState={() => <p className="cash-empty" role="status">{query.loading ? "正在读取未结事项…" : query.error ? "读取失败，请重试。" : "该范围没有已登记的未结事项。"}</p>}>{(data?.rows ?? []).map(row => <FinanceTableRow key={row.item_id} id={row.item_id} textValue={row.content} className={row.ledger_group === "company" ? "cash-row--company" : row.ledger_group === "external_person" ? "cash-row--external-person" : "cash-row--personal-principal"}>
        <FinanceTableCell columnRole="date">{row.origin_date}</FinanceTableCell><FinanceTableCell columnRole="description">{row.project?.name_snapshot ?? "无项目"}</FinanceTableCell><FinanceTableCell columnRole="identity">{row.counterparty}</FinanceTableCell><FinanceTableCell columnRole="status">{groups.find(group => group.value === row.ledger_group)?.label}</FinanceTableCell><FinanceTableCell columnRole="description">{row.content}</FinanceTableCell><FinanceTableCell columnRole="status">{row.obligation_direction === "receivable" ? "应收 / 对方应还" : "应付 / 我方应还"}</FinanceTableCell>
        <FinanceTableCell columnRole="amount">{cashAmount(row.original_amount)}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.settled_amount)}</FinanceTableCell><FinanceTableCell columnRole="amount">{cashAmount(row.remaining_amount)}</FinanceTableCell><FinanceTableCell columnRole="action"><Button size="sm" variant="tertiary" onPress={() => onItem(row.item_id)}>详情 / 办理</Button></FinanceTableCell>
      </FinanceTableRow>)}</FinanceTableBody>
    </FinanceTable>
  </>;
}

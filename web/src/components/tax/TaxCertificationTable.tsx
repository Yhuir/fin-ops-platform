import { useEffect, useRef, type ComponentProps } from "react";
import { FinanceTable, FinanceTableHeader, FinanceTableColumn, FinanceTableBody, FinanceTableRow, FinanceTableCell, FinanceStatusTag, FinanceTablePagination } from "../common/FinanceTable";
import { formatTaxMoney } from "../../features/tax/format";
import type { TaxCertificationQuery, TaxCertificationResult } from "../../features/tax/types";

export default function TaxCertificationTable({ result, query, loading, error = false, onPageChange, onSortChange }: {
  result: TaxCertificationResult | null; query: TaxCertificationQuery; loading: boolean; error?: boolean;
  onPageChange: (page: number) => void;
  onSortChange: NonNullable<ComponentProps<typeof FinanceTable>["onSortChange"]>;
}) {
  const scrollRef = useRef<HTMLDivElement>(null);
  useEffect(() => { if (scrollRef.current) scrollRef.current.scrollTop = 0; }, [query]);
  return <FinanceTable ariaLabel="专票认证明细" minWidth={1160} selectableText scrollMode="contained" scrollRef={scrollRef}
    sortDescriptor={{ column: query.sort_by, direction: query.sort_direction === "asc" ? "ascending" : "descending" }} onSortChange={onSortChange}
    footer={<><span className="tax-certification-unit">当前筛选汇总 · 金额单位：元</span>{result ? <FinanceTablePagination page={result.page} pageSize={result.page_size} total={result.total} onPageChange={onPageChange} isDisabled={loading} /> : null}</>}>
    <FinanceTableHeader>
      <FinanceTableColumn id="number" columnRole="identity" isRowHeader>发票号码</FinanceTableColumn>
      <FinanceTableColumn id="seller" columnRole="account">销方名称</FinanceTableColumn>
      <FinanceTableColumn id="issue_date" columnRole="date" allowsSorting>开票日期 <span aria-hidden="true">{query.sort_by === "issue_date" ? query.sort_direction === "asc" ? "↑" : "↓" : "↕"}</span></FinanceTableColumn>
      <FinanceTableColumn id="amount" columnRole="amount">金额</FinanceTableColumn>
      <FinanceTableColumn id="tax" columnRole="amount">原票税额</FinanceTableColumn>
      <FinanceTableColumn id="status" columnRole="status">认证状态</FinanceTableColumn>
      <FinanceTableColumn id="deductible_tax" columnRole="amount">有效抵扣税额</FinanceTableColumn>
      <FinanceTableColumn id="selection_time" columnRole="date" allowsSorting>勾选时间 <span aria-hidden="true">{query.sort_by === "selection_time" ? query.sort_direction === "asc" ? "↑" : "↓" : "↕"}</span></FinanceTableColumn>
    </FinanceTableHeader>
    <FinanceTableBody renderEmptyState={() => loading ? "正在加载专票…" : error ? "专票加载失败，请重试" : query.status === "uncertified" && (query.selection_year || query.selection_month) ? "未认证专票没有勾选时间，请调整勾选期间" : "暂无专票"}>{(result?.rows ?? []).map(row => <FinanceTableRow key={row.id} id={row.id}>
      <FinanceTableCell columnRole="identity">{row.digital_invoice_no || row.invoice_no || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="account">{row.seller_name || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="date">{row.issue_date || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="amount">{formatTaxMoney(row.amount)}</FinanceTableCell>
      <FinanceTableCell columnRole="amount">{formatTaxMoney(row.tax_amount)}</FinanceTableCell>
      <FinanceTableCell columnRole="status"><FinanceStatusTag tone={row.certification_status === "certified" ? "success" : "neutral"}>{row.certification_status === "certified" ? "已认证" : "未认证"}</FinanceStatusTag></FinanceTableCell>
      <FinanceTableCell columnRole="amount" className={row.certification_status === "certified" ? "tax-certification-deductible" : undefined}>{formatTaxMoney(row.deductible_tax_amount)}</FinanceTableCell>
      <FinanceTableCell columnRole="date">{row.selection_time || "—"}</FinanceTableCell>
    </FinanceTableRow>)}</FinanceTableBody>
  </FinanceTable>;
}

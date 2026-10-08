import type { ComponentProps } from "react";
import { FinanceTable, FinanceTableHeader, FinanceTableColumn, FinanceTableBody, FinanceTableRow, FinanceTableCell, FinanceStatusTag, FinanceTablePagination } from "../common/FinanceTable";
import { formatMoney } from "../../features/money";
import type { TaxCertificationQuery, TaxCertificationResult } from "../../features/tax/types";

export default function TaxCertificationTable({ result, query, loading, onPageChange, onSortChange }: {
  result: TaxCertificationResult; query: TaxCertificationQuery; loading: boolean;
  onPageChange: (page: number) => void;
  onSortChange: NonNullable<ComponentProps<typeof FinanceTable>["onSortChange"]>;
}) {
  return <FinanceTable ariaLabel="专票认证明细" minWidth={1030} selectableText
    sortDescriptor={{ column: query.sort_by, direction: query.sort_direction === "asc" ? "ascending" : "descending" }} onSortChange={onSortChange}
    footer={<FinanceTablePagination page={result.page} pageSize={result.page_size} total={result.total} onPageChange={onPageChange} isDisabled={loading} />}>
    <FinanceTableHeader>
      <FinanceTableColumn id="number" columnRole="identity" isRowHeader>发票号码</FinanceTableColumn>
      <FinanceTableColumn id="seller" columnRole="account">销方名称</FinanceTableColumn>
      <FinanceTableColumn id="issue_date" columnRole="date" allowsSorting>开票日期 <span aria-hidden="true">{query.sort_by === "issue_date" ? query.sort_direction === "asc" ? "↑" : "↓" : "↕"}</span></FinanceTableColumn>
      <FinanceTableColumn id="amount" columnRole="amount">金额</FinanceTableColumn>
      <FinanceTableColumn id="tax" columnRole="amount">税额</FinanceTableColumn>
      <FinanceTableColumn id="status" columnRole="status">认证状态</FinanceTableColumn>
      <FinanceTableColumn id="selection_time" columnRole="date" allowsSorting>勾选时间 <span aria-hidden="true">{query.sort_by === "selection_time" ? query.sort_direction === "asc" ? "↑" : "↓" : "↕"}</span></FinanceTableColumn>
    </FinanceTableHeader>
    <FinanceTableBody renderEmptyState={() => "暂无专票"}>{result.rows.map(row => <FinanceTableRow key={row.id} id={row.id}>
      <FinanceTableCell columnRole="identity">{row.digital_invoice_no || row.invoice_no || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="account">{row.seller_name || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="date">{row.issue_date || "—"}</FinanceTableCell>
      <FinanceTableCell columnRole="amount">{formatMoney(row.amount, "—")}</FinanceTableCell>
      <FinanceTableCell columnRole="amount">{formatMoney(row.tax_amount, "—")}</FinanceTableCell>
      <FinanceTableCell columnRole="status"><FinanceStatusTag tone={row.certification_status === "certified" ? "success" : "neutral"}>{row.certification_status === "certified" ? "已认证" : "未认证"}</FinanceStatusTag></FinanceTableCell>
      <FinanceTableCell columnRole="date">{row.selection_time || "—"}</FinanceTableCell>
    </FinanceTableRow>)}</FinanceTableBody>
  </FinanceTable>;
}

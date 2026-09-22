import type { ImportReviewCategory, ImportReviewRowsPage } from "../../features/imports/types";
import { formatMoney } from "../../features/money";
import {
  FinanceTable, FinanceTableBody, FinanceTableCell, FinanceTableColumn,
  FinanceTableHeader, FinanceTablePagination, FinanceTableRow,
} from "../common/FinanceTable";

const CATEGORY_LABELS: Record<ImportReviewCategory, string> = {
  review: "需检查", new: "新增项", existing: "App 内已存在", batch_duplicate: "本批重复",
};
const FIELD_LABELS: Record<string, string> = {
  amount: "金额", tax_amount: "税额", total_with_tax: "价税合计", invoice_date: "开票日期",
  invoice_type: "发票类型", seller_tax_no: "销方税号", buyer_tax_no: "购方税号",
};

export default function ImportReviewTable({ rows, loading, invoiceMode, page, pageSize, total, onPageChange }: {
  rows: ImportReviewRowsPage["rows"]; loading: boolean; invoiceMode: boolean;
  page: number; pageSize: number; total: number; onPageChange: (page: number) => void;
}) {
  return (
    <FinanceTable className="import-review-table" ariaLabel="导入文件全部明细" minWidth={920} footer={total > pageSize ? (
      <FinanceTablePagination compact isDisabled={loading} onPageChange={onPageChange} page={page} pageSize={pageSize} total={total} />
    ) : null}>
      <FinanceTableHeader>
        <FinanceTableColumn id="row" columnRole="quantity" isRowHeader>行号</FinanceTableColumn>
        <FinanceTableColumn id="status" columnRole="status">状态</FinanceTableColumn>
        <FinanceTableColumn id="identity" columnRole="identity">{invoiceMode ? "发票号码 / 日期" : "账户 / 交易时间"}</FinanceTableColumn>
        <FinanceTableColumn id="party" columnRole="description">{invoiceMode ? "销方 / 购方" : "对方户名 / 收支"}</FinanceTableColumn>
        <FinanceTableColumn id="amount" columnRole="amount">{invoiceMode ? "金额 / 税额 / 价税合计" : "金额"}</FinanceTableColumn>
        <FinanceTableColumn id="reason" columnRole="description">检查内容</FinanceTableColumn>
      </FinanceTableHeader>
      <FinanceTableBody>
        {rows.length === 0 ? (
          <FinanceTableRow id="empty" textValue={loading ? "正在加载" : "无明细"}>
            {Array.from({ length: 6 }, (_, index) => <FinanceTableCell key={index} columnRole="description">{index === 0 ? (loading ? "正在加载…" : "无明细") : ""}</FinanceTableCell>)}
          </FinanceTableRow>
        ) : rows.map((row) => (
          <FinanceTableRow key={row.id} id={row.id} className={`import-review-row--${row.category}`} textValue={`第 ${row.rowNo} 行 ${CATEGORY_LABELS[row.category]}`}>
            <FinanceTableCell columnRole="quantity">{row.rowNo}</FinanceTableCell>
            <FinanceTableCell columnRole="status">{CATEGORY_LABELS[row.category]}</FinanceTableCell>
            <FinanceTableCell columnRole="identity">
              <div className="import-review-identity">{invoiceMode ? row.invoiceNo : row.accountNo}</div>
              <div>{invoiceMode ? row.invoiceDate : row.tradeTime}</div>
            </FinanceTableCell>
            <FinanceTableCell columnRole="description">
              {invoiceMode ? <><div>销方：{row.sellerName || "—"}</div><div>购方：{row.buyerName || "—"}</div></>
                : <><div>{row.counterpartyName || "—"}</div><div>{["income", "inflow"].includes(row.direction ?? "") ? "收入" : ["expense", "outflow"].includes(row.direction ?? "") ? "支出" : row.direction}</div></>}
            </FinanceTableCell>
            <FinanceTableCell columnRole="amount">
              <div className="import-review-money">{formatMoney(row.amount, "—")}</div>
              {invoiceMode ? <><div className="import-review-money">税额 {formatMoney(row.taxAmount, "—")}</div><div className="import-review-money">合计 {formatMoney(row.totalWithTax, "—")}</div></> : null}
            </FinanceTableCell>
            <FinanceTableCell columnRole="description">
              {row.conflicts.length > 0 ? (
                <details className="import-review-conflicts">
                  <summary>{row.conflicts.map((conflict) => FIELD_LABELS[conflict.field]).join("、")}不一致</summary>
                  {row.conflicts.map((conflict) => <div key={conflict.field} className="import-review-conflict">
                    <strong>{FIELD_LABELS[conflict.field]}</strong>
                    <div>文件：{conflict.fileValue}</div><div>App 当前：{conflict.currentValue}</div>
                  </div>)}
                  {row.currentSource ? <p>App 来源：{row.currentSource}</p> : null}
                  <p>请核对原票。修正文件或 App 来源后重新预览。</p>
                </details>
              ) : row.category === "review" ? <div>{row.decisionReason || "请核对来源后重新预览。"}</div>
                : row.decision === "status_updated" ? "确认后更新状态"
                : row.category === "batch_duplicate" ? "同批已有相同记录，不重复新增"
                : row.category === "new" ? "确认成功后写入" : "不重复新增"}
            </FinanceTableCell>
          </FinanceTableRow>
        ))}
      </FinanceTableBody>
    </FinanceTable>
  );
}
